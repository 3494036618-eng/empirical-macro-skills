"""Assemble estimator cells with immutable DataPro precedence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from macro_data.observation_matrix import (
    CanonicalObservationKey,
    ExpectedObservationMatrix,
)
from macro_data.primary_cell_ledger import (
    LockedObservation,
    PrimaryCellLedger,
)
from macro_data.series_mapping import OverlapValidation

ContributionClass = Literal[
    "datapro_only",
    "datapro_primary",
    "datapro_assisted",
    "datapro_attempted",
]


@dataclass(frozen=True, slots=True)
class ProviderContribution:
    classification: ContributionClass
    datapro_count: int
    official_fallback_count: int
    unresolved_count: int
    datapro_ratio: float
    official_fallback_ratio: float


@dataclass(frozen=True, slots=True)
class CompletionResult:
    matrix: ExpectedObservationMatrix
    observations: tuple[LockedObservation, ...]
    validation_overlaps: tuple[LockedObservation, ...]
    overlap_results: tuple[OverlapValidation, ...]
    contribution: ProviderContribution
    residual_gap_count: int
    conflict_count: int
    issue_codes: tuple[str, ...]


def classify_contribution(
    datapro: int,
    official: int,
    *,
    datapro_attempted: bool,
) -> ContributionClass:
    """Classify provider contribution using estimator observations only."""
    if datapro < 0 or official < 0:
        raise ValueError("provider counts must be non-negative")
    total = datapro + official
    ratio = datapro / total if total else 0.0
    if total and datapro == total:
        return "datapro_only"
    if ratio >= 0.8:
        return "datapro_primary"
    if datapro:
        return "datapro_assisted"
    if datapro_attempted:
        return "datapro_attempted"
    raise ValueError("zero DataPro observations require an attempted retrieval")


def assemble_completion(
    *,
    matrix: ExpectedObservationMatrix,
    primary: PrimaryCellLedger,
    fallback: Sequence[LockedObservation],
    overlaps: Sequence[OverlapValidation],
) -> CompletionResult:
    """Fill absent cells while preserving primary observations."""
    if primary.matrix_id != matrix.matrix_id:
        raise ValueError("primary ledger matrix_id does not match matrix")
    matrix_keys = matrix.keys()
    primary_by_key = primary.by_key()
    validation = tuple(
        item for item in fallback if item.origin_role == "validation_overlap"
    )
    conflict_keys = _conflict_keys(matrix, primary, validation, overlaps)
    issues = set(primary.issue_codes)
    issues.update(
        issue
        for overlap in overlaps
        for issue in overlap.issue_codes
    )
    estimator: dict[CanonicalObservationKey, LockedObservation] = {
        key: item
        for key, item in primary_by_key.items()
        if key not in conflict_keys
    }
    fallback_groups = _fallback_groups(
        fallback,
        matrix_keys=matrix_keys,
        primary_keys=set(primary_by_key),
        conflict_keys=conflict_keys,
        issues=issues,
    )
    for key, candidates in fallback_groups.items():
        if len(candidates) > 1:
            conflict_keys.add(key)
            issues.add(_fallback_duplicate_issue(candidates))
            continue
        estimator[key] = candidates[0]

    for key in conflict_keys:
        estimator.pop(key, None)
    observations = tuple(sorted(estimator.values(), key=_observation_sort_key))
    contribution = _contribution(matrix, observations)
    return CompletionResult(
        matrix=matrix,
        observations=observations,
        validation_overlaps=tuple(
            sorted(validation, key=_observation_sort_key)
        ),
        overlap_results=tuple(overlaps),
        contribution=contribution,
        residual_gap_count=len(matrix_keys - set(estimator)),
        conflict_count=len(conflict_keys),
        issue_codes=tuple(sorted(issues)),
    )


def _fallback_groups(
    fallback: Sequence[LockedObservation],
    *,
    matrix_keys: frozenset[CanonicalObservationKey],
    primary_keys: set[CanonicalObservationKey],
    conflict_keys: set[CanonicalObservationKey],
    issues: set[str],
) -> dict[CanonicalObservationKey, list[LockedObservation]]:
    groups: dict[CanonicalObservationKey, list[LockedObservation]] = {}
    for item in fallback:
        if item.origin_role == "validation_overlap":
            continue
        if item.key not in matrix_keys:
            issues.add("fallback_cell_outside_matrix")
            continue
        if item.key in conflict_keys:
            continue
        if item.key in primary_keys:
            issues.add("fallback_attempted_primary_replacement")
            continue
        if item.origin_role != "official_missing_only":
            issues.add("fallback_origin_role_invalid")
            continue
        groups.setdefault(item.key, []).append(item)
    return groups


def _conflict_keys(
    matrix: ExpectedObservationMatrix,
    primary: PrimaryCellLedger,
    validation: tuple[LockedObservation, ...],
    overlaps: Sequence[OverlapValidation],
) -> set[CanonicalObservationKey]:
    periods = {
        period
        for overlap in overlaps
        if overlap.status == "conflicted"
        for period in overlap.compared_periods
    }
    keys = {item.key for item in validation if item.key.period in periods}
    if periods and not keys:
        keys.update(cell.key for cell in matrix.cells if cell.key.period in periods)
    keys.update(_primary_conflict_keys(primary))
    return keys


def _primary_conflict_keys(
    primary: PrimaryCellLedger,
) -> set[CanonicalObservationKey]:
    keys: set[CanonicalObservationKey] = set()
    for rejection in primary.rejected:
        reasons = rejection.get("reason_codes")
        item = rejection.get("item")
        if (
            not isinstance(reasons, list)
            or "datapro_cell_value_conflict" not in reasons
            or not isinstance(item, dict)
        ):
            continue
        keys.add(_item_key(item))
    return keys


def _item_key(item: dict[object, object]) -> CanonicalObservationKey:
    return CanonicalObservationKey(
        indicator_code=str(item.get("indicator_code") or ""),
        entity_code=str(item.get("entity_code") or ""),
        period=str(item.get("time_raw") or "").replace("-Q", "Q"),
        frequency=str(item.get("observed_frequency") or ""),
    )


def _fallback_duplicate_issue(
    candidates: list[LockedObservation],
) -> str:
    values = {item.value for item in candidates}
    return (
        "fallback_cell_value_conflict"
        if len(values) > 1
        else "fallback_cell_duplicate"
    )


def _contribution(
    matrix: ExpectedObservationMatrix,
    observations: tuple[LockedObservation, ...],
) -> ProviderContribution:
    datapro = sum(item.origin_role == "datapro_primary" for item in observations)
    official = sum(
        item.origin_role == "official_missing_only" for item in observations
    )
    total = datapro + official
    return ProviderContribution(
        classification=classify_contribution(
            datapro,
            official,
            datapro_attempted=True,
        ),
        datapro_count=datapro,
        official_fallback_count=official,
        unresolved_count=len(matrix.cells) - total,
        datapro_ratio=datapro / total if total else 0.0,
        official_fallback_ratio=official / total if total else 0.0,
    )


def _observation_sort_key(
    item: LockedObservation,
) -> tuple[str, str, str, str]:
    key = item.key
    return (key.indicator_code, key.entity_code, key.period, key.frequency)
