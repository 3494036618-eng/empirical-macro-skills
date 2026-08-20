from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from robustness_audit.subprocess_runner import run_command


def test_runner_closes_stdin_and_returns_output() -> None:
    result = run_command(
        [sys.executable, "-c", "import sys; print(sys.stdin.read())"],
        cwd=Path.cwd(),
        timeout_seconds=2,
    )

    assert result.returncode == 0
    assert result.stdout == "\n"
    assert result.stderr == ""


def test_runner_does_not_leak_parent_virtual_environment() -> None:
    result = run_command(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('VIRTUAL_ENV'))",
        ],
        cwd=Path.cwd(),
        timeout_seconds=2,
    )

    assert result.stdout == "None\n"


def test_runner_kills_process_group_on_timeout() -> None:
    child = (
        "import subprocess,sys,time;"
        "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
        "time.sleep(30)"
    )
    started = time.monotonic()

    with pytest.raises(subprocess.TimeoutExpired):
        run_command(
            [sys.executable, "-c", child],
            cwd=Path.cwd(),
            timeout_seconds=0.2,
        )

    assert time.monotonic() - started < 2
