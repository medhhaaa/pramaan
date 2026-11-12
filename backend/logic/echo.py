"""Echo detection: a medicine line copied word-for-word from an older document is a copy,
not new evidence. Sets fact["echo_of"] to the fact_id of the earliest original. (Deeksha, P2)

"4 documents say Atenolol, 3 are copies of the 2019 record. Last real evidence: 2019."

A changed line ("Metformin increased to 1000mg BD") does not match the old line closely,
so it counts as fresh evidence. Pure function: facts in, facts out, no database.
"""
import re

from rapidfuzz import fuzz

from backend.logic.flags import document_order, same_name

COPY_THRESHOLD = 95  # rapidfuzz ratio (0-100): 95+ means "almost word for word"


def numbers_in(text):
    return re.findall(r"\d+(?:\.\d+)?", text or "")


def is_copy(quote, earlier_quote):
    """Almost word for word AND every number the same, so "Atenolol 25mg OD" is a dose
    change, not a copy of "Atenolol 50mg OD" (the text alone is 95% similar)."""
    similar = fuzz.ratio((quote or "").lower(), (earlier_quote or "").lower()) >= COPY_THRESHOLD
    return similar and numbers_in(quote) == numbers_in(earlier_quote)


def mark_echoes(facts):
    """For each medication fact, look at medication facts from EARLIER documents (oldest
    first). The first one with the same name and an almost identical quote is the original."""
    medications = sorted((f for f in facts if f["type"] == "medication"), key=document_order)
    for i, fact in enumerate(medications):
        fact["echo_of"] = None
        for earlier in medications[:i]:
            if (document_order(earlier) < document_order(fact)
                    and earlier["document_id"] != fact["document_id"]
                    and same_name(earlier) == same_name(fact)
                    and is_copy(fact["quote"], earlier["quote"])):
                fact["echo_of"] = earlier["fact_id"]
                break
    return facts
