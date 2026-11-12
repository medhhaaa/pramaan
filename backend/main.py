"""Pramaan backend. Run from the repo root:

    uvicorn backend.main:app --reload --port 8000

Then open http://localhost:8000/docs to try every route in the browser.
"""
from dotenv import load_dotenv

load_dotenv()  # must run before importing modules that read env vars

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from backend import auth  # noqa: E402
from backend.db import init_db  # noqa: E402
from backend.routes import (  # noqa: E402
    ask, audit, brief, check_medicine, corrections, delete, documents, flags,
    medications, metrics, patients, questions, timeline, upload,
)

app = FastAPI(title="Pramaan")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

for module in [
    auth,
    # core backend
    patients, upload, timeline, medications, flags, documents, corrections,
    # Medha
    ask, questions, brief, check_medicine, metrics, audit, delete,
]:
    app.include_router(module.router)


@app.get("/health")
def health():
    return {"ok": True}
