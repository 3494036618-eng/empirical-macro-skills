"""Prepare and remove installer-managed Skill runtimes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

RUNTIME_MARKER = ".empirical-macro-runtime-managed"
RUNTIME_MARKER_CONTENT = "managed-by=empirical-macro-installer\n"


def runtime_root(skill_root: Path) -> Path:
    return skill_root / ".venv"


def runtime_python(skill_root: Path) -> Path:
    if os.name == "nt":
        return runtime_root(skill_root) / "Scripts" / "python.exe"
    return runtime_root(skill_root) / "bin" / "python"


def managed_runtime(skill_root: Path) -> bool:
    marker = runtime_root(skill_root) / RUNTIME_MARKER
    return (
        marker.is_file()
        and marker.read_text(encoding="utf-8") == RUNTIME_MARKER_CONTENT
    )


def inside_managed_runtime(
    path: Path,
    target_root: Path,
    skills: Iterable[str],
) -> bool:
    try:
        relative = path.relative_to(target_root)
    except ValueError:
        return False
    if len(relative.parts) < 3 or relative.parts[1] != ".venv":
        return False
    skill = relative.parts[0]
    return skill in set(skills) and managed_runtime(target_root / skill)


def prepare_runtime(skill_root: Path) -> Path:
    if not (skill_root / "pyproject.toml").is_file():
        return Path(sys.executable)
    if not (skill_root / "uv.lock").is_file():
        raise ValueError(f"runtime lock missing: {skill_root.name}")
    uv = shutil.which("uv")
    if uv is None:
        raise ValueError("uv is required to install Skill runtime dependencies")
    environment = dict(os.environ)
    environment["UV_PROJECT_ENVIRONMENT"] = str(runtime_root(skill_root))
    completed = subprocess.run(  # noqa: S603
        [
            uv,
            "sync",
            "--project",
            str(skill_root),
            "--locked",
            "--no-dev",
            "--no-editable",
        ],
        cwd=skill_root,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise ValueError(
            f"runtime dependency installation failed: {skill_root.name}{suffix}"
        )
    python = runtime_python(skill_root)
    if not python.is_file():
        raise ValueError(f"runtime Python missing: {skill_root.name}")
    (runtime_root(skill_root) / RUNTIME_MARKER).write_text(
        RUNTIME_MARKER_CONTENT,
        encoding="utf-8",
    )
    return python


def run_quick_validators(staging: Path, skills: Iterable[str]) -> None:
    for skill in skills:
        skill_root = staging / skill
        script = skill_root / "scripts" / "quick_validate.py"
        if not script.is_file():
            raise ValueError(f"quick validator missing: {skill}")
        python = prepare_runtime(skill_root)
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        completed = subprocess.run(  # noqa: S603
            [str(python), str(script)],
            cwd=skill_root,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"quick validator returned invalid JSON: {skill}"
            ) from error
        if (
            completed.returncode != 0
            or not isinstance(result, dict)
            or result.get("valid") is not True
        ):
            raise ValueError(f"quick validator failed: {skill}")


def remove_managed_runtimes(
    target_root: Path,
    skills: Iterable[str],
    *,
    dry_run: bool,
) -> list[str]:
    removed: list[str] = []
    for skill in skills:
        skill_root = target_root / skill
        runtime = runtime_root(skill_root)
        if not runtime.is_dir() or not managed_runtime(skill_root):
            continue
        removed.append(runtime.relative_to(target_root).as_posix())
        if not dry_run:
            shutil.rmtree(runtime)
    return removed
