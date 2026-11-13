"""In-page search (backend/search.py, GET /patients/{id}/search) on Nisha (p7): a pneumonia
episode on 03/11/2025 (prescription, CRP report, chest X-ray) and an unrelated 2024
diabetes visit. Her 5 PDFs go through ingest_document with the saved pipeline output
(data/extracted/p7.json), so no AI is called; recompute_patient builds the search index.
"""
import gc
import json
import os

import pytest
from fastapi.testclient import TestClient

from backend import seed
from backend.db import get_conn
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
def doctor(client):
    """A doctor who opened Nisha's share (the only way a doctor sees a patient)."""
    headers = login(client, "doctor", "doctor123")
    code = client.post("/patients/p7/share", json={"minutes": 30}, headers=login(client, "nisha", "nisha123")).json()["code"]
    assert client.post("/share/open", json={"code": code}, headers=headers).status_code == 200
    return headers


def search(client, headers, q, page):
    r = client.get("/patients/p7/search", params={"q": q, "page": page}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def by_name(client, headers):
    """medication fact_id -> medicine name, document_id -> filename"""
    names = {}
    for m in client.get("/patients/p7/medications", headers=headers).json():
        for e in m["entries"]:
            names[e["fact_id"]] = m["name"]
    for d in client.get("/patients/p7/documents", headers=headers).json():
        names[d["id"]] = d["filename"]
    return names


def test_pneumonia_on_the_medications_page(client, doctor):
    names = by_name(client, doctor)
    results = search(client, doctor, "pneumonia", "medications")
    found = {names[r["item_id"]]: r for r in results}
    assert found["Augmentin"]["reason"] == "mentioned"
    assert found["Augmentin"]["score"] == 1.0
    assert "pneumonia" in [t.lower() for t in found["Augmentin"]["matched_terms"]]
    assert "pneumonia" in found["Augmentin"]["source"]["text"]
    assert found["Azithromycin"]["reason"] == "same_visit" and found["Azithromycin"]["score"] == 0.7
    assert found["Paracetamol"]["reason"] == "same_visit"
    assert "Metformin" not in found and "Atorvastatin" not in found  # the 2024 diabetes visit
    assert [r["score"] for r in results] == sorted([r["score"] for r in results], reverse=True)


def test_pneumonia_on_the_records_page(client, doctor):
    names = by_name(client, doctor)
    found = {names[r["item_id"]]: r for r in search(client, doctor, "pneumonia", "records")}
    assert found["d5_chest_xray_2025.pdf"]["reason"] == "mentioned"
    assert found["d3_prescription_2025.pdf"]["reason"] == "mentioned"
    assert found["d4_lab_crp_2025.pdf"]["reason"] == "same_visit"  # same day, never says pneumonia
    assert "d1_prescription_2024.pdf" not in found and "d2_lab_2024.pdf" not in found


def test_lung_infection_finds_the_same_items(client, doctor):
    for page in ("medications", "records"):
        pneumonia = {r["item_id"] for r in search(client, doctor, "pneumonia", page)}
        lung = {r["item_id"] for r in search(client, doctor, "lung infection", page)}
        assert pneumonia <= lung, page


def test_brand_name_finds_the_generic(client, doctor):
    names = by_name(client, doctor)
    found = {names[r["item_id"]]: r for r in search(client, doctor, "Glycomet", "medications")}
    assert found["Metformin"]["reason"] == "mentioned"
    assert "Metformin" in found["Metformin"]["matched_terms"]


def test_unrelated_query_matches_nothing(client, doctor):
    assert search(client, doctor, "fracture", "medications") == []
    assert search(client, doctor, "fracture", "records") == []
    assert search(client, doctor, "   ", "records") == []


def test_no_access_without_a_share(client):
    stranger = login(client, "guestdoctor", "guest123")
    r = client.get("/patients/p7/search", params={"q": "pneumonia", "page": "records"}, headers=stranger)
    assert r.status_code == 403
    assert client.get("/patients/p7/documents", headers=stranger).status_code == 403


def test_bad_page_is_refused(client, doctor):
    r = client.get("/patients/p7/search", params={"q": "pneumonia", "page": "timeline"}, headers=doctor)
    assert r.status_code == 422


def test_audit_log_has_the_query_but_no_record_content(client, doctor):
    search(client, doctor, "pneumonia", "records")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT detail FROM audit_log WHERE action = 'search' AND patient_id = 'p7' ORDER BY id DESC").fetchone()
    detail = json.loads(row["detail"])
    assert detail["query"] == "pneumonia" and detail["page"] == "records" and detail["matches"] >= 3
    assert "consolidation" not in row["detail"].lower()  # nothing from the documents themselves


def test_index_text_is_encrypted_in_the_database(client):
    with get_conn() as conn:
        rows = conn.execute("SELECT search_text FROM search_items WHERE patient_id = 'p7'").fetchall()
    assert rows and not any("pneumonia" in r["search_text"].lower() for r in rows)
