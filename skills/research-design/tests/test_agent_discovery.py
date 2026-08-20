from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    # The test controls both the interpreter and every script argument.
    return subprocess.run(  # noqa: S603
        [sys.executable, *arguments],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_requires_intake_request_macro_schema_and_output() -> None:
    completed = _run("scripts/run_research_design.py")

    assert completed.returncode == 2
    assert "--intake-json" in completed.stderr


def test_three_agent_links_resolve_to_one_skill(
    agent_skill_paths: list[Path],
) -> None:
    targets = [path.resolve() for path in agent_skill_paths]

    assert len(set(targets)) == 1
    assert targets[0] == PROJECT_ROOT
    assert all((path / "SKILL.md").is_file() for path in agent_skill_paths)


def test_quick_validate_checks_skill_structure_and_contracts() -> None:
    completed = _run("scripts/quick_validate.py")

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["valid"] is True
    assert report["schema_count"] == 7
    assert report["secret_findings"] == []
    assert report["behavior_pressure_tests"] == "passed_2026-08-16"


def test_cli_compiles_offline_annual_panel_bundle(
    tmp_path: Path,
    macro_schema_path: Path,
) -> None:
    fixtures = PROJECT_ROOT / "fixtures" / "gold"
    output = tmp_path / "annual-panel"

    completed = _run(
        "scripts/run_research_design.py",
        "--intake-json",
        str(fixtures / "annual-panel-intake.json"),
        "--request-json",
        str(fixtures / "annual-panel-request.json"),
        "--macro-schema",
        str(macro_schema_path),
        "--macro-request-json",
        str(fixtures / "annual-panel-macro-request.json"),
        "--output",
        str(output),
    )

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["design_readiness"] == "ready_for_data"
    assert (output / "research-design-run-manifest.json").is_file()
