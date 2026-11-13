"""Partial sharing: the patient picks what a QR / code share shows, the doctor is told that
something is hidden (never what), and can ask the patient to share more. (Ashil)

Patient (own records only):
  GET  /patients/{id}/share-options     groups the patient can pick before making a QR:
       {"groups": [{"tag", "label", "count", "examples"}], "always": ["allergy", "demographic"]}
       count = different items (medicines, conditions, tests, events) in that group; one item
       can be in two groups (atenolol: blood pressure and heart), it is shown if either is picked.
  GET  /patients/{id}/share-requests    pending "please share more" requests:
       [{"id", "share_id", "doctor", "note", "created_at", "scope", "options": [group, ...]}]
  POST /share-requests/{id}/answer      {"add": "all" | ["heart", "other"]}  or  {"decline": true}
       -> {"id", "status": "answered" | "declined", "scope"}  (the share's new scope)

Doctor (with an open share or care-team access):
  GET  /patients/{id}/hidden            {"partial": false}  or
       {"partial": true, "can_request": bool, "request": {id, status, created_at, answered_at} | null,
        "hidden": {"total", "medicines", "current_medicines", "conditions", "tests", "events",
                   "documents", "flagged", "important"}}
       Only counts: the doctor never learns names, groups or dates of hidden records.
       "important": a hidden medicine that may be current, a hidden condition, or a hidden
       fact with a flag (contradiction, unit mismatch, ...). Polled by the screen, so not audited.
  POST /patients/{id}/share-requests    {"note": "Starting an antibiotic, need your current medicines"}
       Only with an open QR / code share; one pending request per share. The patient gets a
       notification (header bell) and answers on the Share page.

What a share shows is enforced in backend/auth.py + backend/scope.py like a care-team scope;
every route that returns facts already filters them. Allergies and blood group / sex / DOB are
always shown (safety). Requests are deleted with their share (backend/routes/share.py).
"""
from collections import Counter
from datetime import datetime, timezone
from typing import List, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import active_share, get_current_user, has_full_access, require_patient_access
from backend.db import get_conn, log_action
from backend.routes.fact_helpers import load_documents, load_facts, medication_summaries
from backend.routes.share import check_scope
from backend.scope import (ALWAYS_VISIBLE, SCOPE_LABELS, SCOPE_NAMES, access_scope, document_in_scope,
                           fact_in_scope, groups_of, parse_scope, scope_text, union_scope)

router = APIRouter()

MAX_EXAMPLES = 4
PROBLEM_FLAGS = {"contradiction", "duplicate", "unit_mismatch", "ambiguous_date", "wrong_patient", "implausible_value"}
COUNTED_TYPES = {"medication": "medicines", "condition": "conditions", "lab_test": "tests", "event": "events"}


def now_sql():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def shareable_facts(conn, patient_id):
    """Facts a scope can hide: from the documents (not backend-made gaps), not always-visible."""
    return [f for f in load_facts(conn, patient_id)
            if f["status"] != "not_documented" and f["type"] not in ALWAYS_VISIBLE]


def distinct(facts):
    """One fact per (type, name): count items, not mentions."""
    seen = {}
    for f in facts:
        seen.setdefault((f["type"], (f["name"] or "").strip().lower()), f)
    return list(seen.values())


def share_groups(conn, patient_id):
    """[{tag, label, count, examples}] for the groups this patient's records actually have."""
    members = {tag: [] for tag in SCOPE_NAMES}
    for f in shareable_facts(conn, patient_id):
        for tag in groups_of(f["type"], f["name"]):
            members[tag].append(f)
    out = []
    for tag in SCOPE_NAMES:
        names = [f["name"] for f in distinct(members[tag])]
        if names:
            out.append({"tag": tag, "label": SCOPE_LABELS[tag], "count": len(names), "examples": names[:MAX_EXAMPLES]})
    return out


def hidden_summary(conn, patient_id, scope):
    hidden = [f for f in shareable_facts(conn, patient_id) if not fact_in_scope(f, scope)]
    by_type = Counter(f["type"] for f in distinct(hidden))
    current = sum(1 for m in medication_summaries(hidden) if m["current"])
    flagged = sum(1 for f in hidden if PROBLEM_FLAGS & set(f.get("flags") or []))
    facts_by_doc = {}
    for f in load_facts(conn, patient_id):
        facts_by_doc.setdefault(f["document_id"], []).append(f)
    documents = sum(1 for doc_id, doc in load_documents(conn, patient_id).items()
                    if not doc["held_back"] and not document_in_scope(facts_by_doc.get(doc_id, []), scope))
    summary = {key: by_type.get(kind, 0) for kind, key in COUNTED_TYPES.items()}
    summary.update({
        "total": len(distinct(hidden)),
        "current_medicines": current,
        "documents": documents,
        "flagged": flagged,
        "important": bool(current or summary["conditions"] or flagged),
    })
    return summary


def require_own(user, patient_id, conn):
    if user["role"] != "patient" or not has_full_access(conn, user, patient_id):
        raise HTTPException(status_code=403, detail="Only the patient decides what to share")


def request_out(row):
    return {"id": row["id"], "status": row["status"], "created_at": row["created_at"],
            "answered_at": row["answered_at"], "added": parse_scope(row["added"]) if row["added"] else None}


# ---------- patient ----------

