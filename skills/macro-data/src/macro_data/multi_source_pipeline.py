"""Provider-neutral DataPro-first completion orchestration."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, cast

from macro_data.completion_assembler import CompletionResult, assemble_completion
from macro_data.connectors.base import Connector, ConnectorRequest
from macro_data.contracts import validate_document
from macro_data.datapro_batch_plan import (
    BatchPolicy,
    build_datapro_batch_plan,
)
from macro_data.observation_matrix import (
    ExpectedObservationMatrix,
    build_expected_matrix,
)
from macro_data.primary_cell_ledger import (
    LockedObservation,
    PrimaryCellLedger,
    lock_datapro_cells,
)
from macro_data.provenance import canonical_json, sha256_bytes
from macro_data.residual_gap import (
    OfficialGapRequest,
    ResidualGapManifest,
    build_residual_gaps,
)
from macro_data.semantic_validator import evaluate_candidates
from macro_data.series_mapping import (
    OverlapValidation,
    map_official_candidates,
    validate_overlap,
)
from macro_data.source_registry import SourceRegistry
from macro_data.source_router import RoutePlan, SourceRouter
from macro_data.transformation_engine import apply_transformations

OfficialConnectorRegistry = Mapping[str, Connector]
_OVERLAP_ABSOLUTE_TOLERANCE = 1e-9
_OVERLAP_RELATIVE_TOLERANCE = 1e-9
_BENIGN_OFFICIAL_FILTER_ISSUES = {"time_range_mismatch"}


@dataclass(frozen=True, slots=True)
class RetrievalRecord:
    provider: str
    request_id: str
    raw: dict[str, Any]
    parsed: dict[str, Any]
    retrieved_at: str


@dataclass(frozen=True, slots=True)
class _Retrieved:
    record: RetrievalRecord
    raw_artifact: str
    raw_checksum: str


def _retrieve_primary(
    *,
    request: dict[str, Any],
    matrix: ExpectedObservationMatrix,
    connector: Connector,
    output_dir: Path,
    batch_policy: BatchPolicy | None,
) -> tuple[PrimaryCellLedger, tuple[RetrievalRecord, ...], set[str]]:
    if batch_policy is not None:
        from macro_data.datapro_batch_runner import run_datapro_batches

        batch_run = run_datapro_batches(
            request=request,
            matrix=matrix,
            batches=build_datapro_batch_plan(request, batch_policy),
            connector=connector,
            output_dir=output_dir,
            maximum_calls=batch_policy.maximum_calls,
        )
        return batch_run.primary, batch_run.retrievals, set(batch_run.issue_codes)
    retrieved = _retrieve(
        connector=connector,
        connector_request=ConnectorRequest(
            request_id=matrix.request_id,
            query=cast(str, request["research_question"]),
            research_request=request,
        ),
        research_request=request,
        output_dir=output_dir,
    )
    evaluation = evaluate_candidates(request, retrieved.record.parsed)
    primary = _primary_with_evaluation_issues(
        lock_datapro_cells(
            request=request,
            matrix=matrix,
            evaluation=evaluation,
        ),
        evaluation,
    )
    return primary, (retrieved.record,), set()


def run_datapro_first_completion(
    *,
    request: dict[str, Any],
    datapro_connector: Connector,
    official_connectors: OfficialConnectorRegistry,
    output_dir: Path,
    input_mode: str = "live",
    batch_policy: BatchPolicy | None = None,
) -> dict[str, Any]:
    """Run DataPro first, then exact missing-only official completion."""
    validate_document("request", request)
    if request["schema_version"] != "0.3.0-beta":
        raise ValueError("DataPro-first completion requires a 0.3 request")
    if datapro_connector.code != "datapro":
        raise ValueError("primary connector must be datapro")

    matrix = build_expected_matrix(request)
    primary, primary_retrievals, batch_issues = _retrieve_primary(
        request=request,
        matrix=matrix,
        connector=datapro_connector,
        output_dir=output_dir,
        batch_policy=batch_policy,
    )
    route_plan = _available_route_plan(request, official_connectors)
    gaps = build_residual_gaps(
        request=request,
        matrix=matrix,
        primary=primary,
        route_plan=route_plan,
    )
    official = _retrieve_official(
        requests=gaps.official_requests,
        connectors=official_connectors,
        matrix=matrix,
        primary=primary,
        output_dir=output_dir,
    )
    completion = assemble_completion(
        matrix=matrix,
        primary=primary,
        fallback=official.observations,
        overlaps=official.overlaps,
    )
    issues = batch_issues | set(gaps.issue_codes) | set(official.issue_codes)
    issues.update(completion.issue_codes)
    completion = replace(
        completion,
        issue_codes=tuple(sorted(issues)),
    )
    return _run_result(
        matrix=matrix,
        primary=primary,
        gaps=gaps,
        completion=completion,
        retrievals=(*primary_retrievals, *official.retrievals),
        issue_codes=issues,
        input_mode=input_mode,
    )


@dataclass(frozen=True, slots=True)
class _OfficialResult:
    observations: tuple[LockedObservation, ...]
    overlaps: tuple[OverlapValidation, ...]
    retrievals: tuple[RetrievalRecord, ...]
    issue_codes: tuple[str, ...]


def _retrieve_official(
    *,
    requests: Sequence[OfficialGapRequest],
    connectors: OfficialConnectorRegistry,
    matrix: ExpectedObservationMatrix,
    primary: PrimaryCellLedger,
    output_dir: Path,
) -> _OfficialResult:
    observations: list[LockedObservation] = []
    validations: list[OverlapValidation] = []
    retrievals: list[RetrievalRecord] = []
    issues: set[str] = set()
    for gap_request in requests:
        connector = connectors.get(gap_request.provider)
        if connector is None:
            issues.add("connector_unavailable")
            continue
        try:
            retrieved = _retrieve(
                connector=connector,
                connector_request=ConnectorRequest(
                    request_id=gap_request.gap_request_id,
                    query=cast(
                        str,
                        gap_request.research_request["research_question"],
                    ),
                    research_request=gap_request.research_request,
                ),
                research_request=gap_request.research_request,
                output_dir=output_dir,
            )
        except Exception:
            issues.add("official_provider_error")
            continue
        retrievals.append(retrieved.record)
        batch = _official_batch(
            retrieved=retrieved,
            gap_request=gap_request,
            matrix=matrix,
            primary=primary,
        )
        observations.extend(batch.observations)
        validations.extend(batch.overlaps)
        issues.update(batch.issue_codes)
    return _OfficialResult(
        observations=tuple(observations),
        overlaps=tuple(validations),
        retrievals=tuple(retrievals),
        issue_codes=tuple(sorted(issues)),
    )


def _official_batch(
    *,
    retrieved: _Retrieved,
    gap_request: OfficialGapRequest,
    matrix: ExpectedObservationMatrix,
    primary: PrimaryCellLedger,
) -> _OfficialResult:
    parsed = retrieved.record.parsed
    evaluation = evaluate_candidates(gap_request.research_request, parsed)
    issues: set[str] = set()
    if evaluation["execution"].get("provider_code") != 0:
        issues.add("official_provider_error")
    selected = cast(list[dict[str, Any]], evaluation["selected_items"])
    if evaluation["delivery_eligibility"] != "analysis_ready":
        evaluation_issues = set(cast(list[str], evaluation["issue_codes"]))
        issues.update(evaluation_issues)
        if (
            evaluation["research_readiness"] == "blocked"
            or evaluation["source_coverage"]["complete"] is not True
            or evaluation_issues - _BENIGN_OFFICIAL_FILTER_ISSUES
        ):
            selected = []
    mapping = map_official_candidates(
        candidates=cast(list[dict[str, Any]], parsed["candidates"]),
        selected=selected,
        allowed_periods=set(gap_request.periods),
        matrix=matrix,
        primary=primary,
    )
    issues.update(mapping.issue_codes)
    if _has_source_identity_rejection(evaluation):
        issues.add("cross_source_mapping_rejected")
    overlaps = (
        (
            validate_overlap(
                primary.locked,
                mapping.validation_overlaps,
                absolute_tolerance=_OVERLAP_ABSOLUTE_TOLERANCE,
                relative_tolerance=_OVERLAP_RELATIVE_TOLERANCE,
            ),
        )
        if mapping.validation_overlaps
        else ()
    )
    if not mapping.fallback and evaluation["execution"].get("provider_code") == 0:
        issues.add("official_gap_unresolved")
    return _OfficialResult(
        observations=(*mapping.fallback, *mapping.validation_overlaps),
        overlaps=overlaps,
        retrievals=(retrieved.record,),
        issue_codes=tuple(sorted(issues)),
    )


def _retrieve(
    *,
    connector: Connector,
    connector_request: ConnectorRequest,
    research_request: dict[str, Any],
    output_dir: Path,
) -> _Retrieved:
    response = connector.retrieve(connector_request)
    parsed = copy.deepcopy(connector.parse_response(response.raw))
    candidates, transformations = apply_transformations(
        research_request,
        cast(list[dict[str, Any]], parsed["candidates"]),
    )
    artifact = f"raw/{connector.code}-{connector_request.request_id}.json"
    payload = canonical_json(response.raw)
    path = output_dir / artifact
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    checksum = sha256_bytes(payload)
    parsed["candidates"] = [
        {
            **item,
            "retrieval_provider": connector.code,
            "raw_artifact": artifact,
            "raw_checksum": checksum,
            "retrieved_at": response.retrieved_at,
        }
        for item in candidates
    ]
    parsed["transformations"] = transformations
    parsed["fixture_provenance"] = {
        "fixture_type": "connector",
        "executed_at": response.retrieved_at,
        "request": {"query": connector_request.query},
    }
    record = RetrievalRecord(
        provider=connector.code,
        request_id=connector_request.request_id,
        raw=copy.deepcopy(response.raw),
        parsed=parsed,
        retrieved_at=response.retrieved_at,
    )
    return _Retrieved(record=record, raw_artifact=artifact, raw_checksum=checksum)


def _has_source_identity_rejection(evaluation: dict[str, Any]) -> bool:
    filtered = cast(list[dict[str, Any]], evaluation["filtered_candidates"])
    return any(
        {"source_mismatch", "dataset_mismatch"} & set(item.get("reasons", []))
        for item in filtered
    )


def _primary_with_evaluation_issues(
    primary: PrimaryCellLedger,
    evaluation: dict[str, Any],
) -> PrimaryCellLedger:
    gap_reasons = {
        "empty_result",
        "unsupported_query",
        "provider_error",
    }
    issues = set(primary.issue_codes)
    issues.update(set(evaluation["issue_codes"]) & gap_reasons)
    return PrimaryCellLedger(
        matrix_id=primary.matrix_id,
        locked=primary.locked,
        rejected=primary.rejected,
        issue_codes=tuple(sorted(issues)),
    )


def _available_route_plan(
    request: dict[str, Any],
    connectors: OfficialConnectorRegistry,
) -> RoutePlan:
    planned = SourceRouter(SourceRegistry.default()).plan(request)
    return RoutePlan(
        primary=planned.primary,
        fallback_mode=planned.fallback_mode,
        fallback_candidates=[
            code for code in planned.fallback_candidates if code in connectors
        ],
        review_required=planned.review_required,
    )


def _run_result(
    *,
    matrix: ExpectedObservationMatrix,
    primary: PrimaryCellLedger,
    gaps: ResidualGapManifest,
    completion: CompletionResult,
    retrievals: tuple[RetrievalRecord, ...],
    issue_codes: set[str],
    input_mode: str,
) -> dict[str, Any]:
    complete = (
        completion.residual_gap_count == 0
        and completion.conflict_count == 0
        and len(completion.observations) == len(matrix.cells)
    )
    return {
        "schema_version": "0.3.0-beta",
        "input_mode": input_mode,
        "matrix": matrix,
        "primary": primary,
        "gap_manifest": gaps,
        "completion": completion,
        "retrievals": retrievals,
        "provider_contribution": asdict(completion.contribution),
        "issue_codes": tuple(sorted(issue_codes)),
        "execution_status": "success" if complete else ("partial" if primary.locked else "failed"),
        "research_readiness": "ready" if complete else "blocked",
        "delivery_eligibility": "analysis_ready" if complete else "not_deliverable",
        "eligible_for_estimation": complete,
        "review_required": not complete,
    }
