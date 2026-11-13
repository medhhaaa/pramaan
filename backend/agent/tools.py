"""The fixed list of tools the assistants may pick from. (Ashil, AGENTIC_PLAN point 15)

    TOOLS["doctor"]["brief"].run(ctx, {})  -> {"data": ..., "fact_ids": [...]}

Agreed tool shape (AGENTIC_PLAN section A.2): def tool(ctx, args) -> {"data", "fact_ids"}.
A write tool returns {"proposal": {"action", "args", "summary"}} and changes nothing.

The AI only names a tool and its arguments. OUR code runs it, with ctx (backend/agent/context.py):
the logged-in user's own access and partial-sharing scope. Every tool reuses a function that
already takes `access`, so a tool can never return more than the matching page shows.
"""
from dataclasses import dataclass, field
from typing import Callable

from backend.db import fact_from_row, get_conn
from backend.disease_search import disease_search as search_disease
from backend.disease_search import fact_ids as disease_fact_ids
from backend.logic.flags import find_gaps
from backend.routes.brief import build_brief
from backend.routes.check_medicine import medicine_warnings
from backend.routes.flags import FLAG_TYPES, group_by_flag

MAX_ITEMS = 40  # per list in a tool result: keeps prompts small


@dataclass
class Tool:
    name: str
    description: str          # one line for the prompt
    args: dict                # name -> description ("optional: ..." when not required)
    fn: Callable
    write: bool = False       # write tools return a proposal the user must confirm
    required: list = field(default_factory=list)

    def run(self, ctx, args):
        args = {k: v for k, v in (args or {}).items() if k in self.args}
        missing = [a for a in self.required if not str(args.get(a) or "").strip()]
        if missing:
            return {"data": {"error": f"missing argument(s): {', '.join(missing)}"}, "fact_ids": []}
        return self.fn(ctx, args)

    def prompt_line(self):
        args = ", ".join(f"{k}: {v}" for k, v in self.args.items()) or "no arguments"
        return f"- {self.name}({args}): {self.description}"


def collect_fact_ids(obj):
    """Every fact_id inside a tool result (keys "fact_id" and lists "fact_ids"), in order."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "fact_id" and isinstance(v, str):
                    found.append(v)
                elif k == "fact_ids" and isinstance(v, list):
                    found.extend(x for x in v if isinstance(x, str))
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return list(dict.fromkeys(found))


def _small_fact(f):
    keep = ("fact_id", "type", "name", "dose", "frequency", "value", "unit", "action", "status",
            "event_date", "document_id", "echo_of", "flags")
    return {k: f.get(k) for k in keep if f.get(k) not in (None, [], "")}


# ---------- doctor tools ----------

def brief_tool(ctx, args):
    brief = build_brief(ctx.patient_id, ctx.access, ctx.lang)
    brief.pop("patient", None)  # name, DOB, phone, address: the AI never needs them
    return {"data": brief, "fact_ids": collect_fact_ids(brief)}


def flags_tool(ctx, args):
    """Same facts as GET /patients/{id}/flags (backend/routes/flags.py): held-back documents
    included so a reviewer sees the wrong-patient report, gaps from the trusted facts."""
    from backend.scope import scoped

    with get_conn() as conn:
        rows = conn.execute(
            """SELECT f.*, d.held_back FROM facts f JOIN documents d ON d.id = f.document_id
               WHERE f.patient_id = ? ORDER BY f.event_date, f.document_date, f.fact_id""",
            (ctx.patient_id,),
        ).fetchall()
    facts, trusted = [], []
    for row in rows:
        fact = fact_from_row(row)
        held_back = fact.pop("held_back")
        facts.append(fact)
        if not held_back:
            trusted.append(fact)
    groups = group_by_flag(scoped(facts, ctx.access))
    groups["gap"] = find_gaps(scoped(trusted, ctx.access))
    kind = (args.get("kind") or "").strip().lower()
    if kind in groups:
        groups = {kind: groups[kind]}
    data = {k: [_small_fact(f) for f in v[:MAX_ITEMS]] for k, v in groups.items() if v}
    return {"data": data or {"note": "no flags"}, "fact_ids": collect_fact_ids(data)}


def disease_search_tool(ctx, args):
    result = search_disease(ctx.patient_id, ctx.access, str(args["disease"]))
    data = {k: result[k] for k in ("disease", "label", "matched_by", "matched_terms", "hidden_count")}
    for section in ("conditions", "medicines", "labs", "events"):
        data[section] = [_small_fact(f) for f in result[section][:MAX_ITEMS]]
    data["documents"] = result["documents"]
    return {"data": data, "fact_ids": disease_fact_ids(result)}


def check_medicine_tool(ctx, args):
    drug = str(args["drug"]).strip()[:100]
    generic, drug_class, warnings = medicine_warnings(ctx.patient_id, drug, ctx.access, ctx.lang)
    data = {
        "drug": drug, "generic": generic, "drug_class": drug_class, "known": generic is not None,
        "warnings": [{"kind": w["kind"], "text": w["text"],
                      "fact_id": (w.get("source") or {}).get("fact_id")} for w in warnings],
        "note": "Checked against these records only. This is not prescribing advice.",
    }
    return {"data": data, "fact_ids": collect_fact_ids(data)}


def _questions(ctx):
    from backend.routes.questions import list_questions_for
    from backend.scope import scoped_questions

    with get_conn() as conn:
        return scoped_questions(list_questions_for(conn, ctx.patient_id, ctx.lang), ctx.access)


def _question_out(q):
    return {"question_id": f"question_{q['id']}", "text": q.get("text"), "status": q.get("status"),
            "routed_to": q.get("routed_to"), "fact_ids": collect_fact_ids(q.get("facts") or [])}


def open_questions_tool(ctx, args):
    """The doctor's Open Questions: sent to the doctor (statuses agreed with Akanksha), not resolved."""
    qs = [q for q in _questions(ctx) if q.get("status") == "sent_to_doctor" or q.get("routed_to") == "doctor"]
    qs = [q for q in qs if q.get("status") != "resolved" and not q.get("claim_condition")]
    data = [_question_out(q) for q in qs[:MAX_ITEMS]]
    return {"data": data or {"note": "no open questions for the doctor"}, "fact_ids": collect_fact_ids(data),
            "source_ids": [q["question_id"] for q in data]}


