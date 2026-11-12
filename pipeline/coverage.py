"""Coverage map: mark every medical line captured (green) or not (yellow). (Ashil, P2)

coverage(lines, facts) -> [{"page", "line", "text", "medical": bool, "covered": bool}]
    lines   read_pdf() output for ONE document
    facts   that document's verified facts (they carry page + line)

medical  the line looks clinical: a medicine form (Tab., Inj., Inhaler...), a number with a
         unit (500mg, 7.2 %, 122 mg/dL), a test name or a diagnosis word. Letterheads,
         signatures, reference ranges, section headings, test methods and advice lines
         are not counted (advice is an instruction, not a fact about the patient's history,
         and the extraction prompt skips it on purpose).
covered  a fact quotes this line. A covered line always counts as medical.

So a yellow line (medical, not covered) is an omission anyone can see, never hidden.

Try it:  python -m pipeline.coverage p1          (uses the saved data/extracted/p1.json)
"""
import re

DRUG_FORM = r"\b(?:tab|tabs|cap|caps|inj|syp|syr|inhaler|neb|oint|drops?)\b\.?"
NUMBER_WITH_UNIT = (
    r"\d\s*(?:mg|mcg|g|ml|iu|units?|mmol/l|mg/dl|g/dl|ng/ml|ng/dl|uiu/ml|miu/l|umol/l|"
    r"mmhg|%|l/min|cells/cumm|ml/min)(?![a-z])"
)
TEST_WORDS = (
    r"\b(?:hba1c|glucose|sugar|cholesterol|ldl|hdl|triglycerides|creatinine|egfr|urea|"
    r"potassium|sodium|tsh|t3|t4|haemoglobin|hemoglobin|hb|platelets?|wbc|psa|troponin|"
    r"ecg|x-ray|usg|ct|mri|spirometry|fev1|pefr|spo2|bp|pulse|ferritin|vitamin|ige|"
    r"eosinophil|acr|albumin|blood group)\b"
)
DIAGNOSIS_WORDS = (
    r"\b(?:diagnosis|diagnosed|history of|known case|k/c/o|allerg\w*|admitted|ruled out|"
    r"complaints?|pain|fever|diabetes|hypertension|asthma\w*|thyroid|hypothyroidism|kidney|"
    r"ckd|disease|syndrome|infarction|mi|cabg|surgery|\w+ectomy|\w+itis|\w+iasis|injury|"
    r"deficiency|dyslipidaemia|deranged|swelling)\b"
)
MEDICAL = re.compile("|".join([DRUG_FORM, NUMBER_WITH_UNIT, TEST_WORDS, DIAGNOSIS_WORDS]),
                     re.IGNORECASE)

# a line that is only a reference range: "4.0 - 5.6 %", "< 200 mg/dL", "> 90 mL/min/1.73m2"
REFERENCE_RANGE = re.compile(r"^[<>]?\s*\d[\d.,]*\s*(?:-\s*\d[\d.,]*)?\s*[a-zA-Z%/.\d]*$")
# letterheads, signatures, methods, footers
NOT_MEDICAL = re.compile(
    r"\bPh:|clinic|hospital|diagnostics|laborator|centre|\bReg\. No|consultant|\bMBBS\b|"
    r"\bMD\b|\bDM\b|\bMS\b|^Method|^Note:|^Advice|^\*\*\*|SYNTHETIC TEST DOCUMENT",
    re.IGNORECASE,
)
SECTION_HEADINGS = {
    "rx", "presenting complaint", "past history", "allergies", "investigations",
    "final diagnosis", "discharge medications", "procedure",
}


def is_medical(text):
    stripped = text.strip()
    if stripped.lower() in SECTION_HEADINGS:
        return False
    if REFERENCE_RANGE.match(stripped) or NOT_MEDICAL.search(stripped):
        return False
    return bool(MEDICAL.search(stripped))


def _covered_positions(lines, facts):
    """(page, line) of every line some fact quotes. A quote verify.py matched across two
    lines covers the next line too."""
    by_position = {(l["page"], l["line"]): i for i, l in enumerate(lines)}
    covered = set()
    for fact in facts:
        i = by_position.get((fact.get("page"), fact.get("line")))
        if i is None:  # gap facts and facts from other documents have no position here
            continue
        covered.add((lines[i]["page"], lines[i]["line"]))
        quote = fact.get("quote") or ""
        if i + 1 < len(lines) and len(quote) > len(lines[i]["text"]) and lines[i + 1]["text"] in quote:
            covered.add((lines[i + 1]["page"], lines[i + 1]["line"]))
    return covered


def coverage(lines, facts):
    covered = _covered_positions(lines, facts)
    result = []
    for line in lines:
        is_covered = (line["page"], line["line"]) in covered
        result.append({
            "page": line["page"],
            "line": line["line"],
            "text": line["text"],
            "medical": is_covered or is_medical(line["text"]),
            "covered": is_covered,
        })
    return result


def summary(rows):
    medical = [r for r in rows if r["medical"]]
    covered = [r for r in medical if r["covered"]]
    return {"medical_lines": len(medical), "covered_lines": len(covered),
            "coverage": round(len(covered) / len(medical), 3) if medical else None}


if __name__ == "__main__":
    import json
    import os
    import sys

    from pipeline.read_pdf import read_pdf

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for pid in sys.argv[1:] or ["p1"]:
        with open(os.path.join(root, "data", "answer_keys", f"{pid}.json"), encoding="utf-8") as f:
            documents = {d["document_id"]: d for d in json.load(f)["documents"]}
        with open(os.path.join(root, "data", "extracted", f"{pid}.json"), encoding="utf-8") as f:
            extracted = json.load(f)
        for doc in extracted["documents"]:
            filename = documents[doc["document_id"]]["filename"]
            rows = coverage(read_pdf(os.path.join(root, "data", "patients", pid, filename)), doc["facts"])
            s = summary(rows)
            print(f"\n{doc['document_id']}  {s['covered_lines']}/{s['medical_lines']} medical lines covered")
            for r in rows:
                mark = "GREEN " if r["covered"] else ("YELLOW" if r["medical"] else "      ")
                print(f"  {mark} {r['line']:3} {r['text']}")
