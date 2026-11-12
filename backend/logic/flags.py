"""Plain-code checks, no AI. (Deeksha)

add_flags(facts) -> facts with "flags" filled. Keeps flags set by others
(wrong_patient, implausible_value) and adds:
    contradiction   one document says "no allergy" / "no X", another says it is there
    duplicate       the same result on the same date in two documents (the later copy is flagged)
    unit_mismatch   the same lab test written in different units (never converted)
    ambiguous_date  a date like 04/05/2023 where day and month could be swapped

find_gaps(facts) -> not_documented gap facts for missing basics (no allergy information,
no blood group). "Not documented" never means "does not have".

These functions are pure: a list of fact dicts in, the same list out. No database.
"""
import re
from collections import defaultdict

# the order flags are added in, after any flags set by others
MY_FLAGS = ["contradiction", "duplicate", "unit_mismatch", "ambiguous_date"]


# ---------- small helpers ----------

def same_name(fact):
    """Names are compared ignoring case and extra spaces ("HbA1c" == "hba1c ")."""
    return (fact["name"] or "").strip().lower()


def document_order(fact):
    """Sort key for 'which document came first': document date, then the number in the
    document id (so p1_d10 comes after p1_d9)."""
    number = re.search(r"(\d+)$", fact["document_id"] or "")
    return (fact["document_date"] or "", int(number.group(1)) if number else 0, fact["document_id"] or "")


def add_flag(fact, flag):
    if flag not in fact["flags"]:
        fact["flags"].append(flag)


# ---------- the four checks ----------

def is_general_allergy_statement(fact):
    """'No known drug allergies' is about ALL allergies, not one named drug."""
    return "allerg" in same_name(fact)


def check_contradictions(facts):
    """Flag both sides when one document says something is absent and another says it is
    present: any allergy vs. 'no known allergies', or the same allergy/condition name."""
    for negated in facts:
        if negated["status"] != "negated" or negated["type"] not in ("allergy", "condition"):
            continue
        for present in facts:
            if (present["status"] == "documented"
                    and present["type"] == negated["type"]
                    and present["document_id"] != negated["document_id"]
                    and (same_name(present) == same_name(negated)
                         or (negated["type"] == "allergy" and is_general_allergy_statement(negated)))):
                add_flag(negated, "contradiction")
                add_flag(present, "contradiction")


def check_duplicates(facts):
    """The same fact (type, name, dose, value, unit, status) on the same date in a second
    document is a duplicate: the copy in the later document gets the flag."""
    first_document = {}
    for fact in sorted(facts, key=document_order):
        key = (fact["type"], same_name(fact), fact["dose"], fact["value"], fact["unit"],
               fact["status"], fact["event_date"])
        if key not in first_document:
            first_document[key] = fact["document_id"]
        elif first_document[key] != fact["document_id"]:
            add_flag(fact, "duplicate")


def check_unit_mismatches(facts):
    """If one lab test name appears with two or more different units, flag every one of
    them. The values are never converted."""
    units = defaultdict(set)
    for fact in facts:
        if fact["type"] == "lab_test" and fact["unit"]:
            units[same_name(fact)].add(fact["unit"].strip())
    for fact in facts:
        if fact["type"] == "lab_test" and len(units[same_name(fact)]) > 1:
            add_flag(fact, "unit_mismatch")


AMBIGUOUS_DATE = re.compile(r"^\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\s*$")


def is_ambiguous_date(date_raw):
    """04/05/2023 could be 4 May or 5 April: both numbers are 12 or less and differ."""
    match = AMBIGUOUS_DATE.match(date_raw or "")
    if not match:
        return False
    first, second = int(match.group(1)), int(match.group(2))
    return first <= 12 and second <= 12 and first != second


def check_ambiguous_dates(facts):
    for fact in facts:
        if is_ambiguous_date(fact["date_raw"]):
            add_flag(fact, "ambiguous_date")


def add_flags(facts):
    """Run all four checks. Flags set by others (wrong_patient, implausible_value) stay."""
    for fact in facts:
        fact["flags"] = [f for f in (fact.get("flags") or []) if f not in MY_FLAGS]
    check_contradictions(facts)
    check_duplicates(facts)
    check_unit_mismatches(facts)
    check_ambiguous_dates(facts)
    for fact in facts:  # stable order: others' flags first, then mine in MY_FLAGS order
        others = [f for f in fact["flags"] if f not in MY_FLAGS]
        fact["flags"] = others + [f for f in MY_FLAGS if f in fact["flags"]]
    return facts


# ---------- gaps ----------

def gap_fact(patient_id, key, fact_type, name):
    """A placeholder fact that says 'the records don't mention this'. It has no document
    and no quote, and it is never stored: it is computed each time."""
    return {
        "fact_id": f"{patient_id}_gap_{key}",
        "patient_id": patient_id,
        "document_id": None,
        "type": fact_type,
        "name": name,
        "dose": None, "frequency": None, "value": None, "unit": None, "action": None,
        "status": "not_documented",
        "event_date": None, "document_date": None, "date_raw": None,
        "quote": None, "page": None, "line": None,
        "quote_verified": False,
        "echo_of": None, "badge": None, "flags": [], "corrected": False,
    }


def find_gaps(facts):
    """Return gap facts for basics no document mentions: allergy status (neither an
    allergy nor 'no known allergies') and blood group. Facts flagged wrong_patient
    don't count, because they may belong to someone else."""
    if not facts:
        return []  # nothing uploaded yet: nothing to compare
    patient_id = facts[0]["patient_id"]
    usable = [f for f in facts if "wrong_patient" not in (f.get("flags") or [])]

    gaps = []
    if not any(f["type"] == "allergy" for f in usable):
        gaps.append(gap_fact(patient_id, "allergy", "allergy", "Allergy status"))
    if not any(f["type"] == "demographic" and f["name"] == "blood_group" for f in usable):
        gaps.append(gap_fact(patient_id, "blood_group", "demographic", "blood_group"))
    return gaps
