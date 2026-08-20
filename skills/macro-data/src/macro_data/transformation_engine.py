"""Controlled, deterministic transformations allowed by the Beta contract."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any


def _quarter(period: str) -> str:
    year, month = period.split("-")
    return f"{year}Q{(int(month) - 1) // 3 + 1}"


def _year(period: str) -> str:
    return period[:4]


def _aggregate(values: list[float], method: str) -> float:
    if method == "sum":
        return sum(values)
    if method == "mean":
        return mean(values)
    if method == "last":
        return values[-1]
    raise ValueError(f"unsupported downsample method: {method}")


def _apply_unit_scale(
    candidates: list[dict[str, Any]],
    parameters: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    specification = parameters.get("unit_scale")
    if not specification:
        raise ValueError("unit_scale transformation parameters are required")
    multiplier = specification["multiplier"]
    output = []
    for item in candidates:
        scaled = dict(item)
        if item.get("value") is not None:
            scaled["value"] = item["value"] * multiplier
        scaled["unit"] = {
            "value": specification["to_unit"],
            "status": "transformed",
        }
        output.append(scaled)
    return output, {
        "type": "unit_scale",
        "formula": f"value * {multiplier}",
        **specification,
    }


def _downsample_settings(
    parameters: dict[str, Any],
) -> tuple[dict[str, Any], str, str, int]:
    specification = parameters.get("downsample")
    if not specification:
        raise ValueError("downsample transformation parameters are required")
    source = specification["source_frequency"]
    target = specification["target_frequency"]
    if (source, target) not in {("M", "Q"), ("M", "A"), ("Q", "A")}:
        raise ValueError(f"unsupported downsample path: {source}->{target}")
    expected = 3 if (source, target) == ("M", "Q") else 12
    if (source, target) == ("Q", "A"):
        expected = 4
    return specification, source, target, expected


def _downsample_groups(
    candidates: list[dict[str, Any]],
    source: str,
    target: str,
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    period_mapper = _quarter if target == "Q" else _year
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        if item.get("observed_frequency") != source:
            raise ValueError("downsample source frequency mismatch")
        groups[
            (
                str(item.get("series_key") or ""),
                period_mapper(str(item["time_raw"])),
            )
        ].append(item)
    return groups


def _aggregate_period(
    period: str,
    items: list[dict[str, Any]],
    target: str,
    expected_count: int,
    method: str,
) -> dict[str, Any]:
    ordered = sorted(items, key=lambda item: str(item["time_raw"]))
    if len(ordered) != expected_count:
        raise ValueError(
            f"incomplete downsample period {period}: expected {expected_count}, got {len(ordered)}"
        )
    values = [item["value"] for item in ordered]
    if any(value is None for value in values):
        raise ValueError(f"downsample period contains missing values: {period}")
    aggregated = dict(ordered[-1])
    aggregated["time_raw"] = period
    aggregated["time_grain"] = "quarter" if target == "Q" else "year"
    aggregated["observed_frequency"] = target
    aggregated["value"] = _aggregate(values, method)
    return aggregated


def _apply_downsample(
    candidates: list[dict[str, Any]],
    parameters: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    specification, source, target, expected_count = _downsample_settings(parameters)
    groups = _downsample_groups(candidates, source, target)
    output = [
        _aggregate_period(
            period,
            items,
            target,
            expected_count,
            specification["method"],
        )
        for (_, period), items in sorted(groups.items())
    ]
    return output, {"type": "downsample", **specification}


def apply_transformations(
    request: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    transformed = candidates
    records: list[dict[str, Any]] = []
    requested = request["transformation_policy"]["requested_transformations"]
    parameters = request.get("transformation_parameters") or {}

    if "unit_scale" in requested:
        transformed, record = _apply_unit_scale(transformed, parameters)
        records.append(record)

    if "downsample" in requested:
        transformed, record = _apply_downsample(transformed, parameters)
        records.append(record)

    return transformed, records
