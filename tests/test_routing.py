"""Who the agent asks (AGENTIC_PLAN point 7): clinical conflicts go straight to the doctor,
everything else to the patient first. Uses p1's real demo documents (saved results, no AI)."""
import gc

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    gc.collect()
    import os

    from backend import load_demo
    # conftest points seed.ROOT at a temp folder (for storage); the demo PDFs and saved results
    # are read from the real data/ folder
    load_demo.ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_demo.load(["p1"], use_saved=True)
    from backend.main import app
    return TestClient(app)


def questions():
    from backend.db import get_conn
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM questions WHERE patient_id = 'p1'")]


def test_clinical_conflicts_go_straight_to_the_doctor(client):
    qs = questions()
    allergy = [q for q in qs if "allergic" in q["text"].lower()]
    assert allergy and all(q["routed_to"] == "doctor" and q["status"] == "sent_to_doctor" for q in allergy)
    assert "allergy records disagree" in allergy[0]["route_reason"]

    wrong = [q for q in qs if "may belong to someone else" in q["text"]]
    assert wrong and wrong[0]["routed_to"] == "doctor" and wrong[0]["status"] == "sent_to_doctor"


def test_everything_else_asks_the_patient_first(client):
    qs = questions()
    still_taking = [q for q in qs if "still taking" in q["text"] and q["status"] != "resolved"]  # not retired
    assert still_taking and all(q["routed_to"] == "patient" and q["status"] == "open" for q in still_taking)


def test_each_side_sees_the_right_questions(client):
    sunita = {"Authorization": "Bearer " + client.post("/login", json={"username": "sunita", "password": "sunita123"}).json()["token"]}
    mine = client.get("/patients/p1/questions", headers=sunita).json()
    open_for_patient = [q for q in mine if q["status"] == "open"]  # what Things to Check shows
    assert open_for_patient and all(q["routed_to"] == "patient" for q in open_for_patient)

    # the doctor (through a share) sees the doctor-routed ones in the brief, with the reason
    guest = {"Authorization": "Bearer " + client.post("/login", json={"username": "guestdoctor", "password": "guest123"}).json()["token"]}
    code = client.post("/patients/p1/share", json={"minutes": 5}, headers=sunita).json()["code"]
    client.post("/share/open", json={"code": code}, headers=guest)
    brief = client.get("/patients/p1/brief", headers=guest).json()
    direct = [q for q in brief["open_questions"] if q["routed_to"] == "doctor"]
    assert direct and all(q["route_reason"] for q in direct)


def test_routing_is_recorded_as_an_agent_step(client):
    from backend.agent.steps import steps_for
    d3 = [s for s in steps_for("p1_d3") if s["step"] == "questions"]
    assert d3 and "straight to the doctor" in d3[0]["detail"]


def test_outdated_questions_are_retired(client):
    open_qs = [q for q in questions() if q["status"] in ("open", "sent_to_doctor")]
    atenolol = [q for q in open_qs if q["text"].startswith("Atenolol")]
    assert len(atenolol) == 1 and "3 documents" in atenolol[0]["text"]        # the newest picture only
    assert not [q for q in open_qs if q["text"].startswith("Metformin 500mg")]  # dose changed in 2023
    retired = [q for q in questions() if q["answer"] and '"superseded"' in q["answer"]]
    assert retired  # kept for the record, marked as retired by the agent
