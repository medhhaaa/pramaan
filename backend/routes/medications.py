"""GET /patients/{patient_id}/medications -> per-medicine history + last fresh evidence (Deeksha)

Shape (KICKOFF.md):
[{"name", "current": bool, "last_fresh_evidence_date", "echo_count",
  "entries": [{"fact_id", "document_id", "date", "dose", "frequency", "action", "echo_of"}]}]

Facts from held-back documents (suspected wrong patient) are left out, like the timeline.
Negated medication facts ("not on insulin") are left out: they are not a dose history.
"""
from fastapi import APIRouter, Depends

from backend.auth import get_current_user, require_patient_access
from backend.scope import scoped
from backend.db import fact_from_row, get_conn, log_action

router = APIRouter()


def entry_sort_key(fact):
    """Oldest first: by when it happened, then by document date, then by fact id."""
    return (fact["event_date"] or "", fact["document_date"] or "", fact["fact_id"])


def medicine_summary(entries):
    """Turn one medicine's facts (sorted oldest first) into the API shape."""
    fresh = [f for f in entries if f["echo_of"] is None]
    return {
        "name": entries[0]["name"],
        "current": entries[-1]["action"] != "stopped",
        "last_fresh_evidence_date": fresh[-1]["event_date"] if fresh else None,
        "echo_count": len(entries) - len(fresh),
        "entries": [
            {
                "fact_id": f["fact_id"],
                "document_id": f["document_id"],
                "date": f["event_date"],
                "dose": f["dose"],
                "frequency": f["frequency"],
                "action": f["action"],
                "echo_of": f["echo_of"],
            }
            for f in entries
        ],
    }


def group_medications(facts):
    """Group medication facts by name (ignoring case) and summarise each medicine."""
    groups = {}
    for fact in sorted(facts, key=entry_sort_key):
        if fact["type"] == "medication" and fact["status"] == "documented":
            groups.setdefault(fact["name"].strip().lower(), []).append(fact)
    return [medicine_summary(groups[key]) for key in sorted(groups)]


@router.get("/patients/{patient_id}/medications")
def medications_route(patient_id: str, user=Depends(get_current_user)):
    access = require_patient_access(user, patient_id)
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT f.* FROM facts f
               JOIN documents d ON d.id = f.document_id
               WHERE f.patient_id = ? AND d.held_back = 0 AND f.type = 'medication'""",
            (patient_id,),
        ).fetchall()
    log_action(user, "view_medications", patient_id)
    return group_medications(scoped([fact_from_row(r) for r in rows], access))  # care-team scope
