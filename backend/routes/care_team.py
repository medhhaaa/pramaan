"""Care team: a patient's lasting consent for the doctors who treat them. (Medha)

Patient (own records only):
  GET  /doctors/search?q=rao                      doctors by name or registration number
  GET  /condition-tags                             scopes a patient can pick (rules/condition_tags.json)
  GET  /patients/{id}/care-team                    doctors, scope, date added, last viewed, review_due
  POST /patients/{id}/care-team                    {"doctor_id": 9, "scope": "all" | ["diabetes"]}
  POST /patients/{id}/care-team/{entry}/revoke     the doctor loses access at once
  POST /patients/{id}/care-team/{entry}/keep       answers "Keep Dr. X on your care team?"
  GET  /patients/{id}/access-history               "Dr. X viewed your records on <date>"

Doctor:
  GET  /doctors/me/patients                        My Patients dashboard (care-team patients + tags)
  POST /patients/{id}/follow-up                    {"date": "2026-12-01" | null} (care-team doctor)

Access itself is checked in backend/auth.py (require_patient_access); scope filtering in
backend/scope.py. Every action is written to the audit log.

Dashboard tags, highest priority first (TAG_ORDER): refill_request (a pending refill request
to this doctor), new_report (a document uploaded after this doctor last opened the patient),
missed_doses (under 70% of due doses taken in the last 14 days), followup_overdue (the
doctor's follow-up date passed with no consult record since it was set), stable (none).
Sorted by the highest tag, then most recent activity.
"""
from datetime import date, datetime, timedelta, timezone
from typing import List, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.adherence import adherence, today_utc
from backend.auth import active_care_team, get_current_user, require_patient_access
from backend.db import get_conn, log_action
from backend.scope import TAGS, TAG_NAMES, document_in_scope, fact_in_scope, parse_scope, scope_text

router = APIRouter()

TAG_ORDER = ["refill_request", "new_report", "missed_doses", "followup_overdue", "stable"]
MISSED_DOSES_BELOW = 70   # percent of due doses taken, last 14 days
ADHERENCE_DAYS = 14
REVIEW_AFTER_DAYS = 180   # no consult record this long -> "Keep Dr. X on your care team?"
TAG_LABELS = {t["tag"]: t["label"] for t in TAGS}


def now_sql():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def doctor_out(row):
    return {"id": row["id"], "name": row["full_name"] or row["username"],
            "registration_number": row["registration_number"]}


def require_own_patient(user, patient_id):
    """Care-team changes are the patient's own decision: never a doctor's."""
    if user["role"] != "patient":
        raise HTTPException(status_code=403, detail="Only the patient manages their care team")
    require_patient_access(user, patient_id)


def require_doctor(user):
    if user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="Doctors only")


def last_viewed(conn, doctor_id, patient_id):
    """When this doctor last opened anything of this patient (from the audit log)."""
    row = conn.execute(
        "SELECT MAX(created_at) AS at FROM audit_log WHERE user_id = ? AND patient_id = ?",
        (doctor_id, patient_id),
    ).fetchone()
    return row["at"]


def last_consult(conn, doctor_id, patient_id):
    row = conn.execute(
        "SELECT MAX(created_at) AS at FROM consult_records WHERE doctor_id = ? AND patient_id = ?",
        (doctor_id, patient_id),
    ).fetchone()
    return row["at"]


def review_due(conn, entry, today=None):
    """True when the doctor has had no consult record with the patient for 180 days (counting
    from when the patient added or last kept them)."""
    if entry["status"] != "active":
        return False
    latest = max(filter(None, [entry["last_confirmed_at"], entry["created_at"],
                               last_consult(conn, entry["doctor_id"], entry["patient_id"])]))
    cutoff = (today or today_utc()) - timedelta(days=REVIEW_AFTER_DAYS)
    return date.fromisoformat(latest[:10]) < cutoff


