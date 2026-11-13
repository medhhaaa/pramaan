"""Privacy layer: runs before EVERY AI call (extraction and Q&A / chat).

    result = protect(text, identity)      -> Redaction(text, mapping, findings)   or raises PrivacyBlocked
    answer = restore(ai_reply, result.mapping)   put the real values back, on our server only
    preview(text, identity)               -> original vs redacted + what each layer caught (no AI call)

identity = what we know about the patient from our database:
    {"name": "Sunita Rao", "dob": "1952-06-14", "phone": "+91 98765 43210", "address": "..."}

Five layers, in order:
  1. known identity  the patient's own name (fuzzy: spelling slips, initials like "S. Rao"), DOB in any
                     common format, phone (any spacing), address parts             -> [PATIENT], [DOB]...
  2. patterns        Indian mobile/landline, Aadhaar (12 digits + Verhoeff checksum), ABHA number and
                     address, PAN, email, PIN code (with a place or "PIN" before it), UHID/MRN/IP/Reg no.,
                     dates of birth                                             -> [PHONE_1], [AADHAAR_1]...
  3. local NER       Presidio + spaCy (en_core_web_md, runs on this machine): other people's names,
                     places, organisations                                       -> [PERSON_1], [PLACE_1]...
  4. context cues    a word after Mr/Mrs/Dr/Smt/Shri, S/o W/o D/o C/o, "Name:", "Patient:", "my son",
                     "my daughter", Kannada "nanna maga" / "ನನ್ನ ಮಗ"...               -> [PERSON_n]
  5. allow-list      medicine and disease names (data/brand_generic.json, incl. eponyms like Parkinson's)
                     are never redacted by layers 2-4.

Dates other than the date of birth are KEPT: CLAUDE.md requires dates to stay exact (the timeline
is built from them); a visit date alone does not identify a person.

Fail closed: after redacting, layers 1-4 run again on the redacted text. If anything is still found,
protect() raises PrivacyBlocked(findings) and the AI must not be called; the caller shows the
findings so the user can remove them.
"""
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from functools import lru_cache

from rapidfuzz import fuzz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOW_PATH = os.path.join(ROOT, "data", "brand_generic.json")
SPACY_MODEL = os.getenv("PRIVACY_SPACY_MODEL", "en_core_web_md")
TOKEN_RE = re.compile(r"\[[A-Z_]+(?:_\d+)?\]")


@dataclass
class Finding:
    text: str
    start: int
    end: int
    kind: str    # PATIENT, DOB, PHONE, AADHAAR, ABHA, PAN, EMAIL, PIN, ID, ADDRESS, PERSON, PLACE, ORG
    layer: str   # "1 known identity" | "2 pattern" | "3 NER" | "4 context"


@dataclass
class Redaction:
    original: str
    text: str
    mapping: dict = field(default_factory=dict)    # token -> original (stays on our server)
    findings: list = field(default_factory=list)

    def as_dict(self):
        return {"original": self.original, "redacted": self.text,
                "findings": [asdict(f) for f in self.findings], "tokens": self.mapping}


class PrivacyBlocked(Exception):
    """Something identifying is still there after redaction: do not call the AI."""

    def __init__(self, findings, redacted_text):
        self.findings, self.redacted_text = findings, redacted_text
        super().__init__("Personal details are still present: " + ", ".join(f"{f.kind} '{f.text}'" for f in findings))


# ---------- layer 5: allow-list ----------

@lru_cache(maxsize=1)
def _allow():
    with open(ALLOW_PATH, encoding="utf-8") as f:
        data = json.load(f)
    words = set()
    for name, generic in data["medicines"].items():
        for part in [name, *re.split(r"\s*\+\s*", generic or "")]:
            words.add(part.lower().strip())
    words |= {d.lower() for d in data["diseases"]}
    words |= {t.lower() for t in data.get("tests", [])} | {w.lower() for w in data.get("medical_words", [])}
    return words


def _base(word):
    return re.sub(r"['’]s?$", "", word.lower().strip(" .,;:()[]"))


