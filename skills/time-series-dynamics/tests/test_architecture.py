from __future__ import annotations

import ast
from pathlib import Path

import time_series_dynamics

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src" / "time_series_dynamics"
FORBIDDEN_IMPORTS = {"macro_data", "research_design"}


def _production_files() -> list[Path]:
    return sorted(SOURCE_ROOT.glob("*.py"))


def _function_lengths(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        (node.name, node.end_lineno - node.lineno + 1)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.end_lineno is not None
    ]


def _top_level_import(module: str | None) -> str | None:
    return module.split(".", maxsplit=1)[0] if module else None


def test_package_scaffold_is_installable_shape() -> None:
    assert time_series_dynamics.__name__ == "time_series_dynamics"
    assert (PROJECT_ROOT / "pyproject.toml").is_file()
    assert (SOURCE_ROOT / "__init__.py").is_file()
    assert (SOURCE_ROOT / "py.typed").is_file()


def test_production_files_stay_within_size_limits() -> None:
    files = _production_files()
    assert files
    for path in files:
        assert len(path.read_text(encoding="utf-8").splitlines()) <= 400, path
        for name, length in _function_lengths(path):
            assert length <= 80, f"{path}:{name} has {length} lines"


def test_package_does_not_import_upstream_internals() -> None:
    for path in _production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            _top_level_import(node.module)
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        imports.update(
            _top_level_import(alias.name)
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert imports.isdisjoint(FORBIDDEN_IMPORTS), path
