"""Lock eligible DataPro observations without permitting later replacement."""

from __future__ import annotations

import copy
import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any, cast

from macro_data.metadata_gate import metadata_issues
from macro_data.observation_matrix import (
    CanonicalObservationKey,
    ExpectedObservationMatrix,
)
from macro_data.provenance import canonical_json
from macro_data.semantic_constraints import request_constraint_issues

_ARTIFACT = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")
_CHECKSUM = re.compile(r"^sha256:[a-f0-9]{64}$")


@dataclass(frozen=True, slots=True)
class LockedObservation:
    cell_id: str
    key: CanonicalObservationKey
    value: float
    retrieval_provider: str
    source_system: str
    dataset_id: str
    native_series_key: str
    canonical_series_id: str
    origin_role: str
    raw_artifact: str
    raw_checksum: str
    retrieved_at: str | None
    item: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PrimaryCellLedger:
    matrix_id: str
    locked: tuple[LockedObservation, ...]
    rejected: tuple[dict[str, object], ...]
    issue_codes: tuple[str, ...]

    def by_key(self) -> dict[CanonicalObservationKey, LockedObservation]:
        return {observation.key: observation for observation in self.locked}


def lock_datapro_cells(
    *,
    request: dict[str, Any],
    matrix: ExpectedObservationMatrix,
    evaluation: dict[str, Any],
) -> PrimaryCellLedger:
    """Lock unique, exact, physically bound DataPro observations."""
    items = copy.deepcopy(
        cast(list[dict[str, Any]], evaluation.get("selected_items", []))
    )
    cell_ids = {cell.key: cell.cell_id for cell in matrix.cells}
    rejected: list[dict[str, object]] = []
    eligible: dict[CanonicalObservationKey, list[dict[str, Any]]] = {}
    for item in items:
        key = _key(item)
        reasons = _candidate_reasons(request, matrix, item, key)
        if reasons:
            rejected.append(_rejection(item, reasons))
            continue
        eligible.setdefault(key, []).append(item)

    locked: list[LockedObservation] = []
    issues: set[str] = set()
    for key, candidates in eligible.items():
        if len(candidates) > 1:
            issue = _duplicate_issue(candidates)
            issues.add(issue)
            rejected.extend(_rejection(item, (issue,)) for item in candidates)
            continue
        locked.append(_locked(cell_ids[key], key, candidates[0]))

    return PrimaryCellLedger(
        matrix_id=matrix.matrix_id,
        locked=tuple(sorted(locked, key=_locked_sort_key)),
        rejected=tuple(rejected),
        issue_codes=tuple(sorted(issues)),
    )


def _candidate_reasons(
    request: dict[str, Any],
    matrix: ExpectedObservationMatrix,
    item: dict[str, Any],
    key: CanonicalObservationKey,
) -> tuple[str, ...]:
    reasons: set[str] = set()
    entities = {
        cast(str, entity["name_or_code"])
        for entity in cast(list[dict[str, Any]], request["entities"])
    }
    indicators = {
        cast(str, indicator["name_or_code"])
        for indicator in cast(list[dict[str, Any]], request["indicators"])
    }
    if item.get("retrieval_provider", item.get("provider")) != "datapro":
        reasons.add("retrieval_provider_mismatch")
    if key.entity_code not in entities:
        reasons.add("entity_mismatch")
    if key.indicator_code not in indicators:
        reasons.add("indicator_mismatch")
    if key.frequency != request["frequency"]:
        reasons.add("frequency_mismatch")
    if (
        key.entity_code in entities
        and key.indicator_code in indicators
        and key.frequency == request["frequency"]
        and key not in matrix.keys()
    ):
        reasons.add("period_outside_matrix")
    reasons.update(_value_reasons(item))
    reasons.update(_physical_binding_reasons(item))
    reasons.update(_native_identity_reasons(request, item))
    if _metadata_shape_complete(item):
        reasons.update(metadata_issues(request, [item]))
        reasons.update(request_constraint_issues(request, [item]))
    else:
        reasons.add("metadata_insufficient")
    return tuple(sorted(reasons))


