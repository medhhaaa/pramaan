"""GET /patients/{patient_id}/brief -> the 60-second doctor brief. (Medha)

Built in plain code from the stored facts (no AI). Every item carries its fact_id and source.
Response:
{
  "patient": {"id", "name", "dob", "sex", "blood_group"},
  "current_medicines": [{"name", "dose", "frequency", "last_fresh_evidence_date",
                         "mentions", "echo_count", "only_copies_since", "source"}],
  "allergies":         [{"name", "reaction", "status", "date", "conflicting", "source"}],
  "conditions":        [{"name", "first_date", "last_date", "mentions", "source"}],
  "latest_results":    [{"name", "value", "unit", "date", "flags", "previous", "source"}],
  "events":            [{"name", "date", "source"}],
  "red_flags":         [{"flag", "text", "fact_ids"}],
  "open_questions":    [{"id", "text", "status"}]
}
red_flags and open_questions text follow the user's language (English or Kannada);
names, values, units, dates and quotes inside them stay exactly as written.
"""
from fastapi import APIRouter, Depends, HTTPException

from backend.auth import get_current_user, require_patient_access
from backend.db import get_conn
from backend.logic.flags import find_gaps
from backend.routes.audit_helper import log_action
from backend.routes.fact_helpers import (
    describe, load_documents, load_facts, medication_summaries, source_info,
)
from backend.routes.language import FACT_TYPE_KN, gap_name, user_language
from backend.routes.questions import list_questions_for

router = APIRouter()


def current_medicines(facts, docs):
    out = []
    for med in medication_summaries(facts):
        if not med["current"]:
            continue
        fresh = med["latest_fresh"]
        out.append({
            "name": med["name"],
            "dose": fresh["dose"],
            "frequency": fresh["frequency"],
            "last_fresh_evidence_date": med["last_fresh_evidence_date"],
            "mentions": med["mentions"],
            "echo_count": med["echo_count"],
            # the newest mention is only a copy -> the doctor should not trust it as current
            "only_copies_since": med["last_fresh_evidence_date"] if med["latest"]["echo_of"] else None,
            "source": source_info(fresh, docs),
        })
    return out


def allergies(facts, docs):
    return [
        {
            "name": f["name"],
            "reaction": f["value"],
            "status": f["status"],
            "date": f["event_date"],
            "conflicting": "contradiction" in f["flags"],
            "source": source_info(f, docs),
        }
        for f in facts
        if f["type"] == "allergy"
    ]


def conditions(facts, docs):
    groups = {}
    for f in facts:
        if f["type"] == "condition" and f["status"] == "documented":
            groups.setdefault(f["name"].strip().lower(), []).append(f)
    out = []
    for entries in groups.values():
        dates = [e["event_date"] for e in entries if e["event_date"]]
        out.append({
            "name": entries[-1]["name"],
            "first_date": min(dates) if dates else None,
            "last_date": max(dates) if dates else None,
            "mentions": len(entries),
            "source": source_info(entries[-1], docs),
        })
    return out


def latest_results(facts, docs):
    """Newest value per lab test, with the previous different-date value. Never converted."""
    groups = {}
    for f in facts:
        if f["type"] == "lab_test" and f["status"] == "documented":
            groups.setdefault(f["name"].strip().lower(), []).append(f)
    out = []
    for entries in groups.values():
        # duplicates of the same result come last so the original document is used
        entries.sort(key=lambda f: (f["event_date"] or "", "duplicate" not in f["flags"]))
        latest = entries[-1]
        older = [e for e in entries if e["event_date"] != latest["event_date"]]
        prev = older[-1] if older else None
        out.append({
            "name": latest["name"],
            "value": latest["value"],
            "unit": latest["unit"],
            "date": latest["event_date"],
            "flags": sorted({flag for e in entries for flag in e["flags"]}),
            "previous": {"value": prev["value"], "unit": prev["unit"], "date": prev["event_date"],
                         "fact_id": prev["fact_id"]} if prev else None,
            "source": source_info(latest, docs),
        })
    return out


def events(facts, docs):
    return [
        {"name": f["name"], "date": f["event_date"], "source": source_info(f, docs)}
        for f in facts
        if f["type"] == "event" and f["status"] == "documented"
    ]


