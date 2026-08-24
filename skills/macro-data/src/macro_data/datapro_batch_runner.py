"""Run deterministic DataPro batches and lock one physical series per request."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from macro_data.connectors.base import Connector, ConnectorRequest
from macro_data.datapro_batch_evidence import write_batch_ledgers, write_batch_plan
from macro_data.datapro_batch_plan import DataProBatch
from macro_data.multi_source_pipeline import RetrievalRecord, _retrieve
from macro_data.observation_matrix import (
    CanonicalObservationKey,
    ExpectedObservationMatrix,
)
from macro_data.primary_cell_ledger import (
    LockedObservation,
    PrimaryCellLedger,
    lock_datapro_cells,
)
from macro_data.provenance import canonical_json
from macro_data.semantic_validator import evaluate_candidates


@dataclass(frozen=True, slots=True)
class SeriesLock:
    source_system: str
    dataset_id: str
    entity_code: str
    indicator_code: str
    series_key: str
    frequency: str
    unit: object
    seasonal_adjustment: object
    price_basis: object


@dataclass(frozen=True, slots=True)
class BatchRun:
    retrievals: tuple[RetrievalRecord, ...]
    primary: PrimaryCellLedger
    locks: tuple[SeriesLock, ...]
    unresolved_periods: tuple[str, ...]
    issue_codes: tuple[str, ...]


@dataclass(slots=True)
class _BatchState:
    retrievals: list[RetrievalRecord]
    locks: dict[tuple[str, str], SeriesLock]
    locked: dict[CanonicalObservationKey, LockedObservation]
    rejected: list[dict[str, object]]
    issues: set[str]
    executed_batches: list[DataProBatch]
    calls: int
    next_sequence: int


def _pair(batch: DataProBatch) -> tuple[str, str]:
    return batch.entity_code, batch.indicator_code


def _series_lock(item: dict[str, Any]) -> SeriesLock:
    return SeriesLock(
        source_system=str(item.get("source_system") or ""),
        dataset_id=str(item.get("dataset_id") or ""),
        entity_code=str(item.get("entity_code") or ""),
        indicator_code=str(item.get("indicator_code") or ""),
        series_key=str(item.get("series_key") or ""),
        frequency=str(item.get("observed_frequency") or ""),
        unit=copy.deepcopy(item.get("unit")),
        seasonal_adjustment=copy.deepcopy(item.get("seasonal_adjustment")),
        price_basis=copy.deepcopy(item.get("price_basis")),
    )


def _identity_key(lock: SeriesLock) -> bytes:
    return canonical_json(
        {
            "source_system": lock.source_system,
            "dataset_id": lock.dataset_id,
            "entity_code": lock.entity_code,
            "indicator_code": lock.indicator_code,
            "series_key": lock.series_key,
            "frequency": lock.frequency,
            "unit": lock.unit,
            "seasonal_adjustment": lock.seasonal_adjustment,
            "price_basis": lock.price_basis,
        }
    )


def _matches_lock(item: dict[str, Any], lock: SeriesLock) -> bool:
    return _identity_key(_series_lock(item)) == _identity_key(lock)


def _narrow_request(
    request: dict[str, Any],
    batch: DataProBatch,
) -> dict[str, Any]:
    narrowed = copy.deepcopy(request)
    narrowed["entities"] = [
        item
        for item in cast(list[dict[str, Any]], request["entities"])
        if item["name_or_code"] == batch.entity_code
    ]
    narrowed["indicators"] = [
        item
        for item in cast(list[dict[str, Any]], request["indicators"])
        if item["name_or_code"] == batch.indicator_code
    ]
    narrowed["native_source_constraints"] = [
        item
        for item in cast(
            list[dict[str, Any]],
            request.get("native_source_constraints") or [],
        )
        if item.get("indicator_code") in {None, batch.indicator_code}
    ]
    narrowed["time_range"] = {
        "start": batch.periods[0],
        "end": batch.periods[-1],
    }
    return narrowed


def _locked_sort_key(
    observation: LockedObservation,
) -> tuple[str, str, str, str]:
    key = observation.key
    return (key.indicator_code, key.entity_code, key.period, key.frequency)


def _merge_observations(
    locked: dict[CanonicalObservationKey, LockedObservation],
    observations: tuple[LockedObservation, ...],
    issues: set[str],
) -> None:
    for observation in observations:
        existing = locked.get(observation.key)
        if existing is None:
            locked[observation.key] = observation
            continue
        if (
            existing.native_series_key == observation.native_series_key
            and existing.value == observation.value
        ):
            continue
        issues.add("datapro_cell_value_conflict")


def _missing_for_batch(
    batch: DataProBatch,
    locked: dict[CanonicalObservationKey, LockedObservation],
) -> tuple[str, ...]:
    return tuple(
        period
        for period in batch.periods
        if CanonicalObservationKey(
            batch.indicator_code,
            batch.entity_code,
            period,
            batch.frequency,
        )
        not in locked
    )


def _contiguous_groups(
    missing: tuple[str, ...],
    ordered_periods: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    missing_set = set(missing)
    groups: list[list[str]] = []
    for period in ordered_periods:
        if period not in missing_set:
            continue
        if not groups:
            groups.append([period])
            continue
        previous_index = ordered_periods.index(groups[-1][-1])
        current_index = ordered_periods.index(period)
        if current_index == previous_index + 1:
            groups[-1].append(period)
        else:
            groups.append([period])
    return tuple(tuple(group) for group in groups)


def _retry_batches(
    batch: DataProBatch,
    missing: tuple[str, ...],
    *,
    next_sequence: int,
) -> tuple[DataProBatch, ...]:
    groups = _contiguous_groups(missing, batch.periods)
    if groups == (batch.periods,) and len(batch.periods) > 1:
        midpoint = len(batch.periods) // 2
        groups = (batch.periods[:midpoint], batch.periods[midpoint:])
    retries = []
    for index, periods in enumerate(groups):
        retries.append(
            DataProBatch(
                batch_id=f"{batch.batch_id}-retry-{next_sequence + index}",
                request_id=batch.request_id,
                entity_code=batch.entity_code,
                indicator_code=batch.indicator_code,
                frequency=batch.frequency,
                periods=periods,
                query=batch.query.replace(
                    f"{batch.periods[0]}至{batch.periods[-1]}",
                    f"{periods[0]}至{periods[-1]}",
                ),
                sequence=next_sequence + index,
            )
        )
    return tuple(retries)


def _reject_candidates(
    state: _BatchState,
    candidates: list[dict[str, Any]],
    issue: str,
) -> None:
    state.issues.add(issue)
    state.rejected.extend(
        {
            "item": copy.deepcopy(item),
            "reason_codes": [issue],
        }
        for item in candidates
    )


def _resolve_lock(
    batch: DataProBatch,
    candidates: list[dict[str, Any]],
    state: _BatchState,
) -> tuple[SeriesLock | None, bool]:
    pair = _pair(batch)
    lock = state.locks.get(pair)
    identities = {
        _identity_key(_series_lock(item)): _series_lock(item)
        for item in candidates
    }
    if lock is None and len(identities) > 1:
        _reject_candidates(state, candidates, "series_identity_ambiguous")
        return None, True
    if lock is None and identities:
        lock = next(iter(identities.values()))
        state.locks[pair] = lock
    if lock is not None and candidates and not any(
        _matches_lock(item, lock) for item in candidates
    ):
        _reject_candidates(state, candidates, "series_identity_drift")
        return lock, True
    return lock, False


def _execute_batch(
    *,
    request: dict[str, Any],
    matrix: ExpectedObservationMatrix,
    batch: DataProBatch,
    connector: Connector,
    output_dir: Path,
    state: _BatchState,
) -> tuple[tuple[str, ...], bool]:
    narrowed = _narrow_request(request, batch)
    retrieved = _retrieve(
        connector=connector,
        connector_request=ConnectorRequest(
            request_id=batch.batch_id,
            query=batch.query,
            research_request=narrowed,
        ),
        research_request=narrowed,
        output_dir=output_dir,
    )
    state.calls += 1
    state.executed_batches.append(batch)
    state.retrievals.append(retrieved.record)
    evaluation = evaluate_candidates(narrowed, retrieved.record.parsed)
    candidates = cast(
        list[dict[str, Any]],
        evaluation.get("selected_items") or [],
    )
    lock, stop_retry = _resolve_lock(batch, candidates, state)
    matching = (
        [item for item in candidates if _matches_lock(item, lock)]
        if lock is not None
        else []
    )
    batch_ledger = lock_datapro_cells(
        request=narrowed,
        matrix=matrix,
        evaluation={"selected_items": matching},
    )
    state.rejected.extend(batch_ledger.rejected)
    state.issues.update(batch_ledger.issue_codes)
    _merge_observations(state.locked, batch_ledger.locked, state.issues)
    missing = _missing_for_batch(batch, state.locked)
    write_batch_ledgers(
        output_dir,
        batch,
        evaluation,
        batch_ledger,
        missing,
    )
    return missing, stop_retry


def _finalize(
    matrix: ExpectedObservationMatrix,
    state: _BatchState,
) -> BatchRun:
    unresolved = tuple(
        sorted(
            {
                cell.key.period
                for cell in matrix.cells
                if cell.key not in state.locked
            }
        )
    )
    if unresolved:
        state.issues.add("batch_period_incomplete")
    primary = PrimaryCellLedger(
        matrix_id=matrix.matrix_id,
        locked=tuple(
            sorted(state.locked.values(), key=_locked_sort_key)
        ),
        rejected=tuple(state.rejected),
        issue_codes=tuple(sorted(state.issues)),
    )
    return BatchRun(
        retrievals=tuple(state.retrievals),
        primary=primary,
        locks=tuple(
            sorted(
                state.locks.values(),
                key=lambda item: (item.entity_code, item.indicator_code),
            )
        ),
        unresolved_periods=unresolved,
        issue_codes=tuple(sorted(state.issues)),
    )


def run_datapro_batches(
    *,
    request: dict[str, Any],
    matrix: ExpectedObservationMatrix,
    batches: tuple[DataProBatch, ...],
    connector: Connector,
    output_dir: Path,
    maximum_calls: int,
) -> BatchRun:
    """Execute planned batches without changing the original observation matrix."""
    queue = list(batches)
    state = _BatchState(
        retrievals=[],
        locks={},
        locked={},
        rejected=[],
        issues=set(),
        executed_batches=[],
        calls=0,
        next_sequence=max((batch.sequence for batch in batches), default=-1) + 1,
    )
    while queue and state.calls < maximum_calls:
        batch = queue.pop(0)
        missing, stop_retry = _execute_batch(
            request=request,
            matrix=matrix,
            batch=batch,
            connector=connector,
            output_dir=output_dir,
            state=state,
        )
        if missing and not stop_retry and len(batch.periods) > 1:
            retries = _retry_batches(
                batch,
                missing,
                next_sequence=state.next_sequence,
            )
            state.next_sequence += len(retries)
            queue[0:0] = list(retries)
    write_batch_plan(
        output_dir,
        state.executed_batches,
        maximum_calls=maximum_calls,
        executed_call_count=state.calls,
    )
    return _finalize(matrix, state)
