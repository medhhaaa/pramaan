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


def line_boxes(path, lines):
    """{(page, line): [x0, y0, x1, y1]}: where each line of read_pdf() sits on its page, as
    fractions of the page width / height (0-1, top left = 0, 0). Used to draw a box over the
    quoted line on the original photo (a photo upload's PDF page IS the photo, scaled).
    Only pages with a text layer (digital text, or the invisible text added over a scan or
    photo) have positions; a line that can't be matched exactly gets no box."""
    boxes = {}
    by_page = {}
    for line in lines:
        by_page.setdefault(line["page"], []).append(line)
    with pymupdf.open(path) as doc:
        for page_number, page_lines in by_page.items():
            page = doc[page_number - 1]
            if not page_has_text(page):
                continue
            width, height = page.rect.width, page.rect.height
            placed = []  # the page's text lines in reading order, with their rectangles
            for block in page.get_text("dict")["blocks"]:
                for row in block.get("lines", []):
                    text = "".join(span["text"] for span in row["spans"]).strip()
                    if _is_text(text):
                        placed.append((text, row["bbox"]))
            j = 0
            for line in page_lines:  # same order as read_pdf: match forwards, never reuse
                for k in range(j, min(j + 6, len(placed))):
                    if placed[k][0] == line["text"]:
                        x0, y0, x1, y1 = placed[k][1]
                        boxes[(page_number, line["line"])] = [
                            round(max(0.0, x0 / width), 4), round(max(0.0, y0 / height), 4),
                            round(min(1.0, x1 / width), 4), round(min(1.0, y1 / height), 4)]
                        j = k + 1
                        break
    return boxes


def read_pdf(path):
    lines = []
    with pymupdf.open(path) as doc:
        for page_number, page in enumerate(doc, start=1):
            text = page.get_text() if page_has_text(page) else ocr_page_text(page)
            text_lines = [t.strip() for t in text.splitlines() if _is_text(t)]
            for line_number, line_text in enumerate(text_lines, start=1):
                lines.append({"page": page_number, "line": line_number, "text": line_text})
    return lines
