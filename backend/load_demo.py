"""Build the real demo database: reset, then run every synthetic PDF through the same
upload steps as POST /patients/{id}/upload (encrypt -> pipeline/AI -> checks). (Core backend)

    python -m backend.load_demo            all demo patients (uses the AI: one call per document)
    python -m backend.load_demo p1 p3      only these patients
    python -m backend.load_demo --saved    NO AI calls: uses Ashil's saved extraction results
                                           (data/extracted/pN.json); encryption, wrong-patient
                                           check and all the checks still run. Takes seconds.

Groq's free tier allows 200,000 tokens per day for the whole team. A full AI run uses
about half of that, so use --saved for normal work and the AI run only when needed.

Documents are loaded in filename order (d1, d2, ...), so document IDs match the answer keys
(p4's d6 copy is dated 2018 but keeps the ID p4_d6).
Needs LLM_API_KEY and FILE_ENCRYPTION_KEY in .env.
"""
import json
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from backend.ingest import ingest_document  # noqa: E402
from backend.seed import PATIENT_IDS, ROOT, load_answer_key, seed  # noqa: E402


def load_saved(patient_id):
    """{document_id: saved pipeline output} from data/extracted/<patient>.json"""
    with open(os.path.join(ROOT, "data", "extracted", f"{patient_id}.json"), encoding="utf-8") as f:
        return {d["document_id"]: d for d in json.load(f)["documents"]}


def load(patient_ids, use_saved=False):
    seed(with_sample_facts=False)
    total_start = time.time()
    for patient_id in patient_ids:
        docs = sorted(load_answer_key(patient_id)["documents"], key=lambda d: d["filename"])
        saved = load_saved(patient_id) if use_saved else {}
        print(f"\n{patient_id}: {len(docs)} documents" + (" (saved results, no AI)" if use_saved else ""))
        for d in docs:
            with open(os.path.join(ROOT, "data", "patients", patient_id, d["filename"]), "rb") as f:
                data = f.read()
            start = time.time()
            r = ingest_document(patient_id, d["filename"], data,
                                saved=saved[d["document_id"]] if use_saved else None)
            held = "  HELD BACK: " + "; ".join(r["reasons"]) if r["held_back"] else ""
            print(f"  {d['filename']:<28} -> {r['document_id']:<7} {r['facts_added']:>3} facts, "
                  f"{r['dropped']} dropped, {r['doc_type']}, {r['document_date']}  "
                  f"({time.time() - start:.0f}s){held}")
    print(f"\nDone in {time.time() - total_start:.0f}s")
    # Dr. Rao's care team, prescriptions, doses and a refill request (needs the documents above)
    from backend.demo_care_team import build
    build()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    load(args or PATIENT_IDS, use_saved="--saved" in sys.argv)
