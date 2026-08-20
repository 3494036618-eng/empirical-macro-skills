from __future__ import annotations

import ast
from importlib import resources
from pathlib import Path

import research_design

SRC = Path(__file__).parents[1] / "src" / "research_design"


def test_installed_package_exposes_typing_metadata() -> None:
    package_root = resources.files(research_design)
    assert package_root.joinpath("py.typed").is_file()


def test_production_code_does_not_import_macro_data() -> None:
    assert SRC.exists()
    for path in SRC.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert not {name for name in imports if name.startswith("macro_data")}


def test_new_functions_remain_bounded() -> None:
    assert SRC.exists()
    for path in SRC.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.end_lineno is not None
                assert node.end_lineno - node.lineno + 1 <= 80


def test_new_modules_remain_bounded() -> None:
    assert SRC.exists()
    for path in SRC.glob("*.py"):
        assert len(path.read_text(encoding="utf-8").splitlines()) <= 400
