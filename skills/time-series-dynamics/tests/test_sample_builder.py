from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from time_series_dynamics.sample_builder import build_horizon_sample


def _frame(periods: int = 12) -> pd.DataFrame:
    values = np.arange(periods, dtype=float)
    return pd.DataFrame(
        {
            "qdate": pd.date_range("2000-01-01", periods=periods, freq="QS"),
            "outcome": values / 100.0,
            "exposure": values + 1.0,
            "control_a": values * 0.5,
            "control_b": np.sin(values),
        }
    )


def test_build_horizon_sample_uses_long_difference_and_lagged_controls() -> None:
    sample = build_horizon_sample(
        _frame(),
        outcome="outcome",
        exposure="exposure",
        controls=("control_a", "control_b"),
        horizon=1,
        lags=2,
    )

    assert sample.nobs == 9
    assert sample.exposure_column == 1
    assert sample.x.shape == (9, 6)
    assert sample.y[0] == pytest.approx(2.0)
    assert sample.x[0].tolist() == pytest.approx([1.0, 3.0, 0.5, 0.0, np.sin(1.0), np.sin(0.0)])
    assert sample.dropped_for_lags == 2
    assert sample.dropped_for_lead == 1
    assert sample.dropped_for_missing == 0


def test_build_horizon_sample_rejects_missing_columns() -> None:
    with pytest.raises(ValueError, match="missing sample columns: absent"):
        build_horizon_sample(
            _frame(),
            outcome="outcome",
            exposure="exposure",
            controls=("absent",),
            horizon=0,
            lags=1,
        )


def test_build_horizon_sample_rejects_insufficient_rows() -> None:
    with pytest.raises(ValueError, match="no usable observations"):
        build_horizon_sample(
            _frame(periods=4),
            outcome="outcome",
            exposure="exposure",
            controls=("control_a",),
            horizon=3,
            lags=2,
        )


def test_build_horizon_sample_applies_declared_response_scale() -> None:
    sample = build_horizon_sample(
        _frame(),
        outcome="outcome",
        exposure="exposure",
        controls=("control_a",),
        horizon=1,
        lags=1,
        response_scale=1.0,
    )

    assert sample.y[0] == pytest.approx(0.02)
