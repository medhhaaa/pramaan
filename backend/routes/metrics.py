"""GET /metrics -> extraction precision / recall. (Medha)

Returns data/metrics_results.json, written by Ashil's `python -m pipeline.metrics`:
{"overall": {"precision", "recall", "f1"}, "per_patient": {...}, "per_type": {...}}
"""
import json
import os

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import get_current_user

router = APIRouter()

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
METRICS_FILE = os.path.join(ROOT, "data", "metrics_results.json")


@router.get("/metrics")
def metrics_route(user=Depends(get_current_user)):
    if not os.path.exists(METRICS_FILE):
        raise HTTPException(
            status_code=404,
            detail="No metrics yet. Run: python -m pipeline.metrics",
        )
    with open(METRICS_FILE, encoding="utf-8") as f:
        return json.load(f)
