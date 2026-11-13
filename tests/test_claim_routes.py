"""Claim Documents API (backend/routes/claims.py), end to end on a throwaway database.

Ravi's 5 synthetic PDFs go through the same ingest_document() as an upload, using the saved
pipeline output (data/extracted/p6.json), so no AI is called. The discharge summary opens
his hospital stay automatically.
"""
import io
import json
import os
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend import seed
from backend.db import get_conn
from backend.ingest import ingest_document

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def client():
    seed.seed(with_sample_facts=False)
    with open(os.path.join(ROOT, "data", "extracted", "p6.json"), encoding="utf-8") as f:
        saved = {d["document_id"]: d for d in json.load(f)["documents"]}
    for d in sorted(seed.load_answer_key("p6")["documents"], key=lambda d: d["filename"]):
        with open(os.path.join(ROOT, "data", "patients", "p6", d["filename"]), "rb") as f:
            ingest_document("p6", d["filename"], f.read(), saved=saved[d["document_id"]])

    from backend.main import app
    return TestClient(app)


def login(client, username, password):
    token = client.post("/login", json={"username": username, "password": password}).json()["token"]
    return {"Authorization": "Bearer " + token}


@pytest.fixture(scope="module")
def ravi(client):
    return login(client, "ravi", "ravi123")


@pytest.fixture(scope="module")
def sunita(client):
    return login(client, "sunita", "sunita123")


@pytest.fixture(scope="module")
def doctor(client, ravi):
    """A doctor sees Ravi only after Ravi shares by code (backend/auth.py)."""
    headers = login(client, "doctor", "doctor123")
    code = client.post("/patients/p6/share", json={"minutes": 30}, headers=ravi).json()["code"]
    assert client.post("/share/open", json={"code": code}, headers=headers).status_code == 200
    return headers


def stay_id(client, headers):
    stays = client.get("/patients/p6/hospital-stays", headers=headers).json()
    return next(s["id"] for s in stays if s["source"] == "discharge_summary")


