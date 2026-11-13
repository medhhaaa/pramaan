"""The assistants (backend/agent/, POST /patients/{id}/assistant) on Sunita (p1 sample facts).

call_llm is replaced by FakeLLM: scripted replies, no AI tokens. FakeLLM keeps the real
call_llm's privacy contract (every receipt's redacted text is in the prompt, nothing left for the
last-net scan), so these tests also prove every prompt went through the privacy layer.
"""
import gc
import json
import re

import pytest
from fastapi.testclient import TestClient

from backend import seed
from backend.agent.chat import MAX_STEPS
from backend.agent.context import agent_context
from backend.agent.tools import TOOLS
from backend.db import get_conn
from backend.routes.ask import NOT_DOCUMENTED
from pipeline import llm, privacy_layer


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


class FakeLLM:
    """Scripted replies. A reply is a dict (sent as JSON), a string, or fn(prompt) -> dict."""

    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    def __call__(self, prompt, receipts=None):
        receipts = receipts if isinstance(receipts, (list, tuple)) else [receipts] if receipts else []
        assert receipts and all(isinstance(r, privacy_layer.Redaction) and r.text in prompt for r in receipts), \
            "prompt did not go through the privacy layer"
        assert not privacy_layer.quick_scan(prompt), "personal details left in the prompt"
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        reply = reply(prompt) if callable(reply) else reply
        return reply if isinstance(reply, str) else json.dumps(reply)


@pytest.fixture
def fake(monkeypatch):
    def make(*replies):
        f = FakeLLM(replies)
        monkeypatch.setattr(llm, "call_llm", f)
        return f
    return make


def ask(client, headers, message, history=None, patient="p1"):
    return client.post(f"/patients/{patient}/assistant", json={"message": message, "history": history or []},
                       headers=headers)


def ids_in(prompt):
    return set(re.findall(r"p1_d\d+_f\d+", prompt))


# ---------- the loop ----------

def test_the_tool_the_ai_picks_is_run_and_the_answer_is_cited(client, sunita, doctor, fake):
    share(client, sunita, doctor)
    f = fake({"tool": "check_medicine", "args": {"drug": "Augmentin"}},
             {"answer": "A penicillin allergy (rash) is documented.", "fact_ids": ["p1_d3_f004", "p1_made_up"]})
    r = ask(client, doctor, "Can I give Augmentin?")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["tools_used"] == [{"tool": "check_medicine", "args": {"drug": "Augmentin"}}]
    assert out["fact_ids"] == ["p1_d3_f004"]  # the made-up id is dropped
    assert out["citations"][0]["name"] == "Penicillin"
    for name in ("brief", "flags", "disease_search", "check_medicine"):
        assert f"- {name}(" in f.prompts[0]
    assert "Penicillin" in f.prompts[1] and "p1_d3_f004" in f.prompts[1]  # the tool result went to the AI
    assert len(f.prompts) == 2


def test_each_doctor_tool_returns_only_real_fact_ids(client, sunita, doctor):
    share(client, sunita, doctor)
    from backend.auth import current_request

    current_request.set(("GET", "/patients/p1/brief"))
    ctx = agent_context({**_user("doctor"), "role": "doctor"}, "p1")
    with get_conn() as conn:
        real = {r["fact_id"] for r in conn.execute("SELECT fact_id FROM facts WHERE patient_id = 'p1'")}
    for name, args in [("brief", {}), ("flags", {}), ("flags", {"kind": "contradiction"}),
                       ("disease_search", {"disease": "sugar"}), ("check_medicine", {"drug": "Amoxicillin"})]:
        result = TOOLS["doctor"][name].run(ctx, args)
        assert result["fact_ids"], name
        assert set(result["fact_ids"]) <= real | {i for i in result["fact_ids"] if "gap" in i}, name
    assert "p1_d3_f004" in TOOLS["doctor"]["flags"].run(ctx, {"kind": "contradiction"})["fact_ids"]
    missing = TOOLS["doctor"]["check_medicine"].run(ctx, {})
    assert "missing" in missing["data"]["error"] and missing["fact_ids"] == []


