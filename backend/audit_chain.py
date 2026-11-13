"""Check (and, for the demo, deliberately break) the tamper-evident audit log. (Core backend)

    python -m backend.audit_chain verify     recompute every hash: intact, or the first broken row
    python -m backend.audit_chain tamper     DEMO: quietly edit one old row, like someone hiding
                                             that they opened a record. The scorecard turns red.
    python -m backend.audit_chain untamper   put that row back exactly as it was

How the chain works: backend/db.py (append_audit / verify_audit_chain).
"""
import json
import os
import sys

from backend.db import DB_PATH, get_conn, verify_audit_chain

BACKUP = os.path.join(os.path.dirname(DB_PATH), ".audit_tamper_backup.json")


def tamper():
    with get_conn() as conn:
        rows = conn.execute("SELECT id, action, detail FROM audit_log ORDER BY id").fetchall()
        if len(rows) < 3:
            sys.exit("Need at least 3 audit entries: use the app a little first.")
        row = rows[len(rows) // 2]  # one in the middle, so many rows after it depend on it
        json.dump({"id": row["id"], "action": row["action"], "detail": row["detail"]}, open(BACKUP, "w"))
        conn.execute("UPDATE audit_log SET action = 'login', detail = NULL WHERE id = ?", (row["id"],))
    print(f"Changed audit entry #{row['id']} (was '{row['action']}', now looks like a harmless 'login').")


def untamper():
    if not os.path.exists(BACKUP):
        sys.exit("Nothing to undo.")
    saved = json.load(open(BACKUP))
    with get_conn() as conn:
        conn.execute("UPDATE audit_log SET action = ?, detail = ? WHERE id = ?",
                     (saved["action"], saved["detail"], saved["id"]))
    os.remove(BACKUP)
    print(f"Audit entry #{saved['id']} restored.")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if command == "tamper":
        tamper()
    elif command == "untamper":
        untamper()
    result = verify_audit_chain()
    if result["intact"]:
        print(f"Audit chain intact: {result['entries']} entries. Latest hash {result['latest_hash'][:16]}...")
    else:
        print(f"Audit chain BROKEN at entry #{result['broken_at']}: {result['reason']}.")
