from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest
from jsonschema import ValidationError
from test_contracts import (
    association_request,
    causal_request,
    valid_shock_artifact,
)

from time_series_dynamics.artifact_validation import validate_handoff

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic"


def _plan(track: str) -> dict[str, object]:
    causal = track == "identified_shock_irf"
    return {
        "schema_version": "0.1.0-draft",
        "plan_id": (
            "research-plan-fedcba9876543210"
            if track == "conditional_dynamic_association"
            else "research-plan-0123456789abcdef"
        ),
        "request_id": ("rd-request-0123456789abcdef" if causal else "rd-request-fedcba9876543210"),
        "research_family": "dynamic_shock_response",
        "intended_claim": "causal" if causal else "associational",
        "analysis_track": track,
        "primary_design": "local_projection" if causal else "conditional_projection",
        "claim_eligibility": ("causal_candidate" if causal else "associational_only"),
        "design_readiness": "review_required" if causal else "ready_for_data",
        "review_required": causal,
    }


def _macro_result() -> dict[str, object]:
    return {
        "schema_version": "0.2.0-beta",
        "result_id": "macro-result-0123456789abcdef",
        "research_use": "dynamic_response",
        "execution_status": "success",
        "research_readiness": "ready",
        "delivery_eligibility": "analysis_ready",
        "eligible_for_estimation": True,
        "review_required": False,
        "frequency": "Q",
        "observation_period": {"start": "1985Q1", "end": "2007Q4"},
        "source_checksum": ("19ca23c02ff86dd1f7c78018e4052eea98de4ecca879f467c3a9d57f55b38d2c"),
        "source": {
            "provider": "research_replication_artifact",
            "dataset": "Jorda-Taylor JEL Example 5",
            "version": "655696c1c576b7537c5a939d2c261f0a111ae663",
            "license": "CC0-1.0",
        },
        "variables": [
            "rr_shock",
            "lcpi",
            "lrgdp",
            "stir",
            "dlcpi",
            "dlrgdp",
            "dstir",
        ],
        "provenance_complete": True,
    }


def test_valid_causal_and_association_handoffs_have_no_issues() -> None:
    causal = causal_request()
    association = association_request()

    assert (
        validate_handoff(
            causal,
            _plan("identified_shock_irf"),
            [_macro_result()],
            valid_shock_artifact(),
        )
        == []
    )
    assert (
        validate_handoff(
            association,
            _plan("conditional_dynamic_association"),
            [_macro_result()],
            None,
        )
        == []
    )


def test_handoff_reports_canonical_cross_artifact_issues() -> None:
    request = causal_request()
    plan = _plan("conditional_dynamic_association")
    macro = _macro_result()
    macro["delivery_eligibility"] = "comparison_only"
    macro["research_readiness"] = "review_required"
    macro["eligible_for_estimation"] = False
    macro["review_required"] = True

    assert validate_handoff(request, plan, [macro], None) == [
        "analysis_track_mismatch",
        "macro_bundle_not_analysis_ready",
        "research_plan_reference_mismatch",
        "shock_artifact_required",
    ]


def test_handoff_detects_shock_checksum_and_forbidden_artifact() -> None:
    causal = causal_request()
    shock = copy.deepcopy(valid_shock_artifact())
    shock["checksum"] = "a" * 64
    association = association_request()

    assert validate_handoff(
        causal,
        _plan("identified_shock_irf"),
        [_macro_result()],
        shock,
    ) == ["shock_checksum_mismatch"]
    assert validate_handoff(
        association,
        _plan("conditional_dynamic_association"),
        [_macro_result()],
        valid_shock_artifact(),
    ) == ["shock_artifact_forbidden"]


def test_handoff_detects_sample_scope_mismatch() -> None:
    request = association_request()
    macro = _macro_result()
    macro["observation_period"] = {"start": "1990Q1", "end": "2007Q4"}

    assert validate_handoff(
        request,
        _plan("conditional_dynamic_association"),
        [macro],
        None,
    ) == ["sample_window_mismatch"]


def test_handoff_rejects_documents_outside_envelope_contracts() -> None:
    request = causal_request()
    plan = _plan("identified_shock_irf")
    macro = _macro_result()
    plan.pop("plan_id")
    macro.pop("source_checksum")

    with pytest.raises(ValidationError):
        validate_handoff(
            request,
            plan,
            [_macro_result()],
            valid_shock_artifact(),
        )
    with pytest.raises(ValidationError):
        validate_handoff(
            request,
            _plan("identified_shock_irf"),
            [macro],
            valid_shock_artifact(),
        )


def test_handoff_reports_research_plan_reference_mismatch() -> None:
    request = causal_request()
    plan = _plan("identified_shock_irf")
    plan["plan_id"] = "research-plan-fedcba9876543210"

    assert validate_handoff(
        request,
        plan,
        [_macro_result()],
        valid_shock_artifact(),
    ) == ["research_plan_reference_mismatch"]


def test_association_requires_generic_macro_evidence_profile() -> None:
    request_document = json.loads(
        (FIXTURES / "canonical-association.request.json").read_text(encoding="utf-8")
    )
    request = cast(dict[str, object], request_document)
    macro = _macro_result()
    macro.update(
        {
            "result_id": "macro-result-abcdef0123456789",
            "observation_period": {
                "start": "2000Q1",
                "end": "2019Q4",
            },
            "evidence_kind": "macro_data_association",
            "data_profile": "canonical_long_table",
            "data_use_scope": "controlled_public_demo",
            "public_payload_policy": "metadata_only",
            "product_authorization_ref": "product-auth-" + "a" * 32,
            "series_bindings": request["series_bindings"],
            "source": {
                "provider": "datapro",
                "dataset": "International Financial Statistics",
                "version": "run-" + "b" * 32,
                "license": "product-auth-" + "a" * 32,
            },
        }
    )
    plan = _plan("conditional_dynamic_association")
    plan["plan_id"] = request["research_plan_ref"]

    assert (
        validate_handoff(
            request,
            plan,
            [macro],
            None,
        )
        == []
    )

    macro["evidence_kind"] = "jel_identified_shock"
    macro["data_profile"] = "precomputed_columns"
    assert validate_handoff(
        request,
        plan,
        [macro],
        None,
    ) == [
        "association_data_profile_mismatch",
        "association_macro_evidence_kind_mismatch",
    ]
