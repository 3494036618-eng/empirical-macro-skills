"""从结构化结果编译 report claims。"""

from __future__ import annotations

from typing import cast

from research_synthesis.claim_policy import effective_claim_eligibility
from research_synthesis.identifiers import content_id
from research_synthesis.models import EnvelopeMap


def _evidence_by_role(
    evidence_index: dict[str, object],
) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for item in cast(list[dict[str, object]], evidence_index["evidence"]):
        result.setdefault(str(item["semantic_role"]), []).append(item)
    return result


def _claim(
    claim_type: str,
    text: str,
    eligibility: str,
    evidence_refs: list[str],
    status: str = "qualified",
) -> dict[str, object]:
    payload = {
        "claim_type": claim_type,
        "status": status,
        "report_text": text,
        "claim_eligibility": eligibility,
        "evidence_refs": evidence_refs,
        "limitation_refs": [],
        "review_required": eligibility in {
            "causal_candidate",
            "structural_candidate",
        },
        "prohibited_expansions": [
            "confirmed_causal",
            "fully_robust",
            "whole_path_significance",
        ],
    }
    return {"claim_id": content_id("rs-claim", payload), **payload}


def _anchor_horizons(envelopes: EnvelopeMap) -> list[int]:
    plan = cast(
        dict[str, object],
        envelopes["robustness_audit"].statuses["audit_plan"],
    )
    checks = cast(list[dict[str, object]], plan["checks"])
    return cast(list[int], checks[0]["anchor_horizons"])


def _result_claim_type(eligibility: str) -> str:
    if eligibility == "associational_only":
        return "associational"
    if eligibility == "descriptive_only":
        return "descriptive"
    if eligibility == "causal_candidate":
        return "causal_candidate"
    raise ValueError(f"unsupported_dynamic_claim:{eligibility}")


def _robustness_text(assessment: str, plan_timing: str) -> str:
    messages = {
        "passed_declared_checks": (
            "在已声明并实际执行的检查范围内，没有发现超过冻结阈值的敏感性"
        ),
        "sensitive": "已声明检查显示结果对至少一项检查敏感",
        "inconclusive": "已声明检查不足以形成明确的稳健性判断",
        "not_assessed": "尚未形成稳健性 assessment",
    }
    message = messages.get(assessment)
    if message is None:
        raise ValueError(f"unknown_robustness_assessment:{assessment}")
    timing = {
        "post_result_exploratory": "post-result exploratory",
        "pre_result_bound": "pre-result bound",
    }.get(plan_timing, plan_timing.replace("_", "-"))
    return f"{message}；该审计为 {timing}。"


def _design_text(envelopes: EnvelopeMap) -> str:
    track = str(
        envelopes["research_design"].statuses["analysis_track"]
    )
    if track == "conditional_dynamic_association":
        return "研究采用已批准的 Local Projection 条件动态关联设计。"
    return "研究采用已批准的 Local Projection 动态响应设计。"


def _confidence_label(value: object) -> str:
    percentage = float(cast(float, value)) * 100
    return f"{percentage:g}%"


def _data_text(envelopes: EnvelopeMap) -> str:
    source = cast(
        dict[str, object],
        envelopes["macro_data"].statuses["source"],
    )
    return (
        f"分析使用固定版本、{source['license']} 许可的"
        f" {source['source_title']} 数据。"
    )


def _result_claims(
    envelopes: EnvelopeMap,
    by_role: dict[str, list[dict[str, object]]],
    eligibility: str,
) -> list[dict[str, object]]:
    rows = cast(
        list[dict[str, object]],
        envelopes["estimator"].statuses["horizon_results"],
    )
    by_horizon = {int(cast(int, row["horizon"])): (index, row) for index, row in enumerate(rows)}
    claims: list[dict[str, object]] = []
    estimate_evidence = by_role["estimate"]
    uncertainty_evidence = by_role["uncertainty"]
    for horizon in _anchor_horizons(envelopes):
        index, row = by_horizon[horizon]
        confidence = _confidence_label(row["confidence_level"])
        uncertainty_refs = [
            str(item["evidence_id"])
            for item in uncertainty_evidence
            if str(
                cast(dict[str, object], item["locator"])["value"]
            ).startswith(f"/horizon_results/{index}/")
        ]
        text = (
            f"h={horizon} 时，估计值为 {float(cast(float, row['estimate'])):.3f}"
            f"，{confidence} pointwise interval 为 "
            f"[{float(cast(float, row['confidence_lower'])):.3f}, "
            f"{float(cast(float, row['confidence_upper'])):.3f}]。"
        )
        claims.append(
            _claim(
                _result_claim_type(eligibility),
                text,
                eligibility,
                [
                    str(estimate_evidence[index]["evidence_id"]),
                    *uncertainty_refs,
                ],
            )
        )
    return claims


def compile_claim_ledger(
    envelopes: EnvelopeMap,
    evidence_index: dict[str, object],
) -> dict[str, object]:
    """编译不升级上游 claim 的报告声明。"""
    audit = envelopes["robustness_audit"]
    eligibility = effective_claim_eligibility(
        envelopes["estimator"].claim_eligibility,
        str(audit.statuses["assessment"]),
    )
    by_role = _evidence_by_role(evidence_index)
    assessment = str(audit.statuses["assessment"])
    plan_timing = str(audit.statuses["plan_timing"])
    claims = [
        _claim(
            "design",
            _design_text(envelopes),
            eligibility,
            [
                str(by_role["research_question"][0]["evidence_id"]),
                str(by_role["estimand"][0]["evidence_id"]),
            ],
        ),
        _claim(
            "data",
            _data_text(envelopes),
            eligibility,
            [
                str(by_role["data_identity"][0]["evidence_id"]),
                str(by_role["license"][0]["evidence_id"]),
            ],
        ),
        *_result_claims(envelopes, by_role, eligibility),
        _claim(
            "robustness",
            _robustness_text(assessment, plan_timing),
            eligibility,
            [
                str(item["evidence_id"])
                for role in ("assessment", "robustness_check")
                for item in by_role[role]
            ],
        ),
    ]
    payload = {
        "schema_version": "0.1.0",
        "effective_claim_eligibility": eligibility,
        "claims": claims,
    }
    return {
        **payload,
        "claim_ledger_id": content_id("rs-claim-ledger", payload),
    }
