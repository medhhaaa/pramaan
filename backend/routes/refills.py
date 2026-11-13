"""In-app prescriptions, medicine reminders, refill requests and notifications. (Medha)

Patient:
  GET  /patients/{id}/my-medicines          in-app medicines, today's reminders, refill state
  POST /reminders/{id}/log                  {"status": "taken" | "skipped", "date": "YYYY-MM-DD"?}
  POST /patients/{id}/refill-requests       {"prescription_item_id": 3, "note": "..."?}
  GET  /me/notifications                    newest first
  POST /notifications/{id}/read

Care-team doctor:
  POST /patients/{id}/prescriptions         {"items": [{medicine, dose, frequency, duration_days}],
                                             "override_reason": "..."?}
  GET  /patients/{id}/prescriptions         active in-app prescriptions (within scope)
  GET  /doctors/me/refill-requests          pending requests to this doctor
  GET  /refill-requests/{id}/review         medicine, brief, 30-day adherence, latest report, checks
  POST /refill-requests/{id}/decision       {"action": "approve" | "decline" | "visit",
                                             "note": "..."?, "override_reason": "..."?}

Rules:
- A refill can be requested only for an ACTIVE medicine on an IN-APP prescription (a
  prescription_items row; medicines read from documents can't be refilled here) whose
  prescribing doctor is on the patient's care team right now. One pending request per medicine.
- Prescribing and refill review re-run the existing allergy and duplicate checks
  (check_medicine.medicine_warnings). Going ahead despite a warning needs an override reason.
- Approve: a new prescription version with the same medicine, dose and duration; the
  reminders are extended by that duration. Decline: a doctor note is required. Ask to visit:
  optional note, default "Please book a visit before your next refill."
- The patient gets an in-app notification with the decision and note.
- Every prescription and every refill decision creates a consult record.
- Wording: the app never recommends approving or declining. It shows records and checks only.
"""
from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.adherence import adherence, daily, today_utc
from backend.auth import active_care_team, get_current_user, require_patient_access
from backend.db import get_conn, log_action
from backend.prescriptions import create_prescription, is_active, renew_item
from backend.routes.check_medicine import medicine_warnings
from backend.routes.consult_records import build_snapshot, create_consult_record, now_sql
from backend.routes.language import user_language
from backend.scope import access_scope, medicine_in_scope, tags_of

router = APIRouter()

VISIT_NOTE = "Please book a visit before your next refill."
ACTIONS = {"approve": "approved", "decline": "declined", "visit": "visit_required"}
ADHERENCE_REVIEW_DAYS = 30


def require_patient_role(user, patient_id):
    if user["role"] != "patient":
        raise HTTPException(status_code=403, detail="Only the patient can do this")
    require_patient_access(user, patient_id)


def require_care_team_doctor(user, patient_id):
    """A doctor on the patient's care team right now (a QR share alone is not enough)."""
    if user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="Doctors only")
    access = require_patient_access(user, patient_id)
    with get_conn() as conn:
        entry = active_care_team(conn, user, patient_id)
    if not entry:
        raise HTTPException(status_code=403, detail="Only a doctor on the patient's care team can do this")
    if access["kind"] != "care_team":  # a share is open too: still use the care-team scope
        from backend.scope import parse_scope
        access = {"kind": "care_team", "scope": parse_scope(entry["scope"]), "care_team_id": entry["id"]}
    return access


def item_row(conn, item_id):
    return conn.execute(
        """SELECT i.*, p.doctor_id, p.created_at AS prescribed_at, COALESCE(u.full_name, u.username) AS doctor_name
           FROM prescription_items i JOIN prescriptions p ON p.id = i.prescription_id JOIN users u ON u.id = p.doctor_id
           WHERE i.id = ?""",
        (item_id,),
    ).fetchone()


def first_prescribed(conn, item):
    """Date of the first prescription in this medicine's chain of refills."""
    at, row = item["prescribed_at"], item
    while row["previous_item_id"]:
        row = item_row(conn, row["previous_item_id"])
        at = row["prescribed_at"]
    return at


