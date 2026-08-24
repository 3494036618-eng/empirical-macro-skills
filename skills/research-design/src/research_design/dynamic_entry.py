"""Compile a small dynamic-research input into the full design contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from research_design.contracts import validate_document

Claim = Literal["causal", "associational"]
ShockIdentification = Literal[
    "unresolved",
    "narrative",
    "external_instrument",
    "statistical_innovation",
    "randomized",
]


def _identifier(prefix: str, *values: object) -> str:
    payload = json.dumps(values, ensure_ascii=True, separators=(",", ":"))
    return f"{prefix}-{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


def _provenance(field_path: str, evidence: str) -> dict[str, object]:
    return {
        "field_path": field_path,
        "source": "user_provided",
        "evidence_text": evidence,
        "confidence": "high",
    }


def _intake(
    *,
    question: str,
    intake_id: str,
    candidate_id: str,
    intended_claim: Claim,
    unresolved: list[str],
) -> dict[str, object]:
    return {
        "schema_version": "0.1.0-draft",
        "intake_id": intake_id,
        "raw_user_input": question,
        "input_maturity": "question_ready",
        "candidate_questions": [
            {
                "candidate_id": candidate_id,
                "research_question": question,
                "intended_claim_candidate": intended_claim,
                "research_family_candidate": "dynamic_shock_response",
                "plain_language_explanation": (
                    "使用 Local Projection 估计动态路径，并保持识别边界。"
                ),
                "risk_level": "high" if intended_claim == "causal" else "medium",
                "locked_user_fields": [
                    "research_question",
                    "outcome",
                    "policy_variable",
                    "entity",
                    "frequency",
                    "horizon",
                ],
                "unresolved_decisions": unresolved,
            }
        ],
        "recommended_candidate_id": candidate_id,
        "field_provenance": [
            _provenance("research_question", question),
        ],
        "clarifications": [],
        "safe_default": {
            "applied": False,
            "downgraded_to": "none",
            "reason": None,
        },
        "status": "ready_to_compile",
        "output_language": "zh-CN",
    }


def _variables(
    outcome: str,
    policy_variable: str,
    *,
    causal: bool,
) -> list[dict[str, object]]:
    return [
        {
            "variable_id": "outcome",
            "role": "outcome",
            "concept": outcome,
            "definition_constraints": [outcome],
        },
        {
            "variable_id": "policy_exposure",
            "role": "shock" if causal else "exposure",
            "concept": policy_variable,
            "definition_constraints": [
                (
                    "必须使用独立识别并审核通过的外生冲击序列"
                    if causal
                    else "仅解释为观察到的政策变化"
                )
            ],
        },
    ]


def _request_provenance(
    question: str,
    intended_claim: Claim,
    entity: str,
    start: str,
    end: str,
    frequency: str,
    *,
    causal: bool,
) -> list[dict[str, object]]:
    return [
        _provenance("research_question", question),
        _provenance("intended_claim", intended_claim),
        _provenance("target_population", entity),
        _provenance("unit_of_analysis", "country_time"),
        _provenance("time_scope", f"{start} to {end}, {frequency}"),
        _provenance("variables[0].role", "outcome"),
        _provenance("variables[1].role", "shock" if causal else "exposure"),
    ]


def _request(
    *,
    question: str,
    outcome: str,
    policy_variable: str,
    entity: str,
    start: str,
    end: str,
    frequency: str,
    horizon: int,
    intended_claim: Claim,
    shock_identification: ShockIdentification,
    intake_id: str,
    candidate_id: str,
) -> dict[str, object]:
    causal = intended_claim == "causal"
    identified = shock_identification != "unresolved"
    return {
        "schema_version": "0.1.0-draft",
        "source_intake_id": intake_id,
        "selected_candidate_id": candidate_id,
        "request_id": _identifier("rd-request", question, entity, frequency),
        "research_question": question,
        "input_maturity": "design_ready",
        "intended_claim": intended_claim,
        "preferred_design": "local_projection" if causal else "conditional_projection",
        "target_population": {
            "description": entity,
            "entity_types": ["country"],
            "inclusion_rules": [f"Include observations for {entity}"],
            "exclusion_rules": [],
        },
        "unit_of_analysis": "country_time",
        "data_entities": [
            {
                "name_or_code": entity,
                "entity_type": "country",
                "code_scheme": None,
            }
        ],
        "time_scope": {
            "start": start,
            "end": end,
            "frequency": frequency,
        },
        "variables": _variables(outcome, policy_variable, causal=causal),
        "intervention_or_shock": {
            "name": policy_variable,
            "timing_known": identified,
            "assignment_mechanism": (
                shock_identification if identified else "unknown"
            ),
        },
        "comparison": "冲击或政策变化发生前的条件路径",
        "forecast": None,
        "response_horizons": list(range(horizon + 1)),
        "design_audit_inputs": {
            "shock_identification": (
                "explicit" if identified else "unresolved"
            )
        },
        "field_provenance": _request_provenance(
            question,
            intended_claim,
            entity,
            start,
            end,
            frequency,
            causal=causal,
        ),
        "unresolved_decisions": (
            [] if identified else ["外生冲击序列及其识别来源"]
        ),
        "safe_downgrade_applied": False,
        "output_language": "zh-CN",
    }


def build_dynamic_documents(
    *,
    question: str,
    outcome: str,
    policy_variable: str,
    entity: str,
    start: str,
    end: str,
    frequency: str,
    horizon: int,
    intended_claim: Claim = "causal",
    shock_identification: ShockIdentification = "unresolved",
) -> tuple[dict[str, object], dict[str, object]]:
    """Return validated intake and request documents for Local Projection."""
    if frequency not in {"M", "Q"}:
        raise ValueError("frequency must be M or Q")
    if isinstance(horizon, bool) or not 0 <= horizon <= 120:
        raise ValueError("horizon must be between 0 and 120")
    identity = (
        question,
        outcome,
        policy_variable,
        entity,
        start,
        end,
        frequency,
        horizon,
        intended_claim,
        shock_identification,
    )
    intake_id = _identifier("rd-intake", *identity)
    candidate_id = _identifier("rd-candidate", *identity)
    unresolved = (
        ["外生冲击序列及其识别来源"]
        if intended_claim == "causal" and shock_identification == "unresolved"
        else []
    )
    intake = _intake(
        question=question,
        intake_id=intake_id,
        candidate_id=candidate_id,
        intended_claim=intended_claim,
        unresolved=unresolved,
    )
    request = _request(
        question=question,
        outcome=outcome,
        policy_variable=policy_variable,
        entity=entity,
        start=start,
        end=end,
        frequency=frequency,
        horizon=horizon,
        intended_claim=intended_claim,
        shock_identification=shock_identification,
        intake_id=intake_id,
        candidate_id=candidate_id,
    )
    validate_document("intake", intake)
    validate_document("request", request)
    return intake, request