def timeline_tool(ctx, args):
    start, end = str(args.get("from") or "")[:10], str(args.get("to") or "")[:10]
    facts = [f for f in ctx.facts() if f["status"] != "not_documented"
             and (not start or (f.get("event_date") or "") >= start)
             and (not end or (f.get("event_date") or "9999") <= end)]
    facts.sort(key=lambda f: (f.get("event_date") or "", f["fact_id"]))
    data = [_small_fact(f) for f in facts[-60:]]  # the newest 60 in the range
    return {"data": data or {"note": "nothing in this date range"}, "fact_ids": collect_fact_ids(data)}


# ---------- patient tools ----------

def explain_records_tool(ctx, args):
    """Facts about a topic: the disease search when the topic is a known disease / medicine / test,
    plus any fact whose name or source line has the topic (or its synonyms) as whole words."""
    from backend.disease_search import resolve
    from backend.search import _term_pattern, expand_query

    topic = str(args["topic"]).strip()[:100]
    picked = {}
    key, _how = resolve(topic)
    if key:
        found = search_disease(ctx.patient_id, ctx.access, topic)
        for section in ("conditions", "medicines", "labs", "events"):
            for f in found[section]:
                picked[f["fact_id"]] = f
    terms = expand_query(topic)
    for f in ctx.facts():
        if f["status"] == "not_documented" or f["fact_id"] in picked:
            continue
        if any(_term_pattern(t).search(f"{f.get('name') or ''} {f.get('quote') or ''}") for t in terms):
            picked[f["fact_id"]] = f
    facts = sorted(picked.values(), key=lambda f: (f.get("event_date") or "", f["fact_id"]))[-MAX_ITEMS:]
    data = [{**_small_fact(f), "quote": (f.get("quote") or "")[:200]} for f in facts]
    return {"data": {"topic": topic, "facts": data} if data else {"topic": topic, "note": "nothing found"},
            "fact_ids": collect_fact_ids(data)}


def my_medicines_tool(ctx, args):
    from backend.routes.medications import group_medications

    meds = group_medications(ctx.facts())
    data = [{
        "name": m["name"], "current": m["current"], "last_fresh_evidence_date": m["last_fresh_evidence_date"],
        "copies": m.get("echo_count"),
        "entries": [{k: e.get(k) for k in ("fact_id", "date", "dose", "frequency", "action", "echo_of")}
                    for e in m["entries"][-6:]],
    } for m in meds]
    return {"data": data or {"note": "no medicines in the records"}, "fact_ids": collect_fact_ids(data)}


