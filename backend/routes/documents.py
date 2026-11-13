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
            raise HTTPException(status_code=403, detail="This document is outside your care-team scope")

    pdf_base64, lines = None, []
    if os.path.exists(abs_path(doc["file_path"])):
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
