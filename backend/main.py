"""Pramaan backend. Run from the repo root:

    uvicorn backend.main:app --reload --port 8000

Then open http://localhost:8000/docs to try every route in the browser.
"""
import os

from dotenv import load_dotenv

load_dotenv()  # must run before importing modules that read env vars

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from backend import auth  # noqa: E402
from backend.db import init_db  # noqa: E402
from backend.routes import (  # noqa: E402
    agent, ask, audit, brief, not_sure, care_team, check_medicine, claims, consult_records, corrections, delete, documents,
    flags, language, medications, metrics, patients, privacy, questions, reading, refills, search, security, share,
    share_requests, timeline, upload,
)

# remember_request runs first on every request so shared (QR) access can be kept read-only
app = FastAPI(title="Pramaan", dependencies=[Depends(auth.remember_request)])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# trial OCR engine: load PaddleOCR's model now, not on the first upload
if os.getenv("OCR_ENGINE", "").lower() == "paddleocr":
    from pipeline.paddle_ocr import warm_up

    warm_up()

for module in [
    auth,
    # core backend
    patients, upload, timeline, medications, flags, documents, corrections, share, reading, security, privacy, agent, not_sure,
    # Medha
    ask, questions, brief, check_medicine, metrics, audit, delete, language, claims, care_team,
    refills, consult_records,
    # Ashil
    search, share_requests,
]:
    app.include_router(module.router)


@app.on_event("startup")
def start_agent_scheduler():
    """Question reminders and escalation every 15 minutes (backend/agent/reminders.py)."""
    if os.getenv("AGENT_SCHEDULER", "on").lower() != "off":
        from backend.agent.reminders import start_scheduler

        start_scheduler()


@app.get("/health")
def health():
    return {"ok": True}
