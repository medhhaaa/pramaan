"""Precision / recall of extracted facts vs data/answer_keys/pN.json. (Ashil)

Run:
    python -m pipeline.metrics            run the pipeline (calls the AI) on every patient
                                          that has an answer key, then score
    python -m pipeline.metrics p1 p2      only these patients
    python -m pipeline.metrics --cached   score the saved data/extracted/pN.json again (no AI)

Saves:  data/extracted/pN.json   what the pipeline found (verified + dropped facts)
        data/metrics.json        the scores (for GET /metrics)

How a match is decided: an extracted fact matches an answer-key fact from the same
document when the type is the same, the name is similar (rapidfuzz >= 80, plus a few
common abbreviations), and the dose / value is the same when the key has one.
Each answer-key fact can be matched only once.

    precision = matched / extracted     (how much of what we show is right)
    recall    = matched / expected      (how much of what is there we found)
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

from rapidfuzz import fuzz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
KEY_DIR = os.path.join(DATA_DIR, "answer_keys")
EXTRACTED_DIR = os.path.join(DATA_DIR, "extracted")
METRICS_PATH = os.path.join(DATA_DIR, "metrics.json")

NAME_THRESHOLD = 80
ALIASES = {  # abbreviation -> full name, used only for matching
    "mi": "myocardial infarction",
    "bp": "blood pressure",
    "t2dm": "type 2 diabetes mellitus",
    "dm": "diabetes mellitus",
    "htn": "hypertension",
    "fbs": "fasting blood glucose",
    "nkda": "drug allergy",
    "acs": "acute coronary syndrome",
}
FIELDS_CHECKED = ["status", "action", "event_date", "unit", "frequency", "line"]


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _name(text):
    words = re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).split()
    return " ".join(ALIASES.get(w, w) for w in words)


def _compact(text):
    return re.sub(r"\s+", "", str(text or "")).lower()


def names_match(a, b):
    a, b = _name(a), _name(b)
    return a == b or fuzz.token_set_ratio(a, b) >= NAME_THRESHOLD


def values_match(expected, got, field):
    if not expected:
        return True  # nothing to compare
    e, g = _compact(expected), _compact(got)
    if e == g:
        return True
    if field == "sex":
        return e[:1] == g[:1]  # "Female" vs "F"
    numeric = re.fullmatch(r"[\d.]+", e)
    return bool(g) and not numeric and (e in g or g in e)  # "Sunita Rao" in "Mrs. Sunita Rao"


def is_match(key_fact, fact):
    if key_fact["document_id"] != fact["document_id"] or key_fact["type"] != fact["type"]:
        return False
    if key_fact["type"] == "allergy" and key_fact["status"] == fact["status"] == "negated":
        return True  # "No known drug allergies" may be named many ways
    if key_fact["type"] == "demographic":
        if key_fact["name"] != fact["name"]:
            return False
        return values_match(key_fact["value"], fact["value"], key_fact["name"])
    return (names_match(key_fact["name"], fact["name"])
            and values_match(key_fact["dose"], fact["dose"], "dose")
            and values_match(key_fact["value"], fact["value"], "value"))


def match_facts(key_facts, facts):
    """Greedy one-to-one matching. Returns (pairs, unmatched_facts, missed_key_facts)."""
    free = list(key_facts)
    pairs, extra = [], []
    for fact in facts:
        found = next((k for k in free if is_match(k, fact)), None)
        if found is None:
            extra.append(fact)
        else:
            free.remove(found)
            pairs.append((found, fact))
    return pairs, extra, free


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _ratio(a, b):
    return round(a / b, 3) if b else None


def score(matched, extracted, expected):
    precision, recall = _ratio(matched, extracted), _ratio(matched, expected)
    f1 = (round(2 * precision * recall / (precision + recall), 3)
          if precision and recall else 0.0)
    return {"precision": precision, "recall": recall, "f1": f1,
            "matched": matched, "extracted": extracted, "expected": expected}


def score_patient(key, facts):
    pairs, extra, missed = match_facts(key["facts"], facts)
    result = score(len(pairs), len(facts), len(key["facts"]))

    result["by_type"] = {}
    for fact_type in sorted({f["type"] for f in key["facts"]} | {f["type"] for f in facts}):
        result["by_type"][fact_type] = score(
            sum(1 for k, _ in pairs if k["type"] == fact_type),
            sum(1 for f in facts if f["type"] == fact_type),
            sum(1 for k in key["facts"] if k["type"] == fact_type),
        )

    # of the facts we matched, how often each detail is also right
    result["field_accuracy"] = {}
    for field in FIELDS_CHECKED:
        relevant = [(k, f) for k, f in pairs if k.get(field) is not None]
        right = sum(1 for k, f in relevant if _compact(k[field]) == _compact(f.get(field)))
        result["field_accuracy"][field] = _ratio(right, len(relevant))

    short = lambda f: {k: f.get(k) for k in ("document_id", "type", "name", "dose", "value", "quote")}  # noqa: E731
    result["false_positives"] = [short(f) for f in extra]
    result["missed"] = [short(k) for k in missed]
    return result


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------

def load_key(patient_id):
    with open(os.path.join(KEY_DIR, f"{patient_id}.json"), encoding="utf-8") as f:
        return json.load(f)


def run_pipeline(key):
    """Process every document of one patient. Saves and returns the extraction."""
    from pipeline.process import process_document_full

    pid = key["patient_id"]
    out = {"patient_id": pid, "documents": []}
    for doc in key["documents"]:
        path = os.path.join(DATA_DIR, "patients", pid, doc["filename"])
        started = time.time()
        result = process_document_full(path, pid, doc["document_id"],
                                       known_names=[key["patient"]["name"]])
        seconds = round(time.time() - started, 1)
        print(f"  {doc['document_id']}: {len(result['facts'])} facts, "
              f"{len(result['dropped'])} dropped, {seconds}s")
        out["documents"].append({"document_id": doc["document_id"], "seconds": seconds, **result})

    os.makedirs(EXTRACTED_DIR, exist_ok=True)
    with open(os.path.join(EXTRACTED_DIR, f"{pid}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    return out


def load_extracted(patient_id):
    with open(os.path.join(EXTRACTED_DIR, f"{patient_id}.json"), encoding="utf-8") as f:
        return json.load(f)


def main(argv):
    cached = "--cached" in argv
    patient_ids = [a for a in argv if not a.startswith("--")] or sorted(
        name[:-5] for name in os.listdir(KEY_DIR) if name.endswith(".json"))

    patients, all_facts, all_keys, dropped = {}, [], [], 0
    for pid in patient_ids:
        key = load_key(pid)
        print(f"{pid}:{' (cached)' if cached else ''}")
        extraction = load_extracted(pid) if cached else run_pipeline(key)
        facts = [f for d in extraction["documents"] for f in d["facts"]]
        dropped += sum(len(d["dropped"]) for d in extraction["documents"])
        patients[pid] = score_patient(key, facts)
        all_facts += facts
        all_keys += key["facts"]
        s = patients[pid]
        print(f"  precision {s['precision']}  recall {s['recall']}  f1 {s['f1']}  "
              f"({s['matched']} matched / {s['extracted']} extracted / {s['expected']} expected)")

    overall = score_patient({"facts": all_keys}, all_facts)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "overall": {k: overall[k] for k in ("precision", "recall", "f1", "matched", "extracted", "expected")},
        "by_type": overall["by_type"],
        "field_accuracy": overall["field_accuracy"],
        "dropped_by_verification": dropped,
        "patients": patients,
    }
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    o = report["overall"]
    print(f"\nOVERALL  precision {o['precision']}  recall {o['recall']}  f1 {o['f1']}")
    for fact_type, s in report["by_type"].items():
        print(f"  {fact_type:12} precision {s['precision']}  recall {s['recall']}")
    print(f"  field accuracy on matched facts: {report['field_accuracy']}")
    print(f"  facts dropped by quote verification: {dropped}")
    print(f"Saved {METRICS_PATH}")


if __name__ == "__main__":
    main(sys.argv[1:])
