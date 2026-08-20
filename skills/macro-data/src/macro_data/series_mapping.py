"""Resolve exact series identity and validate provider overlaps."""

from __future__ import annotations

import copy
import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from macro_data.observation_matrix import (
    CanonicalObservationKey,
    ExpectedObservationMatrix,
)
from macro_data.primary_cell_ledger import (
    LockedObservation,
    PrimaryCellLedger,
)
from macro_data.provenance import canonical_json

MappingStatus = Literal[
    "exact_native",
    "approved_mapping",
    "rejected",
]


@dataclass(frozen=True, slots=True)
class SeriesIdentityMapping:
    mapping_id: str
    source_system: str
    primary_native_series_key: str
    fallback_native_series_key: str
    canonical_series_id: str
    status: MappingStatus
    mapping_version: str


@dataclass(frozen=True, slots=True)
class OverlapValidation:
    status: Literal["verified", "conflicted", "not_run"]
    compared_periods: tuple[str, ...]
    maximum_absolute_error: float | None
    maximum_relative_error: float | None
    issue_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OfficialMappingResult:
    fallback: tuple[LockedObservation, ...]
    validation_overlaps: tuple[LockedObservation, ...]
    issue_codes: tuple[str, ...]


def resolve_series_mapping(
    primary: dict[str, Any],
    fallback: dict[str, Any],
    approved: Sequence[SeriesIdentityMapping] = (),
) -> SeriesIdentityMapping:
    """Map only exact native identities or a versioned explicit approval."""
    approved_mapping = _approved_mapping(primary, fallback, approved)
    if approved_mapping is not None:
        return approved_mapping

    exact = _identity_document(primary) == _identity_document(fallback)
    status: MappingStatus = "exact_native" if exact else "rejected"
    source_system = str(primary.get("source_system") or "")
    primary_key = str(primary.get("series_key") or "")
    fallback_key = str(fallback.get("series_key") or "")
    identity = {
        "primary": _identity_document(primary),
        "fallback": _identity_document(fallback),
        "status": status,
    }
    canonical_series_id = str(
        primary.get("canonical_series_id")
        or "macro-series-" + _digest(_identity_document(primary))[:32]
    )
    return SeriesIdentityMapping(
        mapping_id="series-map-" + _digest(identity)[:32],
        source_system=source_system,
        primary_native_series_key=primary_key,
        fallback_native_series_key=fallback_key,
        canonical_series_id=canonical_series_id,
        status=status,
        mapping_version="exact-native-v1" if exact else "unmapped-v1",
    )


