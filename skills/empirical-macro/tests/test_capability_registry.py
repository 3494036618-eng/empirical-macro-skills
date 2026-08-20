from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    ("family", "executor"),
    (
        ("dynamic_shock_response", "time-series-dynamics"),
        ("conditional_dynamic_association", "time-series-dynamics"),
    ),
)
def test_only_current_dynamic_families_are_executable(
    family: str,
    executor: str,
) -> None:
    """Break caught: an approved dynamic method loses its executor mapping."""
    from empirical_macro.capability_registry import resolve_capability

    decision = resolve_capability(family)
    assert decision.executable is True
    assert decision.executor_skill == executor
    assert decision.issue_code is None
    assert decision.user_message is None


@pytest.mark.parametrize(
    "family",
    (
        "panel_association",
        "causal_policy_evaluation",
        "forecasting_nowcasting",
        "structural_modeling",
    ),
)
def test_unsupported_family_has_one_exact_user_message(family: str) -> None:
    """Break caught: an unimplemented method leaks advice or an executor."""
    from empirical_macro.capability_registry import resolve_capability

    decision = resolve_capability(family)
    assert decision.executable is False
    assert decision.executor_skill is None
    assert decision.issue_code == "method_not_implemented"
    assert decision.user_message == "当前版本不能执行该方法"


def test_unknown_family_is_rejected_closed() -> None:
    """Break caught: a registry typo silently falls through as supported."""
    from empirical_macro.capability_registry import resolve_capability

    with pytest.raises(ValueError, match="unknown method family"):
        resolve_capability("imaginary_method")
