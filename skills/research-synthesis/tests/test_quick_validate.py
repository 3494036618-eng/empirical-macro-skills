from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.factories import PROJECT_ROOT, ROOT, real_request


def test_run_and_validate_cli_round_trip(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(real_request(), ensure_ascii=False),
        encoding="utf-8",
    )
    output = tmp_path / "package"
    run = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/run_research_synthesis.py",
            "--request-json",
            str(request_path),
            "--adapter-capabilities-json",
            str(ROOT / "configs" / "local-upstream-adapters.json"),
            "--project-root",
            str(PROJECT_ROOT),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    validation = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/validate_bundle.py",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["execution_status"] == "success"
    assert validation.returncode == 0, validation.stderr
    assert json.loads(validation.stdout) == {"valid": True, "errors": []}


def test_quick_validate_reports_valid_structure() -> None:
    run = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/quick_validate.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(run.stdout)

    assert run.returncode == 0, run.stderr
    assert report["valid"] is True
    assert report["schema_count"] == 9
    assert report["primary_output"] == "research-report.md"
