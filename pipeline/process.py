"""The full pipeline for one uploaded document. (Ashil)

process_document(pdf_path, patient_id, document_id, known_names=(), document_date=None)
    -> list of verified facts in the contract format (CLAUDE.md section 5)

    read_pdf -> deidentify -> extract (AI) -> reidentify -> verify -> fill contract fields
    -> plausibility guard (adds "implausible_value" to impossible lab values)
    -> facts from a page read from handwriting get "handwriting" (check against the image)
    These are the only flags the pipeline sets; the backend checks keep them.

    known_names    the patient's name(s) from the patients table, so they are surely redacted
    document_date  ISO date if the uploader already knows it; otherwise the AI reads it

process_document_full(...) -> {"facts", "dropped", "document_date", "document_date_raw",
                               "document_date_verified", "doc_type", "doc_type_quote",
                               "doc_type_page", "doc_type_line", "redactions"}
    Same thing, plus what the backend may want to store about the document
    (doc_type, document_date) and the facts verification threw away.
    doc_type is checked like a fact (pipeline/doc_type.py): no verified quote -> "unknown".
    document_date_verified: the date as written was found in the document text.
    stay_dates: {"admitted_on", "discharged_on"} read from a discharge summary, only if verified.

Try it:  python -m pipeline.process data/patients/p1/d1_prescription_2019.pdf p1 p1_d1 "Sunita Rao"
"""
import time

from pipeline.coverage import coverage
from pipeline.deidentify import deidentify, reidentify
from pipeline.doc_type import UNKNOWN, classify_document, date_written_in, stay_dates
from pipeline.extract import extract_document
from rapidfuzz import fuzz

from pipeline.ocr import handwriting_confidences, handwritten_pages, unread_pages
from pipeline.privacy_layer import PrivacyBlocked, protect
from pipeline.self_check import retry_dropped
from pipeline.plausibility import check_plausibility
from pipeline.read_pdf import read_pdf
from pipeline.verify import verify_facts

TEXT_FIELDS = ["name", "dose", "frequency", "value", "unit", "date_raw", "quote"]


def _reidentify_fact(fact, mapping):
    """Put real names back into the AI's fact. This runs on our server only."""
    fact = dict(fact)
    for field in TEXT_FIELDS:
        if fact.get(field):
            fact[field] = reidentify(fact[field], mapping)
    return fact


def _contract_fact(fact, number, patient_id, document_id, document_date, document_date_raw):
    """Final shape, same key order as CLAUDE.md section 5."""
    return {
        "fact_id": f"{document_id}_f{number:03d}",
        "patient_id": patient_id,
        "document_id": document_id,
        "type": fact["type"],
        "name": fact["name"],
        "dose": fact["dose"],
        "frequency": fact["frequency"],
        "value": fact["value"],
        "unit": fact["unit"],
        "action": fact["action"],
        "status": fact["status"],
        "event_date": fact["event_date"] or document_date,
        "document_date": document_date,
        "date_raw": fact["date_raw"] or document_date_raw,
        "quote": fact["quote"],
        "page": fact["page"],
        "line": fact["line"],
        "quote_verified": True,
        "echo_of": None,   # set later by backend/logic/echo.py
        "badge": None,     # set later by backend/logic/badges.py
        "flags": [],       # set later by backend/logic/flags.py (plus our plausibility guard)
        "corrected": False,
        "confidence": None,  # 0-100, only for facts read from handwriting
        "unsure": [],        # words the reader marked as a best guess (shown highlighted)
    }


def _step(trace, name, started, detail, status="ok"):
    """One line of "What the agent did" (saved by backend/ingest.py into agent_steps)."""
    trace.append({"step": name, "status": status, "detail": detail,
                  "ms": int((time.perf_counter() - started) * 1000)})
    return time.perf_counter()


