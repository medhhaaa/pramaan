"""Sign-up (POST /signup in backend/auth.py): new accounts are added next to the demo ones,
and a new patient starts with an empty record of their own. Throwaway database (conftest.py)."""
import gc

import pytest
from fastapi.testclient import TestClient

from backend import seed


@pytest.fixture(scope="module")
def client():
    gc.collect()  # close sqlite connections other test files left open (Windows file lock)
    seed.seed(with_sample_facts=True)
    from backend.main import app
    return TestClient(app)


def auth(token):
    return {"Authorization": "Bearer " + token}


def sign_up(client, **body):
    return client.post("/signup", json={"password": "secret123", "role": "patient", "full_name": "Asha Kamath", **body})


def test_new_patient_gets_an_empty_record_of_their_own(client):
    r = sign_up(client, username="asha")
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "patient" and r.json()["language"] is None
    me = auth(r.json()["token"])
    [own] = client.get("/patients", headers=me).json()
    assert own["id"] == "p101" and own["name"] == "Asha Kamath"
    assert client.get("/patients/p101/timeline", headers=me).json() == []
    assert client.get("/patients/p101/documents", headers=me).json() == []
    assert client.get("/patients/p1/timeline", headers=me).status_code == 403  # nobody else's records
    # and the new account can log in like any other
    r = client.post("/login", json={"username": "asha", "password": "secret123"})
    assert r.status_code == 200 and r.json()["role"] == "patient"


def test_demo_accounts_are_kept(client):
    sign_up(client, username="ben", full_name="Ben D'Souza")
    for username in ("sunita", "doctor", "drrao"):
        password = username + "123"
        assert client.post("/login", json={"username": username, "password": password}).status_code == 200
    sunita = auth(client.post("/login", json={"username": "sunita", "password": "sunita123"}).json()["token"])
    assert len(client.get("/patients/p1/timeline", headers=sunita).json()) > 0  # demo data untouched
    ben = auth(client.post("/login", json={"username": "ben", "password": "secret123"}).json()["token"])
    assert client.get("/patients", headers=ben).json()[0]["id"] == "p102"


def test_username_must_be_free(client):
    assert sign_up(client, username="sunita").status_code == 409
    assert sign_up(client, username="ASHA").status_code == 409  # case does not make a new name


def test_input_rules(client):
    assert sign_up(client, username="a b").status_code == 422
    assert sign_up(client, username="ok_name", password="123").status_code == 422
    assert sign_up(client, username="ok_name", full_name="").status_code == 422


def test_signup_keeps_the_audit_chain_intact(client):
    from backend.db import verify_audit_chain

    sign_up(client, username="chain_check", full_name="Chain Check")
    assert verify_audit_chain()["intact"]


def test_scan_without_tesseract_gives_a_clear_message(client, monkeypatch):
    import pymupdf

    from pipeline import handwriting

    monkeypatch.setattr(handwriting, "TESSERACT", r"C:\no\such\tesseract.exe")
    doc = pymupdf.open()
    doc.new_page()  # a page with no text layer, like a scan
    me = auth(client.post("/login", json={"username": "asha", "password": "secret123"}).json()["token"])
    r = client.post("/patients/p101/upload", headers=me,
                    files={"file": ("scan.pdf", doc.tobytes(), "application/pdf")})
    assert r.status_code == 503 and "Tesseract" in r.json()["detail"]


def test_new_doctor_needs_a_registration_number_and_sees_nobody(client):
    assert sign_up(client, username="drnew", role="doctor", full_name="Dr. New").status_code == 422
    r = sign_up(client, username="drnew", role="doctor", full_name="Dr. New", registration_number="KMC 70001")
    assert r.status_code == 200 and r.json()["role"] == "doctor"
    assert client.get("/patients", headers=auth(r.json()["token"])).json() == []
    # patients can find the new doctor to add them to a care team
    asha = auth(client.post("/login", json={"username": "asha", "password": "secret123"}).json()["token"])
    found = client.get("/doctors/search", params={"q": "70001"}, headers=asha).json()
    assert [d["name"] for d in found] == ["Dr. New"]
