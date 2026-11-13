"""Reminders and escalation for unanswered questions (AGENTIC_PLAN points 9-10). Plain code, no AI.

  48 h after a patient question was asked and still open  -> remind the patient (notification in
                                                              their language), stamp reminded_at
  48 h after the reminder and still open                   -> escalate: the question moves to the
                                                              doctor's Open Questions (status
                                                              sent_to_doctor), care-team doctors
                                                              are notified, stamp escalated_at
  The patient answers "I don't know" / skip                -> already goes to the doctor
                                                              (backend/routes/questions.py)
Claim checklist questions are only reminded, never sent to a doctor (they are the patient's own).

run_reminders(now=None, patient_id=None) -> {"reminded": [...], "escalated": [...]}
    now = a UTC datetime; the demo passes "48 hours from now" to show it without waiting.

    python -m backend.agent.reminders            run once now
    python -m backend.agent.reminders --hours 96 pretend 96 hours have passed (demo)
start_scheduler()  runs it every 15 minutes in a background thread (main.py, at startup)
"""
import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

from backend.agent.steps import record
from backend.db import get_conn

WAIT = timedelta(hours=48)
EVERY_SECONDS = 15 * 60

REMIND_TEXT = {
    "en": "You have {n} question(s) about your records waiting in Things to Check.",
    "kn": "ನಿಮ್ಮ ದಾಖಲೆಗಳ ಬಗ್ಗೆ {n} ಪ್ರಶ್ನೆ(ಗಳು) 'ಪರಿಶೀಲಿಸಬೇಕಾದವು' ವಿಭಾಗದಲ್ಲಿ ಕಾಯುತ್ತಿವೆ.",
    "hi": "आपके रिकॉर्ड के बारे में {n} सवाल 'जाँचने वाली बातें' में आपका इंतज़ार कर रहे हैं।",
}
ESCALATE_TEXT = {
    "en": "{n} question(s) for {name} got no answer 48 hours after a reminder and are now in your Open Questions.",
    "kn": "{name} ಅವರ {n} ಪ್ರಶ್ನೆ(ಗಳು) ನೆನಪಿಸಿದ 48 ಗಂಟೆಗಳ ನಂತರವೂ ಉತ್ತರ ಪಡೆದಿಲ್ಲ; ಈಗ ನಿಮ್ಮ ತೆರೆದ ಪ್ರಶ್ನೆಗಳಲ್ಲಿವೆ.",
    "hi": "{name} के {n} सवालों का याद दिलाने के 48 घंटे बाद भी जवाब नहीं आया; अब वे आपके खुले सवालों में हैं।",
}


def _ts(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _lang(conn, user_id):
    row = conn.execute("SELECT language FROM users WHERE id = ?", (user_id,)).fetchone()
    return row["language"] if row and row["language"] in REMIND_TEXT else "en"


def _notify(conn, user_id, patient_id, kind, text, link):
    conn.execute("INSERT INTO notifications (user_id, patient_id, kind, text, link) VALUES (?, ?, ?, ?, ?)",
                 (user_id, patient_id, kind, text, link))


def run_reminders(now=None, patient_id=None):
    now = now or datetime.now(timezone.utc)
    cutoff = _ts(now - WAIT)
    reminded, escalated = {}, {}
    with get_conn() as conn:
        where, args = ("AND patient_id = ?", [patient_id]) if patient_id else ("", [])
        # 1. remind: open, asked 48 h ago or more, never reminded
        for q in conn.execute(f"""SELECT id, patient_id FROM questions WHERE status = 'open' AND reminded_at IS NULL
                                  AND created_at <= ? {where}""", [cutoff, *args]).fetchall():
            conn.execute("UPDATE questions SET reminded_at = ? WHERE id = ?", (_ts(now), q["id"]))
            reminded.setdefault(q["patient_id"], []).append(q["id"])
        # 2. escalate: still open 48 h after the reminder (claim questions stay with the patient)
        for q in conn.execute(f"""SELECT id, patient_id FROM questions WHERE status = 'open' AND claim_condition IS NULL
                                  AND reminded_at IS NOT NULL AND reminded_at <= ? {where}""",
                              [cutoff, *args]).fetchall():
            conn.execute(
                """UPDATE questions SET status = 'sent_to_doctor', escalated_at = ?,
                   route_reason = 'no answer 48 hours after a reminder' WHERE id = ?""", (_ts(now), q["id"]))
            escalated.setdefault(q["patient_id"], []).append(q["id"])

        for pid, ids in reminded.items():
            for u in conn.execute("""SELECT up.user_id FROM user_patients up JOIN users u ON u.id = up.user_id
                                     WHERE up.patient_id = ? AND u.role = 'patient'""", (pid,)):
                _notify(conn, u["user_id"], pid, "question_reminder",
                        REMIND_TEXT[_lang(conn, u["user_id"])].format(n=len(ids)), "/things")
            record(conn, pid, None, "remind", "ok", f"reminded the patient about {len(ids)} unanswered question(s)")
        for pid, ids in escalated.items():
            name = (conn.execute("SELECT name FROM patients WHERE id = ?", (pid,)).fetchone() or {"name": pid})["name"]
            for d in conn.execute("SELECT doctor_id FROM care_team WHERE patient_id = ? AND status = 'active'", (pid,)):
                _notify(conn, d["doctor_id"], pid, "question_escalated",
                        ESCALATE_TEXT[_lang(conn, d["doctor_id"])].format(n=len(ids), name=name), "/brief")
            record(conn, pid, None, "escalate", "warn",
                   f"{len(ids)} question(s) unanswered 48 h after the reminder: moved to the doctor's Open Questions")
    return {"reminded": [i for ids in reminded.values() for i in ids],
            "escalated": [i for ids in escalated.values() for i in ids]}


def start_scheduler():
    """Run the reminders every 15 minutes in a background thread (daemon: stops with the server)."""
    def loop():
        while True:
            try:
                run_reminders()
            except Exception as e:  # never let a bad run stop the loop
                print(f"reminders: {e!r}")
            time.sleep(EVERY_SECONDS)

    threading.Thread(target=loop, name="question-reminders", daemon=True).start()


if __name__ == "__main__":
    hours = float(sys.argv[sys.argv.index("--hours") + 1]) if "--hours" in sys.argv else 0
    result = run_reminders(datetime.now(timezone.utc) + timedelta(hours=hours))
    print(json.dumps(result))
