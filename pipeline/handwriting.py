"""Read handwriting with a vision AI model that runs on our own machine (Ollama). (Ashil)

Tesseract reads print well but not doctors' handwriting. When Tesseract is unsure about a
page (needs_vision), a LOCAL vision model (Qwen2.5-VL by default) copies the page's text
line by line. It must be local: a handwritten page cannot be de-identified before it is
read (the patient's name is handwritten inside the picture), so the image never leaves
this machine. Only the transcribed text goes on, through de-identification, as usual.

Tesseract still tells us WHERE the text lines are, even when it can't read them. Each
transcribed line is matched to a Tesseract line (place_lines), so click-to-proof can
highlight it on the page.

Facts from such pages get the flag "handwriting" (pipeline/process.py): the transcription
itself was made by an AI, so a person must check those facts against the image.

Cloud option (faster, much better at handwriting): set VISION_MODEL in .env (e.g. qwen-vl on
free.ai). Before a page leaves this machine, mask_personal() blacks out the patient's name,
UHID, phone and address (found by Tesseract next to labels like "Patient:" or "Mobile:"), the
letterhead and the doctor's signature line. If no such label is found, the page is NOT sent:
it falls back to the local model, or to plain Tesseract.

Detection: a page counts as handwritten (mixed pages too) when at least 4.5% of its words have
Tesseract confidence below 80. Measured on our test pages: handwritten 5-42%, clean printed
scans 0-4%; a blurry photo of print may also go to the model, which reads print fine.

tesseract_lines(page) -> [{"text", "rect", "confs"}]      where Tesseract found text lines
needs_vision(lines) -> bool                                Tesseract unsure -> use the model
vision_available() -> bool                                 is the model installed in Ollama?
mask_personal(page, lines) -> png bytes | None             page with personal details blacked out
transcribe(page, lines) -> [str] | None                    the model's line-by-line copy (None: no
                                                           model can safely read it)
place_lines(texts, lines) -> [{"text", "rect"}]            each copied line with a position

Settings (.env): VISION_MODEL (cloud, optional), HANDWRITING_MODEL (local, default
qwen2.5vl:7b), OLLAMA_URL, HANDWRITING=off
"""
import base64
import csv
import io
import os
import re
import shutil
import subprocess
import tempfile

import pymupdf
import requests
from rapidfuzz import fuzz

from pipeline import llm

TESS_DPI = 300
VISION_WIDTH_PX = 1000          # page width sent to the model: handwriting still readable, much faster
UNSURE_CONFIDENCE = 80          # a word Tesseract is unsure about
HANDWRITTEN_SHARE = 0.045       # handwritten pages: 5-42% unsure words; clean printed scans: 0-4%
MIN_MATCH = 35                  # rapidfuzz score to trust a line position

PROMPT = """You are copying a medical document that may be handwritten.
Write out ALL of its text exactly as written, top to bottom, one line of the document per line of output.
Rules:
- Copy spelling, numbers, units, doses and abbreviations exactly. Do not correct, expand or translate anything.
- If a word cannot be read, write [?] in its place. Never guess a medicine name or a number.
- Output only the copied text, nothing else."""


# Windows: the installer doesn't always put Tesseract on PATH
TESSERACT = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def _model():
    return os.getenv("HANDWRITING_MODEL", "qwen2.5vl:7b")


def _ollama_url():
    return os.getenv("OLLAMA_URL", "http://localhost:11434")


def tesseract_lines(page):
    """Tesseract's text lines with positions (PDF points) and word confidences."""
    png = os.path.join(tempfile.gettempdir(), f"pramaan_tess_{os.getpid()}.png")
    page.get_pixmap(dpi=TESS_DPI).save(png)
    try:
        tsv = subprocess.run([TESSERACT, png, "stdout", "tsv"], capture_output=True, text=True,
                             check=True).stdout
    finally:
        os.remove(png)

    scale = 72 / TESS_DPI
    lines = {}
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t"):
        key = (row["block_num"], row["par_num"], row["line_num"])
        left, top = int(row["left"]) * scale, int(row["top"]) * scale
        right, bottom = left + int(row["width"]) * scale, top + int(row["height"]) * scale
        if row["level"] == "4":  # a line: its box
            lines[key] = {"rect": pymupdf.Rect(left, top, right, bottom), "words": [], "confs": [],
                          "boxes": []}
        elif row["level"] == "5" and key in lines and row["text"].strip():  # a word on that line
            lines[key]["words"].append(row["text"])
            lines[key]["confs"].append(float(row["conf"]))
            lines[key]["boxes"].append(pymupdf.Rect(left, top, right, bottom))
    result = [{"text": " ".join(l["words"]), "rect": l["rect"], "confs": l["confs"], "words": l["words"],
               "boxes": l["boxes"]}
              for l in lines.values() if l["words"]]
    return sorted(result, key=lambda l: (round(l["rect"].y0), l["rect"].x0))


def needs_vision(lines):
    confs = [c for line in lines for word, c in zip(line["text"].split(), line["confs"])
             if sum(ch.isalnum() for ch in word) >= 2]
    if not confs:
        return True  # Tesseract found no words at all
    unsure = sum(c < UNSURE_CONFIDENCE for c in confs) / len(confs)
    return unsure >= HANDWRITTEN_SHARE


def enabled():
    """HANDWRITING=off in .env: scanned pages go straight to plain Tesseract OCR."""
    return os.getenv("HANDWRITING", "on").lower() != "off"


def vision_available():
    if not enabled():
        return False
    try:
        models = requests.get(_ollama_url() + "/api/tags", timeout=3).json()["models"]
    except (requests.RequestException, ValueError, KeyError):
        return False
    return any(m["name"] == _model() for m in models)