def validate_overlap(
    primary: Sequence[LockedObservation],
    fallback: Sequence[LockedObservation],
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> OverlapValidation:
    """Compare shared canonical cells without selecting replacement values."""
    if absolute_tolerance < 0 or relative_tolerance < 0:
        raise ValueError("overlap tolerances must be non-negative")
    primary_by_key = {item.key: item for item in primary}
    fallback_by_key = {item.key: item for item in fallback}
    shared = sorted(
        primary_by_key.keys() & fallback_by_key.keys(),
        key=lambda key: (
            key.indicator_code,
            key.entity_code,
            key.period,
            key.frequency,
        ),
    )
    if not shared:
        return OverlapValidation(
            status="not_run",
            compared_periods=(),
            maximum_absolute_error=None,
            maximum_relative_error=None,
            issue_codes=("overlap_not_available",),
        )

    errors = [
        _errors(primary_by_key[key].value, fallback_by_key[key].value)
        for key in shared
    ]
    conflicted = any(
        not math.isfinite(absolute)
        or not math.isfinite(relative)
        or (absolute > absolute_tolerance and relative > relative_tolerance)
        for absolute, relative in errors
    )
    return OverlapValidation(
        status="conflicted" if conflicted else "verified",
        compared_periods=tuple(sorted({key.period for key in shared})),
        maximum_absolute_error=max(absolute for absolute, _ in errors),
        maximum_relative_error=max(relative for _, relative in errors),
        issue_codes=("overlap_value_conflict",) if conflicted else (),
    )


def map_official_candidates(
    *,
    candidates: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    allowed_periods: set[str],
    matrix: ExpectedObservationMatrix,
    primary: PrimaryCellLedger,
) -> OfficialMappingResult:
    """Map selected gaps and overlap anchors without replacing primary cells."""
    selected_ids = {id(item) for item in selected}
    primary_by_key = primary.by_key()
    fallback: list[LockedObservation] = []
    validations: list[LockedObservation] = []
    issues: set[str] = set()
    for item in candidates:
        key = candidate_key(item)
        if key in primary_by_key:
            mapping = resolve_series_mapping(primary_by_key[key].item, item)
            if mapping.status == "rejected":
                issues.add("cross_source_mapping_rejected")
                continue
            observation = _locked_official(
                item,
                matrix,
                canonical_series_id=mapping.canonical_series_id,
                origin_role="validation_overlap",
            )
            if observation is not None:
                validations.append(observation)
            continue
        if id(item) not in selected_ids or key.period not in allowed_periods:
            continue
        canonical_id = _canonical_series_id(item, primary)
        if canonical_id is None:
            issues.add("cross_source_mapping_rejected")
            continue
        observation = _locked_official(
            item,
            matrix,
            canonical_series_id=canonical_id,
            origin_role="official_missing_only",
        )
        if observation is None:
            issues.add("official_value_invalid")
            continue
        fallback.append(observation)
    return OfficialMappingResult(
        fallback=tuple(fallback),
        validation_overlaps=tuple(validations),
        issue_codes=tuple(sorted(issues)),
    )


def candidate_key(item: dict[str, Any]) -> CanonicalObservationKey:
    return CanonicalObservationKey(
        indicator_code=str(item.get("indicator_code") or ""),
        entity_code=str(item.get("entity_code") or ""),
        period=str(item.get("time_raw") or "").replace("-Q", "Q"),
        frequency=str(item.get("observed_frequency") or ""),
    )


def _canonical_series_id(
    item: dict[str, Any],
    primary: PrimaryCellLedger,
) -> str | None:
    candidates = [
        locked
        for locked in primary.locked
        if locked.key.entity_code == item.get("entity_code")
        and locked.key.indicator_code == item.get("indicator_code")
        and locked.key.frequency == item.get("observed_frequency")
    ]
    if candidates:
        mapping = resolve_series_mapping(candidates[0].item, item)
        return mapping.canonical_series_id if mapping.status != "rejected" else None
    identity = {
        "source_system": item.get("source_system"),
        "dataset_id": item.get("dataset_id"),
        "series_key": item.get("series_key"),
    }
    return "macro-series-" + _digest(identity)[:32]


def _locked_official(
    item: dict[str, Any],
    matrix: ExpectedObservationMatrix,
    *,
    canonical_series_id: str,
    origin_role: str,
) -> LockedObservation | None:
    value = item.get("value")
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        return None
    key = candidate_key(item)
    cell_ids = {cell.key: cell.cell_id for cell in matrix.cells}
    if key not in cell_ids:
        return None
    return LockedObservation(
        cell_id=cell_ids[key],
        key=key,
        value=float(value),
        retrieval_provider=str(item.get("retrieval_provider") or item.get("provider")),
        source_system=str(item.get("source_system") or ""),
        dataset_id=str(item.get("dataset_id") or ""),
        native_series_key=str(item.get("series_key") or ""),
        canonical_series_id=canonical_series_id,
        origin_role=origin_role,
        raw_artifact=str(item.get("raw_artifact") or ""),
        raw_checksum=str(item.get("raw_checksum") or ""),
        retrieved_at=(
            str(item["retrieved_at"]) if item.get("retrieved_at") is not None else None
        ),
        item=copy.deepcopy(item),
    )


def _approved_mapping(
    primary: dict[str, Any],
    fallback: dict[str, Any],
    approved: Sequence[SeriesIdentityMapping],
) -> SeriesIdentityMapping | None:
    source = str(primary.get("source_system") or "")
    if source != str(fallback.get("source_system") or ""):
        return None
    primary_key = str(primary.get("series_key") or "")
    fallback_key = str(fallback.get("series_key") or "")
    return next(
        (
            mapping
            for mapping in approved
            if mapping.status == "approved_mapping"
            and mapping.source_system == source
            and mapping.primary_native_series_key == primary_key
            and mapping.fallback_native_series_key == fallback_key
        ),
        None,
    )


def _identity_document(item: dict[str, Any]) -> dict[str, object]:
    return {
        "source_system": item.get("source_system"),
        "dataset_id": item.get("dataset_id"),
        "dataset_name": item.get("dataset_name"),
        "native_series_key": item.get("series_key"),
        "indicator_code": item.get("indicator_code"),
        "entity_code": item.get("entity_code"),
        "frequency": item.get("observed_frequency") or item.get("frequency"),
        "unit": _metadata_value(item, "unit"),
        "seasonal_adjustment": _metadata_value(item, "seasonal_adjustment"),
        "price_basis": _metadata_value(item, "price_basis"),
    }


def _metadata_value(item: dict[str, Any], field: str) -> object:
    metadata = item.get(field)
    return metadata.get("value") if isinstance(metadata, dict) else metadata


def _errors(primary: float, fallback: float) -> tuple[float, float]:
    absolute = abs(primary - fallback)
    denominator = max(abs(primary), abs(fallback), 1e-15)
    return absolute, absolute / denominator


def _digest(document: object) -> str:
    return hashlib.sha256(canonical_json(document)).hexdigest()
