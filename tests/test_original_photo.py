"""A photographed prescription keeps its original photo for Source (pipeline/original_image.py,
backend/ingest.py, GET /documents/{id}, GET /documents/{id}/original). Synthetic images only;
OCR and the AI are replaced: the photo's PDF gets a known invisible text line, and the saved
pipeline output stands in for extraction."""
import gc
import io
import json
import os

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageOps

from backend import seed, storage
from backend.db import get_conn
from backend.ingest import ingest_document
from pipeline.ocr import _add_invisible_line, image_to_pdf
from pipeline.original_image import original_image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVED = {d["document_id"]: d for d in
         json.load(open(os.path.join(ROOT, "data", "extracted", "p1.json"), encoding="utf-8"))["documents"]}
LINE = "Tab Metformin 500mg BD"
LINE_AT = (0.10, 0.40, 0.70, 0.46)  # where the line is written, as fractions of the page


def phone_photo(orientation=6):
    """A synthetic phone JPEG with the metadata a phone writes: make, model, time, GPS, rotation."""
    img = Image.new("RGB", (600, 800), "white")
    for x in range(60, 420):  # something to look at: a dark stroke
        for y in range(320, 330):
            img.putpixel((x, y), (20, 20, 60))
    exif = Image.Exif()
    exif[0x010F] = "PhoneCo"           # Make
    exif[0x0110] = "Pixel 7"           # Model
    exif[0x0132] = "2026:11:13 09:30:00"
    exif[0x0112] = orientation
    exif.get_ifd(0x8825).update({1: "N", 2: (12.0, 52.0, 30.0), 3: "E", 4: (74.0, 51.0, 10.0)})  # GPS
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=88, exif=exif)
    return out.getvalue()


def searchable_pdf(image_bytes):
    """What prepare_document makes of a photo, with one known line read from it (no OCR here)."""
    doc = pymupdf.open(stream=image_to_pdf(image_bytes), filetype="pdf")
    page = doc[0]
    w, h = page.rect.width, page.rect.height
    x0, y0, x1, y1 = LINE_AT
    _add_invisible_line(page, LINE, pymupdf.Rect(x0 * w, y0 * h, x1 * w, y1 * h))
    return doc.tobytes()


# ---------- the photo itself ----------

def test_metadata_is_removed_but_the_picture_and_rotation_stay():
    data = phone_photo()
    kept, mime = original_image(data)
    assert mime == "image/jpeg"
    for secret in (b"PhoneCo", b"Pixel 7", b"2026:11:13"):
        assert secret in data and secret not in kept
    exif = Image.open(io.BytesIO(kept)).getexif()
    assert dict(exif) == {0x0112: 6}                       # only the rotation is left
    assert not exif.get_ifd(0x8825)                        # no GPS
    # the compressed image data is copied, not re-saved: identical pixels
    assert Image.open(io.BytesIO(kept)).tobytes() == Image.open(io.BytesIO(data)).tobytes()
    # and it still shows upright, the same way as the PDF page made from it
    assert ImageOps.exif_transpose(Image.open(io.BytesIO(kept))).size == (800, 600)


def test_png_loses_its_text_chunks_and_a_pdf_has_no_separate_original():
    from PIL import PngImagePlugin

    info = PngImagePlugin.PngInfo()
    info.add_text("Author", "Owner Name")
    img = Image.new("RGB", (40, 30), (200, 10, 10))
    out = io.BytesIO()
    img.save(out, format="PNG", pnginfo=info)
    kept, mime = original_image(out.getvalue())
    assert mime == "image/png" and b"Owner Name" not in kept
    assert Image.open(io.BytesIO(kept)).tobytes() == img.tobytes()
    with open(os.path.join(ROOT, "data", "patients", "p1", "d1_prescription_2019.pdf"), "rb") as f:
        assert original_image(f.read()) is None
    assert original_image(b"not an image") is None


# ---------- upload, Source and the photo route ----------

@pytest.fixture(scope="module")
def client():
    gc.collect()  # earlier test files leave sqlite connections open; Windows then can't reseed
    seed.seed(with_sample_facts=False)
    from backend.main import app
    return TestClient(app)


