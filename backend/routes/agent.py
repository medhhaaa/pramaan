"""Document agent routes. (Core backend, AGENTIC_PLAN points 1-11)

GET /documents/{id}/agent-steps -> {"document_id", "filename", "steps": [{"step", "status", "detail", "ms", "created_at"}]}
    "What the agent did" with this document, in order (status: ok | warn | blocked | retry).
"""
from fastapi import APIRouter, Depends, HTTPException

from backend.agent.steps import steps_for
from backend.auth import get_current_user, require_patient_access
from backend.db import get_conn, log_action

router = APIRouter()


@router.get("/documents/{document_id}/agent-steps")
def agent_steps(document_id: str, user=Depends(get_current_user)):
    with get_conn() as conn:
        doc = conn.execute("SELECT id, patient_id, filename FROM documents WHERE id = ?", (document_id,)).fetchone()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    require_patient_access(user, doc["patient_id"])
    log_action(user, "view_agent_steps", doc["patient_id"], {"document_id": document_id})
    return {"document_id": document_id, "filename": doc["filename"], "steps": steps_for(document_id)}
