"""Plain-code checks, no AI. (Deeksha)

add_flags(facts) -> facts with "flags" filled: contradiction, duplicate, unit_mismatch,
ambiguous_date (e.g. 04/05/2023 where day and month are both <= 12).
find_gaps(facts) -> not_documented gap facts for missing basics.
"""


def add_flags(facts):
    raise NotImplementedError


def find_gaps(facts):
    raise NotImplementedError
