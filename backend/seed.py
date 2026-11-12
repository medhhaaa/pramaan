"""Reset the database with demo users and the 5 demo patients. (Core backend)

    python -m backend.seed           users + patients p1-p5 + p1's SAMPLE facts
                                     (shared/sample_facts.json; no AI calls, for frontend work)
    python -m backend.seed --empty   users + patients p1-p5, no documents or facts
                                     (backend/load_demo.py uses this, then uploads the real PDFs)

Patient details come from Ashil's answer keys (data/answer_keys/pN.json), so they always
match the synthetic PDFs.
"""
import json
import os
import shutil
import sys

from backend.auth import hash_password
from backend.db import DB_PATH, get_conn, init_db, insert_fact

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_FACTS = os.path.join(ROOT, "shared", "sample_facts.json")
ANSWER_KEYS = os.path.join(ROOT, "data", "answer_keys")
PATIENT_IDS = ["p1", "p2", "p3", "p4", "p5"]

# username, password, role, patients they can see
USERS = [
    ("doctor", "doctor123", "doctor", PATIENT_IDS),
    ("sunita", "sunita123", "patient", ["p1"]),
]


def load_answer_key(patient_id):
    with open(os.path.join(ANSWER_KEYS, f"{patient_id}.json"), encoding="utf-8") as f:
        return json.load(f)


def seed(with_sample_facts=True):
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    # uploaded files belong to the old database, so remove them too
    shutil.rmtree(os.path.join(ROOT, "storage"), ignore_errors=True)
    os.makedirs(os.path.join(ROOT, "storage"), exist_ok=True)
    open(os.path.join(ROOT, "storage", ".gitkeep"), "w").close()

    init_db()
    with get_conn() as conn:
        for patient_id in PATIENT_IDS:
            p = load_answer_key(patient_id)["patient"]
            conn.execute(
                "INSERT INTO patients VALUES (?, ?, ?, ?, ?)",
                (patient_id, p["name"], p["dob"], p["sex"], p["blood_group"]),
            )

        for username, password, role, patient_ids in USERS:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, hash_password(password), role),
            )
            for patient_id in patient_ids:
                conn.execute("INSERT INTO user_patients VALUES (?, ?)", (cur.lastrowid, patient_id))

        facts = []
        if with_sample_facts:
            # p1's documents from the answer key, pointing at the real synthetic PDFs
            for d in load_answer_key("p1")["documents"]:
                conn.execute(
                    "INSERT INTO documents VALUES (?, 'p1', ?, ?, ?, ?, ?)",
                    (d["document_id"], d["filename"], d["doc_type"], d["document_date"],
                     f"data/patients/p1/{d['filename']}", int(d["held_back"])),
                )
            with open(SAMPLE_FACTS, encoding="utf-8") as f:
                facts = json.load(f)
            for fact in facts:
                insert_fact(conn, fact)

    print(f"Seeded {DB_PATH}: {len(USERS)} users, {len(PATIENT_IDS)} patients, {len(facts)} sample facts")


if __name__ == "__main__":
    seed(with_sample_facts="--empty" not in sys.argv)
