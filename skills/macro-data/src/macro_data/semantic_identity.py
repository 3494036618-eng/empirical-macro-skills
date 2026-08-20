"""Filter provider candidates against requested series identity."""

from __future__ import annotations

import re
from typing import Any


def period_key(period: str, frequency: str) -> int:
    year = int(period[:4])
    if frequency == "A":
        return year
    if frequency == "Q":
        match = re.search(r"Q([1-4])", period)
        return year * 4 + int(match.group(1)) - 1 if match else year * 4
    if frequency == "M":
        match = re.search(r"-(\d{2})$", period)
        return year * 12 + int(match.group(1)) - 1 if match else year * 12
    return year


def period_in_range(
    period: str | None,
    start: str,
    end: str,
    observed_frequency: str | None,
    requested_frequency: str,
) -> bool:
    if not period:
        return False
    if observed_frequency == requested_frequency:
        return period_key(period, requested_frequency) >= period_key(
            start, requested_frequency
        ) and period_key(period, requested_frequency) <= period_key(end, requested_frequency)
    return int(start[:4]) <= int(period[:4]) <= int(end[:4])


def identity_reasons(
    candidate: dict[str, Any],
    *,
    entities: set[str],
    indicators: set[str],
    constraints: list[dict[str, Any]],
    start: str,
    end: str,
    requested_frequency: str,
    as_of: str | None,
) -> list[str]:
    reasons: list[str] = []
    if candidate.get("entity_code") not in entities:
        reasons.append("entity_mismatch")
    if indicators and candidate.get("indicator_code") not in indicators:
        reasons.append("indicator_mismatch")

    release_date = candidate.get("release_date") or {}
    if (
        as_of
        and release_date.get("status") == "source_provided"
        and release_date.get("value")
        and str(release_date["value"]) > as_of
    ):
        reasons.append("future_information_excluded")
    if not period_in_range(
        str(candidate.get("time_raw") or ""),
        start,
        end,
        candidate.get("observed_frequency"),
        requested_frequency,
    ):
        reasons.append("time_range_mismatch")

    matches = [
        (
            constraint.get("source_system") in (None, candidate.get("source_system"))
            and constraint.get("dataset_name") in (None, candidate.get("dataset_name"))
            and constraint.get("indicator_code") in (None, candidate.get("indicator_code"))
        )
        for constraint in constraints
    ]
    if constraints and not any(matches):
        expected_sources = {
            item.get("source_system") for item in constraints if item.get("source_system")
        }
        expected_datasets = {
            item.get("dataset_name") for item in constraints if item.get("dataset_name")
        }
        expected_indicators = {
            item.get("indicator_code") for item in constraints if item.get("indicator_code")
        }
        if expected_sources and candidate.get("source_system") not in expected_sources:
            reasons.append("source_mismatch")
        if expected_datasets and candidate.get("dataset_name") not in expected_datasets:
            reasons.append("dataset_mismatch")
        if expected_indicators and candidate.get("indicator_code") not in expected_indicators:
            reasons.append("indicator_mismatch")
    return reasons


def select_candidates(
    candidates: list[dict[str, Any]],
    *,
    entities: set[str],
    indicators: set[str],
    constraints: list[dict[str, Any]],
    start: str,
    end: str,
    requested_frequency: str,
    as_of: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    selected: list[dict[str, Any]] = []
    filtered: list[dict[str, Any]] = []
    issues: set[str] = set()
    for candidate in candidates:
        reasons = identity_reasons(
            candidate,
            entities=entities,
            indicators=indicators,
            constraints=constraints,
            start=start,
            end=end,
            requested_frequency=requested_frequency,
            as_of=as_of,
        )
        if reasons:
            filtered.append(
                {
                    "series_key": candidate.get("series_key"),
                    "entity_code": candidate.get("entity_code"),
                    "indicator_code": candidate.get("indicator_code"),
                    "source_system": candidate.get("source_system"),
                    "dataset_name": candidate.get("dataset_name"),
                    "time_raw": candidate.get("time_raw"),
                    "reasons": sorted(set(reasons)),
                }
            )
            issues.update(reasons)
            continue
        candidate["requested_frequency"] = requested_frequency
        selected.append(candidate)

    if any("entity_mismatch" in item["reasons"] for item in filtered):
        issues.add("entity_candidates_filtered")
    return selected, filtered, issues