# dose / form / frequency words that appear next to medicine names
MED_WORDS = {"tab", "tabs", "tablet", "cap", "caps", "capsule", "syp", "syr", "syrup", "inj", "injection", "drops",
             "inhaler", "cream", "gel", "od", "bd", "bid", "tds", "tid", "qid", "hs", "sos", "prn", "stat", "ac", "pc",
             "mg", "mcg", "ml", "iu", "g", "sr", "xr", "xl", "er", "cr", "md", "ds", "forte", "plus", "gp", "mf", "d", "m"}


def _is_med_word(w):
    w = w.lower().strip(" .,;:()[]")
    return w in MED_WORDS or bool(re.fullmatch(r"[a-z]{0,3}\d+(?:\.\d+)?[a-z]{0,3}", w))  # 650, 5mg, gp1, 1000mg


def is_allowed(text):
    """True if the text is a medicine or disease name, possibly with its strength / form / frequency."""
    allow = _allow()
    t = text.lower().strip(" .,;:()[]")
    if t in allow or _base(t) in allow:
        return True
    words = [w for w in re.split(r"[\s/,-]+", t) if w]
    if words and all(_is_med_word(w) for w in words) and any(c.isalpha() for c in t):
        return True  # "OD", "BD", "5mg": dose and frequency words on their own
    named = [w for w in words if w in allow or _base(w) in allow]
    return bool(named) and all(w in allow or _base(w) in allow or _is_med_word(w) for w in words)


# ---------- layer 1: known identity ----------

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def _name_variants(name):
    parts = [p for p in re.split(r"[\s.]+", name or "") if p]
    variants = {name}
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        variants |= {f"{first[0]}. {last}", f"{first[0]} {last}", f"{first[0]}.{last}", f"{first} {last[0]}",
                     f"{last} {first}", f"{last}, {first}"}
    return [v for v in variants if v], [p for p in parts if len(p) >= 3]


def _dob_patterns(dob):
    try:
        d = date.fromisoformat(dob)
    except (TypeError, ValueError):
        return []
    day, month, year = d.day, d.month, d.year
    mon = MONTHS[month - 1]
    num = [f"{day:02d}{s}{month:02d}{s}{year}" for s in "-/. "] + [f"{day}{s}{month}{s}{year}" for s in "-/."]
    num += [f"{year}-{month:02d}-{day:02d}", f"{day:02d}-{month:02d}-{str(year)[2:]}", f"{day:02d}/{month:02d}/{str(year)[2:]}"]
    pats = [re.escape(x) for x in num]
    pats.append(rf"{day}(?:st|nd|rd|th)?[\s-]*{mon}[a-z]*[\s,-]*{year}")
    pats.append(rf"{mon}[a-z]*\s+{day}(?:st|nd|rd|th)?,?\s+{year}")
    return pats


def _digits(text):
    return re.sub(r"\D", "", text)


def layer_known_identity(text, identity):
    found = []
    if not identity:
        return found
    variants, parts = _name_variants(identity.get("name"))
    for v in sorted(variants, key=len, reverse=True):  # exact variants first (longest wins)
        for m in re.finditer(rf"(?<!\w){re.escape(v)}(?!\w)", text, re.IGNORECASE):
            found.append(Finding(m.group(), m.start(), m.end(), "PATIENT", "1 known identity"))
    # fuzzy: single words close to a name part ("Suneeta" ~ "Sunita"), skipping medicine/disease words
    for m in re.finditer(r"[A-Za-z]{3,}", text):
        w = m.group()
        if is_allowed(w):
            continue
        for p in parts:
            limit = 100 if len(p) <= 3 else (75 if len(p) >= 5 else 90)
            if w[0].lower() == p[0].lower() and fuzz.ratio(w.lower(), p.lower()) >= limit:
                found.append(Finding(w, m.start(), m.end(), "PATIENT", "1 known identity"))
                break
    for pat in _dob_patterns(identity.get("dob")):
        for m in re.finditer(pat, text, re.IGNORECASE):
            found.append(Finding(m.group(), m.start(), m.end(), "DOB", "1 known identity"))
    phone = _digits(identity.get("phone") or "")[-10:]
    if len(phone) == 10:
        for m in re.finditer(r"(?:\+?\d[\d\s().-]{8,}\d)", text):
            if _digits(m.group()).endswith(phone):
                found.append(Finding(m.group(), m.start(), m.end(), "PHONE", "1 known identity"))
    for piece in re.split(r"[,\n]", identity.get("address") or ""):
        piece = piece.strip()
        if len(piece) >= 6 and not piece.isdigit():
            for m in re.finditer(re.escape(piece), text, re.IGNORECASE):
                found.append(Finding(m.group(), m.start(), m.end(), "ADDRESS", "1 known identity"))
    return found


