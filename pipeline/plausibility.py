"""Plausibility guard: flag lab values that cannot be real. (Ashil, P3)

check_plausibility(facts) -> the same facts; impossible ones get "implausible_value" in flags

"Impossible" means outside what a living person can have, so it is almost surely a unit
or typing error ("Potassium 45 mmol/L" is really 4.5). These limits are deliberately wide:
an abnormal value is NOT implausible, and this is never a judgement about health.
The original value is never changed. Tests or units we don't know are never flagged.
"""
import re

# (words in the test name, unit as written lower-case without spaces) -> (lowest, highest)
LIMITS = [
    (("hba1c",), "%", (2, 25)),
    (("glucose",), "mg/dl", (10, 2000)),
    (("glucose",), "mmol/l", (0.5, 110)),
    (("creatinine",), "mg/dl", (0.05, 30)),
    (("creatinine",), "umol/l", (5, 2700)),
    (("potassium",), "mmol/l", (1, 12)),
    (("sodium",), "mmol/l", (90, 200)),
    (("haemoglobin", "hemoglobin"), "g/dl", (1, 26)),
    (("tsh",), "uiu/ml", (0, 1000)),
    (("tsh",), "miu/l", (0, 1000)),
    (("egfr",), "ml/min/1.73m2", (0, 250)),
    (("cholesterol",), "mg/dl", (10, 1500)),
    (("cholesterol",), "mmol/l", (0.2, 40)),
    (("triglycerides",), "mg/dl", (5, 10000)),
    (("spo2",), "%", (30, 100)),
]
BP_LIMITS = {"systolic": (40, 320), "diastolic": (15, 220)}
FLAG = "implausible_value"


def _number(text):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*", text or "")
    return float(match.group(1)) if match else None


def is_implausible(fact):
    if fact.get("type") != "lab_test" or not fact.get("value"):
        return False
    name = (fact.get("name") or "").lower()
    unit = re.sub(r"\s+", "", fact.get("unit") or "").lower()

    if ("blood pressure" in name or name == "bp") and unit == "mmhg":
        parts = fact["value"].split("/")
        if len(parts) != 2 or None in (_number(parts[0]), _number(parts[1])):
            return False
        systolic, diastolic = _number(parts[0]), _number(parts[1])
        low_s, high_s = BP_LIMITS["systolic"]
        low_d, high_d = BP_LIMITS["diastolic"]
        return not (low_s <= systolic <= high_s and low_d <= diastolic <= high_d
                    and diastolic < systolic)

    value = _number(fact["value"])
    if value is None:
        return False
    for words, limit_unit, (low, high) in LIMITS:
        if unit == limit_unit and any(w in name for w in words):
            return not (low <= value <= high)
    return False  # a test or unit we don't know: never guess


def check_plausibility(facts):
    for fact in facts:
        if is_implausible(fact):
            flags = list(fact.get("flags") or [])
            if FLAG not in flags:
                flags.append(FLAG)
            fact["flags"] = flags
    return facts
