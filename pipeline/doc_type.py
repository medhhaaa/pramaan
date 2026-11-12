"""What kind of document is this? Checked like every fact: no quote, no doc_type. (Medha)

classify_document(raw_type, raw_quote, raw_confidence, lines)
    -> {"doc_type", "doc_type_quote", "doc_type_page", "doc_type_line"}

The AI names the type AND quotes the line that shows it (usually the title, such as
"DISCHARGE SUMMARY" or "FINAL BILL"). The quote is checked with the same find_quote()
that verifies facts (pipeline/verify.py). The type becomes "unknown" when:
  - the AI's type is not one of DOC_TYPES,
  - there is no quote, or the quote is not in the document,
  - the AI says its confidence is low.
"unknown" is also used when the document has no text at all.

date_written_in(date_raw, lines) -> True if that date string really appears in the document.

stay_dates(doc_type, facts, document_date, document_date_raw, lines)
    -> {"admitted_on", "discharged_on"} for a discharge summary, each None unless verified:
       admitted_on   the admission event's date, if its date as written is in the document
       discharged_on the document date (a discharge summary is dated on discharge), same check
"""
from pipeline.verify import find_quote

DOC_TYPES = {
    "discharge_summary", "final_bill", "payment_receipt", "pharmacy_bill",
    "investigation_report", "prescription", "operation_notes", "implant_invoice",
    "fir_or_mlc", "other",
    # older documents and saved results use lab_report for lab and scan reports;
    # the claim checklist counts it as an investigation_report
    "lab_report",
}
UNKNOWN = {"doc_type": "unknown", "doc_type_quote": None, "doc_type_page": None, "doc_type_line": None}


def classify_document(raw_type, raw_quote, raw_confidence, lines):
    doc_type = (raw_type or "").strip().lower()
    if doc_type not in DOC_TYPES or not raw_quote or not lines:
        return dict(UNKNOWN)
    if (raw_confidence or "").strip().lower() == "low":
        return dict(UNKNOWN)
    match = find_quote(raw_quote, lines)
    if match is None:
        return dict(UNKNOWN)
    index, evidence, _score = match
    return {
        "doc_type": doc_type,
        "doc_type_quote": evidence,  # the document's own text, like verified facts
        "doc_type_page": lines[index]["page"],
        "doc_type_line": lines[index]["line"],
    }


def date_written_in(date_raw, lines):
    return bool(date_raw) and bool(lines) and find_quote(date_raw, lines) is not None


def stay_dates(doc_type, facts, document_date, document_date_raw, lines):
    if doc_type != "discharge_summary":
        return {"admitted_on": None, "discharged_on": None}
    admission = next(
        (f for f in facts if f["type"] == "event" and "admi" in (f["name"] or "").lower()), None)
    admitted = admission and admission["event_date"] and date_written_in(admission.get("date_raw"), lines)
    return {
        "admitted_on": admission["event_date"] if admitted else None,
        "discharged_on": document_date if document_date and date_written_in(document_date_raw, lines) else None,
    }
