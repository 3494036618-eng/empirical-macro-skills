from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import cast

import pytest

from tests.helpers import load_intent, load_optional_state

ROOT = Path(__file__).resolve().parents[1]
GOLD_CASES = cast(
    list[dict[str, object]],
    json.loads(
        (ROOT / "fixtures" / "routing" / "gold-cases.json").read_text(
            encoding="utf-8"
        )
    ),
)


def test_routing_gold_distribution_and_prompt_independence() -> None:
    """Break caught: Gold coverage shrinks or prompts name the desired Skill."""
    assert len(GOLD_CASES) == 65
    assert Counter(case["category"] for case in GOLD_CASES) == {
        "vague_research_idea": 10,
        "data_preparation": 10,
        "supported_dynamic": 10,
        "robustness": 5,
        "final_report": 5,
        "unsupported_method": 10,
        "out_of_scope": 10,
        "resume": 5,
    }
    assert all("$" not in cast(str, case["prompt"]) for case in GOLD_CASES)


@pytest.mark.parametrize(
    "case",
    GOLD_CASES,
    ids=[cast(str, case["case_id"]) for case in GOLD_CASES],
)
def test_routing_gold(case: dict[str, object]) -> None:
    """Break caught: deterministic routing differs from the frozen Gold."""
    from empirical_macro.router import route_intent

    intent = load_intent(cast(dict[str, object], case["intent"]))
    decision = route_intent(intent, load_optional_state(case))
    assert decision.action == case["expected_action"]
    assert decision.target_skill == case["expected_target_skill"]
    assert decision.user_message == case["expected_user_message"]
