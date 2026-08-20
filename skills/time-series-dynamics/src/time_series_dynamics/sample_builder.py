"""Construct auditable horizon-specific local-projection samples."""

from __future__ import annotations

import numpy as np
import pandas as pd

from time_series_dynamics.models import HorizonSample


def _validate_inputs(
    frame: pd.DataFrame,
    outcome: str,
    exposure: str,
    controls: tuple[str, ...],
    horizon: int,
    lags: int,
) -> None:
    required = {outcome, exposure, *controls}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing sample columns: {', '.join(missing)}")
    if horizon < 0 or lags < 0:
        raise ValueError("horizon and lags must be non-negative")


def _design_frame(
    frame: pd.DataFrame,
    exposure: str,
    controls: tuple[str, ...],
    lags: int,
) -> pd.DataFrame:
    columns: dict[str, object] = {
        "constant": np.ones(len(frame), dtype=float),
        "exposure": frame[exposure],
    }
    for control in controls:
        for lag in range(1, lags + 1):
            columns[f"{control}_lag{lag}"] = frame[control].shift(lag)
    return pd.DataFrame(columns, index=frame.index)


def build_horizon_sample(
    frame: pd.DataFrame,
    *,
    outcome: str,
    exposure: str,
    controls: tuple[str, ...],
    horizon: int,
    lags: int,
    response_scale: float = 100.0,
) -> HorizonSample:
    _validate_inputs(frame, outcome, exposure, controls, horizon, lags)
    dependent = response_scale * (frame[outcome].shift(-horizon) - frame[outcome].shift(1))
    design = _design_frame(frame, exposure, controls, lags)
    combined = pd.concat([dependent.rename("dependent"), design], axis=1)
    complete = combined.notna().all(axis=1)
    usable = combined.loc[complete]
    if usable.empty:
        raise ValueError("no usable observations for requested horizon")
    x = usable.drop(columns="dependent").to_numpy(dtype=float)
    y = usable["dependent"].to_numpy(dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("non-finite values in estimation sample")
    structural_lag_loss = max(1, lags)
    potential = max(0, len(frame) - structural_lag_loss - horizon)
    return HorizonSample(
        horizon=horizon,
        y=y,
        x=x,
        row_positions=np.flatnonzero(complete.to_numpy()).astype(np.int64),
        exposure_column=1,
        nobs=len(usable),
        dropped_for_lags=structural_lag_loss,
        dropped_for_lead=horizon,
        dropped_for_missing=max(0, potential - len(usable)),
    )
