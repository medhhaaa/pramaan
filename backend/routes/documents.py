"""GET /documents/{id} -> document details + the PDF + its lines. (Core backend)

Used for click-to-proof: the frontend shows the PDF and highlights the fact's page/line.
Reply shape (KICKOFF.md):
  {"id", "patient_id", "filename", "doc_type", "document_date", "held_back",
   "pdf_base64", "lines": [{"page", "line", "text", "covered"}]}
pdf_base64 is null and lines is [] if the file is not on disk yet.
"""
import base64
import os

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import get_current_user, require_patient_access
from backend.scope import access_scope, document_in_scope
from backend.db import get_conn, log_action
from backend.storage import abs_path, read_file, temp_copy
from pipeline.read_pdf import read_pdf

router = APIRouter()


@router.get("/documents/{document_id}")
def get_document(document_id: str, user=Depends(get_current_user)):
    with get_conn() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    access = require_patient_access(user, doc["patient_id"])
    scope = access_scope(access)
    if scope != "all":  # a scoped care-team doctor opens only documents with an in-scope fact
        with get_conn() as conn:
            facts = conn.execute("SELECT type, name FROM facts WHERE document_id = ?", (document_id,)).fetchall()
        if not document_in_scope([dict(f) for f in facts], scope):
            raise HTTPException(status_code=403, detail="The patient has not shared this document with you")

    pdf_base64, lines = None, []
    if doc["doc_type"] == "patient_profile":  # no file: its lines are the patient's own answers
        with get_conn() as conn:
            lines = [{"page": r["page"], "line": r["line"], "text": r["quote"], "covered": True}
                     for r in conn.execute("SELECT page, line, quote FROM facts WHERE document_id = ? ORDER BY line",
                                           (document_id,))]
    elif doc["file_path"] and os.path.exists(abs_path(doc["file_path"])):
        pdf_base64 = base64.b64encode(read_file(doc["file_path"])).decode()  # decrypts .enc files
        tmp = temp_copy(doc["file_path"])
        try:
            # covered is filled in later from pipeline.coverage (P2)
            lines = [{**line, "covered": False} for line in read_pdf(tmp)]
        finally:
            os.remove(tmp)

    log_action(user, "view_document", doc["patient_id"], {"document_id": document_id})
    return {
        "id": doc["id"],
        "patient_id": doc["patient_id"],
        "filename": doc["filename"],
        "doc_type": doc["doc_type"],
        "document_date": doc["document_date"],
        "held_back": bool(doc["held_back"]),
        "pdf_base64": pdf_base64,
        "lines": lines,
    }


@router.get("/patients/{patient_id}/documents")
def list_documents(patient_id: str, user=Depends(get_current_user)):
    """The patient's documents for the Records page, newest first:
    [{"id", "filename", "doc_type", "document_date", "held_back", "facts"}]  (facts = how many).
    A scoped doctor (partial share or care-team scope) gets only documents they may open, and
    counts only the facts they may see."""
    from backend.scope import fact_in_scope

    scope = access_scope(require_patient_access(user, patient_id))
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT d.id, d.filename, d.doc_type, d.document_date, d.held_back
               FROM documents d WHERE d.patient_id = ?
               ORDER BY d.document_date DESC, d.id DESC""",
            (patient_id,),
        ).fetchall()
        facts = conn.execute("SELECT document_id, type, name FROM facts WHERE patient_id = ?", (patient_id,)).fetchall()
    by_doc = {}
    for f in facts:
        by_doc.setdefault(f["document_id"], []).append(dict(f))
    out = []
    for r in rows:
        doc_facts = by_doc.get(r["id"], [])
        if not document_in_scope(doc_facts, scope):
            continue
        visible = [f for f in doc_facts if fact_in_scope(f, scope)]
        out.append({**dict(r), "held_back": bool(r["held_back"]), "facts": len(visible)})
    log_action(user, "list_documents", patient_id)
    return out
