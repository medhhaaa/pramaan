"""Encrypted file storage. (Core backend)

Uploaded PDFs are encrypted with Fernet (key FILE_ENCRYPTION_KEY in .env) before they
touch the disk. Paths in the documents table are relative to the repo root.

save_encrypted(data, rel_path)   write bytes, encrypted
read_file(rel_path) -> bytes     decrypts files ending in .enc, reads others as-is
                                 (the synthetic demo PDFs in data/ are plain)
temp_copy(rel_path) -> path      decrypted copy in a temp file, for tools that need a path.
                                 Delete it with os.remove() when done.
"""
import os
import tempfile

from cryptography.fernet import Fernet

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fernet():
    key = os.getenv("FILE_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("FILE_ENCRYPTION_KEY is missing from .env (see .env.example)")
    return Fernet(key.encode())


def abs_path(rel_path):
    return os.path.join(ROOT, rel_path)


def save_encrypted(data, rel_path):
    path = abs_path(rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(_fernet().encrypt(data))


def read_file(rel_path):
    with open(abs_path(rel_path), "rb") as f:
        data = f.read()
    return _fernet().decrypt(data) if rel_path.endswith(".enc") else data


def temp_copy(rel_path):
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, "wb") as f:
        f.write(read_file(rel_path))
    return tmp


def delete_file(rel_path):
    path = abs_path(rel_path)
    if os.path.exists(path):
        os.remove(path)
