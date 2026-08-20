"""Claim-language rules for dynamic analysis tracks."""

from __future__ import annotations

from time_series_dynamics.models import ClaimPolicy

POLICIES = {
    "identified_shock_irf": ClaimPolicy(
        analysis_track="identified_shock_irf",
        result_label="impulse_response",
        claim_eligibility="causal_candidate",
        review_required=True,
        causal_language_allowed=True,
        title_zh="已识别冲击的动态响应",
        required_disclaimer_zh="该结果是因果候选，因果解释仍需独立审查。",
    ),
    "conditional_dynamic_association": ClaimPolicy(
        analysis_track="conditional_dynamic_association",
        result_label="conditional_projection_path",
        claim_eligibility="associational_only",
        review_required=False,
        causal_language_allowed=False,
        title_zh="条件动态关联路径",
        required_disclaimer_zh=(
            "这是一项条件关联分析，不是因果效应估计。"
            "结果不能说明政策变化导致了后续经济变量变化。"
        ),
    ),
}
FORBIDDEN_ASSOCIATION_TERMS = (
    "导致",
    "因果效应",
    "冲击响应",
    "impulse response",
    "irf",
)


def claim_policy(track: str) -> ClaimPolicy:
    try:
        return POLICIES[track]
    except KeyError as exc:
        raise ValueError(f"unsupported analysis track: {track}") from exc


def assert_summary_language(text: str, policy: ClaimPolicy) -> None:
    if policy.required_disclaimer_zh not in text:
        raise ValueError("required claim disclaimer is missing")
    if policy.causal_language_allowed:
        return
    remainder = text.replace(policy.required_disclaimer_zh, "").casefold()
    term = next(
        (item for item in FORBIDDEN_ASSOCIATION_TERMS if item.casefold() in remainder),
        None,
    )
    if term is not None:
        raise ValueError(f"forbidden causal language: {term}")
