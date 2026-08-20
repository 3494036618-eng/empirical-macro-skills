from __future__ import annotations

from importlib import import_module

import pytest


@pytest.mark.parametrize(
    ("estimator_claim", "assessment", "expected"),
    [
        ("associational_only", "passed_declared_checks", "associational_only"),
        ("causal_candidate", "passed_declared_checks", "causal_candidate"),
        ("causal_candidate", "sensitive", "causal_candidate"),
        ("causal_candidate", "inconclusive", "causal_candidate"),
    ],
)
def test_claim_eligibility_never_upgrades(
    estimator_claim: str,
    assessment: str,
    expected: str,
) -> None:
    module = import_module("research_synthesis.claim_policy")
    assert hasattr(module, "effective_claim_eligibility")

    assert (
        module.effective_claim_eligibility(estimator_claim, assessment)
        == expected
    )


def test_report_language_rejects_overclaim() -> None:
    module = import_module("research_synthesis.claim_policy")
    assert hasattr(module, "assert_report_language")

    with pytest.raises(ValueError, match="forbidden_report_language"):
        module.assert_report_language(
            "这证明因果关系已经确定，而且整条路径显著。",
            "causal_candidate",
        )


def test_report_language_allows_qualified_candidate() -> None:
    module = import_module("research_synthesis.claim_policy")
    assert hasattr(module, "assert_report_language")

    module.assert_report_language(
        "在仍未解决的识别假设下，估计路径属于因果候选。",
        "causal_candidate",
    )
