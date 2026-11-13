"""Health profile: a short form the patient fills in after their first login. (Core backend)

GET  /patients/{id}/profile       -> the patient's current answers (see profile_out)
PUT  /patients/{id}/profile       body {"dob", "sex", "blood_group", "allergy_answer", "allergies"}
POST /patients/{id}/profile/skip  "Do it later": the form is not shown again by itself

Questions: date of birth, sex, blood group (or "I don't know"), allergies with their reaction
(or "No known allergies", or "I don't know").

How the answers are stored: as ordinary facts in one document per patient, "{id}_profile"
(doc_type patient_profile, no file). The quote of each fact is the patient's own answer, e.g.
"Allergy: Penicillin (reaction: rash)". So, with no extra code elsewhere:
  - the doctor sees them in the timeline, brief and check-a-medicine
  - recompute gives them the patient_reported badge, and they never count as an
    independent document (backend/recompute.py)
  - "No known allergies" vs an allergy in a document (or the other way round) is flagged as a
    contradiction and becomes an Open Question, like any other conflict
  - "I don't know" stores nothing: not documented stays not documented
Each save is written to the audit log with the full answers, so earlier answers are kept.

Only the patient can read or save their own profile (a doctor sees the facts, not the form).
The patients table (used by the wrong-patient check) is only filled where it is empty, so a
typed answer never overrides what was there already.
"""
import re
from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import get_current_user, require_patient_access
from backend.db import fact_from_row, get_conn, log_action

router = APIRouter()

BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
PROFILE_DOC_TYPE = "patient_profile"
PROFILE_FILENAME = "Health profile (filled in by the patient)"


def profile_document_id(patient_id):
    return f"{patient_id}_profile"


class Allergy(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    reaction: Optional[str] = Field(default=None, max_length=80)


class ProfileBody(BaseModel):
    dob: Optional[str] = None  # YYYY-MM-DD, None = not answered
    sex: Optional[Literal["Female", "Male", "Other"]] = None
    blood_group: Optional[Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]] = None  # None = I don't know
    allergy_answer: Optional[Literal["yes", "none", "dont_know"]] = None
    allergies: List[Allergy] = Field(default_factory=list, max_length=20)


# ---------- helpers ----------

def _own_patient(user, patient_id):
    """Only the patient themself fills in or reads the form."""
    access = require_patient_access(user, patient_id)
    if user["role"] != "patient" or access.get("kind") != "own":
        raise HTTPException(status_code=403, detail="Only the patient can fill in their health profile")


def _clean(text):
    return re.sub(r"\s+", " ", (text or "").strip())


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "item"


def _check_dob(dob):
    try:
        d = date.fromisoformat(dob)
    except ValueError:
        raise HTTPException(status_code=422, detail="Date of birth must look like 1952-06-14")
    if d > date.today() or d.year < 1900:
        raise HTTPException(status_code=422, detail="Date of birth must be between 1900 and today")
    return d.isoformat()


def answers_to_facts(body):
    """The answers as [(key, type, name, value, status, quote)], in form order. Pure, no database."""
    rows = []
    if body.dob:
        dob = _check_dob(body.dob)
        rows.append(("dob", "demographic", "dob", dob, "documented", f"Date of birth: {dob}"))
    if body.sex:
        rows.append(("sex", "demographic", "sex", body.sex, "documented", f"Sex: {body.sex}"))
    if body.blood_group:
        rows.append(("blood_group", "demographic", "blood_group", body.blood_group, "documented",
                     f"Blood group: {body.blood_group}"))
    if body.allergy_answer == "yes":
        seen = set()
        for a in body.allergies:
            name, reaction = _clean(a.name), _clean(a.reaction) or None
            key = "allergy_" + _slug(name)
            if not name or key in seen:
                continue
            seen.add(key)
            quote = f"Allergy: {name}" + (f" (reaction: {reaction})" if reaction else "")
            rows.append((key, "allergy", name, reaction, "documented", quote))
        if not seen:
            raise HTTPException(status_code=422, detail="Add at least one allergy, or choose another answer")
    elif body.allergy_answer == "none":
        rows.append(("no_known_allergies", "allergy", "No known allergies", None, "negated", "No known allergies"))
    return rows


