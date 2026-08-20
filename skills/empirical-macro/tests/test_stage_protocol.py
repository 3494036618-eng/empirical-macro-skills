from __future__ import annotations

import json
import subprocess
import sys

import pytest

from empirical_macro.stage_protocol import (
    StageCommand,
    SubprocessStageRunner,
    parse_stage_refs,
)


def command() -> StageCommand:
    return StageCommand(
        stage="design_ready",
        skill="research-design",
        command=(sys.executable, "-c", "print('ok')"),
        expected_artifacts=("artifacts/design/result.json",),
    )


def test_subprocess_stage_runner_uses_argument_array() -> None:
    """Break caught: stage execution stops invoking the declared argv."""
    completed = SubprocessStageRunner().run(command())
    assert completed.returncode == 0
    assert completed.stdout == "ok\n"


@pytest.mark.parametrize(
    ("document", "message"),
    (
        ([], "stage result is not valid"),
        ({"valid": False}, "stage result is not valid"),
        ({"valid": True}, "stage result has no artifact refs"),
    ),
)
def test_stage_protocol_rejects_invalid_envelopes(
    document: object,
    message: str,
) -> None:
    """Break caught: malformed stage output is accepted as evidence."""
    completed = subprocess.CompletedProcess(
        command().command,
        0,
        stdout=json.dumps(document),
        stderr="",
    )
    with pytest.raises(ValueError, match=message):
        parse_stage_refs(completed, command())


@pytest.mark.parametrize(
    ("path", "validator", "message"),
    (
        (
            "artifacts/other/result.json",
            "research-design",
            "stage result is missing expected artifacts",
        ),
        (
            "artifacts/design/result.json",
            "macro-data",
            "stage result validator mismatch",
        ),
    ),
)
def test_stage_protocol_rejects_wrong_artifact_contract(
    path: str,
    validator: str,
    message: str,
) -> None:
    """Break caught: a stage claims the wrong artifact or validator."""
    document = {
        "valid": True,
        "artifact_refs": [
            {
                "role": "design_ready",
                "path": path,
                "sha256": "sha256:" + "0" * 64,
                "validator": validator,
            }
        ],
    }
    completed = subprocess.CompletedProcess(
        command().command,
        0,
        stdout=json.dumps(document),
        stderr="",
    )
    with pytest.raises(ValueError, match=message):
        parse_stage_refs(completed, command())
