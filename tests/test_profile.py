"""Health profile form (backend/routes/profile.py): the patient's answers become patient_reported
facts that take part in the checks. p1's real demo documents (saved results, no AI)."""
import gc
import os

import pytest
from fastapi.testclient import TestClient

from backend.db import get_conn


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


def profile_facts():
    with get_conn() as conn:
        return {r["fact_id"]: dict(r) for r in conn.execute("SELECT * FROM facts WHERE document_id = 'p1_profile'")}


def test_form_is_needed_once_and_starts_from_the_patient_record(client):
    sunita = login(client, "sunita", "sunita123")
    p = client.get("/patients/p1/profile", headers=sunita).json()
    assert p["needed"] and p["dob"] == "1952-06-14" and p["sex"] == "Female" and p["blood_group"] == "O+"
    assert p["allergy_answer"] is None and p["allergies"] == []
    assert client.post("/patients/p1/profile/skip", headers=sunita).json()["needed"] is False


def test_allergy_from_the_patient_is_patient_reported_and_conflicts_with_no_known_allergies(client):
    sunita = login(client, "sunita", "sunita123")
    body = {"dob": "1952-06-14", "sex": "Female", "blood_group": "O+", "allergy_answer": "yes",
            "allergies": [{"name": "Sulfa drugs", "reaction": "rash"}, {"name": " sulfa  drugs ", "reaction": None}]}
    r = client.put("/patients/p1/profile", json=body, headers=sunita)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["needed"] is False and out["allergies"] == [{"name": "Sulfa drugs", "reaction": "rash"}]  # same allergy once
    assert out["mismatches"] == []

    facts = profile_facts()
    sulfa = facts["p1_profile_allergy_sulfa_drugs"]
    assert sulfa["quote"] == "Allergy: Sulfa drugs (reaction: rash)" and sulfa["value"] == "rash"
    # d1 says "No known drug allergies": a contradiction, so the patient's answer shows as conflicting
    assert "contradiction" in sulfa["flags"] and sulfa["badge"] == "conflicting"
    assert facts["p1_profile_blood_group"]["badge"] == "patient_reported"

    # the doctor gets an Open Question about it, quoting the patient's own answer
    with get_conn() as conn:
        q = conn.execute("""SELECT * FROM questions WHERE patient_id = 'p1' AND fact_ids LIKE '%p1_profile_allergy%'
                            AND status != 'resolved'""").fetchone()
    assert q and q["routed_to"] == "doctor" and "health profile filled in by the patient" in q["text"]

    # timeline and click-to-proof show the answers
    timeline = client.get("/patients/p1/timeline", headers=sunita).json()
    assert any(f["fact_id"] == "p1_profile_allergy_sulfa_drugs" for f in timeline)
    doc = client.get("/documents/p1_profile", headers=sunita).json()
    assert [l["text"] for l in doc["lines"]][:3] == ["Date of birth: 1952-06-14", "Sex: Female", "Blood group: O+"]


def test_patient_answers_never_count_as_a_second_document(client):
    sunita = login(client, "sunita", "sunita123")
    with get_conn() as conn:
        before = conn.execute("SELECT fact_id, badge FROM facts WHERE patient_id = 'p1' AND type = 'allergy'"
                              " AND name = 'Penicillin'").fetchall()
    client.put("/patients/p1/profile", json={"allergy_answer": "yes", "allergies": [{"name": "Penicillin"}]},
               headers=sunita)
    with get_conn() as conn:
        for row in before:
            badge = conn.execute("SELECT badge FROM facts WHERE fact_id = ?", (row["fact_id"],)).fetchone()["badge"]
            assert badge != "independent_2plus"  # still one document, whatever the patient says


def test_dont_know_stores_nothing_and_removed_answers_are_deleted(client):
    sunita = login(client, "sunita", "sunita123")
    client.put("/patients/p1/profile", json={"blood_group": "O+", "allergy_answer": "none"}, headers=sunita)
    assert profile_facts()["p1_profile_no_known_allergies"]["status"] == "negated"

    out = client.put("/patients/p1/profile", json={"allergy_answer": "dont_know"}, headers=sunita).json()
    assert profile_facts() == {}  # nothing typed = nothing stored: not documented stays not documented
    assert out["allergy_answer"] == "dont_know" and out["blood_group"] is None
    with get_conn() as conn:
        assert conn.execute("SELECT 1 FROM documents WHERE id = 'p1_profile'").fetchone() is None
        saves = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'save_profile'").fetchone()[0]
    assert saves == 2  # every save (with its answers) is in the audit log


def test_a_different_blood_group_is_shown_but_never_overrides_the_record(client):
    sunita = login(client, "sunita", "sunita123")
    out = client.put("/patients/p1/profile", json={"blood_group": "B+", "sex": "Female"}, headers=sunita).json()
    assert [(m["field"], m["you_said"], m["records_say"]) for m in out["mismatches"]] == [("blood_group", "B+", "O+")]
    with get_conn() as conn:
        assert conn.execute("SELECT blood_group FROM patients WHERE id = 'p1'").fetchone()[0] == "O+"


def test_check_medicine_says_the_patient_reported_it(client):
    sunita = login(client, "sunita", "sunita123")
    client.put("/patients/p1/profile", json={"allergy_answer": "yes", "allergies": [{"name": "Ibuprofen", "reaction": "swelling"}]},
               headers=sunita)
    r = client.post("/patients/p1/check-medicine", json={"drug": "Ibuprofen"}, headers=sunita)
    assert r.status_code == 200, r.text
    texts = " ".join(w.get("text", "") for w in r.json().get("warnings", []))
    assert "The patient reported a Ibuprofen allergy (swelling) in their health profile" in texts


def test_only_the_patient_fills_in_their_profile(client):
    doctor, ravi = login(client, "doctor", "doctor123"), login(client, "ravi", "ravi123")
    body = {"blood_group": "A+"}
    assert client.get("/patients/p1/profile", headers=ravi).status_code == 403
    assert client.put("/patients/p1/profile", json=body, headers=ravi).status_code == 403
    assert client.put("/patients/p1/profile", json=body, headers=doctor).status_code == 403
    sunita = login(client, "sunita", "sunita123")
    bad = client.put("/patients/p1/profile", json={"dob": "2999-01-01"}, headers=sunita)
    assert bad.status_code == 422
    assert client.put("/patients/p1/profile", json={"allergy_answer": "yes", "allergies": []},
                      headers=sunita).status_code == 422
