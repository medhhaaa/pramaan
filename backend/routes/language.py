"""Each user's language: English, Kannada or Hindi. (Medha)

PUT /me/language  {"language": "kn"}  -> {"language": "kn"}
    Saved in users.language. The frontend asks once, right after the first login
    (language is null until then), and the header lets the user switch later.
    "hi" is saved for the screens; text the backend writes has no Hindi yet, so it
    falls back to English.

user_language(user) -> "en" or "kn" (Hindi users get "en"), for routes that build text (questions, brief,
check-medicine, ask). Medicine names, doses, values, units, dates and quotes are never
translated: they always stay exactly as written in the document.
"""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.auth import get_current_user
from backend.db import get_conn
from backend.routes.audit_helper import log_action

router = APIRouter()

LANGUAGES = ("en", "kn")  # languages the backend writes text in


def user_language(user):
    with get_conn() as conn:
        row = conn.execute("SELECT language FROM users WHERE id = ?", (user["id"],)).fetchone()
    return row["language"] if row and row["language"] in LANGUAGES else "en"


class LanguageBody(BaseModel):
    language: Literal["en", "kn", "hi"]


@router.put("/me/language")
def set_language(body: LanguageBody, user=Depends(get_current_user)):
    with get_conn() as conn:
        conn.execute("UPDATE users SET language = ? WHERE id = ?", (body.language, user["id"]))
    log_action(user, "set_language", None, body.language)
    return {"language": body.language}


# ---------- Kannada words shared by the routes that build sentences ----------

DOC_TYPE_KN = {
    "prescription": "ಔಷಧ ಚೀಟಿ",
    "lab_report": "ಪ್ರಯೋಗಾಲಯ ವರದಿ",
    "discharge_summary": "ಡಿಸ್ಚಾರ್ಜ್ ಸಾರಾಂಶ",
    "patient_profile": "ರೋಗಿಯೇ ತುಂಬಿದ ಆರೋಗ್ಯ ವಿವರ",
}

FACT_TYPE_KN = {
    "medication": "ಔಷಧ",
    "lab_test": "ಪ್ರಯೋಗಾಲಯ ಪರೀಕ್ಷೆ",
    "allergy": "ಅಲರ್ಜಿ",
    "condition": "ಆರೋಗ್ಯ ಸ್ಥಿತಿ",
    "event": "ಘಟನೆ",
    "demographic": "ವೈಯಕ್ತಿಕ ವಿವರ",
}

# gap names from find_gaps() ("blood_group", "allergy", ...)
GAP_NAME_KN = {
    "blood group": "ರಕ್ತದ ಗುಂಪು",
    "allergy": "ಅಲರ್ಜಿ",
    "allergies": "ಅಲರ್ಜಿಗಳು",
    "sex": "ಲಿಂಗ",
    "dob": "ಜನ್ಮ ದಿನಾಂಕ",
    "date of birth": "ಜನ್ಮ ದಿನಾಂಕ",
}


# ---------- Hindi words for the question templates (backend/routes/questions.py) ----------

DOC_TYPE_HI = {
    "prescription": "पर्चा",
    "lab_report": "लैब रिपोर्ट",
    "discharge_summary": "डिस्चार्ज सारांश",
    "final_bill": "अस्पताल का बिल",
    "pharmacy_bill": "दवा का बिल",
    "patient_profile": "मरीज़ की अपनी भरी स्वास्थ्य प्रोफ़ाइल",
}
GAP_NAME_HI = {
    "blood group": "ब्लड ग्रुप",
    "allergy": "एलर्जी",
    "allergies": "एलर्जी",
    "sex": "लिंग",
    "dob": "जन्म तिथि",
    "date of birth": "जन्म तिथि",
}


def doc_type_label(doc_type, lang):
    if lang == "kn":
        return DOC_TYPE_KN.get(doc_type, "ದಾಖಲೆ")
    if lang == "hi":
        return DOC_TYPE_HI.get(doc_type, "दस्तावेज़")
    if doc_type == "patient_profile":
        return "health profile filled in by the patient"
    return (doc_type or "document").replace("_", " ")


def gap_name(name, lang):
    what = (name or "").replace("_", " ").lower()
    if lang == "kn":
        return GAP_NAME_KN.get(what, what)
    if lang == "hi":
        return GAP_NAME_HI.get(what, what)
    return what


def question_language(user):
    """'en', 'kn' or 'hi': questions have Hindi text too (other routes still use user_language)."""
    with get_conn() as conn:
        row = conn.execute("SELECT language FROM users WHERE id = ?", (user["id"],)).fetchone()
    return row["language"] if row and row["language"] in ("en", "kn", "hi") else "en"