def entry_out(conn, entry, doctor):
    scope = parse_scope(entry["scope"])
    return {
        "id": entry["id"],
        "doctor": doctor_out(doctor),
        "scope": scope,
        "scope_labels": "all" if scope == "all" else [TAG_LABELS[t] for t in scope],
        "status": entry["status"],
        "created_at": entry["created_at"],
        "revoked_at": entry["revoked_at"],
        "last_viewed_at": last_viewed(conn, entry["doctor_id"], entry["patient_id"]),
        "review_due": review_due(conn, entry),
    }


# ---------- patient side ----------

@router.get("/condition-tags")
def condition_tags(user=Depends(get_current_user)):
    return [{"tag": t["tag"], "label": t["label"]} for t in TAGS]


@router.get("/doctors/search")
def search_doctors(q: str = Query(..., min_length=2, max_length=80), user=Depends(get_current_user)):
    if user["role"] != "patient":
        raise HTTPException(status_code=403, detail="Patients search for doctors to add")
    like = f"%{q.strip().lower()}%"
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM users WHERE role = 'doctor' AND (LOWER(COALESCE(full_name, '')) LIKE ?
               OR LOWER(username) LIKE ? OR LOWER(COALESCE(registration_number, '')) LIKE ?)
               ORDER BY COALESCE(full_name, username) LIMIT 20""",
            (like, like, like),
        ).fetchall()
    log_action(user, "search_doctors", None, q)
    return [doctor_out(r) for r in rows]


@router.get("/patients/{patient_id}/care-team")
def list_care_team(patient_id: str, user=Depends(get_current_user)):
    require_own_patient(user, patient_id)
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.*, u.id AS uid, u.username, u.full_name, u.registration_number
               FROM care_team c JOIN users u ON u.id = c.doctor_id
               WHERE c.patient_id = ? ORDER BY c.status, c.created_at DESC""",
            (patient_id,),
        ).fetchall()
        out = [entry_out(conn, r, {"id": r["uid"], "username": r["username"], "full_name": r["full_name"],
                                   "registration_number": r["registration_number"]}) for r in rows]
    log_action(user, "view_care_team", patient_id)
    return out


class AddDoctorBody(BaseModel):
    doctor_id: int
    scope: Union[Literal["all"], List[str]] = "all"


@router.post("/patients/{patient_id}/care-team")
def add_doctor(patient_id: str, body: AddDoctorBody, user=Depends(get_current_user)):
    require_own_patient(user, patient_id)
    scope = body.scope
    if scope != "all":
        scope = sorted(set(scope))
        if not scope or any(t not in TAG_NAMES for t in scope):
            raise HTTPException(status_code=422, detail=f"Scope must be 'all' or tags from {TAG_NAMES}")
    with get_conn() as conn:
        doctor = conn.execute("SELECT * FROM users WHERE id = ? AND role = 'doctor'", (body.doctor_id,)).fetchone()
        if not doctor:
            raise HTTPException(status_code=404, detail="Doctor not found")
        if conn.execute("SELECT 1 FROM care_team WHERE patient_id = ? AND doctor_id = ? AND status = 'active'",
                        (patient_id, body.doctor_id)).fetchone():
            raise HTTPException(status_code=409, detail="This doctor is already on your care team")
        now = now_sql()
        cur = conn.execute(
            """INSERT INTO care_team (patient_id, doctor_id, scope, status, created_at, last_confirmed_at)
               VALUES (?, ?, ?, 'active', ?, ?)""",
            (patient_id, body.doctor_id, scope_text(scope), now, now),
        )
        entry = conn.execute("SELECT * FROM care_team WHERE id = ?", (cur.lastrowid,)).fetchone()
        out = entry_out(conn, entry, doctor)
    log_action(user, "add_care_team_doctor", patient_id, {"doctor_id": body.doctor_id, "scope": scope})
    return out


def load_entry(conn, patient_id, entry_id):
    entry = conn.execute("SELECT * FROM care_team WHERE id = ? AND patient_id = ?", (entry_id, patient_id)).fetchone()
    if not entry:
        raise HTTPException(status_code=404, detail="Care team entry not found")
    return entry


