from __future__ import annotations

import pytest

from research_design.policy_gate import research_policy_issues


@pytest.mark.parametrize(
    ("audit_inputs", "expected"),
    [
        (
            {"lagged_outcome_included": True, "dynamic_panel_review": False},
            ["direct_lagged_outcome_fe_rejected"],
        ),
        (
            {"staggered_adoption": True, "heterogeneity_robust_design": False},
            ["plain_twfe_rejected"],
        ),
        (
            {"instrument_selection": "significance_seeking"},
            ["significance_driven_instrument_rejected"],
        ),
        (
            {"shock_identification": "raw_policy_change"},
            ["shock_identification_unresolved"],
        ),
        (
            {"final_vintage_used_for_backtest": True},
            ["future_information_leakage"],
        ),
    ],
)
def test_high_risk_policy_shortcuts_are_rejected(
    audit_inputs: dict[str, object],
    expected: list[str],
) -> None:
    request: dict[str, object] = {"design_audit_inputs": audit_inputs}

    assert research_policy_issues(request) == expected


def test_complete_policy_audit_inputs_have_no_issues() -> None:
    request: dict[str, object] = {
        "design_audit_inputs": {
            "convergence_definition": "beta",
            "structural_break_evidence": "formally_tested",
            "price_basis_aligned": True,
            "entity_boundary_stitching": False,
            "vintage_comparison_defined": True,
            "functional_form_preregistered": True,
            "moderator_preregistered": True,
            "lagged_outcome_included": True,
            "dynamic_panel_review": True,
            "coefficient_used_as_causal_proof": False,
            "shock_identification": "explicit",
            "state_timing": "ex_ante",
            "multiplier_definition": "specified",
            "universal_method_claim": False,
            "treatment_defined": True,
            "comparison_group_defined": True,
            "anticipation_assessed": True,
            "spillovers_assessed": True,
            "staggered_adoption": True,
            "heterogeneity_robust_design": True,
            "parallel_trends_claimed_from_nonsignificance": False,
            "instrument_selection": "preregistered",
            "synthetic_did_conditions_complete": True,
            "final_vintage_used_for_backtest": False,
            "random_temporal_split": False,
            "single_fit_metric_only": False,
            "news_decomposition_defined": True,
        }
    }

    assert research_policy_issues(request) == []


def test_dynamic_causal_design_requires_explicit_shock_identification() -> None:
    request: dict[str, object] = {
        "intended_claim": "causal",
        "design_audit_inputs": {},
    }

    assert research_policy_issues(request, "dynamic_shock_response") == [
        "shock_identification_unresolved"
    ]


def test_causal_policy_requires_timing_comparison_anticipation_and_spillovers() -> None:
    request: dict[str, object] = {
        "intended_claim": "causal",
        "design_audit_inputs": {"treatment_defined": True},
    }

    assert research_policy_issues(request, "causal_policy_evaluation") == [
        "anticipation_assessment_required",
        "comparison_group_required",
        "spillover_assessment_required",
    ]
