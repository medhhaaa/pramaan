"""Claim Documents checklist: which documents commonly needed for a reimbursement claim are
already saved in Pramaan. Plain code, no AI, no claim decision of any kind. (Medha)

load_rules(path=RULES_PATH) -> the list in rules/claim_checklist.json

build_checklist(rules, documents, stay) -> {"items": [...], "summary": {...}}
    rules      [{"doc", "label", "when"}]   when = "always" | "surgery" | "implant_used" | "accident"
    documents  the patient's documents: [{"id", "patient_id", "doc_type", "doc_type_quote",
                                          "held_back", "document_date"}]
    stay       {"patient_id", "admitted_on", "discharged_on", "surgery", "implant_used", "accident"}
               conditions are True / False / None (None = not answered or "I don't know")

    item = {"doc", "label", "when", "status", "document_ids"}
      status: "saved" | "not_saved" | "not_needed" | "unsure"
        when "always" or its condition is True -> the item applies:
            "saved" if at least one matching document counts, else "not_saved"
        condition False -> "not_needed";  condition None -> "unsure"
    A document counts when it belongs to the stay's patient, its doc_type matches, its
    doc_type was verified by a quote, it is not held back, and it is dated within the stay
    (an undated document counts only when the stay has no dates).
    summary = {"saved_count", "required_count" (items that apply), "unsure_count"}
"""
import json
import os

RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "rules", "claim_checklist.json")

# older documents call lab and scan reports "lab_report"
MATCHING_TYPES = {"investigation_report": {"investigation_report", "lab_report"}}
CONDITIONS = ("surgery", "implant_used", "accident")


def load_rules(path=RULES_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def within_stay(document_date, stay):
    """ISO dates compare correctly as strings. A stay without dates accepts every document."""
    start, end = stay.get("admitted_on"), stay.get("discharged_on")
    if not start and not end:
        return True
    if not document_date:
        return False
    return (not start or document_date >= start) and (not end or document_date <= end)


def document_counts(doc, doc_type, stay):
    return (
        doc.get("patient_id") == stay.get("patient_id")
        and doc.get("doc_type") in MATCHING_TYPES.get(doc_type, {doc_type})
        and bool(doc.get("doc_type_quote"))  # verified: the type came with a quote found in the document
        and not doc.get("held_back")
        and within_stay(doc.get("document_date"), stay)
    )


def build_checklist(rules, documents, stay):
    items = []
    for rule in rules:
        when = rule["when"]
        condition = True if when == "always" else stay.get(when)
        item = {"doc": rule["doc"], "label": rule["label"], "when": when, "document_ids": []}
        if condition is None:
            item["status"] = "unsure"
        elif condition is False:
            item["status"] = "not_needed"
        else:
            item["document_ids"] = [d["id"] for d in documents if document_counts(d, rule["doc"], stay)]
            item["status"] = "saved" if item["document_ids"] else "not_saved"
        items.append(item)

    applies = [i for i in items if i["status"] in ("saved", "not_saved")]
    return {
        "items": items,
        "summary": {
            "saved_count": sum(1 for i in applies if i["status"] == "saved"),
            "required_count": len(applies),
            "unsure_count": sum(1 for i in items if i["status"] == "unsure"),
        },
    }
