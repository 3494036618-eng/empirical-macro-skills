"""Optional OpenAI4S sidecar for macro-data preparation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def requirements() -> dict[str, list[str]]:
    return {
        "imports": ["jsonschema", "pyarrow"],
        "pip": ["jsonschema>=4.26,<5", "pyarrow>=21,<22"],
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


def plan(request: dict[str, object]) -> dict[str, object]:
    from macro_data.contracts import validate_document
    from macro_data.datapro_batch_plan import (
        BatchPolicy,
        build_datapro_batch_plan,
    )
    from macro_data.observation_matrix import build_expected_matrix

    validate_document("request", request)
    matrix = build_expected_matrix(request)
    batches = build_datapro_batch_plan(
        request,
        BatchPolicy(
            maximum_periods={"M": 12, "Q": 8, "A": 10},
            maximum_calls=200,
        ),
    )
    return {
        "status": "dry_run",
        "planned_primary_provider": "datapro",
        "expected_observation_count": len(matrix.cells),
        "matrix_id": matrix.matrix_id,
        "batch_count": len(batches),
        "batches": [batch.as_document() for batch in batches],
    }


def run_with_datapro(
    host: object,
    request: dict[str, object],
    *,
    output_dir: str,
) -> dict[str, object]:
    from macro_data.openai4s_datapro import run_with_openai4s_datapro

    return run_with_openai4s_datapro(
        host,
        request,
        _workspace_path(output_dir),
    )


def validate(output_dir: str) -> dict[str, object]:
    from macro_data.completion_validation import validate_completion_bundle

    return validate_completion_bundle(
        _workspace_path(output_dir, must_exist=True)
    )
