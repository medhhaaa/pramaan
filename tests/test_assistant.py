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


# ---------- patient assistant, confirm flow (AGENTIC_PLAN C, E) ----------

def patient_ctx():
    from backend.auth import current_request

    current_request.set(("GET", "/patients/p1/timeline"))
    return agent_context(_user("sunita"), "p1")


def make_stay(client, sunita):
    r = client.post("/patients/p1/hospital-stays", json={"admitted_on": "2022-08-03", "discharged_on": "2022-08-05"},
                    headers=sunita)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def pack_rows(stay_id):
    with get_conn() as conn:
        return [r["document_id"] for r in conn.execute("SELECT document_id FROM claim_pack_items WHERE stay_id = ?",
                                                       (stay_id,))]


def test_patient_tools(client, sunita, doctor):
    share(client, sunita, doctor)
    ctx = patient_ctx()
    tools = TOOLS["patient"]
    meds = tools["my_medicines"].run(ctx, {})
    assert {m["name"] for m in meds["data"]} >= {"Metformin", "Atenolol"} and meds["fact_ids"]
    sugar = tools["explain_records"].run(ctx, {"topic": "sugar"})
    assert "p1_d1_f002" in sugar["fact_ids"] and "p1_d2_f001" in sugar["fact_ids"]  # T2DM, HbA1c
    assert "p1_d1_f004" not in sugar["fact_ids"]  # Atenolol is not about sugar
    who = tools["who_can_see"].run(ctx, {})
    assert who["data"]["qr_shares"] and who["source_ids"][0].startswith("share_")
    assert isinstance(tools["things_to_check"].run(ctx, {})["data"], (list, dict))
    assert "save_to_claim_pack" not in TOOLS["doctor"]  # a doctor never gets write tools


def test_a_write_tool_only_acts_after_confirm(client, sunita, fake):
    stay = make_stay(client, sunita)
    fake({"tool": "claim_checklist", "args": {}},
         {"tool": "save_to_claim_pack", "args": {"stay": f"stay_{stay}", "document_ids": ["p1_d3"]}},
         {"answer": "Shall I add your discharge summary to the claim pack?", "fact_ids": []})
    out = ask(client, sunita, "Save my discharge summary for the August hospital stay").json()
    action = out["pending_action"]
    assert action and action["action"] == "save_to_claim_pack" and "Add 1 document" in action["summary"]
    assert [t["tool"] for t in out["tools_used"]] == ["claim_checklist", "save_to_claim_pack"]
    assert out["answer"].startswith("Shall I add")
    assert pack_rows(stay) == []  # nothing saved yet

    r = client.post("/patients/p1/assistant/confirm", json={"action_id": action["action_id"]}, headers=sunita)
    assert r.status_code == 200, r.text
    assert r.json()["result"]["added"] == ["p1_d3"] and pack_rows(stay) == ["p1_d3"]
    again = client.post("/patients/p1/assistant/confirm", json={"action_id": action["action_id"]}, headers=sunita)
    assert again.status_code == 409


def test_cancel_saves_nothing(client, sunita, fake):
    stay = make_stay(client, sunita)
    fake({"tool": "save_to_claim_pack", "args": {"stay": f"stay_{stay}", "document_ids": ["p1_d2"]}},
         {"answer": "Add your lab report?", "fact_ids": []})
    action = ask(client, sunita, "Add my lab report to the pack").json()["pending_action"]
    r = client.post("/patients/p1/assistant/cancel", json={"action_id": action["action_id"]}, headers=sunita)
    assert r.json()["status"] == "cancelled" and pack_rows(stay) == []
    assert client.post("/patients/p1/assistant/confirm", json={"action_id": action["action_id"]},
                       headers=sunita).status_code == 409


