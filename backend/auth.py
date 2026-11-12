"""Login, passwords and per-patient access. (Core backend)

POST /login  {"username", "password"} -> {"token", "role", "username", "language"}
             language is "en", "kn", or null (not chosen yet: the frontend asks once)

In any route:
    user = Depends(get_current_user)        -> {"id", "username", "role"} or 401
    require_patient_access(user, patient_id) -> 403 if this user can't see the patient
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
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


def require_patient_access(user, patient_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM user_patients WHERE user_id = ? AND patient_id = ?",
            (user["id"], patient_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="No access to this patient")


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