def things_to_check_tool(ctx, args):
    """Questions waiting for the patient (status open, not routed to the doctor)."""
    qs = [q for q in _questions(ctx) if q.get("status") == "open" and q.get("routed_to") != "doctor"]
    data = [_question_out(q) for q in qs[:MAX_ITEMS]]
    return {"data": data or {"note": "nothing to check right now"}, "fact_ids": collect_fact_ids(data),
            "source_ids": [q["question_id"] for q in data]}


def claim_checklist_tool(ctx, args):
    """Reuses claims.checklist_for (Medha): what is commonly needed for this stay, saved or not saved
    yet, plus what the patient added to the claim pack and other documents they could add."""
    from backend.agent.claim_pack import pack_items
    from backend.routes.claims import checklist_for, load_stay, patient_documents, stay_out

    with get_conn() as conn:
        stays = [stay_out(r) for r in conn.execute(
            "SELECT * FROM hospital_stays WHERE patient_id = ? ORDER BY id DESC", (ctx.patient_id,))]
        if not stays:
            return {"data": {"note": "no hospital stay is saved yet"}, "fact_ids": []}
        wanted = str(args.get("stay") or "").replace("stay_", "").strip()
        stay = load_stay(conn, ctx.patient_id, int(wanted)) if wanted.isdigit() and \
            any(s["id"] == int(wanted) for s in stays) else stays[0]
        result = checklist_for(conn, ctx.patient_id, stay)
        in_pack = pack_items(conn, stay["id"])
        documents = [d for d in patient_documents(conn, ctx.patient_id) if not d["held_back"]]
    listed = {d["id"] for item in result["items"] for d in item["documents"]}
    short = lambda d: {k: d.get(k) for k in ("id", "doc_type", "document_date")}
    data = {
        "stay": {"stay_id": f"stay_{stay['id']}", "admitted_on": stay["admitted_on"], "discharged_on": stay["discharged_on"]},
        "all_stays": [{"stay_id": f"stay_{s['id']}", "admitted_on": s["admitted_on"], "discharged_on": s["discharged_on"]}
                      for s in stays],
        "items": [{"label": i["label"], "status": i["status"].replace("_", " "),
                   "documents": [short(d) for d in i["documents"]]} for i in result["items"]],
        "added_to_claim_pack_by_patient": in_pack,
        "other_documents": [short(d) for d in documents if d["id"] not in listed][:MAX_ITEMS],
        "wording": "Say 'commonly needed', 'saved', 'not saved yet'. Never 'eligible', 'approved' or 'guaranteed'. "
                   "The insurer makes the final decision.",
    }
    source_ids = [f"stay_{stay['id']}", *listed, *in_pack, *(d["id"] for d in data["other_documents"])]
    out = {"data": data, "fact_ids": [], "source_ids": list(dict.fromkeys(source_ids))}
    if any(i["status"] == "not_saved" for i in result["items"]):
        out["links"] = [CLAIM_UPLOAD_LINK]  # Claim documents has an upload button per missing item
    return out


UPLOAD_LINK = {"to": "/upload", "kind": "upload"}
CLAIM_UPLOAD_LINK = {"to": "/claim-documents", "kind": "claim_upload"}


def upload_help_tool(ctx, args):
    """The assistant cannot upload or receive files. This only returns where the patient uploads,
    so every document still goes through the Upload page and the full pipeline."""
    data = {"note": "The assistant cannot upload files. The patient uploads PDFs or photos on the Upload page; "
                    "documents missing for an insurance claim can also be uploaded on the Claim documents page.",
            "page_id": "upload_page"}
    return {"data": data, "fact_ids": [], "source_ids": ["upload_page"], "links": [UPLOAD_LINK]}


def save_to_claim_pack_tool(ctx, args):
    from backend.agent.claim_pack import propose_save

    ids = args.get("document_ids")
    ids = [ids] if isinstance(ids, str) else ids or []
    return propose_save(ctx, str(args.get("stay") or "").replace("stay_", ""), ids)


