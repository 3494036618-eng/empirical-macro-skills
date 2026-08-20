"""验证 research design、data、estimator 和 robustness 身份绑定。"""

from __future__ import annotations

from research_synthesis.models import EnvelopeMap

REQUIRED_ROLES = {
    "research_design",
    "macro_data",
    "estimator",
    "robustness_audit",
}


def _identity_errors(envelopes: EnvelopeMap) -> list[str]:
    design = envelopes["research_design"]
    data = envelopes["macro_data"]
    estimator = envelopes["estimator"]
    audit = envelopes["robustness_audit"]
    errors: list[str] = []
    checks = (
        (
            estimator.identities.get("research_plan_ref"),
            design.identities.get("plan_id"),
            "research_plan_reference_mismatch",
        ),
        (
            estimator.identities.get("macro_result_ref"),
            data.identities.get("macro_result_id"),
            "macro_result_reference_mismatch",
        ),
        (
            estimator.identities.get("shock_ref"),
            data.identities.get("shock_id"),
            "shock_reference_mismatch",
        ),
        (
            audit.identities.get("baseline_request_ref"),
            estimator.identities.get("request_id"),
            "robustness_baseline_request_mismatch",
        ),
        (
            audit.identities.get("baseline_bundle_ref"),
            estimator.identities.get("run_id"),
            "robustness_baseline_run_mismatch",
        ),
    )
    errors.extend(code for observed, expected, code in checks if observed != expected)
    return errors


def _checksum_errors(envelopes: EnvelopeMap) -> list[str]:
    design = envelopes["research_design"]
    data = envelopes["macro_data"]
    estimator = envelopes["estimator"]
    checks = (
        (
            estimator.identities.get("data_checksum"),
            data.identities.get("data_checksum"),
            "data_checksum_mismatch",
        ),
        (
            estimator.identities.get("macro_handoff_checksum"),
            data.identities.get("macro_document_checksum"),
            "macro_handoff_checksum_mismatch",
        ),
        (
            estimator.identities.get("shock_artifact_checksum"),
            data.identities.get("shock_document_checksum"),
            "shock_checksum_mismatch",
        ),
        (
            estimator.identities.get("research_plan_checksum"),
            design.identities.get("estimator_handoff_checksum"),
            "research_plan_checksum_mismatch",
        ),
    )
    return [code for observed, expected, code in checks if observed != expected]


def _semantic_errors(envelopes: EnvelopeMap) -> list[str]:
    design = envelopes["research_design"]
    data = envelopes["macro_data"]
    estimator = envelopes["estimator"]
    audit = envelopes["robustness_audit"]
    errors: list[str] = []
    if not (
        design.statuses.get("analysis_track")
        == estimator.statuses.get("analysis_track")
    ):
        errors.append("analysis_track_mismatch")
    if len(
        {
            design.claim_eligibility,
            estimator.claim_eligibility,
            audit.claim_eligibility,
        }
    ) != 1:
        errors.append("claim_eligibility_mismatch")
    if data.statuses.get("delivery_eligibility") != "analysis_ready":
        errors.append("macro_data_not_analysis_ready")
    if data.statuses.get("sample_window") != estimator.statuses.get(
        "sample_window"
    ):
        errors.append("sample_window_mismatch")
    estimand = design.statuses.get("estimand")
    if not isinstance(estimand, dict):
        errors.append("estimand_missing")
    else:
        components = (
            (
                estimand.get("outcome_variable_id"),
                estimator.statuses.get("outcome_variable_id"),
            ),
            (
                estimand.get("treatment_or_shock_variable_id"),
                estimator.statuses.get("exposure_variable_id"),
            ),
            (estimand.get("horizons"), estimator.statuses.get("horizons")),
        )
        if any(observed != expected for observed, expected in components):
            errors.append("estimand_fingerprint_mismatch")
    if audit.statuses.get("required_check_count") != audit.statuses.get(
        "completed_required_check_count"
    ):
        errors.append("required_robustness_check_incomplete")
    return errors


def validate_cross_bundle_binding(envelopes: EnvelopeMap) -> list[str]:
    """返回全部跨 bundle 身份、checksum 和语义错误。"""
    missing = REQUIRED_ROLES - set(envelopes)
    if missing:
        return [f"required_role_missing:{role}" for role in sorted(missing)]
    errors = [
        *_identity_errors(envelopes),
        *_checksum_errors(envelopes),
        *_semantic_errors(envelopes),
    ]
    return sorted(set(errors))
