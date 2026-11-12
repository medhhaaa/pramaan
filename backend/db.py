"""SQLite database: one file, plain sqlite3, no ORM. (Core backend)

get_conn()          open a connection; rows behave like dicts (row["name"])
init_db()           create all tables if they don't exist
fact_from_row(row)  turn a facts-table row into the contract dict (CLAUDE.md section 5)
"""
import json
import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "pramaan.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('doctor', 'patient'))
);
CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    name TEXT, dob TEXT, sex TEXT, blood_group TEXT
);
CREATE TABLE IF NOT EXISTS user_patients (
    user_id INTEGER NOT NULL,
    patient_id TEXT NOT NULL,
    PRIMARY KEY (user_id, patient_id)
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    filename TEXT, doc_type TEXT, document_date TEXT, file_path TEXT,
    held_back INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    type TEXT, name TEXT, dose TEXT, frequency TEXT, value TEXT, unit TEXT,
    action TEXT, status TEXT,
    event_date TEXT, document_date TEXT, date_raw TEXT,
    quote TEXT, page INTEGER, line INTEGER,
    quote_verified INTEGER DEFAULT 0,
    echo_of TEXT, badge TEXT,
    flags TEXT DEFAULT '[]',
    corrected INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id TEXT, field TEXT, old_value TEXT, new_value TEXT,
    corrected_by INTEGER, role TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, action TEXT, patient_id TEXT, detail TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT, fact_ids TEXT, text TEXT,
    status TEXT DEFAULT 'open' CHECK (status IN ('open', 'answered', 'sent_to_doctor', 'resolved')),
    answer TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
-- time-limited QR / code sharing (backend/routes/share.py). Only hashes of the token and
-- code are stored. Times are UTC "YYYY-MM-DD HH:MM:SS" so SQLite's datetime('now') compares.
CREATE TABLE IF NOT EXISTS share_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    created_by INTEGER NOT NULL,
    token_hash TEXT UNIQUE NOT NULL,
    code_hash TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    opened_by INTEGER,
    opened_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

FACT_FIELDS = [
    "fact_id", "patient_id", "document_id", "type", "name", "dose", "frequency",
    "value", "unit", "action", "status", "event_date", "document_date", "date_raw",
    "quote", "page", "line", "quote_verified", "echo_of", "badge", "flags", "corrected",
]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def fact_from_row(row):
    fact = dict(row)
    fact["flags"] = json.loads(fact["flags"] or "[]")
    fact["quote_verified"] = bool(fact["quote_verified"])
    fact["corrected"] = bool(fact["corrected"])
    return fact


def log_action(user, action, patient_id=None, detail=None):
    """Write one row to audit_log. Call it from every route that reads or changes patient data.

    user: the dict from get_current_user  action: short verb like "view_timeline"
    detail: optional string or dict (dicts are saved as JSON)
    """
    if isinstance(detail, (dict, list)):
        detail = json.dumps(detail)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO audit_log (user_id, action, patient_id, detail) VALUES (?, ?, ?, ?)",
            (user["id"] if user else None, action, patient_id, detail),
        )


def insert_fact(conn, fact):
    """Save one contract-format fact (replaces an existing one with the same fact_id)."""
    row = dict(fact)
    row["flags"] = json.dumps(row.get("flags") or [])
    row["quote_verified"] = int(bool(row.get("quote_verified")))
    row["corrected"] = int(bool(row.get("corrected")))
    columns = ", ".join(FACT_FIELDS)
    placeholders = ", ".join("?" for _ in FACT_FIELDS)
    conn.execute(
        f"INSERT OR REPLACE INTO facts ({columns}) VALUES ({placeholders})",
        [row.get(field) for field in FACT_FIELDS],
    )
