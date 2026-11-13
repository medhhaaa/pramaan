"""Disease search (backend/disease_search.py, GET /patients/{id}/disease-search) on Sunita (p1,
shared/sample_facts.json): type 2 diabetes with Metformin, HbA1c and fasting glucose; Atenolol and
Amlodipine (blood pressure); a held-back PSA report. No AI involved."""
import gc
import json

import pytest
from fastapi.testclient import TestClient

from backend import seed
from backend.db import get_conn
from backend.disease_search import resolve


@pytest.fixture(scope="module")
def client():
    gc.collect()  # earlier test files leave sqlite connections open; Windows then can't reseed
    seed.seed(with_sample_facts=True)
    from backend.main import app
    return TestClient(app)


def login(client, username, password):
    token = client.post("/login", json={"username": username, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def sunita(client):
    return login(client, "sunita", "sunita123")


@pytest.fixture(scope="module")
def doctor(client):
    return login(client, "doctor", "doctor123")


def share(client, sunita, doctor, scope="all"):
    for s in client.get("/patients/p1/shares", headers=sunita).json():
        client.delete(f"/share/{s['share_id']}", headers=sunita)
    code = client.post("/patients/p1/share", json={"minutes": 15, "scope": scope}, headers=sunita).json()["code"]
    assert client.post("/share/open", json={"code": code}, headers=doctor).status_code == 200


def search(client, headers, q):
    r = client.get("/patients/p1/disease-search", params={"q": q}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def ids(result):
    return sorted(i["fact_id"] for s in ("conditions", "medicines", "labs", "events") for i in result[s])


def names(result, section):
    return {i["name"] for i in result[section]}


def test_diabetes_sugar_and_glycomet_give_the_same_results(client, sunita):
    results = [search(client, sunita, q) for q in ("diabetes", "sugar", "Glycomet")]
    assert {r["disease"] for r in results} == {"diabetes"}
    assert ids(results[0]) and ids(results[0]) == ids(results[1]) == ids(results[2])
    r = results[0]
    assert names(r, "conditions") == {"Type 2 diabetes mellitus"}
    assert names(r, "medicines") == {"Metformin"}
    assert names(r, "labs") == {"HbA1c", "Fasting blood glucose"}
    assert "Atenolol" not in names(r, "medicines")  # blood pressure, not diabetes
    assert "PSA" not in names(r, "labs")
    assert {d["id"] for d in r["documents"]} >= {"p1_d1", "p1_d2", "p1_d4"}
    assert r["hidden_count"] == 0


def test_how_the_query_was_understood():
    assert resolve("sugar") == ("diabetes", "condition")
    assert resolve("T2DM") == ("diabetes", "condition")
    assert resolve("Glycomet 500") == ("diabetes", "medicine")
    assert resolve("HbA1c") == ("diabetes", "lab")
    assert resolve("lung infection") == ("pneumonia", "condition")
    assert resolve("fracture") == (None, None)
    assert resolve("   ") == (None, None)


def test_every_item_can_open_its_source(client, sunita):
    for item in search(client, sunita, "diabetes")["labs"]:
        assert item["document_id"] and item["event_date"] and "line" in item and "quote" in item


def test_unknown_disease_finds_nothing(client, sunita):
    r = search(client, sunita, "fracture")
    assert r["disease"] is None and ids(r) == [] and r["documents"] == []


def test_partial_sharing_is_respected(client, sunita, doctor):
    full = search(client, sunita, "diabetes")
    share(client, sunita, doctor, ["hypertension"])
    hidden = search(client, doctor, "diabetes")
    assert ids(hidden) == [] and hidden["documents"] == []
    assert hidden["hidden_count"] == len(ids(full))  # how many, never what
    bp = search(client, doctor, "high blood pressure")
    assert bp["disease"] == "hypertension" and {"Atenolol", "Amlodipine"} <= names(bp, "medicines")
    share(client, sunita, doctor, "all")
    assert ids(search(client, doctor, "diabetes")) == ids(full)


def test_no_access_without_a_share(client):
    stranger = login(client, "guestdoctor", "guest123")
    r = client.get("/patients/p1/disease-search", params={"q": "diabetes"}, headers=stranger)
    assert r.status_code == 403


def test_audit_row_has_the_query_not_the_records(client, sunita):
    search(client, sunita, "sugar")
    with get_conn() as conn:
        row = conn.execute("SELECT detail FROM audit_log WHERE action = 'disease_search' ORDER BY id DESC").fetchone()
    detail = json.loads(row["detail"])
    assert detail["query"] == "sugar" and detail["disease"] == "diabetes" and detail["matches"] > 0
    assert "Metformin" not in row["detail"] and "HbA1c" not in row["detail"]
