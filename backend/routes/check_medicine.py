"""POST /patients/{patient_id}/check-medicine -> warn about allergy / same medicine. (Medha)

Body:     {"drug": "Augmentin 625"}
Response: {"drug", "generic", "drug_class", "class_label", "known", "warnings": [...], "note"}
          warning = {"kind": "allergy" | "same_medicine" | "same_class", "text", "source"}

Plain code: a small dictionary of brand and generic names -> (generic, class).
Checks the drug against documented allergies and current medicines in the records only.
It never says whether a drug is safe; it only points to what the records say.
Warning text, class_label and note follow the user's language (English or Kannada);
drug names, doses, dates and quotes stay exactly as written.
"""
import json
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.auth import get_current_user, require_patient_access
from backend.scope import scoped
from backend.db import get_conn
from backend.routes.audit_helper import log_action
from backend.routes.fact_helpers import load_documents, load_facts, medication_summaries, source_info
from backend.routes.language import doc_type_label, user_language

router = APIRouter()

CLASS_LABELS = {
    "penicillin": "penicillin antibiotics",
    "cephalosporin": "cephalosporin antibiotics",
    "macrolide": "macrolide antibiotics",
    "fluoroquinolone": "fluoroquinolone antibiotics",
    "sulfonamide": "sulfonamides (sulfa drugs)",
    "nsaid": "NSAID painkillers",
    "paracetamol": "paracetamol",
    "beta_blocker": "beta blockers",
    "biguanide": "biguanides",
    "sulfonylurea": "sulfonylureas",
    "calcium_channel_blocker": "calcium channel blockers",
    "ace_inhibitor": "ACE inhibitors",
    "arb": "angiotensin receptor blockers",
    "statin": "statins",
    "thyroid_hormone": "thyroid hormone",
    "ppi": "proton pump inhibitors",
    "bronchodilator": "bronchodilators",
    "inhaled_steroid": "inhaled steroids",
    "diuretic": "diuretics",
    "anticoagulant": "anticoagulants",
}

