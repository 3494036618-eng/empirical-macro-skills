"""Claim-language firewall for robustness audit summaries."""

from __future__ import annotations

FORBIDDEN_ROBUSTNESS_CLAIMS = (
    "结果已经稳健",
    "所有规格都一致",
    "因果关系得到证明",
    "稳健性检验证明 shock 外生",
    "关联结果通过稳健性后成为因果",
)
FORBIDDEN_ASSOCIATION_TERMS = (
    "导致",
    "引起",
    "因果关系",
    "因果效应",
    "冲击响应",
    "impulse response",
    "irf",
)
FORBIDDEN_WHOLE_PATH_TERMS = (
    "整条响应路径",
    "联合显著",
    "whole-path",
    "whole path",
    "simultaneous significance",
)


def assert_audit_summary_language(
    text: str,
    claim_eligibility: str,
) -> None:
    claim = next(
        (item for item in FORBIDDEN_ROBUSTNESS_CLAIMS if item in text),
        None,
    )
    if claim is not None:
        raise ValueError(f"forbidden robustness claim: {claim}")
    lowered = text.casefold()
    whole_path = next(
        (
            item
            for item in FORBIDDEN_WHOLE_PATH_TERMS
            if item.casefold() in lowered
        ),
        None,
    )
    if whole_path is not None:
        raise ValueError(f"forbidden whole-path claim: {whole_path}")
    if claim_eligibility != "associational_only":
        return
    lowered = lowered.replace("不是因果效应估计".casefold(), "")
    term = next(
        (
            item
            for item in FORBIDDEN_ASSOCIATION_TERMS
            if item.casefold() in lowered
        ),
        None,
    )
    if term is not None:
        raise ValueError(f"forbidden causal language: {term}")
