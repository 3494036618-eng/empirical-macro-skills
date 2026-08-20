from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "robustness_audit"
FORBIDDEN = {"research_design", "macro_data", "time_series_dynamics"}


def test_package_and_required_boundaries_exist() -> None:
    spec = importlib.util.find_spec("robustness_audit")
    assert spec is not None
    package = importlib.import_module("robustness_audit")
    assert package.__name__ == "robustness_audit"
    assert (ROOT / "SKILL.md").is_file()
    assert (SOURCE / "py.typed").is_file()


def test_production_files_stay_small_and_do_not_import_skill_internals() -> None:
    files = sorted(SOURCE.glob("*.py"))
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 400
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.end_lineno is not None
                assert node.end_lineno - node.lineno + 1 <= 80
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".", 1)[0] not in FORBIDDEN
