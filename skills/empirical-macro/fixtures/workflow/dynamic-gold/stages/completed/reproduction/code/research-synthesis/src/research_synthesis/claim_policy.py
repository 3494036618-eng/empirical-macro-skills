"""限制 research report 的 claim 级别和语言。"""

from __future__ import annotations

ALLOWED_CLAIMS = {
    "descriptive_only",
    "associational_only",
    "predictive_only",
    "causal_candidate",
    "structural_candidate",
    "not_eligible",
}
ASSESSMENTS = {
    "passed_declared_checks",
    "sensitive",
    "inconclusive",
    "not_assessed",
}
FORBIDDEN = {
    "证明因果",
    "因果关系已经确定",
    "全面稳健",
    "所有规格一致",
    "整条路径显著",
    "联合显著",
    "whole-path significance",
    "simultaneous significance",
}
ASSOCIATIONAL_FORBIDDEN = {
    "因果效应",
    "冲击响应",
    "impulse response",
    "导致",
    "引起",
}


def effective_claim_eligibility(
    estimator_claim: str,
    assessment: str,
) -> str:
    """稳健性审计不得升级 estimator claim。"""
    if estimator_claim not in ALLOWED_CLAIMS:
        raise ValueError("unknown_claim_eligibility")
    if assessment not in ASSESSMENTS:
        raise ValueError("unknown_robustness_assessment")
    return estimator_claim


def assert_report_language(report: str, claim_eligibility: str) -> None:
    """拒绝超过有效 claim eligibility 的报告语言。"""
    text = report.casefold()
    forbidden = set(FORBIDDEN)
    if claim_eligibility == "associational_only":
        forbidden.update(ASSOCIATIONAL_FORBIDDEN)
    hits = sorted(phrase for phrase in forbidden if phrase.casefold() in text)
    if hits:
        raise ValueError(f"forbidden_report_language:{','.join(hits)}")
