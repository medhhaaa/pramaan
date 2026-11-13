"""Document agent routes. (Core backend, AGENTIC_PLAN points 1-11)

GET /documents/{id}/agent-steps -> {"document_id", "filename", "steps": [{"step", "status", "detail", "ms", "created_at"}]}
    "What the agent did" with this document, in order (status: ok | warn | blocked | retry).
GET /patients/{id}/agent-steps -> the same, for steps not tied to one document (remind, escalate)
POST /patients/{id}/agent/run-reminders?hours=48 -> {"reminded": [question ids], "escalated": [...]}
    Runs the reminder / escalation check for this patient now, or as if `hours` had passed (demo).
    It also runs by itself every 15 minutes (backend/agent/reminders.py).
"""
from datetime import datetime, timedelta, timezone

from fastapi import Query
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


@router.get("/patients/{patient_id}/agent-steps")
def patient_agent_steps(patient_id: str, user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT step, status, detail, ms, created_at FROM agent_steps
               WHERE patient_id = ? AND document_id IS NULL ORDER BY id""", (patient_id,)).fetchall()
    log_action(user, "view_agent_steps", patient_id, {"document_id": None})
    return {"patient_id": patient_id, "steps": [dict(r) for r in rows]}


@router.post("/patients/{patient_id}/agent/run-reminders")
def run_patient_reminders(patient_id: str, hours: float = Query(0, ge=0, le=24 * 30),
                          user=Depends(get_current_user)):
    from backend.agent.reminders import run_reminders

    require_patient_access(user, patient_id)
    result = run_reminders(datetime.now(timezone.utc) + timedelta(hours=hours), patient_id)
    log_action(user, "run_reminders", patient_id, {"hours": hours, **result})
    return result
