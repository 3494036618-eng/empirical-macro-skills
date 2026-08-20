"""Deterministic policy rules for high-risk research-design shortcuts."""

from __future__ import annotations

TRUE_IS_ISSUE = {
    "entity_boundary_stitching": "entity_version_alignment_required",
    "coefficient_used_as_causal_proof": "causal_claim_from_association_rejected",
    "universal_method_claim": "universal_method_choice_rejected",
    "parallel_trends_claimed_from_nonsignificance": "parallel_trends_not_proven",
    "final_vintage_used_for_backtest": "future_information_leakage",
    "random_temporal_split": "temporal_split_required",
    "single_fit_metric_only": "forecast_evaluation_insufficient",
}
FALSE_IS_ISSUE = {
    "price_basis_aligned": "price_basis_alignment_required",
    "vintage_comparison_defined": "vintage_definition_required",
    "functional_form_preregistered": "functional_form_preregistration_required",
    "moderator_preregistered": "moderator_preregistration_required",
    "treatment_defined": "treatment_definition_required",
    "comparison_group_defined": "comparison_group_required",
    "anticipation_assessed": "anticipation_assessment_required",
    "spillovers_assessed": "spillover_assessment_required",
    "synthetic_did_conditions_complete": "synthetic_did_conditions_unresolved",
    "news_decomposition_defined": "news_decomposition_required",
}
ENUM_ISSUES = {
    ("convergence_definition", "unresolved"): "convergence_definition_required",
    ("structural_break_evidence", "hypothesis"): "structural_break_test_required",
    ("shock_identification", "unresolved"): "shock_identification_unresolved",
    ("shock_identification", "raw_policy_change"): "shock_identification_unresolved",
    ("state_timing", "unresolved"): "state_timing_required",
    ("multiplier_definition", "unresolved"): "multiplier_definition_required",
    (
        "instrument_selection",
        "significance_seeking",
    ): "significance_driven_instrument_rejected",
    ("instrument_selection", "unresolved"): "instrument_selection_unresolved",
}


def _audit_inputs(request: dict[str, object]) -> dict[str, object]:
    value = request.get("design_audit_inputs")
    return value if isinstance(value, dict) else {}


def _required_family_issues(
    request: dict[str, object],
    family: str | None,
    inputs: dict[str, object],
) -> set[str]:
    if request.get("intended_claim") != "causal":
        return set()
    if family == "dynamic_shock_response":
        return (
            set()
            if inputs.get("shock_identification") == "explicit"
            else {"shock_identification_unresolved"}
        )
    if family != "causal_policy_evaluation":
        return set()
    required = {
        "treatment_defined": "treatment_definition_required",
        "comparison_group_defined": "comparison_group_required",
        "anticipation_assessed": "anticipation_assessment_required",
        "spillovers_assessed": "spillover_assessment_required",
    }
    return {issue for field, issue in required.items() if inputs.get(field) is not True}


def research_policy_issues(
    request: dict[str, object],
    family: str | None = None,
) -> list[str]:
    inputs = _audit_inputs(request)
    issues = {
        issue
        for field, issue in TRUE_IS_ISSUE.items()
        if inputs.get(field) is True
    }
    issues.update(
        issue
        for field, issue in FALSE_IS_ISSUE.items()
        if field in inputs and inputs.get(field) is False
    )
    issues.update(
        issue
        for (field, value), issue in ENUM_ISSUES.items()
        if inputs.get(field) == value
    )
    if (
        inputs.get("lagged_outcome_included") is True
        and inputs.get("dynamic_panel_review") is not True
    ):
        issues.add("direct_lagged_outcome_fe_rejected")
    if (
        inputs.get("staggered_adoption") is True
        and inputs.get("heterogeneity_robust_design") is not True
    ):
        issues.add("plain_twfe_rejected")
    issues.update(_required_family_issues(request, family, inputs))
    return sorted(issues)
