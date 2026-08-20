from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from empirical_macro.contracts import validate_document
from empirical_macro.models import ResearchIntent


def load_research_intent(path: Path) -> ResearchIntent:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("research intent must be an object")
    intent = cast(dict[str, object], document)
    validate_document("research_intent", intent)
    return ResearchIntent(
        domain=cast(str, intent["domain"]),
        request_kind=cast(str, intent["request_kind"]),
        method_family=cast(str | None, intent["method_family"]),
        has_research_plan=cast(bool, intent["has_research_plan"]),
        has_macro_data_bundle=cast(bool, intent["has_macro_data_bundle"]),
        has_estimator_bundle=cast(bool, intent["has_estimator_bundle"]),
        has_robustness_bundle=cast(bool, intent["has_robustness_bundle"]),
        has_workflow_state=cast(bool, intent["has_workflow_state"]),
    )
