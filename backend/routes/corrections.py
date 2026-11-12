"""POST /facts/{id}/correct  {"field": "dose", "new_value": "25mg"} -> the updated fact. (Core backend)

The original value is kept in the corrections table (who, role, when).
The evidence itself (quote, page, line, document) can never be corrected.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth import get_current_user, require_patient_access
from backend.db import fact_from_row, get_conn, log_action
from backend.recompute import recompute_patient

# Only these fields can be corrected. Everything else is evidence or an ID.
CORRECTABLE = {"name", "dose", "frequency", "value", "unit", "action", "status", "event_date"}

router = APIRouter()


class CorrectionBody(BaseModel):
    field: str
    new_value: str | None


@router.post("/facts/{fact_id}/correct")
def correct_fact(fact_id: str, body: CorrectionBody, user=Depends(get_current_user)):
    if body.field not in CORRECTABLE:
        raise HTTPException(status_code=400, detail=f"Field '{body.field}' cannot be corrected")

    with get_conn() as conn:
        fact = conn.execute("SELECT * FROM facts WHERE fact_id = ?", (fact_id,)).fetchone()
        if not fact:
            raise HTTPException(status_code=404, detail="Fact not found")
        require_patient_access(user, fact["patient_id"])

        conn.execute(
            """INSERT INTO corrections (fact_id, field, old_value, new_value, corrected_by, role)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (fact_id, body.field, fact[body.field], body.new_value, user["id"], user["role"]),
        )
        # body.field is safe to put in the SQL: it was checked against CORRECTABLE above
        conn.execute(
            f"UPDATE facts SET {body.field} = ?, corrected = 1 WHERE fact_id = ?",
            (body.new_value, fact_id),
        )

    # rerun the checks: a doctor's correction makes the fact doctor_verified
    recompute_patient(fact["patient_id"])
    with get_conn() as conn:
        updated = conn.execute("SELECT * FROM facts WHERE fact_id = ?", (fact_id,)).fetchone()

    log_action(user, "correct_fact", fact["patient_id"],
               {"fact_id": fact_id, "field": body.field, "old": fact[body.field], "new": body.new_value})
    return fact_from_row(updated)
