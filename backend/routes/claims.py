"""Claim Documents: documents COMMONLY needed for an insurance reimbursement claim after a
hospital stay, and which of them are already saved in Pramaan. (Medha)

No insurer integration and no claim decision of any kind: the insurer makes the final decision.
Wording rule (UI, API and the pack's checklist page): say "commonly needed", "saved",
"not saved yet"; never "complete", "eligible", "approved", "guaranteed", or a claim deadline.

POST  /patients/{pid}/hospital-stays                   {"admitted_on"?, "discharged_on"?}
      -> the new stay (patient only). Also adds its 3 condition questions to Things to Check.
GET   /patients/{pid}/hospital-stays                   -> [stay + "summary"], newest first
PATCH /patients/{pid}/hospital-stays/{sid}             {"admitted_on"?, "discharged_on"?, "my_reminder_date"?}
      (patient only; dates the patient types themselves)
GET   /patients/{pid}/hospital-stays/{sid}/claim-checklist
      -> {"stay", "items", "summary", "also_keep_ready", "reminder", "condition_questions", "note"}
GET   /patients/{pid}/hospital-stays/{sid}/claim-pack
      -> a zip: saved documents named in checklist order (01_discharge_summary.pdf, ...)
         plus checklist.txt listing every item and its status.

A stay is also opened automatically when a discharge summary is saved with a verified
doc_type and the patient has no open stay (stay_from_discharge_summary, called by ingest.py).
The conditions (surgery, implant_used, accident) are answered by the patient through the
Things to Check questions: Yes -> true, No -> false, I don't know / unanswered -> null.
The checklist itself is pipeline/claim_checklist.py (plain code, no AI).
"""
import io
import json
import re
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, field_validator

from backend.auth import get_current_user, require_patient_access
from backend.db import get_conn
from backend.routes.audit_helper import log_action
from backend.storage import read_file
from pipeline.claim_checklist import CONDITIONS, build_checklist, load_rules

router = APIRouter()

NOTE = ("Documents commonly requested for reimbursement claims. Your insurer may ask for "
        "different or additional documents. Check your policy.")
FINAL_DECISION = "Your insurer makes the final decision."
# not uploaded documents: shown as a plain reminder, never tracked
ALSO_KEEP_READY = [
    {"key": "claim_form", "label": "Claim form"},
    {"key": "policy_copy", "label": "Policy copy or e-card"},
    {"key": "id_proof", "label": "ID proof"},
    {"key": "bank_details", "label": "Bank details (cancelled cheque)"},
]
STATUS_TEXT = {
    "saved": "saved",
    "not_saved": "not saved yet",
    "unsure": "not sure if needed",
    "not_needed": "not needed",
}
CONDITION_QUESTIONS = {
    "surgery": ("Did you have surgery during this hospital stay?",
                "ಈ ಆಸ್ಪತ್ರೆ ವಾಸದ ಸಮಯದಲ್ಲಿ ನಿಮಗೆ ಶಸ್ತ್ರಚಿಕಿತ್ಸೆ ಆಯಿತೇ?"),
    "implant_used": ("Was an implant used (e.g. stent, plate, lens, joint)?",
                     "ಇಂಪ್ಲಾಂಟ್ ಬಳಸಲಾಗಿದೆಯೇ (ಉದಾ. ಸ್ಟೆಂಟ್, ಪ್ಲೇಟ್, ಲೆನ್ಸ್, ಕೀಲು)?"),
    "accident": ("Was this hospital stay due to an accident?",
                 "ಈ ಆಸ್ಪತ್ರೆ ವಾಸ ಅಪಘಾತದಿಂದಾಗಿ ಆಯಿತೇ?"),
}
CLAIM_ANSWERS = {"yes": 1, "no": 0, "dont_know": None}
REMINDER_DAYS = 2
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------- stays ----------

def stay_out(row):
    stay = dict(row)
    for condition in CONDITIONS:
        stay[condition] = None if stay[condition] is None else bool(stay[condition])
    return stay


