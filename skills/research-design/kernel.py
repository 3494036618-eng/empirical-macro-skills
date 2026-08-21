"""Optional OpenAI4S sidecar for research-design execution."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def requirements() -> dict[str, list[str]]:
    return {
        "imports": ["jsonschema"],
        "pip": ["jsonschema>=4.26,<5"],
    }


def _workspace_path(value: str, *, must_exist: bool = False) -> Path:
    supplied = Path(value)
    if not value or supplied.is_absolute() or ".." in supplied.parts:
        raise ValueError("path must be workspace-relative")
    workspace = Path.cwd().resolve()
    resolved = (workspace / supplied).resolve()
    if resolved != workspace and workspace not in resolved.parents:
        raise ValueError("path must be workspace-relative")
    if must_exist and not resolved.exists():
        raise FileNotFoundError(resolved)
    return resolved


def run(
    intake: dict[str, object],
    request: dict[str, object],
    *,
    output_dir: str,
    macro_request: dict[str, object] | None = None,
) -> dict[str, object]:
    from research_design.pipeline import run_research_design

    schema = ROOT / "assets" / "macro-data-request.schema.json"
    if not schema.is_file():
        sibling = ROOT.parent / "macro-data" / "schemas" / "macro-data-request.schema.json"
        schema = sibling
    return run_research_design(
        intake,
        request,
        _workspace_path(output_dir),
        schema,
        macro_request_document=macro_request,
    )
