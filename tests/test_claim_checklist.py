"""build_checklist(): the plain-code Claim Documents logic (pipeline/claim_checklist.py)."""
import json
import os

from pipeline.claim_checklist import build_checklist, load_rules

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = load_rules()
ALWAYS = [r["doc"] for r in RULES if r["when"] == "always"]


def doc(doc_id, doc_type, date="2026-10-07", verified=True, patient="p6", held_back=False):
    return {"id": doc_id, "patient_id": patient, "doc_type": doc_type, "document_date": date,
            "doc_type_quote": doc_type.upper() if verified else None, "held_back": held_back}


def stay(surgery=None, implant_used=None, accident=None, admitted="2026-10-05", discharged="2026-10-09"):
    return {"patient_id": "p6", "admitted_on": admitted, "discharged_on": discharged,
            "surgery": surgery, "implant_used": implant_used, "accident": accident}


def status(result):
    return {i["doc"]: i["status"] for i in result["items"]}


def test_items_follow_the_rules_file_order():
    result = build_checklist(RULES, [], stay())
    assert [i["doc"] for i in result["items"]] == [r["doc"] for r in RULES]
    assert set(result["items"][0]) == {"doc", "label", "when", "status", "document_ids"}


def test_always_items_apply_even_with_no_documents():
    result = build_checklist(RULES, [], stay())
    assert all(status(result)[d] == "not_saved" for d in ALWAYS)
    assert result["summary"] == {"saved_count": 0, "required_count": len(ALWAYS), "unsure_count": 3}


def test_condition_true_false_none():
    s = status(build_checklist(RULES, [], stay(surgery=True, implant_used=False, accident=None)))
    assert s["operation_notes"] == "not_saved"  # True -> applies
    assert s["implant_invoice"] == "not_needed"  # False
    assert s["fir_or_mlc"] == "unsure"  # None: not answered or "I don't know"


def test_saved_vs_not_saved():
    result = build_checklist(RULES, [doc("d1", "final_bill"), doc("d2", "final_bill")], stay())
    item = next(i for i in result["items"] if i["doc"] == "final_bill")
    assert item["status"] == "saved" and item["document_ids"] == ["d1", "d2"]
    assert status(result)["payment_receipt"] == "not_saved"
    assert result["summary"]["saved_count"] == 1


def test_documents_outside_the_stay_are_not_counted():
    docs = [doc("before", "final_bill", "2026-10-04"), doc("after", "final_bill", "2026-10-10"),
            doc("undated", "final_bill", None)]
    assert status(build_checklist(RULES, docs, stay()))["final_bill"] == "not_saved"
    # the first and last day of the stay count
    edges = [doc("in1", "prescription", "2026-10-05"), doc("in2", "pharmacy_bill", "2026-10-09")]
    s = status(build_checklist(RULES, edges, stay()))
    assert s["prescription"] == "saved" and s["pharmacy_bill"] == "saved"


def test_stay_without_dates_counts_every_document():
    docs = [doc("old", "final_bill", "2019-01-01"), doc("undated", "payment_receipt", None)]
    s = status(build_checklist(RULES, docs, stay(admitted=None, discharged=None)))
    assert s["final_bill"] == "saved" and s["payment_receipt"] == "saved"


def test_stay_with_only_an_admission_date():
    docs = [doc("before", "final_bill", "2026-10-01"), doc("later", "payment_receipt", "2026-11-01")]
    s = status(build_checklist(RULES, docs, stay(discharged=None)))
    assert s["final_bill"] == "not_saved" and s["payment_receipt"] == "saved"


def test_unknown_doc_type_never_matches():
    docs = [doc("u1", "unknown"), doc("u2", "other")]
    result = build_checklist(RULES, docs, stay(True, True, True))
    assert result["summary"]["saved_count"] == 0
    assert all(i["document_ids"] == [] for i in result["items"])


def test_unverified_held_back_or_other_patient_documents_are_not_counted():
    docs = [doc("a", "final_bill", verified=False), doc("b", "prescription", held_back=True),
            doc("c", "pharmacy_bill", patient="p1")]
    s = status(build_checklist(RULES, docs, stay()))
    assert s["final_bill"] == s["prescription"] == s["pharmacy_bill"] == "not_saved"


def test_lab_report_counts_as_investigation_report():
    s = status(build_checklist(RULES, [doc("lab", "lab_report")], stay()))
    assert s["investigation_report"] == "saved"


def test_ravi_expected_result_from_the_real_pipeline_output():
    """data/extracted/p6.json is the real pipeline's output on Ravi's 5 synthetic PDFs."""
    with open(os.path.join(ROOT, "data", "extracted", "p6.json"), encoding="utf-8") as f:
        extracted = json.load(f)["documents"]
    docs = [{"id": d["document_id"], "patient_id": "p6", "doc_type": d["doc_type"],
             "doc_type_quote": d["doc_type_quote"], "document_date": d["document_date"], "held_back": False}
            for d in extracted]
    discharge = next(d for d in extracted if d["doc_type"] == "discharge_summary")
    ravi_stay = {"patient_id": "p6", **discharge["stay_dates"],
                 "surgery": True, "implant_used": True, "accident": False}

    result = build_checklist(RULES, docs, ravi_stay)
    s = status(result)
    assert result["summary"]["saved_count"] == 5
    assert result["summary"]["required_count"] == 8
    assert {d for d, st in s.items() if st == "not_saved"} == {"payment_receipt", "implant_invoice", "operation_notes"}
    assert s["fir_or_mlc"] == "not_needed"
