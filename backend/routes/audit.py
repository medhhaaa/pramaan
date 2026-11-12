"""GET /patients/{patient_id}/audit -> who did what with this patient's data. (Medha)

Response: [{"id", "username", "role", "action", "detail", "created_at"}], newest first.
Both the doctor and the patient can read it (if they have access to the patient).
"""
from fastapi import APIRouter, Depends

from backend.auth import get_current_user, require_patient_access
from backend.db import get_conn
from backend.routes.audit_helper import log_action

router = APIRouter()


@router.get("/patients/{patient_id}/audit")
def audit_route(patient_id: str, user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    log_action(user, "view_audit", patient_id, "")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT a.id, u.username, u.role, a.action, a.detail, a.created_at
               FROM audit_log a LEFT JOIN users u ON u.id = a.user_id
               WHERE a.patient_id = ?
               ORDER BY a.id DESC""",
            (patient_id,),
        ).fetchall()
    return [dict(r) for r in rows]
