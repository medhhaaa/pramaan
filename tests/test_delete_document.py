"""DELETE /documents/{id}: delete one uploaded document, e.g. a file added twice by mistake.
Sunita (p1): d6 is a planted exact copy of d5; d4 copies the Atenolol line from d1. Documents go
in through ingest_document with the saved pipeline output, so no AI is called."""
import gc
import json
import os

import pytest
from fastapi.testclient import TestClient

from backend import seed, storage
from backend.db import get_conn
from backend.ingest import ingest_document
from backend.routes import delete as delete_route

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVED = {d["document_id"]: d for d in
         json.load(open(os.path.join(ROOT, "data", "extracted", "p1.json"), encoding="utf-8"))["documents"]}
FILES = {"p1_d1": "d1_prescription_2019.pdf", "p1_d4": "d4_prescription_2023.pdf",
         "p1_d5": "d5_lab_2023.pdf", "p1_d6": "d6_lab_2023_copy.pdf"}


def pdf(name):
    with open(os.path.join(ROOT, "data", "patients", "p1", name), "rb") as f:
        return f.read()


def login(client, username, password):
    token = client.post("/login", json={"username": username, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client(monkeypatch):
    gc.collect()  # earlier test files leave sqlite connections open; Windows then can't reseed
    seed.seed(with_sample_facts=False)
    ids = {}
    for saved_id, name in FILES.items():  # ids follow upload order: d1, d2, d3, d4 here
        ids[saved_id] = ingest_document("p1", name, pdf(name), saved=SAVED[saved_id])["document_id"]
    # uploads are stored under the test folder (conftest): delete files from there too
    monkeypatch.setattr(delete_route, "ROOT", storage.ROOT)
    monkeypatch.setattr(delete_route, "STORAGE_DIR", os.path.join(storage.ROOT, "storage"))
    from backend.main import app
    c = TestClient(app)
    c.ids = ids
    return c


def facts_of(document_id):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM facts WHERE document_id = ?", (document_id,))]


def test_patient_deletes_a_copy_uploaded_twice(client):
    sunita = login(client, "sunita", "sunita123")
    copy_id = client.ids["p1_d6"]
    with get_conn() as conn:
        file_path = conn.execute("SELECT file_path FROM documents WHERE id = ?", (copy_id,)).fetchone()["file_path"]
    assert facts_of(copy_id) and os.path.isfile(storage.abs_path(file_path))

    r = client.delete(f"/documents/{copy_id}", headers=sunita)
    assert r.status_code == 200
    assert r.json()["deleted"]["document_id"] == copy_id and r.json()["deleted"]["facts"] > 0
    assert r.json()["deleted"]["files"] == 1

    listed = [d["id"] for d in client.get("/patients/p1/documents", headers=sunita).json()]
    assert copy_id not in listed and client.ids["p1_d5"] in listed  # the original stays
    assert facts_of(copy_id) == [] and not os.path.exists(storage.abs_path(file_path))
    # the original's results are no longer duplicates of anything
    assert all("duplicate" not in json.loads(f["flags"]) for f in facts_of(client.ids["p1_d5"]))
    audit = client.get("/patients/p1/audit", headers=sunita).json()
    assert any(row.get("action") == "delete_document" for row in audit)


def test_every_check_runs_again_without_the_deleted_document(client):
    """d4's Atenolol line is a copy of d1's. Delete d1 and it is the original again."""
    sunita = login(client, "sunita", "sunita123")
    atenolol = [f for f in facts_of(client.ids["p1_d4"]) if f["name"] == "Atenolol"]
    assert atenolol and atenolol[0]["echo_of"]
    assert client.delete(f"/documents/{client.ids['p1_d1']}", headers=sunita).status_code == 200
    atenolol = [f for f in facts_of(client.ids["p1_d4"]) if f["name"] == "Atenolol"]
    assert atenolol[0]["echo_of"] is None


def test_only_the_patient_can_delete(client):
    doc_id = client.ids["p1_d6"]
    sunita, iqbal = login(client, "sunita", "sunita123"), login(client, "iqbal", "iqbal123")
    doctor = login(client, "doctor", "doctor123")
    assert client.delete(f"/documents/{doc_id}", headers=iqbal).status_code == 403  # another patient
    share = client.post("/patients/p1/share", json={"minutes": 15}, headers=sunita).json()
    assert client.post("/share/open", json={"code": share["code"]}, headers=doctor).status_code == 200
    assert client.delete(f"/documents/{doc_id}", headers=doctor).status_code == 403  # doctors only read
    assert facts_of(doc_id)
    assert client.delete("/documents/p1_d999", headers=sunita).status_code == 404


def test_the_health_profile_is_not_deleted_here(client):
    sunita = login(client, "sunita", "sunita123")
    body = {"sex": "Female", "blood_group": "O+", "allergy_answer": "none", "allergies": []}
    assert client.put("/patients/p1/profile", json=body, headers=sunita).status_code == 200
    r = client.delete("/documents/p1_profile", headers=sunita)
    assert r.status_code == 400 and "profile" in r.json()["detail"]
    assert facts_of("p1_profile")


# ---------- PATCH /documents/{id}: rename ----------

def test_patient_renames_a_document(client):
    sunita = login(client, "sunita", "sunita123")
    doc_id = client.ids["p1_d5"]
    facts_before = facts_of(doc_id)
    r = client.patch(f"/documents/{doc_id}", json={"filename": "  HbA1c   January 2023  "}, headers=sunita)
    assert r.status_code == 200
    assert r.json() == {"id": doc_id, "filename": "HbA1c January 2023.pdf"}  # spaces tidied, .pdf kept
    listed = {d["id"]: d["filename"] for d in client.get("/patients/p1/documents", headers=sunita).json()}
    assert listed[doc_id] == "HbA1c January 2023.pdf"
    assert facts_of(doc_id) == facts_before  # only the name changes
    # a name with its own extension is kept as typed
    r = client.patch(f"/documents/{doc_id}", json={"filename": "lab.PDF"}, headers=sunita)
    assert r.json()["filename"] == "lab.PDF"
    audit = client.get("/patients/p1/audit", headers=sunita).json()
    assert any(row.get("action") == "rename_document" for row in audit)


def test_bad_names_are_refused(client):
    sunita = login(client, "sunita", "sunita123")
    doc_id = client.ids["p1_d5"]
    for bad in ["", "   ", "../secret", "a\b", "x" * 200]:
        assert client.patch(f"/documents/{doc_id}", json={"filename": bad}, headers=sunita).status_code == 422, bad


def test_only_the_patient_can_rename(client):
    doc_id = client.ids["p1_d5"]
    sunita, iqbal = login(client, "sunita", "sunita123"), login(client, "iqbal", "iqbal123")
    doctor = login(client, "doctor", "doctor123")
    assert client.patch(f"/documents/{doc_id}", json={"filename": "x"}, headers=iqbal).status_code == 403
    share = client.post("/patients/p1/share", json={"minutes": 15}, headers=sunita).json()
    assert client.post("/share/open", json={"code": share["code"]}, headers=doctor).status_code == 200
    assert client.patch(f"/documents/{doc_id}", json={"filename": "x"}, headers=doctor).status_code == 403
    assert client.patch("/documents/p1_d999", json={"filename": "x"}, headers=sunita).status_code == 404
