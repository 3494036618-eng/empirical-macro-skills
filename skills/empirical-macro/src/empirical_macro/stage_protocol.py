from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Protocol, cast

from empirical_macro.models import ArtifactRef, WorkflowStage


@dataclass(frozen=True, slots=True)
class StageCommand:
    stage: WorkflowStage
    skill: str
    command: tuple[str, ...]
    expected_artifacts: tuple[str, ...]


class StageRunner(Protocol):
    def run(self, command: StageCommand) -> subprocess.CompletedProcess[str]: ...


class SubprocessStageRunner:
    def run(self, command: StageCommand) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            list(command.command),
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )


def parse_stage_refs(
    completed: subprocess.CompletedProcess[str],
    command: StageCommand,
) -> tuple[ArtifactRef, ...]:
    document = json.loads(completed.stdout)
    if not isinstance(document, dict) or document.get("valid") is not True:
        raise ValueError("stage result is not valid")
    raw_refs = document.get("artifact_refs")
    if not isinstance(raw_refs, list) or not raw_refs:
        raise ValueError("stage result has no artifact refs")
    refs = tuple(
        ArtifactRef(
            role=cast(str, item["role"]),
            path=cast(str, item["path"]),
            sha256=cast(str, item["sha256"]),
            validator=cast(str, item["validator"]),
        )
        for item in cast(list[dict[str, object]], raw_refs)
    )
    if not set(command.expected_artifacts).issubset({ref.path for ref in refs}):
        raise ValueError("stage result is missing expected artifacts")
    if any(ref.validator != command.skill for ref in refs):
        raise ValueError("stage result validator mismatch")
    return refs
