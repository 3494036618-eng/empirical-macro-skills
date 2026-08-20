from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from empirical_macro.models import (
    ArtifactRef,
    RouteAction,
    WorkflowStage,
    WorkflowState,
    WorkflowStatus,
)

ALLOWED_TRANSITIONS: dict[WorkflowStage, frozenset[WorkflowStage]] = {
    "idea_received": frozenset({"design_ready", "blocked", "failed"}),
    "design_ready": frozenset({"data_ready", "blocked", "failed"}),
    "data_ready": frozenset({"estimation_ready", "blocked", "failed"}),
    "estimation_ready": frozenset({"audit_ready", "blocked", "failed"}),
    "audit_ready": frozenset({"synthesis_ready", "blocked", "failed"}),
    "synthesis_ready": frozenset({"completed", "blocked", "failed"}),
    "blocked": frozenset(),
    "failed": frozenset(),
    "completed": frozenset(),
}
SUCCESS_STAGES = frozenset(
    {
        "design_ready",
        "data_ready",
        "estimation_ready",
        "audit_ready",
        "synthesis_ready",
        "completed",
    }
)
NEXT_ACTIONS: dict[WorkflowStage, RouteAction] = {
    "idea_received": "route_research_design",
    "design_ready": "route_macro_data",
    "data_ready": "route_time_series_dynamics",
    "estimation_ready": "route_robustness_audit",
    "audit_ready": "route_research_synthesis",
    "synthesis_ready": "route_research_synthesis",
    "completed": "completed",
    "blocked": "stopped",
    "failed": "stopped",
}
STAGE_STATUS: dict[WorkflowStage, WorkflowStatus] = {
    "idea_received": "active",
    "design_ready": "active",
    "data_ready": "active",
    "estimation_ready": "active",
    "audit_ready": "active",
    "synthesis_ready": "active",
    "completed": "completed",
    "blocked": "blocked",
    "failed": "failed",
}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def transition_state(
    state: WorkflowState,
    *,
    target_stage: WorkflowStage,
    artifact_refs: tuple[ArtifactRef, ...],
    issue_codes: tuple[str, ...] = (),
) -> WorkflowState:
    if target_stage not in ALLOWED_TRANSITIONS[state.current_stage]:
        raise ValueError(
            f"illegal workflow transition: {state.current_stage} -> {target_stage}"
        )
    if target_stage in SUCCESS_STAGES and not artifact_refs:
        raise ValueError(f"artifact refs are required for stage: {target_stage}")
    combined_issues = tuple(dict.fromkeys((*state.issue_codes, *issue_codes)))
    active = STAGE_STATUS[target_stage] == "active"
    return replace(
        state,
        updated_at=_timestamp(),
        current_stage=target_stage,
        route_action=NEXT_ACTIONS[target_stage],
        artifact_refs=(*state.artifact_refs, *artifact_refs),
        issue_codes=combined_issues,
        checkpoint_id=None,
        resume_eligible=active,
        status=STAGE_STATUS[target_stage],
    )
