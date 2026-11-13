"""Upload report: where a duplicate is stored (backend/upload_report.py, POST /patients/{id}/upload).
Sunita (p1): d6 is a planted exact copy of the d5 lab report; d3 and d4 copy medicine lines from
d1. Documents go in through ingest_document with the saved pipeline output, so no AI is called."""
import gc
import json
import os

import pytest
from fastapi.testclient import TestClient

from backend import seed
from backend.ingest import ingest_document
from backend.upload_report import where_else

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVED = {d["document_id"]: d for d in
         json.load(open(os.path.join(ROOT, "data", "extracted", "p1.json"), encoding="utf-8"))["documents"]}


def pdf(name):
    with open(os.path.join(ROOT, "data", "patients", "p1", name), "rb") as f:
        return f.read()


@pytest.fixture(scope="module")
def client():
    gc.collect()  # earlier test files leave sqlite connections open; Windows then can't reseed
    seed.seed(with_sample_facts=False)
    for doc_id, name in [("p1_d1", "d1_prescription_2019.pdf"), ("p1_d2", "d2_lab_2021.pdf"),
                         ("p1_d3", "d3_discharge_2022.pdf"), ("p1_d4", "d4_prescription_2023.pdf"),
                         ("p1_d5", "d5_lab_2023.pdf")]:
        ingest_document("p1", name, pdf(name), saved=SAVED[doc_id])
    from backend.main import app
    return TestClient(app)


def test_a_copied_lab_report_points_to_the_original(client):
    new = ingest_document("p1", "d6_lab_2023_copy.pdf", pdf("d6_lab_2023_copy.pdf"), saved=SAVED["p1_d6"])
    report = where_else("p1", new["document_id"])
    copy = report["copy_of_document"]
    assert copy and copy["id"] == "p1_d5" and copy["filename"] == "d5_lab_2023.pdf"
    assert copy["matching"] == copy["of"] > 0
    dup = {d["name"]: d for d in report["duplicates"]}
    assert dup["HbA1c"]["kind"] == "duplicate" and dup["HbA1c"]["value"] == "8.1"
    original = dup["HbA1c"]["original"]
    assert original["document_id"] == "p1_d5" and original["page"] and original["line"]
    assert "HbA1c" in original["quote"] and original["document_date"] == "2023-01-16"


def test_copied_medicine_lines_point_to_the_older_prescription(client):
    report = where_else("p1", "p1_d4")
    atenolol = [d for d in report["duplicates"] if d["name"] == "Atenolol"]
    assert atenolol and atenolol[0]["kind"] == "copied_line"
    assert atenolol[0]["original"]["document_id"] in ("p1_d1", "p1_d3")
    assert not any(d["name"] == "Amlodipine" for d in report["duplicates"])  # newly started: not a copy
    assert report["copy_of_document"] is None  # only some lines are copies


def test_a_new_document_has_no_duplicates(client):
    report = where_else("p1", "p1_d1")
    assert report["copy_of_document"] is None
    assert all(d["kind"] != "copied_line" for d in report["duplicates"])  # d1 is the original


def test_the_upload_route_returns_where_the_duplicate_is(client, monkeypatch):
    """The real route, with the pipeline replaced by the saved output (no AI)."""
    from backend.routes import upload as upload_route

    monkeypatch.setattr(upload_route, "_ingest_one",
                        lambda pid, name, data, doc_type: ingest_document(pid, name, data, doc_type, saved=SAVED["p1_d6"]))
    token = client.post("/login", json={"username": "sunita", "password": "sunita123"}).json()["token"]
    r = client.post("/patients/p1/upload", headers={"Authorization": f"Bearer {token}"},
                    files={"file": ("lab_again.pdf", pdf("d6_lab_2023_copy.pdf"), "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["copy_of_document"]["id"] == "p1_d5"
    assert any(d["original"]["filename"] == "d5_lab_2023.pdf" for d in body["duplicates"])
