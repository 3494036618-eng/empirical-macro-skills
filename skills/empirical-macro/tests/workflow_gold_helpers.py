from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import cast

from empirical_macro.artifact_refs import sha256_file
from empirical_macro.checkpoint import (
    create_checkpoint,
    resume_workflow,
    write_state_transactionally,
)
from empirical_macro.models import ResearchIntent, WorkflowStage, WorkflowState
from empirical_macro.orchestrator import (
    StageCommand,
    WorkflowRunResult,
    run_intent,
)
from empirical_macro.validation import ValidatorCommand
from tests.helpers import ROOT

GOLD_ROOT = ROOT / "fixtures" / "workflow" / "dynamic-gold"
ATOMIC_ROOT = ROOT.parent
ARTIFACT_PATHS = {
    "design_ready": ".workflow/design_ready/research-design-run-manifest.json",
    "data_ready": ".workflow/data_ready/input-evidence-manifest.json",
    "estimation_ready": ".workflow/estimation_ready/run-manifest.json",
    "audit_ready": ".workflow/audit_ready/run-manifest.json",
    "completed": ".workflow/completed/research-report.md",
}
SKILLS = {
    "design_ready": "research-design",
    "data_ready": "macro-data",
    "estimation_ready": "time-series-dynamics",
    "audit_ready": "robustness-audit",
    "completed": "research-synthesis",
}


