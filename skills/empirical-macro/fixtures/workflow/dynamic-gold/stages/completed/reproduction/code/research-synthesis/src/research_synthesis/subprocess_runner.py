"""以 argv 方式执行上游公共 validator。"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from research_synthesis.models import ValidationEvidence


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def run_command(
    argv: list[str],
    cwd: Path,
    timeout_seconds: float,
) -> ValidationEvidence:
    """执行 argv 并把所有终止状态转换为结构化证据。"""
    if not argv or any(not isinstance(item, str) or not item for item in argv):
        raise ValueError("validator_argv_invalid")
    environment = os.environ.copy()
    environment.pop("VIRTUAL_ENV", None)
    started = time.monotonic()
    try:
        run = subprocess.run(  # noqa: S603
            argv,
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return ValidationEvidence(
            status="timeout",
            returncode=None,
            stdout=_text(exc.stdout),
            stderr=_text(exc.stderr),
            duration_seconds=time.monotonic() - started,
            issue_codes=("validator_timeout",),
        )
    status = "success" if run.returncode == 0 else "failed"
    issues = () if status == "success" else ("validator_nonzero_exit",)
    return ValidationEvidence(
        status=status,
        returncode=run.returncode,
        stdout=run.stdout,
        stderr=run.stderr,
        duration_seconds=time.monotonic() - started,
        issue_codes=issues,
    )
