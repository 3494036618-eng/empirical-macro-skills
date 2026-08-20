"""Derive exact missing cells and safe official fallback requests."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from typing import Any, Literal, cast

from macro_data.contracts import validate_document
from macro_data.observation_matrix import (
    CanonicalObservationKey,
    ExpectedObservationMatrix,
)
from macro_data.primary_cell_ledger import PrimaryCellLedger
from macro_data.provenance import canonical_json
from macro_data.semantic_identity import period_key
from macro_data.source_router import RoutePlan

GapReason = Literal[
    "empty_result",
    "unsupported_query",
    "period_missing",
    "exact_candidate_missing",
    "metadata_insufficient",
    "provider_error",
    "license_or_use_not_authorized",
    "identity_ambiguity",
]


@dataclass(frozen=True, slots=True)
class GapCell:
    cell_id: str
    key: CanonicalObservationKey
    reason: GapReason

    def as_document(self) -> dict[str, object]:
        return {
            "cell_id": self.cell_id,
            "key": self.key.as_document(),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class OfficialGapRequest:
    gap_request_id: str
    provider: str
    entity_code: str
    indicator_code: str
    periods: tuple[str, ...]
    research_request: dict[str, Any]

    def as_document(self) -> dict[str, object]:
        return {
            "gap_request_id": self.gap_request_id,
            "provider": self.provider,
            "entity_code": self.entity_code,
            "indicator_code": self.indicator_code,
            "periods": list(self.periods),
            "research_request": copy.deepcopy(self.research_request),
        }


@dataclass(frozen=True, slots=True)
class ResidualGapManifest:
    schema_version: str
    gap_manifest_id: str
    matrix_id: str
    datapro_locked_cell_ids: tuple[str, ...]
    gap_cells: tuple[GapCell, ...]
    official_requests: tuple[OfficialGapRequest, ...]
    issue_codes: tuple[str, ...]

    def as_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "gap_manifest_id": self.gap_manifest_id,
            "matrix_id": self.matrix_id,
            "datapro_locked_cell_ids": list(self.datapro_locked_cell_ids),
            "gap_cells": [cell.as_document() for cell in self.gap_cells],
            "official_requests": [
                request.as_document() for request in self.official_requests
            ],
            "issue_codes": list(self.issue_codes),
        }


def build_residual_gaps(
    *,
    request: dict[str, Any],
    matrix: ExpectedObservationMatrix,
    primary: PrimaryCellLedger,
    route_plan: RoutePlan,
) -> ResidualGapManifest:
    """Build missing-only official requests without any primary cell."""
    if primary.matrix_id != matrix.matrix_id:
        raise ValueError("primary ledger matrix_id does not match matrix")
    locked = primary.by_key()
    gaps = tuple(
        GapCell(
            cell_id=cell.cell_id,
            key=cell.key,
            reason=_gap_reason(cell.key, primary),
        )
        for cell in matrix.cells
        if cell.key not in locked
    )
    issues = _policy_issues(gaps, route_plan)
    official_requests = (
        _official_requests(request, matrix.matrix_id, gaps, route_plan)
        if gaps and not issues
        else ()
    )
    locked_ids = tuple(
        cell.cell_id for cell in matrix.cells if cell.key in locked
    )
    identity = {
        "matrix_id": matrix.matrix_id,
        "datapro_locked_cell_ids": locked_ids,
        "gap_cells": [cell.as_document() for cell in gaps],
        "official_requests": [item.as_document() for item in official_requests],
        "issue_codes": issues,
    }
    manifest = ResidualGapManifest(
        schema_version="0.3.0-beta",
        gap_manifest_id="macro-gaps-" + _digest(identity)[:32],
        matrix_id=matrix.matrix_id,
        datapro_locked_cell_ids=locked_ids,
        gap_cells=gaps,
        official_requests=official_requests,
        issue_codes=issues,
    )
    validate_document("residual_gap_manifest", manifest.as_document())
    return manifest


def _policy_issues(
    gaps: tuple[GapCell, ...],
    route_plan: RoutePlan,
) -> tuple[str, ...]:
    if not gaps:
        return ()
    if route_plan.fallback_mode == "never":
        return ("fallback_disabled",)
    if route_plan.fallback_mode == "ask" or route_plan.review_required:
        return ("fallback_approval_required",)
    if route_plan.fallback_mode not in {
        "allow_official",
        "allow_official_missing_only",
    }:
        return ("fallback_disabled",)
    if not route_plan.fallback_candidates:
        return ("connector_unavailable",)
    return ()


def _official_requests(
    request: dict[str, Any],
    matrix_id: str,
    gaps: tuple[GapCell, ...],
    route_plan: RoutePlan,
) -> tuple[OfficialGapRequest, ...]:
    provider = route_plan.fallback_candidates[0]
    grouped: dict[tuple[str, str, str], list[GapCell]] = {}
    for gap in gaps:
        group_key = (
            gap.key.entity_code,
            gap.key.indicator_code,
            gap.key.frequency,
        )
        grouped.setdefault(group_key, []).append(gap)

    requests: list[OfficialGapRequest] = []
    for group_key, cells in sorted(grouped.items()):
        ordered = sorted(
            cells,
            key=lambda cell: period_key(cell.key.period, cell.key.frequency),
        )
        for window in _contiguous_windows(ordered):
            requests.append(
                _official_request(
                    request=request,
                    matrix_id=matrix_id,
                    provider=provider,
                    cells=window,
                    group_key=group_key,
                )
            )
    return tuple(requests)


def _contiguous_windows(cells: list[GapCell]) -> tuple[tuple[GapCell, ...], ...]:
    windows: list[list[GapCell]] = []
    for cell in cells:
        if not windows or not _is_next(windows[-1][-1], cell):
            windows.append([cell])
        else:
            windows[-1].append(cell)
    return tuple(tuple(window) for window in windows)


def _is_next(previous: GapCell, current: GapCell) -> bool:
    return period_key(current.key.period, current.key.frequency) == (
        period_key(previous.key.period, previous.key.frequency) + 1
    )


def _official_request(
    *,
    request: dict[str, Any],
    matrix_id: str,
    provider: str,
    cells: tuple[GapCell, ...],
    group_key: tuple[str, str, str],
) -> OfficialGapRequest:
    entity, indicator, frequency = group_key
    periods = tuple(cell.key.period for cell in cells)
    narrowed = _narrow_request(request, entity, indicator, periods, frequency)
    identity = {
        "matrix_id": matrix_id,
        "provider": provider,
        "entity": entity,
        "indicator": indicator,
        "frequency": frequency,
        "periods": periods,
    }
    return OfficialGapRequest(
        gap_request_id="macro-gap-request-" + _digest(identity)[:32],
        provider=provider,
        entity_code=entity,
        indicator_code=indicator,
        periods=periods,
        research_request=narrowed,
    )


def _narrow_request(
    request: dict[str, Any],
    entity: str,
    indicator: str,
    periods: tuple[str, ...],
    frequency: str,
) -> dict[str, Any]:
    narrowed = copy.deepcopy(request)
    narrowed["entities"] = [
        item for item in narrowed["entities"] if item["name_or_code"] == entity
    ]
    narrowed["indicators"] = [
        item for item in narrowed["indicators"] if item["name_or_code"] == indicator
    ]
    narrowed["time_range"] = {
        "start": _request_period(periods[0], frequency),
        "end": _request_period(periods[-1], frequency),
    }
    constraints = cast(
        list[dict[str, Any]],
        narrowed.get("native_source_constraints") or [],
    )
    narrowed["native_source_constraints"] = [
        item for item in constraints if item.get("indicator_code") in (None, indicator)
    ]
    return narrowed


def _request_period(period: str, frequency: str) -> str:
    if frequency == "Q" and "-Q" not in period:
        return period[:4] + "-Q" + period[-1]
    return period


def _gap_reason(
    key: CanonicalObservationKey,
    primary: PrimaryCellLedger,
) -> GapReason:
    global_reasons = set(primary.issue_codes)
    if "provider_error" in global_reasons:
        return "provider_error"
    if "unsupported_query" in global_reasons:
        return "unsupported_query"
    if "empty_result" in global_reasons:
        return "empty_result"
    reasons = _rejection_reasons(key, primary.rejected)
    if reasons & {"license_unresolved"}:
        return "license_or_use_not_authorized"
    if reasons & {
        "datapro_cell_value_conflict",
        "datapro_cell_duplicate",
        "native_series_identity_mismatch",
    }:
        return "identity_ambiguity"
    if reasons & {
        "unit_unknown",
        "seasonal_adjustment_unknown",
        "definition_unknown",
        "metadata_insufficient",
    }:
        return "metadata_insufficient"
    if reasons:
        return "exact_candidate_missing"
    return "period_missing"


def _rejection_reasons(
    key: CanonicalObservationKey,
    rejected: tuple[dict[str, object], ...],
) -> set[str]:
    reasons: set[str] = set()
    for rejection in rejected:
        item = rejection.get("item")
        if not isinstance(item, dict) or _item_key(item) != key:
            continue
        codes = rejection.get("reason_codes")
        if isinstance(codes, list):
            reasons.update(str(code) for code in codes)
    return reasons


def _item_key(item: dict[object, object]) -> CanonicalObservationKey:
    return CanonicalObservationKey(
        indicator_code=str(item.get("indicator_code") or ""),
        entity_code=str(item.get("entity_code") or ""),
        period=str(item.get("time_raw") or "").replace("-Q", "Q"),
        frequency=str(item.get("observed_frequency") or ""),
    )


def _digest(document: object) -> str:
    return hashlib.sha256(canonical_json(document)).hexdigest()
