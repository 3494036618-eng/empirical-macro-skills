from __future__ import annotations

import copy
from importlib import import_module

from research_synthesis.claim_compiler import compile_claim_ledger
from research_synthesis.contracts import validate_document
from research_synthesis.evidence_index import compile_evidence_index
from tests.factories import real_envelopes


def test_limitations_preserve_material_open_threats() -> None:
    module = import_module("research_synthesis.limitations")
    assert hasattr(module, "compile_limitations")
    envelopes = real_envelopes()
    index = compile_evidence_index(envelopes)
    claims = compile_claim_ledger(envelopes, index)

    limitations = module.compile_limitations(envelopes, claims)

    validate_document("limitations", limitations)
    statements = "\n".join(
        item["statement"] for item in limitations["limitations"]
    )
    for code in (
        "shock_exogeneity",
        "simultaneity",
        "structural_break",
        "multiple_testing",
        "post_result_exploratory",
        "pointwise_not_simultaneous",
    ):
        assert code in statements
    assert all(
        item["source_refs"] and item["affected_claim_refs"]
        for item in limitations["limitations"]
    )
    assert "已识别的货币政策冲击" in statements
    assert "The identified monetary shock" not in statements


def test_associational_claims_are_bound_to_limitations() -> None:
    module = import_module("research_synthesis.limitations")
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
    index = compile_evidence_index(envelopes)
    claims = compile_claim_ledger(envelopes, index)

    limitations = module.compile_limitations(envelopes, claims, index)
    associational_ids = {
        claim["claim_id"]
        for claim in claims["claims"]
        if claim["claim_type"] == "associational"
    }
    affected = {
        claim_id
        for item in limitations["limitations"]
        for claim_id in item["affected_claim_refs"]
    }

    assert associational_ids
    assert associational_ids <= affected


def test_pre_result_audit_does_not_create_post_result_limitation() -> None:
    module = import_module("research_synthesis.limitations")
    envelopes = copy.deepcopy(real_envelopes())
    envelopes["robustness_audit"].statuses["plan_timing"] = "pre_result_bound"
    index = compile_evidence_index(envelopes)
    claims = compile_claim_ledger(envelopes, index)

    limitations = module.compile_limitations(envelopes, claims, index)
    statements = "\n".join(
        item["statement"] for item in limitations["limitations"]
    )

    assert "post_result_exploratory" not in statements
