"""No quote, no fact. (Ashil)

verify_facts(facts, lines, dropped=None) -> facts whose quote is really in the document

For each fact we look for its quote in the PDF lines:
  1. exact match (ignoring case and extra spaces) inside one line, or
  2. a fuzzy match (rapidfuzz) of at least 90/100 against one line or two joined lines,
     but only if every number in the quote also appears in that line.
Then the fact's own dose / value / unit must appear in the matched line, so the AI can't
quote the right line and still report a different number.

Facts that pass get page, line (1-based, the first line of the match), quote_verified=True,
and quote set to the document's own text. Facts that fail are dropped; if you pass a list
as `dropped`, they are added to it with a "drop_reason".
"""
import re

from rapidfuzz import fuzz

MATCH_THRESHOLD = 90


def _norm(text):
    """lower case, single spaces"""
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _compact(text):
    """lower case, no spaces at all: '500 mg' and '500mg' compare equal"""
    return re.sub(r"\s+", "", text or "").lower()


def _numbers(text):
    return set(re.findall(r"\d+(?:\.\d+)?", text or ""))


def _candidates(lines):
    """Every single line, then every pair of neighbouring lines on the same page
    (a sentence can wrap onto the next line). Yields (index_of_first_line, text)."""
    for i, line in enumerate(lines):
        yield i, line["text"]
    for i in range(len(lines) - 1):
        if lines[i]["page"] == lines[i + 1]["page"]:
            yield i, lines[i]["text"] + " " + lines[i + 1]["text"]


def find_quote(quote, lines):
    """Returns (index_of_first_line, matched_document_text, score), or None."""
    q = _norm(quote)
    if not q:
        return None

    # 1. exact: the quote is inside one line
    for i, line in enumerate(lines):
        if q in _norm(line["text"]):
            return i, line["text"], 100

    # 2. fuzzy: best line or line pair, never accepting a changed number
    best = None
    quote_numbers = _numbers(q)
    for i, text in _candidates(lines):
        candidate = _norm(text)
        if not quote_numbers <= _numbers(candidate):
            continue
        score = fuzz.ratio(q, candidate)
        if len(q) >= 12:  # partial matching on very short quotes matches almost anything
            score = max(score, fuzz.partial_ratio(q, candidate))
        if score >= MATCH_THRESHOLD and (best is None or score > best[2]):
            best = (i, text, score)
    return best


def _fields_in_evidence(fact, evidence):
    """dose, value and unit must be written in the matched text."""
    source = _compact(evidence)
    for field in ("dose", "value", "unit"):
        if fact.get(field) and _compact(fact[field]) not in source:
            return field
    return None


def verify_facts(facts, lines, dropped=None):
    verified = []
    for fact in facts:
        match = find_quote(fact.get("quote"), lines)
        reason = None
        if match is None:
            reason = "quote not found in document"
        else:
            index, evidence, _score = match
            bad_field = _fields_in_evidence(fact, evidence)
            if bad_field:
                reason = f"{bad_field} {fact[bad_field]!r} is not in the quoted line"

        if reason:
            if dropped is not None:
                dropped.append({**fact, "drop_reason": reason})
            continue

        verified.append({
            **fact,
            "quote": evidence,
            "page": lines[index]["page"],
            "line": lines[index]["line"],
            "quote_verified": True,
        })
    return verified
