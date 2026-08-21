"""Optional OpenAI4S sidecar for deterministic suite routing."""

from __future__ import annotations

import sys
from pathlib import Path
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
