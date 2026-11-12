"""Generate synthetic patient PDFs with planted traps, plus answer keys. (Ashil)

Each document below is written once, as a list of lines. A line can carry the facts a
perfect extractor should find in it. The PDF and the answer key both come from that one
description, so they can never disagree.

After drawing each PDF we read it back with pipeline/read_pdf.py and check that every
answer-key quote is really there (and record its page + line).

Output:
    data/patients/p1/*.pdf
    data/answer_keys/p1.json     facts in the contract format (CLAUDE.md section 5),
                                 with the flags and echoes we planted

Run:  python data/generate_docs.py

Every person, hospital, doctor and number in this file is made up.
"""
import json
import os
import sys

from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DATA_DIR)
sys.path.insert(0, ROOT)
from pipeline.read_pdf import read_pdf  # noqa: E402


# ---------------------------------------------------------------------------
# Facts: small helpers so the documents below stay short
# ---------------------------------------------------------------------------

def fact(type_, name, *, dose=None, frequency=None, value=None, unit=None, action=None,
         status="documented", event_date=None, date_raw=None, quote=None, flags=(),
         echo_of=None):
    """One expected fact. quote defaults to the text of the line it is attached to.
    event_date / date_raw default to the document's date.
    echo_of is a document key ("d1"): this line was copied word-for-word from there."""
    return {
        "type": type_, "name": name, "dose": dose, "frequency": frequency,
        "value": value, "unit": unit, "action": action, "status": status,
        "event_date": event_date, "date_raw": date_raw, "quote": quote,
        "flags": list(flags), "echo_of": echo_of,
    }


def med(name, dose, frequency, action, **kw):
    return fact("medication", name, dose=dose, frequency=frequency, action=action, **kw)


def condition(name, **kw):
    return fact("condition", name, **kw)


def allergy(name, **kw):
    return fact("allergy", name, **kw)


def lab(name, value, unit, **kw):
    return fact("lab_test", name, value=value, unit=unit, **kw)


def event(name, **kw):
    return fact("event", name, **kw)


def demographic(name, value, **kw):
    return fact("demographic", name, value=value, **kw)


# ---------------------------------------------------------------------------
# Layout: one item per printed line
# ---------------------------------------------------------------------------

def text(s, *facts):
    return {"kind": "text", "text": s, "facts": list(facts)}


def heading(s):
    return {"kind": "heading", "text": s, "facts": []}


def row(left, right="", *facts):
    """Two columns on one printed line. PyMuPDF reads them back as two separate lines.
    Attached facts quote the LEFT text unless they set quote= themselves."""
    return {"kind": "row", "text": left, "right": right, "facts": list(facts)}


GAP = {"kind": "gap", "facts": []}
RULE = {"kind": "rule", "facts": []}


# ---------------------------------------------------------------------------
# Hospitals, clinics and labs (fictional)
# ---------------------------------------------------------------------------

HOSPITALS = {
    "karavali": {
        "name": "KARAVALI HEART & DIABETES CLINIC",
        "lines": [
            "2nd Floor, Lotus Arcade, Kadri Road, Mangaluru - 575003",
            "Ph: 0824 2441122  |  Dr. Anand Shetty, MBBS, MD (General Medicine)",
        ],
        "color": "#0f5c6e",
        "signature": ["Dr. Anand Shetty", "MBBS, MD (General Medicine)", "KMC Reg. No. 48213"],
    },
    "coastline": {
        "name": "COASTLINE DIAGNOSTICS",
        "lines": [
            "Ground Floor, Hampankatta Circle, Mangaluru - 575001",
            "Ph: 0824 2425566  |  NABL accredited laboratory",
        ],
        "color": "#7a2e8e",
        "signature": ["Dr. Meera Kamath", "MD (Pathology)", "Consultant Pathologist"],
    },
    "netravati": {
        "name": "NETRAVATI MULTISPECIALITY HOSPITAL",
        "lines": [
            "Falnir Road, Mangaluru - 575002",
            "Ph: 0824 2233445  |  24x7 Emergency: 0824 2233400",
        ],
        "color": "#a3341f",
        "signature": ["Dr. Prakash Bhat", "MD, DM (Cardiology)", "Consultant Cardiologist"],
    },
    "bluewave": {
        "name": "BLUEWAVE PATHOLOGY LABORATORY",
        "lines": [
            "Bejai Main Road, Mangaluru - 575004",
            "Ph: 0824 2218899  |  Home sample collection available",
        ],
        "color": "#1d4fa3",
        "signature": ["Dr. Rekha Nayak", "MD (Biochemistry)", "Consultant Biochemist"],
    },
}


