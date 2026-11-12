"""Shared plain-code helpers for Medha's routes: questions, brief, check_medicine. (Medha)

No AI here. Values are always copied exactly as written, never converted.
"""
from backend.db import fact_from_row


def load_facts(conn, patient_id, include_held_back=False):
    """This patient's facts in the contract format, oldest first.

    Facts from held-back (suspected wrong-patient) documents are left out unless asked for.
    Backend-made gap facts (status not_documented) may have no document, so LEFT JOIN.
    """
    held_back_filter = "" if include_held_back else "AND (d.held_back IS NULL OR d.held_back = 0)"
    rows = conn.execute(
        f"""SELECT f.* FROM facts f
            LEFT JOIN documents d ON d.id = f.document_id
            WHERE f.patient_id = ? {held_back_filter}
            ORDER BY f.event_date, f.document_date, f.fact_id""",
        (patient_id,),
    ).fetchall()
    return [fact_from_row(r) for r in rows]


def load_documents(conn, patient_id):
    """{document_id: {id, filename, doc_type, document_date, held_back}}"""
    rows = conn.execute(
        "SELECT id, filename, doc_type, document_date, held_back FROM documents WHERE patient_id = ?",
        (patient_id,),
    ).fetchall()
    return {r["id"]: dict(r) for r in rows}


def source_label(fact, docs):
    """'discharge summary from 2022-08-05' for the document a fact came from."""
    doc = docs.get(fact.get("document_id"))
    if not doc:
        return "records"
    kind = (doc["doc_type"] or "document").replace("_", " ")
    return f"{kind} from {doc['document_date'] or fact.get('document_date') or 'an unknown date'}"


def source_info(fact, docs):
    """Small source object for API responses."""
    doc = docs.get(fact.get("document_id")) or {}
    return {
        "fact_id": fact["fact_id"],
        "document_id": fact.get("document_id"),
        "doc_type": doc.get("doc_type"),
        "document_date": doc.get("document_date") or fact.get("document_date"),
        "quote": fact.get("quote"),
        "page": fact.get("page"),
        "line": fact.get("line"),
    }


def describe(fact):
    """'Metformin 1000mg twice daily', 'HbA1c 8.1 %', 'Penicillin (rash)'. Exactly as written."""
    if fact["type"] == "allergy" and fact.get("value"):
        return f"{fact['name']} ({fact['value']})"
    parts = [fact["name"], fact.get("dose"), fact.get("frequency"), fact.get("value"), fact.get("unit")]
    return " ".join(str(p) for p in parts if p)


def medication_summaries(facts):
    """One summary per medicine name, built from its documented medication facts.

    current:   the latest mention does not say "stopped" (it is not proof of taking it today)
    latest_fresh: the newest entry that is NOT a copy (echo) of an older document
    """
    groups = {}
    for f in facts:
        if f["type"] == "medication" and f["status"] == "documented":
            groups.setdefault(f["name"].strip().lower(), []).append(f)

    summaries = []
    for entries in groups.values():
        entries.sort(key=lambda f: (f["event_date"] or "", f["fact_id"]))
        fresh = [f for f in entries if not f["echo_of"]]
        latest = entries[-1]
        latest_fresh = fresh[-1] if fresh else latest
        summaries.append({
            "name": latest_fresh["name"],
            "current": latest["action"] != "stopped",
            "latest": latest,
            "latest_fresh": latest_fresh,
            "last_fresh_evidence_date": latest_fresh["event_date"] if fresh else None,
            "mentions": len(entries),
            "echo_count": len(entries) - len(fresh),
            "entries": entries,
        })
    summaries.sort(key=lambda m: m["name"].lower())
    return summaries
