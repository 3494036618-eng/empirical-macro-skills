"""执行 reproduction manifest 中的 argv steps。"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from research_synthesis.identifiers import sha256_file
from research_synthesis.subprocess_runner import run_command


def _working_directory(package_root: Path, relative: object) -> Path:
    if not isinstance(relative, str):
        raise ValueError("reproduction_working_directory_invalid")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("reproduction_working_directory_unsafe")
    resolved = (package_root / path).resolve()
    try:
        resolved.relative_to(package_root.resolve())
    except ValueError as exc:
        raise ValueError("reproduction_working_directory_unsafe") from exc
    if not resolved.is_dir():
        raise ValueError("reproduction_working_directory_missing")
    return resolved


def run_reproduction(
    manifest: dict[str, object],
    package_root: Path,
    timeout_seconds: float,
) -> dict[str, object]:
    """执行复现 steps 并比较声明输出。"""
    records: list[dict[str, object]] = []
    steps = cast(list[dict[str, object]], manifest["steps"])
    for step in steps:
        cwd = _working_directory(
            package_root,
            step["working_directory"],
        )
        evidence = run_command(
            cast(list[str], step["argv"]),
            cwd,
            timeout_seconds,
        )
        records.append(
            {
                "step_id": step["step_id"],
                "status": evidence.status,
                "returncode": evidence.returncode,
                "duration_seconds": evidence.duration_seconds,
                "stdout": evidence.stdout,
                "stderr": evidence.stderr,
                "issue_codes": list(evidence.issue_codes),
            }
        )
        if evidence.status != "success":
            return {
                "status": "failed",
                "records": records,
                "output_mismatches": [],
            }
    expected = cast(dict[str, str], manifest["expected_outputs"])
    mismatches = []
    for relative, checksum in expected.items():
        path = package_root / relative
        observed = f"sha256:{sha256_file(path)}" if path.is_file() else None
        if observed != checksum:
            mismatches.append(relative)
    return {
        "status": "verified" if not mismatches else "failed",
        "records": records,
        "output_mismatches": sorted(mismatches),
    }
