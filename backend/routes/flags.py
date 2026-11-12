"""GET /patients/{patient_id}/flags -> flagged facts grouped by flag type (Deeksha)

Shape (KICKOFF.md):
{"contradiction": [fact], "duplicate": [...], "unit_mismatch": [...], "ambiguous_date": [...],
 "wrong_patient": [...], "implausible_value": [...], "gap": [...]}

Includes facts from held-back documents, so a reviewer can see the wrong-patient report.
Gaps are computed on the fly from the facts the patient's timeline trusts (not held back).
"""
from fastapi import APIRouter, Depends

from backend.auth import get_current_user, require_patient_access
from backend.db import fact_from_row, get_conn, log_action
from backend.logic.flags import find_gaps

router = APIRouter()

FLAG_TYPES = [
    "contradiction", "duplicate", "unit_mismatch", "ambiguous_date",
    "wrong_patient", "implausible_value",
]


def group_by_flag(facts):
    """Every flag type gets a list (empty if nothing has that flag). A fact with
    two flags appears in both lists."""
    groups = {flag: [] for flag in FLAG_TYPES}
    for fact in facts:
        for flag in fact["flags"]:
            groups.setdefault(flag, []).append(fact)
    return groups


@router.get("/patients/{patient_id}/flags")
def flags_route(patient_id: str, user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT f.*, d.held_back FROM facts f
               JOIN documents d ON d.id = f.document_id
               WHERE f.patient_id = ?
               ORDER BY f.event_date, f.document_date, f.fact_id""",
            (patient_id,),
        ).fetchall()

    facts, trusted = [], []
    for row in rows:
        held_back = row["held_back"]
        fact = fact_from_row(row)
        fact.pop("held_back")
        facts.append(fact)
        if not held_back:
            trusted.append(fact)

    log_action(user, "view_flags", patient_id)
    groups = group_by_flag(facts)
    groups["gap"] = find_gaps(trusted)
    return groups
