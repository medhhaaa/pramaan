"""Time-limited sharing by QR code or typed code. (Core backend)

The patient makes a share; a doctor at another clinic scans the QR or types the code and can
READ that patient's records until the time runs out. Then access closes by itself and the
share is deleted. The patient can also stop a share early.

POST   /patients/{id}/share   {"minutes": 15, "scope": "all" | ["diabetes", "other"]}   (patient only)
       -> {"share_id", "code", "token", "url", "qr_svg", "expires_at", "seconds_left", "scope"}
          scope  what the doctor may see (backend/scope.py); allergies and blood group / sex /
                 DOB are always shown. GET /patients/{id}/share-options lists the groups.
          code   8 letters/digits shown as "K7P3-QXM9" for typing (no 0/O or 1/I/L mix-ups)
          token  long random string inside the QR link
          qr_svg data URI of the QR picture, use it directly as <img src>
POST   /share/open            {"code": "K7P3-QXM9"} or {"token": "..."}   (doctor only)
       -> {"share_id", "patient": {id, name, dob, sex, blood_group}, "expires_at", "seconds_left"}
GET    /patients/{id}/shares  -> active shares: [{"share_id", "created_at", "expires_at",
                                  "seconds_left", "opened_by", "opened_at", "scope"}]
DELETE /share/{share_id}      -> {"stopped": true}   (the patient stops sharing early)

Safety:
- Only SHA-256 hashes of the token and code are stored, never the values themselves.
- Doctor login is required to open a share; a share works for the first doctor who opens it.
- 5 wrong codes in 10 minutes -> 429 (stops guessing). Every step goes to the audit log.
- Shared access is read-only (enforced in auth.require_patient_access).
- Expired shares are deleted on every share request; access checks ignore them anyway.
"""
import hashlib
import os
import secrets
from datetime import datetime, timezone
from typing import List, Literal, Union

import segno
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth import get_current_user, has_full_access
from backend.db import get_conn, log_action
from backend.scope import SCOPE_NAMES, parse_scope, scope_text

router = APIRouter()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L: easy to read aloud
MAX_MINUTES = 60
MAX_WRONG_CODES = 5


def _hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _clean_code(code):
    """'k7p3-qxm9 ' -> 'K7P3QXM9' so typing mistakes in case/spaces/dashes don't matter."""
    return "".join(ch for ch in code.upper() if ch.isalnum())


def _iso(sqlite_time):
    """SQLite UTC '2026-11-12 18:30:00' -> '2026-11-12T18:30:00Z' for the browser."""
    return sqlite_time.replace(" ", "T") + "Z" if sqlite_time else None


