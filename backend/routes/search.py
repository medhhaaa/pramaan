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
from backend.db import log_action
from backend.search import search

router = APIRouter()


@router.get("/patients/{patient_id}/search")
def search_route(patient_id: str, q: str = Query("", max_length=100),
                 page: Literal["medications", "records"] = "medications", user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    results = search(patient_id, q, page)
    log_action(user, "search", patient_id, {"page": page, "query": q.strip(), "matches": len(results)})
    return results
