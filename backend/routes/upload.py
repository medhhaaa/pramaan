"""POST /patients/{id}/upload (multipart form, field "file", optional "doc_type")
-> {"document_id", "facts_added", "held_back", "reasons"}. (Core backend)

Accepts a PDF (digital or scanned) or a photo of a document (JPG, PNG, WEBP). Everything
is turned into a searchable PDF first (pipeline.ocr.prepare_document), so storage, the
PDF viewer and click-to-proof highlighting work the same for scans and photos.

All the steps (encrypt, pipeline, wrong-patient check, save, recompute) are in
backend/ingest.py, shared with the demo loader.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.auth import get_current_user, require_patient_access
from backend.db import log_action
from backend.ingest import ingest_document
from pipeline.ocr import prepare_document

router = APIRouter()
MAX_UPLOAD_MB = 20


@router.post("/patients/{patient_id}/upload")
async def upload(patient_id: str, file: UploadFile = File(...), doc_type: str = Form(""),
                 user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File is larger than {MAX_UPLOAD_MB} MB")
    try:
        data = prepare_document(data)  # PDF, scanned PDF or photo -> searchable PDF
    except ValueError as e:  # not a PDF or image, or a damaged PDF
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = ingest_document(patient_id, file.filename, data, doc_type or None)
    except NotImplementedError:
        raise HTTPException(status_code=503, detail="The extraction pipeline is not built yet")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not process the document: {e}")

    log_action(user, "upload_document", patient_id, {"filename": file.filename, **result})
    return {key: result[key] for key in ("document_id", "facts_added", "held_back", "reasons")}
