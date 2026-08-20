from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from macro_data.contracts import validate_document
from macro_data.metadata_gate import metadata_issues

EXAMPLES = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic" / "schema-examples"


def _load(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def _documented_candidate() -> dict[str, Any]:
    return {
        "unit": {"status": "source_documented"},
        "seasonal_adjustment": {"status": "source_documented"},
        "definition": {"status": "source_provided"},
        "license": {"use_status": "allowed", "allows_requested_use": True},
        "release_date": {"status": "unresolved"},
        "vintage": {"status": "unresolved"},
    }


def test_dynamic_response_request_accepts_association_and_shock_roles() -> None:
    association = _load("request.valid.json")
    association["research_use"] = "dynamic_response"
    association["concepts"] = [
        {
            "concept": "CPI 对数水平",
            "role": "outcome",
            "definition_constraints": ["季度"],
        },
        {
            "concept": "政策利率变化",
            "role": "exposure",
            "definition_constraints": ["仅作条件关联"],
        },
        {
            "concept": "实际 GDP 增长",
            "role": "control",
            "definition_constraints": ["季度"],
        },
    ]
    causal = copy.deepcopy(association)
    causal["concepts"][1]["role"] = "shock"

    validate_document("request", association)
    validate_document("request", causal)


def test_dynamic_response_result_is_a_supported_research_use() -> None:
    result = _load("result.valid.json")
    result.update(
        {
            "research_use": "dynamic_response",
            "result_id": "macro-result-0123456789abcdef",
            "frequency": "Q",
            "observation_period": {"start": "1985Q1", "end": "2007Q4"},
            "source_checksum": "a" * 64,
        }
    )

    validate_document("result", result)


def test_dynamic_response_does_not_require_historical_vintage_by_default() -> None:
    request = {
        "research_use": "dynamic_response",
        "release_or_vintage": {"mode": "latest", "value": None},
    }

    issues = metadata_issues(request, [_documented_candidate()])

    assert "release_date_required" not in issues
    assert "vintage_required" not in issues
