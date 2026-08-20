"""Detect ambiguity, conflicting variants, and duplicate observations."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any


def _variant_issues(selected: list[dict[str, Any]]) -> set[str]:
    issues: set[str] = set()
    by_pair: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for item in selected:
        pair = (item.get("entity_code"), item.get("indicator_code"))
        by_pair.setdefault(pair, []).append(item)

    for items in by_pair.values():
        for field, code in (
            ("unit", "unit_conflict"),
            ("seasonal_adjustment", "seasonal_adjustment_conflict"),
            ("price_basis", "price_basis_conflict"),
        ):
            values = {
                json.dumps(
                    item[field].get("value"),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                for item in items
                if item[field].get("status") in {"source_provided", "source_documented"}
                and item[field].get("value") is not None
            }
            if len(values) > 1:
                issues.add(code)
        if any(item.get("entity_mapping_status") == "conflict" for item in items):
            issues.add("entity_mapping_conflict")

    if any(item.get("value") is None for item in selected):
        issues.add("missing_values")
    if any(
        str(item.get("obs_status") or "").lower() in {"b", "break", "suppressed", "s"}
        for item in selected
    ):
        issues.add("structural_break")

    period_values: dict[tuple[Any, Any, Any], set[tuple[Any, Any]]] = {}
    for item in selected:
        key = (
            item.get("entity_code"),
            item.get("indicator_code"),
            item.get("time_raw"),
        )
        period_values.setdefault(key, set()).add((item.get("source_system"), item.get("value")))
    if any(
        len({source for source, _ in values}) > 1 and len({value for _, value in values}) > 1
        for values in period_values.values()
    ):
        issues.add("cross_source_conflict")
    return issues


def _ambiguity_issues(selected: list[dict[str, Any]]) -> set[str]:
    identities_by_pair: dict[tuple[Any, Any], set[tuple[Any, ...]]] = {}
    sources_by_pair: dict[tuple[Any, Any], set[Any]] = {}
    for item in selected:
        pair = (item.get("entity_code"), item.get("indicator_code"))
        identities_by_pair.setdefault(pair, set()).add(
            (
                item.get("source_system"),
                item.get("dataset_id"),
                item.get("series_key"),
            )
        )
        sources_by_pair.setdefault(pair, set()).add(item.get("source_system"))
    if any(
        len(identities) > 1 and len(sources_by_pair[pair]) == 1
        for pair, identities in identities_by_pair.items()
    ):
        return {"indicator_ambiguity"}
    return set()


def conflict_issues(selected: list[dict[str, Any]]) -> set[str]:
    issues = _variant_issues(selected) | _ambiguity_issues(selected)
    keys = [(item.get("series_key"), item.get("time_raw")) for item in selected]
    if any(count > 1 for count in Counter(keys).values()):
        issues.add("duplicate_observation")
    return issues
