from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from tests.helpers import state_at

ROOT = Path(__file__).resolve().parents[1]



@dataclass(frozen=True)
class StageView:
    current_stage: str


def load_cases() -> list[dict[str, object]]:
    document = json.loads(
        (ROOT / "fixtures" / "routing" / "router-cases.json").read_text(
            encoding="utf-8"
        )
    )
    return cast(list[dict[str, object]], document)


def test_unsupported_method_wins_over_all_other_routes() -> None:
    """Break caught: complete-looking artifacts bypass the method hard gate."""
    from empirical_macro.models import ResearchIntent
    from empirical_macro.router import route_intent

    intent = ResearchIntent(
        domain="empirical_macro",
        request_kind="final_report",
        method_family="panel_association",
        has_research_plan=True,
        has_macro_data_bundle=True,
        has_estimator_bundle=True,
        has_robustness_bundle=True,
        has_workflow_state=False,
    )
    decision = route_intent(intent)
    assert decision.action == "method_not_implemented"
    assert decision.target_skill is None
    assert decision.user_message == "当前版本不能执行该方法"


def test_router_cases_follow_the_frozen_priority() -> None:
    """Break caught: an intent is routed from convenience rather than evidence."""
    from empirical_macro.models import ResearchIntent
    from empirical_macro.router import route_intent

    for case in load_cases():
        intent = ResearchIntent(**cast(dict[str, object], case["intent"]))
        stage = case["state_stage"]
        state = StageView(cast(str, stage)) if isinstance(stage, str) else None
        decision = route_intent(intent, state)
        assert decision.action == case["expected_action"], case["case_id"]
        assert decision.target_skill == case["expected_target_skill"], case["case_id"]
        assert decision.user_message == case["expected_user_message"], case["case_id"]


def test_declared_workflow_without_state_is_rejected() -> None:
    """Break caught: a resume request silently invents workflow state."""
    from empirical_macro.models import ResearchIntent
    from empirical_macro.router import route_intent

    intent = ResearchIntent(
        domain="empirical_macro",
        request_kind="resume",
        method_family="dynamic_shock_response",
        has_research_plan=True,
        has_macro_data_bundle=True,
        has_estimator_bundle=True,
        has_robustness_bundle=True,
        has_workflow_state=True,
    )
    with pytest.raises(ValueError, match="workflow state is required"):
        route_intent(intent)


def test_renderer_only_exposes_the_deterministic_user_message() -> None:
    """Break caught: internal issue codes leak into the unsupported response."""
    from empirical_macro.models import RouteDecision
    from empirical_macro.router import render_user_response

    decision = RouteDecision(
        action="method_not_implemented",
        target_skill=None,
        issue_codes=("method_not_implemented",),
        user_message="当前版本不能执行该方法",
    )
    assert render_user_response(decision) == "当前版本不能执行该方法"


def test_null_method_is_routed_to_design_not_estimation() -> None:
    """Break caught: an unclassified method bypasses the capability allowlist."""
    from empirical_macro.models import ResearchIntent
    from empirical_macro.router import route_intent

    decision = route_intent(
        ResearchIntent(
            domain="empirical_macro",
            request_kind="dynamic_analysis",
            method_family=None,
            has_research_plan=True,
            has_macro_data_bundle=True,
            has_estimator_bundle=False,
            has_robustness_bundle=False,
            has_workflow_state=False,
        )
    )
    assert decision.action == "route_research_design"
    assert decision.target_skill == "research-design"


@pytest.mark.parametrize("stage", ("blocked", "failed"))
def test_failed_terminal_state_uses_stopped_action(stage: str) -> None:
    """Break caught: a failed workflow is exposed as successfully completed."""
    from dataclasses import replace

    from empirical_macro.models import ResearchIntent
    from empirical_macro.router import route_intent

    base = state_at("data_ready")
    state = replace(
        base,
        current_stage=stage,
        status=stage,
        resume_eligible=False,
    )
    decision = route_intent(
        ResearchIntent(
            domain="empirical_macro",
            request_kind="resume",
            method_family="dynamic_shock_response",
            has_research_plan=True,
            has_macro_data_bundle=True,
            has_estimator_bundle=False,
            has_robustness_bundle=False,
            has_workflow_state=True,
        ),
        state,
    )
    assert decision.action == "stopped"
    assert decision.issue_codes == (f"workflow_{stage}",)
