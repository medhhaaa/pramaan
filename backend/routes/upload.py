"""POST /patients/{id}/upload (multipart form, field "file", optional "doc_type")
-> {"document_id", "facts_added", "held_back", "reasons", "dropped", "doc_type",
    "document_date", plus the upload report:
    "read_with"     "text" (digital PDF) or "ocr" (scan or photo)
    "added"         the saved facts (contract format, with their flags)
    "left_out"      facts quote verification refused: type, name, dose..., quote, reason
                    ("quote_not_found" | "dose_not_in_line" | "value_not_in_line" | "unit_not_in_line")
    "not_captured"  medical lines no fact quotes: [{"page", "line", "text"}]}. (Core backend)

Accepts a PDF (digital or scanned) or a photo of a document (JPG, PNG, WEBP). Everything
is turned into a searchable PDF first (pipeline.ocr.prepare_document), so storage, the
PDF viewer and click-to-proof highlighting work the same for scans and photos.

All the steps (encrypt, pipeline, wrong-patient check, save, recompute) are in
backend/ingest.py, shared with the demo loader.
"""
import threading

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from backend.auth import get_current_user, require_patient_access
from backend.db import log_action
from backend.ingest import ingest_document
from pipeline.ocr import prepare_document

router = APIRouter()
MAX_UPLOAD_MB = 20
# OCR and the AI call take ~20 s. They run in a worker thread so the rest of the app
# (timeline, login, other tabs) keeps answering meanwhile. One ingest at a time, so two
# uploads never pick the same new document id.
_ingest_lock = threading.Lock()


def _ingest_one(patient_id, filename, data, doc_type):
    with _ingest_lock:
        return ingest_document(patient_id, filename, data, doc_type)


@router.post("/patients/{patient_id}/upload")
async def upload(patient_id: str, file: UploadFile = File(...), doc_type: str = Form(""),
                 user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File is larger than {MAX_UPLOAD_MB} MB")
    try:
        prepared = await run_in_threadpool(prepare_document, data)  # PDF, scan or photo -> searchable PDF
    except ValueError as e:  # not a PDF or image, or a damaged PDF
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:  # scanned page or photo, but the Tesseract OCR program is not installed
        raise HTTPException(status_code=503, detail="This file has scanned pages, and the OCR program "
                            "(Tesseract) is not installed on this server. Digital PDFs still upload.")
    used_ocr = prepared is not data  # a digital PDF comes back unchanged
    data = prepared

    try:
        result = await run_in_threadpool(_ingest_one, patient_id, file.filename, data, doc_type or None)
    except NotImplementedError:
        raise HTTPException(status_code=503, detail="The extraction pipeline is not built yet")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not process the document: {e}")

    summary = {key: result[key] for key in ("document_id", "facts_added", "held_back", "reasons",
                                            "dropped", "doc_type", "document_date", "needs_reading")}
    log_action(user, "upload_document", patient_id, {"filename": file.filename, **summary})
    return {
        **summary,
        "read_with": "ocr" if used_ocr else "text",
        "added": result["added_facts"],
        "left_out": [_left_out(f) for f in result["dropped_facts"]],
        "not_captured": result["not_captured"],
    }


def _left_out(fact):
    """A fact the AI proposed but quote verification refused, and why (as a code the
    screen can translate): its quote is not in the document, or a dose/value/unit is not
    in the quoted line."""
    reason = fact.get("drop_reason") or ""
    field = reason.split(" ", 1)[0] if "is not in the quoted line" in reason else None
    return {
        "type": fact.get("type"), "name": fact.get("name"), "dose": fact.get("dose"),
        "frequency": fact.get("frequency"), "value": fact.get("value"), "unit": fact.get("unit"),
        "quote": fact.get("quote"),
        "reason": f"{field}_not_in_line" if field else "quote_not_found",
        "reason_text": reason,
    }
