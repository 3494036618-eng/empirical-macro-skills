from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from empirical_macro.capability_registry import registry_version, resolve_capability
from empirical_macro.checkpoint import create_checkpoint, state_to_document
from empirical_macro.contracts import validate_document
from empirical_macro.models import (
    ArtifactRef,
    ResearchIntent,
    RouteDecision,
    WorkflowStage,
    WorkflowState,
)
from empirical_macro.router import render_user_response, route_intent
from empirical_macro.stage_protocol import StageCommand as StageCommand
from empirical_macro.stage_protocol import StageRunner as StageRunner
from empirical_macro.stage_protocol import (
    SubprocessStageRunner as SubprocessStageRunner,
)
from empirical_macro.stage_protocol import parse_stage_refs
from empirical_macro.state_machine import transition_state
from empirical_macro.validation import ValidatorCommand, validate_artifact_ref

RunUntil = Literal["blocked", "completed", "next"]


@dataclass(frozen=True, slots=True)
class WorkflowRunResult:
    state: WorkflowState | None
    route_decision: RouteDecision
    executed_stages: tuple[WorkflowStage, ...]
    artifact_outputs: tuple[str, ...]
    user_message: str | None
    output_root: Path
    stopped_reason: str | None


TARGET_STAGES: dict[WorkflowStage, WorkflowStage] = {
    "idea_received": "design_ready",
    "design_ready": "data_ready",
    "data_ready": "estimation_ready",
    "estimation_ready": "audit_ready",
    "audit_ready": "synthesis_ready",
    "synthesis_ready": "completed",
}
STAGE_SKILLS: dict[WorkflowStage, str] = {
    "design_ready": "research-design",
    "data_ready": "macro-data",
    "estimation_ready": "time-series-dynamics",
    "audit_ready": "robustness-audit",
    "completed": "research-synthesis",
}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _initial_state(intent: ResearchIntent) -> WorkflowState:
    if intent.method_family not in {
        "dynamic_shock_response",
        "conditional_dynamic_association",
    }:
        raise ValueError("supported method is required to create workflow state")
    payload = json.dumps(asdict(intent), sort_keys=True, separators=(",", ":")).encode()
    identity = hashlib.sha256(payload).hexdigest()
    now = _timestamp()
    return WorkflowState(
        schema_version="0.1.0-beta",
        workflow_id="workflow-" + identity[:32],
        created_at=now,
        updated_at=now,
        current_stage="idea_received",
        supported_method=intent.method_family,
        registry_version=registry_version(),
        route_action="route_research_design",
        request_id="request-" + identity[:16],
        artifact_refs=(),
        issue_codes=(),
        checkpoint_id=None,
        resume_eligible=False,
        status="active",
    )


def _state_intent(state: WorkflowState) -> ResearchIntent:
    return ResearchIntent(
        domain="empirical_macro",
        request_kind="resume",
        method_family=state.supported_method,
        has_research_plan=True,
        has_macro_data_bundle=True,
        has_estimator_bundle=True,
        has_robustness_bundle=True,
        has_workflow_state=True,
    )


def _blocked_result(
    state: WorkflowState,
    command: StageCommand,
    output_root: Path,
) -> WorkflowRunResult:
    issue = (
        "macro_bundle_not_analysis_ready"
        if command.skill == "macro-data"
        else command.skill.replace("-", "_") + "_stage_failed"
    )
    blocked = transition_state(
        state,
        target_stage="blocked",
        artifact_refs=(),
        issue_codes=(issue,),
    )
    decision = route_intent(_state_intent(blocked), blocked)
    return WorkflowRunResult(blocked, decision, (), (), None, output_root, issue)


def _failed_result(
    state: WorkflowState,
    command: StageCommand,
    output_root: Path,
) -> WorkflowRunResult:
    issue = command.skill.replace("-", "_") + "_stage_failed"
    failed = transition_state(
        state,
        target_stage="failed",
        artifact_refs=(),
        issue_codes=(issue,),
    )
    decision = route_intent(_state_intent(failed), failed)
    return WorkflowRunResult(failed, decision, (), (), None, output_root, issue)


def _synthesis_checkpoint(state: WorkflowState, output_root: Path) -> WorkflowRunResult:
    source = state.artifact_refs[-1]
    binding = ArtifactRef(
        role="synthesis_checkpoint",
        path=source.path,
        sha256=source.sha256,
        validator=source.validator,
    )
    updated = transition_state(
        state,
        target_stage="synthesis_ready",
        artifact_refs=(binding,),
    )
    decision = route_intent(_state_intent(updated), updated)
    return WorkflowRunResult(
        updated,
        decision,
        ("synthesis_ready",),
        (binding.path,),
        None,
        output_root,
        None,
    )


def _execute_stage(
    *,
    state: WorkflowState,
    command: StageCommand,
    output_root: Path,
    runner: StageRunner,
) -> subprocess.CompletedProcess[str] | WorkflowRunResult:
    try:
        completed = runner.run(command)
    except (OSError, subprocess.SubprocessError):
        return _failed_result(state, command, output_root)
    if completed.returncode != 0:
        return _failed_result(state, command, output_root)
    return completed


def _validate_stage_ref(
    *,
    state: WorkflowState,
    command: StageCommand,
    ref: ArtifactRef,
    project_root: Path,
    output_root: Path,
    validators: Mapping[str, ValidatorCommand],
) -> WorkflowRunResult | None:
    command_validator = validators.get(ref.validator)
    if command_validator is None:
        return _failed_result(state, command, output_root)
    try:
        validate_artifact_ref(
            project_root=project_root,
            artifact_ref=ref,
            validator=command_validator,
        )
    except ValueError:
        return _blocked_result(state, command, output_root)
    except (OSError, subprocess.SubprocessError):
        return _failed_result(state, command, output_root)
    return None