@router.post("/patients/{patient_id}/care-team/{entry_id}/revoke")
def revoke_doctor(patient_id: str, entry_id: int, user=Depends(get_current_user)):
    require_own_patient(user, patient_id)
    with get_conn() as conn:
        entry = load_entry(conn, patient_id, entry_id)
        if entry["status"] == "active":
            conn.execute("UPDATE care_team SET status = 'revoked', revoked_at = ? WHERE id = ?", (now_sql(), entry_id))
    log_action(user, "revoke_care_team_doctor", patient_id, {"doctor_id": entry["doctor_id"]})
    return {"id": entry_id, "status": "revoked"}


@router.post("/patients/{patient_id}/care-team/{entry_id}/keep")
def keep_doctor(patient_id: str, entry_id: int, user=Depends(get_current_user)):
    require_own_patient(user, patient_id)
    with get_conn() as conn:
        entry = load_entry(conn, patient_id, entry_id)
        if entry["status"] != "active":
            raise HTTPException(status_code=409, detail="This doctor is no longer on your care team")
        conn.execute("UPDATE care_team SET last_confirmed_at = ? WHERE id = ?", (now_sql(), entry_id))
    log_action(user, "keep_care_team_doctor", patient_id, {"doctor_id": entry["doctor_id"]})
    return {"id": entry_id, "status": "active"}


