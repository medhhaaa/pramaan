"""The doctor and patient assistants. (Ashil, AGENTIC_PLAN point 15)

POST /patients/{id}/assistant   {"message": "...", "history": [{"role": "user"|"assistant", "text"}]}
  -> {"answer", "fact_ids", "citations", "sources", "documents", "tools_used": [{"tool", "args"}],
      "pending_action": {"action_id", "action", "summary"} | null, "hidden"}
     hidden: counts-only summary when the user (a doctor with partial sharing) can't see everything
  422 {"message", "found": [{"kind", "text"}]} when the message still has personal details after
      the privacy layer (show it like the privacy preview); 502 when the AI can't answer.
POST /patients/{id}/assistant/confirm  {"action_id"}  -> {"action_id", "status": "done", "result"}
POST /patients/{id}/assistant/cancel   {"action_id"}  -> {"action_id", "status": "cancelled"}
     A write tool (save_to_claim_pack) only PROPOSES: the proposal is stored in assistant_actions
     (status proposed) and runs only when the same user confirms it. Shared (QR) and care-team
     doctors can't confirm: auth.require_patient_access refuses "/confirm" for them.

Who: anyone with access to the patient (agent_context = require_patient_access). The tools are
read-only except proposals, so a shared (QR) doctor may ask: "/assistant" is in auth.SHARED_POSTS.
The audit row has the tools used and how many facts were cited, never the message or the answer.
"""
import json
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.agent.chat import run_assistant
from backend.agent.context import agent_context
from backend.auth import get_current_user
from backend.agent.tools import ACTIONS
from backend.db import get_conn, log_action
from pipeline.privacy_layer import PrivacyBlocked

router = APIRouter()


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=2000)


class AssistantBody(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    history: List[Turn] = Field(default_factory=list, max_length=20)


@router.post("/patients/{patient_id}/assistant")
def assistant_route(patient_id: str, body: AssistantBody, user=Depends(get_current_user)):
    ctx = agent_context(user, patient_id)  # 403 exactly like the record pages
    try:
        out = run_assistant(ctx, body.message, [t.model_dump() for t in body.history])
    except PrivacyBlocked as blocked:
        log_action(user, "assistant_blocked", patient_id, {"kinds": sorted({f.kind for f in blocked.findings})})
        raise HTTPException(status_code=422, detail={
            "message": "Please remove these personal details before sending.",
            "found": [{"kind": f.kind, "text": f.text} for f in blocked.findings]})
    except HTTPException:
        raise
    except Exception as err:  # AI down, bad key, JSON twice in a row
        print(f"/assistant failed: {err!r}")
        log_action(user, "assistant_failed", patient_id, {"error": type(err).__name__})
        raise HTTPException(status_code=502, detail="The assistant could not answer right now. Try again.")
    proposal = out.get("pending_action")
    if proposal:  # stored, NOT done: the user confirms or cancels it
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO assistant_actions (user_id, patient_id, action, args) VALUES (?, ?, ?, ?)",
                (user["id"], patient_id, proposal["action"], json.dumps(proposal["args"])))
        out["pending_action"] = {"action_id": cur.lastrowid, "action": proposal["action"], "summary": proposal["summary"]}
    log_action(user, "assistant", patient_id, {"role": ctx.role, "tools": [t["tool"] for t in out["tools_used"]],
                                              "cited": len(out["fact_ids"]) + len(out.get("sources") or []),
                                              "proposed": out["pending_action"]["action_id"] if proposal else None})
    return out


class ActionBody(BaseModel):
    action_id: int


def _proposed_action(conn, user, patient_id, action_id):
    row = conn.execute("SELECT * FROM assistant_actions WHERE id = ? AND patient_id = ? AND user_id = ?",
                       (action_id, patient_id, user["id"])).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Nothing to confirm")
    if row["status"] != "proposed":
        raise HTTPException(status_code=409, detail=f"Already {row['status']}")
    return row


@router.post("/patients/{patient_id}/assistant/confirm")
def confirm_action(patient_id: str, body: ActionBody, user=Depends(get_current_user)):
    ctx = agent_context(user, patient_id)  # a shared or care-team doctor gets 403 here (not in SHARED_POSTS)
    if ctx.read_only:
        raise HTTPException(status_code=403, detail="Shared access is read-only")
    with get_conn() as conn:
        row = _proposed_action(conn, user, patient_id, body.action_id)
        # mark it first, so a double click can't run it twice
        if conn.execute("UPDATE assistant_actions SET status = 'done' WHERE id = ? AND status = 'proposed'",
                        (row["id"],)).rowcount != 1:
            raise HTTPException(status_code=409, detail="Already done")
    run = ACTIONS.get(row["action"])
    try:
        if run is None:
            raise ValueError(f"unknown action {row['action']}")
        result = run(ctx, json.loads(row["args"]))
    except ValueError as err:  # checked again at confirm time: e.g. a document was deleted meanwhile
        with get_conn() as conn:
            conn.execute("UPDATE assistant_actions SET status = 'cancelled' WHERE id = ?", (row["id"],))
        log_action(user, "assistant_action_failed", patient_id, {"action_id": row["id"], "action": row["action"]})
        raise HTTPException(status_code=422, detail=str(err))
    log_action(user, "assistant_action_done", patient_id, {"action_id": row["id"], "action": row["action"], "result": result})
    return {"action_id": row["id"], "status": "done", "result": result}


@router.post("/patients/{patient_id}/assistant/cancel")
def cancel_action(patient_id: str, body: ActionBody, user=Depends(get_current_user)):
    agent_context(user, patient_id)
    with get_conn() as conn:
        row = _proposed_action(conn, user, patient_id, body.action_id)
        conn.execute("UPDATE assistant_actions SET status = 'cancelled' WHERE id = ?", (row["id"],))
    log_action(user, "assistant_action_cancelled", patient_id, {"action_id": row["id"], "action": row["action"]})
    return {"action_id": row["id"], "status": "cancelled"}
