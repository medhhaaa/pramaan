"""recompute_patient(patient_id): rerun the plain-code checks on ALL of a patient's facts
and save the results. Called after every upload and every correction. (Core backend)

Order (KICKOFF.md): mark_echoes -> add_flags -> add_badges  (Deeksha's pure functions)
If one of them is not built yet (NotImplementedError), that step is skipped and the
stored values for it are kept as they are.
"""
import copy
import json

from backend.db import fact_from_row, get_conn
from backend.logic import badges, echo, flags

# flags set by other parts of the system; the checks must keep them
OTHER_FLAGS = {"wrong_patient", "implausible_value"}


def _try(step, facts, reset, *args):
    """Run one check on a copy with its own fields cleared. Return the new facts, or the
    old facts unchanged if the check isn't built yet."""
    fresh = copy.deepcopy(facts)
    for f in fresh:
        reset(f)
    try:
        result = step(fresh, *args)
    except NotImplementedError:
        return facts
    return fresh if result is None else result  # works whether the check returns or edits in place


def _reset_echo(f):
    f["echo_of"] = None


def _reset_flags(f):
    f["flags"] = [x for x in f["flags"] if x in OTHER_FLAGS]


def _reset_badge(f):
    f["badge"] = None


def recompute_patient(patient_id):
    with get_conn() as conn:
        facts = [fact_from_row(r) for r in conn.execute(
            "SELECT * FROM facts WHERE patient_id = ? ORDER BY document_date, fact_id", (patient_id,))]
        doctor_verified_ids = {r["fact_id"] for r in conn.execute(
            """SELECT DISTINCT c.fact_id FROM corrections c JOIN facts f ON f.fact_id = c.fact_id
               WHERE f.patient_id = ? AND c.role = 'doctor'""", (patient_id,))}
        patient_reported_ids = set()
        for r in conn.execute(
                "SELECT fact_ids FROM questions WHERE patient_id = ? AND status = 'answered'", (patient_id,)):
            patient_reported_ids.update(json.loads(r["fact_ids"] or "[]"))

    facts = _try(echo.mark_echoes, facts, _reset_echo)
    facts = _try(flags.add_flags, facts, _reset_flags)
    facts = _try(badges.add_badges, facts, _reset_badge, doctor_verified_ids, patient_reported_ids)

    with get_conn() as conn:
        for f in facts:
            conn.execute(
                "UPDATE facts SET echo_of = ?, flags = ?, badge = ? WHERE fact_id = ?",
                (f["echo_of"], json.dumps(f["flags"]), f["badge"], f["fact_id"]),
            )
    return facts
