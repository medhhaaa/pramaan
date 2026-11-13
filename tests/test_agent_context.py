"""backend/agent/context.py: an agent sees only what the logged-in user may see (point 12)."""
import gc

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import seed
from backend.agent.context import agent_context


@pytest.fixture(scope="module")
def client():
    gc.collect()
    seed.seed(with_sample_facts=True)  # p1's sample facts
    from backend.main import app
    return TestClient(app)


def login(client, username, password):
    r = client.post("/login", json={"username": username, "password": password}).json()
    return r["token"], r


def user_of(client, username, password):
    from backend.db import get_conn
    _, r = login(client, username, password)
    with get_conn() as conn:
        row = conn.execute("SELECT id, username, role FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row)


def test_patient_sees_own_record_only(client):
    sunita = user_of(client, "sunita", "sunita123")
    ctx = agent_context(sunita, "p1")
    assert ctx.role == "patient" and ctx.access["kind"] == "own" and not ctx.read_only
    assert ctx.identity["name"] == "Sunita Rao"
    assert len(ctx.facts()) > 0
    with pytest.raises(HTTPException) as err:
        agent_context(sunita, "p2")
    assert err.value.status_code == 403


def test_doctor_without_share_gets_nothing(client):
    guest = user_of(client, "guestdoctor", "guest123")
    with pytest.raises(HTTPException):
        agent_context(guest, "p1")


def test_partial_share_limits_what_the_agent_sees(client):
    token, _ = login(client, "sunita", "sunita123")
    guest_token, _ = login(client, "guestdoctor", "guest123")
    share = client.post("/patients/p1/share", json={"minutes": 5, "scope": ["diabetes"]},
                        headers={"Authorization": f"Bearer {token}"}).json()
    assert client.post("/share/open", json={"code": share["code"]},
                       headers={"Authorization": f"Bearer {guest_token}"}).status_code == 200
    guest = user_of(client, "guestdoctor", "guest123")
    ctx = agent_context(guest, "p1")
    assert ctx.read_only
    everything = agent_context(user_of(client, "sunita", "sunita123"), "p1").facts()
    shared = ctx.facts()
    assert 0 < len(shared) < len(everything)  # diabetes-related facts (and allergies) only
    assert not any("atenolol" in (f["name"] or "").lower() for f in shared)  # blood pressure medicine: hidden
