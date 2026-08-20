"""Identification audit construction without granting causal validity."""

from __future__ import annotations

import hashlib
import json

from research_design.contracts import validate_document
from research_design.design_router import eligible_designs

DESIGN_TO_FAMILY = {
    "event_study_did": "causal_policy_evaluation",
    "instrumental_variables": "causal_policy_evaluation",
    "local_projection": "dynamic_shock_response",
    "var_svar": "dynamic_shock_response",
    "structural_model": "structural_modeling",
}


def _artifact_suffix(*documents: dict[str, object]) -> str:
    payload = json.dumps(documents, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _request_id(request: dict[str, object]) -> str:
    request_id = request.get("request_id")
    if isinstance(request_id, str):
        return request_id
    return f"rd-request-{_artifact_suffix(request)}"


def _assumption(design: str) -> dict[str, object]:
    if design == "event_study_did":
        code, statement = "parallel_trends", "反事实结果路径满足设计所需的平行趋势假设。"
    elif design == "instrumental_variables":
        code, statement = "instrument_exclusion", "工具仅通过目标处理影响结果。"
    elif design in {"local_projection", "var_svar"}:
        code, statement = "shock_exogeneity", "已定义冲击与同期及未来未观测创新正交。"
    else:
        code, statement = "structural_stability", "结构关系和参数在目标反事实范围内稳定。"
    return {
        "code": code,
        "statement": statement,
        "status": "unresolved",
        "testability": "indirect",
        "required_diagnostics": ["independent_identification_review"],
        "evidence_references": [],
    }


def _threat(design: str) -> dict[str, object]:
    if design == "event_study_did":
        code = "parallel_trends"
    elif design == "instrumental_variables":
        code = "instrument_invalidity"
    elif design in {"local_projection", "var_svar"}:
        code = "simultaneity"
    else:
        code = "structural_break"
    return {
        "code": code,
        "severity": "high",
        "status": "open",
        "mitigation": "必须完成独立方法审查，不能由模型自动认定假设成立。",
    }


def _design_is_eligible(request: dict[str, object], design: str) -> bool:
    family = DESIGN_TO_FAMILY.get(design)
    if family is None:
        return False
    candidates = eligible_designs(request, family)
    return any(
        item["code"] == design and item["decision"] == "adopt"
        for item in candidates
    )


def build_identification_audit(
    request: dict[str, object],
    estimand: dict[str, object],
    design: str,
) -> dict[str, object]:
    intended_claim = request.get("intended_claim")
    claim = intended_claim if isinstance(intended_claim, str) else "causal"
    estimand_status = estimand.get("status")
    status = estimand_status if isinstance(estimand_status, str) else "missing"
    eligible = _design_is_eligible(request, design) and status == "specified"
    if claim == "structural":
        identification_status = "assumption_sensitive"
        claim_eligibility = "structural_candidate"
    else:
        identification_status = "candidate_identified" if eligible else "not_identified"
        claim_eligibility = "causal_candidate" if eligible else "not_eligible"
    audit: dict[str, object] = {
        "schema_version": "0.1.0-draft",
        "audit_id": f"id-audit-{_artifact_suffix(request, estimand, {'design': design})}",
        "request_id": _request_id(request),
        "intended_claim": claim,
        "estimand_status": status,
        "assumptions": [_assumption(design)],
        "threats": [_threat(design)],
        "identification_status": identification_status,
        "claim_eligibility": claim_eligibility,
        "review_required": True,
    }
    validate_document("identification_audit", audit)
    return audit
