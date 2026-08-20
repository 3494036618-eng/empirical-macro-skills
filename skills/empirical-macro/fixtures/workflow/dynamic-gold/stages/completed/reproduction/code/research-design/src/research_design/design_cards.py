"""Immutable, versioned eligibility cards for candidate research designs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DesignCard:
    code: str
    families: tuple[str, ...]
    required_fields: tuple[str, ...]
    forbidden_shortcuts: tuple[str, ...]
    required_diagnostics: tuple[str, ...]
    allowed_claim: str


DESIGN_CARDS = (
    DesignCard(
        "descriptive_trend",
        ("descriptive_measurement",),
        ("outcome_role",),
        ("causal_language",),
        ("missingness_report",),
        "descriptive_only",
    ),
    DesignCard(
        "event_study_did",
        ("causal_policy_evaluation",),
        ("outcome_role", "treatment_role", "treatment_timing", "comparison_group"),
        ("parallel_trends_assumed", "plain_twfe_default"),
        ("pretrend_diagnostics", "spillover_assessment"),
        "causal_candidate",
    ),
    DesignCard(
        "forecast_backtest",
        ("forecasting_nowcasting",),
        ("forecast_target_role", "forecast_specification"),
        ("random_temporal_split", "latest_data_as_historical"),
        ("baseline_comparison", "out_of_sample_loss"),
        "predictive_only",
    ),
    DesignCard(
        "instrumental_variables",
        ("causal_policy_evaluation",),
        ("outcome_role", "instrument_role", "exposure_role"),
        ("first_stage_proves_exclusion",),
        ("weak_instrument_diagnostics",),
        "causal_candidate",
    ),
    DesignCard(
        "local_projection",
        ("dynamic_shock_response",),
        ("outcome_role", "shock_role", "identified_shock"),
        ("raw_policy_change_as_shock",),
        ("horizon_diagnostics",),
        "causal_candidate",
    ),
    DesignCard(
        "conditional_projection",
        ("dynamic_shock_response",),
        ("outcome_role", "exposure_role"),
        ("causal_language", "exposure_relabelled_as_shock"),
        ("horizon_diagnostics", "confounding_warning"),
        "associational_only",
    ),
    DesignCard(
        "nowcast",
        ("forecasting_nowcasting",),
        ("forecast_target_role", "forecast_specification"),
        ("final_vintage_as_realtime",),
        ("news_and_revision_audit",),
        "predictive_only",
    ),
    DesignCard(
        "panel_fixed_effects",
        ("panel_association",),
        ("outcome_role", "exposure_role"),
        ("lagged_outcome_direct_fe", "causal_language"),
        ("cluster_level_review", "common_shock_review"),
        "associational_only",
    ),
    DesignCard(
        "structural_model",
        ("structural_modeling",),
        ("outcome_role",),
        ("automatic_structural_readiness",),
        ("equilibrium_and_moment_review",),
        "structural_candidate",
    ),
    DesignCard(
        "var_svar",
        ("dynamic_shock_response",),
        ("outcome_role", "shock_role", "identified_shock"),
        ("raw_policy_change_as_shock",),
        ("stability_and_identification_review",),
        "causal_candidate",
    ),
)
