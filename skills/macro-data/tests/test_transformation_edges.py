from __future__ import annotations

from typing import Any

import pytest

from macro_data.transformation_engine import (
    _aggregate,
    apply_transformations,
)


def _transform_request(
    name: str,
    parameters: dict[str, object] | None,
) -> dict[str, Any]:
    return {
        "transformation_policy": {
            "requested_transformations": [name],
        },
        "transformation_parameters": ({name: parameters} if parameters is not None else {}),
    }


def _item(
    period: str,
    frequency: str,
    value: float | None,
) -> dict[str, Any]:
    return {
        "series_key": "SERIES",
        "time_raw": period,
        "observed_frequency": frequency,
        "value": value,
    }


def test_unit_scale_requires_parameters() -> None:
    request = _transform_request("unit_scale", None)

    with pytest.raises(
        ValueError,
        match="unit_scale transformation parameters",
    ):
        apply_transformations(request, [_item("2020", "A", 1.0)])


def test_downsample_requires_parameters() -> None:
    request = _transform_request("downsample", None)

    with pytest.raises(
        ValueError,
        match="downsample transformation parameters",
    ):
        apply_transformations(request, [_item("2020-01", "M", 1.0)])


def test_rejects_unsupported_downsample_path() -> None:
    request = _transform_request(
        "downsample",
        {
            "source_frequency": "A",
            "target_frequency": "Q",
            "method": "mean",
        },
    )

    with pytest.raises(ValueError, match="unsupported downsample path"):
        apply_transformations(request, [_item("2020", "A", 1.0)])


def test_rejects_source_frequency_mismatch() -> None:
    request = _transform_request(
        "downsample",
        {
            "source_frequency": "M",
            "target_frequency": "Q",
            "method": "mean",
        },
    )

    with pytest.raises(ValueError, match="source frequency mismatch"):
        apply_transformations(request, [_item("2020-Q1", "Q", 1.0)])


def test_rejects_incomplete_downsample_period() -> None:
    request = _transform_request(
        "downsample",
        {
            "source_frequency": "M",
            "target_frequency": "Q",
            "method": "mean",
        },
    )
    items = [
        _item("2020-01", "M", 1.0),
        _item("2020-02", "M", 2.0),
    ]

    with pytest.raises(ValueError, match="incomplete downsample period"):
        apply_transformations(request, items)


def test_rejects_missing_downsample_value() -> None:
    request = _transform_request(
        "downsample",
        {
            "source_frequency": "M",
            "target_frequency": "Q",
            "method": "mean",
        },
    )
    items = [
        _item("2020-01", "M", 1.0),
        _item("2020-02", "M", None),
        _item("2020-03", "M", 3.0),
    ]

    with pytest.raises(ValueError, match="contains missing values"):
        apply_transformations(request, items)


def test_quarter_to_year_uses_four_observations() -> None:
    request = _transform_request(
        "downsample",
        {
            "source_frequency": "Q",
            "target_frequency": "A",
            "method": "sum",
        },
    )
    items = [
        _item("2020-Q1", "Q", 1.0),
        _item("2020-Q2", "Q", 2.0),
        _item("2020-Q3", "Q", 3.0),
        _item("2020-Q4", "Q", 4.0),
    ]

    transformed, records = apply_transformations(request, items)

    assert transformed[0]["time_raw"] == "2020"
    assert transformed[0]["value"] == 10.0
    assert records[0]["type"] == "downsample"


@pytest.mark.parametrize(
    ("method", "expected"),
    [("sum", 6.0), ("mean", 2.0), ("last", 3.0)],
)
def test_aggregate_methods(method: str, expected: float) -> None:
    assert _aggregate([1.0, 2.0, 3.0], method) == expected


def test_aggregate_rejects_unknown_method() -> None:
    with pytest.raises(ValueError, match="unsupported downsample method"):
        _aggregate([1.0], "median")