def process_document_full(pdf_path, patient_id, document_id, known_names=(), document_date=None, identity=None):
    trace = []
    t = time.perf_counter()
    lines = read_pdf(pdf_path)
    hand, unread = handwritten_pages(pdf_path), unread_pages(pdf_path)
    t = _step(trace, "read", t, f"{len(lines)} text lines"
              + (f"; handwriting read by the vision model on page(s) {sorted(hand)}" if hand else "")
              + (f"; page(s) {unread} kept for a person (not sent to any AI)" if unread else ""))
    if not lines:  # scanned image PDF: we do no OCR for the demo
        return {"facts": [], "dropped": [], "not_captured": [], "document_date": document_date,
                "document_date_raw": None, "document_date_verified": False, **UNKNOWN,
                "stay_dates": {"admitted_on": None, "discharged_on": None}, "redactions": 0,
                "unread_pages": unread, "trace": trace}

    original_text = "\n".join(line["text"] for line in lines)
    clean_text, mapping = deidentify(original_text, known_names)
    # second layer before the AI: known identity, patterns, local NER, context cues; fail closed
    identity = identity or ({"name": known_names[0]} if known_names else None)
    try:
        receipt = protect(clean_text, identity, mapping)
    except PrivacyBlocked as blocked:
        # something identifying is still there: never send it; keep the document for a person
        _step(trace, "protect", t, "personal details still found after redaction: NOT sent to the AI, "
              "kept for a person", "blocked")
        return {"facts": [], "dropped": [], "not_captured": [], "document_date": document_date,
                "document_date_raw": None, "document_date_verified": False, **UNKNOWN,
                "stay_dates": {"admitted_on": None, "discharged_on": None}, "redactions": len(mapping),
                "unread_pages": [], "privacy_blocked": [{"kind": f.kind, "text": f.text} for f in blocked.findings],
                "trace": trace}
    clean_text, mapping = receipt.text, receipt.mapping
    t = _step(trace, "protect", t, f"{len(mapping)} personal details replaced by tokens; second check found nothing")

    result = extract_document(clean_text, receipt)  # the only step that talks to the AI
    t = _step(trace, "extract", t, f"AI returned {len(result['facts'])} facts")

    facts = [_reidentify_fact(f, mapping) for f in result["facts"]]
    dropped = []
    verified = verify_facts(facts, lines, dropped)
    t = _step(trace, "check", t, f"{len(verified)} quotes found in the document, {len(dropped)} not found",
              "warn" if dropped else "ok")
    # the agent checks its own work: re-read OCR pages, then a stronger model, then "App not sure"
    recovered, dropped, retry_trace = retry_dropped(dropped, lines, pdf_path, clean_text, receipt, mapping,
                                                    _reidentify_fact)
    verified += recovered
    trace += retry_trace
    t = time.perf_counter()

    document_date = document_date or result["document_date"]
    document_date_raw = result["document_date_raw"]
    # the quote comes back de-identified; put real names back before checking it
    doc_type = classify_document(result["doc_type"], reidentify(result["doc_type_quote"] or "", mapping),
                                 result["doc_type_confidence"], lines)
    t = _step(trace, "classify", t, f"{doc_type['doc_type']}"
              + (f' (evidence: "{doc_type["doc_type_quote"]}")' if doc_type.get("doc_type_quote") else " (no evidence line)"),
              "ok" if doc_type["doc_type"] != "unknown" else "warn")
    facts = [
        _contract_fact(f, n, patient_id, document_id, document_date, document_date_raw)
        for n, f in enumerate(verified, start=1)
    ]
    # a page read from handwriting by the vision model: a person must check these facts
    from_handwriting = handwritten_pages(pdf_path)
    confidences = handwriting_confidences(pdf_path)
    for fact in facts:
        if fact["page"] in from_handwriting:
            fact["flags"].append("handwriting")
            # the line the quote was found in: how sure we are it was read right
            rows = confidences.get(fact["page"], [])
            if rows:
                best = max(rows, key=lambda r: fuzz.partial_ratio(fact["quote"].lower(), r[0].lower()))
                fact["confidence"] = best[1]
                # best-guess words that ended up in this fact's own fields: highlight + lower the score
                fields = " ".join(str(fact.get(k) or "") for k in ("name", "dose", "frequency", "value", "unit")).lower()
                fact["unsure"] = [w for w in (best[2] if len(best) > 2 else []) if w.lower() in fields]
                if fact["unsure"]:
                    fact["confidence"] = min(fact["confidence"], 50)
    facts = check_plausibility(facts)
    # medical lines no verified fact quotes: shown on the upload screen as "not captured"
    not_captured = [{"page": c["page"], "line": c["line"], "text": c["text"]}
                    for c in coverage(lines, facts) if c["medical"] and not c["covered"]]
    return {
        "facts": facts,
        "unread_pages": unread_pages(pdf_path),
        "dropped": dropped,
        "not_captured": not_captured,
        "document_date": document_date,
        "document_date_raw": document_date_raw,
        "document_date_verified": date_written_in(document_date_raw, lines),
        **doc_type,
        "stay_dates": stay_dates(doc_type["doc_type"], facts, document_date, document_date_raw, lines),
        "redactions": len(mapping),
        "trace": trace,
    }


def process_document(pdf_path, patient_id, document_id, known_names=(), document_date=None):
    return process_document_full(pdf_path, patient_id, document_id, known_names, document_date)["facts"]


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 4:
        print('Usage: python -m pipeline.process <file.pdf> <patient_id> <document_id> ["Patient Name"]')
        sys.exit(1)
    out = process_document_full(sys.argv[1], sys.argv[2], sys.argv[3], known_names=sys.argv[4:])
    print(json.dumps(out["facts"], indent=2, ensure_ascii=False))
    print(f"\n{len(out['facts'])} verified facts, {len(out['dropped'])} dropped, "
          f"{out['redactions']} values redacted before the AI call, "
          f"doc_type={out['doc_type']}, document_date={out['document_date']}")
    for d in out["dropped"]:
        print(f"  dropped: {d['type']} {d['name']!r}: {d['drop_reason']}")