def _validated_stage_refs(
    *,
    state: WorkflowState,
    command: StageCommand,
    completed: subprocess.CompletedProcess[str],
    project_root: Path,
    output_root: Path,
    validators: Mapping[str, ValidatorCommand],
) -> tuple[ArtifactRef, ...] | WorkflowRunResult:
    try:
        refs = parse_stage_refs(completed, command)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _failed_result(state, command, output_root)
    for ref in refs:
        failure = _validate_stage_ref(
            state=state,
            command=command,
            ref=ref,
            project_root=project_root,
            output_root=output_root,
            validators=validators,
        )
        if failure is not None:
            return failure
    return refs


def run_next_stage(
    *,
    state: WorkflowState,
    commands: Mapping[WorkflowStage, StageCommand],
    project_root: Path,
    output_root: Path,
    runner: StageRunner,
    validators: Mapping[str, ValidatorCommand] | None = None,
) -> WorkflowRunResult:
    if validators is None:
        raise ValueError("validator commands are required")
    if state.current_stage == "audit_ready":
        return _synthesis_checkpoint(state, output_root)
    if state.current_stage in {"completed", "blocked", "failed"}:
        decision = route_intent(_state_intent(state), state)
        return WorkflowRunResult(state, decision, (), (), None, output_root, None)
    target = TARGET_STAGES[state.current_stage]
    command = commands.get(target)
    if command is None or command.stage != target:
        raise ValueError(f"stage command missing: {target}")
    expected_skill = STAGE_SKILLS[target]
    if command.skill != expected_skill:
        raise ValueError(
            f"stage skill mismatch: {target} requires {expected_skill}"
        )
    executed = _execute_stage(
        state=state,
        command=command,
        output_root=output_root,
        runner=runner,
    )
    if isinstance(executed, WorkflowRunResult):
        return executed
    validated = _validated_stage_refs(
        state=state,
        command=command,
        completed=executed,
        project_root=project_root,
        output_root=output_root,
        validators=validators,
    )
    if isinstance(validated, WorkflowRunResult):
        return validated
    refs = validated
    updated = transition_state(state, target_stage=target, artifact_refs=refs)
    decision = route_intent(_state_intent(updated), updated)
    return WorkflowRunResult(
        updated,
        decision,
        (target,),
        tuple(ref.path for ref in refs),
        render_user_response(decision),
        output_root,
        None,
    )


def _validate_existing_state(
    *,
    intent: ResearchIntent,
    state: WorkflowState,
    project_root: Path,
    validators: Mapping[str, ValidatorCommand] | None,
) -> None:
    if not intent.has_workflow_state:
        raise ValueError("workflow state declaration mismatch")
    if intent.method_family != state.supported_method:
        raise ValueError("workflow method mismatch")
    capability = resolve_capability(state.supported_method)
    if not capability.executable:
        raise ValueError("workflow method is not executable")
    if state.registry_version != registry_version():
        raise ValueError("registry version mismatch")
    validate_document("workflow_state", state_to_document(state))
    if state.current_stage not in {"idea_received", "blocked", "failed"}:
        create_checkpoint(state)
    if validators is None:
        raise ValueError("validator commands are required")
    for ref in state.artifact_refs:
        command = validators.get(ref.validator)
        if command is None:
            raise ValueError(f"validator command missing: {ref.validator}")
        validate_artifact_ref(
            project_root=project_root,
            artifact_ref=ref,
            validator=command,
        )


def run_intent(
    *,
    intent: ResearchIntent,
    runner: StageRunner,
    state: WorkflowState | None = None,
    commands: Mapping[WorkflowStage, StageCommand] | None = None,
    project_root: Path = Path("."),
    output_root: Path = Path("."),
    run_until: RunUntil = "completed",
    validators: Mapping[str, ValidatorCommand] | None = None,
) -> WorkflowRunResult:
    decision = route_intent(intent, state)
    if decision.action in {"method_not_implemented", "out_of_scope"}:
        return WorkflowRunResult(
            state,
            decision,
            (),
            (),
            render_user_response(decision),
            output_root,
            decision.action,
        )
    if state is not None:
        _validate_existing_state(
            intent=intent,
            state=state,
            project_root=project_root,
            validators=validators,
        )
    if commands is None:
        return WorkflowRunResult(state, decision, (), (), None, output_root, "route_only")
    if state is None and decision.action != "route_research_design":
        return WorkflowRunResult(state, decision, (), (), None, output_root, "route_only")
    current = state or _initial_state(intent)
    stages: list[WorkflowStage] = []
    artifacts: list[str] = []
    while current.current_stage not in {"completed", "blocked", "failed"}:
        step = run_next_stage(
            state=current,
            commands=commands,
            project_root=project_root,
            output_root=output_root,
            runner=runner,
            validators=validators,
        )
        if step.state is None:
            raise RuntimeError("stage execution lost workflow state")
        current = step.state
        stages.extend(step.executed_stages)
        artifacts.extend(step.artifact_outputs)
        if step.stopped_reason is not None or run_until == "next":
            return WorkflowRunResult(
                current,
                step.route_decision,
                tuple(stages),
                tuple(artifacts),
                step.user_message,
                output_root,
                step.stopped_reason,
            )
    final_decision = route_intent(_state_intent(current), current)
    return WorkflowRunResult(
        current,
        final_decision,
        tuple(stages),
        tuple(artifacts),
        render_user_response(final_decision),
        output_root,
        current.current_stage if current.current_stage != "completed" else None,
    )