def checklist(client, headers, sid):
    r = client.get(f"/patients/p6/hospital-stays/{sid}/claim-checklist", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def answer(client, headers, sid, condition, value):
    q = checklist(client, headers, sid)["condition_questions"][condition]
    return client.post(f"/questions/{q['id']}/answer", json={"answer": value}, headers=headers)


def test_documents_are_classified_with_verified_quotes(client):
    with get_conn() as conn:
        rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM documents WHERE patient_id = 'p6'")}
    assert {r["doc_type"] for r in rows.values()} == {
        "lab_report", "discharge_summary", "final_bill", "pharmacy_bill", "prescription"}
    assert all(r["doc_type_quote"] and r["doc_type_page"] and r["doc_type_line"] for r in rows.values())


def test_discharge_summary_opens_a_stay_with_verified_dates(client, ravi):
    stays = client.get("/patients/p6/hospital-stays", headers=ravi).json()
    assert len(stays) == 1
    s = stays[0]
    assert (s["source"], s["admitted_on"], s["discharged_on"]) == ("discharge_summary", "2026-10-05", "2026-10-09")
    assert (s["surgery"], s["implant_used"], s["accident"]) == (None, None, None)


def test_condition_questions_appear_in_things_to_check(client, ravi, doctor):
    questions = client.get("/patients/p6/questions", headers=ravi).json()
    claim = {q["claim_condition"]: q for q in questions if q["claim_condition"]}
    assert set(claim) == {"surgery", "implant_used", "accident"}
    assert claim["surgery"]["text"] == "Did you have surgery during this hospital stay?"
    brief = client.get("/patients/p6/brief", headers=doctor).json()
    assert not any("hospital stay" in q["text"] for q in brief["open_questions"])  # never sent to the doctor


def test_unanswered_conditions_are_unsure(client, ravi):
    result = checklist(client, ravi, stay_id(client, ravi))
    assert result["summary"] == {"saved_count": 5, "required_count": 6, "unsure_count": 3}


def test_only_the_patient_answers_and_only_yes_no_dont_know(client, ravi, doctor):
    sid = stay_id(client, ravi)
    assert answer(client, doctor, sid, "surgery", "yes").status_code == 403
    assert answer(client, ravi, sid, "surgery", "skip").status_code == 422
    assert answer(client, ravi, sid, "surgery", "value").status_code == 422


def test_dont_know_keeps_the_question_open_and_the_item_unsure(client, ravi):
    sid = stay_id(client, ravi)
    r = answer(client, ravi, sid, "accident", "dont_know")
    assert r.status_code == 200 and r.json()["status"] == "open"
    items = {i["doc"]: i["status"] for i in checklist(client, ravi, sid)["items"]}
    assert items["fir_or_mlc"] == "unsure"


def test_ravi_after_answering_five_of_eight_saved(client, ravi):
    sid = stay_id(client, ravi)
    for condition, value in [("surgery", "yes"), ("implant_used", "yes"), ("accident", "no")]:
        assert answer(client, ravi, sid, condition, value).status_code == 200
    result = checklist(client, ravi, sid)
    items = {i["doc"]: i["status"] for i in result["items"]}
    assert result["summary"]["saved_count"] == 5 and result["summary"]["required_count"] == 8
    assert {d for d, s in items.items() if s == "not_saved"} == {"payment_receipt", "implant_invoice", "operation_notes"}
    assert items["fir_or_mlc"] == "not_needed"
    # created today -> the discharge reminder lists exactly the 3 missing documents
    assert result["reminder"] == {"show": True, "docs": ["payment_receipt", "operation_notes", "implant_invoice"]}
    assert result["stay"]["surgery"] is True and result["stay"]["accident"] is False


def test_claim_pack_files_in_checklist_order(client, ravi):
    sid = stay_id(client, ravi)
    r = client.get(f"/patients/p6/hospital-stays/{sid}/claim-pack", headers=ravi)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    pack = zipfile.ZipFile(io.BytesIO(r.content))
    assert pack.namelist() == [
        "01_discharge_summary.pdf", "02_final_bill.pdf", "04_pharmacy_bill.pdf",
        "05_investigation_report.pdf", "06_prescription.pdf", "checklist.txt",
    ]
    assert all(pack.read(n).startswith(b"%PDF") for n in pack.namelist() if n.endswith(".pdf"))
    text = pack.read("checklist.txt").decode()
    assert "5 of 8 documents saved" in text
    assert "03  Payment receipts: not saved yet" in text
    assert "09  FIR or MLC copy: not needed" in text


def test_access_denied_for_another_patient(client, ravi, sunita):
    sid = stay_id(client, ravi)
    base = f"/patients/p6/hospital-stays/{sid}"
    assert client.get(base + "/claim-checklist", headers=sunita).status_code == 403
    assert client.get(base + "/claim-pack", headers=sunita).status_code == 403
    assert client.get("/patients/p6/hospital-stays", headers=sunita).status_code == 403
    assert client.post("/patients/p6/hospital-stays", headers=sunita).status_code == 403
    assert client.patch(base, json={"admitted_on": "2026-10-01"}, headers=sunita).status_code == 403
    # a stay id that belongs to someone else is not found under your own patient id
    assert client.get(f"/patients/p1/hospital-stays/{sid}/claim-checklist", headers=sunita).status_code == 404


def test_only_the_patient_creates_or_edits_a_stay(client, doctor):
    assert client.post("/patients/p6/hospital-stays", headers=doctor).status_code == 403


def test_audit_log_records_views_and_downloads(client, ravi):
    actions = [row["action"] for row in client.get("/patients/p6/audit", headers=ravi).json()]
    assert "view_claim_checklist" in actions
    assert "download_claim_pack" in actions


def test_patient_creates_a_stay_and_edits_dates(client, ravi):
    r = client.post("/patients/p6/hospital-stays", headers=ravi)
    assert r.status_code == 200
    new = r.json()
    assert (new["source"], new["admitted_on"], new["discharged_on"]) == ("patient", None, None)
    # no dates yet -> every verified document counts; conditions not answered yet
    assert checklist(client, ravi, new["id"])["summary"] == {"saved_count": 5, "required_count": 6, "unsure_count": 3}

    base = f"/patients/p6/hospital-stays/{new['id']}"
    assert client.patch(base, json={"admitted_on": "05/10/2026"}, headers=ravi).status_code == 422
    r = client.patch(base, json={"admitted_on": "2026-11-01", "my_reminder_date": "2026-12-01"}, headers=ravi)
    assert r.status_code == 200 and r.json()["my_reminder_date"] == "2026-12-01"
    # Ravi's documents are from October, before this stay started
    assert checklist(client, ravi, new["id"])["summary"]["saved_count"] == 0
    actions = [row["action"] for row in client.get("/patients/p6/audit", headers=ravi).json()]
    assert "create_hospital_stay" in actions and "update_hospital_stay" in actions


def test_delete_my_data_removes_stays(client, ravi):
    r = client.delete("/patients/p6", headers=ravi)
    assert r.status_code == 200 and r.json()["deleted"]["hospital_stays"] == 2
    with get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM hospital_stays WHERE patient_id = 'p6'").fetchone()[0] == 0
