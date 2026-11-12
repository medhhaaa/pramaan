"""Is OCR safe to use? Checks every scanned synthetic document, no AI calls. (Ashil)

For each scan in data/scanned/ it checks:
  1. quotes   Can each answer-key fact still be verified against the OCR text, with its
              numbers exactly right? (If not, the pipeline drops that fact: a miss, never
              a wrong fact.)
  2. redaction  After OCR, does de-identification still remove every identifier? We also
              look for NEAR-misses: an identifier OCR garbled slightly ("98765 4321O") that
              the regex rules would not catch but a person could still read.

Run:  python data/make_scans.py      (once, makes the scans)
      python -m pipeline.ocr_check   (all patients)   or   python -m pipeline.ocr_check p1
"""
import importlib.util
import json
import os
import re
import sys
import time

from rapidfuzz import fuzz

from pipeline.deidentify import deidentify
from pipeline.read_pdf import read_pdf
from pipeline.verify import _fields_in_evidence, find_quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
NEAR_MISS = 88  # rapidfuzz similarity that still counts as "readable by a person"
LABELS = ("Patient", "UHID", "IP No", "OP No", "Lab ID", "Sample ID", "Mobile", "DOB", "Address",
          "Aadhaar", "ABHA No", "Ref. by", "Referred by", "Father")


def _generator():
    spec = importlib.util.spec_from_file_location("generate_docs", os.path.join(DATA, "generate_docs.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def identifiers(gen, patient):
    """Every identifier printed on this patient's documents, taken from the generator."""
    items = set(patient["patient"]["name"].split())
    for doc in patient["documents"]:
        hospital = gen.HOSPITALS[doc["hospital"]]
        items |= {hospital["name"], hospital["lines"][0]}
        items |= set(re.findall(r"0\d{3} \d{7}", hospital["lines"][1]))
        signature = doc.get("signature", hospital["signature"])
        items |= {signature[0].replace("Dr. ", ""), signature[0].split()[-1]}
        items |= set(re.findall(r"Reg\. No\. (\d+)", signature[-1]))
        for item in doc["lines"]:
            for text in (item.get("text"), item.get("right")):
                if text and text.split(":")[0] in LABELS:
                    value = text.split(":", 1)[1].strip()
                    items.add(re.sub(r"^(Dr|Mr|Mrs)\. ", "", value))
    return {i for i in items if i}


def leaks(clean_text, pii):
    exact, near = [], []
    lower = clean_text.lower()
    for item in pii:
        if item.lower() in lower:
            exact.append(item)
        # a garbled identifier can only hide in a line at least as long as itself
        elif len(item) >= 6 and any(fuzz.partial_ratio(item.lower(), line.lower()) >= NEAR_MISS
                                    for line in clean_text.splitlines() if len(line) >= len(item)):
            near.append(item)
    return exact, near


def check_patient(gen, patient):
    pid = patient["patient_id"]
    with open(os.path.join(DATA, "answer_keys", f"{pid}.json"), encoding="utf-8") as f:
        key = json.load(f)
    pii = identifiers(gen, patient)
    totals = {"facts": 0, "verifiable": 0, "seconds": 0.0, "exact_leaks": [], "near_misses": []}
    lost = []
    for doc in key["documents"]:
        path = os.path.join(DATA, "scanned", pid, doc["filename"])
        started = time.time()
        lines = read_pdf(path)
        totals["seconds"] += time.time() - started

        for fact in (f for f in key["facts"] if f["document_id"] == doc["document_id"]):
            totals["facts"] += 1
            match = find_quote(fact["quote"], lines)
            if match and not _fields_in_evidence(fact, match[1]):
                totals["verifiable"] += 1
            else:
                lost.append((doc["document_id"], fact["quote"], match[1] if match else None))

        clean, _ = deidentify("\n".join(l["text"] for l in lines), [key["patient"]["name"]])
        exact, near = leaks(clean, pii)
        totals["exact_leaks"] += [(doc["document_id"], x) for x in exact]
        totals["near_misses"] += [(doc["document_id"], x) for x in near]
    return totals, lost, len(key["documents"])


def main(patient_ids):
    gen = _generator()
    patients = [p for p in gen.PATIENTS if not patient_ids or p["patient_id"] in patient_ids]
    all_ok = True
    for patient in patients:
        t, lost, n_docs = check_patient(gen, patient)
        rate = t["verifiable"] / t["facts"]
        print(f"{patient['patient_id']}: {t['verifiable']}/{t['facts']} facts verifiable on the scans "
              f"({rate:.1%}), OCR {t['seconds'] / n_docs:.1f}s per page, "
              f"leaks {len(t['exact_leaks'])}, near-misses {len(t['near_misses'])}")
        for doc_id, quote, ocr_text in lost:
            print(f"    would be dropped  {doc_id}: {quote!r}  OCR read: {ocr_text!r}")
        for doc_id, item in t["exact_leaks"] + t["near_misses"]:
            print(f"    IDENTIFIER LEFT   {doc_id}: {item!r}")
        all_ok &= not t["exact_leaks"] and not t["near_misses"]
    print("\nredaction after OCR:", "OK, nothing left" if all_ok else "PROBLEMS, see above")


if __name__ == "__main__":
    main(sys.argv[1:])
