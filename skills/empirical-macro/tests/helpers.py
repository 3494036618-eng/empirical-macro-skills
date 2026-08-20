from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from empirical_macro.models import (
        ArtifactRef,
        ResearchIntent,
        WorkflowStage,
        WorkflowState,
    )
    from empirical_macro.orchestrator import StageCommand, WorkflowRunResult
    from empirical_macro.validation import ValidatorCommand


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SUITE = ROOT / "fixtures" / "install" / "public-suite"


def load_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def load_contract_fixture(name: str) -> dict[str, object]:
    return load_json(ROOT / "fixtures" / "contracts" / name)


def read_skill_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 4 or lines[0] != "---":
        raise ValueError("SKILL.md frontmatter is missing")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("SKILL.md frontmatter is not closed") from error
    document: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"invalid frontmatter line: {line}")
        document[key.strip()] = value.strip().strip('"')
    return document


def load_intent(document: dict[str, object]) -> ResearchIntent:
    from empirical_macro.contracts import validate_document
    from empirical_macro.models import ResearchIntent

    validate_document("research_intent", document)
    return ResearchIntent(
        domain=cast(str, document["domain"]),
        request_kind=cast(str, document["request_kind"]),
        method_family=cast(str | None, document["method_family"]),
        has_research_plan=cast(bool, document["has_research_plan"]),
        has_macro_data_bundle=cast(bool, document["has_macro_data_bundle"]),
        has_estimator_bundle=cast(bool, document["has_estimator_bundle"]),
        has_robustness_bundle=cast(bool, document["has_robustness_bundle"]),
        has_workflow_state=cast(bool, document["has_workflow_state"]),
    )


def load_optional_state(case: dict[str, object]) -> WorkflowState | None:
    stage = case.get("state_stage")
    if stage is None:
        return None
    return state_at(cast("WorkflowStage", stage))


def artifact_refs_for(stage: WorkflowStage) -> tuple[ArtifactRef, ...]:
    from empirical_macro.models import ArtifactRef

    validators = {
        "design_ready": "research-design",
        "data_ready": "macro-data",
        "estimation_ready": "time-series-dynamics",
        "audit_ready": "robustness-audit",
        "synthesis_ready": "robustness-audit",
        "completed": "research-synthesis",
    }
    validator = validators.get(stage)
    if validator is None:
        return ()
    return (
        ArtifactRef(
            role=stage,
            path=f"artifacts/{stage}.json",
            sha256="sha256:" + "0" * 64,
            validator=validator,
        ),
    )


def initial_state(
    method: str = "dynamic_shock_response",
) -> WorkflowState:
    from empirical_macro.models import WorkflowState

    return WorkflowState(
        schema_version="0.1.0-beta",
        workflow_id="workflow-" + "1" * 32,
        created_at="2026-08-19T00:00:00Z",
        updated_at="2026-08-19T00:00:00Z",
        current_stage="idea_received",
        supported_method=method,
        registry_version="dynamic-beta-v1",
        route_action="route_research_design",
        request_id="request-12345678",
        artifact_refs=(),
        issue_codes=(),
        checkpoint_id=None,
        resume_eligible=False,
        status="active",
    )


def state_at(stage: WorkflowStage) -> WorkflowState:
    from empirical_macro.state_machine import transition_state

    state = initial_state()
    if stage == "idea_received":
        return state
    for target in (
        "design_ready",
        "data_ready",
        "estimation_ready",
        "audit_ready",
        "synthesis_ready",
        "completed",
    ):
        state = transition_state(
            state,
            target_stage=target,
            artifact_refs=artifact_refs_for(target),
        )
        if target == stage:
            return state
    raise ValueError(f"unsupported test stage: {stage}")


