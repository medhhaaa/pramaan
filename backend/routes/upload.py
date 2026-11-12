"""POST /patients/{id}/upload (multipart form, field "file", optional "doc_type")
-> {"document_id", "facts_added", "held_back", "reasons"}. (Core backend)

All the steps (encrypt, pipeline, wrong-patient check, save, recompute) are in
backend/ingest.py, shared with the demo loader.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.auth import get_current_user, require_patient_access
from backend.db import log_action
from backend.ingest import ingest_document

router = APIRouter()


@router.post("/patients/{patient_id}/upload")
async def upload(patient_id: str, file: UploadFile = File(...), doc_type: str = Form(""),
                 user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    data = await file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Only PDF files can be uploaded")

    try:
        result = ingest_document(patient_id, file.filename, data, doc_type or None)
    except NotImplementedError:
        raise HTTPException(status_code=503, detail="The extraction pipeline is not built yet")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not process the document: {e}")

    log_action(user, "upload_document", patient_id, {"filename": file.filename, **result})
    return {key: result[key] for key in ("document_id", "facts_added", "held_back", "reasons")}
