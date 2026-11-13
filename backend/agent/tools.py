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
    ]},
    "patient": {},  # step 3 (AGENTIC_PLAN F.3)
}


def tools_for(role):
    return TOOLS.get(role, {})
