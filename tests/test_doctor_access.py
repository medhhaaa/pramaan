"""Doctors see a patient ONLY through a QR / code share the patient made (backend/auth.py).

Before the share: no patient in the list, 403 on the brief and the timeline.
During the share: reading plus review work (correct a fact); never upload, delete or share.
After the patient stops the share: 403 again.
"""
import pytest
from fastapi.testclient import TestClient

from backend import seed


@pytest.fixture(scope="module")
def client():
    seed.seed(with_sample_facts=True)  # p1's sample facts, so there is something to correct
    from backend.main import app
    return TestClient(app)


def login(client, username, password):
    token = client.post("/login", json={"username": username, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_doctor_sees_a_patient_only_while_a_share_is_open(client):
    for name, password in [("doctor", "doctor123"), ("guestdoctor", "guest123")]:
        doctor = login(client, name, password)
        sunita = login(client, "sunita", "sunita123")

        # no share: nothing
        assert client.get("/patients", headers=doctor).json() == []
        assert client.get("/patients/p1/brief", headers=doctor).status_code == 403
        assert client.get("/patients/p1/timeline", headers=doctor).status_code == 403

        # Sunita shares, the doctor types the code
        share = client.post("/patients/p1/share", json={"minutes": 15}, headers=sunita).json()
        assert client.post("/share/open", json={"code": share["code"]}, headers=doctor).status_code == 200
        assert [p["id"] for p in client.get("/patients", headers=doctor).json()] == ["p1"]
        assert client.get("/patients/p1/brief", headers=doctor).status_code == 200
        facts = client.get("/patients/p1/timeline", headers=doctor).json()
        assert facts

        # review work is allowed, adding or deleting data is not
        fact = next(f for f in facts if f["type"] == "medication")
        r = client.post(f"/facts/{fact['fact_id']}/correct", json={"field": "dose", "new_value": fact["dose"]}, headers=doctor)
        assert r.status_code == 200
        assert client.delete("/patients/p1", headers=doctor).status_code == 403
        assert client.post("/patients/p1/share", json={"minutes": 15}, headers=doctor).status_code == 403
        r = client.post("/patients/p1/upload", files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")}, headers=doctor)
        assert r.status_code == 403

        # Sunita stops the share: access is gone
        assert client.delete(f"/share/{share['share_id']}", headers=sunita).status_code == 200
        assert client.get("/patients/p1/brief", headers=doctor).status_code == 403
        assert client.get("/patients", headers=doctor).json() == []


def test_every_demo_patient_can_share(client):
    for username, password, pid in [("sunita", "sunita123", "p1"), ("iqbal", "iqbal123", "p2"),
                                    ("lakshmi", "lakshmi123", "p3"), ("arjun", "arjun123", "p4"),
                                    ("gopal", "gopal123", "p5"), ("ravi", "ravi123", "p6")]:
        me = login(client, username, password)
        assert [p["id"] for p in client.get("/patients", headers=me).json()] == [pid]
        assert client.post(f"/patients/{pid}/share", json={"minutes": 5}, headers=me).status_code == 200


def test_a_patient_never_sees_someone_else(client):
    sunita = login(client, "sunita", "sunita123")
    assert client.get("/patients/p2/brief", headers=sunita).status_code == 403
    assert client.get("/patients/p2/timeline", headers=sunita).status_code == 403
