"""DELETE /patients/{patient_id} -> delete all of this patient's data. (Medha)
DELETE /documents/{document_id} -> delete ONE uploaded document (e.g. a file added twice by mistake).
PATCH  /documents/{document_id}  body {"filename"} -> rename an uploaded document (display name only;
       the stored file, its facts and every check stay as they are). -> {"id", "filename"}

Response: {"deleted": {"facts", "documents", "files", "corrections", "questions", "hospital_stays",
                       "audit_entries"}}
One document: {"deleted": {"document_id", "facts", "files"}}. Only the patient themself can do it
(doctors only read). The health profile is not a document you delete here: change it in the form.
Afterwards every check (echoes, flags, badges, search, questions) runs again without it.

Deletes facts, their corrections, questions, documents (rows + uploaded files), access links,
the patient row and the old audit entries. One new audit row records that the deletion
happened, with counts only (no medical or personal details).

Only files inside storage/ are removed. Seeded demo PDFs in data/ are never touched.
"""
import os
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

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


PROFILE_DOC_TYPE = "patient_profile"  # backend/routes/profile.py: answers typed in the form


def own_uploaded_document(user, document_id, verb):
    """The document row, if this user is the patient it belongs to and it is a real upload."""
    with get_conn() as conn:
        doc = conn.execute("SELECT id, patient_id, filename, doc_type, file_path FROM documents WHERE id = ?",
                           (document_id,)).fetchone()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if require_patient_access(user, doc["patient_id"])["kind"] != "own":
        raise HTTPException(status_code=403, detail=f"Only the patient can {verb} a document")
    if doc["doc_type"] == PROFILE_DOC_TYPE:
        raise HTTPException(status_code=400, detail="This is your health profile: change it in the profile form")
    return doc


@router.delete("/documents/{document_id}")
def delete_document_route(document_id: str, user=Depends(get_current_user)):
    from backend.recompute import recompute_patient
    from backend.routes.questions import sync_questions  # imported here: avoids an import loop

    doc = own_uploaded_document(user, document_id, "delete")

    patient_id = doc["patient_id"]
    with get_conn() as conn:
        conn.execute("DELETE FROM corrections WHERE fact_id IN (SELECT fact_id FROM facts WHERE document_id = ?)",
                     (document_id,))
        facts = conn.execute("DELETE FROM facts WHERE document_id = ?", (document_id,)).rowcount
        conn.execute("DELETE FROM not_sure_items WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM agent_steps WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM claim_pack_items WHERE document_id = ?", (document_id,))
        # a hospital stay opened from this discharge summary stays (it may hold the patient's own dates)
        conn.execute("UPDATE hospital_stays SET source_document_id = NULL WHERE source_document_id = ?",
                     (document_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    files = int(remove_stored_file(doc["file_path"]))  # after the rows are gone
    recompute_patient(patient_id)  # echoes, flags, badges and search without this document
    with get_conn() as conn:
        sync_questions(conn, patient_id)  # questions about its facts are retired
    # ids and counts only: no file name, no medical details
    log_action(user, "delete_document", patient_id, f"{document_id}: {facts} facts, {files} file")
    return {"deleted": {"document_id": document_id, "facts": facts, "files": files}}


MAX_NAME = 120
EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,5}$")


class RenameBody(BaseModel):
    filename: str


def clean_filename(new, old):
    """Spaces tidied; no folders or control characters; the old extension (.pdf) is kept when the
    new name has none, so "Lab report March" becomes "Lab report March.pdf"."""
    name = " ".join((new or "").split())
    if not name or name in (".", ".."):
        raise HTTPException(status_code=422, detail="Type a name for the document")
    if re.search(r"[\/\x00-\x1f\x7f]", name):
        raise HTTPException(status_code=422, detail="A name cannot contain / or \\")
    ext = EXTENSION.search(old or "")
    if ext and not EXTENSION.search(name):
        name += ext.group(0)
    if len(name) > MAX_NAME:
        raise HTTPException(status_code=422, detail=f"Keep the name under {MAX_NAME} characters")
    return name


@router.patch("/documents/{document_id}")
def rename_document_route(document_id: str, body: RenameBody, user=Depends(get_current_user)):
    doc = own_uploaded_document(user, document_id, "rename")
    name = clean_filename(body.filename, doc["filename"])
    with get_conn() as conn:
        conn.execute("UPDATE documents SET filename = ? WHERE id = ?", (name, document_id))
    log_action(user, "rename_document", doc["patient_id"], document_id)  # the id only, not the names
    return {"id": document_id, "filename": name}