def refill_eligibility(conn, item, today):
    """(can_request, reason) for one prescription item."""
    if not is_active(item, today):
        return False, "not_active"
    if not conn.execute("SELECT 1 FROM care_team WHERE patient_id = ? AND doctor_id = ? AND status = 'active'",
                        (item["patient_id"], item["doctor_id"])).fetchone():
        return False, "doctor_not_on_care_team"
    if conn.execute("SELECT 1 FROM refill_requests WHERE prescription_item_id = ? AND status = 'pending'",
                    (item["id"],)).fetchone():
        return False, "pending"
    return True, None


def notify_patient(conn, patient_id, kind, text, link=None):
    users = conn.execute("SELECT user_id FROM user_patients WHERE patient_id = ?", (patient_id,)).fetchall()
    for u in users:
        conn.execute("INSERT INTO notifications (user_id, patient_id, kind, text, link) VALUES (?, ?, ?, ?, ?)",
                     (u["user_id"], patient_id, kind, text, link))


def med_label(item):
    return " ".join(x for x in [item["medicine"], item["dose"], item["frequency"]] if x)


# ---------- patient ----------

@router.get("/patients/{patient_id}/my-medicines")
def my_medicines(patient_id: str, user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    if user["role"] != "patient":
        raise HTTPException(status_code=403, detail="This is the patient's own screen")
    today = today_utc()
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT i.id FROM prescription_items i WHERE i.patient_id = ? AND i.status = 'active'
               ORDER BY i.end_date DESC""", (patient_id,)).fetchall()
        medicines = []
        for r in rows:
            item = item_row(conn, r["id"])
            can, reason = refill_eligibility(conn, item, today)
            last = conn.execute(
                """SELECT status, doctor_note, created_at, decided_at FROM refill_requests
                   WHERE prescription_item_id IN (SELECT id FROM prescription_items WHERE id = ? OR id = ?)
                   ORDER BY id DESC LIMIT 1""",
                (item["id"], item["previous_item_id"] or -1),
            ).fetchone()
            reminders = conn.execute(
                "SELECT * FROM reminders WHERE prescription_item_id = ? ORDER BY time_of_day", (item["id"],)).fetchall()
            taps = {t["reminder_id"]: t["status"] for t in conn.execute(
                "SELECT reminder_id, status FROM dose_logs WHERE dose_date = ? AND patient_id = ?",
                (today.isoformat(), patient_id))}
            medicines.append({
                "prescription_item_id": item["id"], "medicine": item["medicine"], "dose": item["dose"],
                "frequency": item["frequency"], "start_date": item["start_date"], "end_date": item["end_date"],
                "active": is_active(item, today), "doctor": item["doctor_name"], "prescribed_at": item["prescribed_at"],
                "can_request_refill": can, "refill_blocked_reason": reason,
                "last_refill_request": dict(last) if last else None,
                "today": [{"reminder_id": rm["id"], "time": rm["time_of_day"], "status": taps.get(rm["id"])}
                          for rm in reminders if rm["start_date"] <= today.isoformat() <= rm["end_date"]],
                "adherence_14d": adherence(conn, patient_id, 14, [item["id"]], today)["percent"],
            })
    log_action(user, "view_my_medicines", patient_id)
    return {"date": today.isoformat(), "medicines": medicines}


class DoseBody(BaseModel):
    status: Literal["taken", "skipped"]
    date: Optional[str] = None  # default today


@router.post("/reminders/{reminder_id}/log")
def log_dose(reminder_id: int, body: DoseBody, user=Depends(get_current_user)):
    with get_conn() as conn:
        rem = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
    if not rem:
        raise HTTPException(status_code=404, detail="Reminder not found")
    require_patient_role(user, rem["patient_id"])
    today = today_utc()
    try:
        day = date.fromisoformat(body.date) if body.date else today
    except ValueError:
        raise HTTPException(status_code=422, detail="Use a date like 2026-12-01")
    if day > today or not (rem["start_date"] <= day.isoformat() <= rem["end_date"]):
        raise HTTPException(status_code=422, detail="This reminder isn't due on that day")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO dose_logs (patient_id, reminder_id, dose_date, status) VALUES (?, ?, ?, ?)
               ON CONFLICT (reminder_id, dose_date) DO UPDATE SET status = excluded.status, logged_at = CURRENT_TIMESTAMP""",
            (rem["patient_id"], reminder_id, day.isoformat(), body.status),
        )
    log_action(user, "log_dose", rem["patient_id"], {"reminder_id": reminder_id, "date": day.isoformat(), "status": body.status})
    return {"reminder_id": reminder_id, "date": day.isoformat(), "status": body.status}


