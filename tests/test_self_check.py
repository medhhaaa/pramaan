"""The agent checks its own work: retry, then 'App not sure' (AGENTIC_PLAN point 5). No AI is called."""
import gc
import json

import pymupdf
import pytest
from fastapi.testclient import TestClient

from backend import seed

P1_D1 = "data/patients/p1/d1_prescription_2019.pdf"
GOOD = {"type": "medication", "name": "Metformin", "dose": "500mg", "frequency": "BD", "action": "started",
        "value": None, "unit": None,
        "status": "documented", "event_date": "2019-03-12", "date_raw": "12/03/2019", "quote": "Tab. Metformin 500mg BD"}
# the AI "remembers" a medicine that is not in the document at all
INVENTED = {**GOOD, "name": "Glimepiride", "dose": "2mg", "frequency": "OD", "quote": "Tab. Glimepiride 2mg OD"}


def extraction(facts):
    return {"document_date": "2019-03-12", "document_date_raw": "12/03/2019", "doc_type": "prescription",
            "doc_type_quote": "PRESCRIPTION", "doc_type_confidence": "high", "facts": [dict(f) for f in facts]}


@pytest.fixture(scope="module")
def client():
    gc.collect()
    seed.seed(with_sample_facts=False)
    from backend.main import app
    return TestClient(app)


def headers(client, username="sunita", password="sunita123"):
    token = client.post("/login", json={"username": username, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def upload(client, path=P1_D1):
    with open(path, "rb") as f:
        r = client.post("/patients/p1/upload", files={"file": (path.split("/")[-1], f, "application/pdf")},
                        headers=headers(client))
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def steps(client, doc_id):
    return client.get(f"/documents/{doc_id}/agent-steps", headers=headers(client)).json()["steps"]


def test_unproven_fact_goes_to_app_not_sure_and_can_be_accepted_or_rejected(client, monkeypatch):
    from pipeline import process
    monkeypatch.delenv("LLM_STRONG_MODEL", raising=False)
    monkeypatch.setattr(process, "extract_document", lambda text, receipt=None, model=None: extraction([GOOD, INVENTED]))
    doc_id = upload(client)

    retry = [s for s in steps(client, doc_id) if s["step"] == "retry"]
    assert any("digital text" in s["detail"] for s in retry)          # re-read skipped for a digital PDF
    assert any("no stronger model" in s["detail"] for s in retry)
    assert any("App not sure" in s["detail"] for s in retry)

    items = client.get("/patients/p1/not-sure", headers=headers(client)).json()
    item = next(i for i in items if i["document_id"] == doc_id)
    assert item["fact"]["name"] == "Glimepiride" and "not found" in item["reason"]

    # Ravi can't see or resolve Sunita's items
    ravi = headers(client, "ravi", "ravi123")
    assert client.get("/patients/p1/not-sure", headers=ravi).status_code == 403
    assert client.post(f"/not-sure/{item['id']}/resolve", json={"action": "accept"}, headers=ravi).status_code == 403

    r = client.post(f"/not-sure/{item['id']}/resolve", json={"action": "accept"}, headers=headers(client)).json()
    assert r["status"] == "accepted" and r["fact"]["corrected"] and not r["fact"]["quote_verified"]
    assert client.post(f"/not-sure/{item['id']}/resolve", json={"action": "reject"},
                       headers=headers(client)).status_code == 409   # already resolved
    assert not [i for i in client.get("/patients/p1/not-sure", headers=headers(client)).json() if i["id"] == item["id"]]


def test_reject_keeps_it_out_of_the_record(client, monkeypatch):
    from pipeline import process
    monkeypatch.delenv("LLM_STRONG_MODEL", raising=False)
    monkeypatch.setattr(process, "extract_document", lambda text, receipt=None, model=None: extraction([INVENTED]))
    doc_id = upload(client)
    item = next(i for i in client.get("/patients/p1/not-sure", headers=headers(client)).json() if i["document_id"] == doc_id)
    assert client.post(f"/not-sure/{item['id']}/resolve", json={"action": "reject"},
                       headers=headers(client)).json() == {"status": "rejected"}
    timeline = client.get("/patients/p1/timeline", headers=headers(client)).json()
    assert not [f for f in timeline if f["document_id"] == doc_id and f["name"] == "Glimepiride"]


def test_stronger_model_recovers_a_fact(client, monkeypatch):
    from pipeline import extract, process
    monkeypatch.setenv("LLM_STRONG_MODEL", "big-model")
    # first run: Metformin's dose misread (not in the quoted line) -> dropped; the stronger model gets it right
    bad = {**GOOD, "dose": "5000mg"}
    monkeypatch.setattr(process, "extract_document", lambda text, receipt=None, model=None: extraction([bad]))
    monkeypatch.setattr(extract, "extract_document",
                        lambda text, receipt=None, model=None: extraction([GOOD] if model == "big-model" else [bad]))
    doc_id = upload(client)
    retry = [s["detail"] for s in steps(client, doc_id) if s["step"] == "retry"]
    assert any("stronger model (big-model): 1 recovered" in d for d in retry), retry
    timeline = client.get("/patients/p1/timeline", headers=headers(client)).json()
    assert [f for f in timeline if f["document_id"] == doc_id and f["name"] == "Metformin" and f["dose"] == "500mg"]
    assert not [i for i in client.get("/patients/p1/not-sure", headers=headers(client)).json() if i["document_id"] == doc_id]


def test_reread_ocr_pages_at_higher_resolution():
    try:
        pymupdf.get_tessdata()
    except RuntimeError:
        pytest.skip("Tesseract language data not installed")
    from pipeline.ocr import make_searchable
    from pipeline.self_check import ocr_pages, reread_lines
    import os
    import tempfile

    pdf = make_searchable(open("data/scanned/p1/d1_prescription_2019.pdf", "rb").read())
    path = os.path.join(tempfile.gettempdir(), "reread_test.pdf")
    open(path, "wb").write(pdf)
    assert ocr_pages(path) == [1]
    text = " ".join(l["text"] for l in reread_lines(path, [1]))
    assert "Metformin" in text
