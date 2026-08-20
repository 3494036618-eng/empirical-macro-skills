from __future__ import annotations

import hashlib
import importlib.util
import sys
from importlib import import_module
from pathlib import Path

import pytest


def test_reproduction_and_export_modules_exist() -> None:
    for module in (
        "bundle_semantics",
        "exporter",
        "reproduction",
        "reproduction_runner",
    ):
        assert importlib.util.find_spec(f"research_synthesis.{module}") is not None


def test_reproduction_runner_verifies_expected_outputs(tmp_path: Path) -> None:
    module = import_module("research_synthesis.reproduction_runner")
    assert hasattr(module, "run_reproduction")
    source = tmp_path / "source.txt"
    source.write_text("verified\n", encoding="utf-8")
    expected = hashlib.sha256(b"verified\n").hexdigest()
    manifest = {
        "steps": [
            {
                "step_id": "copy-source",
                "argv": [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path;"
                        "Path('observed.txt').write_bytes("
                        "Path('source.txt').read_bytes())"
                    ),
                ],
                "working_directory": ".",
                "expected_exit_code": 0,
            }
        ],
        "expected_outputs": {
            "observed.txt": f"sha256:{expected}",
        },
    }

    result = module.run_reproduction(manifest, tmp_path, 30)

    assert result["status"] == "verified"
    assert result["output_mismatches"] == []


def test_reproduction_runner_reports_digest_mismatch(tmp_path: Path) -> None:
    module = import_module("research_synthesis.reproduction_runner")
    assert hasattr(module, "run_reproduction")
    manifest = {
        "steps": [
            {
                "step_id": "write-output",
                "argv": [
                    sys.executable,
                    "-c",
                    "from pathlib import Path;Path('out.txt').write_text('x')",
                ],
                "working_directory": ".",
                "expected_exit_code": 0,
            }
        ],
        "expected_outputs": {
            "out.txt": "sha256:" + "0" * 64,
        },
    }

    result = module.run_reproduction(manifest, tmp_path, 30)

    assert result["status"] == "failed"
    assert result["output_mismatches"] == ["out.txt"]


@pytest.mark.parametrize(
    ("relative", "issue"),
    [
        (None, "reproduction_working_directory_invalid"),
        ("../outside", "reproduction_working_directory_unsafe"),
        ("missing", "reproduction_working_directory_missing"),
    ],
)
def test_reproduction_runner_rejects_unsafe_working_directories(
    tmp_path: Path,
    relative: object,
    issue: str,
) -> None:
    module = import_module("research_synthesis.reproduction_runner")

    with pytest.raises(ValueError, match=issue):
        module._working_directory(tmp_path, relative)


def test_reproduction_runner_rejects_symlink_escape(tmp_path: Path) -> None:
    module = import_module("research_synthesis.reproduction_runner")
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(
        ValueError,
        match="reproduction_working_directory_unsafe",
    ):
        module._working_directory(tmp_path, "escape")


def test_reproduction_runner_structures_failed_step(tmp_path: Path) -> None:
    module = import_module("research_synthesis.reproduction_runner")
    manifest = {
        "steps": [
            {
                "step_id": "fail-step",
                "argv": [sys.executable, "-c", "raise SystemExit(3)"],
                "working_directory": ".",
                "expected_exit_code": 0,
            }
        ],
        "expected_outputs": {"unused.txt": "sha256:" + "0" * 64},
    }

    result = module.run_reproduction(manifest, tmp_path, 30)

    assert result["status"] == "failed"
    assert result["output_mismatches"] == []
    assert result["records"][0]["returncode"] == 3
