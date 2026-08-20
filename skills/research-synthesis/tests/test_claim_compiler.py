from __future__ import annotations

import copy
from importlib import import_module

from research_synthesis.claim_policy import assert_report_language
from research_synthesis.contracts import validate_document
from research_synthesis.evidence_index import compile_evidence_index
from tests.factories import real_envelopes


def test_claim_compiler_uses_frozen_anchor_horizons() -> None:
    module = import_module("research_synthesis.claim_compiler")
    assert hasattr(module, "compile_claim_ledger")
    envelopes = real_envelopes()
    index = compile_evidence_index(envelopes)

    ledger = module.compile_claim_ledger(envelopes, index)

    validate_document("claim_ledger", ledger)
    result_claims = [
        claim
        for claim in ledger["claims"]
        if claim["claim_type"] == "causal_candidate"
    ]
    assert len(result_claims) == 5
    assert all(
        any(f"h={horizon}" in claim["report_text"] for claim in result_claims)
        for horizon in (0, 4, 8, 12, 17)
    )
    report_text = "\n".join(claim["report_text"] for claim in ledger["claims"])
    assert_report_language(report_text, "causal_candidate")
    evidence_by_id = {
        item["evidence_id"]: item for item in index["evidence"]
    }
    for claim in result_claims:
        locators = {
            evidence_by_id[reference]["locator"]["value"]
            for reference in claim["evidence_refs"]
        }
        assert any(str(locator).endswith("/confidence_lower") for locator in locators)
        assert any(str(locator).endswith("/confidence_upper") for locator in locators)


def test_claims_reference_existing_evidence() -> None:
    module = import_module("research_synthesis.claim_compiler")
    envelopes = real_envelopes()
    index = compile_evidence_index(envelopes)
    ledger = module.compile_claim_ledger(envelopes, index)
    evidence_ids = {item["evidence_id"] for item in index["evidence"]}

    assert all(
        set(claim["evidence_refs"]) <= evidence_ids
        for claim in ledger["claims"]
    )
    assert ledger["effective_claim_eligibility"] == "causal_candidate"


def test_associational_input_compiles_associational_claims() -> None:
    module = import_module("research_synthesis.claim_compiler")
    envelopes = copy.deepcopy(real_envelopes())
    object.__setattr__(
        envelopes["estimator"],
        "claim_eligibility",
        "associational_only",
    )
    object.__setattr__(
        envelopes["robustness_audit"],
        "claim_eligibility",
        "associational_only",
    )
    envelopes["estimator"].statuses["claim_eligibility"] = "associational_only"
    envelopes["research_design"].statuses["analysis_track"] = (
        "conditional_dynamic_association"
    )
    envelopes["research_design"].statuses["primary_design"] = (
        "conditional_projection"
    )
    index = compile_evidence_index(envelopes)

    ledger = module.compile_claim_ledger(envelopes, index)

    result_types = {
        claim["claim_type"]
        for claim in ledger["claims"]
        if claim["claim_type"] in {"associational", "causal_candidate"}
    }
    assert ledger["effective_claim_eligibility"] == "associational_only"
    assert result_types == {"associational"}
    design_text = "\n".join(
        claim["report_text"]
        for claim in ledger["claims"]
        if claim["claim_type"] == "design"
    )
    assert "条件动态关联" in design_text


def test_robustness_claim_matches_sensitive_assessment() -> None:
    module = import_module("research_synthesis.claim_compiler")
    envelopes = copy.deepcopy(real_envelopes())
    envelopes["robustness_audit"].statuses["assessment"] = "sensitive"
    index = compile_evidence_index(envelopes)

    ledger = module.compile_claim_ledger(envelopes, index)
    text = "\n".join(
        claim["report_text"]
        for claim in ledger["claims"]
        if claim["claim_type"] == "robustness"
    )

    assert "结果对至少一项检查敏感" in text
    assert "没有发现超过冻结阈值的敏感性" not in text


def test_robustness_claim_matches_inconclusive_assessment() -> None:
    module = import_module("research_synthesis.claim_compiler")
    envelopes = copy.deepcopy(real_envelopes())
    envelopes["robustness_audit"].statuses["assessment"] = "inconclusive"
    index = compile_evidence_index(envelopes)

    ledger = module.compile_claim_ledger(envelopes, index)
    text = "\n".join(
        claim["report_text"]
        for claim in ledger["claims"]
        if claim["claim_type"] == "robustness"
    )

    assert "不足以形成明确的稳健性判断" in text
    assert "没有发现超过冻结阈值的敏感性" not in text


def test_claims_use_structured_confidence_level_and_data_identity() -> None:
    module = import_module("research_synthesis.claim_compiler")
    envelopes = copy.deepcopy(real_envelopes())
    envelopes["estimator"].statuses["confidence_level"] = 0.9
    rows = envelopes["estimator"].statuses["horizon_results"]
    assert isinstance(rows, list)
    for row in rows:
        row["confidence_level"] = 0.9
    source = envelopes["macro_data"].statuses["source"]
    assert isinstance(source, dict)
    source["source_title"] = "Alternative Official Dataset"
    source["license"] = "CC-BY-4.0"
    index = compile_evidence_index(envelopes)

    ledger = module.compile_claim_ledger(envelopes, index)
    text = "\n".join(claim["report_text"] for claim in ledger["claims"])

    assert "90% pointwise interval" in text
    assert "95% pointwise interval" not in text
    assert "Alternative Official Dataset" in text
    assert "CC-BY-4.0" in text
    assert "JEL Example 5" not in text