# name (brand or generic, lower case) -> (generic, class)
DRUGS = {
    # penicillins
    "penicillin": ("penicillin", "penicillin"), "amoxicillin": ("amoxicillin", "penicillin"),
    "amoxycillin": ("amoxicillin", "penicillin"), "ampicillin": ("ampicillin", "penicillin"),
    "cloxacillin": ("cloxacillin", "penicillin"), "piperacillin": ("piperacillin", "penicillin"),
    "augmentin": ("amoxicillin + clavulanate", "penicillin"), "moxclav": ("amoxicillin + clavulanate", "penicillin"),
    "clavam": ("amoxicillin + clavulanate", "penicillin"), "mox": ("amoxicillin", "penicillin"),
    "novamox": ("amoxicillin", "penicillin"),
    # other antibiotics
    "cefixime": ("cefixime", "cephalosporin"), "taxim": ("cefixime", "cephalosporin"),
    "cephalexin": ("cephalexin", "cephalosporin"), "ceftriaxone": ("ceftriaxone", "cephalosporin"),
    "azithromycin": ("azithromycin", "macrolide"), "azithral": ("azithromycin", "macrolide"),
    "clarithromycin": ("clarithromycin", "macrolide"),
    "ciprofloxacin": ("ciprofloxacin", "fluoroquinolone"), "ciplox": ("ciprofloxacin", "fluoroquinolone"),
    "levofloxacin": ("levofloxacin", "fluoroquinolone"),
    "sulfamethoxazole": ("sulfamethoxazole", "sulfonamide"), "cotrimoxazole": ("co-trimoxazole", "sulfonamide"),
    "co-trimoxazole": ("co-trimoxazole", "sulfonamide"), "septran": ("co-trimoxazole", "sulfonamide"),
    "bactrim": ("co-trimoxazole", "sulfonamide"), "sulfasalazine": ("sulfasalazine", "sulfonamide"),
    # painkillers
    "ibuprofen": ("ibuprofen", "nsaid"), "brufen": ("ibuprofen", "nsaid"), "combiflam": ("ibuprofen + paracetamol", "nsaid"),
    "diclofenac": ("diclofenac", "nsaid"), "voveran": ("diclofenac", "nsaid"),
    "aspirin": ("aspirin", "nsaid"), "ecosprin": ("aspirin", "nsaid"), "disprin": ("aspirin", "nsaid"),
    "naproxen": ("naproxen", "nsaid"), "aceclofenac": ("aceclofenac", "nsaid"), "zerodol": ("aceclofenac", "nsaid"),
    "paracetamol": ("paracetamol", "paracetamol"), "dolo": ("paracetamol", "paracetamol"),
    "crocin": ("paracetamol", "paracetamol"), "calpol": ("paracetamol", "paracetamol"),
    # diabetes
    "metformin": ("metformin", "biguanide"), "glycomet": ("metformin", "biguanide"), "glucophage": ("metformin", "biguanide"),
    "glimepiride": ("glimepiride", "sulfonylurea"), "amaryl": ("glimepiride", "sulfonylurea"),
    "gliclazide": ("gliclazide", "sulfonylurea"), "glibenclamide": ("glibenclamide", "sulfonylurea"),
    # heart / blood pressure
    "atenolol": ("atenolol", "beta_blocker"), "aten": ("atenolol", "beta_blocker"), "tenormin": ("atenolol", "beta_blocker"),
    "metoprolol": ("metoprolol", "beta_blocker"), "metolar": ("metoprolol", "beta_blocker"),
    "propranolol": ("propranolol", "beta_blocker"), "bisoprolol": ("bisoprolol", "beta_blocker"),
    "amlodipine": ("amlodipine", "calcium_channel_blocker"), "amlong": ("amlodipine", "calcium_channel_blocker"),
    "stamlo": ("amlodipine", "calcium_channel_blocker"), "norvasc": ("amlodipine", "calcium_channel_blocker"),
    "enalapril": ("enalapril", "ace_inhibitor"), "ramipril": ("ramipril", "ace_inhibitor"),
    "cardace": ("ramipril", "ace_inhibitor"), "lisinopril": ("lisinopril", "ace_inhibitor"),
    "telmisartan": ("telmisartan", "arb"), "telma": ("telmisartan", "arb"), "losartan": ("losartan", "arb"),
    "atorvastatin": ("atorvastatin", "statin"), "atorva": ("atorvastatin", "statin"), "lipitor": ("atorvastatin", "statin"),
    "rosuvastatin": ("rosuvastatin", "statin"), "rosuvas": ("rosuvastatin", "statin"),
    "furosemide": ("furosemide", "diuretic"), "lasix": ("furosemide", "diuretic"),
    "hydrochlorothiazide": ("hydrochlorothiazide", "diuretic"),
    "warfarin": ("warfarin", "anticoagulant"), "clopidogrel": ("clopidogrel", "anticoagulant"),
    # thyroid, stomach, asthma
    "levothyroxine": ("levothyroxine", "thyroid_hormone"), "thyronorm": ("levothyroxine", "thyroid_hormone"),
    "eltroxin": ("levothyroxine", "thyroid_hormone"),
    "pantoprazole": ("pantoprazole", "ppi"), "pan": ("pantoprazole", "ppi"), "pantocid": ("pantoprazole", "ppi"),
    "omeprazole": ("omeprazole", "ppi"), "omez": ("omeprazole", "ppi"),
    "salbutamol": ("salbutamol", "bronchodilator"), "asthalin": ("salbutamol", "bronchodilator"),
    "budesonide": ("budesonide", "inhaled_steroid"), "budecort": ("budesonide", "inhaled_steroid"),
}

# words in an allergy name -> drug class ("Sulfa drugs", "NSAIDs", "Penicillin")
ALLERGY_WORDS = {
    "penicillin": "penicillin", "penicillins": "penicillin",
    "sulfa": "sulfonamide", "sulpha": "sulfonamide", "sulfonamide": "sulfonamide", "sulfonamides": "sulfonamide",
    "nsaid": "nsaid", "nsaids": "nsaid",
    "cephalosporin": "cephalosporin", "cephalosporins": "cephalosporin",
    "macrolide": "macrolide", "macrolides": "macrolide",
    "quinolone": "fluoroquinolone", "fluoroquinolone": "fluoroquinolone", "fluoroquinolones": "fluoroquinolone",
}

