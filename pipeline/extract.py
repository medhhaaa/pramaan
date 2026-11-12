"""Ask the AI for facts from ONE de-identified document. (Ashil)

extract_facts(clean_text, patient_id, document_id) -> list of fact dicts (contract
format in CLAUDE.md section 5; page/line/quote_verified are filled in later by verify.py)
Strip code fences, json.loads, retry once on bad JSON.
"""
from pipeline.llm import call_llm  # noqa: F401


def extract_facts(clean_text, patient_id, document_id):
    raise NotImplementedError
