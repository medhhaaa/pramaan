"""Trust badges: how much should you trust this fact? (Deeksha, P2)

Checked in this order, the first that applies wins:
    doctor_verified    a doctor confirmed or corrected it
    (no badge)         it is an echo (copy), a duplicate, or from a suspected wrong patient
    conflicting        another document contradicts it
    patient_reported   the patient answered a question about it
    independent_2plus  the same fact is in 2+ independent documents
    single_document    only one document says it

Independent documents don't count echoes, duplicates or wrong-patient facts, so
"4 mentions" from copy-paste is still one piece of evidence.
Pure function: facts in, facts out, no database.
"""
from collections import defaultdict

from backend.logic.flags import same_name

NOT_EVIDENCE_FLAGS = {"duplicate", "wrong_patient"}


def is_independent(fact):
    """An original statement: not a copy-paste echo, not a duplicate, not someone else's."""
    return fact["echo_of"] is None and not NOT_EVIDENCE_FLAGS & set(fact["flags"])


def same_fact_key(fact):
    """Medicines, allergies, conditions, events: same type + name.
    Lab results and demographics: the value and unit must match too
    (HbA1c 7.2 % and 8.1 % are two different results, not two confirmations)."""
    key = (fact["type"], same_name(fact))
    if fact["type"] in ("lab_test", "demographic"):
        key += (fact["value"], fact["unit"])
    return key


def add_badges(facts, doctor_verified_ids=frozenset(), patient_reported_ids=frozenset()):
    documents_saying = defaultdict(set)
    for fact in facts:
        if is_independent(fact):
            documents_saying[same_fact_key(fact)].add(fact["document_id"])

    for fact in facts:
        if fact["fact_id"] in doctor_verified_ids:
            fact["badge"] = "doctor_verified"
        elif not is_independent(fact):
            fact["badge"] = None
        elif "contradiction" in fact["flags"]:
            fact["badge"] = "conflicting"
        elif fact["fact_id"] in patient_reported_ids:
            fact["badge"] = "patient_reported"
        elif len(documents_saying[same_fact_key(fact)]) >= 2:
            fact["badge"] = "independent_2plus"
        else:
            fact["badge"] = "single_document"
    return facts
