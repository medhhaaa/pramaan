"""Check Deeksha's logic against the expected answers in shared/sample_facts.json.

Run from the repo root:  python -m backend.logic.check_logic

sample_facts.json already holds the CORRECT echo_of, flags and badge for patient p1.
This script clears those fields, runs the checks in the same order as
backend/recompute.py (mark_echoes -> add_flags -> add_badges) and prints every fact
whose result differs from the expected value. The goal is "0 differences".
"""
import copy
import json
import os

from backend.logic import badges, echo, flags

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
SAMPLE_FACTS = os.path.join(ROOT, "shared", "sample_facts.json")

# flags set by other parts of the system (pipeline, wrong-patient check): kept as input
OTHER_FLAGS = {"wrong_patient", "implausible_value"}


def load_expected():
    with open(SAMPLE_FACTS, encoding="utf-8") as f:
        return json.load(f)


def clear_results(facts):
    """Blank out the fields my checks are supposed to fill in."""
    facts = copy.deepcopy(facts)
    for fact in facts:
        fact["echo_of"] = None
        fact["badge"] = None
        fact["flags"] = [x for x in fact["flags"] if x in OTHER_FLAGS]
    return facts


def run_step(name, step, facts, *args):
    try:
        return step(facts, *args)
    except NotImplementedError:
        print(f"  (skipped {name}: not built yet)")
        return facts


def compare(expected, actual):
    """Return a list of difference messages, one per wrong field."""
    actual_by_id = {f["fact_id"]: f for f in actual}
    diffs = []
    for exp in expected:
        got = actual_by_id.get(exp["fact_id"])
        if got is None:
            diffs.append(f"{exp['fact_id']}: missing from the output")
            continue
        if got["echo_of"] != exp["echo_of"]:
            diffs.append(f"{exp['fact_id']}: echo_of expected {exp['echo_of']!r}, got {got['echo_of']!r}")
        if sorted(got["flags"]) != sorted(exp["flags"]):
            diffs.append(f"{exp['fact_id']}: flags expected {sorted(exp['flags'])}, got {sorted(got['flags'])}")
        if got["badge"] != exp["badge"]:
            diffs.append(f"{exp['fact_id']}: badge expected {exp['badge']!r}, got {got['badge']!r}")
    return diffs


def main():
    expected = load_expected()
    facts = clear_results(expected)

    print(f"Running checks on {len(facts)} facts from {SAMPLE_FACTS}")
    facts = run_step("mark_echoes", echo.mark_echoes, facts)
    facts = run_step("add_flags", flags.add_flags, facts)
    facts = run_step("add_badges", badges.add_badges, facts, set(), set())

    diffs = compare(expected, facts)
    for d in diffs:
        print("  DIFF", d)
    print(f"{len(diffs)} differences")

    # p1 has allergy info and a blood group, so it should have no gaps
    try:
        gaps = flags.find_gaps(facts)
        print(f"find_gaps on p1: {[g['fact_id'] for g in gaps]} (expected [])")
    except NotImplementedError:
        print("  (skipped find_gaps: not built yet)")


if __name__ == "__main__":
    main()