def test_a_shared_doctor_cannot_confirm_writes(client, sunita, doctor, fake):
    share(client, sunita, doctor)
    stay = make_stay(client, sunita)
    fake({"tool": "save_to_claim_pack", "args": {"stay": f"stay_{stay}", "document_ids": ["p1_d1"]}},
         {"answer": "Add it?", "fact_ids": []})
    action = ask(client, sunita, "Add my prescription").json()["pending_action"]
    r = client.post("/patients/p1/assistant/confirm", json={"action_id": action["action_id"]}, headers=doctor)
    assert r.status_code == 403 and pack_rows(stay) == []
    # and the doctor's assistant has no write tool to call at all
    f = fake({"tool": "save_to_claim_pack", "args": {"stay": f"stay_{stay}", "document_ids": ["p1_d1"]}},
             {"answer": "ok", "fact_ids": []})
    out = ask(client, doctor, "Add her prescription to the claim pack").json()
    assert out["pending_action"] is None and out["tools_used"] == [] and "unknown tool" in f.prompts[1]


def test_confirm_checks_again(client, sunita, fake):
    stay = make_stay(client, sunita)
    fake({"tool": "save_to_claim_pack", "args": {"stay": f"stay_{stay}", "document_ids": ["p1_d4"]}},
         {"answer": "Add it?", "fact_ids": []})
    action = ask(client, sunita, "Add my January prescription").json()["pending_action"]
    with get_conn() as conn:
        conn.execute("UPDATE documents SET held_back = 1 WHERE id = 'p1_d4'")  # held back meanwhile
    try:
        r = client.post("/patients/p1/assistant/confirm", json={"action_id": action["action_id"]}, headers=sunita)
        assert r.status_code == 422 and pack_rows(stay) == []
    finally:
        with get_conn() as conn:
            conn.execute("UPDATE documents SET held_back = 0 WHERE id = 'p1_d4'")


def test_another_patients_document_is_never_proposed(client, sunita, fake):
    stay = make_stay(client, sunita)
    f = fake({"tool": "save_to_claim_pack", "args": {"stay": f"stay_{stay}", "document_ids": ["p2_d1"]}},
             {"answer": "Sorry", "fact_ids": []})
    out = ask(client, sunita, "Add p2_d1").json()
    assert out["pending_action"] is None and "not this patient" in f.prompts[1]


def test_claim_answers_cite_the_stay_and_documents(client, sunita, fake):
    stay = make_stay(client, sunita)
    fake({"tool": "claim_checklist", "args": {"stay": f"stay_{stay}"}},
         {"answer": "Your discharge summary is saved; the final bill is not saved yet.",
          "fact_ids": [f"stay_{stay}", "p1_d3", "stay_99999"]})
    out = ask(client, sunita, "What is missing for my claim?").json()
    assert out["answer"].startswith("Your discharge summary")
    assert out["sources"] == [f"stay_{stay}", "p1_d3"]  # stay_99999 was never in a result
    assert [d["id"] for d in out["documents"]] == ["p1_d3"]


def set_language(username, lang):
    with get_conn() as conn:
        conn.execute("UPDATE users SET language = ? WHERE username = ?", (lang, username))


def test_answers_in_hindi_and_kannada(client, sunita, fake):
    from backend.agent.chat import NOT_DOCUMENTED_HI
    from backend.routes.ask import NOT_DOCUMENTED_KN

    try:
        for lang, rule, sentence in [("hi", "Devanagari", NOT_DOCUMENTED_HI), ("kn", "Kannada script", NOT_DOCUMENTED_KN)]:
            set_language("sunita", lang)
            f = fake({"answer": "x", "fact_ids": []})
            out = ask(client, sunita, "Any allergies?").json()
            assert rule in f.prompts[0] and out["answer"] == sentence, lang
        set_language("sunita", "hi")
        fake({"tool": "my_medicines", "args": {}},
             {"answer": "रिकॉर्ड में Metformin 1000mg BD लिखा है।", "fact_ids": ["p1_d4_f001"]})
        out = ask(client, sunita, "मेरी दवाएँ?").json()
        assert "Metformin 1000mg" in out["answer"] and out["fact_ids"] == ["p1_d4_f001"]
    finally:
        set_language("sunita", None)


def test_delete_my_data_removes_assistant_rows(client, sunita):
    """Last test in this file: deletes p1."""
    with get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM assistant_actions WHERE patient_id = 'p1'").fetchone()[0]
    assert client.delete("/patients/p1", headers=sunita).status_code == 200
    with get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM assistant_actions WHERE patient_id = 'p1'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM claim_pack_items").fetchone()[0] == 0
