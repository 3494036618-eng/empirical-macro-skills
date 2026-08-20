from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "research_synthesis"
FORBIDDEN = {
    "macro_data",
    "research_design",
    "robustness_audit",
    "time_series_dynamics",
}


def test_package_contract_files_exist() -> None:
    assert importlib.util.find_spec("research_synthesis") is not None
    assert (ROOT / "SKILL.md").is_file()
    assert (SOURCE / "py.typed").is_file()


def test_production_modules_stay_bounded_and_isolated() -> None:
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