def write_valid_state_and_artifact(root: Path) -> Path:
    from empirical_macro.checkpoint import create_checkpoint, write_state_transactionally
    from empirical_macro.models import ArtifactRef

    design_artifact = root / "artifacts" / "design.json"
    artifact = root / "artifacts" / "result.json"
    artifact.parent.mkdir(parents=True)
    design_content = b'{"valid": true, "stage": "design"}'
    content = b'{"valid": true}'
    design_artifact.write_bytes(design_content)
    artifact.write_bytes(content)
    refs = (
        ArtifactRef(
            role="research_design",
            path="artifacts/design.json",
            sha256="sha256:" + hashlib.sha256(design_content).hexdigest(),
            validator="research-design",
        ),
        ArtifactRef(
            role="macro_data",
            path="artifacts/result.json",
            sha256="sha256:" + hashlib.sha256(content).hexdigest(),
            validator="macro-data",
        ),
    )
    state = replace(
        state_at("data_ready"),
        artifact_refs=refs,
        registry_version="dynamic-beta-v1",
        checkpoint_id=None,
        resume_eligible=True,
    )
    checkpoint = create_checkpoint(state)
    state = replace(state, checkpoint_id=checkpoint.checkpoint_id)
    state_path = root / "workflow-state.json"
    write_state_transactionally(state, state_path)
    return state_path


class RecordingRunner:
    def __init__(
        self,
        root: Path | None = None,
        fail_skill: str | None = None,
    ) -> None:
        self.root = root
        self.fail_skill = fail_skill
        self.calls: list[StageCommand] = []
        self.skills: list[str] = []

    def run(self, command: StageCommand) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        self.skills.append(command.skill)
        if command.skill == self.fail_skill:
            return subprocess.CompletedProcess(
                command.command,
                1,
                stdout='{"valid": false, "issue_codes": ["injected_failure"]}',
                stderr="injected failure",
            )
        path = command.expected_artifacts[0]
        if self.root is not None:
            artifact = self.root / path
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text(path, encoding="utf-8")
        ref = {
            "role": command.stage,
            "path": path,
            "sha256": "sha256:" + hashlib.sha256(path.encode()).hexdigest(),
            "validator": command.skill,
        }
        return subprocess.CompletedProcess(
            command.command,
            0,
            stdout=json.dumps({"valid": True, "artifact_refs": [ref]}),
            stderr="",
        )


def recording_validators(
    root: Path,
    *,
    invalid_skill: str | None = None,
) -> dict[str, ValidatorCommand]:
    from empirical_macro.validation import ValidatorCommand

    commands: dict[str, ValidatorCommand] = {}
    validator_root = root / "recording-validators"
    validator_root.mkdir(parents=True, exist_ok=True)
    for skill in (
        "research-design",
        "macro-data",
        "time-series-dynamics",
        "robustness-audit",
        "research-synthesis",
    ):
        valid = skill != invalid_skill
        script = validator_root / f"{skill}.py"
        script.write_text(
            "import json\n"
            f"print(json.dumps({{'valid': {valid!r}}}))\n"
            f"raise SystemExit({0 if valid else 1})\n",
            encoding="utf-8",
        )
        commands[skill] = ValidatorCommand(
            skill=skill,
            executable=sys.executable,
            script=str(script),
        )
    return commands


def recording_commands() -> dict[WorkflowStage, StageCommand]:
    from empirical_macro.orchestrator import StageCommand

    stages = (
        ("design_ready", "research-design"),
        ("data_ready", "macro-data"),
        ("estimation_ready", "time-series-dynamics"),
        ("audit_ready", "robustness-audit"),
        ("completed", "research-synthesis"),
    )
    return {
        cast("WorkflowStage", stage): StageCommand(
            stage=cast("WorkflowStage", stage),
            skill=skill,
            command=("record", skill),
            expected_artifacts=(f"artifacts/{stage}/result.json",),
        )
        for stage, skill in stages
    }


def run_supported_gold(runner: RecordingRunner) -> WorkflowRunResult:
    from empirical_macro.models import ResearchIntent
    from empirical_macro.orchestrator import run_intent

    intent = ResearchIntent(
        domain="empirical_macro",
        request_kind="final_report",
        method_family="dynamic_shock_response",
        has_research_plan=False,
        has_macro_data_bundle=False,
        has_estimator_bundle=False,
        has_robustness_bundle=False,
        has_workflow_state=False,
    )
    return run_intent(
        intent=intent,
        runner=runner,
        commands=recording_commands(),
        project_root=runner.root or ROOT,
        output_root=runner.root or ROOT / ".test-output",
        run_until="completed",
        validators=recording_validators(runner.root or ROOT),
    )