def load_stay(conn, patient_id, stay_id):
    row = conn.execute(
        "SELECT * FROM hospital_stays WHERE id = ? AND patient_id = ?", (stay_id, patient_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Hospital stay not found")
    return stay_out(row)


def sync_claim_questions(conn, patient_id):
    """Every stay gets its 3 condition questions once (kept whatever their status)."""
    stays = conn.execute("SELECT id FROM hospital_stays WHERE patient_id = ?", (patient_id,)).fetchall()
    for stay in stays:
        for condition, (text, text_kn) in CONDITION_QUESTIONS.items():
            exists = conn.execute(
                "SELECT 1 FROM questions WHERE stay_id = ? AND claim_condition = ?", (stay["id"], condition)
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO questions (patient_id, fact_ids, text, text_kn, stay_id, claim_condition)"
                    " VALUES (?, '[]', ?, ?, ?, ?)",
                    (patient_id, text, text_kn, stay["id"], condition),
                )


def create_stay(conn, patient_id, source, admitted_on=None, discharged_on=None, document_id=None):
    cur = conn.execute(
        "INSERT INTO hospital_stays (patient_id, admitted_on, discharged_on, source, source_document_id)"
        " VALUES (?, ?, ?, ?, ?)",
        (patient_id, admitted_on, discharged_on, source, document_id),
    )
    sync_claim_questions(conn, patient_id)
    return cur.lastrowid


def stay_from_discharge_summary(patient_id, document_id, dates):
    """Called by ingest.py for a verified discharge summary. dates were verified by the pipeline.
    An open stay (no discharge date yet) gets the missing dates; otherwise a new stay is opened."""
    with get_conn() as conn:
        open_stay = conn.execute(
            "SELECT * FROM hospital_stays WHERE patient_id = ? AND discharged_on IS NULL ORDER BY id DESC",
            (patient_id,),
        ).fetchone()
        if open_stay:
            conn.execute(
                "UPDATE hospital_stays SET admitted_on = COALESCE(admitted_on, ?),"
                " discharged_on = COALESCE(discharged_on, ?) WHERE id = ?",
                (dates.get("admitted_on"), dates.get("discharged_on"), open_stay["id"]),
            )
            return open_stay["id"]
        return create_stay(conn, patient_id, "discharge_summary",
                           dates.get("admitted_on"), dates.get("discharged_on"), document_id)


def answer_claim_question(question, answer, user):
    """Things to Check answer for a condition question. Returns the new question status."""
    if user["role"] != "patient":
        raise HTTPException(status_code=403, detail="Only the patient answers this question.")
    if answer not in CLAIM_ANSWERS:
        raise HTTPException(status_code=422, detail="Answer yes, no or dont_know.")
    with get_conn() as conn:
        conn.execute(
            f"UPDATE hospital_stays SET {question['claim_condition']} = ? WHERE id = ?",
            (CLAIM_ANSWERS[answer], question["stay_id"]),
        )
    # "I don't know" keeps the question open, so it can be answered later
    return "open" if answer == "dont_know" else "answered"


# ---------- checklist ----------

def patient_documents(conn, patient_id):
    rows = conn.execute(
        "SELECT id, patient_id, filename, doc_type, document_date, held_back, file_path,"
        " doc_type_quote, doc_type_page, doc_type_line FROM documents WHERE patient_id = ? ORDER BY id",
        (patient_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def show_reminder(stay):
    if not stay["discharged_on"]:
        return True
    created = datetime.strptime(stay["created_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - created <= timedelta(days=REMINDER_DAYS)


def checklist_for(conn, patient_id, stay):
    documents = patient_documents(conn, patient_id)
    result = build_checklist(load_rules(), documents, stay)
    by_id = {d["id"]: d for d in documents}
    for item in result["items"]:
        item["documents"] = [
            {key: by_id[i][key] for key in ("id", "filename", "doc_type", "document_date",
                                             "doc_type_quote", "doc_type_page", "doc_type_line")}
            for i in item["document_ids"]
        ]
    questions = conn.execute(
        "SELECT id, claim_condition, status FROM questions WHERE stay_id = ?", (stay["id"],)
    ).fetchall()
    not_saved = [i["doc"] for i in result["items"] if i["status"] == "not_saved"]
    return {
        "stay": stay,
        **result,
        "also_keep_ready": ALSO_KEEP_READY,
        "reminder": {"show": show_reminder(stay) and bool(not_saved), "docs": not_saved},
        "condition_questions": {q["claim_condition"]: {"id": q["id"], "status": q["status"]} for q in questions},
        "note": NOTE,
    }


def stay_summary(conn, patient_id, stay):
    return build_checklist(load_rules(), patient_documents(conn, patient_id), stay)["summary"]


# ---------- routes ----------

def require_patient(user):
    if user["role"] != "patient":
        raise HTTPException(status_code=403, detail="Only the patient can do this.")


class StayBody(BaseModel):
    admitted_on: Optional[str] = None
    discharged_on: Optional[str] = None
    my_reminder_date: Optional[str] = None

    @field_validator("admitted_on", "discharged_on", "my_reminder_date")
    @classmethod
    def iso_date(cls, value):
        if value in (None, ""):
            return None
        if not ISO_DATE.match(value):
            raise ValueError("Use the format YYYY-MM-DD.")
        return value


@router.post("/patients/{patient_id}/hospital-stays")
def create_stay_route(patient_id: str, body: Optional[StayBody] = None, user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    require_patient(user)
    body = body or StayBody()
    with get_conn() as conn:
        stay_id = create_stay(conn, patient_id, "patient", body.admitted_on, body.discharged_on)
        stay = load_stay(conn, patient_id, stay_id)
    log_action(user, "create_hospital_stay", patient_id, f"stay {stay_id}")
    return stay


@router.get("/patients/{patient_id}/hospital-stays")
def list_stays(patient_id: str, user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM hospital_stays WHERE patient_id = ? ORDER BY id DESC", (patient_id,)
        ).fetchall()
        stays = [stay_out(r) for r in rows]
        for stay in stays:
            stay["summary"] = stay_summary(conn, patient_id, stay)
    return stays


@router.patch("/patients/{patient_id}/hospital-stays/{stay_id}")
def update_stay(patient_id: str, stay_id: int, body: StayBody, user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    require_patient(user)
    changes = body.model_dump(exclude_unset=True)
    with get_conn() as conn:
        load_stay(conn, patient_id, stay_id)
        for field, value in changes.items():  # field names come from StayBody only
            conn.execute(f"UPDATE hospital_stays SET {field} = ? WHERE id = ?", (value, stay_id))
        stay = load_stay(conn, patient_id, stay_id)
    log_action(user, "update_hospital_stay", patient_id, {"stay": stay_id, **changes})
    return stay


@router.get("/patients/{patient_id}/hospital-stays/{stay_id}/claim-checklist")
def claim_checklist(patient_id: str, stay_id: int, user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    with get_conn() as conn:
        sync_claim_questions(conn, patient_id)
        result = checklist_for(conn, patient_id, load_stay(conn, patient_id, stay_id))
    s = result["summary"]
    log_action(user, "view_claim_checklist", patient_id,
               f"stay {stay_id}: {s['saved_count']} of {s['required_count']} saved")
    return result


def pack_filenames(items):
    """[(item doc, document, "01_discharge_summary.pdf")] in checklist order; a second document
    of the same kind gets _2, _3 ..."""
    names = []
    for number, item in enumerate(items, start=1):
        for n, doc in enumerate(item["documents"], start=1):
            suffix = "" if n == 1 else f"_{n}"
            names.append((item["doc"], doc, f"{number:02d}_{item['doc']}{suffix}.pdf"))
    return names


def checklist_text(result, files_by_doc):
    stay, s = result["stay"], result["summary"]
    dates = (f"{stay['admitted_on'] or 'date not known'} to {stay['discharged_on'] or 'date not known'}"
             if stay["admitted_on"] or stay["discharged_on"] else "dates not known")
    lines = [
        "Pramaan: documents commonly needed for a reimbursement claim",
        f"Hospital stay: {dates}",
        f"{s['saved_count']} of {s['required_count']} documents saved in Pramaan.",
        "",
        NOTE,
        FINAL_DECISION,
        "",
    ]
    for number, item in enumerate(result["items"], start=1):
        line = f"{number:02d}  {item['label']}: {STATUS_TEXT[item['status']]}"
        if files_by_doc.get(item["doc"]):
            line += " (" + ", ".join(files_by_doc[item["doc"]]) + ")"
        lines.append(line)
    lines += [
        "",
        "Also keep ready (not stored in Pramaan): " + ", ".join(i["label"] for i in ALSO_KEEP_READY),
        "",
        "Information from your records only. Not medical advice.",
    ]
    return "\n".join(lines) + "\n"


@router.get("/patients/{patient_id}/hospital-stays/{stay_id}/claim-pack")
def claim_pack(patient_id: str, stay_id: int, user=Depends(get_current_user)):
    require_patient_access(user, patient_id)
    with get_conn() as conn:
        result = checklist_for(conn, patient_id, load_stay(conn, patient_id, stay_id))
        paths = {d["id"]: d["file_path"] for d in patient_documents(conn, patient_id)}

    files_by_doc = {}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as pack:
        for item_doc, doc, name in pack_filenames(result["items"]):
            pack.writestr(name, read_file(paths[doc["id"]]))
            files_by_doc.setdefault(item_doc, []).append(name)
        pack.writestr("checklist.txt", checklist_text(result, files_by_doc))

    log_action(user, "download_claim_pack", patient_id,
               json.dumps({"stay": stay_id, "files": sum(len(v) for v in files_by_doc.values())}))
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="claim_pack_stay_{stay_id}.zip"'},
    )