# ---------------------------------------------------------------------------
# Patient p1: Sunita Rao (CLAUDE.md section 12)
# ---------------------------------------------------------------------------

def bluewave_hba1c_report(key, filename, doc_flags):
    """d5, and d6 which is an exact copy of it under another filename."""
    return {
        "key": key, "filename": filename, "doc_type": "lab_report",
        "date": "2023-01-16", "date_raw": "16/01/2023", "hospital": "bluewave",
        "title": "TEST REPORT", "doc_flags": doc_flags,
        "lines": [
            row("Patient: Mrs. Sunita Rao", "Sample ID: BW/23/01160",
                demographic("patient_name", "Mrs. Sunita Rao")),
            row("Sex: Female", "Age: 70 Y", demographic("sex", "Female")),
            row("Referred by: Dr. Anand Shetty", "Date: 16/01/2023"),
            row("ABHA No: 91-4471-2286-0053", "Mobile: 98765 43210"),
            RULE,
            row("Investigation / Result", "Bio. ref. interval"),
            row("HbA1c 8.1 %", "< 5.7 %", lab("HbA1c", "8.1", "%")),
            # TRAP unit mismatch: d2 reported glucose in mmol/L
            row("Fasting Glucose 122 mg/dL", "70 - 100 mg/dL",
                lab("Fasting blood glucose", "122", "mg/dL", flags=["unit_mismatch"])),
            GAP,
            text("Note: Results relate only to the sample tested."),
        ],
    }


