"""Wording rule for Claim Documents: Pramaan never suggests a claim decision or a deadline.
Scans the English UI strings, the rules file, the API's messages and responses, and the
claim pack's checklist page for forbidden words.
"""
import ast
import json
import os
import re

from backend.routes import claims
from pipeline.claim_checklist import RULES_PATH, build_checklist, load_rules

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN = ["complete", "eligible", "approved", "approve", "guaranteed", "guarantee",
             "all documents submitted", "deadline", "last date", "due date"]


def forbidden_in(text):
    low = text.lower()
    return [w for w in FORBIDDEN if re.search(rf"\b{re.escape(w)}", low)]


def english_ui_strings():
    """'claims.*' and 'tab.claims' values from the English block of frontend/src/i18n.jsx."""
    with open(os.path.join(ROOT, "frontend", "src", "i18n.jsx"), encoding="utf-8") as f:
        source = f.read()
    english = source.split("const kn = {")[0]
    pattern = r'"((?:claims\.|tab\.claims)[^"]*)":\s*(["\'])(.*?)\2,'
    return {key: value for key, _q, value in re.findall(pattern, english, flags=re.S)}


def code_strings(module):
    """String literals in a module's code, leaving out docstrings and comments."""
    with open(module.__file__, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body
                  and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)}
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


def test_ui_strings_have_no_forbidden_words():
    strings = english_ui_strings()
    assert len(strings) > 30  # the pattern really found the claim strings
    bad = {k: forbidden_in(v) for k, v in strings.items() if forbidden_in(v)}
    assert bad == {}


def test_rules_file_has_no_forbidden_words():
    with open(RULES_PATH, encoding="utf-8") as f:
        assert forbidden_in(f.read()) == []


def test_api_messages_have_no_forbidden_words():
    bad = [s for s in code_strings(claims) if forbidden_in(s)]
    assert bad == []


def test_checklist_page_and_api_response_have_no_forbidden_words():
    stay = {"id": 1, "patient_id": "p6", "admitted_on": "2026-10-05", "discharged_on": "2026-10-09",
            "surgery": True, "implant_used": None, "accident": False, "created_at": "2026-10-09 10:00:00",
            "my_reminder_date": None}
    result = build_checklist(load_rules(), [], stay)
    for item in result["items"]:
        item["documents"] = []
    response = {"stay": stay, **result, "also_keep_ready": claims.ALSO_KEEP_READY, "note": claims.NOTE}
    page = claims.checklist_text(response, {})
    assert forbidden_in(page) == []
    assert forbidden_in(json.dumps(response)) == []
    assert "commonly" in page and "Your insurer makes the final decision." in page


def test_the_check_itself_catches_forbidden_words():
    assert forbidden_in("Your claim is complete") == ["complete"]
    assert forbidden_in("Submit before the deadline") == ["deadline"]
    assert forbidden_in("Documents commonly needed; saved; not saved yet") == []
