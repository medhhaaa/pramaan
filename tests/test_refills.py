"""Refill requests (backend/routes/refills.py) and consult records (backend/routes/consult_records.py),
on a throwaway database with Dr. Rao's demo care team (backend/demo_care_team.py).

Tests in this file run in order and share one database (Meena's demo refill is decided here).
"""
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.adherence import today_utc
from backend.db import get_conn
from backend.prescriptions import create_prescription
from backend.routes import refills
from tests.demo_helpers import load_care_team_demo, login, user_id

BANNED = ["recommend", "should approve", "should decline", "safe to", "we suggest", "advise"]


@pytest.fixture(scope="module")
def client():
    load_care_team_demo()
    from backend.main import app
    return TestClient(app)


def meena_request():
    with get_conn() as conn:
        return dict(conn.execute("SELECT * FROM refill_requests WHERE patient_id = 'p7' ORDER BY id").fetchone())


def item_id(patient_id, medicine):
    with get_conn() as conn:
        return conn.execute(
            "SELECT id FROM prescription_items WHERE patient_id = ? AND medicine = ? AND status = 'active'",
            (patient_id, medicine)).fetchone()["id"]


# ---------- the demo ----------

def test_meenas_refill_is_at_the_top_of_dr_raos_dashboard(client):
    rows = client.get("/doctors/me/patients", headers=login(client, "drrao")).json()
    assert rows[0]["patient_id"] == "p7" and rows[0]["tags"] == ["refill_request"]
    assert rows[0]["refill_request_id"] == meena_request()["id"]
    pending = client.get("/doctors/me/refill-requests", headers=login(client, "drrao")).json()
    assert [(r["patient_id"], r["medicine"]) for r in pending] == [("p7", "Metformin")]


def test_patient_sees_her_in_app_medicines_and_logs_doses(client):
    meena = login(client, "meena")
    data = client.get("/patients/p7/my-medicines", headers=meena).json()
    [med] = data["medicines"]
    assert (med["medicine"], med["dose"], med["frequency"]) == ("Metformin", "500mg", "BD")
    assert med["can_request_refill"] is False and med["refill_blocked_reason"] == "pending"
    assert [t["time"] for t in med["today"]] == ["08:00", "20:00"]
    rid = med["today"][0]["reminder_id"]
    assert client.post(f"/reminders/{rid}/log", json={"status": "taken"}, headers=meena).status_code == 200
    assert client.post(f"/reminders/{rid}/log", json={"status": "skipped"}, headers=meena).json()["status"] == "skipped"
    future = (today_utc() + timedelta(days=1)).isoformat()
    assert client.post(f"/reminders/{rid}/log", json={"status": "taken", "date": future}, headers=meena).status_code == 422
    assert client.post(f"/reminders/{rid}/log", json={"status": "taken"}, headers=login(client, "drrao")).status_code == 403
    assert client.get("/patients/p7/my-medicines", headers=login(client, "drrao")).status_code == 403


# ---------- refill rules ----------

def test_refill_only_for_an_active_in_app_medicine_from_a_care_team_doctor(client):
    arjun = login(client, "arjun")
    rao, kotian = user_id("drrao"), user_id("drkotian")
    with get_conn() as conn:
        # Dr. Kotian is not on Arjun's care team
        create_prescription(conn, "p4", kotian, [{"medicine": "Montelukast", "dose": "10mg", "frequency": "OD",
                                                   "duration_days": 30}], today_utc() - timedelta(days=5))
        # Dr. Rao's earlier prescription ran out 70 days ago
        create_prescription(conn, "p4", rao, [{"medicine": "Budesonide", "dose": "200mcg", "frequency": "BD",
                                                "duration_days": 30}], today_utc() - timedelta(days=100))
    r = client.post("/patients/p4/refill-requests", json={"prescription_item_id": item_id("p4", "Montelukast")}, headers=arjun)
    assert r.status_code == 422 and "care team" in r.json()["detail"]
    r = client.post("/patients/p4/refill-requests", json={"prescription_item_id": item_id("p4", "Budesonide")}, headers=arjun)
    assert r.status_code == 422 and "not active" in r.json()["detail"]
    # a medicine read from documents (no prescription_items row) or someone else's item
    assert client.post("/patients/p4/refill-requests", json={"prescription_item_id": 99999}, headers=arjun).status_code == 404
    other = item_id("p7", "Metformin")
    assert client.post("/patients/p4/refill-requests", json={"prescription_item_id": other}, headers=arjun).status_code == 404
    # only the patient asks
    assert client.post("/patients/p7/refill-requests", json={"prescription_item_id": other},
                       headers=login(client, "drrao")).status_code == 403


