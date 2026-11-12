"""Replace names, phone numbers, Aadhaar/ABHA/UHID, addresses, doctor and
hospital names with tokens BEFORE any AI call. (Ashil)

deidentify(text, known_names) -> (clean_text, mapping)   mapping: token -> original
reidentify(text, mapping) -> text                         run on our server only

How it works: a fixed list of regex rules, applied in order. Every distinct original
string gets its own token ("Sunita Rao" -> [PATIENT_1], "S. Rao" -> [PATIENT_2]), so
reidentify() can put back exactly what was there. Medical content (medicines, doses,
lab values, dates of care) is never touched. When in doubt we redact more, not less.

Try it:  python -m pipeline.deidentify data/patients/p1/d1_prescription_2019.pdf "Sunita Rao"
"""
import re

# Building blocks
TITLE = r"(?:Mr|Mrs|Ms|Smt|Shri|Sri|Kum|Master|Baby)\.?"
# A name: 1-4 capitalised words joined by single spaces ("Sunita Rao", "S. Rao").
# Two or more spaces end the name (that is a new column in the PDF).
NAME = r"[A-Z][A-Za-z.'-]*(?: [A-Z][A-Za-z.'-]*){0,3}"
SEP = r"\s*[:\-]\s*"  # "Patient: ", "Ref. by - "
INSTITUTION_WORD = r"(?:[A-Z][A-Za-z'.-]*|&)"
INSTITUTION_KEYWORD = (
    r"(?i:hospitals?|clinic|diagnostics|laborator(?:y|ies)|labs?|nursing home|polyclinic|"
    r"cent(?:re|er)|medical college|health ?care|institute)"
)


class _Tokens:
    """Hands out [KIND_n] tokens. The same original string always gets the same token."""

    def __init__(self):
        self.mapping = {}       # token -> original
        self._by_original = {}  # original -> token
        self._counts = {}

    def get(self, kind, original):
        if original not in self._by_original:
            n = self._counts.get(kind, 0) + 1
            self._counts[kind] = n
            token = f"[{kind}_{n}]"
            self._by_original[original] = token
            self.mapping[token] = original
        return self._by_original[original]


def _name_variants(full_name):
    """'Sunita Rao' -> ['Sunita Rao', 'S. Rao', 'S Rao', 'Sunita']"""
    parts = full_name.split()
    variants = [full_name]
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        variants += [f"{first[0]}. {last}", f"{first[0]} {last}"]
        if len(first) >= 3:
            variants.append(first)
    return variants