def _profile_facts(conn, patient_id):
    return [fact_from_row(r) for r in conn.execute(
        "SELECT * FROM facts WHERE document_id = ? ORDER BY line", (profile_document_id(patient_id),))]


def record_mismatches(conn, patient_id, facts):
    """Blood group / sex / date of birth the patient typed that differ from their documents.
    Shown to the patient right after saving; the doctor sees both values in the timeline."""
    from backend.logic.wrong_patient import normalise_blood_group, normalise_sex

    normalise = {"blood_group": normalise_blood_group, "sex": normalise_sex, "dob": lambda v: (v or "").strip()}
    typed = {f["name"]: f["value"] for f in facts if f["type"] == "demographic"}
    out, seen = [], set()
    for r in conn.execute(
            """SELECT f.name, f.value, f.flags, d.doc_type, d.document_date FROM facts f
               JOIN documents d ON d.id = f.document_id
               WHERE f.patient_id = ? AND f.type = 'demographic' AND f.status = 'documented'
               AND d.held_back = 0 AND d.doc_type IS NOT ? AND f.name IN ('blood_group', 'sex', 'dob')
               ORDER BY d.document_date""", (patient_id, PROFILE_DOC_TYPE)):
        name = r["name"]
        if name not in typed or "wrong_patient" in (r["flags"] or ""):
            continue
        if name == "dob":  # records write 14-06-1952, the form 1952-06-14: compare the same way round
            parts = re.split(r"[-/.]", r["value"] or "")
            record_value = "-".join(reversed(parts)) if len(parts) == 3 and len(parts[2]) == 4 else r["value"]
        else:
            record_value = r["value"]
        if normalise[name](record_value) != normalise[name](typed[name]) and (name, record_value) not in seen:
            seen.add((name, record_value))  # several documents saying O+: shown once, from the oldest
            out.append({"field": name, "you_said": typed[name], "records_say": r["value"],
                        "source": f"{(r['doc_type'] or 'document').replace('_', ' ')} from {r['document_date']}"})
    return out


def profile_out(conn, patient_id, mismatches=None):
    patient = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    patient = dict(patient)
    facts = _profile_facts(conn, patient_id)
    by_name = {f["name"]: f for f in facts if f["type"] == "demographic"}
    allergies = [f for f in facts if f["type"] == "allergy" and f["status"] == "documented"]
    none = any(f["type"] == "allergy" and f["status"] == "negated" for f in facts)
    filled = patient.get("profile_filled_at")
    sex_on_record = {"F": "Female", "M": "Male"}.get((patient.get("sex") or "").upper()[:1])
    return {
        "patient_id": patient_id,
        # shown by itself after login until the patient saves it or picks "Do it later"
        "needed": not filled and not patient.get("profile_skipped_at"),
        "filled_at": filled,
        "skipped_at": patient.get("profile_skipped_at"),
        # before the first save, start from what the patient record already has
        "dob": by_name["dob"]["value"] if "dob" in by_name else (None if filled else patient.get("dob")),
        "sex": by_name["sex"]["value"] if "sex" in by_name else (None if filled else sex_on_record),
        "blood_group": (by_name["blood_group"]["value"] if "blood_group" in by_name
                        else (None if filled else patient.get("blood_group"))),
        "allergy_answer": "yes" if allergies else ("none" if none else ("dont_know" if filled else None)),
        "allergies": [{"name": f["name"], "reaction": f["value"]} for f in allergies],
        "mismatches": mismatches if mismatches is not None else record_mismatches(conn, patient_id, facts),
    }