def test_one_pending_request_per_medicine(client):
    r = client.post("/patients/p7/refill-requests", json={"prescription_item_id": item_id("p7", "Metformin")},
                    headers=login(client, "meena"))
    assert r.status_code == 409


def test_only_the_doctor_it_was_sent_to_reviews_it(client):
    req = meena_request()
    assert client.get(f"/refill-requests/{req['id']}/review", headers=login(client, "drkotian")).status_code == 403
    assert client.get(f"/refill-requests/{req['id']}/review", headers=login(client, "meena")).status_code == 403


def test_review_shows_records_and_checks_and_never_recommends(client):
    req = meena_request()
    r = client.get(f"/refill-requests/{req['id']}/review", headers=login(client, "drrao"))
    assert r.status_code == 200
    data = r.json()
    med = data["medicine"]
    assert (med["medicine"], med["dose"], med["frequency"]) == ("Metformin", "500mg", "BD")
    assert med["first_prescribed_at"] == med["prescribed_at"]
    assert len(data["adherence_30d"]["days"]) == 30 and data["adherence_30d"]["percent"] is not None
    report = data["latest_report"]
    assert report["document_id"].startswith("p7_") and report["quote"]
    assert any(a["name"] == "Sulfa drugs" for a in data["brief"]["allergies"])
    assert "Nitrofurantoin" not in json.dumps(data)  # outside Dr. Rao's "diabetes" scope
    assert data["refill_request"]["patient_note"] == "My tablets finish in 4 days."
    text = json.dumps(data).lower()
    assert not [w for w in BANNED if w in text]


def test_decline_without_a_note_is_rejected(client):
    req = meena_request()
    r = client.post(f"/refill-requests/{req['id']}/decision", json={"action": "decline"}, headers=login(client, "drrao"))
    assert r.status_code == 422
    r = client.post(f"/refill-requests/{req['id']}/decision", json={"action": "decline", "note": "   "},
                    headers=login(client, "drrao"))
    assert r.status_code == 422
    assert meena_request()["status"] == "pending"


def test_checks_are_re_run_and_a_warning_needs_an_override_reason(client, monkeypatch):
    calls = []
    real = refills.medicine_warnings

    def spy(patient_id, drug, access, lang="en", renewing_item=None):
        generic, drug_class, warnings = real(patient_id, drug, access, lang, renewing_item)
        calls.append(drug)
        return generic, drug_class, warnings + [{"kind": "allergy", "text": "Test warning", "source": None}]

    monkeypatch.setattr(refills, "medicine_warnings", spy)
    rao, req = login(client, "drrao"), meena_request()
    review = client.get(f"/refill-requests/{req['id']}/review", headers=rao).json()
    assert calls == ["Metformin"] and review["warnings"][-1]["text"] == "Test warning"
    r = client.post(f"/refill-requests/{req['id']}/decision", json={"action": "approve"}, headers=rao)
    assert r.status_code == 422 and r.json()["detail"]["warnings"][-1]["text"] == "Test warning"
    assert calls == ["Metformin", "Metformin"]  # run again at decision time, not trusted from the screen
    assert meena_request()["status"] == "pending"


