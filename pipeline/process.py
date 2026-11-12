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
from pipeline.deidentify import deidentify, reidentify
from pipeline.doc_type import UNKNOWN, classify_document, date_written_in, stay_dates
from pipeline.extract import extract_document
from pipeline.ocr import handwritten_pages
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
    }


def process_document_full(pdf_path, patient_id, document_id, known_names=(), document_date=None):
    lines = read_pdf(pdf_path)
    if not lines:  # scanned image PDF: we do no OCR for the demo
        return {"facts": [], "dropped": [], "document_date": document_date,
                "document_date_raw": None, "document_date_verified": False, **UNKNOWN,
                "stay_dates": {"admitted_on": None, "discharged_on": None}, "redactions": 0}

    original_text = "\n".join(line["text"] for line in lines)
    clean_text, mapping = deidentify(original_text, known_names)

    result = extract_document(clean_text)  # the only step that talks to the AI

    facts = [_reidentify_fact(f, mapping) for f in result["facts"]]
    dropped = []
    verified = verify_facts(facts, lines, dropped)

    document_date = document_date or result["document_date"]
    document_date_raw = result["document_date_raw"]
    # the quote comes back de-identified; put real names back before checking it
    doc_type = classify_document(result["doc_type"], reidentify(result["doc_type_quote"] or "", mapping),
                                 result["doc_type_confidence"], lines)
    facts = [
        _contract_fact(f, n, patient_id, document_id, document_date, document_date_raw)
        for n, f in enumerate(verified, start=1)
    ]
    # a page read from handwriting by the vision model: a person must check these facts
    from_handwriting = handwritten_pages(pdf_path)
    for fact in facts:
        if fact["page"] in from_handwriting:
            fact["flags"].append("handwriting")
    return {
        "facts": check_plausibility(facts),
        "dropped": dropped,
        "document_date": document_date,
        "document_date_raw": document_date_raw,
        "document_date_verified": date_written_in(document_date_raw, lines),
        **doc_type,
        "stay_dates": stay_dates(doc_type["doc_type"], facts, document_date, document_date_raw, lines),
        "redactions": len(mapping),
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
