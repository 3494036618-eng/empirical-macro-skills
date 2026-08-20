"""Explicit research-family classification from structured request fields."""

from __future__ import annotations

CLAIM_TO_DEFAULT_FAMILY = {
    "descriptive": "descriptive_measurement",
    "associational": "panel_association",
    "predictive": "forecasting_nowcasting",
    "structural": "structural_modeling",
}


def _variable_roles(request: dict[str, object]) -> set[str]:
    variables = request.get("variables")
    if not isinstance(variables, list):
        return set()
    return {
        role
        for variable in variables
        if isinstance(variable, dict)
        and isinstance((role := variable.get("role")), str)
    }


def classify_research_family(request: dict[str, object]) -> str:
    claim = request.get("intended_claim")
    if isinstance(claim, str) and claim != "causal":
        return CLAIM_TO_DEFAULT_FAMILY.get(claim, "undetermined")
    if claim != "causal":
        return "undetermined"

    roles = _variable_roles(request)
    intervention = request.get("intervention_or_shock")
    timing_known = (
        isinstance(intervention, dict) and intervention.get("timing_known") is True
    )
    if "shock" in roles and timing_known:
        return "dynamic_shock_response"
    comparison = request.get("comparison")
    if "treatment" in roles and timing_known and isinstance(comparison, str):
        return "causal_policy_evaluation"
    return "undetermined"
