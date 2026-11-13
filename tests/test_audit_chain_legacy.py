"""Audit chain on a database that existed before the chain was added (backend/db.py
verify_audit_chain): old rows with no hashes at the START are counted as "before the chain" and
never passed off as checked; the chained rows after them are verified as usual; a row without
hashes anywhere after the chain started still breaks it. The test puts the log back exactly as
it was afterwards."""
import sqlite3

from backend.db import DB_PATH, append_audit, get_conn, init_db, verify_audit_chain

COLUMNS = "id, user_id, action, patient_id, detail, created_at, prev_hash, row_hash"


def _with_log(rows_fn):
    """Run rows_fn(conn) on an emptied audit_log, then restore the original rows."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    saved = conn.execute(f"SELECT {COLUMNS} FROM audit_log ORDER BY id").fetchall()
    try:
        with conn:
            conn.execute("DELETE FROM audit_log")
        rows_fn()
        return verify_audit_chain()
    finally:
        with conn:
            conn.execute("DELETE FROM audit_log")
            conn.executemany(f"INSERT INTO audit_log ({COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", saved)
        conn.close()


def _legacy(conn, n):
    for i in range(n):  # what an old pramaan.db holds: rows written before prev_hash / row_hash existed
        conn.execute("INSERT INTO audit_log (user_id, action, patient_id, detail, created_at) VALUES (?, ?, ?, ?, ?)",
                     (1, "view_timeline", "p1", None, f"2026-11-01 10:0{i}:00"))


def test_old_rows_before_the_chain_are_counted_not_checked():
    def fill():
        with get_conn() as conn:
            _legacy(conn, 3)
            for _ in range(4):
                append_audit(conn, 1, "view_timeline", "p1")
    result = _with_log(fill)
    assert result["intact"] and result["before_chain"] == 3 and result["chained"] == 4 and result["entries"] == 7


def test_editing_a_chained_row_still_breaks_it():
    def fill():
        with get_conn() as conn:
            _legacy(conn, 2)
            for _ in range(3):
                append_audit(conn, 1, "view_timeline", "p1")
            second = conn.execute("SELECT id FROM audit_log WHERE row_hash IS NOT NULL ORDER BY id LIMIT 1 OFFSET 1").fetchone()[0]
            conn.execute("UPDATE audit_log SET action = 'login' WHERE id = ?", (second,))
    result = _with_log(fill)
    assert not result["intact"] and result["reason"] == "this row's contents were changed"


def test_a_row_without_hashes_after_the_chain_started_breaks_it():
    def fill():
        with get_conn() as conn:
            for _ in range(2):
                append_audit(conn, 1, "view_timeline", "p1")
            _legacy(conn, 1)  # slipped in later, with no hashes
            append_audit(conn, 1, "view_timeline", "p1")
    result = _with_log(fill)
    assert not result["intact"] and result["before_chain"] == 0