class GoldReplayRunner:
    def __init__(self, root: Path, mutation: str | None = None) -> None:
        self.root = root
        self.mutation = mutation
        self.skills: list[str] = []

    def run(self, command: StageCommand) -> subprocess.CompletedProcess[str]:
        self.skills.append(command.skill)
        source = GOLD_ROOT / "stages" / command.stage
        destination = self.root / Path(command.expected_artifacts[0]).parent
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        artifact = self.root / command.expected_artifacts[0]
        expected_checksum = sha256_file(artifact)
        self._mutate(command.stage, destination, artifact)
        ref = {
            "role": command.stage,
            "path": command.expected_artifacts[0],
            "sha256": expected_checksum,
            "validator": command.skill,
        }
        return subprocess.CompletedProcess(
            command.command,
            0,
            stdout=json.dumps({"valid": True, "artifact_refs": [ref]}),
            stderr="",
        )

    def _mutate(
        self,
        stage: WorkflowStage,
        bundle: Path,
        artifact: Path,
    ) -> None:
        if self.mutation == "macro_checksum_mismatch" and stage == "data_ready":
            artifact.write_text(
                artifact.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
        elif self.mutation == "shock_artifact_missing" and stage == "data_ready":
            (bundle / "shock-identification-artifact.json").unlink()
        elif self.mutation == "estimator_result_tamper" and stage == "estimation_ready":
            result = bundle / "result.json"
            result.write_text(result.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        elif (
            self.mutation == "required_robustness_check_missing"
            and stage == "audit_ready"
        ):
            (bundle / "check-results.json").unlink()
        elif self.mutation == "synthesis_manifest_mismatch" and stage == "completed":
            manifest_path = bundle / ".audit" / "run-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["run_id"] = "rs-run-" + "0" * 32
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )


def gold_commands() -> dict[WorkflowStage, StageCommand]:
    return {
        cast(WorkflowStage, stage): StageCommand(
            stage=cast(WorkflowStage, stage),
            skill=SKILLS[stage],
            command=("gold-replay", SKILLS[stage]),
            expected_artifacts=(ARTIFACT_PATHS[stage],),
        )
        for stage in ARTIFACT_PATHS
    }


def _validator_source(skill: str) -> tuple[Path, Path]:
    if skill == "macro-data":
        module = ATOMIC_ROOT / "time-series-dynamics"
        return module, module / "scripts" / "validate_input_evidence.py"
    module = ATOMIC_ROOT / skill
    return module, module / "scripts" / "validate_bundle.py"


def gold_validators(root: Path) -> dict[str, ValidatorCommand]:
    validator_root = root / "validators"
    validator_root.mkdir(parents=True, exist_ok=True)
    commands: dict[str, ValidatorCommand] = {}
    for skill in (
        "research-design",
        "macro-data",
        "time-series-dynamics",
        "robustness-audit",
        "research-synthesis",
    ):
        module, source = _validator_source(skill)
        target = validator_root / f"{skill}.py"
        local_python = module / ".venv" / "bin" / "python"
        if local_python.is_file():
            shutil.copyfile(source, target)
        else:
            target.write_text(
                "import runpy, sys\n"
                f"sys.path.insert(0, {str(module / 'src')!r})\n"
                f"runpy.run_path({str(source)!r}, run_name='__main__')\n",
                encoding="utf-8",
            )
        commands[skill] = ValidatorCommand(
            skill=skill,
            executable=str(local_python if local_python.is_file() else Path(sys.executable)),
            script=target.relative_to(root).as_posix(),
        )
    return commands


def gold_intent(*, resume: bool = False) -> ResearchIntent:
    return ResearchIntent(
        domain="empirical_macro",
        request_kind="resume" if resume else "final_report",
        method_family="dynamic_shock_response",
        has_research_plan=resume,
        has_macro_data_bundle=resume,
        has_estimator_bundle=resume,
        has_robustness_bundle=resume,
        has_workflow_state=resume,
    )


def _publish_delivery(root: Path, result: WorkflowRunResult) -> None:
    if result.state is None or result.state.current_stage != "completed":
        return
    package = root / ".workflow" / "completed"
    for item in package.iterdir():
        destination = root / item.name
        if item.is_dir():
            shutil.copytree(item, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(item, destination)


def run_gold_workflow(
    output_root: Path,
    *,
    mutation: str | None = None,
) -> WorkflowRunResult:
    output_root.mkdir(parents=True, exist_ok=True)
    runner = GoldReplayRunner(output_root, mutation)
    result = run_intent(
        intent=gold_intent(),
        runner=runner,
        commands=gold_commands(),
        project_root=output_root,
        output_root=output_root,
        run_until="completed",
        validators=gold_validators(output_root),
    )
    _publish_delivery(output_root, result)
    return result


def _run_to_data(
    root: Path,
    runner: GoldReplayRunner,
    validators: dict[str, ValidatorCommand],
) -> WorkflowState:
    first = run_intent(
        intent=gold_intent(),
        runner=runner,
        commands=gold_commands(),
        project_root=root,
        output_root=root,
        run_until="next",
        validators=validators,
    )
    assert first.state is not None
    second = run_intent(
        intent=gold_intent(resume=True),
        runner=runner,
        state=first.state,
        commands=gold_commands(),
        project_root=root,
        output_root=root,
        run_until="next",
        validators=validators,
    )
    assert second.state is not None
    return second.state


def run_gold_resume(output_root: Path) -> tuple[WorkflowRunResult, list[str]]:
    output_root.mkdir(parents=True, exist_ok=True)
    validators = gold_validators(output_root)
    initial_runner = GoldReplayRunner(output_root)
    data_state = _run_to_data(output_root, initial_runner, validators)
    checkpoint = create_checkpoint(data_state)
    saved_state = replace(data_state, checkpoint_id=checkpoint.checkpoint_id)
    state_path = output_root / "workflow-state.json"
    write_state_transactionally(saved_state, state_path)
    resumed = resume_workflow(
        state_path=state_path,
        project_root=output_root,
        registry_version="dynamic-beta-v1",
        validators=validators,
    )
    resumed_runner = GoldReplayRunner(output_root)
    result = run_intent(
        intent=gold_intent(resume=True),
        runner=resumed_runner,
        state=resumed,
        commands=gold_commands(),
        project_root=output_root,
        output_root=output_root,
        run_until="completed",
        validators=validators,
    )
    _publish_delivery(output_root, result)
    return result, resumed_runner.skills


def gold_content_id(root: Path) -> str:
    digest = hashlib.sha256()
    roots = ("research-report.md", "tables", "figures", "reproduction")
    files: list[Path] = []
    for name in roots:
        path = root / name
        files.extend([path] if path.is_file() else path.rglob("*"))
    for path in sorted(item for item in files if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()