P1 = {
    "patient_id": "p1",
    "patient": {"name": "Sunita Rao", "dob": "1952-06-14", "sex": "F", "blood_group": "O+"},
    "traps": [
        {"type": "contradiction", "documents": ["p1_d1", "p1_d3"],
         "note": "d1 says 'No known drug allergies'; d3 says 'Allergy: Penicillin (rash)'."},
        {"type": "echo", "documents": ["p1_d1", "p1_d3", "p1_d4"],
         "note": "d3 discharge meds and d4 Atenolol line are copied word-for-word from d1. "
                 "Atenolol: mentioned in 3 documents, last real evidence 2019."},
        {"type": "medication_change", "documents": ["p1_d4"],
         "note": "Metformin 500mg BD -> 1000mg BD (fresh change); Amlodipine 5mg OD started."},
        {"type": "event_date_differs", "documents": ["p1_d3"],
         "note": "'History of MI in 2015' written in a 2022 document."},
        {"type": "unit_mismatch", "documents": ["p1_d2", "p1_d5"],
         "note": "Fasting glucose 6.8 mmol/L (d2) vs 122 mg/dL (d5)."},
        {"type": "duplicate", "documents": ["p1_d5", "p1_d6"],
         "note": "d6 is a byte-for-byte copy of d5 under a different filename."},
        {"type": "wrong_patient", "documents": ["p1_d7"],
         "note": "'S. Rao', male, blood group B+, PSA test. Patient is female, O+."},
        {"type": "ambiguous_date", "documents": ["p1_d7"],
         "note": "04/05/2023 could be 4 May or 5 April."},
    ],
    "documents": [
        # d1: the original 2019 prescription
        {
            "key": "d1", "filename": "d1_prescription_2019.pdf", "doc_type": "prescription",
            "date": "2019-03-12", "date_raw": "12/03/2019", "hospital": "karavali",
            "title": "OUT-PATIENT PRESCRIPTION",
            "lines": [
                row("Patient: Sunita Rao", "Date: 12/03/2019",
                    demographic("patient_name", "Sunita Rao")),
                row("Sex: Female", "UHID: KHC-004512", demographic("sex", "Female")),
                row("DOB: 14-06-1952", "Mobile: +91 98765 43210",
                    demographic("dob", "14-06-1952")),
                text("Address: 14, Shanthi Nilaya, Bejai, Mangaluru - 575004"),
                text("Blood group: O+", demographic("blood_group", "O+")),
                RULE,
                text("Diagnosis: Type 2 diabetes mellitus", condition("Type 2 diabetes mellitus")),
                GAP,
                heading("Rx"),
                text("Tab. Metformin 500mg BD", med("Metformin", "500mg", "BD", "started")),
                text("Tab. Atenolol 50mg OD", med("Atenolol", "50mg", "OD", "started")),
                GAP,
                # TRAP contradiction with d3
                text("No known drug allergies",
                     allergy("Drug allergy", status="negated", flags=["contradiction"])),
                text("Advice: Diet control, 30 minutes walk daily. Review after 3 months."),
            ],
        },
        # d2: 2021 lab report, glucose in mmol/L
        {
            "key": "d2", "filename": "d2_lab_2021.pdf", "doc_type": "lab_report",
            "date": "2021-06-20", "date_raw": "2021-06-20", "hospital": "coastline",
            "title": "LABORATORY REPORT",
            "lines": [
                row("Patient: Sunita Rao", "Lab ID: CD-210620-0457",
                    demographic("patient_name", "Sunita Rao")),
                row("Sex: Female", "Age: 69 years", demographic("sex", "Female")),
                row("Ref. by: Dr. Anand Shetty", "Report date: 2021-06-20"),
                RULE,
                row("Test / Result", "Reference range"),
                row("HbA1c: 7.2 %", "4.0 - 5.6 %", lab("HbA1c", "7.2", "%")),
                # TRAP unit mismatch with d5 (mg/dL)
                row("Fasting blood glucose: 6.8 mmol/L", "3.9 - 5.5 mmol/L",
                    lab("Fasting blood glucose", "6.8", "mmol/L", flags=["unit_mismatch"])),
                GAP,
                text("Method: HPLC (HbA1c), Hexokinase (glucose)"),
                text("*** End of report ***"),
            ],
        },
        # d3: 2022 discharge summary. Allergy contradiction + meds echoed from d1
        {
            "key": "d3", "filename": "d3_discharge_2022.pdf", "doc_type": "discharge_summary",
            "date": "2022-08-05", "date_raw": "05-Aug-2022", "hospital": "netravati",
            "title": "DISCHARGE SUMMARY",
            "lines": [
                row("Patient: Sunita Rao", "IP No: NMH/22/018834",
                    demographic("patient_name", "Sunita Rao")),
                row("Sex: Female", "Age: 70 years", demographic("sex", "Female")),
                row("DOB: 14-06-1952", "Aadhaar: 4821 7730 2195",
                    demographic("dob", "14-06-1952")),
                row("Blood group: O+", "Mobile: +91 98765 43210",
                    demographic("blood_group", "O+")),
                row("Date of admission: 03-Aug-2022", "Date of discharge: 05-Aug-2022"),
                RULE,
                heading("Presenting complaint"),
                text("Admitted with complaints of chest pain.",
                     event("Admission for chest pain", event_date="2022-08-03",
                           date_raw="03-Aug-2022")),
                heading("Past history"),
                text("Known case of Type 2 diabetes mellitus.",
                     condition("Type 2 diabetes mellitus")),
                # TRAP event_date (2015) differs from document_date (2022)
                text("History of MI in 2015.",
                     event("Myocardial infarction", event_date="2015-01-01", date_raw="2015")),
                heading("Allergies"),
                # TRAP contradiction with d1
                text("Allergy: Penicillin (rash)",
                     allergy("Penicillin", value="rash", flags=["contradiction"])),
                heading("Investigations"),
                text("ECG: No acute ST-T changes", lab("ECG", "No acute ST-T changes", None)),
                text("Troponin I: Negative", lab("Troponin I", "Negative", None)),
                heading("Final diagnosis"),
                text("Atypical chest pain", condition("Atypical chest pain")),
                text("Acute coronary syndrome ruled out.",
                     condition("Acute coronary syndrome", status="negated")),
                heading("Discharge medications"),
                # TRAP echo: these two lines are copied word-for-word from d1
                text("Tab. Metformin 500mg BD",
                     med("Metformin", "500mg", "BD", "continued", echo_of="d1")),
                text("Tab. Atenolol 50mg OD",
                     med("Atenolol", "50mg", "OD", "continued", echo_of="d1")),
                GAP,
                text("Advice on discharge: Follow up in Cardiology OPD after 2 weeks."),
            ],
        },
        # d4: 2023 prescription. Fresh Metformin change, Atenolol echoed again, Amlodipine new
        {
            "key": "d4", "filename": "d4_prescription_2023.pdf", "doc_type": "prescription",
            "date": "2023-01-15", "date_raw": "15/01/2023", "hospital": "karavali",
            "title": "OUT-PATIENT PRESCRIPTION",
            "lines": [
                row("Patient: Sunita Rao", "Date: 15/01/2023",
                    demographic("patient_name", "Sunita Rao")),
                row("Sex: Female", "UHID: KHC-004512", demographic("sex", "Female")),
                row("Mobile: +91 98765 43210", ""),
                RULE,
                text("BP: 156/94 mmHg", lab("Blood pressure", "156/94", "mmHg")),
                text("Diagnosis: Type 2 diabetes mellitus, Hypertension",
                     condition("Type 2 diabetes mellitus"), condition("Hypertension")),
                GAP,
                heading("Rx"),
                text("Tab. Metformin increased to 1000mg BD",
                     med("Metformin", "1000mg", "BD", "changed")),
                # TRAP echo: copied word-for-word from d1
                text("Tab. Atenolol 50mg OD",
                     med("Atenolol", "50mg", "OD", "continued", echo_of="d1")),
                text("Tab. Amlodipine 5mg OD - start", med("Amlodipine", "5mg", "OD", "started")),
                GAP,
                text("Advice: Low salt diet. Review after 1 month with lab reports."),
            ],
        },
        # d5: 2023 lab from another lab, glucose in mg/dL
        bluewave_hba1c_report("d5", "d5_lab_2023.pdf", doc_flags=[]),
        # d6: TRAP duplicate, identical to d5 under another filename
        bluewave_hba1c_report("d6", "d6_lab_2023_copy.pdf", doc_flags=["duplicate"]),
        # d7: TRAP wrong patient (male, B+) + ambiguous date 04/05/2023
        {
            "key": "d7", "filename": "d7_lab_psa.pdf", "doc_type": "lab_report",
            "date": "2023-05-04", "date_raw": "04/05/2023", "hospital": "coastline",
            "title": "LABORATORY REPORT", "held_back": True,
            "doc_flags": ["wrong_patient", "ambiguous_date"],
            "lines": [
                row("Patient: S. Rao", "Lab ID: CD-230504-0112",
                    demographic("patient_name", "S. Rao")),
                row("Sex: Male", "Age: 61 years", demographic("sex", "Male")),
                row("Ref. by: Dr. Vivek Pai", "Report date: 04/05/2023"),
                text("Blood group: B+", demographic("blood_group", "B+")),
                RULE,
                row("Test / Result", "Reference range"),
                row("PSA (total): 2.1 ng/mL", "0 - 4.0 ng/mL", lab("PSA", "2.1", "ng/mL")),
                GAP,
                text("Method: Chemiluminescence immunoassay (CLIA)"),
                text("*** End of report ***"),
            ],
        },
    ],
}

