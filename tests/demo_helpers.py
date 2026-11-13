"""Load the doctor-feature demo (Dr. Rao's care team) into the throwaway test database."""
import gc
import json
import os

from backend import seed
from backend.db import get_conn
from backend.ingest import ingest_document

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = ["p1", "p2", "p3", "p4", "p7"]


def load_care_team_demo():
    """Reset, ingest the demo patients' PDFs with saved pipeline output (no AI), build the demo."""
    from backend.demo_care_team import build

    gc.collect()  # close sqlite connections other test files left open (Windows file lock)
    seed.seed(with_sample_facts=False)
    for pid in DEMO:
        with open(os.path.join(ROOT, "data", "extracted", f"{pid}.json"), encoding="utf-8") as f:
            saved = {d["document_id"]: d for d in json.load(f)["documents"]}
        for d in sorted(seed.load_answer_key(pid)["documents"], key=lambda d: d["filename"]):
            with open(os.path.join(ROOT, "data", "patients", pid, d["filename"]), "rb") as f:
                ingest_document(pid, d["filename"], f.read(), saved=saved[d["document_id"]])
    build()


def login(client, username):
    password = {"guestdoctor": "guest123"}.get(username, username + "123")
    token = client.post("/login", json={"username": username, "password": password}).json()["token"]
    return {"Authorization": "Bearer " + token}


def user_id(username):
    with get_conn() as conn:
        return conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"]