# labels whose VALUE identifies the patient: blacked out before a page goes to a cloud model
PERSONAL_LABELS = {"patient", "name", "pt", "uhid", "mrn", "reg", "ip", "op", "mobile", "mob",
                   "phone", "ph", "tel", "contact", "address", "addr", "aadhaar", "aadhar", "abha"}
# other labels: the blacked-out area stops here ("Patient: Sunita Rao   Date: 12/03/2019")
OTHER_LABELS = {"date", "sex", "gender", "dob", "age", "blood", "diagnosis", "rx", "weight", "bp"}
MASK_PAD = 2  # points around each blacked-out box


def _label(word):
    """'Patient:' -> 'patient' if it looks like a known label (small OCR slips allowed)."""
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return None
    for label in PERSONAL_LABELS | OTHER_LABELS:
        if w == label or (len(label) >= 5 and fuzz.ratio(w, label) >= 80):
            return label
    return None


def personal_boxes(page, lines):
    """Boxes (PDF points) to black out: personal values next to their labels, the letterhead
    above the first patient label, and the doctor's signature line ("Dr. ...") below it.
    Empty list = no patient label found, so the page must not go to a cloud model."""
    boxes, first_label_y = [], None
    for line in lines:
        words, rects = line["words"], line["boxes"]
        for i, word in enumerate(words):
            if _label(word) not in PERSONAL_LABELS:
                continue
            y = line["rect"].y0
            first_label_y = y if first_label_y is None else min(first_label_y, y)
            end = page.rect.width  # the value runs to the next label on the line, or to the edge
            for later_word, later_rect in zip(words[i + 1:], rects[i + 1:]):
                if _label(later_word):
                    end = later_rect.x0 - MASK_PAD
                    break
            boxes.append(pymupdf.Rect(rects[i].x1, line["rect"].y0, end, line["rect"].y1))
    if first_label_y is None:
        return []
    for line in lines:
        first = re.sub(r"[^a-z]", "", line["text"].split()[0].lower())
        if first == "dr" and line["rect"].y0 > first_label_y:  # signature under the details
            boxes.append(pymupdf.Rect(line["rect"]))
    # letterhead (clinic name, address, phone, doctor): everything above the first patient label.
    # The whole band, not line by line: on a tilted photo the letterhead lines overlap.
    boxes.append(pymupdf.Rect(0, 0, page.rect.width, first_label_y))
    return [b + (-MASK_PAD, -MASK_PAD, MASK_PAD, MASK_PAD) for b in boxes]


def mask_personal(page, lines):
    """PNG of the page (VISION_WIDTH_PX wide) with personal details blacked out, or None if
    no patient label was found (then it is not safe to send the page anywhere)."""
    boxes = personal_boxes(page, lines)
    if not boxes:
        return None
    zoom = VISION_WIDTH_PX / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csRGB, alpha=False)
    for box in boxes:  # paint black straight onto the picture: nothing underneath survives
        pix.set_rect((box * zoom).irect & pix.irect, (0, 0, 0))
    return pix.tobytes("png")


def _clean(text):
    text = re.sub(r"^```\w*|```$", "", text.strip(), flags=re.MULTILINE)  # stray code fences
    return [line.strip() for line in text.splitlines() if line.strip()]


def _transcribe_local(page):
    zoom = VISION_WIDTH_PX / page.rect.width
    png = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
    response = requests.post(
        _ollama_url() + "/api/chat",
        json={
            "model": _model(),
            "messages": [{"role": "user", "content": PROMPT,
                          "images": [base64.b64encode(png).decode()]}],
            "stream": False,
            "options": {"temperature": 0, "num_ctx": 8192},
        },
        timeout=900,
    )
    response.raise_for_status()
    return _clean(response.json()["message"]["content"])


def transcribe(page, lines):
    """Copy a handwritten page line by line.
    1. the cloud model (VISION_MODEL set) on the MASKED page, if personal details were found
    2. else the local Ollama model, if installed
    3. else None: the caller falls back to plain Tesseract"""
    if enabled() and llm.vision_enabled():
        png = mask_personal(page, lines)
        if png is not None:
            return _clean(llm.call_vision(PROMPT, png))
    if vision_available():
        return _transcribe_local(page)
    return None


def _similarity(a, b):
    a, b = a.lower(), b.lower()
    return max(fuzz.ratio(a, b), fuzz.partial_ratio(a, b) if min(len(a), len(b)) >= 6 else 0)


def place_lines(texts, lines):
    """Give each transcribed line a position: match the two lists in order (like lining
    up two versions of a text), so the k-th copied line lands on a Tesseract line that
    looks like it. Lines with no good match go just below the previous one."""
    n, m = len(texts), len(lines)
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            score = _similarity(texts[i], lines[j]["text"])
            take = best[i + 1][j + 1] + score if score >= MIN_MATCH else -1
            best[i][j] = max(take, best[i + 1][j], best[i][j + 1])

    placed, i, j = [], 0, 0
    while i < n:
        score = _similarity(texts[i], lines[j]["text"]) if j < m else 0
        if j < m and score >= MIN_MATCH and best[i][j] == best[i + 1][j + 1] + score:
            placed.append({"text": texts[i], "rect": pymupdf.Rect(lines[j]["rect"])})
            i, j = i + 1, j + 1
        elif j < m and best[i][j] == best[i][j + 1]:
            j += 1
        else:  # no matching Tesseract line: put it under the previous one
            prev = placed[-1]["rect"] if placed else pymupdf.Rect(40, 40, 400, 52)
            placed.append({"text": texts[i], "rect": pymupdf.Rect(prev.x0, prev.y1 + 2, prev.x1, prev.y1 + 2 + prev.height)})
            i += 1
    return placed
