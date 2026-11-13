"""pipeline/privacy_layer.py: runs before every AI call. No AI is called in these tests."""
import pytest

from pipeline import llm
from pipeline.privacy_layer import (PrivacyBlocked, find_identifiers, is_allowed, preview, protect, restore,
                                    verhoeff_valid)
from tests.privacy_messages import CASES, IDENTITY


@pytest.mark.parametrize("message,gone,kept", CASES, ids=[f"msg{i + 1}" for i in range(len(CASES))])
def test_messy_messages(message, gone, kept):
    result = protect(message, IDENTITY)  # also proves the fail-closed second pass finds nothing
    for secret in gone:
        assert secret not in result.text, f"{secret!r} still in: {result.text}"
    for medical in kept:
        assert medical in result.text, f"{medical!r} was removed: {result.text}"


def test_tokens_are_consistent_and_restorable():
    text = "My son Rohan has fever. Rohan's number is 98450 12345. Sunita Rao is his grandmother."
    result = protect(text, IDENTITY)
    assert result.text.count("[PERSON_1]") == 2 and "[PATIENT]" in result.text
    reply = "Give [PERSON_1] plenty of fluids and call [PHONE_1] if the fever stays."
    assert restore(reply, result.mapping) == "Give Rohan plenty of fluids and call 98450 12345 if the fever stays."


def test_aadhaar_needs_a_valid_checksum():
    assert verhoeff_valid("498765432102")
    assert not verhoeff_valid("498765432103")
    found = {f.kind for f in find_identifiers("Aadhaar 4987 6543 2103")}  # wrong check digit
    assert "AADHAAR" not in found


def test_medicines_and_eponym_diseases_are_never_redacted():
    for word in ["Parkinson's", "Alzheimer's", "Graves", "Dolo 650", "Glycomet GP1", "Amlodipine 5mg OD", "Crohn's"]:
        assert is_allowed(word), word
    text = "Dr. Rao said it is not Parkinson's; continue Telma 40 and Ecosprin 75."
    assert "Parkinson's" in protect(text).text and "Telma 40" in protect(text).text


def test_dates_other_than_birth_date_are_kept():
    result = protect("HbA1c 8.1 % on 16/01/2023. DOB 14/06/1952.", IDENTITY)
    assert "16/01/2023" in result.text and "14/06/1952" not in result.text


def test_fail_closed_blocks_what_is_still_there(monkeypatch):
    # simulate a redaction step that misses a phone number: the second pass must stop the AI call
    from pipeline import privacy_layer

    monkeypatch.setattr(privacy_layer, "redact", lambda text, identity=None, mapping=None:
                        privacy_layer.Redaction(original=text, text=text, mapping={}, findings=[]))
    with pytest.raises(PrivacyBlocked) as err:
        privacy_layer.protect("call 98450 12345", IDENTITY)
    assert any(f.kind == "PHONE" for f in err.value.findings)


def test_preview_reports_each_layer():
    p = preview(CASES[0][0], IDENTITY)
    assert p["blocked"] is False
    assert "1 known identity" in p["by_layer"]


def test_ai_is_never_called_without_the_privacy_layer(monkeypatch):
    called = []
    monkeypatch.setattr(llm, "_call_openai", lambda *a, **k: called.append(a) or "{}")
    monkeypatch.setattr(llm, "_provider", lambda: "openai")
    with pytest.raises(llm.PrivacyRequired):
        llm.call_llm("Patient Sunita Rao, phone 98765 43210")             # no receipt
    receipt = protect("fever since 3 days", IDENTITY)
    with pytest.raises(llm.PrivacyRequired):
        llm.call_llm("something else entirely", receipt)                 # receipt for other text
    with pytest.raises(PrivacyBlocked):
        llm.call_llm(receipt.text + " call 98450 12345", receipt)        # raw phone slipped in
    assert llm.call_llm("Answer: " + receipt.text, receipt) == "{}"       # the proper way works
    assert len(called) == 1
