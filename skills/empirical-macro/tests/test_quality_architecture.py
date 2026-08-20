from __future__ import annotations

import ast
from pathlib import Path

from tests.helpers import ROOT


def production_files() -> list[Path]:
    return sorted((ROOT / "src" / "empirical_macro").glob("*.py")) + sorted(
        (ROOT / "scripts").glob("*.py")
    )


def test_production_files_and_functions_stay_within_frozen_limits() -> None:
    """Break caught: orchestration logic grows into an unreviewable module."""
    for path in production_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) < 400, path
        tree = ast.parse("\n".join(lines), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.end_lineno is not None
                assert node.end_lineno - node.lineno + 1 < 80, (
                    path,
                    node.name,
                )


def test_total_router_never_imports_atomic_private_modules() -> None:
    """Break caught: the total Skill couples to an atomic implementation."""
    forbidden = {
        "macro_data",
        "research_design",
        "time_series_dynamics",
        "robustness_audit",
        "research_synthesis",
    }
    for path in production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert forbidden.isdisjoint(alias.name.split(".")[0] for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden


def test_production_sources_contain_no_private_workspace_path() -> None:
    """Break caught: a public package embeds a developer machine path."""
    for path in production_files():
        text = path.read_text(encoding="utf-8")
        assert "/" + "Users/" not in text, path
        assert "/" + "home/" not in text, path
        assert "/" + "private/var/" not in text, path
