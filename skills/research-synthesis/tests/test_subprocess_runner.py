from __future__ import annotations

import subprocess
import sys
from importlib import import_module
from pathlib import Path

import pytest


def test_runner_structures_success_and_failure(tmp_path: Path) -> None:
    module = import_module("research_synthesis.subprocess_runner")
    assert hasattr(module, "run_command")
    success = module.run_command(
        [sys.executable, "-c", "print('ok')"],
        tmp_path,
        10,
    )
    failed = module.run_command(
        [sys.executable, "-c", "import sys; print('bad', file=sys.stderr); sys.exit(3)"],
        tmp_path,
        10,
    )

    assert success.status == "success"
    assert success.returncode == 0
    assert success.stdout == "ok\n"
    assert failed.status == "failed"
    assert failed.returncode == 3
    assert failed.issue_codes == ("validator_nonzero_exit",)


def test_runner_structures_timeout(tmp_path: Path) -> None:
    module = import_module("research_synthesis.subprocess_runner")
    assert hasattr(module, "run_command")

    evidence = module.run_command(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        tmp_path,
        0.01,
    )

    assert evidence.status == "timeout"
    assert evidence.returncode is None
    assert evidence.issue_codes == ("validator_timeout",)


def test_runner_removes_parent_virtual_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("research_synthesis.subprocess_runner")
    assert hasattr(module, "run_command")
    monkeypatch.setenv("VIRTUAL_ENV", "/wrong/environment")

    evidence = module.run_command(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('VIRTUAL_ENV', 'missing'))",
        ],
        tmp_path,
        10,
    )

    assert evidence.stdout == "missing\n"


@pytest.mark.parametrize("argv", [[], [""]])
def test_runner_rejects_invalid_argv(
    tmp_path: Path,
    argv: list[str],
) -> None:
    module = import_module("research_synthesis.subprocess_runner")

    with pytest.raises(ValueError, match="validator_argv_invalid"):
        module.run_command(argv, tmp_path, 10)


def test_runner_decodes_timeout_byte_streams(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("research_synthesis.subprocess_runner")

    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(
            ["validator"],
            1,
            output=b"partial output",
            stderr=b"partial error",
        )

    monkeypatch.setattr(module.subprocess, "run", timeout)

    evidence = module.run_command(["validator"], tmp_path, 1)

    assert evidence.status == "timeout"
    assert evidence.stdout == "partial output"
    assert evidence.stderr == "partial error"
