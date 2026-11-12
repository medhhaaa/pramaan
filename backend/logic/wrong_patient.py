"""Wrong-patient detection. (Core backend)

A document whose blood group or sex disagrees with the patient's record is probably
someone else's (e.g. Dad's report in Mom's folder). Plain code, no AI.

find_conflicts(document_facts, patient) -> list of plain-language reasons
    empty list = no conflict. patient is the patients-table row (dict).
The upload route flags the document's facts as wrong_patient and holds the
document back from the timeline when this list is not empty.
"""


def normalise_blood_group(text):
    """'O+', 'o +ve', 'O positive' -> 'O+'"""
    t = (text or "").upper().replace(" ", "")
    t = t.replace("POSITIVE", "+").replace("NEGATIVE", "-").replace("+VE", "+").replace("-VE", "-")
    return t


def normalise_sex(text):
    """'Male', 'M', 'male' -> 'M'"""
    t = (text or "").strip().upper()
    return t[:1] if t[:1] in ("M", "F") else t


CHECKS = [
    # (demographic fact name, patients-table column, normaliser, label)
    ("blood_group", "blood_group", normalise_blood_group, "Blood group"),
    ("sex", "sex", normalise_sex, "Sex"),
]


def find_conflicts(document_facts, patient):
    reasons = []
    for fact in document_facts:
        if fact.get("type") != "demographic" or fact.get("status") != "documented":
            continue
        for name, column, normalise, label in CHECKS:
            on_record = patient.get(column)
            if fact.get("name") == name and on_record and fact.get("value"):
                if normalise(fact["value"]) != normalise(on_record):
                    reasons.append(f'{label} in this document is "{fact["value"]}" '
                                   f'but the patient record says "{on_record}"')
    return reasons
