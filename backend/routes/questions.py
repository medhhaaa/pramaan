"""Things to Check / Open Questions. (Medha)

GET  /patients/{patient_id}/questions
POST /questions/{question_id}/answer   {"answer": "yes|no|value|dont_know|skip", "value": ...}

Stubs so the frontend can see the routes exist. Replace the 501s with the real code.
"""
from fastapi import APIRouter, Depends, HTTPException

from backend.auth import get_current_user

router = APIRouter()


@router.get("/patients/{patient_id}/questions")
def list_questions(user=Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Not built yet")


@router.post("/questions/{question_id}/answer")
def answer_question(user=Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Not built yet")
