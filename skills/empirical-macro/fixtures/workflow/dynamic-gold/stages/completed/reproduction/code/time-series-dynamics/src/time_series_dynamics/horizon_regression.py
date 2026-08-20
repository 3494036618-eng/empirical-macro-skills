"""Estimate auditable horizon-by-horizon linear projections."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import statsmodels.api as sm  # type: ignore[import-untyped]

from time_series_dynamics.models import (
    DynamicsRequest,
    HorizonEstimate,
    HorizonSample,
)
from time_series_dynamics.sample_builder import build_horizon_sample


def _build_samples(
    frame: pd.DataFrame,
    request: DynamicsRequest,
) -> list[HorizonSample]:
    return [
        build_horizon_sample(
            frame,
            outcome=request.outcome_variable_id,
            exposure=request.exposure_variable_id,
            controls=request.control_variable_ids,
            horizon=horizon,
            lags=request.lags,
        )
        for horizon in request.horizons
    ]


def _use_common_sample(samples: list[HorizonSample]) -> list[HorizonSample]:
    common = set(int(value) for value in samples[0].row_positions)
    for sample in samples[1:]:
        common.intersection_update(int(value) for value in sample.row_positions)
    if not common:
        raise ValueError("no common observations across requested horizons")
    ordered = np.asarray(sorted(common), dtype=np.int64)
    narrowed: list[HorizonSample] = []
    for sample in samples:
        locations = {int(row): index for index, row in enumerate(sample.row_positions)}
        indices = np.asarray([locations[int(row)] for row in ordered], dtype=np.int64)
        removed = sample.nobs - len(indices)
        narrowed.append(
            replace(
                sample,
                y=sample.y[indices],
                x=sample.x[indices],
                row_positions=ordered,
                nobs=len(indices),
                dropped_for_missing=sample.dropped_for_missing + removed,
            )
        )
    return narrowed


def _fit_horizon(
    sample: HorizonSample,
    request: DynamicsRequest,
) -> HorizonEstimate:
    rank = int(np.linalg.matrix_rank(sample.x))
    if rank != sample.x.shape[1]:
        raise ValueError(
            f"design matrix is rank deficient at horizon {sample.horizon}"
        )
    fitted = sm.OLS(sample.y, sample.x, hasconst=True).fit()
    robust = fitted.get_robustcov_results(
        cov_type="HAC",
        maxlags=request.hac_maxlags,
        kernel="bartlett",
        use_correction=False,
        use_t=True,
    )
    parameters = np.asarray(robust.params, dtype=float)
    standard_errors = np.asarray(robust.bse, dtype=float)
    intervals = np.asarray(
        robust.conf_int(alpha=1.0 - request.confidence_level),
        dtype=float,
    )
    column = sample.exposure_column
    values = (
        parameters[column],
        standard_errors[column],
        intervals[column, 0],
        intervals[column, 1],
    )
    if not np.isfinite(values).all():
        raise ValueError(f"non-finite estimate at horizon {sample.horizon}")
    return HorizonEstimate(
        horizon=sample.horizon,
        estimate=float(parameters[column]),
        standard_error=float(standard_errors[column]),
        confidence_lower=float(intervals[column, 0]),
        confidence_upper=float(intervals[column, 1]),
        nobs=sample.nobs,
        df_resid=float(robust.df_resid),
    )


def estimate_path(
    frame: pd.DataFrame,
    request: DynamicsRequest,
) -> tuple[HorizonEstimate, ...]:
    samples = _build_samples(frame, request)
    if request.sample_policy == "common_sample":
        samples = _use_common_sample(samples)
    elif request.sample_policy != "horizon_specific":
        raise ValueError(f"unsupported sample policy: {request.sample_policy}")
    return tuple(_fit_horizon(sample, request) for sample in samples)
