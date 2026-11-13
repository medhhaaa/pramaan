"""SQLite database: one file, plain sqlite3, no ORM. (Core backend)

get_conn()          open a connection; rows behave like dicts (row["name"])
init_db()           create all tables if they don't exist (and add newer columns to an old file)
fact_from_row(row)  turn a facts-table row into the contract dict (CLAUDE.md section 5)
"""
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "pramaan.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('doctor', 'patient')),
    language TEXT  -- 'en', 'kn' or 'hi'; NULL until the user picks one at first login
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
    held_back INTEGER DEFAULT 0,
    -- the line that shows the doc_type, verified like a fact quote (NULL = not verified)
    doc_type_quote TEXT, doc_type_page INTEGER, doc_type_line INTEGER
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
    corrected INTEGER DEFAULT 0,
    confidence INTEGER,  -- 0-100, only for facts read from handwriting
    unsure TEXT DEFAULT '[]'  -- JSON list of best-guess words in this fact (handwriting)
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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    prev_hash TEXT, row_hash TEXT  -- tamper-evident chain (log_action / verify_audit_chain)
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT, fact_ids TEXT, text TEXT,
    status TEXT DEFAULT 'open' CHECK (status IN ('open', 'answered', 'sent_to_doctor', 'resolved')),
    answer TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    text_kn TEXT,  -- the same question in Kannada
    -- claim checklist questions ("Did you have surgery during this hospital stay?")
    stay_id INTEGER, claim_condition TEXT
);
-- a hospital stay, for the Claim Documents checklist (backend/routes/claims.py).
-- surgery / implant_used / accident: 1 yes, 0 no, NULL not answered or "I don't know"
-- in-page search (backend/search.py): one row per searchable item, rebuilt by recompute_patient.
-- page 'medications': item = a medication fact; page 'records': item = a document.
CREATE TABLE IF NOT EXISTS search_items (
    patient_id TEXT NOT NULL,
    page TEXT NOT NULL,
    item_id TEXT NOT NULL,
    search_text TEXT,   -- the item's source lines as JSON, ENCRYPTED (storage.encrypt_text)
    names TEXT,         -- JSON: normalized names (a medicine also gets its generic and brand names)
    synonyms TEXT,      -- JSON: synonym groups (data/synonyms.json) whose terms appear in the item
    visits TEXT,        -- JSON: visit keys shared with other items (doc:<id>, day:<date>, stay:<id>)
    text_hash TEXT,     -- sha256 of the text the embedding was made from (re-embed only on change)
    embedding BLOB,     -- float32 vector from the local sentence-transformers model, or NULL
    PRIMARY KEY (page, item_id)
);
CREATE TABLE IF NOT EXISTS hospital_stays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    admitted_on TEXT, discharged_on TEXT,
    surgery INTEGER, implant_used INTEGER, accident INTEGER,
    source TEXT,              -- 'patient' (tapped "I had a hospital stay") or 'discharge_summary'
    source_document_id TEXT,  -- the discharge summary that created it
    my_reminder_date TEXT,    -- a date the patient typed for their own reminder
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
-- ---- doctor features (backend/routes/care_team.py, refills.py, consult_records.py) ----
-- Care team: the patient's lasting consent for one doctor. scope is 'all' or a JSON list of
-- condition tags from rules/condition_tags.json (["diabetes", "hypertension"]).
-- followup_on: a follow-up date the doctor set; followup_set_at: when they set it.
CREATE TABLE IF NOT EXISTS care_team (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    doctor_id INTEGER NOT NULL,
    scope TEXT NOT NULL DEFAULT 'all',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_confirmed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    revoked_at TEXT,
    followup_on TEXT,
    followup_set_at TEXT
);
-- In-app prescriptions written by a care-team doctor. A refill approval makes a new version
-- (previous_id = the prescription it renews).
CREATE TABLE IF NOT EXISTS prescriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    doctor_id INTEGER NOT NULL,
    previous_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
