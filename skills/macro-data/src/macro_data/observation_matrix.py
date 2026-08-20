"""Build the immutable observation denominator before any retrieval."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from typing import Any, Literal, cast

from macro_data.contracts import validate_document
from macro_data.provenance import canonical_json, sha256_bytes
from macro_data.semantic_coverage import expected_periods

CellStatus = Literal[
    "expected",
    "datapro_locked",
    "official_fallback_locked",
    "unresolved",
    "conflicted",
]


@dataclass(frozen=True, slots=True)
class CanonicalObservationKey:
    indicator_code: str
    entity_code: str
    period: str
    frequency: str

    def as_document(self) -> dict[str, str]:
        return {
            "indicator_code": self.indicator_code,
            "entity_code": self.entity_code,
            "period": self.period,
            "frequency": self.frequency,
        }


@dataclass(frozen=True, slots=True)
class ExpectedCell:
    cell_id: str
    key: CanonicalObservationKey
    status: CellStatus = "expected"

    def as_document(self) -> dict[str, object]:
        return {
            "cell_id": self.cell_id,
            "key": self.key.as_document(),
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ExpectedObservationMatrix:
    schema_version: str
    matrix_id: str
    request_id: str
    request_checksum: str
    cells: tuple[ExpectedCell, ...]

    def as_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "matrix_id": self.matrix_id,
            "request_id": self.request_id,
            "request_checksum": self.request_checksum,
            "cells": [cell.as_document() for cell in self.cells],
        }

    def keys(self) -> frozenset[CanonicalObservationKey]:
        return frozenset(cell.key for cell in self.cells)


def build_expected_matrix(request: dict[str, Any]) -> ExpectedObservationMatrix:
    """Build the complete indicator/entity/period cartesian product."""
    validate_document("request", request)
    canonical_request = _canonical_request(request)
    request_checksum = sha256_bytes(canonical_json(canonical_request))
    request_id = "macro-request-" + request_checksum.removeprefix("sha256:")[:32]
    frequency = cast(str, request["frequency"])
    indicators = _codes(request, "indicators")
    entities = _codes(request, "entities")
    periods = sorted(
        expected_periods(
            cast(dict[str, str], request["time_range"])["start"],
            cast(dict[str, str], request["time_range"])["end"],
            frequency,
        )
    )
    keys = tuple(
        CanonicalObservationKey(indicator, entity, period, frequency)
        for indicator in indicators
        for entity in entities
        for period in periods
    )
    cells = tuple(ExpectedCell(_cell_id(key), key) for key in keys)
    matrix_identity = {
        "request_checksum": request_checksum,
        "cells": [key.as_document() for key in keys],
    }
    matrix = ExpectedObservationMatrix(
        schema_version="0.3.0-beta",
        matrix_id="macro-matrix-" + _digest(matrix_identity)[:32],
        request_id=request_id,
        request_checksum=request_checksum,
        cells=cells,
    )
    validate_document("expected_observation_matrix", matrix.as_document())
    return matrix


def _codes(request: dict[str, Any], field: str) -> tuple[str, ...]:
    records = cast(list[dict[str, Any]], request[field])
    return tuple(sorted(cast(str, record["name_or_code"]) for record in records))


def _cell_id(key: CanonicalObservationKey) -> str:
    return "macro-cell-" + _digest(key.as_document())[:32]


def _digest(document: object) -> str:
    return hashlib.sha256(canonical_json(document)).hexdigest()


def _canonical_request(request: dict[str, Any]) -> dict[str, Any]:
    document = copy.deepcopy(request)
    for field in (
        "concepts",
        "indicators",
        "entities",
        "native_source_constraints",
        "output_format",
    ):
        values = document.get(field)
        if isinstance(values, list):
            document[field] = sorted(values, key=canonical_json)
    policy = document.get("fallback_policy")
    if isinstance(policy, dict) and isinstance(policy.get("allowed_sources"), list):
        policy["allowed_sources"] = sorted(policy["allowed_sources"])
    return document
