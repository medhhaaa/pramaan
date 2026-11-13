"""Privacy preview for the chat screen + the patient identity the privacy layer uses. (Core backend)

POST /patients/{id}/privacy-preview  {"text": "..."}
    -> {"original", "redacted", "findings": [{"text", "start", "end", "kind", "layer"}],
        "by_layer": {"1 known identity": [...], "2 pattern": [...], "3 NER": [...], "4 context": [...]},
        "blocked": bool, "still_found": [...]}
    Nothing is sent to any AI. The chat screen shows the user exactly what would be sent; if
    "blocked" is true, the AI will refuse until the user removes what is listed in still_found.
    The token map stays on the server (it is not returned), so real values never travel with
    the redacted text.

identity_for(patient_id) -> {"name", "dob", "phone", "address"} from the patients table.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import get_current_user, require_patient_access
from backend.db import get_conn, log_action
from pipeline.privacy_layer import preview

router = APIRouter()


def identity_for(patient_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    if not row:
        return None
    row = dict(row)
    return {k: row.get(k) for k in ("name", "dob", "phone", "address")}


class PreviewBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/patients/{patient_id}/privacy-preview")
def privacy_preview(patient_id: str, body: PreviewBody, user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    identity = identity_for(patient_id)
    if identity is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    result = preview(body.text, identity)
    result.pop("tokens", None)  # the token -> real value map never leaves the server
    log_action(user, "privacy_preview", patient_id, {"found": len(result["findings"]), "blocked": result["blocked"]})
    return result
