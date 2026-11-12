"""Things to Check (patient) and Open Questions (doctor). (Medha)

GET  /patients/{patient_id}/questions
     Builds questions in plain code from conflicts, copied (echo) medicines and gaps,
     saves any new ones in the questions table, and returns them all:
     [{"id", "text", "status", "answer", "fact_ids", "facts", "created_at"}]

POST /questions/{question_id}/answer   {"answer": "...", "value": "..."}
     Patient answers:  yes | no | value | dont_know | skip
         yes / no / value  -> status "answered"   (the facts become patient_reported)
         dont_know / skip  -> status "sent_to_doctor"
     Doctor answers:   confirm | correct | unclear  -> status "resolved"
         The frontend first calls POST /facts/{id}/correct for confirm/correct, so the
         fact becomes doctor_verified (badge logic is in backend/logic/badges.py).

The answer column holds JSON: {"answer", "value", "by", "role", "at"}.
Each question is saved in English (text) and Kannada (text_kn); the user's language picks one.
Claim checklist questions (stay_id + claim_condition set, see backend/routes/claims.py) live
in the same table: the patient answers yes / no / dont_know, and the answer sets the hospital
stay's condition. They never go to the doctor.
Quotes, medicine names, doses and dates inside the text stay exactly as written.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import get_current_user, require_patient_access
from backend.db import get_conn
from backend.logic.flags import find_gaps
from backend.recompute import recompute_patient
from backend.routes.claims import answer_claim_question, sync_claim_questions
from backend.routes.audit_helper import log_action
from backend.routes.fact_helpers import (
    describe, load_documents, load_facts, medication_summaries, source_label,
)
from backend.routes.language import gap_name, user_language

router = APIRouter()

PATIENT_ANSWERS = {"yes", "no", "value", "dont_know", "skip"}
DOCTOR_ANSWERS = {"confirm", "correct", "unclear"}


# ---------- building questions (plain code, no AI) ----------
# Each builder returns [(fact_ids, {"en": text, "kn": text})].

def contradiction_questions(facts, docs):
    """'Your records disagree...' for each documented fact that conflicts with a negated one."""
    flagged = [f for f in facts if "contradiction" in f["flags"]]
    questions = []
    for fact_type in sorted({f["type"] for f in flagged}):
        same_type = [f for f in flagged if f["type"] == fact_type]
        negatives = [f for f in same_type if f["status"] == "negated"]
        for pos in (f for f in same_type if f["status"] == "documented"):
            if fact_type == "allergy":
                ask = f"Are you allergic to {pos['name']}?"
                ask_kn = f"ನಿಮಗೆ {pos['name']} ಅಲರ್ಜಿ ಇದೆಯೇ?"
            elif fact_type == "condition":
                ask = f"Have you been told you have {pos['name']}?"
                ask_kn = f"ನಿಮಗೆ {pos['name']} ಇದೆ ಎಂದು ವೈದ್ಯರು ಹೇಳಿದ್ದಾರೆಯೇ?"
            else:
                ask = "Which one is correct?"
                ask_kn = "ಇವುಗಳಲ್ಲಿ ಯಾವುದು ಸರಿ?"
            if negatives:
                neg = negatives[0]
                text = (
                    f'Your records disagree. The {source_label(neg, docs)} says "{neg["quote"]}", '
                    f'but the {source_label(pos, docs)} says "{pos["quote"]}". {ask}'
                )
                text_kn = (
                    f'ನಿಮ್ಮ ದಾಖಲೆಗಳು ಒಂದಕ್ಕೊಂದು ಹೊಂದುತ್ತಿಲ್ಲ. {source_label(neg, docs, "kn")}: "{neg["quote"]}". '
                    f'ಆದರೆ {source_label(pos, docs, "kn")}: "{pos["quote"]}". {ask_kn}'
                )
            else:
                text = f'Your records disagree about {describe(pos)} ("{pos["quote"]}"). {ask}'
                text_kn = f'{describe(pos)} ಬಗ್ಗೆ ನಿಮ್ಮ ದಾಖಲೆಗಳು ಹೊಂದುತ್ತಿಲ್ಲ ("{pos["quote"]}"). {ask_kn}'
            fact_ids = [pos["fact_id"]] + [n["fact_id"] for n in negatives]
            questions.append((fact_ids, {"en": text, "kn": text_kn}))
    return questions


def echo_medicine_questions(facts, docs):
    """A current medicine whose latest mention is only a copy of an older document."""
    questions = []
    for med in medication_summaries(facts):
        if not med["current"] or not med["latest"]["echo_of"]:
            continue
        fresh = med["latest_fresh"]
        copies = med["echo_count"]
        text = (
            f"{describe(fresh)} appears in {med['mentions']} documents, but {copies} of them "
            f"{'is a copy' if copies == 1 else 'are copies'} of your {source_label(fresh, docs)}. "
            f"The last new record of it is from {med['last_fresh_evidence_date'] or 'an unknown date'}. "
            f"Are you still taking {med['name']}?"
        )
        text_kn = (
            f"{describe(fresh)} {med['mentions']} ದಾಖಲೆಗಳಲ್ಲಿ ಇದೆ. ಅವುಗಳಲ್ಲಿ {copies} ಹಳೆಯ ದಾಖಲೆಯ "
            f"ನಕಲು ({source_label(fresh, docs, 'kn')}). "
            f"ಇದರ ಕೊನೆಯ ಹೊಸ ದಾಖಲೆ: {med['last_fresh_evidence_date'] or 'ದಿನಾಂಕ ತಿಳಿದಿಲ್ಲ'}. "
            f"ನೀವು ಈಗಲೂ {med['name']} ತೆಗೆದುಕೊಳ್ಳುತ್ತಿದ್ದೀರಾ?"
        )
        questions.append(([e["fact_id"] for e in med["entries"]], {"en": text, "kn": text_kn}))
    return questions


GAP_TEXT = {
    "allergy": "Your records never say whether you have any allergies. Do you have any allergies to medicines?",
    "demographic": "Your records don't mention your {what}. Do you know it?",
}
GAP_TEXT_OTHER = "Your records never mention {what}. Can you tell us?"
GAP_TEXT_KN = {
    "allergy": "ನಿಮಗೆ ಯಾವುದಾದರೂ ಅಲರ್ಜಿ ಇದೆಯೇ ಎಂದು ನಿಮ್ಮ ದಾಖಲೆಗಳಲ್ಲಿ ಎಲ್ಲಿಯೂ ಹೇಳಿಲ್ಲ. ನಿಮಗೆ ಯಾವುದಾದರೂ ಔಷಧದ ಅಲರ್ಜಿ ಇದೆಯೇ?",
    "demographic": "ನಿಮ್ಮ ದಾಖಲೆಗಳಲ್ಲಿ ನಿಮ್ಮ {what} ಉಲ್ಲೇಖವಿಲ್ಲ. ನಿಮಗೆ ಅದು ಗೊತ್ತೇ?",
}
GAP_TEXT_OTHER_KN = "ನಿಮ್ಮ ದಾಖಲೆಗಳಲ್ಲಿ {what} ಬಗ್ಗೆ ಉಲ್ಲೇಖವಿಲ್ಲ. ನೀವು ತಿಳಿಸಬಹುದೇ?"


def gap_questions(facts):
    """Gaps from Deeksha's find_gaps() (not stored; computed from the trusted facts).
    Gap facts have stable ids like p1_gap_allergy, so each gap is asked only once."""
    questions = []
    for gap in find_gaps(facts):
        text = GAP_TEXT.get(gap["type"], GAP_TEXT_OTHER).format(what=gap_name(gap["name"], "en"))
        text_kn = GAP_TEXT_KN.get(gap["type"], GAP_TEXT_OTHER_KN).format(what=gap_name(gap["name"], "kn"))
        questions.append(([gap["fact_id"]], {"en": text, "kn": text_kn}))
    return questions


def build_questions(facts, docs):
    return contradiction_questions(facts, docs) + echo_medicine_questions(facts, docs) + gap_questions(facts)


def question_key(fact_ids, text):
    """Same facts -> same question (so answered ones are not asked again). No facts -> same text."""
    return json.dumps(sorted(fact_ids)) if fact_ids else text


def sync_questions(conn, patient_id):
    """Save any new questions for this patient. Existing ones (any status) are kept as they are,
    except that a missing Kannada text is filled in (questions saved before text_kn existed)."""
    facts = load_facts(conn, patient_id)
    docs = load_documents(conn, patient_id)
    existing = {
        question_key(json.loads(r["fact_ids"] or "[]"), r["text"]): r
        for r in conn.execute(
            "SELECT id, fact_ids, text, text_kn FROM questions WHERE patient_id = ?", (patient_id,)
        )
    }
    for fact_ids, texts in build_questions(facts, docs):
        key = question_key(fact_ids, texts["en"])
        row = existing.get(key)
        if row is None:
            conn.execute(
                "INSERT INTO questions (patient_id, fact_ids, text, text_kn) VALUES (?, ?, ?, ?)",
                (patient_id, json.dumps(sorted(fact_ids)), texts["en"], texts["kn"]),
            )
            existing[key] = {"text_kn": texts["kn"]}
        elif not row["text_kn"]:
            conn.execute("UPDATE questions SET text_kn = ? WHERE id = ?", (texts["kn"], row["id"]))
    sync_claim_questions(conn, patient_id)


def question_out(row, facts_by_id, lang="en"):
    fact_ids = json.loads(row["fact_ids"] or "[]")
    return {
        "id": row["id"],
        "text": row["text_kn"] if lang == "kn" and row["text_kn"] else row["text"],
        "status": row["status"],
        "answer": json.loads(row["answer"]) if row["answer"] else None,
        "fact_ids": fact_ids,
        "facts": [facts_by_id[i] for i in fact_ids if i in facts_by_id],
        "created_at": row["created_at"],
        "stay_id": row["stay_id"],
        "claim_condition": row["claim_condition"],
    }


def facts_with_gaps(conn, patient_id):
    """{fact_id: fact} for all of a patient's facts plus today's gap facts (never stored)."""
    by_id = {f["fact_id"]: f for f in load_facts(conn, patient_id, include_held_back=True)}
    for gap in find_gaps(load_facts(conn, patient_id)):
        by_id[gap["fact_id"]] = gap
    return by_id


def list_questions_for(conn, patient_id, lang="en"):
    """All questions for a patient (after syncing), with their facts attached."""
    sync_questions(conn, patient_id)
    facts_by_id = facts_with_gaps(conn, patient_id)
    rows = conn.execute("SELECT * FROM questions WHERE patient_id = ? ORDER BY id", (patient_id,)).fetchall()
    return [question_out(r, facts_by_id, lang) for r in rows]


# ---------- routes ----------

@router.get("/patients/{patient_id}/questions")
def list_questions(patient_id: str, user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    with get_conn() as conn:
        questions = list_questions_for(conn, patient_id, user_language(user))
    log_action(user, "view_questions", patient_id, "")
    return questions


class AnswerBody(BaseModel):
    answer: str
    value: Optional[str] = Field(default=None, max_length=500)


@router.post("/questions/{question_id}/answer")
def answer_question(question_id: int, body: AnswerBody, user=Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Question not found")
    patient_id = row["patient_id"]
    require_patient_access(user, patient_id)

    answer = body.answer
    value = (body.value or "").strip() or None
    if row["claim_condition"]:  # hospital stay question for the Claim Documents checklist
        new_status = answer_claim_question(row, answer, user)
        value = None
    elif answer in PATIENT_ANSWERS:
        if user["role"] != "patient":
            raise HTTPException(status_code=403, detail="Only the patient answers Things to Check.")
        if answer == "value" and not value:
            raise HTTPException(status_code=422, detail="Please type a value.")
        new_status = "sent_to_doctor" if answer in ("dont_know", "skip") else "answered"
    elif answer in DOCTOR_ANSWERS:
        if user["role"] != "doctor":
            raise HTTPException(status_code=403, detail="Only a doctor resolves open questions.")
        new_status = "resolved"
    else:
        raise HTTPException(status_code=422, detail=f"Unknown answer: {answer}")

    if row["status"] == "resolved":
        raise HTTPException(status_code=409, detail="This question is already resolved.")

    stored = {
        "answer": answer,
        "value": value,
        "by": user["username"],
        "role": user["role"],
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }
    with get_conn() as conn:
        conn.execute(
            "UPDATE questions SET status = ?, answer = ? WHERE id = ?",
            (new_status, json.dumps(stored), question_id),
        )
    # badges.py counts facts in "answered" questions as patient_reported: rerun the checks now
    if not row["claim_condition"]:
        recompute_patient(patient_id)
    with get_conn() as conn:
        updated = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        facts_by_id = facts_with_gaps(conn, patient_id)

    log_action(user, "answer_question", patient_id, f"question {question_id}: {answer}" + (f" ({value})" if value else ""))
    return question_out(updated, facts_by_id, user_language(user))
