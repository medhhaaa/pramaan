"""GET /patients -> patients this user can access. (Core backend)

Each patient: {"id", "name", "dob", "sex", "blood_group", "shared_until", "care_team"}
shared_until is null for the user's own patients. For a patient a doctor opened by QR / code
(backend/routes/share.py) it is the time the read-only access ends ("2026-11-12T18:30:00Z").
care_team is true for a doctor's care-team patients (backend/routes/care_team.py): lasting
access until the patient revokes it.
"""
from fastapi import APIRouter, Depends

from backend.auth import get_current_user
from backend.db import get_conn, log_action

router = APIRouter()


@router.get("/patients")
def list_patients(user=Depends(get_current_user)):
    with get_conn() as conn:
        own = conn.execute(
            """SELECT p.* FROM patients p
               JOIN user_patients up ON up.patient_id = p.id
               WHERE up.user_id = ? ORDER BY p.id""",
            (user["id"],),
        ).fetchall() if user["role"] == "patient" else []  # doctors: only shared patients
        shared = conn.execute(
            """SELECT p.*, MAX(s.expires_at) AS expires_at FROM patients p
               JOIN share_links s ON s.patient_id = p.id
               WHERE s.opened_by = ? AND s.expires_at > datetime('now')
               GROUP BY p.id ORDER BY p.id""",
            (user["id"],),
        ).fetchall()
        team = conn.execute(
            """SELECT p.* FROM patients p JOIN care_team c ON c.patient_id = p.id
               WHERE c.doctor_id = ? AND c.status = 'active' ORDER BY p.id""",
            (user["id"],),
        ).fetchall() if user["role"] == "doctor" else []
    log_action(user, "list_patients")

    patients = [{**dict(r), "shared_until": None, "care_team": False} for r in own]
    team_ids = {r["id"] for r in team}
    for r in shared:
        p = dict(r)
        p["shared_until"] = p.pop("expires_at").replace(" ", "T") + "Z"
        p["care_team"] = p["id"] in team_ids
        patients.append(p)
    listed = {p["id"] for p in patients}
    patients += [{**dict(r), "shared_until": None, "care_team": True} for r in team if r["id"] not in listed]
    return sorted(patients, key=lambda p: p["id"])
