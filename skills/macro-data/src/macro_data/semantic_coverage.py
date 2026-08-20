"""Measure entity, indicator, and period coverage without shrinking scope."""

from __future__ import annotations

from typing import Any

from macro_data.semantic_identity import period_key


def expected_periods(start: str, end: str, frequency: str) -> set[str]:
    if frequency == "A":
        return {str(year) for year in range(int(start[:4]), int(end[:4]) + 1)}
    if frequency == "Q":
        first = period_key(start.replace("-Q", "Q"), "Q")
        last = period_key(end.replace("-Q", "Q"), "Q")
        return {f"{index // 4}Q{index % 4 + 1}" for index in range(first, last + 1)}
    if frequency == "M":
        first = period_key(start, "M")
        last = period_key(end, "M")
        return {f"{index // 12:04d}-{index % 12 + 1:02d}" for index in range(first, last + 1)}
    raise ValueError(f"unsupported Beta frequency: {frequency}")


def _missing_periods_summary(periods: set[str]) -> str:
    ordered = sorted(periods)
    if len(ordered) <= 12:
        return ",".join(ordered)
    return f"count={len(ordered)};first={ordered[0]};last={ordered[-1]}"


def build_coverage(
    requested_pairs: set[tuple[str, str]],
    selected: list[dict[str, Any]],
    *,
    start: str,
    end: str,
    frequency: str,
) -> tuple[dict[str, Any], bool]:
    delivered_pairs = {(item.get("entity_code"), item.get("indicator_code")) for item in selected}
    failures = {f"{entity}|{indicator}" for entity, indicator in requested_pairs - delivered_pairs}
    expected = expected_periods(start, end, frequency)
    periods_by_pair: dict[tuple[str, str], set[str]] = {pair: set() for pair in requested_pairs}
    for item in selected:
        pair = (item.get("entity_code"), item.get("indicator_code"))
        if pair in periods_by_pair and item.get("observed_frequency") == frequency:
            periods_by_pair[pair].add(str(item.get("time_raw")).replace("-Q", "Q"))

    coverage_incomplete = any(periods != expected for periods in periods_by_pair.values())
    failures.update(
        (f"{entity}|{indicator}|missing:" + _missing_periods_summary(expected - periods))
        for (entity, indicator), periods in periods_by_pair.items()
        if (entity, indicator) in delivered_pairs and periods != expected
    )
    return {
        "complete": not failures and not coverage_incomplete,
        "scope_reduced": False,
        "requested_count": len(requested_pairs),
        "delivered_count": len(requested_pairs & delivered_pairs),
        "failures": sorted(failures),
    }, coverage_incomplete
