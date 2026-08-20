"""Load declared variables from a canonical macro-data long table."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from time_series_dynamics.models import DynamicsRequest, SeriesBinding

REQUIRED_COLUMNS = {
    "period",
    "entity_code",
    "series_key",
    "frequency",
    "value",
}


def _transform(
    values: pd.Series,
    binding: SeriesBinding,
) -> pd.Series:
    if binding.transform in {"log", "log_difference"}:
        if (values <= 0).any():
            raise ValueError(f"log_transform_nonpositive:{binding.variable_id}")
        values = np.log(values)
    if binding.transform in {"difference", "log_difference"}:
        values = values.diff()
    return values


def _binding_values(
    source: pd.DataFrame,
    binding: SeriesBinding,
    expected: pd.PeriodIndex,
) -> pd.Series:
    rows = source.loc[
        (source["series_key"] == binding.series_key)
        & (source["entity_code"] == binding.entity_code)
        & (source["frequency"] == "Q")
    ].copy()
    if rows.empty:
        raise ValueError(f"series_binding_missing:{binding.variable_id}")
    try:
        periods = pd.PeriodIndex(
            rows["period"].astype(str),
            freq="Q",
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"quarterly_period_invalid:{binding.variable_id}") from exc
    rows.index = periods
    rows = rows.loc[(rows.index >= expected[0]) & (rows.index <= expected[-1])].sort_index()
    if rows.index.duplicated().any():
        raise ValueError(f"duplicate_quarter:{binding.variable_id}")
    if not rows.index.equals(expected):
        raise ValueError(f"quarterly_axis_incomplete:{binding.variable_id}")
    values = pd.to_numeric(rows["value"], errors="raise").astype(float)
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError(f"nonfinite_value:{binding.variable_id}")
    return _transform(values, binding)


def load_canonical_quarterly(
    path: Path,
    request: DynamicsRequest,
) -> pd.DataFrame:
    source = pd.read_csv(path)
    missing = sorted(REQUIRED_COLUMNS - set(source.columns))
    if missing:
        raise ValueError(f"canonical_columns_missing:{','.join(missing)}")
    expected = pd.period_range(
        request.sample_start,
        request.sample_end,
        freq="Q",
    )
    output = {
        binding.variable_id: _binding_values(
            source,
            binding,
            expected,
        )
        for binding in request.series_bindings
    }
    analysis = pd.DataFrame(output, index=expected)
    if analysis.iloc[1:].isna().any().any():
        raise ValueError("canonical_transform_missing_values")
    analysis.insert(0, "qdate", expected.to_timestamp(how="start"))
    return analysis.reset_index(drop=True)
