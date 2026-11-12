"""Read a PDF into lines with page and line numbers. (Ashil)

read_pdf(path) -> list of {"page": int, "line": int, "text": str}   (1-based)

Digital PDFs are read from their text layer. A scanned page (no text layer) is read
with OCR (pipeline/ocr.py), so scans and photographed documents work too.
Lines with no letters or digits (OCR's reading of ruled lines and smudges) are skipped,
the same way for every page, so line numbers always agree with GET /documents.
"""
import pymupdf

from pipeline.ocr import ocr_page_text, page_has_text


def _is_text(line):
    return "�" not in line and any(c.isalnum() for c in line)


def read_pdf(path):
    lines = []
    with pymupdf.open(path) as doc:
        for page_number, page in enumerate(doc, start=1):
            text = page.get_text() if page_has_text(page) else ocr_page_text(page)
            text_lines = [t.strip() for t in text.splitlines() if _is_text(t)]
            for line_number, line_text in enumerate(text_lines, start=1):
                lines.append({"page": page_number, "line": line_number, "text": line_text})
    return lines