def test_approve_creates_a_new_version_extends_reminders_and_notifies(client):
    rao, req = login(client, "drrao"), meena_request()
    old_item = req["prescription_item_id"]
    with get_conn() as conn:
        old = dict(conn.execute("SELECT * FROM prescription_items WHERE id = ?", (old_item,)).fetchone())
        reminders = {r["id"] for r in conn.execute("SELECT id FROM reminders WHERE prescription_item_id = ?", (old_item,))}
    r = client.post(f"/refill-requests/{req['id']}/decision", json={"action": "approve"}, headers=rao)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "approved"
    expected_end = (date.fromisoformat(old["end_date"]) + timedelta(days=30)).isoformat()
    assert out["reminders_until"] == expected_end

    with get_conn() as conn:
        new = conn.execute("SELECT * FROM prescription_items WHERE id = ?", (out["new_prescription_item_id"],)).fetchone()
        pres = conn.execute("SELECT * FROM prescriptions WHERE id = ?", (out["new_prescription_id"],)).fetchone()
        old_status = conn.execute("SELECT status FROM prescription_items WHERE id = ?", (old_item,)).fetchone()[0]
        moved = conn.execute("SELECT id, end_date FROM reminders WHERE prescription_item_id = ?", (new["id"],)).fetchall()
    assert (new["medicine"], new["dose"], new["frequency"]) == ("Metformin", "500mg", "BD")
    assert new["previous_item_id"] == old_item and pres["previous_id"] == old["prescription_id"]
    assert old_status == "renewed"
    assert {m["id"] for m in moved} == reminders and {m["end_date"] for m in moved} == {expected_end}

    meena = login(client, "meena")
    note = client.get("/me/notifications", headers=meena).json()[0]
    assert note["kind"] == "refill_approved" and expected_end in note["text"] and note["link"] == "/my-medicines"
    assert client.post(f"/notifications/{note['id']}/read", headers=meena).json()["updated"] is True
    [med] = client.get("/patients/p7/my-medicines", headers=meena).json()["medicines"]
    assert med["end_date"] == expected_end and med["last_refill_request"]["status"] == "approved"
    # decided once only; the renewed medicine can be refilled again later
    assert client.post(f"/refill-requests/{req['id']}/decision", json={"action": "decline", "note": "x"},
                       headers=rao).status_code == 409
    assert med["can_request_refill"] is True


def test_ask_to_visit_uses_the_default_note_and_notifies(client):
    iqbal, rao = login(client, "iqbal"), login(client, "drrao")
    r = client.post("/patients/p2/refill-requests", json={"prescription_item_id": item_id("p2", "Telmisartan")},
                    headers=iqbal)
    assert r.status_code == 200 and r.json()["status"] == "pending"
    rows = {x["patient_id"]: x for x in client.get("/doctors/me/patients", headers=rao).json()}
    assert rows["p2"]["tags"] == ["refill_request", "missed_doses"]  # highest tag first
    r = client.post(f"/refill-requests/{r.json()['id']}/decision", json={"action": "visit"}, headers=rao)
    assert r.status_code == 200 and r.json()["note"] == refills.VISIT_NOTE
    note = client.get("/me/notifications", headers=iqbal).json()[0]
    assert note["kind"] == "refill_visit_required" and refills.VISIT_NOTE in note["text"]
    assert client.get("/me/notifications", headers=login(client, "meena")).json()[0]["kind"] == "refill_approved"


def test_decline_with_a_note(client):
    iqbal, rao = login(client, "iqbal"), login(client, "drrao")
    r = client.post("/patients/p2/refill-requests", json={"prescription_item_id": item_id("p2", "Telmisartan"),
                                                          "note": "Out of tablets"}, headers=iqbal)
    r = client.post(f"/refill-requests/{r.json()['id']}/decision",
                    json={"action": "decline", "note": "We changed this at your last visit."}, headers=rao)
    assert r.status_code == 200 and r.json()["status"] == "declined"
    assert "We changed this at your last visit." in client.get("/me/notifications", headers=iqbal).json()[0]["text"]


# ---------- consult records ----------

def records(client, patient_id, who):
    return client.get(f"/patients/{patient_id}/consult-records", headers=login(client, who)).json()


def test_consult_record_on_every_refill_decision(client):
    recs = records(client, "p7", "drrao")
    assert [r["type"] for r in recs] == ["refill_decision", "prescription"]  # newest first; demo prescription
    rec = client.get(f"/consult-records/{recs[0]['id']}", headers=login(client, "drrao")).json()
    assert rec["decision"]["action"] == "approve" and rec["decision"]["reminders_until"]
    snap = rec["snapshot"]
    assert snap["brief"]["allergies"] and snap["adherence_30d"]["percent"] is not None
    assert snap["refill_request"]["patient_note"] == "My tablets finish in 4 days."
    assert "p7_d1" in snap["source_document_ids"]
    assert [r["decision"]["status"] for r in records(client, "p2", "drrao")[:2]] == ["declined", "visit_required"]


