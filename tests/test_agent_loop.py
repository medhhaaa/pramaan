"""The question loop (AGENTIC_PLAN points 8-11): Hindi questions, 48 h reminder, escalation to the
doctor, answers that update the record. p1's real demo documents (saved results, no AI)."""
import gc
import os
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.db import get_conn

DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def fresh():
    gc.collect()
    from backend import load_demo
    load_demo.ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # real data/ folder
    load_demo.load(["p1"], use_saved=True)


@pytest.fixture()
def client():
    fresh()
    from backend.main import app
    return TestClient(app)


def login(client, username, password):
    return {"Authorization": "Bearer " + client.post("/login", json={"username": username, "password": password}).json()["token"]}


def still_taking(conn):
    return conn.execute("""SELECT * FROM questions WHERE patient_id = 'p1' AND status = 'open'
                           AND text LIKE 'Atenolol%still taking%'""").fetchone()


def test_questions_in_hindi_keep_medicine_names(client):
    sunita = login(client, "sunita", "sunita123")
    assert client.put("/me/language", json={"language": "hi"}, headers=sunita).status_code == 200
    open_qs = [q for q in client.get("/patients/p1/questions", headers=sunita).json() if q["status"] == "open"]
    q = next(q for q in open_qs if "Atenolol" in q["text"])
    assert DEVANAGARI.search(q["text"]) and "Atenolol 50mg OD" in q["text"]   # Hindi, names as written


def test_no_to_still_taking_marks_the_medicine_stopped(client):
    sunita = login(client, "sunita", "sunita123")
    with get_conn() as conn:
        q = still_taking(conn)
    r = client.post(f"/questions/{q['id']}/answer", json={"answer": "no"}, headers=sunita)
    assert r.status_code == 200 and r.json()["status"] == "answered"
    with get_conn() as conn:
        latest = conn.execute("""SELECT * FROM facts WHERE patient_id = 'p1' AND name = 'Atenolol'
                                 ORDER BY event_date DESC LIMIT 1""").fetchone()
        correction = conn.execute("SELECT * FROM corrections WHERE fact_id = ? AND field = 'action'",
                                  (latest["fact_id"],)).fetchone()
        step = conn.execute("SELECT detail FROM agent_steps WHERE step = 'answer' ORDER BY id DESC").fetchone()
    assert latest["action"] == "stopped" and latest["corrected"]
    assert correction["new_value"] == "stopped" and correction["role"] == "patient"  # original kept
    assert "Atenolol marked as stopped" in step["detail"]


def test_dont_know_tells_the_doctor_why(client):
    sunita = login(client, "sunita", "sunita123")
    with get_conn() as conn:
        q = still_taking(conn)
    r = client.post(f"/questions/{q['id']}/answer", json={"answer": "dont_know"}, headers=sunita).json()
    assert r["status"] == "sent_to_doctor" and r["route_reason"] == "the patient answered: I don't know"


def test_reminder_after_48h_then_escalation_after_another_48h(client):
    from backend.agent.reminders import run_reminders
    now = datetime.now(timezone.utc)
    assert run_reminders(now + timedelta(hours=47), "p1") == {"reminded": [], "escalated": []}  # too early

    first = run_reminders(now + timedelta(hours=49), "p1")
    assert first["reminded"] and not first["escalated"]
    with get_conn() as conn:
        note = conn.execute("""SELECT n.text FROM notifications n JOIN users u ON u.id = n.user_id
                               WHERE u.username = 'sunita' AND n.kind = 'question_reminder'""").fetchone()
    assert note and "Things to Check" in note["text"]

    assert run_reminders(now + timedelta(hours=60), "p1")["escalated"] == []  # reminder only 11 h ago
    second = run_reminders(now + timedelta(hours=98), "p1")
    assert second["escalated"] and not second["reminded"]
    with get_conn() as conn:
        q = conn.execute("SELECT * FROM questions WHERE id = ?", (second["escalated"][0],)).fetchone()
        claim_escalated = conn.execute("""SELECT COUNT(*) FROM questions WHERE patient_id = 'p1'
                                          AND claim_condition IS NOT NULL AND escalated_at IS NOT NULL""").fetchone()[0]
        steps = [r["step"] for r in conn.execute("SELECT step FROM agent_steps WHERE document_id IS NULL")]
    assert q["status"] == "sent_to_doctor" and q["route_reason"] == "no answer 48 hours after a reminder"
    assert claim_escalated == 0                      # claim questions stay with the patient
    assert "remind" in steps and "escalate" in steps


def test_demo_route_respects_access(client):
    sunita, ravi = login(client, "sunita", "sunita123"), login(client, "ravi", "ravi123")
    assert client.post("/patients/p1/agent/run-reminders?hours=49", headers=ravi).status_code == 403
    r = client.post("/patients/p1/agent/run-reminders?hours=49", headers=sunita)
    assert r.status_code == 200 and r.json()["reminded"]
    assert client.get("/patients/p1/agent-steps", headers=sunita).json()["steps"][-1]["step"] == "remind"
