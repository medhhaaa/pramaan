"""The document agent: every upload step is recorded ('What the agent did'). No AI is called:
the extraction step returns the saved results for that document."""
import gc
import json

import pytest
from fastapi.testclient import TestClient

from backend import seed

P1_D1 = "data/patients/p1/d1_prescription_2019.pdf"
P1_D7 = "data/patients/p1/d7_lab_psa.pdf"  # someone else's report (wrong patient)


def saved_extraction(document_id):
    saved = {d["document_id"]: d for d in json.load(open("data/extracted/p1.json", encoding="utf-8"))["documents"]}
    d = saved[document_id]
    return {"document_date": d.get("document_date"), "document_date_raw": d.get("document_date_raw"),
            # the saved file has the type but not the line that proves it; the real AI returns both
            "doc_type": d.get("doc_type"),
            "doc_type_quote": d.get("doc_type_quote") or {"prescription": "PRESCRIPTION"}.get(d.get("doc_type")),
            "doc_type_confidence": d.get("doc_type_confidence", "high"), "facts": d["facts"]}


@pytest.fixture(scope="module")
def client():
    gc.collect()
    seed.seed(with_sample_facts=False)
    from backend.main import app
    return TestClient(app)


def headers(client, username="sunita", password="sunita123"):
    token = client.post("/login", json={"username": username, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def upload(client, monkeypatch, path, saved_id):
    from pipeline import process
    monkeypatch.setattr(process, "extract_document", lambda text, receipt=None: saved_extraction(saved_id))
    with open(path, "rb") as f:
        r = client.post("/patients/p1/upload", files={"file": (path.split("/")[-1], f, "application/pdf")},
                        headers=headers(client))
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def test_every_step_is_recorded_in_order(client, monkeypatch):
    doc_id = upload(client, monkeypatch, P1_D1, "p1_d1")
    r = client.get(f"/documents/{doc_id}/agent-steps", headers=headers(client))
    assert r.status_code == 200
    steps = [s["step"] for s in r.json()["steps"]]
    assert steps == ["read", "protect", "extract", "check", "classify", "patient", "save", "merge", "questions"], steps
    by_step = {s["step"]: s for s in r.json()["steps"]}
    assert "personal details replaced" in by_step["protect"]["detail"]
    assert by_step["classify"]["detail"].startswith("prescription")


def test_wrong_patient_step_says_held_back(client, monkeypatch):
    doc_id = upload(client, monkeypatch, P1_D7, "p1_d7")
    steps = {s["step"]: s for s in client.get(f"/documents/{doc_id}/agent-steps", headers=headers(client)).json()["steps"]}
    assert steps["patient"]["status"] == "blocked" and "held back" in steps["patient"]["detail"]


def test_steps_respect_access(client):
    ravi = headers(client, "ravi", "ravi123")
    assert client.get("/documents/p1_d1/agent-steps", headers=ravi).status_code == 403
    assert client.get("/documents/nope/agent-steps", headers=ravi).status_code == 404
