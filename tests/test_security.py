"""Security checks the scorecard runs live (backend/routes/security.py).

Each test is one promise from the privacy story: a patient sees only their own records, a
login is needed and can't be forged, shared access is read-only and ends.
"""
import gc
import sqlite3

import jwt
import pytest
from fastapi.testclient import TestClient

from backend import seed


@pytest.fixture(scope="module")
def client():
    gc.collect()  # Windows: close leftover sqlite connections before seed() deletes the test DB
    seed.seed(with_sample_facts=True)
    from backend.main import app
    return TestClient(app)


def login(client, username, password):
    token = client.post("/login", json={"username": username, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_patient_cannot_see_another_patient(client):
    sunita = login(client, "sunita", "sunita123")
    assert client.get("/patients/p1/timeline", headers=sunita).status_code == 200
    for path in ["/patients/p2/timeline", "/patients/p2/brief", "/patients/p2/audit", "/patients/p2/flags"]:
        assert client.get(path, headers=sunita).status_code == 403, path


def test_no_login_no_data(client):
    for path in ["/patients", "/patients/p1/timeline", "/documents/p1_d1", "/security/scorecard"]:
        assert client.get(path).status_code in (401, 403), path


def test_forged_token_is_refused(client):
    fake = jwt.encode({"sub": "1", "username": "doctor", "role": "doctor"}, "not-our-secret", algorithm="HS256")
    assert client.get("/patients", headers={"Authorization": f"Bearer {fake}"}).status_code == 401


def test_wrong_password_is_refused(client):
    assert client.post("/login", json={"username": "doctor", "password": "guess"}).status_code == 401


def test_shared_access_is_read_only_and_ends(client):
    sunita = login(client, "sunita", "sunita123")
    guest = login(client, "guestdoctor", "guest123")
    share = client.post("/patients/p1/share", json={"minutes": 5}, headers=sunita).json()
    assert client.post("/share/open", json={"code": share["code"]}, headers=guest).status_code == 200
    assert client.get("/patients/p1/timeline", headers=guest).status_code == 200
    # writes that must never work through a share
    assert client.delete("/patients/p1", headers=guest).status_code == 403
    files = {"file": ("x.pdf", b"%PDF-1.4 test", "application/pdf")}
    assert client.post("/patients/p1/upload", files=files, headers=guest).status_code == 403
    # the time runs out: access ends
    from backend.db import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    with conn:
        conn.execute("UPDATE share_links SET expires_at = datetime('now', '-1 second') WHERE id = ?",
                     (share["share_id"],))
    conn.close()  # Windows: an open connection would stop the next test file from reseeding
    assert client.get("/patients/p1/timeline", headers=guest).status_code == 403


def test_ai_view_respects_patient_access(client):
    sunita = login(client, "sunita", "sunita123")
    assert client.get("/documents/p1_d1/ai-view", headers=sunita).status_code in (200, 404)
    ravi = login(client, "ravi", "ravi123")
    assert client.get("/documents/p1_d1/ai-view", headers=ravi).status_code == 403


def test_audit_log_tampering_is_detected(client):
    from backend.db import DB_PATH, verify_audit_chain
    sunita = login(client, "sunita", "sunita123")
    for _ in range(3):  # make sure there are a few entries
        client.get("/patients/p1/timeline", headers=sunita)
    assert verify_audit_chain()["intact"]
    conn = sqlite3.connect(DB_PATH)
    row_id, action = conn.execute("SELECT id, action FROM audit_log ORDER BY id LIMIT 1 OFFSET 1").fetchone()
    with conn:
        conn.execute("UPDATE audit_log SET action = 'login' WHERE id = ?", (row_id,))
    result = verify_audit_chain()
    assert not result["intact"] and result["broken_at"] == row_id
    with conn:  # put it back: the chain is whole again
        conn.execute("UPDATE audit_log SET action = ? WHERE id = ?", (action, row_id))
    conn.close()
    assert verify_audit_chain()["intact"]
