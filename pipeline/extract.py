"""Ask the AI for facts from ONE de-identified document. (Ashil)

extract_facts(clean_text, patient_id, document_id) -> list of fact dicts
    The AI's facts, cleaned up. page / line / quote_verified are filled in later by
    verify.py, and fact_id / document_date by process.py.

extract_document(clean_text) -> {"document_date", "document_date_raw", "doc_type",
                                  "doc_type_quote", "doc_type_confidence", "facts"}
    Same call, but also returns what the AI read about the document itself. doc_type is the
    AI's raw answer here; pipeline/doc_type.py checks its quote (process.py does that).

The AI reply is parsed robustly: strip code fences, json.loads, and retry once on bad JSON.
Anything that breaks the rules (unknown type, no quote, "not_documented") is thrown away.
"""
import json
import os
import re

from pipeline.llm import call_llm

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompts", "extraction.txt")

FACT_TYPES = {"medication", "allergy", "condition", "lab_test", "event", "demographic"}
ACTIONS = {"started", "continued", "changed", "stopped", "mentioned"}
DEMOGRAPHIC_NAMES = {"patient_name", "sex", "dob", "blood_group"}
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

RETRY_NOTE = "\n\nYour previous reply was not valid JSON. Reply with ONLY the JSON object."


def build_prompt(clean_text):
    with open(PROMPT_PATH, encoding="utf-8") as f:
        template = f.read()
    # .replace, not .format: the template itself contains JSON braces
    return template.replace("{document_text}", clean_text)


def parse_json(reply):
    """Turn the model's reply into Python data. Raises ValueError if it is not JSON."""
    text = reply.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)  # opening code fence
    text = re.sub(r"\s*```$", "", text)           # closing code fence
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # the model wrote words around the JSON: keep from the first { or [ to the last } or ]
        starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
        end = max(text.rfind("}"), text.rfind("]"))
        if not starts or end == -1:
            raise ValueError("No JSON found in the AI reply")
        return json.loads(text[min(starts):end + 1])


def _ask_ai(prompt, receipt, model=None):
    try:
        return parse_json(call_llm(prompt, receipt, model=model))
    except ValueError:  # json.JSONDecodeError is a ValueError too
        return parse_json(call_llm(prompt + RETRY_NOTE, receipt, model=model))  # one retry, then give up


def _text_or_none(value):
    """Values must stay strings exactly as written; numbers are turned back into text."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def clean_fact(raw):
    """Check one AI fact against the contract. Returns a clean dict, or None to drop it."""
    if not isinstance(raw, dict):
        return None
    fact_type = _text_or_none(raw.get("type"))
    name = _text_or_none(raw.get("name"))
    quote = _text_or_none(raw.get("quote"))
    status = _text_or_none(raw.get("status")) or "documented"
    if fact_type not in FACT_TYPES or not name or not quote:
        return None  # no quote, no fact
    if status not in ("documented", "negated"):
        return None  # the AI must never say "not_documented"
    if fact_type == "demographic":
        name = name.lower()
        if name not in DEMOGRAPHIC_NAMES:
            return None

    is_medication = fact_type == "medication"
    action = _text_or_none(raw.get("action"))
    event_date = _text_or_none(raw.get("event_date"))
    return {
        "type": fact_type,
        "name": name,
        "dose": _text_or_none(raw.get("dose")) if is_medication else None,
        "frequency": _text_or_none(raw.get("frequency")) if is_medication else None,
        "value": _text_or_none(raw.get("value")),
        "unit": _text_or_none(raw.get("unit")),
        "action": (action if action in ACTIONS else "mentioned") if is_medication else None,
        "status": status,
        "event_date": event_date if event_date and ISO_DATE.match(event_date) else None,
        "date_raw": _text_or_none(raw.get("date_raw")),
        "quote": quote,
    }


def extract_document(clean_text, receipt=None, model=None):
    """clean_text must come from privacy_layer.protect(); receipt is that result (llm.call_llm checks it).
    Without a receipt the text is protected here, with no known patient identity."""
    if receipt is None:
        from pipeline.privacy_layer import protect

        receipt = protect(clean_text)
        clean_text = receipt.text
    data = _ask_ai(build_prompt(clean_text), receipt, model)
    if isinstance(data, list):  # the model returned just the facts list
        data = {"facts": data}
    if not isinstance(data, dict):
        raise ValueError("AI reply was JSON but not an object or list")

    document_date = _text_or_none(data.get("document_date"))
    facts = [clean_fact(raw) for raw in data.get("facts") or []]
    return {
        "document_date": document_date if document_date and ISO_DATE.match(document_date) else None,
        "document_date_raw": _text_or_none(data.get("document_date_raw")),
        "doc_type": _text_or_none(data.get("doc_type")),
        "doc_type_quote": _text_or_none(data.get("doc_type_quote")),
        "doc_type_confidence": _text_or_none(data.get("doc_type_confidence")),
        "facts": [f for f in facts if f is not None],
    }


def extract_facts(clean_text, patient_id, document_id):
    facts = extract_document(clean_text)["facts"]
    for fact in facts:
        fact["patient_id"] = patient_id
        fact["document_id"] = document_id
    return facts
