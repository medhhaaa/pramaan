"""Care team consent (backend/auth.py, backend/scope.py, backend/routes/care_team.py) and Dr. Rao's
My Patients dashboard, on a throwaway database with the demo data (backend/demo_care_team.py).
Documents go through the same ingest as an upload, using saved pipeline output (no AI).
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend.db import get_conn
from backend.scope import document_in_scope, fact_in_scope, tags_of
from tests.demo_helpers import load_care_team_demo, login, user_id


@pytest.fixture(scope="module")
def client():
    load_care_team_demo()
    from backend.main import app
    return TestClient(app)


# ---------- scope rules (plain code) ----------

def test_scope_matches_by_condition_tag():
    assert tags_of("medication", "Metformin") == ["diabetes"]
    assert fact_in_scope({"type": "allergy", "name": "Sulfa drugs"}, ["hypertension"])  # always visible
    assert not fact_in_scope({"type": "medication", "name": "Nitrofurantoin"}, ["diabetes"])
    assert fact_in_scope({"type": "lab_test", "name": "HbA1c"}, ["diabetes"])
    demographics_only = [{"type": "demographic", "name": "sex"}]
    assert not document_in_scope(demographics_only, ["diabetes"])
    assert document_in_scope(demographics_only, "all")


# ---------- access ----------

def test_doctor_without_care_team_or_share_gets_403(client):
    rao = login(client, "drrao")
    for path in ["/patients/p5/brief", "/patients/p5/timeline", "/patients/p6/medications"]:
        assert client.get(path, headers=rao).status_code == 403
    assert client.get("/patients/p1/brief", headers=login(client, "doctor")).status_code == 403


def test_care_team_doctor_reads_but_never_uploads_deletes_or_shares(client):
    rao = login(client, "drrao")
    assert client.get("/patients/p4/brief", headers=rao).status_code == 200
    assert client.delete("/patients/p4", headers=rao).status_code == 403
    assert client.post("/patients/p4/share", json={"minutes": 15}, headers=rao).status_code == 403
    r = client.post("/patients/p4/upload", files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")}, headers=rao)
    assert r.status_code == 403
    ids = [p["id"] for p in client.get("/patients", headers=rao).json()]
    assert ids == ["p1", "p2", "p3", "p4", "p8"]


def test_out_of_scope_data_is_hidden(client):
    rao, meena = login(client, "drrao"), login(client, "meena")
    own = {f["name"] for f in client.get("/patients/p8/timeline", headers=meena).json()}
    seen = client.get("/patients/p8/timeline", headers=rao).json()
    names = {f["name"] for f in seen}
    assert {"Nitrofurantoin", "Urinary tract infection"} <= own
    assert not {"Nitrofurantoin", "Urinary tract infection"} & names   # outside "diabetes"
    assert {"Metformin", "Sulfa drugs", "Type 2 diabetes mellitus"} <= names  # allergy always shown
    assert all(fact_in_scope(f, ["diabetes"]) for f in seen)

    meds = {m["name"] for m in client.get("/patients/p8/medications", headers=rao).json()}
    assert "Nitrofurantoin" not in meds and "Metformin" in meds
    brief = client.get("/patients/p8/brief", headers=rao).json()
    assert "Nitrofurantoin" not in json.dumps(brief)
    assert any(a["name"] == "Sulfa drugs" for a in brief["allergies"])


def test_revoked_doctor_gets_403(client):
    sunita, kotian = login(client, "sunita"), login(client, "drkotian")
    assert client.get("/patients/p1/brief", headers=kotian).status_code == 200
    entry = next(e for e in client.get("/patients/p1/care-team", headers=sunita).json()
                 if e["doctor"]["name"] == "Dr. Suresh Kotian")
    assert client.post(f"/patients/p1/care-team/{entry['id']}/revoke", headers=sunita).status_code == 200
    assert client.get("/patients/p1/brief", headers=kotian).status_code == 403
    assert client.get("/patients/p1/timeline", headers=kotian).status_code == 403
    assert client.get("/patients", headers=kotian).json() == []


# ---------- dashboard ----------

def test_dr_rao_dashboard_tags_and_order(client):
    rows = client.get("/doctors/me/patients", headers=login(client, "drrao")).json()
    assert [(r["patient_id"], r["tags"]) for r in rows] == [
        ("p8", ["refill_request"]),
        ("p1", ["new_report"]),
        ("p2", ["missed_doses"]),
        ("p3", ["followup_overdue"]),
        ("p4", ["stable"]),
    ]
    by_id = {r["patient_id"]: r for r in rows}
    assert by_id["p2"]["adherence_14d"] == 57 and by_id["p8"]["adherence_14d"] == 79
    assert by_id["p8"]["conditions"] == ["Type 2 diabetes mellitus"]  # within scope only
    assert by_id["p8"]["scope"] == ["diabetes"] and by_id["p8"]["age"] == 60


def test_opening_the_patient_clears_new_report(client):
    rao = login(client, "drrao")
    assert client.get("/patients/p1/brief", headers=rao).status_code == 200
    rows = {r["patient_id"]: r for r in client.get("/doctors/me/patients", headers=rao).json()}
    assert rows["p1"]["tags"] == ["stable"]


def test_follow_up_date_set_by_the_care_team_doctor_only(client):
    rao = login(client, "drrao")
    assert client.post("/patients/p4/follow-up", json={"date": "2020-01-01"}, headers=rao).status_code == 200
    rows = {r["patient_id"]: r for r in client.get("/doctors/me/patients", headers=rao).json()}
    assert rows["p4"]["tags"] == ["followup_overdue"] and rows["p4"]["followup_on"] == "2020-01-01"
    assert client.post("/patients/p4/follow-up", json={"date": None}, headers=rao).status_code == 200
    assert client.post("/patients/p4/follow-up", json={"date": "2030-01-01"}, headers=login(client, "arjun")).status_code == 403
    assert client.post("/patients/p5/follow-up", json={"date": "2030-01-01"}, headers=rao).status_code == 403


def test_dashboard_is_doctors_only_and_audited(client):
    assert client.get("/doctors/me/patients", headers=login(client, "meena")).status_code == 403
    with get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM audit_log WHERE user_id = ? AND action = 'view_my_patients'",
                         (user_id("drrao"),)).fetchone()[0]
    assert n >= 1


# ---------- the patient's My Care Team ----------

def test_patient_finds_and_adds_a_doctor_with_a_scope(client):
    arjun = login(client, "arjun")
    by_name = client.get("/doctors/search", params={"q": "rao"}, headers=arjun).json()
    by_reg = client.get("/doctors/search", params={"q": "63105"}, headers=arjun).json()
    assert by_name[0]["name"] == "Dr. Rao" and by_reg == by_name[:1]
    guest = next(d for d in client.get("/doctors/search", params={"q": "guest"}, headers=arjun).json())

    assert client.get("/patients/p4/brief", headers=login(client, "guestdoctor")).status_code == 403
    r = client.post("/patients/p4/care-team", json={"doctor_id": guest["id"], "scope": ["asthma"]}, headers=arjun)
    assert r.status_code == 200 and r.json()["scope"] == ["asthma"]
    assert client.get("/patients/p4/brief", headers=login(client, "guestdoctor")).status_code == 200
    # duplicates, bad tags and doctors adding themselves are refused
    assert client.post("/patients/p4/care-team", json={"doctor_id": guest["id"]}, headers=arjun).status_code == 409
    assert client.post("/patients/p4/care-team", json={"doctor_id": guest["id"], "scope": ["knees"]}, headers=arjun).status_code == 422
    assert client.post("/patients/p4/care-team", json={"doctor_id": guest["id"]}, headers=login(client, "drrao")).status_code == 403
    assert client.get("/doctors/search", params={"q": "rao"}, headers=login(client, "drrao")).status_code == 403


def test_auto_review_after_180_days_without_a_consult(client):
    arjun = login(client, "arjun")
    team = {e["doctor"]["name"]: e for e in client.get("/patients/p4/care-team", headers=arjun).json()}
    assert team["Dr. Rao"]["review_due"] is False  # added 80 days ago
    with get_conn() as conn:
        conn.execute("UPDATE care_team SET created_at = '2025-01-01 10:00:00', last_confirmed_at = '2025-01-01 10:00:00'"
                     " WHERE id = ?", (team["Dr. Rao"]["id"],))
    team = {e["doctor"]["name"]: e for e in client.get("/patients/p4/care-team", headers=arjun).json()}
    assert team["Dr. Rao"]["review_due"] is True
    assert client.post(f"/patients/p4/care-team/{team['Dr. Rao']['id']}/keep", headers=arjun).status_code == 200
    team = {e["doctor"]["name"]: e for e in client.get("/patients/p4/care-team", headers=arjun).json()}
    assert team["Dr. Rao"]["review_due"] is False


def test_access_history_shows_doctor_views(client):
    client.get("/patients/p4/timeline", headers=login(client, "drrao"))
    history = client.get("/patients/p4/access-history", headers=login(client, "arjun")).json()
    assert history[0]["doctor_name"] in {"Dr. Rao", "Dr. Guest"}
    assert "Dr. Rao" in {h["doctor_name"] for h in history}
    assert client.get("/patients/p4/access-history", headers=login(client, "drrao")).status_code == 403
