from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = ROOT / "package.json"
CLI_PATH = ROOT / "bin" / "empirical-macro-skills.mjs"


def _release_scanner():
    scanner_path = ROOT / "scripts" / "scan_public_release.py"
    spec = importlib.util.spec_from_file_location("scan_public_release", scanner_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_package_exposes_one_cli() -> None:
    assert PACKAGE_PATH.is_file()
    package = json.loads(PACKAGE_PATH.read_text("utf-8"))
    plugin = json.loads((ROOT / "plugin.json").read_text("utf-8"))

    assert package["name"] == "empirical-macro-skills"
    assert package["version"] == "0.2.0-beta"
    assert package["version"] == plugin["version"]
    assert package["private"] is False
    assert package["bin"] == {
        "empirical-macro-skills": "bin/empirical-macro-skills.mjs"
    }
    assert {"bin", "scripts", "skills"}.issubset(package["files"])
    assert package["engines"]["node"] == ">=20"


def test_cli_help_lists_supported_hosts() -> None:
    assert CLI_PATH.is_file()

    completed = subprocess.run(
        ["node", str(CLI_PATH), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--host" in completed.stdout
    for host in ("generic", "trae", "codex", "claude-code", "openai4s"):
        assert host in completed.stdout


def test_cli_generic_dry_run_delegates_to_the_python_installer(
    tmp_path: Path,
) -> None:
    assert CLI_PATH.is_file()
    target = tmp_path / "skills"
    environment = {
        **os.environ,
        "UV_PROJECT_ENVIRONMENT": str(tmp_path / "installer-venv"),
    }

    completed = subprocess.run(
        [
            "node",
            str(CLI_PATH),
            "--host",
            "generic",
            "--target-root",
            str(target),
            "--dry-run",
            "--yes",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout.strip().splitlines()[-1])
    assert report["dry_run"] is True
    assert report["host"] == "generic"
    assert len(report["installed_skills"]) == 6
    assert not target.exists()


def test_cli_openai4s_dry_run_selects_the_versioned_host_path(
    tmp_path: Path,
) -> None:
    environment = {
        **os.environ,
        "UV_PROJECT_ENVIRONMENT": str(tmp_path / "installer-venv"),
    }

    completed = subprocess.run(
        [
            "node",
            str(CLI_PATH),
            "--host",
            "openai4s",
            "--dry-run",
            "--yes",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout.strip().splitlines()[-1])
    assert report["valid"] is True
    assert report["host"] == "openai4s"
    assert report["scope"] == "personal"
    assert len(report["skills"]) == 6


def test_npm_package_excludes_runtime_caches_and_private_evidence() -> None:
    completed = subprocess.run(
        ["npm", "pack", "--dry-run", "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    package = json.loads(completed.stdout)[0]
    paths = {item["path"] for item in package["files"]}
    assert "skills/empirical-macro/SKILL.md" in paths
    assert "skills/empirical-macro/kernel.py" in paths
    assert not any("__pycache__" in path for path in paths)
    assert not any(path.endswith((".pyc", ".pyo")) for path in paths)
    assert not any("platform-hotfix" in path for path in paths)
    assert not any("openai4s_local_adapter" in path for path in paths)


def test_release_scanner_allows_the_npm_entry_files(tmp_path: Path) -> None:
    scanner = _release_scanner()
    (tmp_path / ".npmignore").write_text("**/__pycache__/**\n", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "empirical-macro-skills.mjs").write_text(
        "#!/usr/bin/env node\n",
        encoding="utf-8",
    )

    assert scanner.scan(tmp_path) == []
