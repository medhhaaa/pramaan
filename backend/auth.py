"""Login, passwords and per-patient access. (Core backend)

POST /login  {"username", "password"} -> {"token", "role", "username", "language"}
             language is "en", "kn", "hi", or null (not chosen yet: the frontend asks once)

In any route:
    user = Depends(get_current_user)        -> {"id", "username", "role"} or 401
    require_patient_access(user, patient_id) -> 403 if this user can't see the patient, else
        {"kind": "own" | "shared" | "care_team", "scope": "all" | ["diabetes", ...]}
        Routes that return facts filter them with backend.scope.scoped(facts, access).

Three kinds of access:
  own        the PATIENT's own account (linked in user_patients). Only patients get this:
             a doctor never gets it, even if a user_patients row links them.
  care_team  a doctor the patient added to their care team (backend/routes/care_team.py),
             while that entry is active. Scope "all" or a list of condition tags: facts
             outside the scope are hidden (backend/scope.py). Reading, the review actions
             below, and the doctor's own actions (prescribe, decide a refill, set a follow-up).
  shared     the patient made a QR / code and the doctor opened it (backend/routes/share.py).
             Only until the share expires; scope "all". GET requests plus the review actions
             below. If a doctor has both, the share (wider scope) wins.
Nobody but the patient can upload, delete, share or use claims.
"""
import hashlib
import os
import secrets
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Literal, Optional

from pydantic import BaseModel, Field

from backend.db import get_conn

JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me-in-dotenv-file")
TOKEN_HOURS = 12

router = APIRouter()
bearer = HTTPBearer()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return f"{salt}${digest.hex()}"


def verify_password(password, stored):
    salt, _ = stored.split("$", 1)
    return secrets.compare_digest(hash_password(password, salt), stored)


def create_token(user):
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"id": int(payload["sub"]), "username": payload["username"], "role": payload["role"]}


# POST routes that only read records, so a shared (read-only) doctor may use them
# what a doctor may do during a share besides reading: questions to the records, and the
# review work (correct a fact, resolve an open question). Nothing that adds or deletes data.
SHARED_POSTS = ("/ask", "/check-medicine", "/correct", "/answer")
# what a care-team doctor may also do: write a prescription, decide a refill, set a follow-up,
# correct their own consult record (as a new record)
CARE_TEAM_POSTS = SHARED_POSTS + ("/prescriptions", "/decision", "/follow-up", "/corrections")

# method + path of the request being handled, saved by remember_request (main.py runs it
# for every request) so require_patient_access knows whether the route reads or writes
current_request = ContextVar("current_request", default=("GET", ""))


async def remember_request(request: Request):
    current_request.set((request.method, request.url.path))


def has_full_access(conn, user, patient_id):
    """Lasting access: only the patient's own account. Doctors only ever get shared access."""
    if user["role"] != "patient":
        return False
    return conn.execute(
        "SELECT 1 FROM user_patients WHERE user_id = ? AND patient_id = ?",
        (user["id"], patient_id),
    ).fetchone() is not None


def active_share(conn, user, patient_id):
    """The share this doctor opened for this patient, if it hasn't expired."""
    return conn.execute(
        """SELECT * FROM share_links WHERE opened_by = ? AND patient_id = ?
           AND expires_at > datetime('now') ORDER BY expires_at DESC""",
        (user["id"], patient_id),
    ).fetchone()


def active_care_team(conn, user, patient_id):
    """This doctor's active care-team entry for this patient, if any."""
    if user["role"] != "doctor":
        return None
    return conn.execute(
        "SELECT * FROM care_team WHERE doctor_id = ? AND patient_id = ? AND status = 'active'",
        (user["id"], patient_id),
    ).fetchone()


def require_patient_access(user, patient_id):
    from backend.scope import parse_scope  # plain helper module; imported here to keep auth light

    with get_conn() as conn:
        if has_full_access(conn, user, patient_id):
            return {"kind": "own", "scope": "all"}
        share = active_share(conn, user, patient_id)
        team = None if share else active_care_team(conn, user, patient_id)
    if not share and not team:
        raise HTTPException(status_code=403, detail="No access to this patient")
    method, path = current_request.get()
    allowed = SHARED_POSTS if share else CARE_TEAM_POSTS
    if method != "GET" and not path.rstrip("/").endswith(allowed):
        raise HTTPException(status_code=403, detail="Doctors may only read and review here")
    if share:
        return {"kind": "shared", "scope": "all"}
    return {"kind": "care_team", "scope": parse_scope(team["scope"]), "care_team_id": team["id"]}


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginBody):
    with get_conn() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (body.username,)
        ).fetchone()
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Wrong username or password")
    return {
        "token": create_token(user),
        "role": user["role"],
        "username": user["username"],
        "language": user["language"],
    }


# ---------- sign-up (Medha) ----------
# Adds a new account next to the demo ones (nothing is deleted). A new patient gets an EMPTY
# record of their own (no documents, no facts) and lasting access to it. A new doctor sees
# nobody until a patient adds them to a care team or opens a QR share.
# New patient ids start at p101 so they never clash with demo patients (p1-p8, or later ones).

FIRST_SIGNUP_PATIENT = 101


class SignupBody(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9._-]{3,30}$")
    password: str = Field(min_length=6, max_length=128)
    role: Literal["patient", "doctor"] = "patient"
    full_name: str = Field(min_length=2, max_length=80)
    registration_number: Optional[str] = Field(default=None, max_length=40)


def next_patient_id(conn):
    taken = [int(r["id"][1:]) for r in conn.execute("SELECT id FROM patients") if r["id"][1:].isdigit()]
    return f"p{max([FIRST_SIGNUP_PATIENT - 1, *taken]) + 1}"


@router.post("/signup")
def signup(body: SignupBody):
    username, full_name = body.username.strip(), body.full_name.strip()
    reg = (body.registration_number or "").strip() or None
    if body.role == "doctor" and not reg:
        raise HTTPException(status_code=422, detail="A doctor needs a registration number")
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM users WHERE lower(username) = lower(?)", (username,)).fetchone():
            raise HTTPException(status_code=409, detail="This username is taken")
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role, full_name, registration_number) VALUES (?, ?, ?, ?, ?)",
            (username, hash_password(body.password), body.role, full_name, reg if body.role == "doctor" else None),
        )
        user_id = cur.lastrowid
        if body.role == "patient":
            patient_id = next_patient_id(conn)
            conn.execute("INSERT INTO patients (id, name, dob, sex, blood_group) VALUES (?, ?, NULL, NULL, NULL)",
                         (patient_id, full_name))
            conn.execute("INSERT INTO user_patients (user_id, patient_id) VALUES (?, ?)", (user_id, patient_id))
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.execute("INSERT INTO audit_log (user_id, action, patient_id, detail) VALUES (?, 'signup', ?, ?)",
                     (user_id, patient_id if body.role == "patient" else None, body.role))
    return {"token": create_token(user), "role": user["role"], "username": user["username"], "language": None}
