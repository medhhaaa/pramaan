"""Consult records: a medico-legal snapshot of every prescription and refill decision. (Medha)

    GET  /patients/{id}/consult-records        list (a doctor sees the records they made;
                                               the patient sees all of theirs)
    GET  /consult-records/{id}                 the record as JSON
    GET  /consult-records/{id}/pdf             printable PDF
    GET  /consult-records/{id}/verify          {"valid": true | false}: recomputes the hash
    POST /consult-records/{id}/corrections     {"note": "..."}: a NEW record that points at the
                                               original (corrects_record_id). The original is kept.

Records are created by code only (create_consult_record, called on every prescription and every
refill decision) and are never updated or deleted: there is no PUT, PATCH or DELETE route.

snapshot_json   the 60-second brief exactly as the doctor's screen built it at that moment
                (current medicines, allergies, conditions, results, red flags, open questions;
                scoped to what this doctor may see), plus active in-app prescriptions and the
                source document IDs. Data, not screenshots. Stored in English, the record language.
decision_json   what the doctor decided (and any note)
warnings_shown_json  the allergy / duplicate warnings shown before deciding
overrides_json  [{"warning": ..., "reason": ...}] when the doctor went ahead despite a warning
sha256          SHA-256 of the canonical JSON (sorted keys, no spaces) of every other column,
                including id and created_at. /verify recomputes it, so any edit made directly in
                the database shows as valid: false.

Who may read a record: the patient, and the doctor who made it (even after the patient revokes
their care-team access: it is the doctor's own medico-legal record of what they did).
"""
import hashlib
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.auth import get_current_user, has_full_access, require_patient_access
from backend.db import get_conn, log_action

router = APIRouter()

HASHED_FIELDS = ["id", "doctor_id", "patient_id", "type", "snapshot_json", "decision_json",
                 "warnings_shown_json", "overrides_json", "corrects_record_id", "created_at"]
JSON_FIELDS = ["snapshot_json", "decision_json", "warnings_shown_json", "overrides_json"]


def now_sql():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def record_hash(row):
    """SHA-256 of the canonical JSON of every field except sha256."""
    return hashlib.sha256(canonical({f: row[f] for f in HASHED_FIELDS}).encode("utf-8")).hexdigest()


def document_ids(value):
    """Every document_id mentioned anywhere in a snapshot."""
    found = set()
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "document_id" and v:
                found.add(v)
            else:
                found |= document_ids(v)
    elif isinstance(value, list):
        for v in value:
            found |= document_ids(v)
    return found


def active_prescriptions(conn, patient_id, scope="all"):
    from backend.adherence import today_utc
    from backend.scope import medicine_in_scope

    rows = conn.execute(
        """SELECT i.medicine, i.dose, i.frequency, i.start_date, i.end_date, i.id AS prescription_item_id,
                  COALESCE(u.full_name, u.username) AS doctor
           FROM prescription_items i JOIN prescriptions p ON p.id = i.prescription_id JOIN users u ON u.id = p.doctor_id
           WHERE i.patient_id = ? AND i.status = 'active' AND i.end_date >= ? ORDER BY i.id""",
        (patient_id, today_utc().isoformat()),
    ).fetchall()
    return [dict(r) for r in rows if medicine_in_scope(r["medicine"], scope)]


def build_snapshot(patient_id, access, extra=None):
    """The brief as this doctor's screen shows it right now, plus in-app prescriptions."""
    from backend.routes.brief import build_brief
    from backend.scope import access_scope

    brief = build_brief(patient_id, access, "en")
    with get_conn() as conn:
        prescriptions = active_prescriptions(conn, patient_id, access_scope(access))
    snap = {"brief": brief, "active_in_app_prescriptions": prescriptions, **(extra or {})}
    snap["source_document_ids"] = sorted(document_ids(snap))
    return snap


