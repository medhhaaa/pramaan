"""What a care-team doctor may see: their scope. (Medha)

A patient adds a doctor to their care team with scope "all" or a list of condition tags
(rules/condition_tags.json, e.g. ["diabetes"]). A doctor with a tag list sees only facts that
match one of those tags by name, plus two things every treating doctor needs for safety:
allergies and demographics (name, sex, DOB, blood group).

    access = require_patient_access(user, patient_id)   # backend/auth.py
    facts = scoped(facts, access)                        # [] stays [], "all" keeps everything

Plain keyword matching, no AI. A source PDF opens for a scoped doctor only if at least one of
its facts is in scope (the whole page is then visible: documents are never cut up).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAGS_PATH = os.path.join(ROOT, "rules", "condition_tags.json")
ALWAYS_VISIBLE = {"allergy", "demographic"}
KEYS_BY_TYPE = {
    "condition": ("conditions",),
    "medication": ("medicines",),
    "lab_test": ("tests",),
    "event": ("events", "conditions"),
}

with open(TAGS_PATH, encoding="utf-8") as f:
    TAGS = json.load(f)
TAG_NAMES = [t["tag"] for t in TAGS]
# "other": facts that match no tag above (a chest infection, a fracture). Used by QR / code
# shares (backend/routes/share.py) so a patient can share those too without sharing everything.
OTHER = "other"
SCOPE_NAMES = TAG_NAMES + [OTHER]
SCOPE_LABELS = {**{t["tag"]: t["label"] for t in TAGS}, OTHER: "Other records"}


def parse_scope(text):
    """'all' or a list of tags, from the care_team.scope / share_links.scope column."""
    if not text or text == "all":
        return "all"
    tags = json.loads(text)
    return [t for t in tags if t in SCOPE_NAMES]


def union_scope(a, b):
    """Everything either scope shows."""
    if a == "all" or b == "all":
        return "all"
    return sorted(set(a) | set(b))


def scope_text(scope):
    return "all" if scope == "all" else json.dumps(sorted(set(scope)))


def tags_of(fact_type, name):
    """Tags whose keywords appear in this fact's name (for its type)."""
    low = (name or "").lower()
    found = []
    for tag in TAGS:
        keys = [k for group in KEYS_BY_TYPE.get(fact_type, ()) for k in tag.get(group, [])]
        if any(k in low for k in keys):
            found.append(tag["tag"])
    return found


def groups_of(fact_type, name):
    """The scope groups a fact belongs to: its tags, or ["other"] if it matches none."""
    return tags_of(fact_type, name) or [OTHER]


def fact_in_scope(fact, scope):
    if scope == "all" or fact.get("type") in ALWAYS_VISIBLE:
        return True
    return bool(set(groups_of(fact.get("type"), fact.get("name"))) & set(scope))


def medicine_in_scope(medicine, scope):
    return scope == "all" or bool(set(groups_of("medication", medicine)) & set(scope))


def access_scope(access):
    return (access or {}).get("scope", "all")


def scoped(facts, access):
    scope = access_scope(access)
    if scope == "all":
        return facts
    return [f for f in facts if fact_in_scope(f, scope)]


def scoped_questions(questions, access):
    """Open questions a scoped doctor may see: those about at least one in-scope fact."""
    scope = access_scope(access)
    if scope == "all":
        return questions
    return [q for q in questions if any(fact_in_scope(f, scope) for f in q.get("facts", []))]


def document_in_scope(facts, scope):
    """A scoped doctor may open a source document only if it has an in-scope clinical fact
    (demographics alone don't count: every document has them)."""
    if scope == "all":
        return True
    clinical = [f for f in facts if f.get("type") != "demographic"]
    if not clinical:  # nothing read from it yet (a handwritten page waiting to be read)
        return OTHER in scope
    return any(fact_in_scope(f, scope) for f in clinical)