@router.get("/patients/{patient_id}/share-options")
def share_options(patient_id: str, user=Depends(get_current_user)):
    with get_conn() as conn:
        require_own(user, patient_id, conn)
        groups = share_groups(conn, patient_id)
    return {"groups": groups, "always": sorted(ALWAYS_VISIBLE)}


@router.get("/patients/{patient_id}/share-requests")
def pending_requests(patient_id: str, user=Depends(get_current_user)):
    with get_conn() as conn:
        require_own(user, patient_id, conn)
        conn.execute("DELETE FROM share_requests WHERE share_id NOT IN "
                     "(SELECT id FROM share_links WHERE expires_at > datetime('now'))")
        rows = conn.execute(
            """SELECT r.*, s.scope, COALESCE(u.full_name, u.username) AS doctor_name
               FROM share_requests r JOIN share_links s ON s.id = r.share_id
               JOIN users u ON u.id = r.doctor_id
               WHERE r.patient_id = ? AND r.status = 'pending' ORDER BY r.id""",
            (patient_id,),
        ).fetchall()
        groups = share_groups(conn, patient_id)
    out = []
    for r in rows:
        scope = parse_scope(r["scope"])
        out.append({
            "id": r["id"], "share_id": r["share_id"], "doctor": r["doctor_name"], "note": r["note"],
            "created_at": r["created_at"], "scope": scope,
            "options": [g for g in groups if scope != "all" and g["tag"] not in scope],
        })
    return out


class AnswerBody(BaseModel):
    add: Union[Literal["all"], List[str], None] = None
    decline: bool = False


@router.post("/share-requests/{request_id}/answer")
def answer_request(request_id: int, body: AnswerBody, user=Depends(get_current_user)):
    with get_conn() as conn:
        req = conn.execute("SELECT * FROM share_requests WHERE id = ?", (request_id,)).fetchone()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        require_own(user, req["patient_id"], conn)
        if req["status"] != "pending":
            raise HTTPException(status_code=409, detail="This request was already answered")
        share = conn.execute("SELECT * FROM share_links WHERE id = ? AND expires_at > datetime('now')",
                             (req["share_id"],)).fetchone()
        if not share:
            raise HTTPException(status_code=410, detail="This share has ended")
        scope = parse_scope(share["scope"])
        if body.decline or body.add is None:
            status, added = "declined", None
        else:
            added = check_scope(body.add)
            scope = union_scope(scope, added)
            status = "answered"
            conn.execute("UPDATE share_links SET scope = ? WHERE id = ?", (scope_text(scope), share["id"]))
        conn.execute("UPDATE share_requests SET status = ?, added = ?, answered_at = ? WHERE id = ?",
                     (status, scope_text(added) if added else None, now_sql(), request_id))
    log_action(user, "share_more_" + status, req["patient_id"], {"request_id": request_id, "added": added})
    return {"id": request_id, "status": status, "scope": scope}


# ---------- doctor ----------

@router.get("/patients/{patient_id}/hidden")
def hidden(patient_id: str, user=Depends(get_current_user)):
    access = require_patient_access(user, patient_id)
    scope = access_scope(access)
    if access["kind"] == "own" or scope == "all":
        return {"partial": False}
    with get_conn() as conn:
        summary = hidden_summary(conn, patient_id, scope)
        req = None
        if access.get("share_id"):
            req = conn.execute("SELECT * FROM share_requests WHERE share_id = ? AND doctor_id = ? ORDER BY id DESC",
                               (access["share_id"], user["id"])).fetchone()
    return {
        "partial": summary["total"] > 0 or summary["documents"] > 0,
        "hidden": summary,
        "can_request": bool(access.get("share_id")),
        "request": request_out(req) if req else None,
    }


class RequestBody(BaseModel):
    note: Optional[str] = Field(default=None, max_length=300)


@router.post("/patients/{patient_id}/share-requests")
def request_more(patient_id: str, body: RequestBody, user=Depends(get_current_user)):
    from backend.routes.refills import notify_patient  # the patient's header bell (Medha)

    if user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="Doctors ask; the patient decides")
    note = (body.note or "").strip() or None
    with get_conn() as conn:
        share = active_share(conn, user, patient_id)
        if not share:
            raise HTTPException(status_code=403, detail="Ask for more while the patient's QR / code share is open")
        if parse_scope(share["scope"]) == "all":
            raise HTTPException(status_code=409, detail="The patient already shares everything")
        if conn.execute("SELECT 1 FROM share_requests WHERE share_id = ? AND status = 'pending'",
                        (share["id"],)).fetchone():
            raise HTTPException(status_code=409, detail="You already asked; waiting for the patient")
        cur = conn.execute(
            "INSERT INTO share_requests (share_id, patient_id, doctor_id, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (share["id"], patient_id, user["id"], note, now_sql()),
        )
        doctor = conn.execute("SELECT COALESCE(full_name, username) AS name FROM users WHERE id = ?",
                              (user["id"],)).fetchone()["name"]
        notify_patient(conn, patient_id, "share_request",
                       f"{doctor} asks to see more of your records.", "/qr")
        row = conn.execute("SELECT * FROM share_requests WHERE id = ?", (cur.lastrowid,)).fetchone()
    log_action(user, "share_more_requested", patient_id, {"request_id": cur.lastrowid, "has_note": bool(note)})
    return request_out(row)
