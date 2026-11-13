"""Handwritten pages a person must read. (Core backend)

A handwritten page with no "Name:"/"Patient:" style label can't be safely blacked out, so it is
never sent to an AI. The document is kept (picture only) with needs_reading = 1, and the
doctor reads it from the image and types the medicines in.

GET  /patients/{id}/needs-reading -> [{"id", "filename", "doc_type", "document_date", "facts_added"}]
POST /documents/{id}/facts  {"type": "medication", "name", "dose", "frequency", "action",
                             "event_date", "value", "unit"}  -> the new fact
     The fact is marked as typed by this person (quote says so, flag "handwriting"), and the
     entry is saved in the corrections table (who, role, when), so a doctor's entry becomes
     doctor_verified like any other doctor correction.
POST /documents/{id}/read   -> {"done": true}   the person finished reading: hide the notice
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth import get_current_user, require_patient_access
from backend.db import fact_from_row, get_conn, insert_fact, log_action
from backend.recompute import recompute_patient

router = APIRouter()

FACT_TYPES = {"medication", "allergy", "condition", "lab_test", "event"}
ACTIONS = {"started", "continued", "changed", "stopped", "mentioned"}


def _document(conn, document_id, user):
    doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    require_patient_access(user, doc["patient_id"])
    return doc


@router.get("/patients/{patient_id}/needs-reading")
def needs_reading(patient_id: str, user=Depends(get_current_user)):
    from backend.scope import access_scope, document_in_scope

    scope = access_scope(require_patient_access(user, patient_id))
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT d.id, d.filename, d.doc_type, d.document_date,
                      (SELECT COUNT(*) FROM facts f WHERE f.document_id = d.id) AS facts_added
               FROM documents d WHERE d.patient_id = ? AND d.needs_reading = 1 AND d.held_back = 0
               ORDER BY d.id""",
            (patient_id,),
        ).fetchall()
        if scope != "all":  # a partial share / care-team scope: only documents this doctor may open
            rows = [r for r in rows if document_in_scope(
                [dict(f) for f in conn.execute("SELECT type, name FROM facts WHERE document_id = ?", (r["id"],))], scope)]
    log_action(user, "list_needs_reading", patient_id)
    return [dict(r) for r in rows]


class NewFact(BaseModel):
    type: str = "medication"
    name: str
    dose: str | None = None
    frequency: str | None = None
    action: str | None = "mentioned"
    event_date: str | None = None
    value: str | None = None
    unit: str | None = None


@router.post("/documents/{document_id}/facts")
def add_fact(document_id: str, body: NewFact, user=Depends(get_current_user)):
    if body.type not in FACT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown type: {body.type}")
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Please type the name")
    with get_conn() as conn:
        doc = _document(conn, document_id, user)
        n = conn.execute("SELECT COUNT(*) FROM facts WHERE fact_id LIKE ?", (f"{document_id}_m%",)).fetchone()[0]
        fact = {
            "fact_id": f"{document_id}_m{n + 1:03d}",  # m = typed in by a person
            "patient_id": doc["patient_id"],
            "document_id": document_id,
            "type": body.type,
            "name": body.name.strip(),
            "dose": body.dose if body.type == "medication" else None,
            "frequency": body.frequency if body.type == "medication" else None,
            "value": body.value,
            "unit": body.unit,
            "action": (body.action if body.action in ACTIONS else "mentioned") if body.type == "medication" else None,
            "status": "documented",
            "event_date": body.event_date or doc["document_date"],
            "document_date": doc["document_date"],
            "date_raw": None,
            "quote": f"Read from the handwritten image by {user['username']} ({user['role']})",
            "page": 1,
            "line": None,
            "quote_verified": False,
            "echo_of": None,
            "badge": None,
            "flags": ["handwriting"],
            "corrected": True,
            "confidence": None,
            "unsure": [],
        }
        insert_fact(conn, fact)
        # who typed it, when, in which role: kept like a correction (the "original" was empty)
        conn.execute(
            """INSERT INTO corrections (fact_id, field, old_value, new_value, corrected_by, role)
               VALUES (?, 'added_from_image', NULL, ?, ?, ?)""",
            (fact["fact_id"], json.dumps(body.model_dump()), user["id"], user["role"]),
        )
    recompute_patient(doc["patient_id"])
    log_action(user, "add_fact_from_image", doc["patient_id"], {"fact_id": fact["fact_id"], "name": fact["name"]})
    with get_conn() as conn:
        return fact_from_row(conn.execute("SELECT * FROM facts WHERE fact_id = ?", (fact["fact_id"],)).fetchone())


@router.post("/documents/{document_id}/read")
def mark_read(document_id: str, user=Depends(get_current_user)):
    with get_conn() as conn:
        doc = _document(conn, document_id, user)
        conn.execute("UPDATE documents SET needs_reading = 0 WHERE id = ?", (document_id,))
    log_action(user, "mark_document_read", doc["patient_id"], {"document_id": document_id})
    return {"done": True}
