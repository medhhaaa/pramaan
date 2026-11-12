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

tesseract_lines(page) -> [{"text", "rect", "confs"}]      where Tesseract found text lines
needs_vision(lines) -> bool                                Tesseract unsure -> use the model
vision_available() -> bool                                 is the model installed in Ollama?
transcribe(page) -> [str]                                  the model's line-by-line copy
place_lines(texts, lines) -> [{"text", "rect"}]            each copied line with a position

Settings (.env): HANDWRITING_MODEL (default qwen2.5vl:7b), OLLAMA_URL, HANDWRITING=off
"""
import base64
import csv
import io
import os
import re
import subprocess
import tempfile

import pymupdf
import requests
from rapidfuzz import fuzz

TESS_DPI = 300
VISION_WIDTH_PX = 1000          # page width sent to the model: handwriting still readable, much faster
MIN_MEAN_CONFIDENCE = 90        # printed scans and photos score 92-96
MAX_UNSURE_SHARE = 0.05         # printed: 0-4% of words below 60; handwriting: more
MIN_MATCH = 35                  # rapidfuzz score to trust a line position

PROMPT = """You are copying a medical document that may be handwritten.
Write out ALL of its text exactly as written, top to bottom, one line of the document per line of output.
Rules:
- Copy spelling, numbers, units, doses and abbreviations exactly. Do not correct, expand or translate anything.
- If a word cannot be read, write [?] in its place. Never guess a medicine name or a number.
- Output only the copied text, nothing else."""


def _model():
    return os.getenv("HANDWRITING_MODEL", "qwen2.5vl:7b")


def _ollama_url():
    return os.getenv("OLLAMA_URL", "http://localhost:11434")


def tesseract_lines(page):
    """Tesseract's text lines with positions (PDF points) and word confidences."""
    png = os.path.join(tempfile.gettempdir(), f"pramaan_tess_{os.getpid()}.png")
    page.get_pixmap(dpi=TESS_DPI).save(png)
    try:
        tsv = subprocess.run(["tesseract", png, "stdout", "tsv"], capture_output=True, text=True,
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
            lines[key] = {"rect": pymupdf.Rect(left, top, right, bottom), "words": [], "confs": []}
        elif row["level"] == "5" and key in lines and row["text"].strip():  # a word on that line
            lines[key]["words"].append(row["text"])
            lines[key]["confs"].append(float(row["conf"]))
    result = [{"text": " ".join(l["words"]), "rect": l["rect"], "confs": l["confs"]}
              for l in lines.values() if l["words"]]
    return sorted(result, key=lambda l: (round(l["rect"].y0), l["rect"].x0))


def needs_vision(lines):
    confs = [c for line in lines for word, c in zip(line["text"].split(), line["confs"])
             if sum(ch.isalnum() for ch in word) >= 2]
    if not confs:
        return True  # Tesseract found no words at all
    mean = sum(confs) / len(confs)
    unsure = sum(c < 60 for c in confs) / len(confs)
    return mean < MIN_MEAN_CONFIDENCE or unsure > MAX_UNSURE_SHARE


def vision_available():
    if os.getenv("HANDWRITING", "on").lower() == "off":
        return False
    try:
        models = requests.get(_ollama_url() + "/api/tags", timeout=3).json()["models"]
    except (requests.RequestException, ValueError, KeyError):
        return False
    return any(m["name"] == _model() for m in models)


def transcribe(page):
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
    text = response.json()["message"]["content"]
    text = re.sub(r"^```\w*|```$", "", text.strip(), flags=re.MULTILINE)  # stray code fences
    return [line.strip() for line in text.splitlines() if line.strip()]


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
