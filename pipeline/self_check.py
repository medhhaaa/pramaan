"""The agent checks its own work (AGENTIC_PLAN point 5).

After the quote check, some facts may be dropped (their quote was not found in the document, or
a dose/value is not in the quoted line). Before giving up on them, the agent tries again:

  1. re-read   pages that were read by OCR are read again at a higher resolution (OCR misreads
               like "SOOmg" for "500mg" often go away). Digital PDFs are skipped: re-reading their
               text layer can't change anything.
  2. stronger  if LLM_STRONG_MODEL is set in .env, the same protected text is extracted again with
     model   that model; facts from that run that match a dropped fact AND pass the quote check
               are kept.
  3. not sure  anything still failing is returned as "not sure": the caller stores it for a person
               (backend/routes/not_sure.py), it is never silently thrown away.

retry_dropped(dropped, lines, pdf_path, clean_text, receipt, mapping, reidentify_fact)
    -> (recovered_facts, still_dropped, trace_steps)
"""
import os
import time

import pymupdf

from pipeline.verify import verify_facts

REREAD_DPI = 400


def ocr_pages(pdf_path):
    """Pages (1-based) whose text was made by printed OCR (pipeline/ocr.py marks them)."""
    from pipeline.ocr import OCR_MARK

    with pymupdf.open(pdf_path) as doc:
        author = doc.metadata.get("author") or ""
    if not author.startswith(OCR_MARK):
        return []
    return [int(n) for n in author[len(OCR_MARK):].split(",") if n.isdigit()]


def reread_lines(pdf_path, pages, dpi=REREAD_DPI):
    """Fresh OCR of the given pages at a higher resolution -> [{"page", "line", "text"}]."""
    lines = []
    with pymupdf.open(pdf_path) as doc:
        for number in pages:
            page = doc[number - 1]
            textpage = page.get_textpage_ocr(dpi=dpi, full=True, tessdata=pymupdf.get_tessdata())
            n = 0
            for block in page.get_text("dict", textpage=textpage)["blocks"]:
                for line in block.get("lines", []):
                    text = " ".join(span["text"] for span in line["spans"]).strip()
                    if text:
                        n += 1
                        lines.append({"page": number, "line": n, "text": text})
    return lines


def _key(fact):
    return ((fact.get("type") or "").lower(), (fact.get("name") or "").lower().strip())


def _step(trace, started, detail, status):
    trace.append({"step": "retry", "status": status, "detail": detail,
                  "ms": int((time.perf_counter() - started) * 1000)})
    return time.perf_counter()


def retry_dropped(dropped, lines, pdf_path, clean_text, receipt, mapping, reidentify_fact):
    trace, recovered = [], []
    if not dropped:
        return recovered, dropped, trace
    still = [dict(f) for f in dropped]
    t = time.perf_counter()

    # 1. re-read OCR pages at a higher resolution
    pages = sorted({f.get("page") for f in still if f.get("page")} | set(ocr_pages(pdf_path)))
    pages = [p for p in pages if p in ocr_pages(pdf_path)]
    if pages:
        try:
            extra = reread_lines(pdf_path, pages)
            ok = verify_facts([{k: v for k, v in f.items() if k != "drop_reason"} for f in still], extra)
            got = {_key(f) for f in ok}
            for f in ok:
                f["retry"] = f"re-read at {REREAD_DPI} dpi"
            recovered += ok
            still = [f for f in still if _key(f) not in got]
            t = _step(trace, t, f"re-read page(s) {pages} at {REREAD_DPI} dpi: {len(ok)} recovered", "retry")
        except Exception as e:  # Tesseract missing etc.: note it and go on
            t = _step(trace, t, f"re-read not possible ({str(e)[:60]})", "warn")
    else:
        t = _step(trace, t, "digital text, re-reading can't change it: skipped", "ok")

    # 2. a stronger model on the same protected text
    strong = os.getenv("LLM_STRONG_MODEL")
    if still and strong:
        from pipeline.extract import extract_document

        try:
            second = extract_document(clean_text, receipt, model=strong)["facts"]
            wanted = {_key(f) for f in still}
            candidates = [reidentify_fact(f, mapping) for f in second if _key(f) in wanted]
            ok = verify_facts(candidates, lines)
            got = {_key(f) for f in ok}
            for f in ok:
                f["retry"] = f"re-extracted with {strong}"
            recovered += ok
            still = [f for f in still if _key(f) not in got]
            t = _step(trace, t, f"asked a stronger model ({strong}): {len(ok)} recovered", "retry")
        except Exception as e:  # stronger model down / no quota: keep going, nothing is lost
            t = _step(trace, t, f"stronger model failed ({str(e)[:60]})", "warn")
    elif still:
        t = _step(trace, t, "no stronger model configured (LLM_STRONG_MODEL): skipped", "ok")

    if still:
        _step(trace, t, f"{len(still)} fact(s) still not proven by the document: sent to 'App not sure' "
                        "for a person to accept or reject", "warn")
    return recovered, still, trace
