from __future__ import annotations

import pytest

from research_design.estimand_validator import validate_estimand
from research_design.taxonomy import classify_research_family


@pytest.mark.parametrize(
    ("claim", "family"),
    [
        ("descriptive", "descriptive_measurement"),
        ("associational", "panel_association"),
        ("predictive", "forecasting_nowcasting"),
        ("structural", "structural_modeling"),
    ],
)
def test_noncausal_claims_have_explicit_default_family(
    claim: str,
    family: str,
) -> None:
    assert classify_research_family({"intended_claim": claim}) == family


def test_causal_shock_routes_to_dynamic_response_candidate() -> None:
    request: dict[str, object] = {
        "intended_claim": "causal",
        "variables": [{"variable_id": "shock", "role": "shock"}],
        "intervention_or_shock": {"timing_known": True},
    }

    assert classify_research_family(request) == "dynamic_shock_response"


def test_causal_treatment_without_comparison_remains_undetermined() -> None:
    request: dict[str, object] = {
        "intended_claim": "causal",
        "variables": [{"variable_id": "policy", "role": "treatment"}],
        "intervention_or_shock": {"timing_known": True},
    }

    assert classify_research_family(request) == "undetermined"


def test_unknown_claim_remains_undetermined() -> None:
    assert classify_research_family({"intended_claim": "unsupported"}) == "undetermined"


def test_dynamic_response_requires_horizon(
    dynamic_plan: dict[str, object],
) -> None:
    estimand = dynamic_plan["estimand"]
    assert isinstance(estimand, dict)
    estimand["horizons"] = []

    assert validate_estimand(dynamic_plan) == [
        "dynamic_response_horizon_required"
    ]


def test_dynamic_response_requires_identified_shock_variable(
    dynamic_plan: dict[str, object],
) -> None:
    estimand = dynamic_plan["estimand"]
    assert isinstance(estimand, dict)
    estimand["treatment_or_shock_variable_id"] = None

    assert validate_estimand(dynamic_plan) == [
        "dynamic_response_shock_required"
    ]


def test_missing_estimand_is_rejected() -> None:
    assert validate_estimand({"research_family": "panel_association"}) == [
        "estimand_required"
    ]


def test_incomplete_causal_estimand_reports_all_missing_components() -> None:
    plan: dict[str, object] = {
        "research_family": "causal_policy_evaluation",
        "estimand": {
            "type": "att",
            "outcome_variable_id": None,
            "treatment_or_shock_variable_id": None,
            "target_population": None,
            "comparison": None,
            "horizons": [],
            "status": "partial",
        },
    }

    assert validate_estimand(plan) == [
        "causal_comparison_required",
        "causal_treatment_required",
        "estimand_not_specified",
        "estimand_outcome_required",
        "estimand_target_population_required",
    ]


def test_forecast_estimand_requires_horizon() -> None:
    plan: dict[str, object] = {
        "research_family": "forecasting_nowcasting",
        "estimand": {
            "type": "forecast_target",
            "outcome_variable_id": "gdp_growth",
            "treatment_or_shock_variable_id": None,
            "target_population": "季度GDP",
            "comparison": "真实值",
            "horizons": [],
            "status": "specified",
        },
    }

    assert validate_estimand(plan) == ["forecast_horizon_required"]
