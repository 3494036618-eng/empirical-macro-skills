from __future__ import annotations

import pytest

from robustness_audit.claim_policy import assert_audit_summary_language


def test_scoped_summary_is_allowed_for_causal_candidate() -> None:
    text = (
        "在已声明且实际完成的检查范围内，没有观察到超过冻结判据的敏感性。"
        "这不证明识别假设成立，也不覆盖未执行的规格。"
    )

    assert_audit_summary_language(text, "causal_candidate")


@pytest.mark.parametrize(
    "text",
    [
        "结果已经稳健。",
        "所有规格都一致。",
        "因果关系得到证明。",
        "稳健性检验证明 shock 外生。",
        "关联结果通过稳健性后成为因果。",
    ],
)
def test_unbounded_or_upgraded_claims_are_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="forbidden robustness claim"):
        assert_audit_summary_language(text, "causal_candidate")


def test_association_summary_cannot_use_causal_language() -> None:
    valid = (
        "在已声明检查范围内，条件关联路径没有超过冻结判据。"
        "这不是因果效应估计。"
    )
    assert_audit_summary_language(valid, "associational_only")

    with pytest.raises(ValueError, match="forbidden causal language"):
        assert_audit_summary_language(
            "在已声明检查范围内，加息导致通胀下降。",
            "associational_only",
        )
    with pytest.raises(ValueError, match="forbidden causal language"):
        assert_audit_summary_language(
            "这不是因果效应估计，但加息导致通胀下降。",
            "associational_only",
        )
    with pytest.raises(ValueError, match="forbidden causal language"):
        assert_audit_summary_language(
            "这不是因果效应估计，但加息引起通胀下降，存在因果关系。",
            "associational_only",
        )


def test_pointwise_intervals_cannot_support_whole_path_claims() -> None:
    with pytest.raises(ValueError, match="whole-path"):
        assert_audit_summary_language(
            "整条响应路径在95%置信水平上显著。",
            "causal_candidate",
        )
