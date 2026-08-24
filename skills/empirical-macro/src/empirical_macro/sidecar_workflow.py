from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

from empirical_macro.artifact_refs import sha256_file
from empirical_macro.capability_registry import resolve_capability
from empirical_macro.checkpoint import (
    state_from_document,
    state_to_document,
    write_state_transactionally,
)
from empirical_macro.contracts import validate_document
from empirical_macro.models import (
    ArtifactRef,
    ResearchIntent,
    RouteDecision,
    WorkflowState,
)
from empirical_macro.orchestrator import create_initial_state
from empirical_macro.router import route_intent
from empirical_macro.stage_result_gate import decide_after_stage
from empirical_macro.state_machine import transition_state

DesignRunner = Callable[..., dict[str, object]]

DYNAMIC_METHODS = frozenset(
    {
        "dynamic_shock_response",
        "conditional_dynamic_association",
    }
)
DYNAMIC_REQUIRED_INPUTS = frozenset(
    {
        "outcome",
        "policy_variable",
        "entity",
        "start",
        "end",
        "frequency",
        "horizon",
    }
)
DYNAMIC_OPTIONAL_INPUTS = frozenset(
    {
        "intended_claim",
        "shock_identification",
    }
)


def _decision_document(decision: RouteDecision) -> dict[str, object]:
    return {
        "schema_version": "0.1.0-beta",
        "action": decision.action,
        "target_skill": decision.target_skill,
        "issue_codes": list(decision.issue_codes),
        "user_message": decision.user_message,
    }


def _validate_dynamic_inputs(
    method_family: str,
    method_inputs: dict[str, object],
) -> dict[str, object]:
    missing = sorted(DYNAMIC_REQUIRED_INPUTS - method_inputs.keys())
    if missing:
        raise ValueError("method inputs missing: " + ",".join(missing))
    unknown = sorted(
        method_inputs.keys()
        - DYNAMIC_REQUIRED_INPUTS
        - DYNAMIC_OPTIONAL_INPUTS
    )
    if unknown:
        raise ValueError("unsupported method inputs: " + ",".join(unknown))
    result = dict(method_inputs)
    expected_claim = (
        "associational"
        if method_family == "conditional_dynamic_association"
        else "causal"
    )
    supplied_claim = result.setdefault("intended_claim", expected_claim)
    if supplied_claim != expected_claim:
        raise ValueError("method input conflict: intended_claim")
    result.setdefault("shock_identification", "unresolved")
    return result


def _design_artifact_ref(
    *,
    project_root: Path,
    design_output: Path,
) -> ArtifactRef:
    manifest = design_output / "research-design-run-manifest.json"
    relative = manifest.resolve().relative_to(project_root.resolve())
    return ArtifactRef(
        role="design_ready",
        path=relative.as_posix(),
        sha256=sha256_file(manifest),
        validator="research-design",
    )


def _result_document(
    *,
    state: WorkflowState,
    next_decision: dict[str, object],
    stage_result: dict[str, object],
    state_path: Path,
) -> dict[str, object]:
    state_document = state_to_document(state)
    return {
        "status": (
            "stopped"
            if next_decision["action"] == "stopped"
            else state_document["status"]
        ),
        "current_stage": state_document["current_stage"],
        "next_action": next_decision["action"],
        "target_skill": next_decision["target_skill"],
        "issue_codes": next_decision["issue_codes"],
        "stage_result": stage_result,
        "workflow_state_path": str(state_path),
    }


def _reject_existing_workflow(output_root: Path) -> None:
    state_path = output_root / "workflow-state.json"
    if not state_path.exists():
        return
    document = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("workflow state must be an object")
    state_document = cast(dict[str, object], document)
    validate_document("workflow_state", state_document)
    state = state_from_document(state_document)
    if state.status in {"blocked", "failed", "completed"}:
        raise ValueError(f"workflow state is terminal: {state.current_stage}")
    raise ValueError("workflow state already exists; resume required")


def run_design_stage(
    *,
    question: str,
    method_family: str,
    method_inputs: dict[str, object],
    output_root: Path,
    project_root: Path,
    design_runner: DesignRunner,
) -> dict[str, object]:
    _reject_existing_workflow(output_root)
    capability = resolve_capability(method_family)
    if not capability.executable:
        return {
            "status": "stopped",
            "current_stage": None,
            "next_action": "method_not_implemented",
            "target_skill": None,
            "issue_codes": [cast(str, capability.issue_code)],
            "stage_result": None,
            "workflow_state_path": None,
        }
    if method_family not in DYNAMIC_METHODS:
        raise ValueError(f"method adapter missing: {method_family}")
    arguments = _validate_dynamic_inputs(method_family, method_inputs)
    intent = ResearchIntent(
        domain="empirical_macro",
        request_kind="research_idea",
        method_family=method_family,
        has_research_plan=False,
        has_macro_data_bundle=False,
        has_estimator_bundle=False,
        has_robustness_bundle=False,
        has_workflow_state=False,
    )
    initial_state = create_initial_state(intent)
    initial_decision = route_intent(intent)
    design_output = output_root / "research-design"
    stage_result = design_runner(
        question,
        output_dir=str(design_output),
        **arguments,
    )
    next_decision = decide_after_stage(
        _decision_document(initial_decision),
        stage_result,
    )
    design_ref = _design_artifact_ref(
        project_root=project_root,
        design_output=design_output,
    )
    if next_decision["action"] == "stopped":
        state = transition_state(
            initial_state,
            target_stage="blocked",
            artifact_refs=(design_ref,),
            issue_codes=tuple(cast(list[str], next_decision["issue_codes"])),
        )
    else:
        state = transition_state(
            initial_state,
            target_stage="design_ready",
            artifact_refs=(design_ref,),
        )
    state_path = output_root / "workflow-state.json"
    write_state_transactionally(state, state_path)
    return _result_document(
        state=state,
        next_decision=next_decision,
        stage_result=stage_result,
        state_path=state_path,
    )
