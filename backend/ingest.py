"""ingest_document(): everything that happens to one uploaded PDF. (Core backend)

Used by the upload route AND by backend/load_demo.py, so both run exactly the same steps:
1. save the PDF ENCRYPTED under storage/<patient>/
2. run Ashil's pipeline on a temporary decrypted copy (deleted right after)
3. wrong-patient check: if the document's blood group / sex disagree with the patient
   record, its facts get the wrong_patient flag and the document is held back
4. save the document row (with its doc_type evidence) + verified facts
5. rerun the checks on ALL the patient's facts (recompute_patient)
6. a verified discharge summary opens a hospital stay for the Claim Documents checklist
   if the patient has no open stay (backend/routes/claims.py)
If the pipeline fails, the stored file is removed, nothing is saved, and the error is raised.
"""
import os

from backend.db import fact_from_row, get_conn, insert_fact
from backend.logic.wrong_patient import find_conflicts
from backend.recompute import recompute_patient
from backend.storage import delete_file, save_encrypted, temp_copy
from pipeline import process


def new_document_id(conn, patient_id):
    n = conn.execute("SELECT COUNT(*) FROM documents WHERE patient_id = ?", (patient_id,)).fetchone()[0] + 1
    while conn.execute("SELECT 1 FROM documents WHERE id = ?", (f"{patient_id}_d{n}",)).fetchone():
        n += 1
    return f"{patient_id}_d{n}"


def _use_saved(saved, patient_id, document_id):
    """Ashil's saved pipeline output (data/extracted/pN.json) for one document, with the
    IDs set to the document_id this upload got."""
    result = dict(saved)
    result["facts"] = [
        dict(f, patient_id=patient_id, document_id=document_id, fact_id=f"{document_id}_f{n:03d}")
        for n, f in enumerate(saved["facts"], start=1)
    ]
    return result


def ingest_document(patient_id, filename, data, doc_type=None, saved=None):
    """data = the PDF bytes. Returns {"document_id", "facts_added", "held_back", "reasons",
    "dropped", "doc_type", "document_date"} plus, for the upload report, "added_facts"
    (the saved facts), "dropped_facts" (left out by quote verification, with drop_reason)
    and "not_captured" (medical lines no fact quotes).
    saved = optional saved pipeline output for this document: then the AI is not called
    (used by load_demo --saved), and every other step still runs."""
    with get_conn() as conn:
        patient = dict(conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone())
        document_id = new_document_id(conn, patient_id)

    rel_path = f"storage/{patient_id}/{document_id}.pdf.enc"
    save_encrypted(data, rel_path)
    if saved is not None:
        result = _use_saved(saved, patient_id, document_id)
    else:
        tmp = temp_copy(rel_path)
        try:
            # known_names makes sure the patient's own name is redacted before the AI call
            result = process.process_document_full(tmp, patient_id, document_id, known_names=[patient["name"]])
        except Exception:
            delete_file(rel_path)
            raise
        finally:
            os.remove(tmp)

    facts = result["facts"]
    conflicts = find_conflicts(facts, patient)
    if conflicts:
        for fact in facts:
            fact["flags"] = list(fact.get("flags") or []) + ["wrong_patient"]

    # a doc_type typed by the uploader has no quote, so it counts as not verified
    evidence = {} if doc_type else result
    doc_type = doc_type or result.get("doc_type") or "unknown"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO documents (id, patient_id, filename, doc_type, document_date, file_path,"
            " held_back, doc_type_quote, doc_type_page, doc_type_line)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (document_id, patient_id, filename, doc_type, result.get("document_date"), rel_path,
             int(bool(conflicts)), evidence.get("doc_type_quote"), evidence.get("doc_type_page"),
             evidence.get("doc_type_line")),
        )
        for fact in facts:
            insert_fact(conn, fact)

    recompute_patient(patient_id)
    if doc_type == "discharge_summary" and evidence.get("doc_type_quote") and not conflicts:
        from backend.routes.claims import stay_from_discharge_summary  # avoids an import loop
        stay_from_discharge_summary(patient_id, document_id, result.get("stay_dates") or {})
    # the saved facts as they are now, with the flags the checks just added
    with get_conn() as conn:
        added = [fact_from_row(row) for row in conn.execute(
            "SELECT * FROM facts WHERE document_id = ? ORDER BY page, line", (document_id,))]
    return {
        "added_facts": added,
        "dropped_facts": result.get("dropped") or [],
        "not_captured": result.get("not_captured") or [],
        "document_id": document_id,
        "facts_added": len(facts),
        "held_back": bool(conflicts),
        "reasons": conflicts,
        "dropped": len(result.get("dropped") or []),
        "doc_type": doc_type,
        "document_date": result.get("document_date"),
    }
