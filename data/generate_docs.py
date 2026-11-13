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

Run:  python data/generate_docs.py           every patient
      python data/generate_docs.py p6        only these patients

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
    "paduva": {
        "name": "PADUVA FAMILY CLINIC",
        "lines": [
            "Opp. Bus Stand, Bunder Road, Mangaluru - 575001",
            "Ph: 0824 2456789  |  Dr. Suresh Kotian, MBBS, MD (General Medicine)",
        ],
        "color": "#2f6b2f",
        "signature": ["Dr. Suresh Kotian", "MBBS, MD (General Medicine)", "KMC Reg. No. 51907"],
    },
    "lalbagh": {
        "name": "LALBAGH ENDOCRINE CLINIC",
        "lines": [
            "1st Floor, Ocean Plaza, Lalbagh, Mangaluru - 575003",
            "Ph: 0824 2492020  |  Thyroid, Diabetes & Hormone Disorders",
        ],
        "color": "#8a5a00",
        "signature": ["Dr. Kavya Rai", "MD, DM (Endocrinology)", "KMC Reg. No. 60218"],
    },
    "seabreeze": {
        "name": "SEA BREEZE CHEST & ALLERGY CLINIC",
        "lines": [
            "NH 66, Surathkal, Mangaluru - 575014",
            "Ph: 0824 2477310  |  Asthma, Allergy & Sleep Medicine",
        ],
        "color": "#00707a",
        "signature": ["Dr. Fathima Rizwana", "MD (Pulmonary Medicine)", "KMC Reg. No. 57341"],
    },
    "udyavara": {
        "name": "UDYAVARA GENERAL CLINIC",
        "lines": [
            "Main Road, Udyavara, Udupi - 574118",
            "Ph: 0820 2591144  |  Timings: 9 am - 1 pm, 5 pm - 9 pm",
        ],
        "color": "#5b3a8c",
        "signature": ["Dr. Ganesh Acharya", "MBBS", "KMC Reg. No. 39025"],
    },
    "kudla": {
        "name": "KUDLA KIDNEY CARE CENTRE",
        "lines": [
            "Kankanady Cross Road, Mangaluru - 575002",
            "Ph: 0824 2431818  |  Dialysis unit open 24 hours",
        ],
        "color": "#004f8c",
        "signature": ["Dr. Harish Alva", "MD, DM (Nephrology)", "KMC Reg. No. 52266"],
    },
    "netravati_pharmacy": {
        "name": "NETRAVATI HOSPITAL PHARMACY",
        "lines": [
            "Ground Floor, Netravati Multispeciality Hospital, Falnir Road, Mangaluru - 575002",
            "Ph: 0824 2233460  |  DL No: KA-DK-21B-01177",
        ],
        "color": "#2e7d32",
        "signature": ["Pharmacist", "Netravati Hospital Pharmacy"],
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
                text("Tab. Metformin 500mg BD", med("Metformin", "500mg", "BD", "mentioned")),
                text("Tab. Atenolol 50mg OD", med("Atenolol", "50mg", "OD", "mentioned")),
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
                     med("Metformin", "500mg", "BD", "mentioned", echo_of="d1")),
                text("Tab. Atenolol 50mg OD",
                     med("Atenolol", "50mg", "OD", "mentioned", echo_of="d1")),
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
                     med("Atenolol", "50mg", "OD", "mentioned", echo_of="d1")),
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

# ---------------------------------------------------------------------------
# Patient p2: Mohammed Iqbal. Hypertension + dyslipidaemia
# ---------------------------------------------------------------------------

