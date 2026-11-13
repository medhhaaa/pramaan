"""Where else is it? For the upload report: which facts of a new document are already stored in
another document, and where. (Ashil)

    where_else(patient_id, document_id) ->
      {"duplicates": [{"fact_id", "type", "name", "dose", "frequency", "value", "unit",
                       "kind": "duplicate" | "copied_line",
                       "original": {"fact_id", "document_id", "filename", "doc_type", "document_date",
                                    "uploaded_at", "page", "line", "quote", "held_back"},
                       "other_documents": n}],
       "copy_of_document": {"id", "filename", "doc_type", "document_date", "uploaded_at",
                            "matching", "of"} | null}

duplicate    the same result on the same date in another document: exactly the rule of the
             "duplicate" flag (backend/logic/flags.duplicate_key). original = the earliest copy.
copied_line  a medicine line copied word for word from an older document (echo, backend/logic/echo.py).
copy_of_document: every clinical fact of the new document is also in ONE earlier document, so the
             upload is most likely the same paper again (e.g. a lab report saved twice).
Demographics (blood group, sex) are left out: every document repeats them. Plain code, no AI.
"""
from collections import Counter, defaultdict

from backend.db import fact_from_row, get_conn
from backend.logic.flags import document_order, duplicate_key

FIELDS = ("fact_id", "type", "name", "dose", "frequency", "value", "unit")


def _place(fact):
    return {"fact_id": fact["fact_id"], "document_id": fact["document_id"], "filename": fact["filename"],
            "doc_type": fact["doc_type"], "document_date": fact["doc_date"], "uploaded_at": fact["uploaded_at"],
            "page": fact["page"], "line": fact["line"], "quote": fact["quote"], "held_back": bool(fact["held_back"])}


def where_else(patient_id, document_id):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT f.*, d.filename, d.doc_type, d.document_date AS doc_date, d.uploaded_at, d.held_back
               FROM facts f JOIN documents d ON d.id = f.document_id WHERE f.patient_id = ?""",
            (patient_id,),
        ).fetchall()
    facts = [fact_from_row(r) for r in rows]
    by_id = {f["fact_id"]: f for f in facts}
    new = [f for f in facts if f["document_id"] == document_id
           and f["type"] != "demographic" and f["status"] != "not_documented"]
    elsewhere = defaultdict(list)
    for f in facts:
        if f["document_id"] != document_id:
            elsewhere[duplicate_key(f)].append(f)

    duplicates, docs_matching = [], Counter()
    for fact in sorted(new, key=lambda f: (f.get("page") or 0, f.get("line") or 0)):
        same = sorted(elsewhere.get(duplicate_key(fact), []), key=document_order)
        if same:
            other_docs = {s["document_id"] for s in same}
            docs_matching.update(other_docs)
            duplicates.append({**{k: fact.get(k) for k in FIELDS}, "kind": "duplicate",
                               "original": _place(same[0]), "other_documents": len(other_docs)})
            continue
        original = by_id.get(fact.get("echo_of"))
        if original and original["document_id"] != document_id:
            duplicates.append({**{k: fact.get(k) for k in FIELDS}, "kind": "copied_line",
                               "original": _place(original), "other_documents": 1})

    copy_of = None
    if new and docs_matching:
        # the document matching the most facts; on a tie (the same paper stored twice already) the
        # earliest one, so the answer never depends on set order (most_common alone would)
        first_fact = {}
        for f in facts:
            first_fact.setdefault(f["document_id"], f)
        matching = max(docs_matching.values())
        doc_id = min((d for d, n in docs_matching.items() if n == matching),
                     key=lambda d: document_order(first_fact[d]))
        if matching == len(new):
            any_fact = first_fact[doc_id]
            copy_of = {"id": doc_id, "filename": any_fact["filename"], "doc_type": any_fact["doc_type"],
                       "document_date": any_fact["doc_date"], "uploaded_at": any_fact["uploaded_at"],
                       "matching": matching, "of": len(new)}
    return {"duplicates": duplicates, "copy_of_document": copy_of}
