"""Cross-artifact validation for dynamic-analysis handoffs."""

from __future__ import annotations

from typing import cast

from time_series_dynamics.contracts import validate_document


def _macro_issues(
    request: dict[str, object],
    macro_results: list[dict[str, object]],
) -> set[str]:
    issues: set[str] = set()
    expected_refs = set(cast(list[str], request["macro_data_bundle_refs"]))
    observed_refs = {str(item.get("result_id")) for item in macro_results}
    if len(macro_results) != 1 or expected_refs != observed_refs:
        issues.add("macro_bundle_not_analysis_ready")
    sample_window = cast(dict[str, object], request["sample_window"])
    for result in macro_results:
        if (
            result.get("delivery_eligibility") != "analysis_ready"
            or result.get("research_use") != "dynamic_response"
        ):
            issues.add("macro_bundle_not_analysis_ready")
        period = result.get("observation_period")
        if not isinstance(period, dict) or any(
            period.get(field) != sample_window.get(field) for field in ("start", "end")
        ):
            issues.add("sample_window_mismatch")
    return issues


def _shock_issues(
    request: dict[str, object],
    macro_results: list[dict[str, object]],
    shock_artifact: dict[str, object] | None,
) -> set[str]:
    track = request.get("analysis_track")
    if track == "conditional_dynamic_association":
        return {"shock_artifact_forbidden"} if shock_artifact is not None else set()
    if shock_artifact is None:
        return {"shock_artifact_required"}
    validate_document("shock_artifact", shock_artifact)
    if shock_artifact.get("shock_id") != request.get(
        "shock_identification_artifact_ref"
    ):
        return {"shock_artifact_required"}
    checksums = {
        str(item.get("source_checksum"))
        for item in macro_results
        if isinstance(item.get("source_checksum"), str)
    }
    if checksums and str(shock_artifact.get("checksum")) not in checksums:
        return {"shock_checksum_mismatch"}
    return set()


def validate_handoff(
    request: dict[str, object],
    research_plan: dict[str, object],
    macro_results: list[dict[str, object]],
    shock_artifact: dict[str, object] | None,
) -> list[str]:
    validate_document("request", request)
    validate_document("research_plan_handoff", research_plan)
    for result in macro_results:
        validate_document("macro_data_handoff", result)
    issues = _macro_issues(request, macro_results)
    issues.update(_shock_issues(request, macro_results, shock_artifact))
    if research_plan.get("plan_id") != request.get("research_plan_ref"):
        issues.add("research_plan_reference_mismatch")
    if research_plan.get("analysis_track") != request.get("analysis_track"):
        issues.add("analysis_track_mismatch")
    expected_estimand = (
        "impulse_response"
        if request.get("analysis_track") == "identified_shock_irf"
        else "conditional_projection_path"
    )
    if request.get("estimand_type") != expected_estimand:
        issues.add("estimand_type_mismatch")
    return sorted(issues)
