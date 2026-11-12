"""pytest setup: every test run uses a throwaway database and storage folder, never the real
backend/pramaan.db or storage/. Run from the repo root:  python -m pytest
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMP = tempfile.mkdtemp(prefix="pramaan_tests_")
os.environ["DB_PATH"] = os.path.join(TMP, "test.db")  # read when backend.db is imported
if not os.getenv("FILE_ENCRYPTION_KEY"):
    from cryptography.fernet import Fernet

    os.environ["FILE_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from backend import seed, storage  # noqa: E402

# seed() deletes ROOT/storage and storage.py writes under ROOT: point both at the temp folder
seed.ROOT = TMP
storage.ROOT = TMP
