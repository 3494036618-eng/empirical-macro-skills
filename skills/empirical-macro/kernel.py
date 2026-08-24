"""Optional OpenAI4S sidecar for deterministic suite routing."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def requirements() -> dict[str, list[str]]:
    return {
        "imports": ["jsonschema"],
        "pip": ["jsonschema>=4.26,<5"],
    }


def _workspace_path(value: str) -> Path:
    supplied = Path(value)
    if not value or supplied.is_absolute() or ".." in supplied.parts:
        raise ValueError("path must be workspace-relative")
    workspace = Path.cwd().resolve()
    resolved = (workspace / supplied).resolve()
    if resolved != workspace and workspace not in resolved.parents:
        raise ValueError("path must be workspace-relative")
    return resolved


def _load_research_design_kernel() -> ModuleType:
    try:
        return importlib.import_module("research-design.kernel")
    except ModuleNotFoundError as error:
        path = ROOT.parent / "research-design" / "kernel.py"
        spec = importlib.util.spec_from_file_location(
            "empirical_macro_research_design_kernel",
            path,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load {path}") from error
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def run(
    user_question: str,
    *,
    method_family: str,
    method_inputs: dict[str, object],
    output_dir: str,
) -> dict[str, object]:
    """Run the first controlled stage of the empirical-macro workflow."""
    from empirical_macro.sidecar_workflow import run_design_stage

    output_root = _workspace_path(output_dir)
    module = _load_research_design_kernel()
    raw_design_runner = getattr(module, "run_dynamic_question", None)
    if not callable(raw_design_runner):
        raise RuntimeError("research-design dynamic runner is unavailable")

    workspace = Path.cwd().resolve()

    def design_runner(
        design_question: str,
        **arguments: object,
    ) -> dict[str, object]:
        supplied = Path(str(arguments["output_dir"])).resolve()
        arguments["output_dir"] = supplied.relative_to(workspace).as_posix()
        return cast(
            Callable[..., dict[str, object]],
            raw_design_runner,
        )(design_question, **arguments)

    return run_design_stage(
        question=user_question,
        method_family=method_family,
        method_inputs=method_inputs,
        output_root=output_root,
        project_root=workspace,
        design_runner=design_runner,
    )


def route(intent: dict[str, object]) -> dict[str, object]:
    from empirical_macro.contracts import validate_document
    from empirical_macro.models import ResearchIntent
    from empirical_macro.router import route_intent

    validate_document("research_intent", intent)
    candidate = ResearchIntent(
        domain=cast(str, intent["domain"]),
        request_kind=cast(str, intent["request_kind"]),
        method_family=cast(str | None, intent["method_family"]),
        has_research_plan=cast(bool, intent["has_research_plan"]),
        has_macro_data_bundle=cast(bool, intent["has_macro_data_bundle"]),
        has_estimator_bundle=cast(bool, intent["has_estimator_bundle"]),
        has_robustness_bundle=cast(bool, intent["has_robustness_bundle"]),
        has_workflow_state=cast(bool, intent["has_workflow_state"]),
    )
    decision = route_intent(candidate)
    result: dict[str, object] = {
        "schema_version": "0.1.0-beta",
        "action": decision.action,
        "target_skill": decision.target_skill,
        "issue_codes": list(decision.issue_codes),
        "user_message": decision.user_message,
    }
    validate_document("route_decision", result)
    return result


def decide_after_stage(
    route_decision: dict[str, object],
    stage_result: dict[str, object],
) -> dict[str, object]:
    from empirical_macro.stage_result_gate import (
        decide_after_stage as decide,
    )

    return decide(route_decision, stage_result)
