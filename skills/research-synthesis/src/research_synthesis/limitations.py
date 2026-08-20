"""编译研究限制及其受影响 claims。"""

from __future__ import annotations

from typing import cast

from research_synthesis.identifiers import content_id
from research_synthesis.models import EnvelopeMap

ASSUMPTION_STATEMENTS = {
    "shock_exogeneity": (
        "已识别的货币政策冲击必须与影响结果路径的未观测创新正交；"
        "该外生性假设尚未解决。"
    ),
}


def _evidence_id(
    evidence_index: dict[str, object],
    semantic_role: str,
) -> str:
    evidence = cast(list[dict[str, object]], evidence_index["evidence"])
    return str(
        next(
            item["evidence_id"]
            for item in evidence
            if item["semantic_role"] == semantic_role
        )
    )


def _affected_claims(claim_ledger: dict[str, object]) -> list[str]:
    claims = cast(list[dict[str, object]], claim_ledger["claims"])
    affected = [
        str(claim["claim_id"])
        for claim in claims
        if claim["claim_type"] in {
            "associational",
            "causal_candidate",
            "descriptive",
            "robustness",
        }
    ]
    if not affected:
        raise ValueError("no_substantive_claims_for_limitations")
    return affected


def _limitation(
    code: str,
    category: str,
    severity: str,
    statement: str,
    evidence_ref: str,
    affected_claim_refs: list[str],
    mitigation: str,
) -> dict[str, object]:
    payload = {
        "category": category,
        "severity": severity,
        "status": "open",
        "statement": f"{code}: {statement}",
        "source_refs": [evidence_ref],
        "affected_claim_refs": affected_claim_refs,
        "mitigation": mitigation,
        "release_impact": "review_required",
    }
    return {
        "limitation_id": content_id("rs-limitation", payload),
        **payload,
    }


def _identification_limitations(
    envelopes: EnvelopeMap,
    evidence_ref: str,
    claims: list[str],
) -> list[dict[str, object]]:
    design = envelopes["research_design"]
    assumptions = cast(
        list[dict[str, object]],
        design.statuses["identification_assumptions"],
    )
    threats = cast(
        list[dict[str, object]],
        design.statuses["identification_threats"],
    )
    result = [
        _limitation(
            str(item["code"]),
            "identification",
            "material",
            ASSUMPTION_STATEMENTS.get(
                str(item["code"]),
                "该识别假设尚未解决，需要人工审核。",
            ),
            evidence_ref,
            claims,
            "保留人工识别审核并执行所列 diagnostics。",
        )
        for item in assumptions
        if item.get("status") == "unresolved"
    ]
    categories = {
        "simultaneity": "identification",
        "sample_selection": "sample",
        "structural_break": "robustness",
        "multiple_testing": "inference",
    }
    result.extend(
        _limitation(
            str(item["code"]),
            categories.get(str(item["code"]), "design"),
            str(item["severity"]),
            f"该识别威胁当前状态为 {item['status']}。",
            evidence_ref,
            claims,
            str(item["mitigation"]),
        )
        for item in threats
        if item.get("status") == "open"
    )
    return result


def compile_limitations(
    envelopes: EnvelopeMap,
    claim_ledger: dict[str, object],
    evidence_index: dict[str, object] | None = None,
) -> dict[str, object]:
    """编译所有 material/open limitations。"""
    if evidence_index is None:
        from research_synthesis.evidence_index import compile_evidence_index

        evidence_index = compile_evidence_index(envelopes)
    claims = _affected_claims(claim_ledger)
    identification_ref = _evidence_id(evidence_index, "identification")
    assessment_ref = _evidence_id(evidence_index, "assessment")
    uncertainty_ref = _evidence_id(evidence_index, "uncertainty")
    limitations = _identification_limitations(
        envelopes,
        identification_ref,
        claims,
    )
    if (
        envelopes["robustness_audit"].statuses["plan_timing"]
        == "post_result_exploratory"
    ):
        limitations.append(
            _limitation(
                "post_result_exploratory",
                "robustness",
                "material",
                "稳健性计划在 baseline result 之后冻结。",
                assessment_ref,
                claims,
                "保持 review_required，不把 passed checks 升级为全面稳健。",
            )
        )
    limitations.append(
        _limitation(
            "pointwise_not_simultaneous",
            "inference",
            "material",
            "当前区间为逐 horizon pointwise intervals。",
            uncertainty_ref,
            claims,
            "禁止整条路径或 simultaneous significance 声明。",
        )
    )
    payload = {
        "schema_version": "0.1.0",
        "limitations": limitations,
    }
    return {
        **payload,
        "limitations_id": content_id("rs-limitations", payload),
    }