def deidentify(text, known_names=()):
    tokens = _Tokens()

    def replace_all(pattern, kind, flags=re.MULTILINE):
        """Replace every full match of pattern with a token."""
        nonlocal text
        text = re.sub(pattern, lambda m: tokens.get(kind, m.group(0)), text, flags=flags)

    def replace_value(label_pattern, value_pattern, kind, flags=re.MULTILINE | re.IGNORECASE,
                      sep=SEP):
        """Keep the label ("UHID: "), replace only the value after it."""
        nonlocal text
        pattern = rf"({label_pattern})({sep})({value_pattern})"
        text = re.sub(
            pattern,
            lambda m: m.group(1) + m.group(2) + tokens.get(kind, m.group(3)),
            text,
            flags=flags,
        )

    # 1. Contact details and government IDs (fixed formats)
    replace_all(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b", "EMAIL")
    replace_all(r"\b\d{2}-\d{4}-\d{4}-\d{4}\b", "ABHA")             # ABHA number
    replace_all(r"\b[\w.]+@(?:abdm|sbx)\b", "ABHA")                  # ABHA address
    replace_all(r"\b\d{4}[ -]\d{4}[ -]\d{4}\b|\b\d{12}\b", "AADHAAR")

    # 2. Hospital / lab record numbers, doctor registration numbers
    replace_value(
        r"\b(?:UHID|MRN|IP ?No\.?|OP ?No\.?|Lab ID|Sample ID|Patient ID|Bill No\.?|"
        r"Hospital No\.?|Reg(?:istration)?\.? ?No\.?)",
        r"[A-Z0-9][A-Za-z0-9/.-]*",
        "ID",
        sep=r"\s*[:.]?\s*",  # "Reg. No. 48213" has no colon
    )

    # 2b. Labelled numbers, whatever their shape. OCR can turn a 0 into an O
    #     ("98765 4321O"), which the digit patterns below would miss.
    #     A digit (or a letter OCR confuses with one) may be followed by ONE space or hyphen.
    ocr_digit = r"[\dOoIl]"
    replace_value(r"\b(?:Mobile|Mob\.?|Phone|Ph\.?|Tel\.?|Contact(?: no\.?)?|Emergency)",
                  rf"\+?{ocr_digit}(?:[ -]?{ocr_digit}){{6,}}", "PHONE", sep=r"\s*[:.]?\s*")
    replace_value(r"\bAadhaar(?: No\.?)?", rf"{ocr_digit}(?:[ -]?{ocr_digit}){{11,}}", "AADHAAR",
                  sep=r"\s*[:.]?\s*")
    replace_value(r"\bABHA(?: No\.?| Number| ID)?", rf"{ocr_digit}(?:[ -]?{ocr_digit}){{13,}}", "ABHA",
                  sep=r"\s*[:.]?\s*")

    # 3. Phone numbers: mobiles (+91 98765 43210) and landlines (0824 2441122)
    replace_all(r"(?:\+91[ -]?)?\b[6-9]\d{4}[ -]?\d{5}\b", "PHONE")
    replace_all(r"\b0\d{2,4}[ -]?\d{6,8}\b", "PHONE")

    # 4. Date of birth (keeps the label; the AI can still say "a DOB is documented")
    replace_value(r"\b(?:DOB|D\.O\.B\.?|Date of birth)", r"[0-9][0-9A-Za-z/.-]*", "DOB")

    # 5. Addresses: "Address: ..." and any line ending in a PIN code ("Mangaluru - 575003")
    replace_value(r"\b(?:Address|Addr\.?|Residence)", r"[^\n]+", "ADDRESS")
    replace_all(r"^.*(?:[A-Za-z]\s*-\s*|\bPIN(?: ?code)?\s*[:.-]?\s*)\d{6}\b.*$", "ADDRESS")

    # 6. The patient's own name(s), passed in by the caller (longest first)
    variants = sorted({v for n in known_names if n for v in _name_variants(n)}, key=len, reverse=True)
    for variant in variants:
        replace_all(rf"\b{re.escape(variant)}\b", "PATIENT", flags=re.IGNORECASE)

    # 7. Doctors: "Dr. Anand Shetty", "Ref. by: Anand Shetty"
    replace_all(rf"\bDr\b\.?\s?{NAME}", "DOCTOR")
    replace_value(r"\b(?:Ref\.? ?by|Referred by|Consultant|Treating doctor|Doctor)",
                  NAME, "DOCTOR", flags=re.MULTILINE)

    # 8. Other names: "Patient: S. Rao", relatives ("W/o Mr. Ramesh Rao"), "Mrs. Rekha Pai"
    replace_value(r"^\s*(?:Patient(?:'s)?(?: name)?|Pt\.? name|Name)",
                  rf"(?:{TITLE} )?{NAME}", "PATIENT", flags=re.MULTILINE | re.IGNORECASE)
    # (?<!/) so the "C/O" inside "K/C/O Bronchial asthma" (known case of) is left alone
    replace_all(rf"(?<![/\w])[SWDC]/[Oo]\.?\s*(?:{TITLE} )?{NAME}", "PERSON")
    replace_all(rf"\b{TITLE} {NAME}", "PERSON")

    # 9. Hospitals, clinics and labs: capitalised words ending in a keyword
    replace_all(rf"\b(?:{INSTITUTION_WORD} +){{1,5}}{INSTITUTION_KEYWORD}\b", "HOSPITAL")

    # 10. Safety net: anything we already found once is removed everywhere else too
    for token, original in sorted(tokens.mapping.items(), key=lambda kv: -len(kv[1])):
        if len(original) >= 5:
            text = text.replace(original, token)

    return text, tokens.mapping


def reidentify(text, mapping):
    for token, original in mapping.items():
        text = text.replace(token, original)
    return text


if __name__ == "__main__":
    import sys

    from pipeline.read_pdf import read_pdf

    if len(sys.argv) < 2:
        print('Usage: python -m pipeline.deidentify <file.pdf> ["Patient Name" ...]')
        sys.exit(1)
    original = "\n".join(line["text"] for line in read_pdf(sys.argv[1]))
    clean, mapping = deidentify(original, known_names=sys.argv[2:])
    print(clean)
    print("\n--- mapping (stays on our server) ---")
    for token, value in mapping.items():
        print(f"{token:14} {value}")
    print("\nreidentify() restores the original exactly:", reidentify(clean, mapping) == original)
