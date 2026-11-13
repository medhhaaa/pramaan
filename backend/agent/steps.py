"""'What the agent did': one row per step for each document. (Core backend, AGENTIC_PLAN point 1-6)

record(conn, patient_id, document_id, step, status, detail, ms=None)
steps_for(document_id) -> [{"step", "status", "detail", "ms", "created_at"}] in order

Steps written during an upload (pipeline/process.py trace + backend/ingest.py):
    read      text lines, handwriting pages, pages kept for a person
    protect   personal details replaced; or "blocked" (never sent)
    extract   facts the AI returned
    check     quotes found / not found in the document
    retry     second attempt for facts whose quote failed (feature 3)
    classify  document type and the line that proves it
    patient   wrong-patient check (held back or not)
    save      facts saved
    merge     flags raised on this document after merging with the patient's other records
    questions questions created, and who they go to (feature 4)
"""
from backend.db import get_conn


def record(conn, patient_id, document_id, step, status, detail, ms=None):
    conn.execute(
        "INSERT INTO agent_steps (patient_id, document_id, step, status, detail, ms) VALUES (?, ?, ?, ?, ?, ?)",
        (patient_id, document_id, step, status, detail, ms),
    )


def record_trace(conn, patient_id, document_id, trace):
    for s in trace or []:
        record(conn, patient_id, document_id, s["step"], s.get("status", "ok"), s.get("detail"), s.get("ms"))


def steps_for(document_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT step, status, detail, ms, created_at FROM agent_steps WHERE document_id = ? ORDER BY id",
            (document_id,),
        ).fetchall()
    return [dict(r) for r in rows]
