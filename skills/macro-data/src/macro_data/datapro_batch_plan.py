"""Build deterministic DataPro batches for annual, quarterly, and monthly data."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, cast

from macro_data.contracts import validate_document
from macro_data.provenance import canonical_json
from macro_data.semantic_coverage import expected_periods

FREQUENCY_LABELS = {
    "A": "年度",
    "Q": "季度",
    "M": "月度",
}


@dataclass(frozen=True, slots=True)
class BatchPolicy:
    maximum_periods: Mapping[str, int]
    maximum_calls: int


@dataclass(frozen=True, slots=True)
class DataProBatch:
    batch_id: str
    request_id: str
    entity_code: str
    indicator_code: str
    frequency: str
    periods: tuple[str, ...]
    query: str
    sequence: int

    def as_document(self) -> dict[str, object]:
        return asdict(self)


def _windows(
    periods: tuple[str, ...],
    size: int,
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        periods[index : index + size]
        for index in range(0, len(periods), size)
    )


def _batch_id(document: dict[str, object]) -> str:
    digest = hashlib.sha256(canonical_json(document)).hexdigest()
    return "datapro-batch-" + digest[:32]


def _query(
    *,
    entity_code: str,
    indicator: dict[str, Any],
    frequency: str,
    periods: tuple[str, ...],
) -> str:
    concept = str(
        indicator.get("required_definition")
        or indicator["name_or_code"]
    )
    return (
        f"查询{entity_code}{periods[0]}至{periods[-1]}的{concept}，"
        f"{FREQUENCY_LABELS[frequency]}频率。"
    )


def build_datapro_batch_plan(
    request: dict[str, Any],
    policy: BatchPolicy,
) -> tuple[DataProBatch, ...]:
    """Expand a request into one-entity, one-indicator time windows."""
    validate_document("request", request)
    frequency = cast(str, request["frequency"])
    size = policy.maximum_periods.get(frequency)
    if size is None:
        raise ValueError(f"batch_window_missing:{frequency}")
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise ValueError(f"batch_window_invalid:{frequency}")
    if (
        isinstance(policy.maximum_calls, bool)
        or not isinstance(policy.maximum_calls, int)
        or policy.maximum_calls < 1
    ):
        raise ValueError("maximum_calls_invalid")

    time_range = cast(dict[str, str], request["time_range"])
    periods = tuple(
        sorted(
            expected_periods(
                time_range["start"],
                time_range["end"],
                frequency,
            )
        )
    )
    windows = _windows(periods, size)
    entities = sorted(
        cast(list[dict[str, Any]], request["entities"]),
        key=lambda item: str(item["name_or_code"]),
    )
    indicators = sorted(
        cast(list[dict[str, Any]], request["indicators"]),
        key=lambda item: str(item["name_or_code"]),
    )
    request_id = str(request.get("request_id") or "")
    batches: list[DataProBatch] = []
    for entity in entities:
        entity_code = str(entity["name_or_code"])
        for indicator in indicators:
            indicator_code = str(indicator["name_or_code"])
            for window in windows:
                identity: dict[str, object] = {
                    "request_id": request_id,
                    "entity_code": entity_code,
                    "indicator_code": indicator_code,
                    "frequency": frequency,
                    "periods": list(window),
                }
                batches.append(
                    DataProBatch(
                        batch_id=_batch_id(identity),
                        request_id=request_id,
                        entity_code=entity_code,
                        indicator_code=indicator_code,
                        frequency=frequency,
                        periods=window,
                        query=_query(
                            entity_code=entity_code,
                            indicator=indicator,
                            frequency=frequency,
                            periods=window,
                        ),
                        sequence=len(batches),
                    )
                )
    if len(batches) > policy.maximum_calls:
        raise ValueError("call_budget_exceeded")
    return tuple(batches)