PATIENTS = [P1]


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

LEFT, COL2, RIGHT = 50, 330, 545
GREY = HexColor("#555555")
FOOTER = "SYNTHETIC TEST DOCUMENT - generated for the Pramaan demo. Not a real patient."


def draw_pdf(path, doc):
    hospital = HOSPITALS[doc["hospital"]]
    color = HexColor(hospital["color"])
    width, height = A4
    # invariant=1 -> no timestamps, so the same document always gives the same bytes
    # (that is what makes d6 an exact copy of d5)
    c = canvas.Canvas(path, pagesize=A4, invariant=1)

    # letterhead
    y = height - 55
    c.setFillColor(color)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(LEFT, y, hospital["name"])
    y -= 15
    c.setFillColor(GREY)
    c.setFont("Helvetica", 9)
    for line in hospital["lines"]:
        c.drawString(LEFT, y, line)
        y -= 12
    c.setStrokeColor(color)
    c.setLineWidth(1.5)
    c.line(LEFT, y, RIGHT, y)
    y -= 24

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(width / 2, y, doc["title"])
    y -= 26

    # body
    c.setStrokeColor(GREY)
    c.setLineWidth(0.5)
    for item in doc["lines"]:
        kind = item["kind"]
        if kind == "gap":
            y -= 8
        elif kind == "rule":
            c.line(LEFT, y + 4, RIGHT, y + 4)
            y -= 10
        elif kind == "heading":
            y -= 4
            c.setFont("Helvetica-Bold", 10.5)
            c.drawString(LEFT, y, item["text"])
            y -= 16
        else:
            c.setFont("Helvetica", 10)
            c.drawString(LEFT, y, item["text"])
            if item.get("right"):
                c.drawString(COL2, y, item["right"])
            y -= 15

    # signature
    y -= 30
    c.setFont("Helvetica-Bold", 10)
    for i, line in enumerate(hospital["signature"]):
        c.drawRightString(RIGHT, y, line)
        c.setFont("Helvetica", 9)
        y -= 12
    if y < 60:
        raise ValueError(f"{doc['filename']} does not fit on one page")

    c.setFillColor(GREY)
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawCentredString(width / 2, 30, FOOTER)
    c.save()


