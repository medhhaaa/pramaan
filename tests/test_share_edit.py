"""The patient changes what an open share shows: PUT /share/{id}/scope (backend/routes/share.py).
Nisha (p7): diabetes visit (Metformin) and a pneumonia episode in "other" (Augmentin)."""
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


def open_share(client, nisha, doctor, scope):
    for s in client.get("/patients/p7/shares", headers=nisha).json():
        client.delete(f"/share/{s['share_id']}", headers=nisha)
    r = client.post("/patients/p7/share", json={"minutes": 15, "scope": scope}, headers=nisha)
    assert client.post("/share/open", json={"code": r.json()["code"]}, headers=doctor).status_code == 200
    return r.json()["share_id"]


def medicines(client, headers):
    return {m["name"] for m in client.get("/patients/p7/medications", headers=headers).json()}


def test_patient_shares_more_then_takes_it_back(client):
    nisha, doctor = login(client, "nisha", "nisha123"), login(client, "doctor", "doctor123")
    share_id = open_share(client, nisha, doctor, ["diabetes"])
    assert "Augmentin" not in medicines(client, doctor)

    # the doctor asks; the patient adds "other" from the Share page instead of the request card
    assert client.post("/patients/p7/share-requests", json={"note": "antibiotic?"}, headers=doctor).status_code == 200
    r = client.put(f"/share/{share_id}/scope", json={"scope": ["diabetes", "other"]}, headers=nisha)
    assert r.status_code == 200 and r.json()["added"] == ["other"] and r.json()["removed"] == []
    assert "Augmentin" in medicines(client, doctor)
    assert client.get("/patients/p7/share-requests", headers=nisha).json() == []  # request answered

    # ... and takes it back: hidden again at once
    r = client.put(f"/share/{share_id}/scope", json={"scope": ["diabetes"]}, headers=nisha)
    assert r.json()["removed"] == ["other"]
    assert "Augmentin" not in medicines(client, doctor) and "Metformin" in medicines(client, doctor)

    # everything, then back to a part
    assert client.put(f"/share/{share_id}/scope", json={"scope": "all"}, headers=nisha).json()["scope"] == "all"
    assert "Augmentin" in medicines(client, doctor)
    r = client.put(f"/share/{share_id}/scope", json={"scope": ["diabetes"]}, headers=nisha).json()
    assert "other" in r["removed"] and "Augmentin" not in medicines(client, doctor)


def test_only_the_patient_changes_an_open_share(client):
    nisha, doctor, ravi = (login(client, "nisha", "nisha123"), login(client, "doctor", "doctor123"),
                           login(client, "ravi", "ravi123"))
    share_id = open_share(client, nisha, doctor, ["diabetes"])
    assert client.put(f"/share/{share_id}/scope", json={"scope": "all"}, headers=doctor).status_code == 403
    assert client.put(f"/share/{share_id}/scope", json={"scope": "all"}, headers=ravi).status_code == 404
    assert client.put(f"/share/{share_id}/scope", json={"scope": []}, headers=nisha).status_code == 422
    assert client.put(f"/share/{share_id}/scope", json={"scope": ["nonsense"]}, headers=nisha).status_code == 422
    client.delete(f"/share/{share_id}", headers=nisha)
    assert client.put(f"/share/{share_id}/scope", json={"scope": "all"}, headers=nisha).status_code == 404
