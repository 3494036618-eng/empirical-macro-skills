from __future__ import annotations

import pytest

from robustness_audit.comparison import compare_paths


def _result(
    estimates: list[float],
    standard_errors: list[float],
    nobs: list[int],
) -> dict[str, object]:
    return {
        "horizon_results": [
            {
                "horizon": horizon,
                "estimate": estimate,
                "standard_error": standard_error,
                "confidence_lower": estimate - 2 * standard_error,
                "confidence_upper": estimate + 2 * standard_error,
                "nobs": count,
            }
            for horizon, (estimate, standard_error, count) in enumerate(
                zip(estimates, standard_errors, nobs, strict=True)
            )
        ]
    }


def test_compare_paths_matches_independent_hand_calculation() -> None:
    baseline = _result([0.0, 1.0, -2.0], [1.0, 0.5, 1.0], [100, 90, 80])
    alternative = _result([0.0, 1.5, -1.0], [1.0, 0.75, 2.0], [100, 85, 70])

    metrics = compare_paths(
        baseline,
        alternative,
        epsilon=1e-12,
        anchor_horizons=(0, 1, 2),
    )

    assert metrics["estimate_delta"] == pytest.approx([0.0, 0.5, 1.0])
    assert metrics["absolute_estimate_delta"] == pytest.approx([0.0, 0.5, 1.0])
    assert metrics["standard_error_ratio"] == pytest.approx([1.0, 1.5, 2.0])
    assert metrics["nobs_delta"] == [0, -5, -10]
    assert metrics["max_standardized_path_deviation"] == pytest.approx(2.0 / 3.0)
    assert metrics["max_coefficient_delta"] == pytest.approx(1.0)
    assert metrics["anchor_sign_changes"] == 0


def test_compare_paths_rejects_horizon_mismatch_or_nonpositive_epsilon() -> None:
    baseline = _result([1.0], [0.5], [20])
    alternative = _result([1.0, 2.0], [0.5, 0.5], [20, 19])

    with pytest.raises(ValueError, match="horizon mismatch"):
        compare_paths(baseline, alternative, epsilon=1e-12, anchor_horizons=(0,))
    with pytest.raises(ValueError, match="epsilon"):
        compare_paths(baseline, baseline, epsilon=0.0, anchor_horizons=(0,))
