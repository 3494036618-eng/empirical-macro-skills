from __future__ import annotations

from research_design.design_router import eligible_designs
from research_design.forecasting_gate import forecasting_issues
from research_design.identification_gate import build_identification_audit


def test_policy_rate_level_is_not_an_identified_shock(
    policy_rate_level_request: dict[str, object],
) -> None:
    candidates = eligible_designs(
        policy_rate_level_request,
        "dynamic_shock_response",
    )

    assert candidates
    assert all(item["decision"] == "reject" for item in candidates)
    by_code = {str(item["code"]): item for item in candidates}
    for code in ("local_projection", "var_svar"):
        assert "identified_shock" in by_code[code]["missing_prerequisites"]
    assert "exposure_role" in by_code["conditional_projection"][
        "missing_prerequisites"
    ]


def test_panel_design_candidates_are_sorted_and_prerequisite_driven() -> None:
    request: dict[str, object] = {
        "intended_claim": "associational",
        "variables": [
            {"variable_id": "growth", "role": "outcome"},
            {"variable_id": "trade", "role": "exposure"},
        ],
    }

    candidates = eligible_designs(request, "panel_association")

    assert [item["code"] for item in candidates] == ["panel_fixed_effects"]
    assert candidates[0]["decision"] == "adopt"
    assert candidates[0]["missing_prerequisites"] == []


def test_complete_policy_design_qualifies_did_and_iv_candidates() -> None:
    request: dict[str, object] = {
        "variables": [
            {"variable_id": "growth", "role": "outcome"},
            {"variable_id": "policy", "role": "treatment"},
            {"variable_id": "dose", "role": "exposure"},
            {"variable_id": "instrument", "role": "instrument"},
        ],
        "intervention_or_shock": {"timing_known": True},
        "comparison": "尚未接受政策的地区",
    }

    candidates = eligible_designs(request, "causal_policy_evaluation")

    assert [item["code"] for item in candidates] == [
        "event_study_did",
        "instrumental_variables",
    ]
    assert all(item["decision"] == "adopt" for item in candidates)


def test_complete_forecast_design_qualifies_both_candidates() -> None:
    request: dict[str, object] = {
        "variables": [{"variable_id": "gdp", "role": "forecast_target"}],
        "forecast": {"horizons": [0, 1]},
    }

    candidates = eligible_designs(request, "forecasting_nowcasting")

    assert [item["code"] for item in candidates] == [
        "forecast_backtest",
        "nowcast",
    ]
    assert all(item["decision"] == "adopt" for item in candidates)


def test_structural_design_is_deferred_even_when_prerequisites_exist() -> None:
    request: dict[str, object] = {
        "variables": [{"variable_id": "output", "role": "outcome"}],
    }

    candidates = eligible_designs(request, "structural_modeling")

    assert candidates[0]["code"] == "structural_model"
    assert candidates[0]["decision"] == "defer"


def test_missing_variables_rejects_panel_design() -> None:
    candidates = eligible_designs({}, "panel_association")

    assert candidates[0]["decision"] == "reject"
    assert candidates[0]["missing_prerequisites"] == [
        "outcome_role",
        "exposure_role",
    ]


def test_causal_candidate_always_requires_review(
    causal_request: dict[str, object],
    causal_estimand: dict[str, object],
) -> None:
    audit = build_identification_audit(
        causal_request,
        causal_estimand,
        "event_study_did",
    )

    assert audit["identification_status"] == "candidate_identified"
    assert audit["claim_eligibility"] == "causal_candidate"
    assert audit["review_required"] is True


def test_dynamic_identification_uses_machine_readable_diagnostic_code(
    dynamic_plan: dict[str, object],
) -> None:
    """Break caught: robustness handoff needs a local Chinese-to-English patch."""
    request: dict[str, object] = {
        "request_id": "rd-request-1234567890abcdef",
        "intended_claim": "causal",
        "variables": [
            {"variable_id": "inflation", "role": "outcome"},
            {"variable_id": "shock", "role": "shock"},
        ],
        "intervention_or_shock": {
            "name": "叙事识别货币政策冲击",
            "timing_known": True,
            "assignment_mechanism": "narrative",
        },
    }
    estimand = dynamic_plan["estimand"]
    assert isinstance(estimand, dict)

    audit = build_identification_audit(request, estimand, "local_projection")
    assumptions = audit["assumptions"]
    assert isinstance(assumptions, list)
    assert assumptions[0]["required_diagnostics"] == [
        "independent_identification_review"
    ]


def test_unidentified_policy_rate_level_is_not_eligible(
    policy_rate_level_request: dict[str, object],
    causal_estimand: dict[str, object],
) -> None:
    audit = build_identification_audit(
        policy_rate_level_request,
        causal_estimand,
        "local_projection",
    )

    assert audit["identification_status"] == "not_identified"
    assert audit["claim_eligibility"] == "not_eligible"
    assert audit["review_required"] is True


def test_forecast_without_origin_or_vintage_is_blocked(
    latest_only_forecast_request: dict[str, object],
) -> None:
    assert forecasting_issues(latest_only_forecast_request) == [
        "forecast_origin_required",
        "historical_vintage_required",
    ]


def test_empty_forecast_protocol_reports_every_required_component() -> None:
    assert forecasting_issues({"forecast": {}}) == [
        "forecast_baseline_required",
        "forecast_horizon_required",
        "forecast_loss_required",
        "forecast_origin_required",
        "historical_vintage_required",
        "point_in_time_data_required",
        "temporal_split_required",
    ]


def test_missing_forecast_object_is_rejected() -> None:
    assert forecasting_issues({}) == ["forecast_specification_required"]


def test_structural_candidate_is_assumption_sensitive_and_reviewed() -> None:
    request: dict[str, object] = {
        "request_id": "rd-request-dddddddddddddddd",
        "intended_claim": "structural",
        "variables": [{"variable_id": "output", "role": "outcome"}],
    }
    estimand: dict[str, object] = {
        "type": "structural_parameter",
        "outcome_variable_id": "output",
        "treatment_or_shock_variable_id": None,
        "target_population": "目标经济体",
        "comparison": "政策反事实",
        "horizons": [],
        "status": "specified",
    }

    audit = build_identification_audit(request, estimand, "structural_model")

    assert audit["identification_status"] == "assumption_sensitive"
    assert audit["claim_eligibility"] == "structural_candidate"
    assert audit["review_required"] is True


def test_iv_candidate_uses_instrument_specific_assumption() -> None:
    request: dict[str, object] = {
        "request_id": "rd-request-eeeeeeeeeeeeeeee",
        "intended_claim": "causal",
        "variables": [
            {"variable_id": "growth", "role": "outcome"},
            {"variable_id": "policy", "role": "exposure"},
            {"variable_id": "instrument", "role": "instrument"},
        ],
    }
    estimand: dict[str, object] = {
        "type": "ate",
        "outcome_variable_id": "growth",
        "treatment_or_shock_variable_id": "policy",
        "target_population": "目标经济体",
        "comparison": "工具变量诱导的处理变化",
        "horizons": [],
        "status": "specified",
    }

    audit = build_identification_audit(
        request,
        estimand,
        "instrumental_variables",
    )
    assumptions = audit["assumptions"]
    assert isinstance(assumptions, list)
    assert assumptions[0]["code"] == "instrument_exclusion"
