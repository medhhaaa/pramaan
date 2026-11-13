"""GET /patients/{id}/search?q=&page=medications|records -> in-page search results. (Ashil)

[{"item_id", "score", "reason", "matched_terms", "source", "via"}], matches only, best first,
at most 50. item_id is a fact_id (medications) or a document_id (records).
reason: "mentioned" (1.0, source = the line {page, line, text}) | "same_visit" (0.7, via = the
item that mentioned it) | "similar" (embedding cosine x 0.6). How: backend/search.py.

Same access rules as the pages themselves (a doctor needs an open share). The audit log gets
the query text and the number of matches, never record content. No LLM is involved.
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query

from backend.auth import get_current_user, require_patient_access
from backend.db import get_conn, log_action
from backend.scope import access_scope, document_in_scope, fact_in_scope
from backend.search import search

router = APIRouter()


def visible_items(patient_id, scope):
    """(page, item_id) -> may this scoped doctor see it? Medications items are facts, records
    items are documents (backend/scope.py decides both)."""
    with get_conn() as conn:
        facts = [dict(r) for r in conn.execute(
            "SELECT fact_id, document_id, type, name FROM facts WHERE patient_id = ?", (patient_id,))]
    facts_ok = {f["fact_id"] for f in facts if fact_in_scope(f, scope)}
    by_doc = {}
    for f in facts:
        by_doc.setdefault(f["document_id"], []).append(f)
    docs_ok = {d for d, fs in by_doc.items() if document_in_scope(fs, scope)}
    return lambda page, item_id: item_id in (facts_ok if page == "medications" else docs_ok)


@router.get("/patients/{patient_id}/search")
def search_route(patient_id: str, q: str = Query("", max_length=100),
                 page: Literal["medications", "records"] = "medications", user=Depends(get_current_user)):
    scope = access_scope(require_patient_access(user, patient_id))
    results = search(patient_id, q, page, visible=None if scope == "all" else visible_items(patient_id, scope))
    log_action(user, "search", patient_id, {"page": page, "query": q.strip(), "matches": len(results)})
    return results