# ---------------------------------------------------------------------------
# Answer key
# ---------------------------------------------------------------------------

def find_line(quote, lines):
    """Page + line of the quote in what read_pdf returns. Exact line first, then contains."""
    for line in lines:
        if line["text"] == quote:
            return line["page"], line["line"]
    for line in lines:
        if quote in line["text"]:
            return line["page"], line["line"]
    return None


def build_answer_key(patient, pdf_lines_by_doc):
    pid = patient["patient_id"]
    facts = []
    for doc in patient["documents"]:
        doc_id = f"{pid}_{doc['key']}"
        lines = pdf_lines_by_doc[doc["key"]]
        n = 0
        for item in doc["lines"]:
            for expected in item["facts"]:
                n += 1
                quote = expected["quote"] or item["text"]
                position = find_line(quote, lines)
                if position is None:
                    raise ValueError(f"{doc_id}: quote not found in PDF text: {quote!r}")
                facts.append({
                    "fact_id": f"{doc_id}_f{n:03d}",
                    "patient_id": pid,
                    "document_id": doc_id,
                    "type": expected["type"],
                    "name": expected["name"],
                    "dose": expected["dose"],
                    "frequency": expected["frequency"],
                    "value": expected["value"],
                    "unit": expected["unit"],
                    "action": expected["action"],
                    "status": expected["status"],
                    "event_date": expected["event_date"] or doc["date"],
                    "document_date": doc["date"],
                    "date_raw": expected["date_raw"] or doc["date_raw"],
                    "quote": quote,
                    "page": position[0],
                    "line": position[1],
                    "quote_verified": True,
                    "echo_of": expected["echo_of"],  # still a doc key, resolved below
                    "badge": None,
                    "flags": expected["flags"] + doc.get("doc_flags", []),
                    "corrected": False,
                })

    # echo_of "d1" -> the fact_id of the same quote in d1
    for f in facts:
        if f["echo_of"]:
            source_doc = f"{pid}_{f['echo_of']}"
            original = next(
                (o for o in facts if o["document_id"] == source_doc
                 and o["type"] == f["type"] and o["quote"] == f["quote"]),
                None,
            )
            if original is None:
                raise ValueError(f"{f['fact_id']}: no original for echo in {source_doc}")
            f["echo_of"] = original["fact_id"]

    documents = [
        {
            "document_id": f"{pid}_{d['key']}",
            "filename": d["filename"],
            "doc_type": d["doc_type"],
            "document_date": d["date"],
            "date_raw": d["date_raw"],
            "held_back": d.get("held_back", False),
        }
        for d in patient["documents"]
    ]
    return {
        "patient_id": pid,
        "patient": patient["patient"],
        "documents": documents,
        "traps": patient["traps"],
        "facts": facts,
    }


# ---------------------------------------------------------------------------

def main():
    os.makedirs(os.path.join(DATA_DIR, "answer_keys"), exist_ok=True)
    for patient in PATIENTS:
        pid = patient["patient_id"]
        folder = os.path.join(DATA_DIR, "patients", pid)
        os.makedirs(folder, exist_ok=True)

        pdf_lines_by_doc = {}
        for doc in patient["documents"]:
            path = os.path.join(folder, doc["filename"])
            draw_pdf(path, doc)
            pdf_lines_by_doc[doc["key"]] = read_pdf(path)

        key = build_answer_key(patient, pdf_lines_by_doc)
        key_path = os.path.join(DATA_DIR, "answer_keys", f"{pid}.json")
        with open(key_path, "w", encoding="utf-8") as f:
            json.dump(key, f, indent=2, ensure_ascii=False)
            f.write("\n")

        print(f"{pid}: {len(patient['documents'])} PDFs in {folder}")
        for doc in key["documents"]:
            n = sum(1 for f in key["facts"] if f["document_id"] == doc["document_id"])
            held = "  (held back)" if doc["held_back"] else ""
            print(f"  {doc['document_id']:7} {doc['filename']:26} {n:2} facts{held}")
        print(f"  answer key: {key_path} ({len(key['facts'])} facts, all quotes found in PDFs)")


if __name__ == "__main__":
    main()
