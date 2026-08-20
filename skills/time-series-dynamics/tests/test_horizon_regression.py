from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from time_series_dynamics.horizon_regression import estimate_path
from time_series_dynamics.models import DynamicsRequest
from time_series_dynamics.sample_builder import build_horizon_sample


def _request(*, sample_policy: str = "horizon_specific") -> DynamicsRequest:
    return DynamicsRequest(
        request_id="tsd-request-0123456789abcdef",
        research_plan_ref="research-plan-0123456789abcdef",
        macro_data_bundle_refs=("macro-result-0123456789abcdef",),
        shock_identification_artifact_ref="shock-artifact-0123456789abcdef",
        analysis_track="identified_shock_irf",
        estimand_type="impulse_response",
        method_profile="observed_shock_linear_lp",
        outcome_variable_id="outcome",
        exposure_variable_id="exposure",
        control_variable_ids=("control_a", "control_b"),
        frequency="Q",
        sample_start="1980Q1",
        sample_end="2009Q4",
        sample_policy=sample_policy,
        horizons=(0, 1, 2),
        lags=2,
        hac_maxlags=2,
        confidence_level=0.95,
        claim_eligibility="causal_candidate",
        output_unit="log_points_x100",
    )


def _random_frame() -> pd.DataFrame:
    rng = np.random.default_rng(20260816)
    periods = 120
    return pd.DataFrame(
        {
            "qdate": pd.date_range("1980-01-01", periods=periods, freq="QS"),
            "outcome": rng.normal(0.0, 0.02, periods).cumsum(),
            "exposure": rng.normal(0.0, 1.0, periods),
            "control_a": rng.normal(0.0, 1.0, periods),
            "control_b": rng.normal(0.0, 1.0, periods),
        }
    )


def test_point_estimate_matches_independent_matrix_solution() -> None:
    frame = _random_frame()
    request = replace(_request(), horizons=(0,))
    sample = build_horizon_sample(
        frame,
        outcome="outcome",
        exposure="exposure",
        controls=("control_a", "control_b"),
        horizon=0,
        lags=2,
    )
    expected = np.linalg.lstsq(sample.x, sample.y, rcond=None)[0][
        sample.exposure_column
    ]

    result = estimate_path(frame, request)

    assert result[0].estimate == pytest.approx(expected, abs=1e-12)
    assert result[0].standard_error > 0
    assert result[0].confidence_lower < result[0].confidence_upper


def test_exposure_sign_flip_reverses_estimated_path() -> None:
    frame = _random_frame()
    flipped = frame.copy()
    flipped["exposure"] *= -1

    original = estimate_path(frame, _request())
    reversed_path = estimate_path(flipped, _request())

    assert [item.estimate for item in reversed_path] == pytest.approx(
        [-item.estimate for item in original],
        abs=1e-12,
    )


def test_common_sample_uses_equal_nobs_across_horizons() -> None:
    result = estimate_path(_random_frame(), _request(sample_policy="common_sample"))

    assert len({item.nobs for item in result}) == 1


def test_rank_deficient_design_fails_closed() -> None:
    frame = _random_frame()
    frame["exposure"] = 1.0

    with pytest.raises(ValueError, match="design matrix is rank deficient"):
        estimate_path(frame, _request())