def save_profile(conn, patient_id, body, today=None):
    """Write the answers as facts of the profile document (stable fact ids, so a doctor's
    confirmation of an unchanged answer is kept). Returns the facts written."""
    today = today or date.today().isoformat()
    doc_id = profile_document_id(patient_id)
    rows = answers_to_facts(body)
    wanted = {f"{doc_id}_{key}" for key, *_ in rows}
    existing = {f["fact_id"]: f for f in _profile_facts(conn, patient_id)}

    if rows:
        conn.execute(
            """INSERT INTO documents (id, patient_id, filename, doc_type, document_date, file_path, held_back)
               VALUES (?, ?, ?, ?, ?, NULL, 0)
               ON CONFLICT(id) DO UPDATE SET document_date = excluded.document_date""",
            (doc_id, patient_id, PROFILE_FILENAME, PROFILE_DOC_TYPE, today))
    for fact_id in set(existing) - wanted:  # answers the patient removed (kept in the audit log)
        conn.execute("DELETE FROM facts WHERE fact_id = ?", (fact_id,))
    for line, (key, ftype, name, value, status, quote) in enumerate(rows, start=1):
        fact_id = f"{doc_id}_{key}"
        old = existing.get(fact_id)
        if old and old["quote"] == quote:
            conn.execute("UPDATE facts SET line = ? WHERE fact_id = ?", (line, fact_id))
            continue
        if old:
            conn.execute("DELETE FROM facts WHERE fact_id = ?", (fact_id,))
        conn.execute(
            """INSERT INTO facts (fact_id, patient_id, document_id, type, name, dose, frequency, value, unit,
                   action, status, event_date, document_date, date_raw, quote, page, line, quote_verified,
                   echo_of, badge, flags, corrected)
               VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, NULL, NULL, ?, ?, ?, ?, ?, 1, ?, 1, NULL,
                       'patient_reported', '[]', 0)""",
            (fact_id, patient_id, doc_id, ftype, name, value, status, today, today, today, quote, line))
    if not rows:
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    # the wrong-patient check compares new documents with the patients table: fill only what is empty
    patient = dict(conn.execute("SELECT dob, sex, blood_group FROM patients WHERE id = ?", (patient_id,)).fetchone())
    fill = {}
    if body.dob and not patient["dob"]:
        fill["dob"] = _check_dob(body.dob)
    if body.sex in ("Female", "Male") and not patient["sex"]:  # "Other" would make every document a mismatch
        fill["sex"] = body.sex[0]
    if body.blood_group and not patient["blood_group"]:
        fill["blood_group"] = body.blood_group
    fill["profile_filled_at"] = today
    conn.execute(f"UPDATE patients SET {', '.join(f'{k} = ?' for k in fill)} WHERE id = ?",
                 [*fill.values(), patient_id])
    return _profile_facts(conn, patient_id)


# ---------- routes ----------

@router.get("/patients/{patient_id}/profile")
def get_profile(patient_id: str, user=Depends(get_current_user)):
    _own_patient(user, patient_id)
    with get_conn() as conn:
        out = profile_out(conn, patient_id)
    log_action(user, "view_profile", patient_id)
    return out


@router.put("/patients/{patient_id}/profile")
def put_profile(patient_id: str, body: ProfileBody, user=Depends(get_current_user)):
    from backend.recompute import recompute_patient
    from backend.routes.questions import sync_questions  # imported here: avoids an import loop

    _own_patient(user, patient_id)
    with get_conn() as conn:
        facts = save_profile(conn, patient_id, body)
        mismatches = record_mismatches(conn, patient_id, facts)
    recompute_patient(patient_id)  # badges + contradictions with the documents
    with get_conn() as conn:
        sync_questions(conn, patient_id)  # a conflict with the records becomes an Open Question
        out = profile_out(conn, patient_id, mismatches)
    log_action(user, "save_profile", patient_id, body.model_dump())
    return out


@router.post("/patients/{patient_id}/profile/skip")
def skip_profile(patient_id: str, user=Depends(get_current_user)):
    _own_patient(user, patient_id)
    with get_conn() as conn:
        conn.execute("UPDATE patients SET profile_skipped_at = ? WHERE id = ?", (date.today().isoformat(), patient_id))
        out = profile_out(conn, patient_id)
    log_action(user, "skip_profile", patient_id)
    return out