CLASS_LABELS_KN = {
    "penicillin": "ಪೆನಿಸಿಲಿನ್ ಆಂಟಿಬಯಾಟಿಕ್‌ಗಳು",
    "cephalosporin": "ಸೆಫಲೋಸ್ಪೊರಿನ್ ಆಂಟಿಬಯಾಟಿಕ್‌ಗಳು",
    "macrolide": "ಮ್ಯಾಕ್ರೋಲೈಡ್ ಆಂಟಿಬಯಾಟಿಕ್‌ಗಳು",
    "fluoroquinolone": "ಫ್ಲೂರೋಕ್ವಿನೋಲೋನ್ ಆಂಟಿಬಯಾಟಿಕ್‌ಗಳು",
    "sulfonamide": "ಸಲ್ಫೋನಮೈಡ್‌ಗಳು (ಸಲ್ಫಾ ಔಷಧಗಳು)",
    "nsaid": "NSAID ನೋವು ನಿವಾರಕಗಳು",
    "paracetamol": "ಪ್ಯಾರಸಿಟಮಾಲ್",
    "beta_blocker": "ಬೀಟಾ ಬ್ಲಾಕರ್‌ಗಳು",
    "biguanide": "ಬೈಗ್ವಾನೈಡ್‌ಗಳು",
    "sulfonylurea": "ಸಲ್ಫೋನಿಲ್ಯೂರಿಯಾಗಳು",
    "calcium_channel_blocker": "ಕ್ಯಾಲ್ಸಿಯಂ ಚಾನೆಲ್ ಬ್ಲಾಕರ್‌ಗಳು",
    "ace_inhibitor": "ACE ಇನ್‌ಹಿಬಿಟರ್‌ಗಳು",
    "arb": "ಆಂಜಿಯೋಟೆನ್ಸಿನ್ ರಿಸೆಪ್ಟರ್ ಬ್ಲಾಕರ್‌ಗಳು",
    "statin": "ಸ್ಟ್ಯಾಟಿನ್‌ಗಳು",
    "thyroid_hormone": "ಥೈರಾಯ್ಡ್ ಹಾರ್ಮೋನ್",
    "ppi": "ಪ್ರೋಟಾನ್ ಪಂಪ್ ಇನ್‌ಹಿಬಿಟರ್‌ಗಳು",
}

NOTE = "Checked against these records only. This is not prescribing advice."
NOTE_KN = "ಈ ದಾಖಲೆಗಳೊಂದಿಗೆ ಮಾತ್ರ ಪರಿಶೀಲಿಸಲಾಗಿದೆ. ಇದು ಔಷಧ ಬರೆಯುವ ಸಲಹೆಯಲ್ಲ."


def class_label(drug_class, lang):
    if not drug_class:
        return None
    if lang == "kn" and drug_class in CLASS_LABELS_KN:
        return CLASS_LABELS_KN[drug_class]
    return CLASS_LABELS.get(drug_class, drug_class)


def words(text):
    return re.findall(r"[a-z][a-z\-]+", (text or "").lower())


def lookup(name):
    """'Tab. Augmentin 625mg' -> ('amoxicillin + clavulanate', 'penicillin'), or (None, None)."""
    for word in words(name):
        if word in DRUGS:
            return DRUGS[word]
    return None, None


def allergy_class(allergy_name):
    """Drug class (and generic, if it names one drug) of an allergy like 'Penicillin' or 'Sulfa drugs'."""
    for word in words(allergy_name):
        if word in ALLERGY_WORDS:
            return None, ALLERGY_WORDS[word]
        if word in DRUGS:
            return DRUGS[word]
    return None, None


class CheckBody(BaseModel):
    drug: str = Field(min_length=1, max_length=100)