def who_can_see_tool(ctx, args):
    """Active QR / code shares and the care team: who can see these records right now."""
    from backend.scope import parse_scope

    with get_conn() as conn:
        shares = conn.execute(
            """SELECT s.id, s.scope, s.expires_at, s.opened_at, COALESCE(u.full_name, u.username) AS doctor
               FROM share_links s LEFT JOIN users u ON u.id = s.opened_by
               WHERE s.patient_id = ? AND s.expires_at > datetime('now') ORDER BY s.id""", (ctx.patient_id,)).fetchall()
        team = conn.execute(
            """SELECT c.id, c.scope, c.created_at, COALESCE(u.full_name, u.username) AS doctor
               FROM care_team c JOIN users u ON u.id = c.doctor_id
               WHERE c.patient_id = ? AND c.status = 'active' ORDER BY c.id""", (ctx.patient_id,)).fetchall()
    data = {
        "qr_shares": [{"share_id": f"share_{r['id']}", "doctor": r["doctor"] or "not opened yet",
                       "sees": parse_scope(r["scope"]), "until": r["expires_at"]} for r in shares],
        "care_team": [{"care_team_id": f"careteam_{r['id']}", "doctor": r["doctor"], "sees": parse_scope(r["scope"]),
                       "since": r["created_at"]} for r in team],
    }
    ids = [s["share_id"] for s in data["qr_shares"]] + [c["care_team_id"] for c in data["care_team"]]
    if not ids:
        data["note"] = "nobody: no open share and nobody on the care team"
        ids = ["sharing_none"]  # "nobody can see them" is itself a fact about the sharing
    return {"data": data, "fact_ids": [], "source_ids": ids}


TOOLS = {
    "doctor": {t.name: t for t in [
        Tool("brief", "the 60-second brief: current medicines, allergies, conditions, latest results, "
             "events, red flags, open questions", {}, brief_tool),
        Tool("flags", "records with problems: contradictions, duplicates, unit mismatches, ambiguous dates, "
             "wrong-patient documents, implausible values, gaps",
             {"kind": "optional: one of " + ", ".join(FLAG_TYPES + ["gap"])}, flags_tool),
        Tool("disease_search", "everything in the records about one disease: conditions, medicines, lab "
             "tests, events, documents", {"disease": "a disease, synonym or medicine, e.g. diabetes"},
             disease_search_tool, required=["disease"]),
        Tool("check_medicine", "allergy and duplicate warnings for a medicine, from the records",
             {"drug": "medicine name, brand or generic"}, check_medicine_tool, required=["drug"]),
        Tool("open_questions", "the doctor's open questions: conflicts and gaps waiting for a doctor", {},
             open_questions_tool),
        Tool("timeline", "facts in a date range, oldest first",
             {"from": "optional: YYYY-MM-DD", "to": "optional: YYYY-MM-DD"}, timeline_tool),
    ]},
    "patient": {t.name: t for t in [
        Tool("explain_records", "facts about a topic (a disease, medicine, test or word), with dates and sources",
             {"topic": "what to look for, e.g. sugar, Metformin, HbA1c"}, explain_records_tool, required=["topic"]),
        Tool("my_medicines", "the patient's medicines: current or stopped, doses, last real evidence", {},
             my_medicines_tool),
        Tool("things_to_check", "questions waiting for the patient to answer", {}, things_to_check_tool),
        Tool("claim_checklist", "documents commonly needed for an insurance claim for a hospital stay: saved or "
             "not saved yet, and other documents that could be added",
             {"stay": "optional: stay_id from a previous result; default the newest stay"}, claim_checklist_tool),
        Tool("save_to_claim_pack", "PROPOSE adding documents to a stay's claim pack (the patient must confirm; "
             "nothing is saved by this tool)",
             {"stay": "stay_id", "document_ids": "list of document ids from claim_checklist"},
             save_to_claim_pack_tool, write=True, required=["stay", "document_ids"]),
        Tool("who_can_see", "who can see these records now: open QR / code shares and the care team", {},
             who_can_see_tool),
        Tool("upload_help", "the patient wants to upload or add a new document: you can NOT upload; this gives "
             "the page where they upload it themselves", {}, upload_help_tool),
    ]},
}

# writes the user confirmed: action name -> fn(ctx, args) (backend/routes/assistant.py runs them)
def _apply_save(ctx, args):
    from backend.agent.claim_pack import apply_save
    return apply_save(ctx, args)


ACTIONS = {"save_to_claim_pack": _apply_save}


def tools_for(role):
    return TOOLS.get(role, {})