def _user(username):
    with get_conn() as conn:
        row = conn.execute("SELECT id, username, role FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row)


def test_no_citation_means_not_mentioned(client, sunita, doctor, fake):
    share(client, sunita, doctor)
    fake({"tool": "brief", "args": {}}, {"answer": "She has diabetes.", "fact_ids": []})
    assert ask(client, doctor, "Does she have diabetes?").json()["answer"] == NOT_DOCUMENTED
    # a real fact_id the AI never got from a tool is not a citation either
    fake({"answer": "She takes Metformin.", "fact_ids": ["p1_d1_f003"]})
    out = ask(client, doctor, "Metformin?").json()
    assert out["answer"] == NOT_DOCUMENTED and out["fact_ids"] == [] and out["tools_used"] == []
    fake(NOT_DOCUMENTED)  # the bare sentence instead of JSON
    assert ask(client, doctor, "Any fractures?").json()["answer"] == NOT_DOCUMENTED


def test_out_of_scope_facts_never_reach_the_prompt_or_the_answer(client, sunita, doctor, fake):
    share(client, sunita, doctor, ["diabetes"])
    f = fake({"tool": "brief", "args": {}}, {"tool": "flags", "args": {}},
             {"tool": "disease_search", "args": {"disease": "high blood pressure"}},
             {"answer": "Metformin is listed; Atenolol too.", "fact_ids": ["p1_d4_f001", "p1_d1_f004"]})
    out = ask(client, doctor, "What is she taking?").json()
    everything = "\n".join(f.prompts)
    for secret in ("Atenolol", "Amlodipine", "Myocardial", "chest pain"):
        assert secret not in everything, secret
    assert not ids_in(everything) & {"p1_d1_f004", "p1_d3_f006", "p1_d4_f002", "p1_d4_f003", "p1_d3_f003"}
    assert "Metformin" in everything
    assert out["fact_ids"] == ["p1_d4_f001"]  # the out-of-scope id is dropped
    assert all(c["name"] != "Atenolol" for c in out["citations"])
    assert out["hidden"] and out["hidden"]["medicines"] >= 2 and "not shared" in f.prompts[0]
    share(client, sunita, doctor, "all")


def test_the_patient_name_never_reaches_the_ai(client, sunita, fake):
    f = fake({"answer": "x", "fact_ids": []})
    ask(client, sunita, "Does Sunita Rao take Metformin? Call me on 98450 12345")
    assert "Sunita" not in f.prompts[0] and "98450" not in f.prompts[0]


def test_another_patients_id_is_refused(client, sunita, doctor, fake):
    share(client, sunita, doctor)
    f = fake()
    assert ask(client, doctor, "Brief please", patient="p2").status_code == 403
    assert ask(client, sunita, "My records", patient="p2").status_code == 403
    assert f.prompts == []  # refused before any AI call


def test_at_most_three_tool_steps(client, sunita, doctor, fake):
    share(client, sunita, doctor)
    f = fake(*[{"tool": "brief", "args": {}}] * (MAX_STEPS + 1))
    out = ask(client, doctor, "Tell me everything").json()
    assert len(out["tools_used"]) == MAX_STEPS and len(f.prompts) == MAX_STEPS + 1
    assert "used all tool steps" in f.prompts[-1] and out["answer"] == NOT_DOCUMENTED


def test_unknown_tool_is_not_run(client, sunita, doctor, fake):
    share(client, sunita, doctor)
    f = fake({"tool": "delete_everything", "args": {}}, {"answer": "Done", "fact_ids": []})
    out = ask(client, doctor, "Delete it").json()
    assert out["tools_used"] == [] and "unknown tool" in f.prompts[1]


def test_bad_json_twice_gives_502(client, sunita, doctor, fake):
    share(client, sunita, doctor)
    fake("not json", "still not json")
    assert ask(client, doctor, "Brief").status_code == 502


def test_shared_doctor_may_ask_and_the_audit_row_has_no_content(client, sunita, doctor, fake):
    share(client, sunita, doctor)
    fake({"tool": "disease_search", "args": {"disease": "diabetes"}},
         {"answer": "HbA1c 8.1 % on 2023-01-16.", "fact_ids": ["p1_d5_f001"]})
    assert ask(client, doctor, "Latest HbA1c for her sugar?").status_code == 200
    with get_conn() as conn:
        row = conn.execute("SELECT detail FROM audit_log WHERE action = 'assistant' ORDER BY id DESC").fetchone()
    detail = json.loads(row["detail"])
    assert detail["tools"] == ["disease_search"] and detail["cited"] == 1
    assert "HbA1c" not in row["detail"] and "sugar" not in row["detail"]