def medicine_warnings(patient_id, drug, access, lang="en", renewing_item=None):
    """Allergy and duplicate warnings for one medicine, from the records (scoped to what this
    user may see; allergies are always in scope) and from the patient's ACTIVE in-app
    prescriptions. Used by check-medicine, prescribing and refill review (backend/routes/refills.py).

    renewing_item: the prescription item being refilled; its own medicine isn't a duplicate of itself.
    Returns (generic, drug_class, warnings). It never says whether a drug is safe.
    """
    kn = lang == "kn"
    drug = drug.strip()
    generic, drug_class = lookup(drug)
    typed_words = set(words(drug))

    with get_conn() as conn:
        facts = scoped(load_facts(conn, patient_id), access)  # allergies are always in scope
        docs = load_documents(conn, patient_id)
        resolved = conn.execute(
            "SELECT fact_ids, answer FROM questions WHERE patient_id = ? AND status = 'resolved'",
            (patient_id,),
        ).fetchall()
    # fact_id -> how a doctor resolved the question about it (Things to Check / Open Questions)
    resolved_by_fact = {}
    for row in resolved:
        answer = json.loads(row["answer"] or "{}")
        for fact_id in json.loads(row["fact_ids"] or "[]"):
            resolved_by_fact[fact_id] = answer

    warnings = []
    no_allergy_quotes = [f for f in facts if f["type"] == "allergy" and f["status"] == "negated"]

    # 1. documented allergies
    for allergy in (f for f in facts if f["type"] == "allergy" and f["status"] == "documented"):
        a_generic, a_class = allergy_class(allergy["name"])
        by_class = drug_class and a_class == drug_class
        by_drug = generic and a_generic == generic
        by_name = bool(typed_words & set(words(allergy["name"])))  # works for drugs not in the list
        if not (by_class or by_drug or by_name):
            continue
        doc = docs.get(allergy["document_id"], {})
        reaction = f" ({allergy['value']})" if allergy["value"] else ""
        doc_kind = doc_type_label(doc.get("doc_type"), lang) if doc.get("doc_type") else ("ದಾಖಲೆ" if kn else "record")
        doc_date = doc.get("document_date") or allergy["event_date"]
        if kn:
            text = f"{allergy['name']} ಅಲರ್ಜಿ{reaction} ದಾಖಲಾಗಿದೆ ({doc_date} ರ {doc_kind}): \"{allergy['quote']}\"."
        else:
            text = f"{allergy['name']} allergy{reaction} is documented in the {doc_kind} from {doc_date}: \"{allergy['quote']}\"."
        if by_class and not by_drug and not by_name:
            label = class_label(drug_class, lang)
            text = (f"{drug} ಈ ಗುಂಪಿಗೆ ಸೇರಿದೆ: {label}. " if kn else f"{drug} is one of the {label}. ") + text
        resolution = resolved_by_fact.get(allergy["fact_id"])
        if resolution and resolution.get("answer") in ("confirm", "correct"):
            by, at = resolution.get("by", "a doctor"), resolution.get("at", "")[:10]
            text += f" {at} ರಂದು {by} ದೃಢೀಕರಿಸಿದ್ದಾರೆ." if kn else f" Confirmed by {by} on {at}."
        elif "contradiction" in allergy["flags"] and no_allergy_quotes:
            other = no_allergy_quotes[0]
            if kn:
                text += f' ಇನ್ನೊಂದು ದಾಖಲೆಯಲ್ಲಿ "{other["quote"]}" ({other["event_date"]}) ಎಂದಿದೆ; ಈ ಸಂಘರ್ಷ ಇನ್ನೂ ಬಗೆಹರಿದಿಲ್ಲ.'
            else:
                text += f' Another record says "{other["quote"]}" ({other["event_date"]}); this conflict is not resolved.'
        warnings.append({"kind": "allergy", "text": text, "source": source_info(allergy, docs)})

    # 2. current medicines: same drug or same class
    for med in medication_summaries(facts):
        if not med["current"]:
            continue
        m_generic, m_class = lookup(med["name"])
        fresh = med["latest_fresh"]
        dose = " ".join(p for p in [fresh["dose"], fresh["frequency"]] if p)
        if kn:
            when = f"ಕೊನೆಯ ಹೊಸ ದಾಖಲೆ {med['last_fresh_evidence_date'] or 'ತಿಳಿದಿಲ್ಲ'}"
            if med["echo_count"]:
                when += f", ನಂತರದ {med['echo_count']} ಉಲ್ಲೇಖ(ಗಳು) ನಕಲು"
        else:
            when = f"last new record {med['last_fresh_evidence_date'] or 'unknown'}"
            if med["echo_count"]:
                when += f", {med['echo_count']} later mention(s) are copies"
        same_drug = (generic and m_generic == generic) or bool(typed_words & set(words(med["name"])))
        if same_drug:
            text = (f"ದಾಖಲೆಗಳಲ್ಲಿ {med['name']} {dose} ಈಗಾಗಲೇ ಪ್ರಸ್ತುತ ಔಷಧವಾಗಿ ಇದೆ ({when})." if kn
                    else f"The records already list {med['name']} {dose} as a current medicine ({when}).")
            warnings.append({"kind": "same_medicine", "text": text, "source": source_info(fresh, docs)})
        elif drug_class and m_class == drug_class:
            label = class_label(drug_class, lang)
            text = (f"{drug} ಮತ್ತು ಪ್ರಸ್ತುತ ಔಷಧ {med['name']} {dose} ಒಂದೇ ಗುಂಪಿನವು ({label}) ({when})." if kn
                    else f"{drug} is in the same group ({label}) as current medicine {med['name']} {dose} ({when}).")
            warnings.append({"kind": "same_class", "text": text, "source": source_info(fresh, docs)})


    warnings += in_app_duplicates(patient_id, drug, generic, drug_class, typed_words, lang, renewing_item)
    if renewing_item:  # the medicine being renewed is listed in the records too: not a duplicate of itself
        same = set(words(renewing_item["medicine"]))
        warnings = [w for w in warnings if not (w["kind"] == "same_medicine" and same & set(words(w["text"])))]
    return generic, drug_class, warnings


