"""The doctor and patient assistants. (Ashil, AGENTIC_PLAN point 15)

POST /patients/{id}/assistant   {"message": "...", "history": [{"role": "user"|"assistant", "text"}]}
  -> {"answer", "fact_ids", "citations", "tools_used": [{"tool", "args"}], "pending_action", "hidden"}
     hidden: counts-only summary when the user (a doctor with partial sharing) can't see everything
  422 {"message", "found": [{"kind", "text"}]} when the message still has personal details after
      the privacy layer (show it like the privacy preview); 502 when the AI can't answer.

Who: anyone with access to the patient (agent_context = require_patient_access). The tools are
read-only here, so a shared (QR) doctor may use it: "/assistant" is in auth.SHARED_POSTS.
The audit row has the tools used and how many facts were cited, never the message or the answer.
"""
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.agent.chat import run_assistant
from backend.agent.context import agent_context
from backend.auth import get_current_user
from backend.db import log_action
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
    log_action(user, "assistant", patient_id, {"role": ctx.role, "tools": [t["tool"] for t in out["tools_used"]],
                                              "cited": len(out["fact_ids"])})
    return out
