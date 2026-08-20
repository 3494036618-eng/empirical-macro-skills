from __future__ import annotations

from dataclasses import replace

import pytest

from time_series_dynamics.claim_policy import (
    assert_summary_language,
    claim_policy,
)
from time_series_dynamics.models import DynamicsRequest, HorizonEstimate
from time_series_dynamics.result_builder import build_result


def _request(track: str) -> DynamicsRequest:
    association = track == "conditional_dynamic_association"
    return DynamicsRequest(
        request_id=(
            "tsd-request-fedcba9876543210"
            if association
            else "tsd-request-0123456789abcdef"
        ),
        research_plan_ref="research-plan-fedcba9876543210",
        macro_data_bundle_refs=("macro-result-0123456789abcdef",),
        shock_identification_artifact_ref=(
            None if association else "shock-artifact-0123456789abcdef"
        ),
        analysis_track=track,
        estimand_type=(
            "conditional_projection_path" if association else "impulse_response"
        ),
        method_profile=(
            "observed_policy_change_projection"
            if association
            else "observed_shock_linear_lp"
        ),
        outcome_variable_id="lcpi",
        exposure_variable_id="dstir" if association else "rr_shock",
        control_variable_ids=("dlrgdp", "dlcpi", "dstir"),
        frequency="Q",
        sample_start="1985Q1",
        sample_end="2007Q4",
        sample_policy="horizon_specific",
        horizons=(0,),
        lags=4,
        hac_maxlags=17,
        confidence_level=0.95,
        claim_eligibility=(
            "associational_only" if association else "causal_candidate"
        ),
        output_unit="log_points_x100",
    )


def _estimate() -> HorizonEstimate:
    return HorizonEstimate(
        horizon=0,
        estimate=-0.2,
        standard_error=0.1,
        confidence_lower=-0.4,
        confidence_upper=0.0,
        nobs=88,
        df_resid=74.0,
    )


def test_claim_policies_keep_result_semantics_separate() -> None:
    causal = claim_policy("identified_shock_irf")
    association = claim_policy("conditional_dynamic_association")

    assert causal.result_label == "impulse_response"
    assert causal.review_required is True
    assert association.result_label == "conditional_projection_path"
    assert association.claim_eligibility == "associational_only"
    assert association.causal_language_allowed is False


def test_unknown_analysis_track_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported analysis track"):
        claim_policy("unknown")


def test_association_summary_requires_disclaimer_and_rejects_causal_language() -> None:
    policy = claim_policy("conditional_dynamic_association")
    valid = (
        f"{policy.required_disclaimer_zh}\n"
        "第4个季度的条件关联系数为负，区间包含零。"
    )
    assert_summary_language(valid, policy)

    with pytest.raises(ValueError, match="required claim disclaimer"):
        assert_summary_language("第4个季度的条件关联系数为负。", policy)
    with pytest.raises(ValueError, match="forbidden causal language"):
        assert_summary_language(
            f"{policy.required_disclaimer_zh}\n加息导致通胀下降。",
            policy,
        )


def test_result_builder_emits_track_specific_contracts() -> None:
    causal = build_result(_request("identified_shock_irf"), (_estimate(),))
    association = build_result(
        _request("conditional_dynamic_association"),
        (replace(_estimate(), estimate=-0.1),),
    )

    assert causal["estimand_type"] == "impulse_response"
    assert causal["review_required"] is True
    assert association["estimand_type"] == "conditional_projection_path"
    assert association["causal_language_allowed"] is False


def test_result_builder_rejects_empty_or_mismatched_results() -> None:
    request = _request("identified_shock_irf")
    with pytest.raises(ValueError, match="at least one horizon"):
        build_result(request, ())
    with pytest.raises(ValueError, match="estimand"):
        build_result(replace(request, estimand_type="conditional_projection_path"), (_estimate(),))
    with pytest.raises(ValueError, match="claim"):
        build_result(replace(request, claim_eligibility="associational_only"), (_estimate(),))
    with pytest.raises(ValueError, match="horizons"):
        build_result(request, (replace(_estimate(), horizon=1),))
