"""Who should answer a question: the patient first, or the doctor directly (AGENTIC_PLAN point 7).

Plain rules, no AI:
  to the DOCTOR (clinical: a patient can't safely settle it)
    - a report in the record may belong to someone else (wrong_patient)
    - a test value that is not possible (implausible_value)
    - allergy or medicine records that contradict each other
  to the PATIENT first (they know their own life; "I don't know" moves it to the doctor)
    - "are you still taking ...?" for copied medicines
    - gaps ("do you have any allergies?")
    - condition records that disagree

route(fact_ids, facts_by_id) -> ("doctor" | "patient", reason)
doctor_only_questions(conn, patient_id, docs) -> [(fact_ids, {"en", "kn"})]  wrong-patient + impossible-value
"""
from backend.routes.fact_helpers import describe, load_facts, source_label

CLINICAL_CONTRADICTION = {"allergy", "medication"}


def route(fact_ids, facts_by_id):
    facts = [facts_by_id[i] for i in fact_ids if i in facts_by_id]
    flags = {flag for f in facts for flag in f.get("flags", [])}
    types = {f.get("type") for f in facts}
    if "wrong_patient" in flags:
        return "doctor", "a report in these records may belong to someone else"
    if "implausible_value" in flags:
        return "doctor", "a test value that is not possible (likely a typing or unit error)"
    if "contradiction" in flags and types & CLINICAL_CONTRADICTION:
        what = "allergy" if "allergy" in types else "medicine"
        return "doctor", f"clinical conflict: the {what} records disagree"
    if "contradiction" in flags:
        return "patient", "the patient may know which record is right"
    if any(f.get("echo_of") for f in facts):
        return "patient", "only the patient knows if they still take it"
    return "patient", "the patient may know; if not, it goes to the doctor"


def wrong_patient_questions(conn, patient_id, docs):
    facts = load_facts(conn, patient_id, include_held_back=True)
    by_doc = {}
    for f in facts:
        if "wrong_patient" in f.get("flags", []):
            by_doc.setdefault(f["document_id"], []).append(f)
    questions = []
    for doc_id, doc_facts in sorted(by_doc.items()):
        first = doc_facts[0]
        label, label_kn = source_label(first, docs), source_label(first, docs, "kn")
        found = ", ".join(f'{f["name"]} "{f["value"]}"' for f in doc_facts if f["type"] == "demographic" and f.get("value"))
        text = (f"The {label} may belong to someone else{f' ({found})' if found else ''}, so it is held back "
                f"from the timeline. Please check the original and decide if it belongs to this patient.")
        text_kn = (f"{label_kn} ಬೇರೆಯವರದ್ದಾಗಿರಬಹುದು{f' ({found})' if found else ''}, ಆದ್ದರಿಂದ ಅದನ್ನು ಟೈಮ್‌ಲೈನ್‌ನಿಂದ "
                   f"ತಡೆಹಿಡಿಯಲಾಗಿದೆ. ಮೂಲ ದಾಖಲೆಯನ್ನು ನೋಡಿ, ಇದು ಈ ರೋಗಿಯದ್ದೇ ಎಂದು ನಿರ್ಧರಿಸಿ.")
        questions.append(([f["fact_id"] for f in doc_facts], {"en": text, "kn": text_kn}))
    return questions


def implausible_questions(conn, patient_id, docs):
    questions = []
    for f in load_facts(conn, patient_id):
        if "implausible_value" not in f.get("flags", []):
            continue
        text = (f'{describe(f)} in the {source_label(f, docs)} ("{f["quote"]}") is not a possible value. '
                f"It may be a typing or unit error. Please check the original report.")
        text_kn = (f'{source_label(f, docs, "kn")}ಯಲ್ಲಿನ {describe(f)} ("{f["quote"]}") ಸಾಧ್ಯವಿರುವ ಮೌಲ್ಯವಲ್ಲ. '
                   f"ಇದು ಟೈಪಿಂಗ್ ಅಥವಾ ಘಟಕದ ತಪ್ಪಾಗಿರಬಹುದು. ದಯವಿಟ್ಟು ಮೂಲ ವರದಿಯನ್ನು ನೋಡಿ.")
        questions.append(([f["fact_id"]], {"en": text, "kn": text_kn}))
    return questions


def doctor_only_questions(conn, patient_id, docs):
    return wrong_patient_questions(conn, patient_id, docs) + implausible_questions(conn, patient_id, docs)
