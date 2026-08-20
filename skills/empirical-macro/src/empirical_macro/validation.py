from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from empirical_macro.artifact_refs import resolve_artifact_path, sha256_file
from empirical_macro.models import ArtifactRef


@dataclass(frozen=True, slots=True)
class ValidatorCommand:
    skill: str
    executable: str
    script: str


def load_validator_commands(
    skill_suite_root: Path,
) -> dict[str, ValidatorCommand]:
    package_config = Path(__file__).resolve().parent / "configs" / "skill-suite.json"
    source_config = Path(__file__).resolve().parents[2] / "configs" / "skill-suite.json"
    config_path = package_config if package_config.is_file() else source_config
    document = json.loads(config_path.read_text(encoding="utf-8"))
    validators = document.get("validators")
    if not isinstance(validators, dict):
        raise ValueError("skill-suite validators must be an object")
    commands: dict[str, ValidatorCommand] = {}
    for skill, relative_script in validators.items():
        if not isinstance(skill, str) or not isinstance(relative_script, str):
            raise ValueError("skill-suite validator entry is invalid")
        skill_root = skill_suite_root / skill
        script = skill_root / relative_script
        executable = skill_root / ".venv" / "bin" / "python"
        if not script.is_file():
            raise ValueError(f"validator script missing: {skill}")
        commands[skill] = ValidatorCommand(
            skill=skill,
            executable=str(executable if executable.is_file() else Path(sys.executable)),
            script=str(script.resolve()),
        )
    return commands


def _validator_result(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("artifact validator returned invalid JSON") from error
    if not isinstance(document, dict):
        raise ValueError("artifact validator result must be an object")
    result = cast(dict[str, object], document)
    if completed.returncode != 0 or result.get("valid") is not True:
        raise ValueError("artifact validator rejected bundle")
    return result


def validate_artifact_ref(
    *,
    project_root: Path,
    artifact_ref: ArtifactRef,
    validator: ValidatorCommand,
) -> dict[str, object]:
    if artifact_ref.validator != validator.skill:
        raise ValueError("artifact validator skill mismatch")
    artifact_path = resolve_artifact_path(project_root, artifact_ref.path)
    actual_checksum = sha256_file(artifact_path)
    if actual_checksum != artifact_ref.sha256:
        raise ValueError(
            f"checksum mismatch: expected {artifact_ref.sha256}, got {actual_checksum}"
        )
    raw_script = Path(validator.script)
    script_path = (
        raw_script.resolve()
        if raw_script.is_absolute()
        else resolve_artifact_path(project_root, validator.script)
    )
    if not script_path.is_file():
        raise ValueError(f"artifact validator script is missing: {validator.skill}")
    bundle_path = artifact_path.parent
    # Executable and script come from the frozen Skill registry, never a shell string.
    completed = subprocess.run(  # noqa: S603
        [validator.executable, str(script_path), str(bundle_path)],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
        shell=False,
    )
    return _validator_result(completed)
