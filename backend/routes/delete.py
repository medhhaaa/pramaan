"""DELETE /patients/{patient_id} -> delete all of this patient's data. (Medha)

Response: {"deleted": {"facts", "documents", "files", "corrections", "questions", "hospital_stays",
                       "audit_entries"}}

Deletes facts, their corrections, questions, documents (rows + uploaded files), access links,
the patient row and the old audit entries. One new audit row records that the deletion
happened, with counts only (no medical or personal details).

Only files inside storage/ are removed. Seeded demo PDFs in data/ are never touched.
"""
import os

from fastapi import APIRouter, Depends

from backend import storage
from backend.auth import get_current_user, require_patient_access
from backend.db import get_conn
from backend.routes.audit_helper import log_action

router = APIRouter()


def remove_stored_file(file_path):
    """Delete the file only if it lives inside storage/. Returns True if a file was removed.
    The root comes from backend.storage at call time (the same place uploads were saved; tests
    point it at a temp folder)."""
    if not file_path:
        return False
    storage_dir = os.path.realpath(os.path.join(storage.ROOT, "storage"))
    full = os.path.realpath(storage.abs_path(file_path))
    if os.path.commonpath([full, storage_dir]) != storage_dir:
        return False
    if os.path.isfile(full):
        os.remove(full)
        return True
    return False


@router.delete("/patients/{patient_id}")
def delete_route(patient_id: str, user=Depends(get_current_user)):
    require_patient_access(user, patient_id)

    with get_conn() as conn:
        file_paths = [  # the working PDF and, for a photo upload, the original photo
            path
            for r in conn.execute("SELECT file_path, original_path FROM documents WHERE patient_id = ?", (patient_id,))
            for path in (r["file_path"], r["original_path"]) if path
        ]
        # before the stays: claim_pack_items only knows its stay
        conn.execute("DELETE FROM claim_pack_items WHERE stay_id IN (SELECT id FROM hospital_stays WHERE patient_id = ?)",
                     (patient_id,))
        deleted = {
            "corrections": conn.execute(
                "DELETE FROM corrections WHERE fact_id IN (SELECT fact_id FROM facts WHERE patient_id = ?)",
                (patient_id,),
            ).rowcount,
            "facts": conn.execute("DELETE FROM facts WHERE patient_id = ?", (patient_id,)).rowcount,
            "questions": conn.execute("DELETE FROM questions WHERE patient_id = ?", (patient_id,)).rowcount,
            "hospital_stays": conn.execute(
                "DELETE FROM hospital_stays WHERE patient_id = ?", (patient_id,)).rowcount,
            "documents": conn.execute("DELETE FROM documents WHERE patient_id = ?", (patient_id,)).rowcount,
            "search_items": conn.execute("DELETE FROM search_items WHERE patient_id = ?", (patient_id,)).rowcount,
            "audit_entries": conn.execute("DELETE FROM audit_log WHERE patient_id = ?", (patient_id,)).rowcount,
        }
        conn.execute("DELETE FROM user_patients WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM share_requests WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM assistant_actions WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM share_links WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))

    # files last, after the database rows are gone
    deleted["files"] = sum(remove_stored_file(p) for p in file_paths)

    summary = ", ".join(f"{n} {name}" for name, n in deleted.items())
    log_action(user, "delete_patient_data", patient_id, summary)
    return {"deleted": deleted}