def test_prescription_past_a_warning_needs_an_override_reason(client):
    rao = login(client, "drrao")
    body = {"items": [{"medicine": "Amoxicillin", "dose": "500mg", "frequency": "TDS", "duration_days": 5}]}
    r = client.post("/patients/p1/prescriptions", json=body, headers=rao)  # Sunita: penicillin allergy on record
    assert r.status_code == 422 and r.json()["detail"]["warnings"][0]["kind"] == "allergy"
    assert client.post("/patients/p1/prescriptions", json={**body, "override_reason": "  "}, headers=rao).status_code == 422
    r = client.post("/patients/p1/prescriptions", json={**body, "override_reason": "Tolerated amoxicillin in 2024"}, headers=rao)
    assert r.status_code == 200
    rec = client.get(f"/consult-records/{r.json()['consult_record_id']}", headers=rao).json()
    assert rec["type"] == "prescription" and rec["warnings_shown"][0]["kind"] == "allergy"
    assert rec["overrides"][0]["reason"] == "Tolerated amoxicillin in 2024"
    assert rec["decision"]["items"][0]["medicine"] == "Amoxicillin"
    # reminders were created for the new prescription (TDS = 3 a day)
    with get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM reminders WHERE prescription_item_id = ?",
                         (item_id("p1", "Amoxicillin"),)).fetchone()[0]
    assert n == 3


def test_prescribing_needs_the_care_team_and_the_scope(client):
    body = {"items": [{"medicine": "Metformin", "dose": "500mg", "frequency": "BD", "duration_days": 30}]}
    assert client.post("/patients/p5/prescriptions", json=body, headers=login(client, "drrao")).status_code == 403
    out_of_scope = {"items": [{"medicine": "Nitrofurantoin", "dose": "100mg", "frequency": "BD", "duration_days": 5}]}
    assert client.post("/patients/p7/prescriptions", json=out_of_scope, headers=login(client, "drrao")).status_code == 403
    assert client.post("/patients/p7/prescriptions", json=body, headers=login(client, "meena")).status_code == 403


def test_consult_records_cannot_be_changed_through_the_api(client):
    rao = login(client, "drrao")
    rid = records(client, "p7", "drrao")[0]["id"]
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(f"/consult-records/{rid}", headers=rao).status_code == 405


def test_verify_detects_a_manual_database_edit(client):
    rao = login(client, "drrao")
    rid = records(client, "p7", "drrao")[0]["id"]
    assert client.get(f"/consult-records/{rid}/verify", headers=rao).json()["valid"] is True
    with get_conn() as conn:
        row = conn.execute("SELECT decision_json FROM consult_records WHERE id = ?", (rid,)).fetchone()
        tampered = row["decision_json"].replace('"approve"', '"decline"')
        conn.execute("UPDATE consult_records SET decision_json = ? WHERE id = ?", (tampered, rid))
    assert client.get(f"/consult-records/{rid}/verify", headers=rao).json()["valid"] is False
    with get_conn() as conn:
        conn.execute("UPDATE consult_records SET decision_json = ? WHERE id = ?", (row["decision_json"], rid))
    assert client.get(f"/consult-records/{rid}/verify", headers=rao).json()["valid"] is True


def test_pdf_download_and_who_may_read(client):
    rid = records(client, "p7", "drrao")[0]["id"]
    r = client.get(f"/consult-records/{rid}/pdf", headers=login(client, "drrao"))
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert client.get(f"/consult-records/{rid}", headers=login(client, "meena")).status_code == 200
    assert client.get(f"/consult-records/{rid}", headers=login(client, "drkotian")).status_code == 403
    assert client.get(f"/consult-records/{rid}", headers=login(client, "sunita")).status_code == 403
    assert records(client, "p1", "drkotian") == []  # a doctor lists only the records they made


def test_correction_is_a_new_record_and_the_original_is_kept(client):
    rao = login(client, "drrao")
    original = records(client, "p7", "drrao")[0]
    r = client.post(f"/consult-records/{original['id']}/corrections",
                    json={"note": "Approved for 30 days, not 60."}, headers=rao)
    assert r.status_code == 200
    new = client.get(f"/consult-records/{r.json()['id']}", headers=rao).json()
    assert new["corrects_record_id"] == original["id"] and new["decision"]["note"] == "Approved for 30 days, not 60."
    assert client.get(f"/consult-records/{original['id']}", headers=rao).json()["decision"] == original["decision"]
    assert client.get(f"/consult-records/{original['id']}/verify", headers=rao).json()["valid"] is True
    assert client.post(f"/consult-records/{original['id']}/corrections", json={"note": "Not mine"},
                       headers=login(client, "meena")).status_code == 403
