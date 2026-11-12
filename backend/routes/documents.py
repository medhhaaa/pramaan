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
from backend.db import get_conn, log_action
from pipeline.read_pdf import read_pdf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

router = APIRouter()


@router.get("/documents/{document_id}")
def get_document(document_id: str, user=Depends(get_current_user)):
    with get_conn() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    require_patient_access(user, doc["patient_id"])

    path = os.path.join(ROOT, doc["file_path"])
    pdf_base64, lines = None, []
    if os.path.exists(path):
        with open(path, "rb") as f:
            pdf_base64 = base64.b64encode(f.read()).decode()
        # covered is filled in later from pipeline.coverage (P2)
        lines = [{**line, "covered": False} for line in read_pdf(path)]

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
