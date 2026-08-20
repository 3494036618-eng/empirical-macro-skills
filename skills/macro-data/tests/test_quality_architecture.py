from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOTS = (ROOT / "src" / "macro_data", ROOT / "scripts")


def _production_files() -> list[Path]:
    return sorted(
        path
        for root in PRODUCTION_ROOTS
        for path in root.rglob("*.py")
    )


def test_production_files_are_under_400_lines() -> None:
    violations = {
        str(path.relative_to(ROOT)): len(
            path.read_text(encoding="utf-8").splitlines()
        )
        for path in _production_files()
        if len(path.read_text(encoding="utf-8").splitlines()) >= 400
    }

    assert violations == {}


def test_production_functions_are_under_80_lines() -> None:
    violations = {}
    for path in _production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = node.end_lineno or node.lineno
                length = end - node.lineno + 1
                if length >= 80:
                    violations[f"{path.relative_to(ROOT)}:{node.name}"] = length

    assert violations == {}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_completion_respects_module_ownership_boundaries() -> None:
    legacy_pipeline = ROOT / "src" / "macro_data" / "pipeline.py"
    assert not any(
        module.startswith("macro_data.completion_")
        for module in _imported_modules(legacy_pipeline)
    )

    connector_root = ROOT / "src" / "macro_data" / "connectors"
    for path in connector_root.glob("*.py"):
        assert "macro_data.completion_assembler" not in _imported_modules(path)


def test_production_does_not_import_acceptance_artifacts() -> None:
    for path in _production_files():
        assert not any(
            "验收" in module or "acceptance" in module
            for module in _imported_modules(path)
        )


def test_unimplemented_imf_connector_is_not_present() -> None:
    connector_root = ROOT / "src" / "macro_data" / "connectors"
    assert not (connector_root / "imf.py").exists()
    assert not (connector_root / "imf_connector.py").exists()