def create_consult_record(conn, doctor_id, patient_id, type_, snapshot, decision,
                          warnings=(), overrides=(), corrects_record_id=None, created_at=None):
    """Insert one record and its hash in the same transaction. Returns the new id."""
    row = {
        "doctor_id": doctor_id, "patient_id": patient_id, "type": type_,
        "snapshot_json": canonical(snapshot), "decision_json": canonical(decision),
        "warnings_shown_json": canonical(list(warnings)), "overrides_json": canonical(list(overrides)),
        "corrects_record_id": corrects_record_id, "created_at": created_at or now_sql(),
    }
    cur = conn.execute(
        """INSERT INTO consult_records (doctor_id, patient_id, type, snapshot_json, decision_json,
               warnings_shown_json, overrides_json, corrects_record_id, created_at, sha256)
           VALUES (:doctor_id, :patient_id, :type, :snapshot_json, :decision_json,
                   :warnings_shown_json, :overrides_json, :corrects_record_id, :created_at, '')""",
        row,
    )
    row["id"] = cur.lastrowid
    conn.execute("UPDATE consult_records SET sha256 = ? WHERE id = ?", (record_hash(row), row["id"]))
    return row["id"]


def load_record(record_id, user):
    """The record, if this user is the patient or the doctor who made it."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT c.*, COALESCE(u.full_name, u.username) AS doctor_name, u.registration_number,
                      p.name AS patient_name, p.dob AS patient_dob, p.sex AS patient_sex
               FROM consult_records c JOIN users u ON u.id = c.doctor_id JOIN patients p ON p.id = c.patient_id
               WHERE c.id = ?""",
            (record_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Consult record not found")
        allowed = row["doctor_id"] == user["id"] or has_full_access(conn, user, row["patient_id"])
    if not allowed:
        raise HTTPException(status_code=403, detail="Only the patient and the doctor who made it can open this record")
    return row


def record_out(row):
    out = {f: row[f] for f in HASHED_FIELDS + ["sha256"]}
    for f in JSON_FIELDS:
        out[f.replace("_json", "")] = json.loads(row[f])
        del out[f]
    out["doctor"] = {"id": row["doctor_id"], "name": row["doctor_name"], "registration_number": row["registration_number"]}
    out["patient"] = {"id": row["patient_id"], "name": row["patient_name"], "dob": row["patient_dob"], "sex": row["patient_sex"]}
    return out


@router.get("/patients/{patient_id}/consult-records")
def list_records(patient_id: str, user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    with get_conn() as conn:
        sql = """SELECT c.id, c.type, c.created_at, c.corrects_record_id, c.decision_json, c.doctor_id,
                        COALESCE(u.full_name, u.username) AS doctor_name
                 FROM consult_records c JOIN users u ON u.id = c.doctor_id WHERE c.patient_id = ?"""
        args = [patient_id]
        if user["role"] == "doctor":
            sql += " AND c.doctor_id = ?"
            args.append(user["id"])
        rows = conn.execute(sql + " ORDER BY c.id DESC", args).fetchall()
    log_action(user, "view_consult_records", patient_id)
    return [{"id": r["id"], "type": r["type"], "created_at": r["created_at"], "doctor_name": r["doctor_name"],
             "corrects_record_id": r["corrects_record_id"], "decision": json.loads(r["decision_json"])} for r in rows]


@router.get("/consult-records/{record_id}")
def get_record(record_id: int, user=Depends(get_current_user)):
    row = load_record(record_id, user)
    log_action(user, "view_consult_record", row["patient_id"], {"record_id": record_id})
    return record_out(row)


@router.get("/consult-records/{record_id}/verify")
def verify_record(record_id: int, user=Depends(get_current_user)):
    row = load_record(record_id, user)
    valid = record_hash(row) == row["sha256"]
    log_action(user, "verify_consult_record", row["patient_id"], {"record_id": record_id, "valid": valid})
    return {"id": record_id, "valid": valid, "sha256": row["sha256"], "recomputed": record_hash(row)}


class CorrectionBody(BaseModel):
    note: str = Field(min_length=3, max_length=2000)


@router.post("/consult-records/{record_id}/corrections")
def correct_record(record_id: int, body: CorrectionBody, user=Depends(get_current_user)):
    row = load_record(record_id, user)
    if row["doctor_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Only the doctor who made a record can correct it")
    access = require_patient_access(user, row["patient_id"])
    snapshot = build_snapshot(row["patient_id"], access)
    decision = {"correction_of": record_id, "note": body.note.strip(),
                "original_decision": json.loads(row["decision_json"])}
    with get_conn() as conn:
        new_id = create_consult_record(conn, user["id"], row["patient_id"], row["type"], snapshot, decision,
                                       corrects_record_id=record_id)
    log_action(user, "correct_consult_record", row["patient_id"], {"record_id": record_id, "new_record_id": new_id})
    return {"id": new_id, "corrects_record_id": record_id}


# ---------- PDF ----------

def pdf_bytes(rec):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from xml.sax.saxutils import escape

    styles = getSampleStyleSheet()
    body, small = styles["BodyText"], styles["Code"]
    out = []

    def h(text):
        out.append(Spacer(1, 3 * mm))
        out.append(Paragraph(escape(text), styles["Heading3"]))

    def p(text, style=body):
        out.append(Paragraph(escape(str(text)), style))

    def items(lines):
        if not lines:
            p("None recorded.")
        for line in lines:
            p(f"- {line}")

    snap, brief = rec["snapshot"], rec["snapshot"].get("brief", {})
    out.append(Paragraph(f"Pramaan consult record #{rec['id']}", styles["Title"]))
    p(f"Type: {rec['type'].replace('_', ' ')}    Created (UTC): {rec['created_at']}")
    if rec["corrects_record_id"]:
        p(f"This record corrects record #{rec['corrects_record_id']}. The original is kept unchanged.")
    pt, dr = rec["patient"], rec["doctor"]
    p(f"Patient: {pt['name']} ({pt['id']}), {pt['sex'] or '?'}, born {pt['dob'] or '?'}")
    p(f"Doctor: {dr['name']}, registration number {dr['registration_number'] or 'not recorded'}")

    h("Decision")
    for k, v in rec["decision"].items():
        p(f"{k.replace('_', ' ')}: {v if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False)}")
    h("Warnings shown")
    items([w.get("text", "") for w in rec["warnings_shown"]])
    h("Overrides")
    items([f"{o.get('warning', '')} -- reason: {o.get('reason', '')}" for o in rec["overrides"]])

    h("Snapshot: the brief as shown")
    p("Current medicines:")
    items([" ".join(x for x in [m.get("name"), m.get("dose"), m.get("frequency")] if x) for m in brief.get("current_medicines", [])])
    p("Allergies:")
    items([f"{a.get('name')} ({a.get('status', '')})" for a in brief.get("allergies", [])])
    p("Conditions:")
    items([c.get("name") for c in brief.get("conditions", [])])
    p("Latest results:")
    items([f"{r.get('name')} {r.get('value') or ''} {r.get('unit') or ''} ({r.get('event_date') or r.get('date') or ''})"
           for r in brief.get("latest_results", [])])
    p("Red flags:")
    items([f.get("text") or f.get("flag") for f in brief.get("red_flags", [])])
    p("Open questions:")
    items([q.get("text") for q in brief.get("open_questions", [])])
    p("Active in-app prescriptions:")
    items([f"{x['medicine']} {x.get('dose') or ''} {x.get('frequency') or ''} until {x['end_date']} ({x['doctor']})"
           for x in snap.get("active_in_app_prescriptions", [])])
    for key in ("refill_request", "adherence_30d", "latest_report"):
        if snap.get(key):
            p(f"{key.replace('_', ' ')}: {json.dumps(snap[key], ensure_ascii=False)}")
    p(f"Source documents: {', '.join(snap.get('source_document_ids', [])) or 'none'}")

    h("Integrity")
    p("SHA-256 of the canonical JSON of all other fields:")
    p(rec["sha256"], small)
    p("Check it any time with GET /consult-records/{id}/verify.")

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, title=f"Consult record {rec['id']}",
                      leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm).build(out)
    return buf.getvalue()


@router.get("/consult-records/{record_id}/pdf")
def record_pdf(record_id: int, user=Depends(get_current_user)):
    row = load_record(record_id, user)
    log_action(user, "download_consult_record", row["patient_id"], {"record_id": record_id})
    return Response(pdf_bytes(record_out(row)), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="consult_record_{record_id}.pdf"'})
