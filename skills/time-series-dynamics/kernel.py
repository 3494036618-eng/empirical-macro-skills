"""Optional OpenAI4S sidecar for dynamic macro estimation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def requirements() -> dict[str, list[str]]:
    return {
        "imports": [
            "jsonschema",
            "matplotlib",
            "numpy",
            "pandas",
            "statsmodels",
        ],
        "pip": [
            "jsonschema==4.26.0",
            "matplotlib==3.10.9",
            "numpy==2.3.5",
            "pandas==2.3.3",
            "statsmodels==0.14.6",
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


def _require_dependencies() -> None:
    required = tuple(requirements()["imports"])
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError("dependency_missing: " + ", ".join(missing))


def run(
    request: dict[str, object],
    research_plan: dict[str, object],
    macro_results: list[dict[str, object]],
    *,
    data_path: str,
    output_dir: str,
    shock_artifact: dict[str, object] | None = None,
) -> dict[str, object]:
    _require_dependencies()
    from time_series_dynamics.pipeline import run_time_series_dynamics

    return run_time_series_dynamics(
        request,
        research_plan,
        macro_results,
        _workspace_path(data_path, must_exist=True),
        _workspace_path(output_dir),
        shock_artifact,
    )