class RefillBody(BaseModel):
    prescription_item_id: int
    note: Optional[str] = Field(default=None, max_length=500)


@router.post("/patients/{patient_id}/refill-requests")
def request_refill(patient_id: str, body: RefillBody, user=Depends(get_current_user)):
    require_patient_role(user, patient_id)
    today = today_utc()
    with get_conn() as conn:
        item = item_row(conn, body.prescription_item_id)
        if not item or item["patient_id"] != patient_id:
            raise HTTPException(status_code=404, detail="Only medicines on a Pramaan prescription can be refilled here")
        can, reason = refill_eligibility(conn, item, today)
        if not can:
            messages = {
                "not_active": "This medicine is not active any more.",
                "doctor_not_on_care_team": "The prescribing doctor is not on your care team.",
                "pending": "A refill request for this medicine is already waiting.",
            }
            raise HTTPException(status_code=409 if reason == "pending" else 422, detail=messages[reason])
        cur = conn.execute(
            """INSERT INTO refill_requests (patient_id, doctor_id, prescription_item_id, status, patient_note, created_at)
               VALUES (?, ?, ?, 'pending', ?, ?)""",
            (patient_id, item["doctor_id"], item["id"], (body.note or "").strip() or None, now_sql()),
        )
    log_action(user, "request_refill", patient_id, {"refill_request_id": cur.lastrowid, "medicine": item["medicine"]})
    return {"id": cur.lastrowid, "status": "pending", "doctor": item["doctor_name"]}


@router.get("/me/notifications")
def my_notifications(user=Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 50", (user["id"],)).fetchall()
    return [dict(r) for r in rows]


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: int, user=Depends(get_current_user)):
    with get_conn() as conn:
        n = conn.execute("UPDATE notifications SET read_at = ? WHERE id = ? AND user_id = ? AND read_at IS NULL",
                         (now_sql(), notification_id, user["id"])).rowcount
    return {"id": notification_id, "updated": bool(n)}


# ---------- doctor: prescribing ----------

class ItemBody(BaseModel):
    medicine: str = Field(min_length=2, max_length=80)
    dose: Optional[str] = Field(default=None, max_length=40)
    frequency: Optional[str] = Field(default=None, max_length=40)
    duration_days: int = Field(ge=1, le=365)


class PrescriptionBody(BaseModel):
    items: List[ItemBody] = Field(min_length=1, max_length=10)
    override_reason: Optional[str] = Field(default=None, max_length=1000)


def overrides_for(warnings, reason):
    return [{"warning": w["text"], "kind": w["kind"], "reason": reason} for w in warnings]


def require_override(warnings, reason):
    if warnings and not (reason or "").strip():
        raise HTTPException(status_code=422, detail={
            "message": "These warnings were shown. To go ahead, give an override reason.",
            "warnings": warnings})


@router.post("/patients/{patient_id}/prescriptions")
def prescribe(patient_id: str, body: PrescriptionBody, user=Depends(get_current_user)):
    access = require_care_team_doctor(user, patient_id)
    scope = access_scope(access)
    for item in body.items:
        if not medicine_in_scope(item.medicine, scope):
            raise HTTPException(status_code=403, detail=f"{item.medicine} is outside your care-team scope")
    warnings = []
    for item in body.items:
        warnings += medicine_warnings(patient_id, item.medicine, access, "en")[2]
    require_override(warnings, body.override_reason)

    snapshot = build_snapshot(patient_id, access)  # the brief as it was before this prescription
    items = [i.model_dump() for i in body.items]
    with get_conn() as conn:
        pres_id = create_prescription(conn, patient_id, user["id"], items, today_utc())
        record_id = create_consult_record(
            conn, user["id"], patient_id, "prescription", snapshot,
            {"action": "prescribe", "prescription_id": pres_id, "items": items},
            warnings, overrides_for(warnings, body.override_reason.strip()) if warnings else [])
    log_action(user, "prescribe", patient_id, {"prescription_id": pres_id, "consult_record_id": record_id})
    return {"prescription_id": pres_id, "consult_record_id": record_id, "warnings": warnings}