def _value_reasons(item: dict[str, Any]) -> set[str]:
    value = item.get("value")
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        return {"non_finite_value"}
    return set()


def _physical_binding_reasons(item: dict[str, Any]) -> set[str]:
    reasons: set[str] = set()
    artifact = item.get("raw_artifact")
    checksum = item.get("raw_checksum")
    if not artifact:
        reasons.add("raw_artifact_missing")
    elif not isinstance(artifact, str) or not _ARTIFACT.fullmatch(artifact):
        reasons.add("raw_artifact_invalid")
    if not isinstance(checksum, str) or not _CHECKSUM.fullmatch(checksum):
        reasons.add("raw_checksum_invalid")
    return reasons


def _native_identity_reasons(
    request: dict[str, Any],
    item: dict[str, Any],
) -> set[str]:
    reasons = {
        code
        for field, code in (
            ("source_system", "source_system_missing"),
            ("dataset_id", "dataset_id_missing"),
            ("series_key", "native_series_key_missing"),
        )
        if not item.get(field)
    }
    constraints = cast(
        list[dict[str, Any]],
        request.get("native_source_constraints") or [],
    )
    if constraints and not any(_constraint_matches(constraint, item) for constraint in constraints):
        reasons.add("native_series_identity_mismatch")
    return reasons


def _constraint_matches(
    constraint: dict[str, Any],
    item: dict[str, Any],
) -> bool:
    return all(
        constraint.get(field) in (None, item.get(field))
        for field in ("source_system", "dataset_name", "indicator_code")
    )


def _metadata_shape_complete(item: dict[str, Any]) -> bool:
    return all(
        isinstance(item.get(field), dict)
        and isinstance(cast(dict[str, Any], item[field]).get("status"), str)
        for field in (
            "unit",
            "seasonal_adjustment",
            "price_basis",
            "definition",
            "release_date",
            "vintage",
        )
    )


def _key(item: dict[str, Any]) -> CanonicalObservationKey:
    return CanonicalObservationKey(
        indicator_code=str(item.get("indicator_code") or ""),
        entity_code=str(item.get("entity_code") or ""),
        period=str(item.get("time_raw") or "").replace("-Q", "Q"),
        frequency=str(item.get("observed_frequency") or ""),
    )


def _locked(
    cell_id: str,
    key: CanonicalObservationKey,
    item: dict[str, Any],
) -> LockedObservation:
    identity = {
        "source_system": item["source_system"],
        "dataset_id": item["dataset_id"],
        "native_series_key": item["series_key"],
    }
    canonical_series_id = str(
        item.get("canonical_series_id")
        or "macro-series-" + hashlib.sha256(canonical_json(identity)).hexdigest()[:32]
    )
    return LockedObservation(
        cell_id=cell_id,
        key=key,
        value=float(item["value"]),
        retrieval_provider="datapro",
        source_system=str(item["source_system"]),
        dataset_id=str(item["dataset_id"]),
        native_series_key=str(item["series_key"]),
        canonical_series_id=canonical_series_id,
        origin_role="datapro_primary",
        raw_artifact=str(item["raw_artifact"]),
        raw_checksum=str(item["raw_checksum"]),
        retrieved_at=(
            str(item["retrieved_at"]) if item.get("retrieved_at") is not None else None
        ),
        item=copy.deepcopy(item),
    )


def _duplicate_issue(candidates: list[dict[str, Any]]) -> str:
    values = {float(item["value"]) for item in candidates}
    return (
        "datapro_cell_value_conflict"
        if len(values) > 1
        else "datapro_cell_duplicate"
    )


def _rejection(
    item: dict[str, Any],
    reasons: tuple[str, ...],
) -> dict[str, object]:
    return {
        "item": copy.deepcopy(item),
        "reason_codes": list(reasons),
    }


def _locked_sort_key(observation: LockedObservation) -> tuple[str, str, str, str]:
    key = observation.key
    return (key.indicator_code, key.entity_code, key.period, key.frequency)
