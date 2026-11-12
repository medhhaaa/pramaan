"""POST /patients/{id}/upload (multipart form, field "file", optional "doc_type")
-> {"document_id", "facts_added", "held_back"}. (Core backend)

1. check it's a PDF and save it ENCRYPTED under storage/<patient>/
2. run Ashil's pipeline on a temporary decrypted copy (deleted right after)
3. save the document row + verified facts
   wrong-patient check: if its blood group / sex disagree with the patient record, its
   facts are flagged wrong_patient and the document is held back from the timeline
4. rerun the checks on all the patient's facts (recompute_patient)
If the pipeline fails, the stored file is removed and nothing is saved.
"""
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.auth import get_current_user, require_patient_access
from backend.db import get_conn, insert_fact, log_action
from backend.logic.wrong_patient import find_conflicts
from backend.recompute import recompute_patient
from backend.storage import delete_file, save_encrypted, temp_copy
from pipeline import process

router = APIRouter()


def _new_document_id(conn, patient_id):
    n = conn.execute("SELECT COUNT(*) FROM documents WHERE patient_id = ?", (patient_id,)).fetchone()[0] + 1
    while conn.execute("SELECT 1 FROM documents WHERE id = ?", (f"{patient_id}_d{n}",)).fetchone():
        n += 1
    return f"{patient_id}_d{n}"


@router.post("/patients/{patient_id}/upload")
async def upload(patient_id: str, file: UploadFile = File(...), doc_type: str = Form("unknown"),
                 user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    data = await file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Only PDF files can be uploaded")

    with get_conn() as conn:
        document_id = _new_document_id(conn, patient_id)
    rel_path = f"storage/{patient_id}/{document_id}.pdf.enc"
    save_encrypted(data, rel_path)

    tmp = temp_copy(rel_path)
    try:
        facts = process.process_document(tmp, patient_id, document_id)
    except NotImplementedError:
        delete_file(rel_path)
        raise HTTPException(status_code=503, detail="The extraction pipeline is not built yet")
    except Exception as e:
        delete_file(rel_path)
        raise HTTPException(status_code=500, detail=f"Could not process the document: {e}")
    finally:
        os.remove(tmp)

    # document_date comes from the pipeline's facts (all facts carry the same one)
    document_date = next((f["document_date"] for f in facts if f.get("document_date")), None)
    with get_conn() as conn:
        patient = dict(conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone())
    conflicts = find_conflicts(facts, patient)
    if conflicts:
        for fact in facts:
            fact["flags"] = list(fact.get("flags") or []) + ["wrong_patient"]

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
            (document_id, patient_id, file.filename, doc_type, document_date, rel_path, int(bool(conflicts))),
        )
        for fact in facts:
            insert_fact(conn, fact)

    recompute_patient(patient_id)

    log_action(user, "upload_document", patient_id,
               {"document_id": document_id, "filename": file.filename, "facts_added": len(facts),
                "held_back": bool(conflicts), "reasons": conflicts})
    return {"document_id": document_id, "facts_added": len(facts), "held_back": bool(conflicts),
            "reasons": conflicts}
