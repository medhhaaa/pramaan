"""GET /patients -> patients this user can access. (Core backend)"""
from fastapi import APIRouter, Depends

from backend.auth import get_current_user
from backend.db import get_conn

router = APIRouter()


@router.get("/patients")
def list_patients(user=Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT p.* FROM patients p
               JOIN user_patients up ON up.patient_id = p.id
               WHERE up.user_id = ? ORDER BY p.id""",
            (user["id"],),
        ).fetchall()
    return [dict(r) for r in rows]