P2 = {
    "patient_id": "p2",
    "patient": {"name": "Mohammed Iqbal", "dob": "1966-09-03", "sex": "M", "blood_group": "B+"},
    "traps": [
        {"type": "echo", "documents": ["p2_d1", "p2_d5"],
         "note": "d5 discharge meds copy the 2018 list from d1 word-for-word, including the "
                 "old Amlodipine 5mg dose (increased to 10mg in d3)."},
        {"type": "contradiction", "documents": ["p2_d3", "p2_d5"],
         "note": "Atorvastatin stopped in d3 (2020) but listed again in d5 (2022) by copy-paste."},
        {"type": "medication_change", "documents": ["p2_d3"],
         "note": "Amlodipine 5mg -> 10mg; Atorvastatin stopped; Rosuvastatin started."},
        {"type": "unit_mismatch", "documents": ["p2_d2", "p2_d4", "p2_d6"],
         "note": "Cholesterol in mg/dL (d2, d6) vs mmol/L (d4)."},
        {"type": "ambiguous_date", "documents": ["p2_d6"],
         "note": "06/03/2023 could be 6 March or 3 June."},
        {"type": "gap", "documents": [],
         "note": "Allergy status not documented anywhere until the 2022 discharge summary."},
    ],
    "documents": [
        {
            "key": "d1", "filename": "d1_prescription_2018.pdf", "doc_type": "prescription",
            "date": "2018-07-18", "date_raw": "18/07/2018", "hospital": "paduva",
            "title": "PRESCRIPTION",
            "lines": [
                row("Patient: Mohammed Iqbal", "Date: 18/07/2018",
                    demographic("patient_name", "Mohammed Iqbal")),
                row("Sex: Male", "Age: 51 years", demographic("sex", "Male")),
                row("Mobile: +91 98765 11002", "OP No: PFC-18-2231"),
                text("Address: 7-3/12, Azizuddin Road, Bunder, Mangaluru - 575001"),
                RULE,
                text("BP: 168/102 mmHg", lab("Blood pressure", "168/102", "mmHg")),
                text("Diagnosis: Essential hypertension", condition("Essential hypertension")),
                text("Dyslipidaemia", condition("Dyslipidaemia")),
                GAP,
                heading("Rx"),
                text("Tab. Amlodipine 5mg OD", med("Amlodipine", "5mg", "OD", "mentioned")),
                text("Tab. Atorvastatin 10mg HS", med("Atorvastatin", "10mg", "HS", "mentioned")),
                GAP,
                text("Advice: Reduce salt. Walk daily. Lipid profile after 6 months."),
            ],
        },
        {
            "key": "d2", "filename": "d2_lab_2019.pdf", "doc_type": "lab_report",
            "date": "2019-02-14", "date_raw": "14-Feb-2019", "hospital": "coastline",
            "title": "LABORATORY REPORT",
            "lines": [
                row("Patient: Mohammed Iqbal", "Lab ID: CD-190214-0381",
                    demographic("patient_name", "Mohammed Iqbal")),
                row("Sex: Male", "Age: 52 years", demographic("sex", "Male")),
                row("Ref. by: Dr. Suresh Kotian", "Report date: 14-Feb-2019"),
                RULE,
                row("Test / Result", "Reference range"),
                row("Total cholesterol: 246 mg/dL", "< 200 mg/dL",
                    lab("Total cholesterol", "246", "mg/dL", flags=["unit_mismatch"])),
                row("LDL cholesterol: 168 mg/dL", "< 100 mg/dL",
                    lab("LDL cholesterol", "168", "mg/dL", flags=["unit_mismatch"])),
                row("HDL cholesterol: 38 mg/dL", "> 40 mg/dL", lab("HDL cholesterol", "38", "mg/dL")),
                row("Triglycerides: 210 mg/dL", "< 150 mg/dL", lab("Triglycerides", "210", "mg/dL")),
                row("Serum creatinine: 1.0 mg/dL", "0.7 - 1.3 mg/dL",
                    lab("Serum creatinine", "1.0", "mg/dL")),
                GAP,
                text("Method: Enzymatic (CHOD-PAP), Jaffe (creatinine)"),
                text("*** End of report ***"),
            ],
        },
        {
            "key": "d3", "filename": "d3_prescription_2020.pdf", "doc_type": "prescription",
            "date": "2020-09-21", "date_raw": "21/09/2020", "hospital": "paduva",
            "title": "PRESCRIPTION",
            "lines": [
                row("Patient: Mohammed Iqbal", "Date: 21/09/2020",
                    demographic("patient_name", "Mohammed Iqbal")),
                row("Sex: Male", "Age: 54 years", demographic("sex", "Male")),
                row("Mobile: +91 98765 11002", "OP No: PFC-18-2231"),
                RULE,
                text("BP: 150/96 mmHg", lab("Blood pressure", "150/96", "mmHg")),
                text("Diagnosis: Essential hypertension, Dyslipidaemia",
                     condition("Essential hypertension"), condition("Dyslipidaemia")),
                GAP,
                heading("Rx"),
                text("Tab. Amlodipine increased to 10mg OD",
                     med("Amlodipine", "10mg", "OD", "changed")),
                text("Tab. Atorvastatin 10mg HS - stop",
                     med("Atorvastatin", "10mg", "HS", "stopped", flags=["contradiction"])),
                text("Tab. Rosuvastatin 10mg HS - start",
                     med("Rosuvastatin", "10mg", "HS", "started")),
                GAP,
                text("Advice: Home BP monitoring. Review after 2 months."),
            ],
        },
        {
            "key": "d4", "filename": "d4_lab_2021.pdf", "doc_type": "lab_report",
            "date": "2021-03-17", "date_raw": "17/03/2021", "hospital": "bluewave",
            "title": "TEST REPORT",
            "lines": [
                row("Patient: Mr. Mohammed Iqbal", "Sample ID: BW/21/03417",
                    demographic("patient_name", "Mr. Mohammed Iqbal")),
                row("Sex: Male", "Age: 54 Y", demographic("sex", "Male")),
                row("Referred by: Dr. Suresh Kotian", "Date: 17/03/2021"),
                RULE,
                row("Investigation / Result", "Bio. ref. interval"),
                # TRAP unit mismatch: d2 and d6 use mg/dL
                row("Total Cholesterol 4.8 mmol/L", "< 5.2 mmol/L",
                    lab("Total cholesterol", "4.8", "mmol/L", flags=["unit_mismatch"])),
                row("LDL Cholesterol 2.9 mmol/L", "< 2.6 mmol/L",
                    lab("LDL cholesterol", "2.9", "mmol/L", flags=["unit_mismatch"])),
                GAP,
                text("Note: Results relate only to the sample tested."),
            ],
        },
        {
            "key": "d5", "filename": "d5_discharge_2022.pdf", "doc_type": "discharge_summary",
            "date": "2022-11-14", "date_raw": "14-Nov-2022", "hospital": "netravati",
            "title": "DISCHARGE SUMMARY",
            "signature": ["Dr. Nandini Shenoy", "MD (General Medicine)", "Consultant Physician"],
            "lines": [
                row("Patient: Mohammed Iqbal", "IP No: NMH/22/024417",
                    demographic("patient_name", "Mohammed Iqbal")),
                row("Sex: Male", "Age: 56 years", demographic("sex", "Male")),
                row("Blood group: B+", "Mobile: +91 98765 11002",
                    demographic("blood_group", "B+")),
                row("Date of admission: 12-Nov-2022", "Date of discharge: 14-Nov-2022"),
                RULE,
                heading("Presenting complaint"),
                text("Admitted with severe headache and BP 190/110 mmHg.",
                     event("Admission for severe headache", event_date="2022-11-12",
                           date_raw="12-Nov-2022"),
                     lab("Blood pressure", "190/110", "mmHg", event_date="2022-11-12",
                         date_raw="12-Nov-2022")),
                heading("Past history"),
                text("Known case of hypertension and dyslipidaemia.",
                     condition("Hypertension"), condition("Dyslipidaemia")),
                heading("Allergies"),
                text("Allergy: Sulfonamides (rash)", allergy("Sulfonamides", value="rash")),
                heading("Investigations"),
                text("Serum creatinine: 1.1 mg/dL", lab("Serum creatinine", "1.1", "mg/dL")),
                text("CT brain: No acute intracranial bleed",
                     lab("CT brain", "No acute intracranial bleed", None)),
                heading("Final diagnosis"),
                text("Hypertensive urgency", condition("Hypertensive urgency")),
                heading("Discharge medications"),
                # TRAP echo: copied from the 2018 prescription (stale dose, stopped statin)
                text("Tab. Amlodipine 5mg OD",
                     med("Amlodipine", "5mg", "OD", "mentioned", echo_of="d1")),
                text("Tab. Atorvastatin 10mg HS",
                     med("Atorvastatin", "10mg", "HS", "mentioned", echo_of="d1",
                         flags=["contradiction"])),
                text("Tab. Telmisartan 40mg OD - start",
                     med("Telmisartan", "40mg", "OD", "started")),
                GAP,
                text("Advice on discharge: Review in Medicine OPD after 1 week."),
            ],
        },
        {
            "key": "d6", "filename": "d6_lab_2023.pdf", "doc_type": "lab_report",
            "date": "2023-03-06", "date_raw": "06/03/2023", "hospital": "coastline",
            "title": "LABORATORY REPORT", "doc_flags": ["ambiguous_date"],
            "lines": [
                row("Patient: Mohammed Iqbal", "Lab ID: CD-230306-0219",
                    demographic("patient_name", "Mohammed Iqbal")),
                row("Sex: Male", "Age: 56 years", demographic("sex", "Male")),
                row("Ref. by: Dr. Suresh Kotian", "Report date: 06/03/2023"),
                RULE,
                row("Test / Result", "Reference range"),
                row("HbA1c: 6.1 %", "4.0 - 5.6 %", lab("HbA1c", "6.1", "%")),
                row("Fasting blood glucose: 118 mg/dL", "70 - 100 mg/dL",
                    lab("Fasting blood glucose", "118", "mg/dL")),
                row("LDL cholesterol: 92 mg/dL", "< 100 mg/dL",
                    lab("LDL cholesterol", "92", "mg/dL", flags=["unit_mismatch"])),
                GAP,
                text("*** End of report ***"),
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Patient p3: Lakshmi Hegde. Hypothyroidism
# ---------------------------------------------------------------------------

def lakshmi_bluewave_header(sample_id, age, date_raw):
    """The patient block Bluewave prints on each of Lakshmi's reports."""
    return [
        row("Patient: Mrs. Lakshmi Hegde", f"Sample ID: {sample_id}",
            demographic("patient_name", "Mrs. Lakshmi Hegde")),
        row("Sex: Female", f"Age: {age}", demographic("sex", "Female")),
        row("Referred by: Dr. Kavya Rai", f"Date: {date_raw}"),
    ]


P3 = {
    "patient_id": "p3",
    "patient": {"name": "Lakshmi Hegde", "dob": "1978-11-22", "sex": "F", "blood_group": "A+"},
    "traps": [
        {"type": "contradiction", "documents": ["p3_d2", "p3_d5"],
         "note": "d2 'Allergy: Ibuprofen (swelling of lips)'; d5 'No known drug allergies'."},
        {"type": "implicit_dose_change", "documents": ["p3_d2", "p3_d4"],
         "note": "Thyroxine 50mcg (d2) -> 75mcg (d4) with no 'increased' written: "
                 "the extractor must say 'mentioned', not invent 'changed'."},
        {"type": "stale_dose", "documents": ["p3_d4", "p3_d5"],
         "note": "d5 discharge lists Thyroxine 50mcg although d4 (2019) prescribed 75mcg."},
        {"type": "unit_mismatch", "documents": ["p3_d1", "p3_d3", "p3_d6"],
         "note": "TSH in uIU/mL (d1) vs mIU/L (d3, d6). Same scale, different unit text."},
        {"type": "event_date_differs", "documents": ["p3_d5"],
         "note": "Surgery on 16-Mar-2021 inside a summary dated 18-Mar-2021."},
    ],
    "documents": [
        {
            "key": "d1", "filename": "d1_lab_2017.pdf", "doc_type": "lab_report",
            "date": "2017-05-22", "date_raw": "2017-05-22", "hospital": "coastline",
            "title": "LABORATORY REPORT",
            "lines": [
                row("Patient: Lakshmi Hegde", "Lab ID: CD-170522-0644",
                    demographic("patient_name", "Lakshmi Hegde")),
                row("Sex: Female", "Age: 38 years", demographic("sex", "Female")),
                row("Ref. by: Dr. Kavya Rai", "Report date: 2017-05-22"),
                RULE,
                row("Test / Result", "Reference range"),
                row("TSH: 9.8 uIU/mL", "0.4 - 4.5 uIU/mL",
                    lab("TSH", "9.8", "uIU/mL", flags=["unit_mismatch"])),
                row("Free T4: 0.7 ng/dL", "0.8 - 1.8 ng/dL", lab("Free T4", "0.7", "ng/dL")),
                row("Haemoglobin: 11.4 g/dL", "12.0 - 15.0 g/dL",
                    lab("Haemoglobin", "11.4", "g/dL")),
                GAP,
                text("Method: CLIA (thyroid), Automated cell counter (Hb)"),
                text("*** End of report ***"),
            ],
        },
        {
            "key": "d2", "filename": "d2_prescription_2017.pdf", "doc_type": "prescription",
            "date": "2017-05-24", "date_raw": "24/05/2017", "hospital": "lalbagh",
            "title": "PRESCRIPTION",
            "lines": [
                row("Patient: Lakshmi Hegde", "Date: 24/05/2017",
                    demographic("patient_name", "Lakshmi Hegde")),
                row("Sex: Female", "Age: 38 years", demographic("sex", "Female")),
                row("DOB: 22-11-1978", "Mobile: +91 98765 22003",
                    demographic("dob", "22-11-1978")),
                text("Address: Flat 302, Sea View Residency, Kodialbail, Mangaluru - 575003"),
                text("Blood group: A+", demographic("blood_group", "A+")),
                RULE,
                text("Diagnosis: Primary hypothyroidism", condition("Primary hypothyroidism")),
                # TRAP contradiction with d5
                text("Allergy: Ibuprofen (swelling of lips)",
                     allergy("Ibuprofen", value="swelling of lips", flags=["contradiction"])),
                GAP,
                heading("Rx"),
                text("Tab. Thyroxine 50mcg OD - start", med("Thyroxine", "50mcg", "OD", "started")),
                GAP,
                text("Advice: Take on empty stomach, 30 minutes before breakfast."),
            ],
        },
        {
            "key": "d3", "filename": "d3_lab_2019.pdf", "doc_type": "lab_report",
            "date": "2019-08-19", "date_raw": "19/08/2019", "hospital": "bluewave",
            "title": "TEST REPORT",
            "lines": lakshmi_bluewave_header("BW/19/08192", "40 Y", "19/08/2019") + [
                row("ABHA No: 91-5520-7713-4410", "Mobile: 98765 22003"),
                RULE,
                row("Investigation / Result", "Bio. ref. interval"),
                row("TSH 6.4 mIU/L", "0.4 - 4.0 mIU/L",
                    lab("TSH", "6.4", "mIU/L", flags=["unit_mismatch"])),
                row("Vitamin D (25-OH) 14 ng/mL", "30 - 100 ng/mL",
                    lab("Vitamin D (25-OH)", "14", "ng/mL")),
                GAP,
                text("Note: Results relate only to the sample tested."),
            ],
        },
        {
            "key": "d4", "filename": "d4_prescription_2019.pdf", "doc_type": "prescription",
            "date": "2019-08-26", "date_raw": "26/08/2019", "hospital": "lalbagh",
            "title": "PRESCRIPTION",
            "lines": [
                row("Patient: Lakshmi Hegde", "Date: 26/08/2019",
                    demographic("patient_name", "Lakshmi Hegde")),
                row("Sex: Female", "Age: 40 years", demographic("sex", "Female")),
                RULE,
                text("Diagnosis: Primary hypothyroidism, Vitamin D deficiency",
                     condition("Primary hypothyroidism"), condition("Vitamin D deficiency")),
                GAP,
                heading("Rx"),
                # TRAP dose went 50 -> 75mcg but the text never says "increased"
                text("Tab. Thyroxine 75mcg OD", med("Thyroxine", "75mcg", "OD", "mentioned")),
                text("Cap. Cholecalciferol 60000 IU once weekly x 8 weeks",
                     med("Cholecalciferol", "60000 IU", "once weekly", "mentioned")),
                GAP,
                text("Advice: Repeat thyroid test after 3 months."),
            ],
        },
        {
            "key": "d5", "filename": "d5_discharge_2021.pdf", "doc_type": "discharge_summary",
            "date": "2021-03-18", "date_raw": "18-Mar-2021", "hospital": "netravati",
            "title": "DISCHARGE SUMMARY",
            "signature": ["Dr. Ravi Kini", "MS (General Surgery)", "Consultant Surgeon"],
            "lines": [
                row("Patient: Lakshmi Hegde", "IP No: NMH/21/006672",
                    demographic("patient_name", "Lakshmi Hegde")),
                row("Sex: Female", "Age: 42 years", demographic("sex", "Female")),
                row("DOB: 22-11-1978", "Aadhaar: 3390 1458 7726",
                    demographic("dob", "22-11-1978")),
                row("Blood group: A+", "Mobile: +91 98765 22003",
                    demographic("blood_group", "A+")),
                row("Date of admission: 15-Mar-2021", "Date of discharge: 18-Mar-2021"),
                RULE,
                heading("Presenting complaint"),
                text("Admitted with pain in right upper abdomen for 3 days.",
                     event("Admission for right upper abdominal pain", event_date="2021-03-15",
                           date_raw="15-Mar-2021")),
                heading("Past history"),
                text("Known case of hypothyroidism.", condition("Hypothyroidism")),
                heading("Allergies"),
                # TRAP contradiction with d2 (Ibuprofen)
                text("No known drug allergies",
                     allergy("Drug allergy", status="negated", flags=["contradiction"])),
                heading("Investigations"),
                text("USG abdomen: Multiple gall bladder calculi",
                     lab("USG abdomen", "Multiple gall bladder calculi", None)),
                heading("Procedure"),
                # TRAP event_date differs from document_date
                text("Laparoscopic cholecystectomy done on 16-Mar-2021.",
                     event("Laparoscopic cholecystectomy", event_date="2021-03-16",
                           date_raw="16-Mar-2021")),
                heading("Final diagnosis"),
                text("Symptomatic cholelithiasis", condition("Symptomatic cholelithiasis")),
                heading("Discharge medications"),
                # TRAP stale dose: d4 prescribed 75mcg
                text("Tab. Thyroxine 50mcg OD", med("Thyroxine", "50mcg", "OD", "mentioned")),
                text("Tab. Paracetamol 650mg SOS", med("Paracetamol", "650mg", "SOS", "mentioned")),
                GAP,
                text("Advice on discharge: Suture removal after 7 days."),
            ],
        },
        {
            "key": "d6", "filename": "d6_lab_2023.pdf", "doc_type": "lab_report",
            "date": "2023-02-25", "date_raw": "25/02/2023", "hospital": "bluewave",
            "title": "TEST REPORT",
            "lines": lakshmi_bluewave_header("BW/23/02251", "44 Y", "25/02/2023") + [
                RULE,
                row("Investigation / Result", "Bio. ref. interval"),
                row("TSH 2.1 mIU/L", "0.4 - 4.0 mIU/L",
                    lab("TSH", "2.1", "mIU/L", flags=["unit_mismatch"])),
                row("Haemoglobin 9.2 g/dL", "12.0 - 15.0 g/dL", lab("Haemoglobin", "9.2", "g/dL")),
                row("Serum ferritin 8 ng/mL", "15 - 150 ng/mL", lab("Serum ferritin", "8", "ng/mL")),
                GAP,
                text("Note: Results relate only to the sample tested."),
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Patient p4: Arjun D'Souza. Bronchial asthma
# ---------------------------------------------------------------------------

def coastline_asthma_labs(key, filename, doc_flags):
    """d3, and d6 which is an exact copy of it under another filename."""
    return {
        "key": key, "filename": filename, "doc_type": "lab_report",
        "date": "2018-10-22", "date_raw": "2018-10-22", "hospital": "coastline",
        "title": "LABORATORY REPORT", "doc_flags": doc_flags,
        "lines": [
            row("Patient: Arjun D'Souza", "Lab ID: CD-181022-0907",
                demographic("patient_name", "Arjun D'Souza")),
            row("Sex: Male", "Age: 17 years", demographic("sex", "Male")),
            row("Ref. by: Dr. Fathima Rizwana", "Report date: 2018-10-22"),
            RULE,
            row("Test / Result", "Reference range"),
            row("Absolute eosinophil count: 640 cells/cumm", "40 - 440 cells/cumm",
                lab("Absolute eosinophil count", "640", "cells/cumm")),
            row("Serum IgE (total): 480 IU/mL", "< 100 IU/mL",
                lab("Serum IgE (total)", "480", "IU/mL")),
            row("Haemoglobin: 14.6 g/dL", "13.0 - 17.0 g/dL", lab("Haemoglobin", "14.6", "g/dL")),
            GAP,
            text("*** End of report ***"),
        ],
    }


P4 = {
    "patient_id": "p4",
    "patient": {"name": "Arjun D'Souza", "dob": "2001-02-07", "sex": "M", "blood_group": "O-"},
    "traps": [
        {"type": "contradiction", "documents": ["p4_d1", "p4_d5"],
         "note": "d1 'Drug allergy: Aspirin (wheeze)'; d5 'No known drug allergies'."},
        {"type": "echo", "documents": ["p4_d1", "p4_d2", "p4_d5"],
         "note": "d5 (a GP in Udupi, 2022) copies the 2015 discharge inhalers word-for-word, "
                 "including Budesonide which d2 stopped in 2018."},
        {"type": "contradiction", "documents": ["p4_d2", "p4_d5"],
         "note": "Budesonide inhaler stopped in d2 but listed again in d5."},
        {"type": "duplicate", "documents": ["p4_d3", "p4_d6"],
         "note": "d6 is a byte-for-byte copy of d3 under a different filename."},
        {"type": "deidentification", "documents": ["p4_d1"],
         "note": "Father's name 'Mr. Joseph D'Souza' must be redacted too."},
    ],
    "documents": [
        {
            "key": "d1", "filename": "d1_discharge_2015.pdf", "doc_type": "discharge_summary",
            "date": "2015-07-02", "date_raw": "02-Jul-2015", "hospital": "netravati",
            "title": "DISCHARGE SUMMARY",
            "signature": ["Dr. Shalini Pinto", "MD (Paediatrics)", "Consultant Paediatrician"],
            "lines": [
                row("Patient: Arjun D'Souza", "IP No: NMH/15/011208",
                    demographic("patient_name", "Arjun D'Souza")),
                row("Sex: Male", "Age: 14 years", demographic("sex", "Male")),
                row("DOB: 07-02-2001", "Mobile: +91 98765 33004",
                    demographic("dob", "07-02-2001")),
                row("Blood group: O-", "Father: Mr. Joseph D'Souza",
                    demographic("blood_group", "O-")),
                row("Date of admission: 29-Jun-2015", "Date of discharge: 02-Jul-2015"),
                RULE,
                heading("Presenting complaint"),
                text("Admitted with acute exacerbation of bronchial asthma.",
                     event("Admission for acute exacerbation of bronchial asthma",
                           event_date="2015-06-29", date_raw="29-Jun-2015")),
                heading("Past history"),
                text("Known case of bronchial asthma.", condition("Bronchial asthma")),
                heading("Allergies"),
                # TRAP contradiction with d5
                text("Drug allergy: Aspirin (wheeze)",
                     allergy("Aspirin", value="wheeze", flags=["contradiction"])),
                text("Allergic to house dust mite and pollen",
                     allergy("House dust mite"), allergy("Pollen")),
                heading("Investigations"),
                text("SpO2 on admission: 89 %",
                     lab("SpO2", "89", "%", event_date="2015-06-29", date_raw="29-Jun-2015")),
                text("Chest X-ray: Hyperinflated lungs, no consolidation",
                     lab("Chest X-ray", "Hyperinflated lungs, no consolidation", None)),
                heading("Discharge medications"),
                text("Inhaler Budesonide 200mcg 2 puffs BD",
                     med("Budesonide", "200mcg", "2 puffs BD", "mentioned")),
                text("Inhaler Salbutamol 100mcg 2 puffs SOS",
                     med("Salbutamol", "100mcg", "2 puffs SOS", "mentioned")),
                GAP,
                text("Advice: Avoid dust exposure. Inhaler technique explained."),
            ],
        },
        {
            "key": "d2", "filename": "d2_prescription_2018.pdf", "doc_type": "prescription",
            "date": "2018-10-23", "date_raw": "23/10/2018", "hospital": "seabreeze",
            "title": "PRESCRIPTION",
            "lines": [
                row("Patient: Arjun D'Souza", "Date: 23/10/2018",
                    demographic("patient_name", "Arjun D'Souza")),
                row("Sex: Male", "Age: 17 years", demographic("sex", "Male")),
                row("Mobile: +91 98765 33004", "UHID: SBC-1043"),
                RULE,
                text("PEFR: 320 L/min", lab("PEFR", "320", "L/min")),
                text("Diagnosis: Bronchial asthma - moderate persistent",
                     condition("Bronchial asthma - moderate persistent")),
                GAP,
                heading("Rx"),
                text("Inhaler Budesonide 200mcg 2 puffs BD - stop",
                     med("Budesonide", "200mcg", "2 puffs BD", "stopped", flags=["contradiction"])),
                text("Inhaler Budesonide + Formoterol 200/6mcg 2 puffs BD - start",
                     med("Budesonide + Formoterol", "200/6mcg", "2 puffs BD", "started")),
                text("Tab. Montelukast 10mg HS - start", med("Montelukast", "10mg", "HS", "started")),
                text("Inhaler Salbutamol 100mcg 2 puffs SOS",
                     med("Salbutamol", "100mcg", "2 puffs SOS", "mentioned", echo_of="d1")),
                GAP,
                text("Advice: Rinse mouth after inhaler use. Review after 3 months."),
            ],
        },
        coastline_asthma_labs("d3", "d3_lab_2018.pdf", doc_flags=[]),
        {
            "key": "d4", "filename": "d4_prescription_2020.pdf", "doc_type": "prescription",
            "date": "2020-08-14", "date_raw": "14/08/2020", "hospital": "seabreeze",
            "title": "PRESCRIPTION",
            "lines": [
                row("Patient: Arjun D'Souza", "Date: 14/08/2020",
                    demographic("patient_name", "Arjun D'Souza")),
                row("Sex: Male", "Age: 19 years", demographic("sex", "Male")),
                row("Mobile: +91 98765 33004", "UHID: SBC-1043"),
                RULE,
                text("Spirometry: FEV1/FVC 0.68", lab("FEV1/FVC", "0.68", None)),
                text("Post-bronchodilator FEV1 reversibility: 16 %",
                     lab("FEV1 reversibility", "16", "%")),
                text("Diagnosis: Bronchial asthma - partly controlled",
                     condition("Bronchial asthma - partly controlled")),
                GAP,
                heading("Rx"),
                text("Inhaler Budesonide + Formoterol 200/6mcg 2 puffs BD",
                     med("Budesonide + Formoterol", "200/6mcg", "2 puffs BD", "mentioned")),
                text("Tab. Montelukast 10mg HS", med("Montelukast", "10mg", "HS", "mentioned")),
                GAP,
                text("Advice: Annual influenza vaccine. Review after 6 months."),
            ],
        },
        {
            "key": "d5", "filename": "d5_prescription_2022.pdf", "doc_type": "prescription",
            "date": "2022-06-27", "date_raw": "27/06/2022", "hospital": "udyavara",
            "title": "PRESCRIPTION",
            "lines": [
                row("Patient: Arjun D'Souza", "Date: 27/06/2022",
                    demographic("patient_name", "Arjun D'Souza")),
                row("Sex: Male", "Age: 21 years", demographic("sex", "Male")),
                row("Mobile: +91 98765 33004", ""),
                RULE,
                text("Diagnosis: Acute pharyngitis", condition("Acute pharyngitis")),
                text("K/C/O Bronchial asthma", condition("Bronchial asthma")),
                # TRAP contradiction with d1 (Aspirin)
                text("No known drug allergies",
                     allergy("Drug allergy", status="negated", flags=["contradiction"])),
                GAP,
                heading("Rx"),
                text("Tab. Azithromycin 500mg OD x 3 days",
                     med("Azithromycin", "500mg", "OD", "mentioned")),
                text("Tab. Paracetamol 650mg TDS", med("Paracetamol", "650mg", "TDS", "mentioned")),
                # TRAP echo of d1; Budesonide alone was stopped in d2
                text("Inhaler Budesonide 200mcg 2 puffs BD",
                     med("Budesonide", "200mcg", "2 puffs BD", "mentioned", echo_of="d1",
                         flags=["contradiction"])),
                text("Inhaler Salbutamol 100mcg 2 puffs SOS",
                     med("Salbutamol", "100mcg", "2 puffs SOS", "mentioned", echo_of="d1")),
                GAP,
                text("Advice: Warm saline gargles. Review if fever persists."),
            ],
        },
        # TRAP duplicate of d3
        coastline_asthma_labs("d6", "d6_lab_2018_copy.pdf", doc_flags=["duplicate"]),
    ],
}


# ---------------------------------------------------------------------------
# Patient p5: Gopal Bhandary. Chronic kidney disease + diabetes + hypertension
# ---------------------------------------------------------------------------

P5 = {
    "patient_id": "p5",
    "patient": {"name": "Gopal Bhandary", "dob": "1958-08-19", "sex": "M", "blood_group": "AB+"},
    "traps": [
        {"type": "unit_mismatch", "documents": ["p5_d1", "p5_d3", "p5_d4", "p5_d6"],
         "note": "Serum creatinine in mg/dL (d1, d4, d6) vs umol/L (d3)."},
        {"type": "implausible_value", "documents": ["p5_d3"],
         "note": "Potassium 45 mmol/L is impossible (likely 4.5). Original must be kept."},
        {"type": "contradiction", "documents": ["p5_d2", "p5_d4"],
         "note": "d2 'Allergies: None known'; d4 'Allergy: Iodinated contrast (anaphylaxis)'."},
        {"type": "medication_change", "documents": ["p5_d2"],
         "note": "Metformin stopped (CKD), Linagliptin started."},
        {"type": "echo", "documents": ["p5_d2", "p5_d4"],
         "note": "d4 'Tab. Telmisartan 40mg OD' copied word-for-word from d2."},
        {"type": "wrong_patient", "documents": ["p5_d5"],
         "note": "'Mrs. G. Bhandary', female, A+ (likely his wife). Patient is male, AB+. "
                 "Her normal creatinine would hide his kidney disease."},
        {"type": "event_date_differs", "documents": ["p5_d4"],
         "note": "'History of CABG in 2012' written in a 2022 document."},
    ],
    "documents": [
        {
            "key": "d1", "filename": "d1_lab_2020.pdf", "doc_type": "lab_report",
            "date": "2020-01-28", "date_raw": "28/01/2020", "hospital": "bluewave",
            "title": "TEST REPORT",
            "lines": [
                row("Patient: Mr. Gopal Bhandary", "Sample ID: BW/20/01283",
                    demographic("patient_name", "Mr. Gopal Bhandary")),
                row("Sex: Male", "Age: 61 Y", demographic("sex", "Male")),
                row("Referred by: Dr. Harish Alva", "Date: 28/01/2020"),
                row("ABHA No: 91-6631-0927-5518", "Mobile: 98765 44005"),
                RULE,
                row("Investigation / Result", "Bio. ref. interval"),
                row("Serum Creatinine 1.6 mg/dL", "0.7 - 1.3 mg/dL",
                    lab("Serum creatinine", "1.6", "mg/dL", flags=["unit_mismatch"])),
                row("eGFR 46 mL/min/1.73m2", "> 90 mL/min/1.73m2",
                    lab("eGFR", "46", "mL/min/1.73m2")),
                row("Urine ACR 180 mg/g", "< 30 mg/g", lab("Urine ACR", "180", "mg/g")),
                row("Potassium 4.6 mmol/L", "3.5 - 5.1 mmol/L", lab("Potassium", "4.6", "mmol/L")),
                row("HbA1c 7.9 %", "< 5.7 %", lab("HbA1c", "7.9", "%")),
                GAP,
                text("Note: Results relate only to the sample tested."),
            ],
        },
        {
            "key": "d2", "filename": "d2_prescription_2020.pdf", "doc_type": "prescription",
            "date": "2020-01-30", "date_raw": "30/01/2020", "hospital": "kudla",
            "title": "OUT-PATIENT PRESCRIPTION",
            "lines": [
                row("Patient: Gopal Bhandary", "Date: 30/01/2020",
                    demographic("patient_name", "Gopal Bhandary")),
                row("Sex: Male", "Age: 61 years", demographic("sex", "Male")),
                row("DOB: 19-08-1958", "Mobile: +91 98765 44005",
                    demographic("dob", "19-08-1958")),
                text("Address: 2-114, Temple Road, Kankanady, Mangaluru - 575002"),
                text("Blood group: AB+", demographic("blood_group", "AB+")),
                RULE,
                text("BP: 146/88 mmHg", lab("Blood pressure", "146/88", "mmHg")),
                text("Diagnosis: Chronic kidney disease stage 3a",
                     condition("Chronic kidney disease stage 3a")),
                text("Type 2 diabetes mellitus, Hypertension",
                     condition("Type 2 diabetes mellitus"), condition("Hypertension")),
                # TRAP contradiction with d4 (contrast allergy)
                text("Allergies: None known",
                     allergy("Allergies", status="negated", flags=["contradiction"])),
                GAP,
                heading("Rx"),
                text("Tab. Metformin 500mg BD - stop", med("Metformin", "500mg", "BD", "stopped")),
                text("Tab. Linagliptin 5mg OD - start", med("Linagliptin", "5mg", "OD", "started")),
                text("Tab. Telmisartan 40mg OD", med("Telmisartan", "40mg", "OD", "mentioned")),
                GAP,
                text("Advice: Avoid painkillers (NSAIDs). Low salt, low protein diet."),
            ],
        },
        {
            "key": "d3", "filename": "d3_lab_2021.pdf", "doc_type": "lab_report",
            "date": "2021-07-19", "date_raw": "2021-07-19", "hospital": "coastline",
            "title": "LABORATORY REPORT",
            "lines": [
                row("Patient: Gopal Bhandary", "Lab ID: CD-210719-0533",
                    demographic("patient_name", "Gopal Bhandary")),
                row("Sex: Male", "Age: 62 years", demographic("sex", "Male")),
                row("Ref. by: Dr. Harish Alva", "Report date: 2021-07-19"),
                RULE,
                row("Test / Result", "Reference range"),
                # TRAP unit mismatch: umol/L here, mg/dL elsewhere
                row("Serum creatinine: 141 umol/L", "62 - 115 umol/L",
                    lab("Serum creatinine", "141", "umol/L", flags=["unit_mismatch"])),
                row("eGFR: 44 mL/min/1.73m2", "> 90 mL/min/1.73m2",
                    lab("eGFR", "44", "mL/min/1.73m2")),
                # TRAP implausible value (likely 4.5)
                row("Potassium: 45 mmol/L", "3.5 - 5.1 mmol/L",
                    lab("Potassium", "45", "mmol/L", flags=["implausible_value"])),
                row("Sodium: 138 mmol/L", "135 - 145 mmol/L", lab("Sodium", "138", "mmol/L")),
                GAP,
                text("*** End of report ***"),
            ],
        },
        {
            "key": "d4", "filename": "d4_discharge_2022.pdf", "doc_type": "discharge_summary",
            "date": "2022-09-09", "date_raw": "09-Sep-2022", "hospital": "netravati",
            "title": "DISCHARGE SUMMARY",
            "signature": ["Dr. Vinay Prabhu", "MD, DM (Nephrology)", "Consultant Nephrologist"],
            "lines": [
                row("Patient: Gopal Bhandary", "IP No: NMH/22/021190",
                    demographic("patient_name", "Gopal Bhandary")),
                row("Sex: Male", "Age: 64 years", demographic("sex", "Male")),
                row("DOB: 19-08-1958", "Aadhaar: 5712 6604 9183",
                    demographic("dob", "19-08-1958")),
                row("Blood group: AB+", "Mobile: +91 98765 44005",
                    demographic("blood_group", "AB+")),
                row("Date of admission: 05-Sep-2022", "Date of discharge: 09-Sep-2022"),
                RULE,
                heading("Presenting complaint"),
                text("Admitted with reduced urine output and swelling of legs.",
                     event("Admission for reduced urine output and leg swelling",
                           event_date="2022-09-05", date_raw="05-Sep-2022")),
                heading("Past history"),
                text("Known case of CKD stage 3a, type 2 diabetes mellitus and hypertension.",
                     condition("Chronic kidney disease stage 3a"),
                     condition("Type 2 diabetes mellitus"), condition("Hypertension")),
                # TRAP event_date differs from document_date
                text("History of CABG in 2012.",
                     event("CABG", event_date="2012-01-01", date_raw="2012")),
                heading("Allergies"),
                text("Allergy: Iodinated contrast (anaphylaxis)",
                     allergy("Iodinated contrast", value="anaphylaxis", flags=["contradiction"])),
                heading("Investigations"),
                text("Serum creatinine: 2.8 mg/dL",
                     lab("Serum creatinine", "2.8", "mg/dL", flags=["unit_mismatch"])),
                text("Potassium: 5.4 mmol/L", lab("Potassium", "5.4", "mmol/L")),
                heading("Final diagnosis"),
                text("Acute kidney injury on chronic kidney disease",
                     condition("Acute kidney injury on chronic kidney disease")),
                heading("Discharge medications"),
                text("Tab. Linagliptin 5mg OD", med("Linagliptin", "5mg", "OD", "mentioned")),
                # TRAP echo of d2
                text("Tab. Telmisartan 40mg OD",
                     med("Telmisartan", "40mg", "OD", "mentioned", echo_of="d2")),
                text("Tab. Furosemide 40mg OD - start", med("Furosemide", "40mg", "OD", "started")),
                GAP,
                text("Advice on discharge: Fluid restriction 1.5 litres/day."),
            ],
        },
        # TRAP wrong patient: his wife's report filed in his folder
        {
            "key": "d5", "filename": "d5_lab_2023.pdf", "doc_type": "lab_report",
            "date": "2023-04-13", "date_raw": "13/04/2023", "hospital": "bluewave",
            "title": "TEST REPORT", "held_back": True, "doc_flags": ["wrong_patient"],
            "lines": [
                row("Patient: Mrs. G. Bhandary", "Sample ID: BW/23/04137",
                    demographic("patient_name", "Mrs. G. Bhandary")),
                row("Sex: Female", "Age: 58 Y", demographic("sex", "Female")),
                row("Referred by: Dr. Harish Alva", "Date: 13/04/2023"),
                row("Blood group: A+", "Mobile: 98765 44005", demographic("blood_group", "A+")),
                RULE,
                row("Investigation / Result", "Bio. ref. interval"),
                row("Serum Creatinine 0.8 mg/dL", "0.5 - 1.1 mg/dL",
                    lab("Serum creatinine", "0.8", "mg/dL")),
                row("Haemoglobin 12.1 g/dL", "12.0 - 15.0 g/dL", lab("Haemoglobin", "12.1", "g/dL")),
                GAP,
                text("Note: Results relate only to the sample tested."),
            ],
        },
        {
            "key": "d6", "filename": "d6_lab_2023.pdf", "doc_type": "lab_report",
            "date": "2023-05-19", "date_raw": "2023-05-19", "hospital": "coastline",
            "title": "LABORATORY REPORT",
            "lines": [
                row("Patient: Gopal Bhandary", "Lab ID: CD-230519-0748",
                    demographic("patient_name", "Gopal Bhandary")),
                row("Sex: Male", "Age: 64 years", demographic("sex", "Male")),
                row("Ref. by: Dr. Harish Alva", "Report date: 2023-05-19"),
                RULE,
                row("Test / Result", "Reference range"),
                row("Serum creatinine: 2.1 mg/dL", "0.7 - 1.3 mg/dL",
                    lab("Serum creatinine", "2.1", "mg/dL", flags=["unit_mismatch"])),
                row("eGFR: 33 mL/min/1.73m2", "> 90 mL/min/1.73m2",
                    lab("eGFR", "33", "mL/min/1.73m2")),
                row("HbA1c: 7.4 %", "4.0 - 5.6 %", lab("HbA1c", "7.4", "%")),
                row("Potassium: 5.1 mmol/L", "3.5 - 5.1 mmol/L", lab("Potassium", "5.1", "mmol/L")),
                GAP,
                text("*** End of report ***"),
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Patient p6: Ravi Kumar. Knee replacement with implant (Claim Documents checklist)
# ---------------------------------------------------------------------------

BILLING_SIGNATURE = ["Billing Section", "Netravati Multispeciality Hospital"]
ORTHO_SIGNATURE = ["Dr. Kiran Pai", "MS (Orthopaedics)", "Consultant Orthopaedic Surgeon"]

P6 = {
    "patient_id": "p6",
    "patient": {"name": "Ravi Kumar", "dob": "1968-03-21", "sex": "M", "blood_group": "B+"},
    "traps": [
        {"type": "claim_documents", "documents": ["p6_d1", "p6_d2", "p6_d3", "p6_d4", "p6_d5"],
         "note": "One hospital stay (05/10/2026 to 09/10/2026) with surgery and an implant. "
                 "Saved: discharge summary, final bill, pharmacy bill, lab report, prescription. "
                 "Deliberately missing: payment receipt, implant invoice, operation notes. "
                 "After surgery=yes, implant=yes, accident=no the checklist shows 5 of 8 saved."},
    ],
    "documents": [
        {
            "key": "d1", "filename": "d1_lab_2026.pdf", "doc_type": "lab_report",
            "date": "2026-10-05", "date_raw": "05/10/2026", "hospital": "netravati",
            "title": "LABORATORY REPORT", "signature": ["Dr. Shruti Rao", "MD (Pathology)", "Consultant Pathologist"],
            "lines": [
                row("Patient: Mr. Ravi Kumar", "Lab ID: NMH/L/26/8841",
                    demographic("patient_name", "Mr. Ravi Kumar")),
                row("Sex: Male", "Age: 58 years", demographic("sex", "Male")),
                row("Ref. by: Dr. Kiran Pai", "Report date: 05/10/2026"),
                RULE,
                row("Test / Result", "Reference range"),
                row("Haemoglobin 13.6 g/dL", "13.0 - 17.0 g/dL", lab("Haemoglobin", "13.6", "g/dL")),
                row("Serum creatinine 1.0 mg/dL", "0.7 - 1.3 mg/dL", lab("Serum creatinine", "1.0", "mg/dL")),
                row("Random blood sugar 118 mg/dL", "70 - 140 mg/dL", lab("Random blood sugar", "118", "mg/dL")),
                text("Blood group: B+", demographic("blood_group", "B+")),
                GAP,
                text("*** End of report ***"),
            ],
        },
        {
            "key": "d2", "filename": "d2_discharge_2026.pdf", "doc_type": "discharge_summary",
            "date": "2026-10-09", "date_raw": "09/10/2026", "hospital": "netravati",
            "title": "DISCHARGE SUMMARY", "signature": ORTHO_SIGNATURE,
            "lines": [
                row("Patient: Mr. Ravi Kumar", "IP No: NMH/26/10512",
                    demographic("patient_name", "Mr. Ravi Kumar")),
                row("Sex: Male", "Age: 58 years", demographic("sex", "Male")),
                row("DOB: 21-03-1968", "Blood group: B+", demographic("dob", "21-03-1968"),
                    demographic("blood_group", "B+", quote="Blood group: B+")),
                row("Date of admission: 05/10/2026", "Date of discharge: 09/10/2026"),
                RULE,
                heading("Reason for admission"),
                text("Admitted for elective right total knee replacement",
                     event("Admission for right total knee replacement", event_date="2026-10-05",
                           date_raw="05/10/2026")),
                heading("Diagnosis"),
                text("Osteoarthritis of right knee", condition("Osteoarthritis of right knee")),
                text("Hypertension", condition("Hypertension")),
                heading("Procedure"),
                text("Right total knee replacement done on 06/10/2026",
                     event("Right total knee replacement", event_date="2026-10-06", date_raw="06/10/2026")),
                text("Implant: cemented knee prosthesis (see implant invoice)"),
                text("Allergies: No known drug allergies", allergy("Drug allergy", status="negated")),
                heading("Discharge medications"),
                text("Tab. Paracetamol 650mg TDS for 5 days", med("Paracetamol", "650mg", "TDS", "started")),
                text("Inj. Enoxaparin 40mg OD for 10 days", med("Enoxaparin", "40mg", "OD", "started")),
                text("Tab. Amlodipine 5mg OD", med("Amlodipine", "5mg", "OD", "continued")),
                GAP,
                text("Follow-up: Orthopaedics OPD after 2 weeks."),
            ],
        },
        {
            "key": "d3", "filename": "d3_final_bill_2026.pdf", "doc_type": "final_bill",
            "date": "2026-10-09", "date_raw": "09/10/2026", "hospital": "netravati",
            "title": "FINAL BILL", "signature": BILLING_SIGNATURE,
            "lines": [
                row("Patient: Mr. Ravi Kumar", "Bill No: NMH/B/26/20877",
                    demographic("patient_name", "Mr. Ravi Kumar")),
                row("IP No: NMH/26/10512", "Bill date: 09/10/2026"),
                row("Admitted: 05/10/2026", "Discharged: 09/10/2026"),
                RULE,
                row("Particulars", "Amount (Rs.)"),
                row("Room charges (4 days)", "14,000.00"),
                row("Surgeon and anaesthetist fees", "65,000.00"),
                row("Operation theatre charges", "30,000.00"),
                row("Knee implant", "95,000.00"),
                row("Pharmacy (in-patient)", "12,450.00"),
                row("Laboratory and imaging", "6,800.00"),
                RULE,
                row("Total", "2,23,250.00"),
                GAP,
                text("Itemised bill. Payment received separately."),
            ],
        },
        {
            "key": "d4", "filename": "d4_pharmacy_bill_2026.pdf", "doc_type": "pharmacy_bill",
            "date": "2026-10-09", "date_raw": "09/10/2026", "hospital": "netravati_pharmacy",
            "title": "PHARMACY BILL", "lines": [
                row("Patient: Ravi Kumar", "Bill No: NHP/26/55102",
                    demographic("patient_name", "Ravi Kumar")),
                row("Prescribed by: Dr. Kiran Pai", "Date: 09/10/2026"),
                RULE,
                row("Item", "Amount (Rs.)"),
                row("Tab. Paracetamol 650mg x 15", "45.00", med("Paracetamol", "650mg", None, "mentioned")),
                row("Inj. Enoxaparin 40mg x 10", "3,850.00", med("Enoxaparin", "40mg", None, "mentioned")),
                row("Tab. Amlodipine 5mg x 30", "60.00", med("Amlodipine", "5mg", None, "mentioned")),
                RULE,
                row("Total", "3,955.00"),
                GAP,
                text("Prescription copy attached."),
            ],
        },
        {
            "key": "d5", "filename": "d5_prescription_2026.pdf", "doc_type": "prescription",
            "date": "2026-10-09", "date_raw": "09/10/2026", "hospital": "netravati",
            "title": "PRESCRIPTION", "signature": ORTHO_SIGNATURE,
            "lines": [
                row("Patient: Ravi Kumar", "Date: 09/10/2026", demographic("patient_name", "Ravi Kumar")),
                row("Sex: Male", "Age: 58 years", demographic("sex", "Male")),
                RULE,
                heading("Rx"),
                text("Tab. Paracetamol 650mg TDS x 5 days", med("Paracetamol", "650mg", "TDS", "started")),
                text("Inj. Enoxaparin 40mg OD x 10 days", med("Enoxaparin", "40mg", "OD", "started")),
                text("Tab. Amlodipine 5mg OD - continue", med("Amlodipine", "5mg", "OD", "continued")),
                GAP,
                text("Advice: Physiotherapy daily. Review in Orthopaedics OPD after 2 weeks."),
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Patient p7: Nisha Pai. Community-acquired pneumonia (in-page search tests)
# ---------------------------------------------------------------------------

CHEST_SIGNATURE = ["Dr. Fathima Rizwana", "MD (Pulmonary Medicine)", "KMC Reg. No. 57341"]
RADIOLOGY_SIGNATURE = ["Dr. Arvind Hegde", "MD (Radiodiagnosis)", "Consultant Radiologist"]

P7 = {
    "patient_id": "p7",
    "patient": {"name": "Nisha Pai", "dob": "1971-09-02", "sex": "F", "blood_group": "A+"},
    "traps": [
        {"type": "search", "documents": ["p7_d3", "p7_d4", "p7_d5"],
         "note": "Search 'pneumonia': only the Augmentin line and the X-ray impression name it. "
                 "Azithromycin and Paracetamol are on the same prescription and the CRP report is "
                 "from the same day: found as 'same visit'. The 2024 diabetes visit is unrelated. "
                 "'Glycomet' is a brand of Metformin (d1)."},
    ],
    "documents": [
        {
            "key": "d1", "filename": "d1_prescription_2024.pdf", "doc_type": "prescription",
            "date": "2024-05-20", "date_raw": "20/05/2024", "hospital": "paduva",
            "title": "PRESCRIPTION",
            "lines": [
                row("Patient: Mrs. Nisha Pai", "Date: 20/05/2024", demographic("patient_name", "Mrs. Nisha Pai")),
                row("Sex: Female", "Age: 52 years", demographic("sex", "Female")),
                text("Blood group: A+", demographic("blood_group", "A+")),
                RULE,
                heading("Diagnosis"),
                text("Type 2 diabetes mellitus", condition("Type 2 diabetes mellitus")),
                heading("Rx"),
                text("Tab. Metformin 500mg BD", med("Metformin", "500mg", "BD", "started")),
                text("Tab. Atorvastatin 10mg HS", med("Atorvastatin", "10mg", "HS", "started")),
                GAP,
                text("Advice: Diet control, walk 30 minutes daily. Review after 3 months."),
            ],
        },
        {
            "key": "d2", "filename": "d2_lab_2024.pdf", "doc_type": "lab_report",
            "date": "2024-05-20", "date_raw": "20/05/2024", "hospital": "coastline",
            "title": "LABORATORY REPORT",
            "lines": [
                row("Patient: Mrs. Nisha Pai", "Sample ID: CD/24/05311", demographic("patient_name", "Mrs. Nisha Pai")),
                row("Sex: Female", "Report date: 20/05/2024", demographic("sex", "Female")),
                RULE,
                row("Test / Result", "Reference range"),
                row("HbA1c 7.6 %", "4.0 - 5.6 %", lab("HbA1c", "7.6", "%")),
                row("Fasting glucose 142 mg/dL", "70 - 100 mg/dL", lab("Fasting glucose", "142", "mg/dL")),
                GAP,
                text("*** End of report ***"),
            ],
        },
        {
            "key": "d3", "filename": "d3_prescription_2025.pdf", "doc_type": "prescription",
            "date": "2025-11-03", "date_raw": "03/11/2025", "hospital": "seabreeze",
            "title": "PRESCRIPTION", "signature": CHEST_SIGNATURE,
            "lines": [
                row("Patient: Mrs. Nisha Pai", "Date: 03/11/2025", demographic("patient_name", "Mrs. Nisha Pai")),
                row("Sex: Female", "Age: 54 years", demographic("sex", "Female")),
                RULE,
                heading("Diagnosis"),
                text("Community-acquired pneumonia (right lower lobe)",
                     condition("Community-acquired pneumonia (right lower lobe)")),
                heading("Rx"),
                text("Tab. Augmentin 625mg BD x 7 days - for pneumonia", med("Augmentin", "625mg", "BD", "started")),
                text("Tab. Azithromycin 500mg OD x 3 days", med("Azithromycin", "500mg", "OD", "started")),
                text("Tab. Paracetamol 650mg SOS for fever", med("Paracetamol", "650mg", "SOS", "started")),
                GAP,
                text("Advice: Blood tests and X-ray today. Review after 3 days."),
            ],
        },
        {
            "key": "d4", "filename": "d4_lab_crp_2025.pdf", "doc_type": "lab_report",
            "date": "2025-11-03", "date_raw": "03/11/2025", "hospital": "coastline",
            "title": "LABORATORY REPORT",
            "lines": [
                row("Patient: Mrs. Nisha Pai", "Sample ID: CD/25/11042", demographic("patient_name", "Mrs. Nisha Pai")),
                row("Sex: Female", "Report date: 03/11/2025", demographic("sex", "Female")),
                RULE,
                row("Test / Result", "Reference range"),
                row("C-reactive protein (CRP) 86 mg/L", "< 6 mg/L", lab("C-reactive protein (CRP)", "86", "mg/L")),
                row("Total WBC count 14,200 cells/cumm", "4,000 - 11,000 cells/cumm",
                    lab("Total WBC count", "14,200", "cells/cumm")),
                row("Neutrophils 82 %", "40 - 75 %", lab("Neutrophils", "82", "%")),
                GAP,
                text("*** End of report ***"),
            ],
        },
        {
            "key": "d5", "filename": "d5_chest_xray_2025.pdf", "doc_type": "lab_report",
            "date": "2025-11-03", "date_raw": "03/11/2025", "hospital": "coastline",
            "title": "RADIOLOGY REPORT", "signature": RADIOLOGY_SIGNATURE,
            "lines": [
                row("Patient: Mrs. Nisha Pai", "Ref. by: Dr. Fathima Rizwana", demographic("patient_name", "Mrs. Nisha Pai")),
                row("Sex: Female", "Date: 03/11/2025", demographic("sex", "Female")),
                RULE,
                heading("Chest X-ray (PA view)"),
                text("Findings: Patchy consolidation in the right lower zone",
                     lab("Chest X-ray", "Patchy consolidation in the right lower zone", None)),
                text("Costophrenic angles clear. Heart size normal."),
                heading("Impression"),
                text("Right lower lobe pneumonia", condition("Right lower lobe pneumonia")),
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Patient p8: Meena Shenoy, for the doctor features (care team, refill requests).
# Her current Metformin is an IN-APP prescription from Dr. Rao (backend/demo_care_team.py);
# these PDFs give her history: type 2 diabetes and a sulfa allergy on record.
# ---------------------------------------------------------------------------

P8 = {
    "patient_id": "p8",
    "patient": {"name": "Meena Shenoy", "dob": "1966-07-02", "sex": "F", "blood_group": "A+"},
    "traps": [
        {"type": "refill_review", "documents": ["p8_d1", "p8_d2", "p8_d3"],
         "note": "Sulfa allergy documented in the 2024 discharge summary. A refill review re-runs "
                 "the allergy check, so a sulfonylurea (e.g. Glimepiride) would warn."},
    ],
    "documents": [
        {
            "key": "d1", "filename": "d1_discharge_2024.pdf", "doc_type": "discharge_summary",
            "date": "2024-02-14", "date_raw": "14/02/2024", "hospital": "netravati",
            "title": "DISCHARGE SUMMARY",
            "lines": [
                row("Patient: Mrs. Meena Shenoy", "IP No: NMH/24/02231",
                    demographic("patient_name", "Mrs. Meena Shenoy")),
                row("Sex: Female", "Age: 57 years", demographic("sex", "Female")),
                row("DOB: 02-07-1966", "Blood group: A+", demographic("dob", "02-07-1966"),
                    demographic("blood_group", "A+", quote="Blood group: A+")),
                row("Date of admission: 11/02/2024", "Date of discharge: 14/02/2024"),
                RULE,
                heading("Reason for admission"),
                text("Admitted with urinary tract infection and high blood sugar",
                     event("Admission for urinary tract infection", event_date="2024-02-11",
                           date_raw="11/02/2024")),
                heading("Diagnosis"),
                text("Type 2 diabetes mellitus", condition("Type 2 diabetes mellitus")),
                text("Urinary tract infection", condition("Urinary tract infection")),
                heading("Allergies"),
                text("Allergy: Sulfa drugs (skin rash on co-trimoxazole)", allergy("Sulfa drugs")),
                heading("Discharge medications"),
                text("Tab. Metformin 500mg BD", med("Metformin", "500mg", "BD", "started")),
                text("Tab. Nitrofurantoin 100mg BD for 5 days", med("Nitrofurantoin", "100mg", "BD", "started")),
                GAP,
                text("Follow-up: Diabetes clinic after 1 month."),
            ],
        },
        {
            "key": "d2", "filename": "d2_lab_2026.pdf", "doc_type": "lab_report",
            "date": "2026-08-20", "date_raw": "20/08/2026", "hospital": "bluewave",
            "title": "LABORATORY REPORT",
            "lines": [
                row("Patient: Mrs. Meena Shenoy", "Sample ID: BW/26/31877",
                    demographic("patient_name", "Mrs. Meena Shenoy")),
                row("Sex: Female", "Age: 60 years", demographic("sex", "Female")),
                row("Collected: 20/08/2026", "Reported: 20/08/2026"),
                RULE,
                row("Test / Result", "Reference range"),
                row("HbA1c 7.4 %", "4.0 - 5.6 %", lab("HbA1c", "7.4", "%")),
                row("Fasting blood sugar 142 mg/dL", "70 - 100 mg/dL", lab("Fasting blood sugar", "142", "mg/dL")),
                row("Serum creatinine 0.9 mg/dL", "0.6 - 1.1 mg/dL", lab("Serum creatinine", "0.9", "mg/dL")),
                text("Blood group: A+", demographic("blood_group", "A+")),
                GAP,
                text("*** End of report ***"),
            ],
        },
        {
            "key": "d3", "filename": "d3_prescription_2026.pdf", "doc_type": "prescription",
            "date": "2026-08-22", "date_raw": "22/08/2026", "hospital": "karavali",
            "title": "PRESCRIPTION",
            "lines": [
                row("Patient: Meena Shenoy", "Date: 22/08/2026", demographic("patient_name", "Meena Shenoy")),
                row("Sex: Female", "Age: 60 years", demographic("sex", "Female")),
                RULE,
                text("Diagnosis: Type 2 diabetes mellitus", condition("Type 2 diabetes mellitus")),
                text("Known allergy: Sulfa drugs", allergy("Sulfa drugs")),
                heading("Rx"),
                text("Tab. Metformin 500mg BD - continue", med("Metformin", "500mg", "BD", "continued")),
                GAP,
                text("Advice: Diet control, walk 30 minutes daily. Review with HbA1c in 3 months."),
            ],
        },
    ],
}

PATIENTS = [P1, P2, P3, P4, P5, P6, P7, P8]


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
    for line in doc.get("signature", hospital["signature"]):  # a document may name its own doctor
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

def main(only=()):
    os.makedirs(os.path.join(DATA_DIR, "answer_keys"), exist_ok=True)
    for patient in PATIENTS:
        if only and patient["patient_id"] not in only:
            continue
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
    main(sys.argv[1:])
