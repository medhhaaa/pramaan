"""Reset the database and load demo users + patient p1 sample facts. (Core backend)

Run:  python -m backend.seed
"""
import json
import os

from backend.auth import hash_password
from backend.db import DB_PATH, get_conn, init_db, insert_fact

ROOT = os.path.dirname(os.path.dirname(__file__))
SAMPLE_FACTS = os.path.join(ROOT, "shared", "sample_facts.json")

USERS = [("doctor", "doctor123", "doctor"), ("sunita", "sunita123", "patient")]

PATIENTS = [("p1", "Sunita Rao", "1952-06-14", "F", "O+")]

DOCUMENTS = [
    # id, filename, doc_type, document_date, held_back
    ("p1_d1", "d1_prescription_2019.pdf", "prescription", "2019-03-12", 0),
    ("p1_d2", "d2_lab_2021.pdf", "lab_report", "2021-06-20", 0),
    ("p1_d3", "d3_discharge_2022.pdf", "discharge_summary", "2022-08-05", 0),
    ("p1_d4", "d4_prescription_2023.pdf", "prescription", "2023-01-15", 0),
    ("p1_d5", "d5_lab_2023.pdf", "lab_report", "2023-01-16", 0),
    ("p1_d6", "d6_lab_2023_copy.pdf", "lab_report", "2023-01-16", 0),
    ("p1_d7", "d7_lab_psa.pdf", "lab_report", "2023-05-04", 1),  # wrong patient: held back
]


def seed():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    with get_conn() as conn:
        for username, password, role in USERS:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, hash_password(password), role),
            )
        conn.executemany("INSERT INTO patients VALUES (?, ?, ?, ?, ?)", PATIENTS)

        # doctor sees every patient, sunita sees only p1
        ids = {r["username"]: r["id"] for r in conn.execute("SELECT id, username FROM users")}
        for patient_id, *_ in PATIENTS:
            conn.execute("INSERT INTO user_patients VALUES (?, ?)", (ids["doctor"], patient_id))
        conn.execute("INSERT INTO user_patients VALUES (?, 'p1')", (ids["sunita"],))

        for doc_id, filename, doc_type, doc_date, held_back in DOCUMENTS:
            conn.execute(
                "INSERT INTO documents VALUES (?, 'p1', ?, ?, ?, ?, ?)",
                (doc_id, filename, doc_type, doc_date, f"data/patients/p1/{filename}", held_back),
            )

        with open(SAMPLE_FACTS, encoding="utf-8") as f:
            facts = json.load(f)
        for fact in facts:
            insert_fact(conn, fact)

    print(f"Seeded {DB_PATH}: {len(USERS)} users, {len(PATIENTS)} patient, {len(facts)} facts")


if __name__ == "__main__":
    seed()
