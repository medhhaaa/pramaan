"""GET /patients/{id}/disease-search?q=diabetes -> everything about one disease in the records. (Ashil)

Shape and matching rules: backend/disease_search.py. Same access as the record pages; a doctor
with partial sharing gets only in-scope facts plus hidden_count. The audit row has the query,
the disease it found and how many items, never record content. No AI.
"""
from fastapi import APIRouter, Depends, Query

from backend.auth import get_current_user, require_patient_access
from backend.db import log_action
from backend.disease_search import disease_search, fact_ids

router = APIRouter()


@router.get("/patients/{patient_id}/disease-search")
def disease_search_route(patient_id: str, q: str = Query(..., min_length=1, max_length=100),
                         user=Depends(get_current_user)):
    access = require_patient_access(user, patient_id)
    result = disease_search(patient_id, access, q.strip())
    log_action(user, "disease_search", patient_id, {"query": q.strip(), "disease": result["disease"],
                                                    "matches": len(fact_ids(result)), "hidden": result["hidden_count"]})
    return result
