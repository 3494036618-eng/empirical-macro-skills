"""Shared pytest fixtures for research-design."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest

CONTRACT_FIXTURES = Path(__file__).parents[1] / "fixtures" / "contracts"


def load_contract_fixture(name: str) -> dict[str, object]:
    document = json.loads((CONTRACT_FIXTURES / name).read_text(encoding="utf-8"))
    return cast(dict[str, object], document)


@pytest.fixture
def pending_intake_document() -> dict[str, object]:
    return copy.deepcopy(load_contract_fixture("intake.valid.json"))


@pytest.fixture
def valid_intake_document(
    pending_intake_document: dict[str, object],
) -> dict[str, object]:
    clarifications = pending_intake_document["clarifications"]
    assert isinstance(clarifications, list)
    clarification = clarifications[0]
    assert isinstance(clarification, dict)
    clarification["status"] = "answered"
    clarification["answer"] = "采用推荐的描述性候选。"
    pending_intake_document["status"] = "ready_to_compile"
    return pending_intake_document


@pytest.fixture
def valid_request_document() -> dict[str, object]:
    return copy.deepcopy(load_contract_fixture("request.valid.json"))


@pytest.fixture
def valid_macro_request_document() -> dict[str, object]:
    return copy.deepcopy(load_contract_fixture("macro-data-request.valid.json"))


@pytest.fixture
def macro_schema_path() -> Path:
    return (
        Path(__file__).parents[2]
        / "macro-data"
        / "schemas"
        / "macro-data-request.schema.json"
    )


@pytest.fixture
def agent_skill_paths() -> list[Path]:
    project_root = Path(__file__).parents[1]
    workspace = project_root.parents[2]
    return [
        workspace / ".trae" / "skills" / "research-design",
        workspace / ".agents" / "skills" / "research-design",
        workspace / ".claude" / "skills" / "research-design",
    ]


@pytest.fixture
def dynamic_plan() -> dict[str, object]:
    plan = copy.deepcopy(load_contract_fixture("research-plan.valid.json"))
    plan["research_family"] = "dynamic_shock_response"
    plan["intended_claim"] = "causal"
    plan["estimand"] = {
        "type": "dynamic_response",
        "outcome_variable_id": "output_growth",
        "treatment_or_shock_variable_id": "monetary_shock",
        "target_population": "采用通胀目标制的经济体",
        "comparison": "冲击前路径",
        "horizons": [0, 1, 2, 3, 4],
        "status": "specified",
    }
    return plan


@pytest.fixture
def policy_rate_level_request() -> dict[str, object]:
    return {
        "intended_claim": "causal",
        "variables": [
            {"variable_id": "output", "role": "outcome"},
            {"variable_id": "policy_rate", "role": "shock"},
        ],
        "intervention_or_shock": {
            "name": "政策利率原始变动",
            "timing_known": True,
            "assignment_mechanism": "observational",
        },
    }


@pytest.fixture
def causal_request() -> dict[str, object]:
    return {
        "request_id": "rd-request-cccccccccccccccc",
        "intended_claim": "causal",
        "variables": [
            {"variable_id": "employment", "role": "outcome"},
            {"variable_id": "policy", "role": "treatment"},
        ],
        "intervention_or_shock": {
            "name": "地区政策",
            "timing_known": True,
            "assignment_mechanism": "observational",
        },
        "comparison": "尚未接受政策的地区",
    }


@pytest.fixture
def causal_estimand() -> dict[str, object]:
    return {
        "type": "att",
        "outcome_variable_id": "employment",
        "treatment_or_shock_variable_id": "policy",
        "target_population": "受政策影响的地区",
        "comparison": "尚未接受政策的地区",
        "horizons": [],
        "status": "specified",
    }


@pytest.fixture
def latest_only_forecast_request() -> dict[str, object]:
    return {
        "intended_claim": "predictive",
        "forecast": {
            "target_variable_id": "gdp_growth",
            "horizons": [1],
            "forecast_origin_policy": "unresolved",
            "point_in_time_required": True,
            "target_vintage_policy": "latest",
            "temporal_split": "rolling",
            "baseline_model": "ar1",
            "loss_function": "rmse",
        },
    }