def red_flags(all_facts, docs, meds, gaps, lang="en"):
    """Plain-language warnings. all_facts includes held-back documents; gaps from find_gaps()."""
    flags = []

    def add(flag, en, kn, fact_ids):
        flags.append({"flag": flag, "text": kn if lang == "kn" else en, "fact_ids": fact_ids})

    contradictions = [f for f in all_facts if "contradiction" in f["flags"]]
    for fact_type in sorted({f["type"] for f in contradictions}):
        group = [f for f in contradictions if f["type"] == fact_type]
        said = "; ".join(f'"{f["quote"]}" ({f["event_date"]})' for f in group)
        add("contradiction",
            f"{fact_type.capitalize()} records disagree: {said}.",
            f"{FACT_TYPE_KN.get(fact_type, fact_type)} ದಾಖಲೆಗಳು ಹೊಂದುತ್ತಿಲ್ಲ: {said}.",
            [f["fact_id"] for f in group])

    by_test = {}
    for f in all_facts:
        if "unit_mismatch" in f["flags"]:
            by_test.setdefault(f["name"].strip().lower(), []).append(f)
    for group in by_test.values():
        seen = sorted({f"{f['value']} {f['unit']} ({f['event_date']})" for f in group})
        add("unit_mismatch",
            f"{group[0]['name']} recorded in different units: {', '.join(seen)}. Not converted.",
            f"{group[0]['name']} ಬೇರೆ ಬೇರೆ ಘಟಕಗಳಲ್ಲಿ ದಾಖಲಾಗಿದೆ: {', '.join(seen)}. ಪರಿವರ್ತಿಸಿಲ್ಲ.",
            [f["fact_id"] for f in group])

    for doc_id in sorted({f["document_id"] for f in all_facts if "duplicate" in f["flags"]}):
        ids = [f["fact_id"] for f in all_facts if f["document_id"] == doc_id and "duplicate" in f["flags"]]
        name = docs.get(doc_id, {}).get("filename", doc_id)
        add("duplicate",
            f"{name} repeats results already in another document.",
            f"{name}: ಬೇರೆ ದಾಖಲೆಯಲ್ಲಿ ಈಗಾಗಲೇ ಇರುವ ಫಲಿತಾಂಶಗಳನ್ನೇ ಮತ್ತೆ ಹೊಂದಿದೆ.",
            ids)

    for doc in docs.values():
        if doc["held_back"]:
            ids = [f["fact_id"] for f in all_facts if f["document_id"] == doc["id"]]
            add("wrong_patient",
                f"{doc['filename']} is held back: it may belong to another patient.",
                f"{doc['filename']} ತಡೆಹಿಡಿಯಲಾಗಿದೆ: ಇದು ಬೇರೆ ರೋಗಿಯದ್ದಾಗಿರಬಹುದು.",
                ids)

    ambiguous = {}
    for f in all_facts:
        if "ambiguous_date" in f["flags"]:
            ambiguous.setdefault((f["document_id"], f["date_raw"]), []).append(f["fact_id"])
    for (doc_id, raw), ids in ambiguous.items():
        name = docs.get(doc_id, {}).get("filename", doc_id)
        add("ambiguous_date",
            f'Date "{raw}" in {name} could be read two ways.',
            f'ದಿನಾಂಕ "{raw}" ({name}) ಅನ್ನು ಎರಡು ರೀತಿಯಲ್ಲಿ ಓದಬಹುದು.',
            ids)

    for f in all_facts:
        if "implausible_value" in f["flags"]:
            add("implausible_value",
                f"{describe(f)} looks implausible (possible unit or typing error). Original kept.",
                f"{describe(f)} ಅಸಂಭವವಾಗಿ ಕಾಣುತ್ತದೆ (ಘಟಕ ಅಥವಾ ಟೈಪಿಂಗ್ ದೋಷ ಇರಬಹುದು). ಮೂಲ ಮೌಲ್ಯವನ್ನು ಹಾಗೆಯೇ ಇಡಲಾಗಿದೆ.",
                [f["fact_id"]])

    for gap in gaps:
        add("gap",
            f"No record mentions {gap_name(gap['name'], 'en')}. Not documented does not mean absent.",
            f"ಯಾವುದೇ ದಾಖಲೆಯಲ್ಲಿ {gap_name(gap['name'], 'kn')} ಉಲ್ಲೇಖವಿಲ್ಲ. ದಾಖಲಾಗಿಲ್ಲ ಎಂದರೆ ಇಲ್ಲ ಎಂದಲ್ಲ.",
            [gap["fact_id"]])

    for med in meds:
        if med["only_copies_since"]:
            add("echo",
                f"{med['name']}: last real evidence {med['only_copies_since']}; "
                f"{med['echo_count']} later mention(s) are copies.",
                f"{med['name']}: ಕೊನೆಯ ನಿಜವಾದ ಪುರಾವೆ {med['only_copies_since']}; "
                f"ನಂತರದ {med['echo_count']} ಉಲ್ಲೇಖ(ಗಳು) ನಕಲು.",
                [med["source"]["fact_id"]])
    return flags


@router.get("/patients/{patient_id}/brief")
def brief_route(patient_id: str, user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    lang = user_language(user)
    with get_conn() as conn:
        patient = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        facts = load_facts(conn, patient_id)
        all_facts = load_facts(conn, patient_id, include_held_back=True)
        docs = load_documents(conn, patient_id)
        questions = list_questions_for(conn, patient_id, lang)

    meds = current_medicines(facts, docs)
    log_action(user, "view_brief", patient_id, "")
    return {
        "patient": dict(patient),
        "current_medicines": meds,
        "allergies": allergies(facts, docs),
        "conditions": conditions(facts, docs),
        "latest_results": latest_results(facts, docs),
        "events": events(facts, docs),
        "red_flags": red_flags(all_facts, docs, meds, find_gaps(facts), lang),
        "open_questions": [
            {"id": q["id"], "text": q["text"], "status": q["status"]}
            for q in questions
            if q["status"] != "resolved"
        ],
    }
