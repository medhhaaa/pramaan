"""No quote, no fact. (Ashil)

verify_facts(facts, lines) -> facts whose quote fuzzy-matches a line in the document
(rapidfuzz), with page, line and quote_verified=True set. Unmatched facts are dropped.
"""


def verify_facts(facts, lines):
    raise NotImplementedError
