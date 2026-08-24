from __future__ import annotations

from empirical_macro.contracts import validate_document

NEXT_ACTIONS = {
    "route_research_design": (
        "route_macro_data",
        "macro-data",
    ),
    "route_macro_data": (
        "route_time_series_dynamics",
        "time-series-dynamics",
    ),
    "route_time_series_dynamics": (
        "route_robustness_audit",
        "robustness-audit",
    ),
    "route_robustness_audit": (
        "route_research_synthesis",
        "research-synthesis",
    ),
    "route_research_synthesis": ("completed", None),
}


def _stage_issues(
    action: str,
    stage_result: dict[str, object],
) -> set[str]:
    raw = stage_result.get("issue_codes")
    issues = (
        {str(item) for item in raw if isinstance(item, str)}
        if isinstance(raw, list | tuple)
        else set()
    )
    design = stage_result.get("design_readiness")
    if design in {"blocked", "review_required"}:
        issues.add(f"research_design_{design}")
    if stage_result.get("claim_eligibility") == "not_eligible":
        issues.add("not_eligible")
    readiness = stage_result.get("research_readiness")
    if readiness in {"blocked", "review_required"}:
        issues.add(f"research_readiness_{readiness}")
    delivery = stage_result.get("delivery_eligibility")
    if delivery in {"not_deliverable", "comparison_only"}:
        issues.add(f"macro_data_{delivery}")
    if stage_result.get("bundle_valid") is False:
        issues.add("bundle_invalid")
    if stage_result.get("status") == "failed":
        issues.add(action.removeprefix("route_").replace("-", "_") + "_failed")
    return issues


def _stage_is_complete(
    action: str,
    stage_result: dict[str, object],
) -> bool:
    if action == "route_research_design":
        return stage_result.get("design_readiness") == "ready_for_data"
    if action == "route_macro_data":
        return (
            stage_result.get("status") == "success"
            and stage_result.get("research_readiness") == "ready"
            and stage_result.get("delivery_eligibility") == "analysis_ready"
            and stage_result.get("eligible_for_estimation") is True
            and stage_result.get("bundle_valid") is True
        )
    if action == "route_time_series_dynamics":
        return (
            isinstance(stage_result.get("result_id"), str)
            and isinstance(stage_result.get("output_dir"), str)
        )
    if action == "route_robustness_audit":
        return isinstance(stage_result.get("audit_result_id"), str)
    if action == "route_research_synthesis":
        return isinstance(stage_result.get("output_dir"), str)
    return False


def decide_after_stage(
    route_decision: dict[str, object],
    stage_result: dict[str, object],
) -> dict[str, object]:
    """Return the only legal next action after an atomic Skill result."""
    validate_document("route_decision", route_decision)
    action = str(route_decision["action"])
    if action not in NEXT_ACTIONS:
        raise ValueError("route decision does not target an atomic stage")
    issues = _stage_issues(action, stage_result)
    if not issues and not _stage_is_complete(action, stage_result):
        issues.add("stage_result_invalid")
    next_action, target = NEXT_ACTIONS[action]
    result: dict[str, object] = {
        "schema_version": "0.1.0-beta",
        "action": "stopped" if issues else next_action,
        "target_skill": None if issues else target,
        "issue_codes": sorted(issues),
        "user_message": None,
    }
    validate_document("route_decision", result)
    return result
