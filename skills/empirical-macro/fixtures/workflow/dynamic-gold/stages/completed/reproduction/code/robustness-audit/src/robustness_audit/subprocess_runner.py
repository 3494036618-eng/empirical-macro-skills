"""Run adapter commands with closed stdin and process-group timeouts."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


def run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: float,
) -> CommandResult:
    started = time.monotonic()
    environment = os.environ.copy()
    environment.pop("VIRTUAL_ENV", None)
    # Commands are fixed argument arrays supplied by an adapter; no shell is used.
    process = subprocess.Popen(  # noqa: S603
        command,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(
            command,
            timeout_seconds,
            output=stdout,
            stderr=stderr,
        ) from exc
    return CommandResult(
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=round(time.monotonic() - started, 6),
    )
