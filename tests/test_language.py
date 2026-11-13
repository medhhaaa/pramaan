"""Each user's language (backend/routes/language.py): null until the first login's popup saves it."""
import pytest
from fastapi.testclient import TestClient

from backend import seed


@pytest.fixture(scope="module")
def client():
    import os
    from backend.db import DB_PATH, get_conn
    # Windows can't replace the database file while an earlier test module still has it open
    if not os.path.exists(DB_PATH):
        seed.seed(with_sample_facts=False)
    with get_conn() as conn:
        conn.execute("UPDATE users SET language = NULL")
    from backend.main import app
    return TestClient(app)


def login(client, username, password):
    return client.post("/login", json={"username": username, "password": password}).json()


def test_language_is_null_until_chosen_then_returned_at_login(client):
    first = login(client, "sunita", "sunita123")
    assert first["language"] is None  # the frontend shows the popup after this login
    headers = {"Authorization": "Bearer " + first["token"]}
    assert client.put("/me/language", json={"language": "kn"}, headers=headers).json() == {"language": "kn"}
    assert login(client, "sunita", "sunita123")["language"] == "kn"


def test_hindi_is_saved_and_backend_text_falls_back_to_english(client):
    from backend.routes.language import user_language
    from backend.db import get_conn
    data = login(client, "doctor", "doctor123")
    headers = {"Authorization": "Bearer " + data["token"]}
    assert client.put("/me/language", json={"language": "hi"}, headers=headers).status_code == 200
    assert login(client, "doctor", "doctor123")["language"] == "hi"
    with get_conn() as conn:
        uid = conn.execute("SELECT id FROM users WHERE username = 'doctor'").fetchone()["id"]
    assert user_language({"id": uid}) == "en"


def test_unknown_language_is_refused(client):
    headers = {"Authorization": "Bearer " + login(client, "sunita", "sunita123")["token"]}
    assert client.put("/me/language", json={"language": "fr"}, headers=headers).status_code == 422