def login(client, username):
    token = client.post("/login", json={"username": username, "password": username + "123"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def uploaded(client):
    """Sunita uploads a photo of a prescription through the real route."""
    from backend.routes import upload as upload_route

    mp = pytest.MonkeyPatch()
    mp.setattr(upload_route, "prepare_document", searchable_pdf)
    mp.setattr(upload_route, "_ingest_one", lambda pid, name, data, doc_type, original=None: ingest_document(
        pid, name, data, doc_type, saved=SAVED["p1_d1"], original=original))
    photo = phone_photo()
    r = client.post("/patients/p1/upload", headers=login(client, "sunita"),
                    files={"file": ("prescription.jpg", photo, "image/jpeg")})
    mp.undo()
    assert r.status_code == 200, r.text
    return {"id": r.json()["document_id"], "photo": photo}


def test_the_original_photo_is_stored_encrypted(client, uploaded):
    with get_conn() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (uploaded["id"],)).fetchone()
    assert doc["original_mime"] == "image/jpeg"
    assert doc["original_path"] == f"storage/p1/{uploaded['id']}.original.jpg.enc"
    raw = open(storage.abs_path(doc["original_path"]), "rb").read()
    assert not raw.startswith(b"\xff\xd8") and b"PhoneCo" not in raw     # encrypted on disk
    assert storage.read_file(doc["original_path"]) == original_image(uploaded["photo"])[0]


def test_source_has_the_photo_and_marks_the_line_on_it(client, uploaded):
    body = client.get(f"/documents/{uploaded['id']}", headers=login(client, "sunita")).json()
    assert body["original"] == {"mime": "image/jpeg"}
    line = next(l for l in body["lines"] if l["text"] == LINE)
    x0, y0, x1, y1 = line["box"]
    assert abs(x0 - LINE_AT[0]) < 0.02 and abs(y0 - LINE_AT[1]) < 0.03 and x1 > x0 and y1 > y0
    assert y1 <= LINE_AT[3] + 0.03


def test_the_photo_route_returns_the_cleaned_photo_and_is_audited(client, uploaded):
    r = client.get(f"/documents/{uploaded['id']}/original", headers=login(client, "sunita"))
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg" and r.headers["cache-control"] == "no-store"
    assert r.content == original_image(uploaded["photo"])[0] and b"Pixel 7" not in r.content
    with get_conn() as conn:
        row = conn.execute("SELECT detail FROM audit_log WHERE action = 'view_original_photo' ORDER BY id DESC").fetchone()
    assert row and uploaded["id"] in row["detail"]


def test_other_people_cannot_see_the_photo(client, uploaded):
    assert client.get(f"/documents/{uploaded['id']}/original", headers=login(client, "iqbal")).status_code == 403
    # a doctor without an open share neither
    assert client.get(f"/documents/{uploaded['id']}/original", headers=login(client, "doctor")).status_code == 403


def test_a_doctor_with_an_open_share_can_check_the_photo(client, uploaded):
    share = client.post("/patients/p1/share", json={"minutes": 30, "scope": "all"},
                        headers=login(client, "sunita")).json()
    doctor = login(client, "doctor")
    assert client.post("/share/open", json={"code": share["code"]}, headers=doctor).status_code == 200
    r = client.get(f"/documents/{uploaded['id']}/original", headers=doctor)
    assert r.status_code == 200 and r.content == original_image(uploaded["photo"])[0]


def test_a_pdf_upload_has_no_photo(client, uploaded):
    pdf_doc = ingest_document("p1", "d2_lab_2021.pdf",
                              open(os.path.join(ROOT, "data", "patients", "p1", "d2_lab_2021.pdf"), "rb").read(),
                              saved=SAVED["p1_d2"])
    sunita = login(client, "sunita")
    body = client.get(f"/documents/{pdf_doc['document_id']}", headers=sunita).json()
    assert body["original"] is None and all("box" not in l for l in body["lines"])
    assert client.get(f"/documents/{pdf_doc['document_id']}/original", headers=sunita).status_code == 404


def test_delete_my_data_removes_the_photo_too(client, uploaded):
    with get_conn() as conn:
        path = conn.execute("SELECT original_path FROM documents WHERE id = ?", (uploaded["id"],)).fetchone()[0]
    assert os.path.exists(storage.abs_path(path))
    assert client.delete("/patients/p1", headers=login(client, "sunita")).status_code == 200
    assert not os.path.exists(storage.abs_path(path))
