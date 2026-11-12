"""Read a PDF into lines with page and line numbers. (Ashil)

read_pdf(path) -> list of {"page": int, "line": int, "text": str}   (1-based)
"""
import pymupdf


def read_pdf(path):
    lines = []
    with pymupdf.open(path) as doc:
        for page_number, page in enumerate(doc, start=1):
            text_lines = [t for t in page.get_text().splitlines() if t.strip()]
            for line_number, text in enumerate(text_lines, start=1):
                lines.append({"page": page_number, "line": line_number, "text": text.strip()})
    return lines
