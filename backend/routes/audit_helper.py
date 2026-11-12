"""log_action() for Medha's routes. (Medha)

KICKOFF.md says the core backend adds backend.db.log_action(user, action, patient_id, detail).
Until that exists, this writes the same audit_log row itself, so the audit screen works now.
Once db.log_action exists it is used automatically and this fallback is never called.
"""
try:
    from backend.db import log_action  # noqa: F401
except ImportError:
    from backend.db import get_conn

    def log_action(user, action, patient_id, detail=""):
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO audit_log (user_id, action, patient_id, detail) VALUES (?, ?, ?, ?)",
                (user["id"] if user else None, action, patient_id, detail),
            )
