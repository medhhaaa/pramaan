"""What an AI agent may see for one request. (Core backend, AGENTIC_PLAN.md point 12)

    ctx = agent_context(user, patient_id)      # 403 exactly like require_patient_access

AgentContext
    user        the logged-in user dict          role      "doctor" | "patient"
    patient_id  the patient being looked at       access    from require_patient_access:
    identity    name / dob / phone / address                 {"kind": "own"|"shared"|"care_team",
                (for pipeline/privacy_layer)                  "scope": "all" | [...], ...}
    lang        "en" | "kn" | "hi"
    read_only   True for a shared doctor (QR / code): tools must not change anything

Helpers every tool should use, so nothing outside the user's access ever reaches an AI:
    ctx.facts()            this patient's facts, held-back documents left out, scope applied
    ctx.in_scope(facts)    filter any list of facts by the scope
"""
from dataclasses import dataclass

from backend.auth import require_patient_access
from backend.db import fact_from_row, get_conn
from backend.routes.language import user_language
from backend.routes.privacy import identity_for
from backend.scope import scoped


@dataclass
class AgentContext:
    user: dict
    patient_id: str
    role: str
    access: dict
    identity: dict
    lang: str

    @property
    def read_only(self):
        return self.access.get("kind") == "shared"

    def in_scope(self, facts):
        return scoped(facts, self.access)

    def facts(self):
        with get_conn() as conn:
            rows = conn.execute(
                """SELECT f.* FROM facts f JOIN documents d ON d.id = f.document_id
                   WHERE f.patient_id = ? AND d.held_back = 0 ORDER BY f.event_date, f.fact_id""",
                (self.patient_id,),
            ).fetchall()
        return self.in_scope([fact_from_row(r) for r in rows])


def agent_context(user, patient_id):
    access = require_patient_access(user, patient_id)  # raises 403 when the user may not see this patient
    return AgentContext(user=user, patient_id=patient_id, role=user["role"], access=access,
                        identity=identity_for(patient_id) or {}, lang=user_language(user))
