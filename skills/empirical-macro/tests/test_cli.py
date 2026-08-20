from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def intent_document(method: str, *, request_kind: str = "final_report") -> dict[str, object]:
    return {
        "schema_version": "0.1.0-beta",
        "domain": "empirical_macro",
        "request_kind": request_kind,
        "method_family": method,
        "has_research_plan": False,
        "has_macro_data_bundle": False,
        "has_estimator_bundle": False,
        "has_robustness_bundle": False,
        "has_workflow_state": False,
    }


def run_script(script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def prepare_design_command(
    tmp_path: Path,
    *,
    invalidate_bundle: bool = False,
) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    relative_artifact = Path(
        "artifacts/design_ready/research-design-run-manifest.json"
    )
    bundle = project_root / relative_artifact.parent
    shutil.copytree(
        ROOT / "fixtures" / "workflow" / "dynamic-gold" / "stages" / "design_ready",
        bundle,
    )
    if invalidate_bundle:
        (bundle / "data_requirements.json").unlink()
    artifact = project_root / relative_artifact
    reference = {
        "role": "design_ready",
        "path": relative_artifact.as_posix(),
        "sha256": "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "validator": "research-design",
    }
    stage_result = json.dumps({"valid": True, "artifact_refs": [reference]})
    commands = tmp_path / "commands.json"
    commands.write_text(
        json.dumps(
            {
                "commands": [
                    {
                        "stage": "design_ready",
                        "skill": "research-design",
                        "command": [sys.executable, "-c", f"print({stage_result!r})"],
                        "expected_artifacts": [relative_artifact.as_posix()],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return project_root, commands


def test_route_cli_emits_valid_structured_decision(tmp_path: Path) -> None:
    """Break caught: the CLI bypasses the same deterministic Router."""
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(
        json.dumps(intent_document("dynamic_shock_response")),
        encoding="utf-8",
    )
    completed = run_script(
        "route_empirical_macro.py",
        "--intent-json",
        str(intent_path),
    )
    assert completed.returncode == 0, completed.stderr
    decision = json.loads(completed.stdout)
    assert decision["action"] == "route_research_design"
    assert decision["target_skill"] == "research-design"


def test_workflow_cli_unsupported_output_is_exact(tmp_path: Path) -> None:
    """Break caught: the user-visible CLI adds explanation to the fixed denial."""
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(
        json.dumps(intent_document("panel_association")),
        encoding="utf-8",
    )
    completed = run_script(
        "run_workflow.py",
        "--intent-json",
        str(intent_path),
        "--project-root",
        str(tmp_path),
        "--output",
        str(tmp_path / "output"),
    )
    assert completed.returncode == 2
    assert completed.stdout == "当前版本不能执行该方法\n"
    assert completed.stderr == ""


def test_workflow_cli_without_commands_only_reports_next_route(tmp_path: Path) -> None:
    """Break caught: default CLI mode executes an unapproved stage command."""
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(
        json.dumps(intent_document("conditional_dynamic_association")),
        encoding="utf-8",
    )
    completed = run_script(
        "run_workflow.py",
        "--intent-json",
        str(intent_path),
        "--project-root",
        str(tmp_path),
        "--output",
        str(tmp_path / "output"),
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "action": "route_research_design",
        "executed": False,
        "target_skill": "research-design",
    }


def test_workflow_cli_persists_resumable_checkpoint(tmp_path: Path) -> None:
    """Break caught: a successful next-stage state cannot be resumed."""
    project_root, commands = prepare_design_command(tmp_path)
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(
        json.dumps(intent_document("dynamic_shock_response")),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    completed = run_script(
        "run_workflow.py",
        "--intent-json",
        str(intent_path),
        "--commands-json",
        str(commands),
        "--project-root",
        str(project_root),
        "--output",
        str(output),
    )
    assert completed.returncode == 0, completed.stderr
    state = json.loads((output / "workflow-state.json").read_text(encoding="utf-8"))
    assert state["current_stage"] == "design_ready"
    assert state["checkpoint_id"].startswith("checkpoint-")


def test_workflow_cli_validator_failure_persists_blocked_state(
    tmp_path: Path,
) -> None:
    """Break caught: invalid stage evidence advances or disappears on failure."""
    project_root, commands = prepare_design_command(
        tmp_path,
        invalidate_bundle=True,
    )
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(
        json.dumps(intent_document("dynamic_shock_response")),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    completed = run_script(
        "run_workflow.py",
        "--intent-json",
        str(intent_path),
        "--commands-json",
        str(commands),
        "--project-root",
        str(project_root),
        "--output",
        str(output),
    )
    assert completed.returncode == 1
    state = json.loads((output / "workflow-state.json").read_text(encoding="utf-8"))
    assert state["current_stage"] == "blocked"
    assert state["status"] == "blocked"
    assert state["checkpoint_id"] is None


def test_workflow_cli_resume_runs_public_validator(tmp_path: Path) -> None:
    """Break caught: resume checks only the manifest checksum, not its bundle."""
    project_root, commands = prepare_design_command(tmp_path)
    first_intent = tmp_path / "first-intent.json"
    first_intent.write_text(
        json.dumps(intent_document("dynamic_shock_response")),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    first = run_script(
        "run_workflow.py",
        "--intent-json",
        str(first_intent),
        "--commands-json",
        str(commands),
        "--project-root",
        str(project_root),
        "--output",
        str(output),
    )
    assert first.returncode == 0, first.stderr
    (project_root / "artifacts" / "design_ready" / "data_requirements.json").unlink()

    resume_document = intent_document(
        "dynamic_shock_response",
        request_kind="resume",
    )
    resume_document["has_research_plan"] = True
    resume_document["has_workflow_state"] = True
    resume_intent = tmp_path / "resume-intent.json"
    resume_intent.write_text(json.dumps(resume_document), encoding="utf-8")
    resumed = run_script(
        "run_workflow.py",
        "--intent-json",
        str(resume_intent),
        "--workflow-state",
        str(output / "workflow-state.json"),
        "--project-root",
        str(project_root),
        "--output",
        str(output),
    )
    assert resumed.returncode != 0
    assert "artifact validator rejected bundle" in resumed.stderr
