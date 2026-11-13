"""Disease search: everything in one patient's records about one disease. (Ashil, AGENTIC_PLAN point 14)

    disease_search(patient_id, access, "sugar") ->
      {"query", "disease", "label", "matched_by", "matched_terms",
       "conditions": [item], "medicines": [item], "labs": [item], "events": [item],
       "documents": [{"id", "filename", "doc_type", "document_date"}], "hidden_count"}
      item = {"fact_id", "type", "name", "dose", "frequency", "value", "unit", "action", "status",
              "event_date", "document_id", "page", "line", "quote", "echo_of", "flags"}  (click-to-proof)

How the query finds the disease (data/disease_map.json), first match wins:
  1. a disease name or synonym (data/synonyms.json + extra_terms): "diabetes", "T2DM", "sugar"
  2. a medicine, brand or generic (check_medicine.DRUGS): "Glycomet" -> metformin -> biguanide
  3. a lab test of that disease: "HbA1c"
Then the patient's facts are matched: conditions and events by the disease's names / events,
medicines by drug class or generic, labs by test name. Whole words only ("mi" never matches
inside "Metformin"). Plain lookup tables, no AI and no embeddings needed.

Scope: only facts this user may see (backend/scope.py). hidden_count = how many facts outside
the user's scope would also match: a number only, never what they are.
"""
import json
import os

from backend.db import get_conn
from backend.routes.check_medicine import lookup
from backend.routes.fact_helpers import load_documents, load_facts
from backend.scope import access_scope, fact_in_scope
from backend.search import SYNONYMS, _term_pattern, normalize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_PATH = os.path.join(ROOT, "data", "disease_map.json")
ITEM_FIELDS = ["fact_id", "type", "name", "dose", "frequency", "value", "unit", "action", "status",
               "event_date", "document_id", "page", "line", "quote", "echo_of", "flags"]
SECTIONS = {"condition": "conditions", "medication": "medicines", "lab_test": "labs", "event": "events"}


def _load_map():
    with open(MAP_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    diseases = {}
    for key, d in raw.items():
        if key.startswith("_"):
            continue
        names = [normalize(t) for t in [key, d["label"], *SYNONYMS.get(key, []), *d.get("extra_terms", [])]]
        diseases[key] = {
            "label": d["label"],
            "names": list(dict.fromkeys(t for t in names if t)),
            "drug_classes": set(d.get("drug_classes", [])),
            "medicines": [normalize(m) for m in d.get("medicines", [])],
            "labs": [normalize(t) for t in d.get("labs", [])],
            "events": [normalize(t) for t in d.get("events", [])],
        }
    return diseases


DISEASES = _load_map()


def _hit(terms, text):
    """The first term found in text as whole words, or None."""
    text = text or ""
    return next((t for t in terms if _term_pattern(t).search(text)), None)


def resolve(query):
    """query -> (disease key, how it matched) or (None, None)."""
    q = normalize(query)
    if not q:
        return None, None
    for key, d in DISEASES.items():
        if any(q == t or _term_pattern(t).search(q) for t in d["names"]):
            return key, "condition"
    generic, drug_class = lookup(q)
    for key, d in DISEASES.items():
        if (drug_class and drug_class in d["drug_classes"]) or _hit(d["medicines"], q) \
                or (generic and _hit(d["medicines"], generic)):
            return key, "medicine"
    for key, d in DISEASES.items():
        if _hit(d["labs"], q):
            return key, "lab"
    return None, None


def match_fact(fact, disease):
    """The term that ties this fact to the disease, or None."""
    name = fact.get("name") or ""
    kind = fact.get("type")
    if kind == "condition":
        return _hit(disease["names"], name) or _hit(disease["events"], name)
    if kind == "event":
        return _hit(disease["events"], name) or _hit(disease["names"], name)
    if kind == "lab_test":
        return _hit(disease["labs"], name)
    if kind == "medication":
        generic, drug_class = lookup(name)
        if drug_class and drug_class in disease["drug_classes"]:
            return normalize(name)
        return _hit(disease["medicines"], name) or (generic and _hit(disease["medicines"], generic))
    return None


def _item(fact):
    return {k: fact.get(k) for k in ITEM_FIELDS}


def disease_search(patient_id, access, query):
    key, matched_by = resolve(query)
    out = {"query": query, "disease": key, "label": DISEASES[key]["label"] if key else None,
           "matched_by": matched_by, "matched_terms": [], "conditions": [], "medicines": [], "labs": [],
           "events": [], "documents": [], "hidden_count": 0}
    if not key:
        return out
    disease, scope = DISEASES[key], access_scope(access)
    with get_conn() as conn:
        facts = [f for f in load_facts(conn, patient_id) if f["status"] != "not_documented"]
        docs = load_documents(conn, patient_id)

    terms, doc_ids = [], []
    for fact in sorted(facts, key=lambda f: (f.get("event_date") or "", f["fact_id"]), reverse=True):
        section = SECTIONS.get(fact["type"])
        term = section and match_fact(fact, disease)
        if not term:
            continue
        if not fact_in_scope(fact, scope):
            out["hidden_count"] += 1  # how many, never which
            continue
        out[section].append(_item(fact))
        terms.append(term)
        doc_ids.append(fact["document_id"])

    out["matched_terms"] = list(dict.fromkeys(terms))
    out["documents"] = [
        {k: docs[d].get(k) for k in ("id", "filename", "doc_type", "document_date")}
        for d in dict.fromkeys(doc_ids) if d in docs
    ]
    return out


def fact_ids(result):
    return [item["fact_id"] for section in SECTIONS.values() for item in result[section]]
