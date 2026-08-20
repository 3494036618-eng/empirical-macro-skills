"""Semantic completeness checks for a primary research estimand."""

from __future__ import annotations


def _estimand(plan: dict[str, object]) -> dict[str, object]:
    value = plan.get("estimand")
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def validate_estimand(plan: dict[str, object]) -> list[str]:
    estimand = _estimand(plan)
    if not estimand:
        return ["estimand_required"]

    issues: list[str] = []
    if not isinstance(estimand.get("outcome_variable_id"), str):
        issues.append("estimand_outcome_required")
    if not isinstance(estimand.get("target_population"), str):
        issues.append("estimand_target_population_required")
    if estimand.get("status") != "specified":
        issues.append("estimand_not_specified")

    family = plan.get("research_family")
    if family == "dynamic_shock_response":
        if not isinstance(estimand.get("treatment_or_shock_variable_id"), str):
            issues.append("dynamic_response_shock_required")
        horizons = estimand.get("horizons")
        if not isinstance(horizons, list) or not horizons:
            issues.append("dynamic_response_horizon_required")
    elif family == "causal_policy_evaluation":
        if not isinstance(estimand.get("treatment_or_shock_variable_id"), str):
            issues.append("causal_treatment_required")
        if not isinstance(estimand.get("comparison"), str):
            issues.append("causal_comparison_required")
    elif family == "forecasting_nowcasting":
        horizons = estimand.get("horizons")
        if not isinstance(horizons, list) or not horizons:
            issues.append("forecast_horizon_required")
    return sorted(issues)
