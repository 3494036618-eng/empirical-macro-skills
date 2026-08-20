from __future__ import annotations

from typing import Protocol, cast

from empirical_macro.capability_registry import (
    METHOD_NOT_IMPLEMENTED_MESSAGE,
    resolve_capability,
)
from empirical_macro.models import ResearchIntent, RouteAction, RouteDecision


class WorkflowStateView(Protocol):
    @property
    def current_stage(self) -> str: ...


STATE_ROUTES: dict[str, tuple[RouteAction, str | None]] = {
    "idea_received": ("route_research_design", "research-design"),
    "design_ready": ("route_macro_data", "macro-data"),
    "data_ready": ("route_time_series_dynamics", "time-series-dynamics"),
    "estimation_ready": ("route_robustness_audit", "robustness-audit"),
    "audit_ready": ("route_research_synthesis", "research-synthesis"),
    "synthesis_ready": ("route_research_synthesis", "research-synthesis"),
    "completed": ("completed", None),
    "blocked": ("stopped", None),
    "failed": ("stopped", None),
}
ROUTE_TARGETS: dict[RouteAction, str] = {
    "route_research_design": "research-design",
    "route_macro_data": "macro-data",
    "route_time_series_dynamics": "time-series-dynamics",
    "route_robustness_audit": "robustness-audit",
    "route_research_synthesis": "research-synthesis",
}


def _decision(action: RouteAction, *issues: str) -> RouteDecision:
    return RouteDecision(action, ROUTE_TARGETS.get(action), tuple(issues), None)


def _route_state(state: WorkflowStateView) -> RouteDecision:
    try:
        action, target = STATE_ROUTES[state.current_stage]
    except KeyError as error:
        raise ValueError(f"unknown workflow stage: {state.current_stage}") from error
    issues = (
        (f"workflow_{state.current_stage}",)
        if state.current_stage in {"blocked", "failed"}
        else ()
    )
    return RouteDecision(action, target, issues, None)


def _route_artifacts(intent: ResearchIntent) -> RouteDecision:
    if intent.request_kind == "data_preparation":
        return _decision("route_macro_data")
    if intent.request_kind in {"research_idea", "other"}:
        return _decision("route_research_design")
    if not intent.has_research_plan:
        return _decision("route_research_design")
    if not intent.has_macro_data_bundle:
        return _decision("route_macro_data")
    if not intent.has_estimator_bundle:
        return _decision("route_time_series_dynamics")
    if intent.request_kind == "dynamic_analysis":
        return _decision("completed")
    if not intent.has_robustness_bundle:
        return _decision("route_robustness_audit")
    if intent.request_kind == "final_report":
        return _decision("route_research_synthesis")
    return _decision("completed")


def route_intent(
    intent: ResearchIntent,
    state: WorkflowStateView | None = None,
) -> RouteDecision:
    if intent.method_family is not None:
        capability = resolve_capability(intent.method_family)
        if not capability.executable:
            return RouteDecision(
                action="method_not_implemented",
                target_skill=None,
                issue_codes=("method_not_implemented",),
                user_message=METHOD_NOT_IMPLEMENTED_MESSAGE,
            )
    if intent.domain != "empirical_macro":
        return _decision("out_of_scope", "out_of_scope")
    if intent.method_family is None:
        return _decision("route_research_design", "method_classification_required")
    if intent.has_workflow_state and state is None:
        raise ValueError("workflow state is required")
    if state is not None:
        return _route_state(state)
    return _route_artifacts(intent)


def render_user_response(decision: RouteDecision) -> str | None:
    if decision.action != "method_not_implemented":
        return None
    return cast(str, decision.user_message)