@router.get("/patients/{patient_id}/access-history")
def access_history(patient_id: str, user=Depends(get_current_user)):
    """One row per doctor per day they opened this patient's records, newest first."""
    require_own_patient(user, patient_id)
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT u.id AS doctor_id, COALESCE(u.full_name, u.username) AS doctor_name,
                      DATE(a.created_at) AS day, MAX(a.created_at) AS last_at, COUNT(*) AS actions
               FROM audit_log a JOIN users u ON u.id = a.user_id
               WHERE a.patient_id = ? AND u.role = 'doctor'
               GROUP BY u.id, DATE(a.created_at) ORDER BY last_at DESC LIMIT 100""",
            (patient_id,),
        ).fetchall()
    log_action(user, "view_access_history", patient_id)
    return [dict(r) for r in rows]


# ---------- doctor side ----------

def patient_age(dob, today):
    try:
        born = date.fromisoformat(dob)
    except (TypeError, ValueError):
        return None
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def scoped_conditions(conn, patient_id, scope):
    rows = conn.execute(
        """SELECT f.type, f.name FROM facts f JOIN documents d ON d.id = f.document_id
           WHERE f.patient_id = ? AND f.type = 'condition' AND f.status = 'documented' AND d.held_back = 0
           ORDER BY f.event_date DESC""",
        (patient_id,),
    ).fetchall()
    names, seen = [], set()
    for r in rows:
        if fact_in_scope(dict(r), scope) and r["name"].lower() not in seen:
            seen.add(r["name"].lower())
            names.append(r["name"])
    return names[:4]


def new_report_since(conn, patient_id, since, scope):
    """Documents uploaded after `since`, counting only those with an in-scope fact."""
    docs = conn.execute(
        "SELECT id FROM documents WHERE patient_id = ? AND uploaded_at > ?", (patient_id, since or ""),
    ).fetchall()
    for d in docs:
        facts = conn.execute("SELECT type, name FROM facts WHERE document_id = ?", (d["id"],)).fetchall()
        if document_in_scope([dict(f) for f in facts], scope):
            return True
    return False


def patient_tags(conn, entry, today):
    doctor_id, patient_id = entry["doctor_id"], entry["patient_id"]
    scope = parse_scope(entry["scope"])
    tags = []
    if conn.execute("SELECT 1 FROM refill_requests WHERE doctor_id = ? AND patient_id = ? AND status = 'pending'",
                    (doctor_id, patient_id)).fetchone():
        tags.append("refill_request")
    seen = last_viewed(conn, doctor_id, patient_id) or entry["created_at"]
    if new_report_since(conn, patient_id, seen, scope):
        tags.append("new_report")
    doses = adherence(conn, patient_id, days=ADHERENCE_DAYS, today=today)
    if doses["percent"] is not None and doses["percent"] < MISSED_DOSES_BELOW:
        tags.append("missed_doses")
    if entry["followup_on"] and entry["followup_on"] < today.isoformat():
        consulted = conn.execute(
            "SELECT 1 FROM consult_records WHERE doctor_id = ? AND patient_id = ? AND created_at >= ?",
            (doctor_id, patient_id, entry["followup_set_at"] or entry["followup_on"]),
        ).fetchone()
        if not consulted:
            tags.append("followup_overdue")
    return tags or ["stable"], doses


def last_activity(conn, entry):
    pid = entry["patient_id"]
    times = [entry["created_at"]]
    for sql in ("SELECT MAX(uploaded_at) FROM documents WHERE patient_id = ?",
                "SELECT MAX(logged_at) FROM dose_logs WHERE patient_id = ?",
                "SELECT MAX(created_at) FROM refill_requests WHERE patient_id = ?",
                "SELECT MAX(created_at) FROM consult_records WHERE patient_id = ?"):
        times.append(conn.execute(sql, (pid,)).fetchone()[0])
    return max(t for t in times if t)


def my_patients(conn, doctor_id, today=None):
    today = today or today_utc()
    entries = conn.execute(
        """SELECT c.*, p.name, p.dob, p.sex FROM care_team c JOIN patients p ON p.id = c.patient_id
           WHERE c.doctor_id = ? AND c.status = 'active'""",
        (doctor_id,),
    ).fetchall()
    out = []
    for e in entries:
        scope = parse_scope(e["scope"])
        tags, doses = patient_tags(conn, e, today)
        out.append({
            "patient_id": e["patient_id"],
            "name": e["name"],
            "age": patient_age(e["dob"], today),
            "sex": e["sex"],
            "scope": scope,
            "conditions": scoped_conditions(conn, e["patient_id"], scope),
            "tags": tags,
            "adherence_14d": doses["percent"],
            "followup_on": e["followup_on"],
            "last_activity": last_activity(conn, e),
            "last_viewed_at": last_viewed(conn, doctor_id, e["patient_id"]),
        })
    # highest-priority tag first, then most recent activity first
    out.sort(key=lambda p: p["last_activity"], reverse=True)
    out.sort(key=lambda p: min(TAG_ORDER.index(t) for t in p["tags"]))
    return out


@router.get("/doctors/me/patients")
def my_patients_route(user=Depends(get_current_user)):
    require_doctor(user)
    with get_conn() as conn:
        patients = my_patients(conn, user["id"])
    log_action(user, "view_my_patients", None, {"count": len(patients)})
    return patients


class FollowUpBody(BaseModel):
    date: Optional[str] = None  # "YYYY-MM-DD", or null to clear


@router.post("/patients/{patient_id}/follow-up")
def set_follow_up(patient_id: str, body: FollowUpBody, user=Depends(get_current_user)):
    require_doctor(user)
    require_patient_access(user, patient_id)
    try:
        when = date.fromisoformat(body.date).isoformat() if body.date else None
    except ValueError:
        raise HTTPException(status_code=422, detail="Use a date like 2026-12-01")
    with get_conn() as conn:
        entry = active_care_team(conn, user, patient_id)
        if not entry:  # a QR / code share alone doesn't make the doctor the patient's treating doctor
            raise HTTPException(status_code=403, detail="Only a care-team doctor sets a follow-up date")
        conn.execute("UPDATE care_team SET followup_on = ?, followup_set_at = ? WHERE id = ?",
                     (when, now_sql() if when else None, entry["id"]))
    log_action(user, "set_follow_up", patient_id, {"date": when})
    return {"patient_id": patient_id, "followup_on": when}