def in_app_duplicates(patient_id, drug, generic, drug_class, typed_words, lang, renewing_item=None):
    """Same medicine or same group among the patient's active in-app prescriptions."""
    from backend.adherence import today_utc

    with get_conn() as conn:
        items = conn.execute(
            """SELECT i.*, COALESCE(u.full_name, u.username) AS doctor_name, p.created_at AS prescribed_at
               FROM prescription_items i JOIN prescriptions p ON p.id = i.prescription_id
               JOIN users u ON u.id = p.doctor_id
               WHERE i.patient_id = ? AND i.status = 'active' AND i.end_date >= ?""",
            (patient_id, today_utc().isoformat()),
        ).fetchall()
    out = []
    for item in items:
        if renewing_item and item["id"] == renewing_item["id"]:
            continue
        i_generic, i_class = lookup(item["medicine"])
        dose = " ".join(p for p in [item["dose"], item["frequency"]] if p)
        source = {"prescription_item_id": item["id"], "doctor": item["doctor_name"], "prescribed_at": item["prescribed_at"]}
        if (generic and i_generic == generic) or typed_words & set(words(item["medicine"])):
            text = (f"{item['medicine']} {dose} ಈಗಾಗಲೇ Pramaan ಪ್ರಿಸ್ಕ್ರಿಪ್ಷನ್‌ನಲ್ಲಿದೆ ({item['doctor_name']}, {item['end_date']} ರವರೆಗೆ)." if lang == "kn"
                    else f"{item['medicine']} {dose} is already on an active Pramaan prescription ({item['doctor_name']}, until {item['end_date']}).")
            out.append({"kind": "same_medicine", "text": text, "source": source})
        elif drug_class and i_class == drug_class:
            label = class_label(drug_class, lang)
            text = (f"{drug} ಮತ್ತು Pramaan ಪ್ರಿಸ್ಕ್ರಿಪ್ಷನ್‌ನ {item['medicine']} {dose} ಒಂದೇ ಗುಂಪಿನವು ({label})." if lang == "kn"
                    else f"{drug} is in the same group ({label}) as {item['medicine']} {dose} on an active Pramaan prescription.")
            out.append({"kind": "same_class", "text": text, "source": source})
    return out


@router.post("/patients/{patient_id}/check-medicine")
def check_medicine_route(patient_id: str, body: CheckBody, user=Depends(get_current_user)):
    access = require_patient_access(user, patient_id)
    lang = user_language(user)
    kn = lang == "kn"
    drug = body.drug.strip()
    generic, drug_class, warnings = medicine_warnings(patient_id, drug, access, lang)

    log_action(user, "check_medicine", patient_id, f"{drug}: {len(warnings)} warning(s)")
    return {
        "drug": drug,
        "generic": generic,
        "drug_class": drug_class,
        "class_label": class_label(drug_class, lang),
        "known": generic is not None,
        "warnings": warnings,
        "note": NOTE_KN if kn else NOTE,
    }
