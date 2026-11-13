"""Partial sharing (backend/routes/share.py + share_requests.py, backend/scope.py) on Nisha (p7):
2024 diabetes visit (Metformin; Atorvastatin = "heart"), 2025 pneumonia episode (Augmentin,
Azithromycin, Paracetamol, CRP, chest X-ray = "other"). The patient shares only "diabetes";
the doctor sees that something is hidden (counts only), asks for more, the patient adds "other".
"""
import gc
import json
import os

import pytest
from fastapi.testclient import TestClient

from backend import seed
from backend.ingest import ingest_document

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def client():
    gc.collect()  # earlier test files leave sqlite connections open; Windows then can't reseed
    seed.seed(with_sample_facts=False)
    with open(os.path.join(ROOT, "data", "extracted", "p7.json"), encoding="utf-8") as f:
        saved = {d["document_id"]: d for d in json.load(f)["documents"]}
    for d in sorted(seed.load_answer_key("p7")["documents"], key=lambda d: d["filename"]):
        with open(os.path.join(ROOT, "data", "patients", "p7", d["filename"]), "rb") as f:
            ingest_document("p7", d["filename"], f.read(), saved=saved[d["document_id"]])
    from backend.main import app
    return TestClient(app)


def login(client, username, password):
    token = client.post("/login", json={"username": username, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def nisha(client):
    return login(client, "nisha", "nisha123")


@pytest.fixture(scope="module")
def doctor(client):
    return login(client, "doctor", "doctor123")


def share(client, nisha, doctor, scope="all"):
    """Stop Nisha's earlier shares, make a new one with this scope, the doctor opens it."""
    for s in client.get("/patients/p7/shares", headers=nisha).json():
        client.delete(f"/share/{s['share_id']}", headers=nisha)
    r = client.post("/patients/p7/share", json={"minutes": 15, "scope": scope}, headers=nisha)
    assert r.status_code == 200, r.text
    assert client.post("/share/open", json={"code": r.json()["code"]}, headers=doctor).status_code == 200
    return r.json()


def medicines(client, headers):
    return {m["name"] for m in client.get("/patients/p7/medications", headers=headers).json()}


def filenames(client, headers):
    return {d["filename"]: d["id"] for d in client.get("/patients/p7/documents", headers=headers).json()}


def test_patient_sees_the_groups_in_their_records(client, nisha):
    out = client.get("/patients/p7/share-options", headers=nisha).json()
    groups = {g["tag"]: g for g in out["groups"]}
    assert {"diabetes", "heart", "other"} <= set(groups)
    assert "Metformin" in groups["diabetes"]["examples"]
    assert "asthma" not in groups  # only groups the records actually have
    assert "allergy" in out["always"] and "demographic" in out["always"]


def test_share_options_are_the_patients_own(client, doctor):
    assert client.get("/patients/p7/share-options", headers=doctor).status_code == 403


def test_bad_scope_is_refused(client, nisha):
    for scope in (["nonsense"], []):
        r = client.post("/patients/p7/share", json={"minutes": 15, "scope": scope}, headers=nisha)
        assert r.status_code == 422, scope


def test_full_share_hides_nothing(client, nisha, doctor):
    made = share(client, nisha, doctor)
    assert made["scope"] == "all"
    assert {"Metformin", "Augmentin", "Atorvastatin"} <= medicines(client, doctor)
    assert client.get("/patients/p7/hidden", headers=doctor).json() == {"partial": False}


def test_partial_share_shows_only_the_chosen_group(client, nisha, doctor):
    share(client, nisha, doctor, ["diabetes"])
    meds = medicines(client, doctor)
    assert "Metformin" in meds
    assert "Augmentin" not in meds and "Atorvastatin" not in meds
    timeline = client.get("/patients/p7/timeline", headers=doctor).json()
    assert not any("pneumonia" in (f["name"] or "").lower() for f in timeline)

    docs = filenames(client, doctor)
    assert "d2_lab_2024.pdf" in docs and "d1_prescription_2024.pdf" in docs
    assert "d3_prescription_2025.pdf" not in docs and "d5_chest_xray_2025.pdf" not in docs
    assert client.get("/documents/p7_d3", headers=doctor).status_code == 403

    # the in-page search finds nothing hidden, not even a "same visit" through a hidden item
    for page in ("records", "medications"):
        r = client.get("/patients/p7/search", params={"q": "pneumonia", "page": page}, headers=doctor)
        assert r.json() == [], page


def test_doctor_is_told_what_kind_of_thing_is_hidden_but_not_what(client, nisha, doctor):
    share(client, nisha, doctor, ["diabetes"])
    r = client.get("/patients/p7/hidden", headers=doctor)
    out = r.json()
    assert out["partial"] and out["can_request"] and out["request"] is None
    hidden = out["hidden"]
    assert hidden["medicines"] >= 4  # Augmentin, Azithromycin, Paracetamol, Atorvastatin
    assert hidden["current_medicines"] >= 1 and hidden["conditions"] >= 1 and hidden["important"]
    assert hidden["documents"] == 3  # the 2025 prescription, CRP report and chest X-ray
    text = r.text.lower()
    for secret in ("augmentin", "pneumonia", "atorvastatin", "heart", "other", "2025"):
        assert secret not in text, secret


def test_check_medicine_warns_about_a_hidden_current_medicine(client, nisha, doctor):
    share(client, nisha, doctor, ["diabetes"])
    r = client.post("/patients/p7/check-medicine", json={"drug": "Amoxicillin"}, headers=doctor).json()
    hidden = [w for w in r["warnings"] if w["kind"] == "hidden_match"]
    assert len(hidden) == 1 and hidden[0]["source"] is None
    assert "augmentin" not in hidden[0]["text"].lower()
    # nothing hidden matches a diabetes medicine the doctor can already see
    r = client.post("/patients/p7/check-medicine", json={"drug": "Glimepiride"}, headers=doctor).json()
    assert not any(w["kind"] == "hidden_match" for w in r["warnings"])


def test_ask_for_more_and_the_patient_adds_a_group(client, nisha, doctor):
    share(client, nisha, doctor, ["diabetes"])
    r = client.post("/patients/p7/share-requests", json={"note": "Need your recent antibiotics"}, headers=doctor)
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert client.post("/patients/p7/share-requests", json={}, headers=doctor).status_code == 409  # one at a time
    assert client.get("/patients/p7/hidden", headers=doctor).json()["request"]["status"] == "pending"

    bell = client.get("/me/notifications", headers=nisha).json()
    assert any(n["kind"] == "share_request" for n in bell)

    pending = client.get("/patients/p7/share-requests", headers=nisha).json()
    assert len(pending) == 1 and pending[0]["note"] == "Need your recent antibiotics"
    options = {g["tag"] for g in pending[0]["options"]}
    assert {"heart", "other"} <= options and "diabetes" not in options

    rid = pending[0]["id"]
    assert client.post(f"/share-requests/{rid}/answer", json={"add": ["other"]}, headers=doctor).status_code == 403
    out = client.post(f"/share-requests/{rid}/answer", json={"add": ["other"]}, headers=nisha).json()
    assert out["status"] == "answered" and out["scope"] == ["diabetes", "other"]

    meds = medicines(client, doctor)
    assert "Augmentin" in meds and "Atorvastatin" not in meds  # heart still hidden
    assert "d3_prescription_2025.pdf" in filenames(client, doctor)
    assert client.get("/patients/p7/hidden", headers=doctor).json()["request"]["status"] == "answered"
    assert client.get("/patients/p7/share-requests", headers=nisha).json() == []
    assert client.post(f"/share-requests/{rid}/answer", json={"add": "all"}, headers=nisha).status_code == 409


def test_patient_can_decline(client, nisha, doctor):
    share(client, nisha, doctor, ["diabetes"])
    client.post("/patients/p7/share-requests", json={}, headers=doctor)
    rid = client.get("/patients/p7/share-requests", headers=nisha).json()[0]["id"]
    out = client.post(f"/share-requests/{rid}/answer", json={"decline": True}, headers=nisha).json()
    assert out == {"id": rid, "status": "declined", "scope": ["diabetes"]}
    assert "Augmentin" not in medicines(client, doctor)


def test_requests_need_an_open_partial_share(client, nisha, doctor):
    assert client.post("/patients/p7/share-requests", json={}, headers=nisha).status_code == 403
    share(client, nisha, doctor)  # everything shared: nothing to ask for
    assert client.post("/patients/p7/share-requests", json={}, headers=doctor).status_code == 409
    stranger = login(client, "guestdoctor", "guest123")
    assert client.post("/patients/p7/share-requests", json={}, headers=stranger).status_code == 403
    assert client.get("/patients/p7/hidden", headers=stranger).status_code == 403


def test_stopping_the_share_removes_its_requests(client, nisha, doctor):
    made = share(client, nisha, doctor, ["diabetes"])
    client.post("/patients/p7/share-requests", json={}, headers=doctor)
    client.delete(f"/share/{made['share_id']}", headers=nisha)
    assert client.get("/patients/p7/share-requests", headers=nisha).json() == []
    assert client.get("/patients/p7/hidden", headers=doctor).status_code == 403


def test_share_list_tells_the_patient_when_the_care_team_sees_more(client, nisha, doctor):
    """A care-team doctor (scope all) opens a diabetes-only QR: they keep seeing everything
    (auth.py adds both scopes), so the patient's Share page must say so instead of "Diabetes"."""
    from backend.db import get_conn

    with get_conn() as conn:
        doctor_id = conn.execute("SELECT id FROM users WHERE username = 'doctor'").fetchone()["id"]
    entry = client.post("/patients/p7/care-team", json={"doctor_id": doctor_id, "scope": "all"}, headers=nisha)
    assert entry.status_code == 200, entry.text
    try:
        share(client, nisha, doctor, ["diabetes"])
        row = client.get("/patients/p7/shares", headers=nisha).json()[0]
        assert row["scope"] == ["diabetes"] and row["care_team_scope"] == "all" and row["sees"] == "all"
        assert "Augmentin" in medicines(client, doctor)
        assert client.get("/patients/p7/hidden", headers=doctor).json() == {"partial": False}
    finally:
        client.post(f"/patients/p7/care-team/{entry.json()['id']}/revoke", headers=nisha)
    row = client.get("/patients/p7/shares", headers=nisha).json()[0]
    assert row["care_team_scope"] is None and row["sees"] == ["diabetes"]
