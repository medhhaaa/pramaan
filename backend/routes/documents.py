"""GET /documents/{document_id} -> PDF + line positions for highlighting (Core backend)

Stub so the frontend can see the route exists. Replace the 501 with the real code.
"""
from fastapi import APIRouter, Depends, HTTPException

from backend.auth import get_current_user

router = APIRouter()


@router.get("/documents/{document_id}")
def documents_route(user=Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Not built yet")
