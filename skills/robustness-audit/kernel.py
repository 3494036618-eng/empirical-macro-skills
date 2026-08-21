"""Optional OpenAI4S sidecar for declared robustness audits."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def requirements() -> dict[str, list[str]]:
    return {
        "imports": ["jsonschema", "matplotlib", "numpy", "pandas"],
        "pip": [
            "jsonschema==4.26.0",
            "matplotlib==3.10.9",
            "numpy==2.3.5",
            "pandas==2.3.3",
        ],
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
    audit_request: dict[str, object],
    audit_plan: dict[str, object],
    handoff: dict[str, object],
    *,
    baseline_bundle: str,
    input_paths: dict[str, str],
    adapter_capability: dict[str, object],
    adapter_root: str,
    output_dir: str,
) -> dict[str, object]:
    from robustness_audit.pipeline import run_robustness_audit

    resolved_inputs = {
        name: _workspace_path(path, must_exist=True)
        for name, path in input_paths.items()
    }
    return run_robustness_audit(
        audit_request,
        audit_plan,
        handoff,
        _workspace_path(baseline_bundle, must_exist=True),
        resolved_inputs,
        adapter_capability,
        _workspace_path(adapter_root, must_exist=True),
        _workspace_path(output_dir),
    )
