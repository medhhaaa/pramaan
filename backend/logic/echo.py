"""Echo detection: a medicine block copied word-for-word from an older document
is a copy, not new evidence. Sets fact["echo_of"]. (Core backend, P2)"""


def mark_echoes(facts):
    raise NotImplementedError
