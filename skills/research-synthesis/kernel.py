"""Optional OpenAI4S sidecar for final research-package synthesis."""

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
        "pip": ["jsonschema==4.26.0"],
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
    request: dict[str, object],
    adapter_capabilities: dict[str, object],
    *,
    project_root: str,
    output_dir: str,
) -> dict[str, object]:
    from research_synthesis.pipeline import run_research_synthesis

    return run_research_synthesis(
        request,
        adapter_capabilities,
        _workspace_path(project_root, must_exist=True),
        _workspace_path(output_dir),
    )
