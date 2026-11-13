"""When someone answers a question, update the record (AGENTIC_PLAN point 11). Plain code, no AI.

apply_answer(conn, question_row, stored_answer, user) -> [plain-language change, ...]

  patient says NO to "are you still taking X?"  -> the latest entry of X is marked "stopped"
                                                    (a correction by the patient; the original
                                                    stays in the corrections table)
  patient says YES / gives a value               -> the facts become patient_reported (badges.py,
                                                    via recompute; nothing to change here)
  patient says I DON'T KNOW / SKIP               -> the doctor sees why it reached them
  doctor CONFIRM / CORRECT                        -> doctor_verified (the frontend corrects the fact
                                                    through POST /facts/{id}/correct first)
A patient's typed value never changes a clinical fact on its own: the doctor's Correct does that.
Every change is written as an agent step ("answer").
"""
import json

from backend.agent.steps import record

STILL_TAKING = "only the patient knows if they still take it"


def _latest_medication(conn, fact_ids):
    marks = ",".join("?" * len(fact_ids))
    return conn.execute(
        f"""SELECT * FROM facts WHERE fact_id IN ({marks}) AND type = 'medication'
            ORDER BY event_date DESC, fact_id DESC LIMIT 1""", fact_ids).fetchone()


def apply_answer(conn, question, stored, user):
    answer = stored["answer"]
    fact_ids = json.loads(question["fact_ids"] or "[]")
    changes = []

    if answer == "no" and question["route_reason"] == STILL_TAKING and fact_ids:
        med = _latest_medication(conn, fact_ids)
        if med and med["action"] != "stopped":
            conn.execute(
                """INSERT INTO corrections (fact_id, field, old_value, new_value, corrected_by, role)
                   VALUES (?, 'action', ?, 'stopped', ?, ?)""",
                (med["fact_id"], med["action"], user["id"], user["role"]),
            )
            conn.execute("UPDATE facts SET action = 'stopped', corrected = 1 WHERE fact_id = ?", (med["fact_id"],))
            changes.append(f"{med['name']} marked as stopped (the patient says they no longer take it; "
                           f"the original entry is kept)")

    if answer in ("dont_know", "skip"):
        reason = "the patient answered: I don't know" if answer == "dont_know" else "the patient skipped it"
        conn.execute("UPDATE questions SET route_reason = ? WHERE id = ?", (reason, question["id"]))
        changes.append(f"question sent to the doctor ({reason})")
    elif answer in ("yes", "value"):
        changes.append("answer saved; the facts it is about are now marked patient-reported")
    elif answer in ("confirm", "correct"):
        changes.append("the doctor resolved it; the facts are now doctor-verified")
    elif answer == "unclear":
        changes.append("the doctor marked it unclear")

    for change in changes:
        record(conn, question["patient_id"], None, "answer", "ok", f"question {question['id']}: {change}")
    return changes
