"""Export deterministic 0.3 DataPro-first completion bundles."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq

from macro_data.bundle_export import _sanitized
from macro_data.completion_assembler import CompletionResult
from macro_data.completion_integrity import COMPLETION_COLUMNS
from macro_data.contracts import validate_document
from macro_data.multi_source_pipeline import RetrievalRecord
from macro_data.provenance import canonical_json, sha256_bytes, sha256_file
from macro_data.residual_gap import ResidualGapManifest
from macro_data.result_builder_v3 import build_result_v3

_PARQUET_SCHEMA = pa.schema(
    [
        pa.field(column, pa.float64() if column == "value" else pa.string())
        for column in COMPLETION_COLUMNS
    ]
)


def export_completion_bundle(
    *,
    request: dict[str, Any],
    result: CompletionResult,
    retrievals: Sequence[RetrievalRecord],
    gap_manifest: ResidualGapManifest,
    output_dir: Path,
    input_mode: str,
) -> dict[str, Any]:
    """Write a complete 0.3 bundle and return its result document."""
    validate_document("request", request)
    validate_document("residual_gap_manifest", gap_manifest.as_document())
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_artifacts = _write_retrievals(output_dir, retrievals)
    _write_json(output_dir / "request_manifest.json", request)
    _write_json(
        output_dir / "raw_response.json",
        _raw_response_document(retrievals, raw_artifacts),
    )
    _write_data(output_dir, result)
    _write_json(output_dir / "series_catalog.json", _series_catalog(result))
    _write_json(output_dir / "quality_report.json", _quality_report(result))

    checksums = _checksums(
        output_dir,
        (
            "request_manifest.json",
            "raw_response.json",
            "data.csv",
            "data.parquet",
            "series_catalog.json",
            "quality_report.json",
        ),
    )
    provenance = _provenance(result, retrievals, raw_artifacts, input_mode)
    _write_json(output_dir / "provenance.json", provenance)
    checksums["provenance.json"] = sha256_file(output_dir / "provenance.json")
    result_document = build_result_v3(
        request=request,
        result=result,
        checksums=checksums,
        raw_artifacts=raw_artifacts,
    )
    _write_json(output_dir / "result.json", result_document)
    checksums["result.json"] = sha256_file(output_dir / "result.json")
    completion_manifest = _completion_manifest(
        result=result,
        retrievals=raw_artifacts,
        gap_manifest=gap_manifest,
    )
    _write_json(output_dir / "completion_manifest.json", completion_manifest)
    checksums["completion_manifest.json"] = sha256_file(
        output_dir / "completion_manifest.json"
    )
    checksums.update(
        {
            artifact["path"]: artifact["sha256"]
            for artifact in raw_artifacts
        }
    )
    _write_json(
        output_dir / "run_manifest.json",
        _run_manifest(
            request=request,
            result_document=result_document,
            completion_manifest=completion_manifest,
            checksums=checksums,
            input_mode=input_mode,
        ),
    )
    return result_document


def _write_retrievals(
    output_dir: Path,
    retrievals: Sequence[RetrievalRecord],
) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for retrieval in retrievals:
        relative = f"raw/{retrieval.provider}-{retrieval.request_id}.json"
        payload = canonical_json(_sanitized(retrieval.raw))
        path = output_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        artifacts.append({"path": relative, "sha256": sha256_bytes(payload)})
    return artifacts


def _raw_response_document(
    retrievals: Sequence[RetrievalRecord],
    raw_artifacts: list[dict[str, str]],
) -> dict[str, object]:
    return {
        "schema_version": "0.3.0-beta",
        "retrievals": [
            {
                "provider": retrieval.provider,
                "request_id": retrieval.request_id,
                "retrieved_at": retrieval.retrieved_at,
                "raw_artifact": artifact["path"],
                "raw_checksum": artifact["sha256"],
            }
            for retrieval, artifact in zip(
                retrievals,
                raw_artifacts,
                strict=True,
            )
        ],
    }


def _write_data(output_dir: Path, result: CompletionResult) -> None:
    rows = [_observation_row(item) for item in result.observations]
    rows.sort(
        key=lambda row: (
            cast(str, row["indicator_code"]),
            cast(str, row["entity_code"]),
            cast(str, row["period"]),
        )
    )
    with (output_dir / "data.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=COMPLETION_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    table = pa.Table.from_pylist(rows, schema=_PARQUET_SCHEMA)
    pq.write_table(
        table,
        output_dir / "data.parquet",
        compression="zstd",
    )


def _observation_row(item: Any) -> dict[str, object]:
    license_document = item.item.get("license")
    authorization = item.item.get("use_authorization")
    return {
        "cell_id": item.cell_id,
        "canonical_series_id": item.canonical_series_id,
        "indicator_code": item.key.indicator_code,
        "entity_code": item.key.entity_code,
        "period": item.key.period,
        "value": item.value,
        "frequency": item.key.frequency,
        "retrieval_provider": item.retrieval_provider,
        "source_system": item.source_system,
        "dataset_id": item.dataset_id,
        "native_series_key": item.native_series_key,
        "origin_role": item.origin_role,
        "raw_artifact": item.raw_artifact,
        "raw_checksum": item.raw_checksum,
        "retrieved_at": item.retrieved_at,
        "authorization_ref": (
            authorization.get("authorization_ref")
            if isinstance(authorization, dict)
            else None
        ),
        "license_ref": (
            license_document.get("id")
            if isinstance(license_document, dict)
            else None
        ),
    }


def _series_catalog(result: CompletionResult) -> dict[str, object]:
    series = {
        (
            item.canonical_series_id,
            item.key.indicator_code,
            item.key.entity_code,
            item.key.frequency,
        )
        for item in result.observations
    }
    return {
        "schema_version": "0.3.0-beta",
        "series": [
            {
                "canonical_series_id": identity,
                "indicator_code": indicator,
                "entity_code": entity,
                "frequency": frequency,
            }
            for identity, indicator, entity, frequency in sorted(series)
        ],
    }


def _quality_report(result: CompletionResult) -> dict[str, object]:
    complete = result.residual_gap_count == 0 and result.conflict_count == 0
    execution_status = (
        "success" if complete else ("partial" if result.observations else "failed")
    )
    return {
        "execution_status": execution_status,
        "research_readiness": "ready" if complete else "blocked",
        "delivery_eligibility": (
            "analysis_ready" if complete else "not_deliverable"
        ),
        "eligible_for_estimation": complete,
        "review_required": not complete,
        "issue_codes": list(result.issue_codes),
        "expected_observation_count": len(result.matrix.cells),
        "final_estimator_observation_count": len(result.observations),
        "residual_gap_count": result.residual_gap_count,
        "conflict_count": result.conflict_count,
        "provider_contribution": asdict(result.contribution),
    }


def _provenance(
    result: CompletionResult,
    retrievals: Sequence[RetrievalRecord],
    raw_artifacts: list[dict[str, str]],
    input_mode: str,
) -> dict[str, object]:
    complete = result.residual_gap_count == 0 and result.conflict_count == 0
    return {
        "schema_version": "0.3.0-beta",
        "input_mode": input_mode,
        "retrievals": [
            {
                "provider": retrieval.provider,
                "request_id": retrieval.request_id,
                "retrieved_at": retrieval.retrieved_at,
                **artifact,
            }
            for retrieval, artifact in zip(
                retrievals,
                raw_artifacts,
                strict=True,
            )
        ],
        "complete": complete,
        "unresolved_links": 0 if complete else result.residual_gap_count,
        "credentials_recorded": False,
    }


def _completion_manifest(
    *,
    result: CompletionResult,
    retrievals: list[dict[str, str]],
    gap_manifest: ResidualGapManifest,
) -> dict[str, Any]:
    complete = result.residual_gap_count == 0 and result.conflict_count == 0
    document: dict[str, Any] = {
        "schema_version": "0.3.0-beta",
        "matrix_id": result.matrix.matrix_id,
        "matrix_checksum": sha256_bytes(
            canonical_json(result.matrix.as_document())
        ),
        "gap_manifest_id": gap_manifest.gap_manifest_id,
        "residual_gap_manifest": gap_manifest.as_document(),
        "expected_observation_count": len(result.matrix.cells),
        "datapro_attempted": True,
        "datapro_locked_cell_ids": list(
            gap_manifest.datapro_locked_cell_ids
        ),
        "official_fallback_cell_ids": [
            item.cell_id
            for item in result.observations
            if item.origin_role == "official_missing_only"
        ],
        "replaced_primary_count": 0,
        "final_estimator_cell_ids": [
            item.cell_id for item in result.observations
        ],
        "final_estimator_count": len(result.observations),
        "residual_gap_count": result.residual_gap_count,
        "conflict_count": result.conflict_count,
        "provider_contribution": asdict(result.contribution),
        "retrievals": [
            {
                "provider": path["path"].split("/", 1)[1].split("-", 1)[0],
                "raw_artifact": path["path"],
                "raw_checksum": path["sha256"],
            }
            for path in retrievals
        ],
        "overlap_validations": [
            asdict(item) for item in result.overlap_results
        ],
        "issue_codes": list(result.issue_codes),
        "completion_status": "complete" if complete else "blocked",
    }
    identity = {key: value for key, value in document.items()}
    document["completion_manifest_id"] = (
        "macro-completion-"
        + hashlib.sha256(canonical_json(identity)).hexdigest()[:32]
    )
    validate_document("completion_manifest", document)
    return document


def _run_manifest(
    *,
    request: dict[str, Any],
    result_document: dict[str, Any],
    completion_manifest: dict[str, Any],
    checksums: dict[str, str],
    input_mode: str,
) -> dict[str, object]:
    run_identity = {
        "request": request,
        "completion_manifest_id": completion_manifest["completion_manifest_id"],
    }
    return {
        "schema_version": "0.3.0-beta",
        "run_id": "run-" + hashlib.sha256(
            canonical_json(run_identity)
        ).hexdigest()[:32],
        "macro_data_version": "0.3.0-beta",
        "input_mode": input_mode,
        "artifacts": dict(sorted(checksums.items())),
        "execution_status": result_document["execution_status"],
        "research_readiness": result_document["research_readiness"],
        "delivery_eligibility": result_document["delivery_eligibility"],
        "eligible_for_estimation": result_document["eligible_for_estimation"],
        "secrets_recorded": False,
    }


def _checksums(
    output_dir: Path,
    artifacts: Sequence[str],
) -> dict[str, str]:
    return {
        name: sha256_file(output_dir / name)
        for name in artifacts
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
