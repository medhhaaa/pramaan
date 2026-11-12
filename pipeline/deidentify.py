"""Replace names, phone numbers, Aadhaar/ABHA/UHID, addresses, doctor and
hospital names with tokens BEFORE any AI call. (Ashil)

deidentify(text, known_names) -> (clean_text, mapping)   mapping: token -> original
reidentify(text, mapping) -> text                         run on our server only
"""


def deidentify(text, known_names=()):
    raise NotImplementedError


def reidentify(text, mapping):
    for token, original in mapping.items():
        text = text.replace(token, original)
    return text
