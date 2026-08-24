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


def run_dynamic_question(
    question: str,
    *,
    outcome: str,
    policy_variable: str,
    entity: str,
    start: str,
    end: str,
    frequency: str,
    horizon: int,
    output_dir: str,
    intended_claim: str = "causal",
    shock_identification: str = "unresolved",
) -> dict[str, object]:
    """Compile a small dynamic input and run the full design validator."""
    from typing import cast

    from research_design.dynamic_entry import (
        Claim,
        ShockIdentification,
        build_dynamic_documents,
    )

    intake, request = build_dynamic_documents(
        question=question,
        outcome=outcome,
        policy_variable=policy_variable,
        entity=entity,
        start=start,
        end=end,
        frequency=frequency,
        horizon=horizon,
        intended_claim=cast(Claim, intended_claim),
        shock_identification=cast(
            ShockIdentification,
            shock_identification,
        ),
    )
    return run(
        intake,
        request,
        output_dir=output_dir,
    )
