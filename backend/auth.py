"""Login, passwords and per-patient access. (Core backend)

POST /login  {"username", "password"} -> {"token", "role", "username"}

In any route:
    user = Depends(get_current_user)        -> {"id", "username", "role"} or 401
    require_patient_access(user, patient_id) -> 403 if this user can't see the patient

Two kinds of access:
  full    the user is linked to the patient in user_patients (their own doctor, the patient)
  shared  a doctor opened the patient's QR / code (backend/routes/share.py). Read-only and
          only until the share expires: GET requests plus the read-only POSTs below.
          Anything that changes data (correct, upload, answer, delete) gets 403.
"""
import hashlib
import os
import secrets
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

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
READ_ONLY_POSTS = ("/ask", "/check-medicine")

# method + path of the request being handled, saved by remember_request (main.py runs it
# for every request) so require_patient_access knows whether the route reads or writes
current_request = ContextVar("current_request", default=("GET", ""))


async def remember_request(request: Request):
    current_request.set((request.method, request.url.path))


def has_full_access(conn, user, patient_id):
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


def require_patient_access(user, patient_id):
    with get_conn() as conn:
        if has_full_access(conn, user, patient_id):
            return
        share = active_share(conn, user, patient_id)
    if not share:
        raise HTTPException(status_code=403, detail="No access to this patient")
    method, path = current_request.get()
    if method != "GET" and not path.endswith(READ_ONLY_POSTS):
        raise HTTPException(status_code=403, detail="Shared access is read-only")


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
    return {"token": create_token(user), "role": user["role"], "username": user["username"]}
