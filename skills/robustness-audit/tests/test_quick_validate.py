from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_quick_validate_checks_current_skill_structure_and_contracts() -> None:
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/quick_validate.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    report = json.loads(completed.stdout)
    assert report["valid"] is True
    assert report["schema_count"] == 6
    assert report["missing_files"] == []
    assert report["secret_findings"] == []
    assert report["errors"] == []
