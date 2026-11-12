"""GET /patients/{id}/timeline -> facts sorted by event_date. (Core backend)

Facts from held-back documents (e.g. suspected wrong patient) are left out
until a reviewer releases the document.
"""
from fastapi import APIRouter, Depends

from backend.auth import get_current_user, require_patient_access
from backend.db import fact_from_row, get_conn, log_action

router = APIRouter()


@router.get("/patients/{patient_id}/timeline")
def timeline(patient_id: str, user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT f.* FROM facts f
               JOIN documents d ON d.id = f.document_id
               WHERE f.patient_id = ? AND d.held_back = 0
               ORDER BY f.event_date, f.document_date, f.fact_id""",
            (patient_id,),
        ).fetchall()
    log_action(user, "view_timeline", patient_id)
    return [fact_from_row(r) for r in rows]
