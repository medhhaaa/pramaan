"""In-page search for the Medications and Records pages. Plain code + a local embedding
model; no LLM, never generates text. (Ashil)

index_patient(patient_id)          rebuild the patient's rows in search_items. Called by
                                   recompute_patient, so it runs whenever records change.
search(patient_id, query, page)    -> [{"item_id", "score", "reason", "matched_terms",
                                        "source", "via"}], best first, at most 50

Items:   page "medications" = one medication fact (as on the Medications page: documented,
         not from a held-back document); page "records" = one document (not held back).
Reasons and scores (the strongest one wins):
  "mentioned"   1.0   the item's own source text names the query, a synonym of it
                      (data/synonyms.json) or, for medicines, a brand/generic name of it
                      (the table in backend/routes/check_medicine.py). "source" = the line.
  "same_visit"  0.7   the item shares a document, a day or a hospital stay with an item
                      (on either page) that was "mentioned". "via" = that item.
  "similar"     cos x 0.6   embedding cosine >= 0.55, only when the model is installed.
The query decides what is shown; the records are never changed.

Embeddings: sentence-transformers (pip install -r requirements-search.txt). Model from
SEARCH_MODEL (default all-MiniLM-L6-v2), runs on this computer. SEARCH_EMBEDDINGS=off turns
the "similar" tier off. Without the package everything else works the same.
"""
import hashlib
import json
import os
import re

import numpy as np

from backend.db import get_conn
from backend.routes.check_medicine import DRUGS, lookup
from backend.storage import decrypt_text, encrypt_text, temp_copy
from pipeline.read_pdf import read_pdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYNONYMS_PATH = os.path.join(ROOT, "data", "synonyms.json")
PAGES = ("medications", "records")
MENTIONED, SAME_VISIT, SIMILAR = "mentioned", "same_visit", "similar"
SAME_VISIT_SCORE = 0.7
# all-MiniLM-L6-v2 on p7: related pairs score 0.33-0.47 and unrelated 0.14-0.22, but at 0.40
# "antibiotic" already matches Paracetamol. 0.55 never shows a wrong "similar" (it rarely fires
# with this small model); a medical embedding model would let it go lower. .env: SEARCH_SIMILAR_MIN
SIMILAR_MIN_COSINE = float(os.getenv("SEARCH_SIMILAR_MIN", "0.55"))
SIMILAR_WEIGHT = 0.6
MAX_RESULTS = 50
MAX_EMBED_LINES = 40  # a document's first lines are enough for its meaning (the model truncates anyway)
# doctors' degrees, registration numbers, phone lines, the synthetic-data footer
LETTERHEAD = re.compile(r"\b(?:MBBS|MD|DM|MS|DNB|FRCS)\b|\bReg\. No|\bPh:|SYNTHETIC TEST DOCUMENT")

_model = None
_model_failed = False


# ---------------------------------------------------------------------------
# words, synonyms, brand <-> generic
# ---------------------------------------------------------------------------

def normalize(text):
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _load_synonyms():
    with open(SYNONYMS_PATH, encoding="utf-8") as f:
        groups = json.load(f)
    return {name: [normalize(t) for t in terms] for name, terms in groups.items() if not name.startswith("_")}


SYNONYMS = _load_synonyms()


def _term_pattern(term):
    """Whole words only, so 'mi' never matches inside 'Metformin'."""
    return re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", re.IGNORECASE)


def _drug_family(text):
    """All names (brands + generic + its parts) for the medicines named in text."""
    generic, _ = lookup(text)
    if not generic:
        return set()
    parts = {p.strip() for p in generic.split("+")}
    names = {generic} | parts
    for name, (g, _cls) in DRUGS.items():
        g_parts = {p.strip() for p in g.split("+")}
        if g == generic or g_parts & parts:
            names.add(name)
    return {normalize(n) for n in names}


def expand_query(query):
    """The query plus its synonyms and, for a medicine, its brand / generic names. Ordered
    best first (the query itself, then each condition's main name, then the other terms):
    the first one found in an item picks the line shown as its source."""
    q = normalize(query)
    terms = [q]
    for name, group in SYNONYMS.items():
        if any(q == t or _term_pattern(t).search(q) for t in group):
            terms += [name] + group
    terms += sorted(_drug_family(q))
    return list(dict.fromkeys(t for t in terms if len(t) >= 2))