@router.get("/patients/{patient_id}/prescriptions")
def list_prescriptions(patient_id: str, user=Depends(get_current_user)):
    from backend.routes.consult_records import active_prescriptions

    access = require_patient_access(user, patient_id)
    with get_conn() as conn:
        rows = active_prescriptions(conn, patient_id, access_scope(access))
    log_action(user, "view_prescriptions", patient_id)
    return rows


# ---------- doctor: refill review and decision ----------

def load_request(conn, request_id, user):
    req = conn.execute("SELECT * FROM refill_requests WHERE id = ?", (request_id,)).fetchone()
    if not req:
        raise HTTPException(status_code=404, detail="Refill request not found")
    if req["doctor_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="This refill request was sent to another doctor")
    return req


def latest_report(conn, patient_id, medicine, scope):
    """The newest lab result for a condition this medicine treats (by condition tag), with its source."""
    tags = set(tags_of("medication", medicine))
    if scope != "all":
        tags &= set(scope)
    if not tags:
        return None
    rows = conn.execute(
        """SELECT f.* FROM facts f JOIN documents d ON d.id = f.document_id
           WHERE f.patient_id = ? AND f.type = 'lab_test' AND f.status = 'documented' AND d.held_back = 0
           ORDER BY COALESCE(f.event_date, f.document_date) DESC, f.fact_id DESC""",
        (patient_id,),
    ).fetchall()
    for f in rows:
        if tags & set(tags_of("lab_test", f["name"])):
            return {"name": f["name"], "value": f["value"], "unit": f["unit"],
                    "date": f["event_date"] or f["document_date"], "fact_id": f["fact_id"],
                    "document_id": f["document_id"], "quote": f["quote"], "page": f["page"], "line": f["line"]}
    return None


def review_data(conn, req, access, today):
    item = item_row(conn, req["prescription_item_id"])
    scope = access_scope(access)
    doses = adherence(conn, req["patient_id"], ADHERENCE_REVIEW_DAYS, [item["id"]], today)
    return item, {
        "refill_request": {"id": req["id"], "status": req["status"], "patient_note": req["patient_note"],
                           "doctor_note": req["doctor_note"], "created_at": req["created_at"], "decided_at": req["decided_at"]},
        "medicine": {"prescription_item_id": item["id"], "medicine": item["medicine"], "dose": item["dose"],
                     "frequency": item["frequency"], "duration_days": item["duration_days"],
                     "start_date": item["start_date"], "end_date": item["end_date"],
                     "prescribed_at": item["prescribed_at"], "first_prescribed_at": first_prescribed(conn, item),
                     "doctor": item["doctor_name"]},
        "adherence_30d": {**doses, "days": daily(conn, req["patient_id"], [item["id"]], ADHERENCE_REVIEW_DAYS, today)},
        "latest_report": latest_report(conn, req["patient_id"], item["medicine"], scope),
    }


@router.get("/doctors/me/refill-requests")
def my_refill_requests(user=Depends(get_current_user)):
    if user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="Doctors only")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT r.*, p.name AS patient_name, i.medicine, i.dose, i.frequency FROM refill_requests r
               JOIN patients p ON p.id = r.patient_id JOIN prescription_items i ON i.id = r.prescription_item_id
               WHERE r.doctor_id = ? AND r.status = 'pending'
                 AND EXISTS (SELECT 1 FROM care_team c WHERE c.doctor_id = r.doctor_id AND c.patient_id = r.patient_id AND c.status = 'active')
               ORDER BY r.created_at""",
            (user["id"],),
        ).fetchall()
    log_action(user, "view_refill_requests", None, {"count": len(rows)})
    return [dict(r) for r in rows]


@router.get("/refill-requests/{request_id}/review")
def review(request_id: int, user=Depends(get_current_user)):
    with get_conn() as conn:
        req = load_request(conn, request_id, user)
    access = require_care_team_doctor(user, req["patient_id"])
    from backend.routes.brief import build_brief

    with get_conn() as conn:
        item, data = review_data(conn, req, access, today_utc())
        patient = conn.execute("SELECT name, dob, sex FROM patients WHERE id = ?", (req["patient_id"],)).fetchone()
    _, _, warnings = medicine_warnings(req["patient_id"], item["medicine"], access, user_language(user), renewing_item=item)
    out = {**data, "patient_id": req["patient_id"], "patient": dict(patient),
           "brief": build_brief(req["patient_id"], access, user_language(user)),
           "warnings": warnings,
           "note": "Records and checks only. The decision is yours."}
    log_action(user, "view_refill_review", req["patient_id"], {"refill_request_id": request_id})
    return out


class DecisionBody(BaseModel):
    action: Literal["approve", "decline", "visit"]
    note: Optional[str] = Field(default=None, max_length=1000)
    override_reason: Optional[str] = Field(default=None, max_length=1000)


@router.post("/refill-requests/{request_id}/decision")
def decide(request_id: int, body: DecisionBody, user=Depends(get_current_user)):
    with get_conn() as conn:
        req = load_request(conn, request_id, user)
    access = require_care_team_doctor(user, req["patient_id"])
    if req["status"] != "pending":
        raise HTTPException(status_code=409, detail="This refill request was already decided")
    note = (body.note or "").strip() or None
    if body.action == "decline" and not note:
        raise HTTPException(status_code=422, detail="A note for the patient is required to decline")
    if body.action == "visit":
        note = note or VISIT_NOTE

    today = today_utc()
    with get_conn() as conn:
        item, data = review_data(conn, req, access, today)
    _, _, warnings = medicine_warnings(req["patient_id"], item["medicine"], access, "en", renewing_item=item)
    if body.action == "approve":
        require_override(warnings, body.override_reason)
    overrides = overrides_for(warnings, body.override_reason.strip()) if body.action == "approve" and warnings else []
    snapshot = build_snapshot(req["patient_id"], access, data)  # what the review screen showed

    with get_conn() as conn:
        decision = {"action": body.action, "status": ACTIONS[body.action], "note": note,
                    "refill_request_id": request_id, "medicine": med_label(item), "prescription_item_id": item["id"]}
        if body.action == "approve":
            new_pres, new_item = renew_item(conn, item, user["id"], today)
            end = conn.execute("SELECT end_date FROM prescription_items WHERE id = ?", (new_item,)).fetchone()[0]
            decision.update({"new_prescription_id": new_pres, "new_prescription_item_id": new_item, "reminders_until": end})
            text = f"{item['doctor_name']} approved your refill of {med_label(item)}. Reminders now run until {end}."
        elif body.action == "decline":
            text = f"{item['doctor_name']} declined your refill of {med_label(item)}."
        else:
            text = f"{item['doctor_name']} asked you to book a visit about {med_label(item)}."
        if note:
            text += f' Note: "{note}"'
        conn.execute("UPDATE refill_requests SET status = ?, doctor_note = ?, decided_at = ? WHERE id = ?",
                     (ACTIONS[body.action], note, now_sql(), request_id))
        record_id = create_consult_record(conn, user["id"], req["patient_id"], "refill_decision",
                                          snapshot, decision, warnings, overrides)
        notify_patient(conn, req["patient_id"], "refill_" + ACTIONS[body.action], text, "/my-medicines")
    log_action(user, "decide_refill", req["patient_id"],
               {"refill_request_id": request_id, "action": body.action, "consult_record_id": record_id})
    return {"id": request_id, "status": ACTIONS[body.action], "note": note, "consult_record_id": record_id,
            **{k: decision[k] for k in ("new_prescription_id", "new_prescription_item_id", "reminders_until") if k in decision}}
