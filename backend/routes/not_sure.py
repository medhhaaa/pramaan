"""'App not sure': facts the agent could not prove even after retrying (AGENTIC_PLAN point 5).

They are never silently thrown away. A person looks at the document and decides.

GET  /patients/{id}/not-sure        -> [{"id", "document_id", "filename", "fact": {...}, "reason",
                                         "attempts", "created_at"}]  open items (scope applied)
POST /not-sure/{item_id}/resolve    {"action": "accept" | "reject"}
     accept -> the fact is added to the record, marked as accepted by this person (corrections
               table keeps who/role/when; a doctor's accept makes it doctor_verified)
     reject -> kept as rejected, never shown again

save_not_sure(conn, patient_id, document_id, dropped_facts)  called by backend/ingest.py
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth import get_current_user, require_patient_access
from backend.db import fact_from_row, get_conn, insert_fact, log_action
from backend.recompute import recompute_patient
from backend.scope import scoped

router = APIRouter()

FACT_KEYS = ("type", "name", "dose", "frequency", "value", "unit", "action", "status", "event_date", "quote")


def save_not_sure(conn, patient_id, document_id, dropped):
    for f in dropped or []:
        fact = {k: f.get(k) for k in FACT_KEYS}
        conn.execute(
            """INSERT INTO not_sure_items (patient_id, document_id, fact, reason, attempts)
               VALUES (?, ?, ?, ?, ?)""",
            (patient_id, document_id, json.dumps(fact, ensure_ascii=False), f.get("drop_reason"),
             json.dumps(["quote check", "re-read (OCR pages)", "stronger model (if set)"])),
        )


@router.get("/patients/{patient_id}/not-sure")
def list_not_sure(patient_id: str, user=Depends(get_current_user)):
    access = require_patient_access(user, patient_id)
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT n.*, d.filename FROM not_sure_items n JOIN documents d ON d.id = n.document_id
               WHERE n.patient_id = ? AND n.status = 'open' ORDER BY n.id""",
            (patient_id,),
        ).fetchall()
    items = []
    for r in rows:
        fact = json.loads(r["fact"])
        if scoped([fact], access):  # a scoped doctor only sees in-scope items
            items.append({"id": r["id"], "document_id": r["document_id"], "filename": r["filename"],
                          "fact": fact, "reason": r["reason"], "attempts": json.loads(r["attempts"] or "[]"),
                          "created_at": r["created_at"]})
    log_action(user, "list_not_sure", patient_id, {"open": len(items)})
    return items


class ResolveBody(BaseModel):
    action: str


@router.post("/not-sure/{item_id}/resolve")
def resolve(item_id: int, body: ResolveBody, user=Depends(get_current_user)):
    if body.action not in ("accept", "reject"):
        raise HTTPException(status_code=422, detail="action must be accept or reject")
    with get_conn() as conn:
        item = conn.execute("SELECT * FROM not_sure_items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        require_patient_access(user, item["patient_id"])
        if item["status"] != "open":
            raise HTTPException(status_code=409, detail="Already resolved")
        fact_id = None
        if body.action == "accept":
            doc = conn.execute("SELECT * FROM documents WHERE id = ?", (item["document_id"],)).fetchone()
            n = conn.execute("SELECT COUNT(*) FROM facts WHERE fact_id LIKE ?", (f"{doc['id']}_u%",)).fetchone()[0]
            fact = json.loads(item["fact"])
            fact_id = f"{doc['id']}_u{n + 1:03d}"  # u = accepted by a person although unproven
            insert_fact(conn, {
                **fact, "fact_id": fact_id, "patient_id": item["patient_id"], "document_id": doc["id"],
                "status": fact.get("status") or "documented", "document_date": doc["document_date"],
                "event_date": fact.get("event_date") or doc["document_date"], "date_raw": None,
                "page": None, "line": None, "quote_verified": False, "echo_of": None, "badge": None,
                "flags": [], "corrected": True, "confidence": None, "unsure": [],
            })
            conn.execute(
                """INSERT INTO corrections (fact_id, field, old_value, new_value, corrected_by, role)
                   VALUES (?, 'accepted_not_sure', NULL, ?, ?, ?)""",
                (fact_id, item["reason"], user["id"], user["role"]),
            )
        conn.execute(
            "UPDATE not_sure_items SET status = ?, resolved_by = ?, resolved_at = datetime('now') WHERE id = ?",
            ("accepted" if body.action == "accept" else "rejected", user["id"], item_id),
        )
    if fact_id:
        recompute_patient(item["patient_id"])
    log_action(user, f"not_sure_{body.action}", item["patient_id"], {"item_id": item_id, "fact_id": fact_id})
    if fact_id:
        with get_conn() as conn:
            return {"status": "accepted", "fact": fact_from_row(
                conn.execute("SELECT * FROM facts WHERE fact_id = ?", (fact_id,)).fetchone())}
    return {"status": "rejected"}