-- One medicine on a prescription. Active while status = 'active' and end_date >= today.
-- dose_times: JSON list of reminder times ["08:00", "20:00"].
CREATE TABLE IF NOT EXISTS prescription_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prescription_id INTEGER NOT NULL,
    patient_id TEXT NOT NULL,
    medicine TEXT NOT NULL, dose TEXT, frequency TEXT,
    duration_days INTEGER NOT NULL,
    start_date TEXT NOT NULL, end_date TEXT NOT NULL,
    dose_times TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'stopped', 'renewed')),
    previous_item_id INTEGER
);
-- Medicine reminders: one row per dose time, from a prescription item's dates.
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    prescription_item_id INTEGER NOT NULL,
    time_of_day TEXT NOT NULL,          -- "08:00"
    start_date TEXT NOT NULL, end_date TEXT NOT NULL
);
-- What the patient tapped for one reminder on one day. A due dose with no row counts as missed.
CREATE TABLE IF NOT EXISTS dose_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    reminder_id INTEGER NOT NULL,
    dose_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('taken', 'skipped')),
    logged_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (reminder_id, dose_date)
);
CREATE TABLE IF NOT EXISTS refill_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    doctor_id INTEGER NOT NULL,
    prescription_item_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'declined', 'visit_required')),
    patient_note TEXT, doctor_note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    decided_at TEXT
);
-- Medico-legal snapshot of every prescription and refill decision. Never updated or deleted:
-- a correction is a new row pointing at the original. sha256 covers every other field.
CREATE TABLE IF NOT EXISTS consult_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id INTEGER NOT NULL,
    patient_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('prescription', 'refill_decision')),
    snapshot_json TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    warnings_shown_json TEXT NOT NULL DEFAULT '[]',
    overrides_json TEXT NOT NULL DEFAULT '[]',
    corrects_record_id INTEGER,
    created_at TEXT NOT NULL,
    sha256 TEXT NOT NULL
);
-- In-app notifications (refill decisions).
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    patient_id TEXT,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    link TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    read_at TEXT
);
"""

FACT_FIELDS = [
    "fact_id", "patient_id", "document_id", "type", "name", "dose", "frequency",
    "value", "unit", "action", "status", "event_date", "document_date", "date_raw",
    "quote", "page", "line", "quote_verified", "echo_of", "badge", "flags", "corrected",
    "confidence", "unsure",
]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# columns added after the first version: init_db adds them to an existing pramaan.db
ADDED_COLUMNS = [
    ("audit_log", "prev_hash", "TEXT"),
    ("audit_log", "row_hash", "TEXT"),
    ("facts", "confidence", "INTEGER"),
    ("facts", "unsure", "TEXT DEFAULT '[]'"),
    ("documents", "needs_reading", "INTEGER DEFAULT 0"),
    ("users", "language", "TEXT"),
    ("questions", "text_kn", "TEXT"),
    ("questions", "stay_id", "INTEGER"),
    ("questions", "claim_condition", "TEXT"),
    ("documents", "doc_type_quote", "TEXT"),
    ("documents", "doc_type_page", "INTEGER"),
    ("documents", "doc_type_line", "INTEGER"),
    # doctors: shown name and registration number (patients search by either)
    ("users", "full_name", "TEXT"),
    ("users", "registration_number", "TEXT"),
    # when the document was uploaded (UTC "YYYY-MM-DD HH:MM:SS"), for "new report" on My Patients
    ("documents", "uploaded_at", "TEXT"),
]


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        for table, column, kind in ADDED_COLUMNS:
            have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")


def fact_from_row(row):
    fact = dict(row)
    fact["flags"] = json.loads(fact["flags"] or "[]")
    if "unsure" in fact:
        fact["unsure"] = json.loads(fact["unsure"] or "[]")
    fact["quote_verified"] = bool(fact["quote_verified"])
    fact["corrected"] = bool(fact["corrected"])
    return fact


# ---------- tamper-evident audit log ----------
# Every audit row stores row_hash = SHA-256 of (previous row's hash + this row's contents).
# Editing, deleting or inserting a row in the middle breaks every hash after it, and
# verify_audit_chain() finds the first broken row. (Deleting only the newest rows can't be
# seen from inside the database: the scorecard shows the latest hash so it can be noted down.)

GENESIS_HASH = "0" * 64  # the "previous hash" of the very first row


def _audit_hash(prev_hash, user_id, action, patient_id, detail, created_at):
    payload = json.dumps([prev_hash, user_id, action, patient_id, detail, created_at],
                         separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append_audit(conn, user_id, action, patient_id=None, detail=None, created_at=None):
    """Add one chained row using an open connection (call log_action from routes)."""
    if isinstance(detail, (dict, list)):
        detail = json.dumps(detail)
    created_at = created_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    last = conn.execute("SELECT row_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    prev_hash = last["row_hash"] if last and last["row_hash"] else GENESIS_HASH
    row_hash = _audit_hash(prev_hash, user_id, action, patient_id, detail, created_at)
    conn.execute(
        """INSERT INTO audit_log (user_id, action, patient_id, detail, created_at, prev_hash, row_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, action, patient_id, detail, created_at, prev_hash, row_hash),
    )


def log_action(user, action, patient_id=None, detail=None):
    """Write one row to audit_log. Call it from every route that reads or changes patient data.

    user: the dict from get_current_user  action: short verb like "view_timeline"
    detail: optional string or dict (dicts are saved as JSON)
    """
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")  # one writer at a time, so two rows never share a parent
        append_audit(conn, user["id"] if user else None, action, patient_id, detail)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify_audit_chain():
    """{"entries", "intact", "broken_at", "reason", "latest_hash"}: recomputes every row's hash."""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    prev = GENESIS_HASH
    for row in rows:
        if row["prev_hash"] != prev:
            return {"entries": len(rows), "intact": False, "broken_at": row["id"],
                    "reason": "a row before this one was changed, removed or added", "latest_hash": None}
        expected = _audit_hash(prev, row["user_id"], row["action"], row["patient_id"], row["detail"], row["created_at"])
        if row["row_hash"] != expected:
            return {"entries": len(rows), "intact": False, "broken_at": row["id"],
                    "reason": "this row's contents were changed", "latest_hash": None}
        prev = row["row_hash"]
    return {"entries": len(rows), "intact": True, "broken_at": None, "reason": None, "latest_hash": prev}


def insert_fact(conn, fact):
    """Save one contract-format fact (replaces an existing one with the same fact_id)."""
    row = dict(fact)
    row["flags"] = json.dumps(row.get("flags") or [])
    row["unsure"] = json.dumps(row.get("unsure") or [])
    row["quote_verified"] = int(bool(row.get("quote_verified")))
    row["corrected"] = int(bool(row.get("corrected")))
    columns = ", ".join(FACT_FIELDS)
    placeholders = ", ".join("?" for _ in FACT_FIELDS)
    conn.execute(
        f"INSERT OR REPLACE INTO facts ({columns}) VALUES ({placeholders})",
        [row.get(field) for field in FACT_FIELDS],
    )
