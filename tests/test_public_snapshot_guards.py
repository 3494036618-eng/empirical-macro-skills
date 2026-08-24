from __future__ import annotations

import shutil
from pathlib import Path

from empirical_macro.public_snapshot import validate_public_snapshot

ROOT = Path(__file__).resolve().parents[1]


def _snapshot(tmp_path: Path) -> Path:
    snapshot = tmp_path / "public-snapshot"
    shutil.copytree(
        ROOT,
        snapshot,
        ignore=shutil.ignore_patterns(
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".venv",
            "__pycache__",
            "*.pyc",
        ),
    )
    return snapshot


def test_public_snapshot_rejects_internal_platform_evidence(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    evidence = snapshot / "platform-hotfix"
    evidence.mkdir()
    (evidence / "issue.txt").write_text("internal reproduction", encoding="utf-8")

    report = validate_public_snapshot(snapshot)

    assert report["valid"] is False
    assert "forbidden_public_path" in report["issue_codes"]
