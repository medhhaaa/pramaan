"""The full pipeline for one uploaded document. (Ashil)

process_document(pdf_path, patient_id, document_id, known_names=(), document_date=None)
    -> list of verified facts in the contract format (CLAUDE.md section 5)

    read_pdf -> deidentify -> extract (AI) -> reidentify -> verify -> fill contract fields

    known_names    the patient's name(s) from the patients table, so they are surely redacted
    document_date  ISO date if the uploader already knows it; otherwise the AI reads it

process_document_full(...) -> {"facts", "dropped", "document_date", "document_date_raw",
                               "doc_type", "redactions"}
    Same thing, plus what the backend may want to store about the document
    (doc_type, document_date) and the facts verification threw away.

Try it:  python -m pipeline.process data/patients/p1/d1_prescription_2019.pdf p1 p1_d1 "Sunita Rao"
"""
from pipeline.deidentify import deidentify, reidentify
from pipeline.extract import extract_document
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
        "flags": [],       # set later by backend/logic/flags.py
        "corrected": False,
    }


def process_document_full(pdf_path, patient_id, document_id, known_names=(), document_date=None):
    lines = read_pdf(pdf_path)
    if not lines:  # scanned image PDF: we do no OCR for the demo
        return {"facts": [], "dropped": [], "document_date": document_date,
                "document_date_raw": None, "doc_type": None, "redactions": 0}

    original_text = "\n".join(line["text"] for line in lines)
    clean_text, mapping = deidentify(original_text, known_names)

    result = extract_document(clean_text)  # the only step that talks to the AI

    facts = [_reidentify_fact(f, mapping) for f in result["facts"]]
    dropped = []
    verified = verify_facts(facts, lines, dropped)

    document_date = document_date or result["document_date"]
    document_date_raw = result["document_date_raw"]
    return {
        "facts": [
            _contract_fact(f, n, patient_id, document_id, document_date, document_date_raw)
            for n, f in enumerate(verified, start=1)
        ],
        "dropped": dropped,
        "document_date": document_date,
        "document_date_raw": document_date_raw,
        "doc_type": result["doc_type"],
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