def _seconds_left(sqlite_time):
    expires = datetime.strptime(sqlite_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return max(0, int((expires - datetime.now(timezone.utc)).total_seconds()))


def _delete_expired(conn):
    conn.execute("DELETE FROM share_links WHERE expires_at <= datetime('now')")
    conn.execute("DELETE FROM share_requests WHERE share_id NOT IN (SELECT id FROM share_links)")


def check_scope(scope):
    """"all", or a non-empty list of known groups (sorted, no repeats) -> 422 otherwise."""
    if scope == "all":
        return "all"
    scope = sorted(set(scope))
    if not scope or any(t not in SCOPE_NAMES for t in scope):
        raise HTTPException(status_code=422, detail=f"Scope must be 'all' or groups from {SCOPE_NAMES}")
    return scope


class ShareBody(BaseModel):
    minutes: int = 15
    scope: Union[Literal["all"], List[str]] = "all"


@router.post("/patients/{patient_id}/share")
def create_share(patient_id: str, body: ShareBody, user=Depends(get_current_user)):
    if user["role"] != "patient":
        raise HTTPException(status_code=403, detail="Only the patient can share their records")
    if not 1 <= body.minutes <= MAX_MINUTES:
        raise HTTPException(status_code=422, detail=f"Minutes must be between 1 and {MAX_MINUTES}")
    scope = check_scope(body.scope)

    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    token = secrets.token_urlsafe(24)
    with get_conn() as conn:
        if not has_full_access(conn, user, patient_id):
            raise HTTPException(status_code=403, detail="No access to this patient")
        _delete_expired(conn)
        cur = conn.execute(
            """INSERT INTO share_links (patient_id, created_by, token_hash, code_hash, expires_at, scope)
               VALUES (?, ?, ?, ?, datetime('now', ?), ?)""",
            (patient_id, user["id"], _hash(token), _hash(code), f"+{body.minutes} minutes", scope_text(scope)),
        )
        expires_at = conn.execute(
            "SELECT expires_at FROM share_links WHERE id = ?", (cur.lastrowid,)
        ).fetchone()["expires_at"]

    url = f"{FRONTEND_URL}/?share={token}"
    log_action(user, "share_created", patient_id, {"share_id": cur.lastrowid, "minutes": body.minutes, "scope": scope})
    return {
        "share_id": cur.lastrowid,
        "code": f"{code[:4]}-{code[4:]}",
        "token": token,
        "url": url,
        "qr_svg": segno.make(url, error="m").svg_data_uri(scale=6, border=2),
        "expires_at": _iso(expires_at),
        "seconds_left": _seconds_left(expires_at),
        "scope": scope,
    }


class OpenBody(BaseModel):
    code: str | None = None
    token: str | None = None


@router.post("/share/open")
def open_share(body: OpenBody, user=Depends(get_current_user)):
    if user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="Only a doctor can open a shared record")
    if body.token:
        column, value = "token_hash", _hash(body.token.strip())
    elif body.code and _clean_code(body.code):
        column, value = "code_hash", _hash(_clean_code(body.code))
    else:
        raise HTTPException(status_code=422, detail="Scan the QR code or type the code")

    with get_conn() as conn:
        wrong = conn.execute(
            """SELECT COUNT(*) FROM audit_log WHERE user_id = ? AND action = 'share_open_failed'
               AND created_at > datetime('now', '-10 minutes')""",
            (user["id"],),
        ).fetchone()[0]
        if wrong >= MAX_WRONG_CODES:
            raise HTTPException(status_code=429, detail="Too many wrong codes. Try again in 10 minutes.")

        _delete_expired(conn)
        share = conn.execute(f"SELECT * FROM share_links WHERE {column} = ?", (value,)).fetchone()
        if share and share["opened_by"] not in (None, user["id"]):
            share = None  # already used by another doctor: treat it like a wrong code
        if share:
            conn.execute(
                "UPDATE share_links SET opened_by = ?, opened_at = COALESCE(opened_at, datetime('now')) WHERE id = ?",
                (user["id"], share["id"]),
            )
            patient = conn.execute("SELECT * FROM patients WHERE id = ?", (share["patient_id"],)).fetchone()

    if not share:
        log_action(user, "share_open_failed", None, {"by": "token" if body.token else "code"})
        raise HTTPException(status_code=404, detail="This code is wrong, expired or already used")

    log_action(user, "share_opened", share["patient_id"], {"share_id": share["id"]})
    return {
        "share_id": share["id"],
        "patient": dict(patient),
        "expires_at": _iso(share["expires_at"]),
        "seconds_left": _seconds_left(share["expires_at"]),
    }


@router.get("/patients/{patient_id}/shares")
def list_shares(patient_id: str, user=Depends(get_current_user)):
    with get_conn() as conn:
        if not has_full_access(conn, user, patient_id):
            raise HTTPException(status_code=403, detail="No access to this patient")
        _delete_expired(conn)
        rows = conn.execute(
            """SELECT s.*, u.username AS opened_by_name FROM share_links s
               LEFT JOIN users u ON u.id = s.opened_by
               WHERE s.patient_id = ? ORDER BY s.created_at DESC""",
            (patient_id,),
        ).fetchall()
    return [
        {
            "share_id": r["id"],
            "created_at": _iso(r["created_at"]),
            "expires_at": _iso(r["expires_at"]),
            "seconds_left": _seconds_left(r["expires_at"]),
            "opened_by": r["opened_by_name"],
            "opened_at": _iso(r["opened_at"]),
            "scope": parse_scope(r["scope"]),
        }
        for r in rows
    ]


@router.delete("/share/{share_id}")
def stop_share(share_id: int, user=Depends(get_current_user)):
    with get_conn() as conn:
        share = conn.execute("SELECT * FROM share_links WHERE id = ?", (share_id,)).fetchone()
        if not share or not has_full_access(conn, user, share["patient_id"]):
            raise HTTPException(status_code=404, detail="Share not found")
        conn.execute("DELETE FROM share_links WHERE id = ?", (share_id,))
        conn.execute("DELETE FROM share_requests WHERE share_id = ?", (share_id,))
    log_action(user, "share_stopped", share["patient_id"], {"share_id": share_id})
    return {"stopped": True}