# ---------- layer 2: patterns ----------

_VERHOEFF_D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
               [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
               [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
               [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_VERHOEFF_P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
               [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
               [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]


def verhoeff_valid(number):
    """Aadhaar's last digit is a Verhoeff checksum: real Aadhaar numbers pass this."""
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


DATE = r"\d{1,2}[-/. ]\d{1,2}[-/. ]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}[\s-]*[A-Za-z]{3,9}[\s,-]*\d{4}"
# (kind, pattern, group): group 1 = only the value after a label ("UHID: <value>")
PATTERNS = [
    ("EMAIL", r"[\w.+-]+@[\w-]+\.[\w.-]+", 0),
    ("ABHA", r"\b[\w.]{3,}@(?:abdm|sbx)\b", 0),                                  # ABHA address
    ("ABHA", r"(?<!\d)\d{2}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}(?!\d)", 0),            # ABHA number, 14 digits
    ("PAN", r"\b[A-Z]{5}\d{4}[A-Z]\b", 0),
    ("ID", r"(?i)\b(?:uhid|mrn|mr no|ip no|op no|reg no|regn no|hosp no|patient id|abha no|card no)[\s:#.-]{1,3}"
           r"([A-Z0-9][A-Z0-9/-]{3,})", 1),
    ("ID", r"\b[A-Z]{2,5}-\d{4,}\b", 0),
    ("DOB", rf"(?i)\b(?:dob|d\.o\.b\.?|date of birth|born on|born)[\s:-]{{1,3}}({DATE})", 1),
    ("PHONE", r"(?<![\d])(?:\+?91[\s.-]*|0)?[6-9](?:[\s.-]?\d){9}(?!\d)", 0),     # mobile, any spacing
    ("PHONE", r"(?<!\d)0\d{2,4}[\s-]\d{6,8}(?!\d)", 0),                           # landline 0824 2441122
    ("PIN", r"(?i)\b(?:pin|pincode|pin code)[\s:-]{1,3}([1-9]\d{2}\s?\d{3})(?!\d)", 1),
    ("PIN", r"[A-Za-z][\s,]{0,2}-\s?([1-9]\d{2}\s?\d{3})(?!\d)", 1),             # "Mangaluru - 575004"
    ("PIN", r"[A-Za-z],\s([1-9]\d{2}\s?\d{3})(?!\d)", 1),                        # "Udupi, 576101"
]


def layer_patterns(text):
    found = []
    for m in re.finditer(r"(?<!\d)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?!\d)", text):  # Aadhaar
        if verhoeff_valid(_digits(m.group())):
            found.append(Finding(m.group(), m.start(), m.end(), "AADHAAR", "2 pattern"))
    for kind, pat, group in PATTERNS:
        for m in re.finditer(pat, text):
            found.append(Finding(m.group(group), m.start(group), m.end(group), kind, "2 pattern"))
    return found


# ---------- layer 3: local NER (Presidio + spaCy) ----------

@lru_cache(maxsize=1)
def _analyzer():
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    engine = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": SPACY_MODEL}]}).create_engine()
    return AnalyzerEngine(nlp_engine=engine, supported_languages=["en"])


NER_KINDS = {"PERSON": "PERSON", "LOCATION": "PLACE", "ORGANIZATION": "ORG", "NRP": None}


EDGE_WORDS = {"my", "our", "nanna", "namma", "ನನ್ನ", "ನಮ್ಮ", "her", "his", "their", "pan", "aadhaar", "abha", "uhid",
              "ph", "phone", "mob", "mobile", "email", "contact", "call", "dr", "mr", "mrs", "ms", "smt", "shri", "sri",
              "ge", "ige", "ki", "ke", "avaru", "pls", "please", "son", "daughter", "husband", "wife", "mother",
              "father", "brother", "sister"} | {w for w in re.split(r"\|", "maga|magalu|ganda|hendathi|hendti|amma|appa|"
              "akka|anna|thamma|tangi|ajji|ajja|ಮಗ|ಮಗಳು|ಗಂಡ|ಹೆಂಡತಿ|ಅಮ್ಮ|ಅಪ್ಪ|ಅಕ್ಕ|ಅಣ್ಣ|ತಮ್ಮ|ತಂಗಿ")}


def _trim(text, start, end):
    """Shrink a span: drop edge words that are kinship words, labels, numbers or single letters."""
    words = [(m.start() + start, m.end() + start) for m in re.finditer(r"\S+", text[start:end])]
    def edge(w):
        bare = text[w[0]:w[1]].strip(".,:;()'").lower()
        return (bare in EDGE_WORDS or bare.isdigit() or len(bare) <= 1 or bool(re.fullmatch(r"[\d\s+-]+", bare))
                or bool(TOKEN_RE.search(text[w[0]:w[1]])))
    while words and edge(words[0]):
        words.pop(0)
    while words and edge(words[-1]):
        words.pop()
    return (words[0][0], words[-1][1]) if words else None


MEDICAL_SUFFIX = re.compile(r"(?i)(?:logy|logist|logists|ics|scopy|graphy|itis|osis|emia|aemia|pathy|ectomy)$")


def _name_like(span):
    """NER spans we trust: one line, letters only (names have no digits or symbols), not a short
    all-capitals abbreviation (WBC, ECG, NABL), not made of medical words."""
    if "\n" in span or re.search(r"[\d+/%()]", span):
        return False
    words = re.findall(r"[^\W\d_][\w'’-]*", span)  # words only: "&" and "," are not words
    if not words or (len(words) == 1 and span.isupper() and len(span) <= 5):
        return False
    allow = _allow()
    return not all(w.lower() in allow or _base(w) in allow or MEDICAL_SUFFIX.search(w) for w in words)


def layer_ner(text):
    found = []
    for r in _analyzer().analyze(text=text, language="en", entities=["PERSON", "LOCATION", "ORGANIZATION"],
                                 score_threshold=0.5):
        kind = NER_KINDS.get(r.entity_type)
        trimmed = _trim(text, r.start, r.end) if kind else None
        if not trimmed:
            continue
        span = text[trimmed[0]:trimmed[1]].split("\n")[0].rstrip(".,")  # never across lines
        if " " not in span and span.islower():  # one lower-case word ("madi", "pls"): too unreliable
            continue
        if not _name_like(span):
            continue
        found.append(Finding(span, trimmed[0], trimmed[0] + len(span), kind, "3 NER"))
    return found


# ---------- layer 4: context cues ----------

STOP = {"is", "was", "has", "had", "the", "a", "an", "and", "or", "to", "of", "for", "with", "said", "told",
        "says", "gave", "asked", "advised", "prescribed", "also", "too", "got", "gets", "takes", "took", "has",
        "ge", "ige", "ki", "ke", "ko", "avaru", "avarige", "please", "sir", "madam", "doctor", "patient"}
TITLES = r"Mr|Mrs|Ms|Miss|Dr|Smt|Shri|Sri|Kum|Kumari|Master|Baby|Prof"
def _longest_first(words):
    return "|".join(sorted(words.split("|"), key=len, reverse=True))


RELATION_EN = _longest_first("son|daughter|husband|wife|mother|father|mom|dad|brother|sister|grandson|granddaughter|"
                             "grandma|grandpa|uncle|aunt|nephew|niece|son-in-law|daughter-in-law")
RELATION_KN = _longest_first("maga|magalu|ganda|hendathi|hendti|amma|appa|akka|anna|thamma|tangi|ajji|ajja|mommaga|"
                             "mommagalu|atte|mava|chikkappa|doddappa")
RELATION_KN_SCRIPT = _longest_first("ಮಗ|ಮಗಳು|ಗಂಡ|ಹೆಂಡತಿ|ಅಮ್ಮ|ಅಪ್ಪ|ಅಕ್ಕ|ಅಣ್ಣ|ತಮ್ಮ|ತಂಗಿ|ಅಜ್ಜಿ|ಅಜ್ಜ")
END = r"(?![\w\u0C80-\u0CFF])"  # the relation word ends here ("ಮಗ" must not match inside "ಮಗಳು")
NAMEWORD = r"[A-Za-zಀ-೿][\wಀ-೿.'-]*"
CONTEXT = [
    rf"\b(?:{TITLES})\.?\s+((?:[A-Z][\w.'-]*\s?){{1,3}})",                       # Mr Ravi Kumar
    rf"(?i)\b(?:mr|mrs|ms|dr|smt|shri|sri)\.?\s+({NAMEWORD})",                     # dr shetty (lower case)
    rf"(?i)\b(?:s/o|d/o|w/o)\.?\s*((?:{NAMEWORD}\s?){{1,3}})",  # S/o Ramesh (not c/o, h/o: "complains of", "history of")
    rf"(?i)\b(?:patient name|name|patient|pt)\s*[:\-]\s*((?:{NAMEWORD}\s?){{1,3}})",
    rf"(?i)\b(?:my|our)\s+(?:{RELATION_EN}){END}\s*(?:is|named|called|,|-)?\s*({NAMEWORD})",
    rf"(?i)\b(?:nanna|namma)\s+(?:{RELATION_KN}){END}\s*(?:,|-)?\s*({NAMEWORD})",
    rf"(?:ನನ್ನ|ನಮ್ಮ)\s*(?:{RELATION_KN_SCRIPT}){END}\s*(?:,|-)?\s*({NAMEWORD})",
]


STREET = (r"Road|Rd|Street|St|Nagar|Layout|Colony|Circle|Cross|Main|Lane|Marg|Bazaar|Market|Halli|Pura|Puram|"
          r"Palya|Peth|Gali|Chowk|Junction|Extension|Block|Sector|Phase|Apartments?|Residency|Enclave")


def layer_context(text):
    found = []
    # a street / locality: capitalised word(s) before Road, Nagar, Layout, Cross... ("Kadri Road")
    for m in re.finditer(rf"\b((?:\d+(?:st|nd|rd|th)?\s+)?(?:[A-Z][a-z]+\s+){{1,3}}(?:{STREET}))\b", text):
        found.append(Finding(m.group(1), m.start(1), m.end(1), "PLACE", "4 context"))
    for pat in CONTEXT:  # (street rule above)
        for m in re.finditer(pat, text):
            words = m.group(1).strip()
            # keep only leading words that look like a name (not "is", not a medicine, not a token)
            kept = []
            for w in words.split():
                bare = w.strip(".,'")
                if bare.lower() in STOP or is_allowed(bare) or TOKEN_RE.fullmatch(w) or bare.isdigit():
                    break
                kept.append(w)
            while kept and len(kept[-1].strip(".,'")) <= 1:  # "Lakshmi Hegde W" (the W of W/o)
                kept.pop()
            if kept:
                span = " ".join(kept).rstrip(".,")
                start = m.start(1) + m.group(1).find(kept[0])
                found.append(Finding(span, start, start + len(span), "PERSON", "4 context"))
    return found


# ---------- putting it together ----------

def find_identifiers(text, identity=None):
    """Layers 1-4, then the allow-list (layer 5). Overlaps: the longer finding wins, identity first."""
    raw = layer_known_identity(text, identity) + layer_patterns(text) + layer_ner(text) + layer_context(text)
    kept = []
    for f in raw:
        if TOKEN_RE.search(f.text):  # already a token: the text was redacted before
            continue
        if f.layer != "1 known identity" and f.kind in ("PERSON", "PLACE", "ORG") and is_allowed(f.text):
            continue  # medicine / disease name, e.g. "Parkinson's" or "Dolo"
        kept.append(f)
    priority = {"1 known identity": 0, "2 pattern": 1, "4 context": 2, "3 NER": 3}
    taken = [(m.start(), m.end()) for m in TOKEN_RE.finditer(text)]  # tokens from an earlier pass
    merged = []
    for f in sorted(kept, key=lambda f: (priority[f.layer], -(f.end - f.start), f.start)):
        pieces = [(f.start, f.end)]
        for a, b in taken:  # cut out the parts another (more exact) finding already covers
            pieces = [seg for s0, e0 in pieces for seg in ((s0, min(e0, a)), (max(s0, b), e0)) if seg[1] > seg[0]]
        for s0, e0 in pieces:
            span = _trim(text, s0, e0) if (s0, e0) != (f.start, f.end) else (s0, e0)
            if not span or not re.search(r"[A-Za-z0-9\u0C80-\u0CFF]", text[span[0]:span[1]]):
                continue
            piece_text = text[span[0]:span[1]]
            if f.layer != "1 known identity" and f.kind in ("PERSON", "PLACE", "ORG") and is_allowed(piece_text):
                continue
            merged.append(Finding(piece_text, span[0], span[1], f.kind, f.layer))
            taken.append(span)
    return sorted(merged, key=lambda f: f.start)


def redact(text, identity=None, mapping=None):
    mapping = dict(mapping or {})
    by_original = {v.lower(): k for k, v in mapping.items()}
    counts = {}
    for k in mapping:
        m = re.match(r"\[([A-Z]+)_(\d+)\]", k)
        if m:
            counts[m.group(1)] = max(counts.get(m.group(1), 0), int(m.group(2)))
    findings = find_identifiers(text, identity)
    out = text
    for f in sorted(findings, key=lambda f: f.start, reverse=True):
        key = f.text.lower()
        token = by_original.get(key)
        if token is None:
            if f.kind == "PATIENT":
                token = "[PATIENT]"
            elif f.kind == "DOB" and identity and f.layer == "1 known identity":
                token = "[PATIENT_DOB]"
            else:
                counts[f.kind] = counts.get(f.kind, 0) + 1
                token = f"[{f.kind}_{counts[f.kind]}]"
            mapping.setdefault(token, f.text)
            by_original[key] = token
        out = out[:f.start] + token + out[f.end:]
    return Redaction(original=text, text=out, mapping=mapping, findings=findings)


def protect(text, identity=None, mapping=None):
    """Redact, then check again (fail closed). Raises PrivacyBlocked if anything is left."""
    result = redact(text, identity, mapping)
    left = find_identifiers(result.text, identity)
    if left:
        raise PrivacyBlocked(left, result.text)
    return result


def restore(text, mapping):
    """Put the real values back into the AI's reply (longest tokens first)."""
    for token in sorted(mapping, key=len, reverse=True):
        text = text.replace(token, mapping[token])
    return text


def preview(text, identity=None):
    """For the chat screen: what would be sent, and whether it would be allowed (no AI call)."""
    result = redact(text, identity)
    left = find_identifiers(result.text, identity)
    by_layer = {}
    for f in result.findings:
        by_layer.setdefault(f.layer, []).append({"text": f.text, "kind": f.kind})
    return {**result.as_dict(), "by_layer": by_layer, "blocked": bool(left),
            "still_found": [asdict(f) for f in left]}


# guard for llm.call_llm: no identifiers that a plain pattern can see, anywhere in a prompt
def quick_scan(prompt):
    return [f for f in layer_patterns(prompt) if not TOKEN_RE.search(f.text)]