def _synonym_groups(text):
    return sorted(name for name, group in SYNONYMS.items() if any(_term_pattern(t).search(text) for t in group))


# ---------------------------------------------------------------------------
# embeddings (optional, local)
# ---------------------------------------------------------------------------

def _embedder():
    global _model, _model_failed
    if _model is not None or _model_failed or os.getenv("SEARCH_EMBEDDINGS", "on").lower() == "off":
        return _model
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(os.getenv("SEARCH_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    except Exception as e:  # not installed, or the model can't be loaded: search works without it
        print(f"search: embeddings off ({e.__class__.__name__}: {e})")
        _model_failed = True
    return _model


def _embed(texts):
    model = _embedder()
    if model is None or not texts:
        return [None] * len(texts)
    vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    return [v.astype(np.float32) for v in vectors]


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------

def _document_lines(doc):
    tmp = temp_copy(doc["file_path"])
    try:
        return [{"page": l["page"], "line": l["line"], "text": l["text"]} for l in read_pdf(tmp)]
    finally:
        os.remove(tmp)


def _visits(doc, stays):
    keys = [f"doc:{doc['id']}"]
    date = doc["document_date"]
    if date:
        keys.append(f"day:{date}")
        keys += [f"stay:{s['id']}" for s in stays
                 if (not s["admitted_on"] or s["admitted_on"] <= date) and (not s["discharged_on"] or date <= s["discharged_on"])
                 and (s["admitted_on"] or s["discharged_on"])]
    return keys


def _build_items(conn, patient_id):
    docs = [dict(r) for r in conn.execute(
        "SELECT * FROM documents WHERE patient_id = ? AND held_back = 0 ORDER BY document_date, id", (patient_id,))]
    stays = [dict(r) for r in conn.execute("SELECT * FROM hospital_stays WHERE patient_id = ?", (patient_id,))]
    facts = [dict(r) for r in conn.execute(
        """SELECT * FROM facts WHERE patient_id = ? AND type = 'medication' AND status = 'documented'
           ORDER BY fact_id""", (patient_id,))]

    items, lines_by_doc = [], {}
    for doc in docs:
        try:
            lines = _document_lines(doc)
        except Exception as e:  # a file that can't be read is simply not searchable
            print(f"search: {doc['id']} not indexed ({e})")
            continue
        lines_by_doc[doc["id"]] = lines
        # letterheads and signatures are not searched: "MD, DM (Cardiology)" is not diabetes
        lines = [l for l in lines if not LETTERHEAD.search(l["text"])]
        text = "\n".join(l["text"] for l in lines)
        items.append({
            "page": "records", "item_id": doc["id"], "lines": lines,
            "names": [normalize(doc["filename"]), normalize(doc["doc_type"] or "")],
            "synonyms": _synonym_groups(text), "visits": _visits(doc, stays),
            "embed_text": f"{(doc['doc_type'] or '').replace('_', ' ')}. "
                          + " ".join(l["text"] for l in lines[:MAX_EMBED_LINES]),
        })

    docs_by_id = {d["id"]: d for d in docs}
    for f in facts:
        doc = docs_by_id.get(f["document_id"])
        if not doc or doc["id"] not in lines_by_doc:
            continue
        own = [l for l in lines_by_doc[doc["id"]] if l["page"] == f["page"] and l["line"] == f["line"]]
        lines = own or [{"page": f["page"], "line": f["line"], "text": f["quote"]}]
        text = " ".join(l["text"] for l in lines)
        items.append({
            "page": "medications", "item_id": f["fact_id"], "lines": lines,
            "names": sorted({normalize(f["name"])} | _drug_family(f["name"])),
            "synonyms": _synonym_groups(text), "visits": _visits(doc, stays),
            "embed_text": f"{f['name']} {f['dose'] or ''} {f['frequency'] or ''}. {text}",
        })
    return items


def index_patient(patient_id):
    """Rebuild this patient's search rows. Embeddings are reused when the text is unchanged."""
    with get_conn() as conn:
        items = _build_items(conn, patient_id)
        old = {(r["page"], r["item_id"]): (r["text_hash"], r["embedding"]) for r in conn.execute(
            "SELECT page, item_id, text_hash, embedding FROM search_items WHERE patient_id = ?", (patient_id,))}

    for item in items:
        item["hash"] = hashlib.sha256(item["embed_text"].encode()).hexdigest()
        prev = old.get((item["page"], item["item_id"]))
        item["embedding"] = prev[1] if prev and prev[0] == item["hash"] and prev[1] is not None else None
    todo = [i for i in items if i["embedding"] is None]
    for item, vector in zip(todo, _embed([i["embed_text"] for i in todo])):
        item["embedding"] = vector.tobytes() if vector is not None else None

    with get_conn() as conn:
        conn.execute("DELETE FROM search_items WHERE patient_id = ?", (patient_id,))
        conn.executemany(
            """INSERT INTO search_items (patient_id, page, item_id, search_text, names, synonyms, visits,
               text_hash, embedding) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(patient_id, i["page"], i["item_id"], encrypt_text(json.dumps(i["lines"])), json.dumps(i["names"]),
              json.dumps(i["synonyms"]), json.dumps(i["visits"]), i["hash"], i["embedding"]) for i in items],
        )
    return len(items)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

def _direct_match(item, terms):
    """(matched_terms as written in the item, its source line) or None. The source line is
    where the best-ranked term (see expand_query) appears."""
    found, source = [], None
    for term in terms:
        pattern = _term_pattern(term)
        for line in item["lines"]:
            for m in pattern.finditer(line["text"]):
                if m.group(0) not in found:
                    found.append(m.group(0))
                source = source or line
    if not found and item["names"] & set(terms):  # e.g. "Glycomet" -> a Metformin line
        source = item["lines"][0]
    return (found, source) if (found or source) else None


def search(patient_id, query, page):
    if page not in PAGES:
        raise ValueError(f"page must be one of {PAGES}")
    query = (query or "").strip()
    if not query:
        return []
    terms = expand_query(query)

    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM search_items WHERE patient_id = ?", (patient_id,)).fetchall()
    items = [{
        "page": r["page"], "item_id": r["item_id"], "lines": json.loads(decrypt_text(r["search_text"])),
        "names": set(json.loads(r["names"])), "visits": json.loads(r["visits"]), "embedding": r["embedding"],
    } for r in rows]

    results, direct_visits = {}, {}
    for item in items:  # direct matches on BOTH pages: either can make a "same visit"
        hit = _direct_match(item, terms)
        if not hit:
            continue
        for key in item["visits"]:
            direct_visits.setdefault(key, item["item_id"])
        if item["page"] == page:
            found, source = hit
            results[item["item_id"]] = {"item_id": item["item_id"], "score": 1.0, "reason": MENTIONED,
                                        "matched_terms": found, "source": source, "via": None}

    for item in items:
        if item["page"] != page or item["item_id"] in results:
            continue
        via = next((direct_visits[k] for k in item["visits"] if k in direct_visits), None)
        if via:
            results[item["item_id"]] = {"item_id": item["item_id"], "score": SAME_VISIT_SCORE, "reason": SAME_VISIT,
                                        "matched_terms": [], "source": None, "via": via}

    rest = [i for i in items if i["page"] == page and i["item_id"] not in results and i["embedding"]]
    if rest:
        q_vec = _embed([query])[0]
        if q_vec is not None:
            for item in rest:
                cosine = float(np.dot(q_vec, np.frombuffer(item["embedding"], dtype=np.float32)))
                if cosine >= SIMILAR_MIN_COSINE:
                    results[item["item_id"]] = {"item_id": item["item_id"], "score": round(cosine * SIMILAR_WEIGHT, 3),
                                                "reason": SIMILAR, "matched_terms": [], "source": None, "via": None}

    return sorted(results.values(), key=lambda r: (-r["score"], r["item_id"]))[:MAX_RESULTS]
