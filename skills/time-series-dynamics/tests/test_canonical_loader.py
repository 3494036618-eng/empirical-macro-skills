from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import pytest

from time_series_dynamics.contracts import validate_document
from time_series_dynamics.models import DynamicsRequest, SeriesBinding

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic"


def _request() -> DynamicsRequest:
    document = json.loads(
        (FIXTURES / "canonical-association.request.json").read_text(encoding="utf-8")
    )
    assert isinstance(document, dict)
    validate_document("request", document)
    return DynamicsRequest.from_document(cast(dict[str, object], document))


def _source_frame() -> pd.DataFrame:
    periods = pd.period_range("2000Q1", "2019Q4", freq="Q")
    rows = []
    for index, period in enumerate(periods):
        rows.extend(
            [
                {
                    "period": str(period),
                    "entity_code": "USA",
                    "series_key": "DATASET|USA|CPI_INDEX",
                    "frequency": "Q",
                    "value": 100.0 + 0.5 * index,
                },
                {
                    "period": str(period),
                    "entity_code": "USA",
                    "series_key": "DATASET|USA|POLICY_RATE",
                    "frequency": "Q",
                    "value": 2.0 + 0.01 * index,
                },
                {
                    "period": str(period),
                    "entity_code": "USA",
                    "series_key": "DATASET|USA|REAL_GDP",
                    "frequency": "Q",
                    "value": 1000.0 + 2.0 * index,
                },
            ]
        )
    return pd.DataFrame(rows)


def _write(frame: pd.DataFrame, path: Path) -> Path:
    frame.to_csv(path, index=False)
    return path


def test_loader_builds_declared_analysis_frame(tmp_path: Path) -> None:
    from time_series_dynamics.canonical_loader import (
        load_canonical_quarterly,
    )

    frame = load_canonical_quarterly(
        _write(_source_frame(), tmp_path / "data.csv"),
        _request(),
    )

    assert list(frame.columns) == [
        "qdate",
        "cpi_log",
        "policy_change",
        "cpi_growth",
        "gdp_growth",
    ]
    assert len(frame) == 80
    assert frame["cpi_log"].notna().all()
    assert frame.loc[0, "cpi_log"] == pytest.approx(np.log(100.0))
    assert pd.isna(frame.loc[0, "policy_change"])
    assert frame.loc[1, "policy_change"] == pytest.approx(0.01)
    assert frame.loc[1, "cpi_growth"] == pytest.approx(np.log(100.5) - np.log(100.0))


def test_loader_rejects_undeclared_series(tmp_path: Path) -> None:
    from time_series_dynamics.canonical_loader import (
        load_canonical_quarterly,
    )

    request = _request()
    missing = SeriesBinding(
        variable_id="cpi_log",
        series_key="DATASET|USA|MISSING",
        entity_code="USA",
        transform="log",
    )
    request = replace(
        request,
        series_bindings=(missing, *request.series_bindings[1:]),
    )

    with pytest.raises(ValueError, match="series_binding_missing:cpi_log"):
        load_canonical_quarterly(
            _write(_source_frame(), tmp_path / "data.csv"),
            request,
        )


def test_log_transform_rejects_nonpositive_values(tmp_path: Path) -> None:
    from time_series_dynamics.canonical_loader import (
        load_canonical_quarterly,
    )

    source = _source_frame()
    mask = (source["series_key"] == "DATASET|USA|CPI_INDEX") & (source["period"] == "2003Q1")
    source.loc[mask, "value"] = 0.0

    with pytest.raises(ValueError, match="log_transform_nonpositive:cpi_log"):
        load_canonical_quarterly(
            _write(source, tmp_path / "data.csv"),
            _request(),
        )


def test_loader_rejects_missing_quarter(tmp_path: Path) -> None:
    from time_series_dynamics.canonical_loader import (
        load_canonical_quarterly,
    )

    source = _source_frame()
    source = source.loc[
        ~((source["series_key"] == "DATASET|USA|CPI_INDEX") & (source["period"] == "2002Q2"))
    ]

    with pytest.raises(
        ValueError,
        match="quarterly_axis_incomplete:cpi_log",
    ):
        load_canonical_quarterly(
            _write(source, tmp_path / "data.csv"),
            _request(),
        )


def test_loader_rejects_duplicate_quarter(tmp_path: Path) -> None:
    from time_series_dynamics.canonical_loader import (
        load_canonical_quarterly,
    )

    source = _source_frame()
    duplicate = source.iloc[[0]]
    source = pd.concat([source, duplicate], ignore_index=True)

    with pytest.raises(
        ValueError,
        match="duplicate_quarter:cpi_log",
    ):
        load_canonical_quarterly(
            _write(source, tmp_path / "data.csv"),
            _request(),
        )


def test_loader_rejects_missing_canonical_column(tmp_path: Path) -> None:
    from time_series_dynamics.canonical_loader import (
        load_canonical_quarterly,
    )

    source = _source_frame().drop(columns="frequency")

    with pytest.raises(
        ValueError,
        match="canonical_columns_missing:frequency",
    ):
        load_canonical_quarterly(
            _write(source, tmp_path / "data.csv"),
            _request(),
        )
