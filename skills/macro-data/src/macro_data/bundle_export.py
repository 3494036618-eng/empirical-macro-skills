"""Write deterministic macro-data research bundles."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq

from macro_data import __version__
from macro_data.contracts import validate_document
from macro_data.metadata_gate import is_documented_status
from macro_data.normalizer import (
    build_series_catalog,
    item_sort_key,
    normalize_item,
)
from macro_data.provenance import build_provenance, build_run_id, sha256_file
from macro_data.result_builder import build_result

_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "x-agent-plan-key",
    "api_key",
    "apikey",
    "token",
    "secret",
    "trace_id",
}
_COLUMNS = [
    "period",
    "entity_code",
    "entity_name",
    "indicator_code",
    "indicator_name",
    "value",
    "source_system",
    "dataset_id",
    "dataset_name",
    "series_key",
    "frequency",
    "requested_frequency",
    "unit",
    "unit_status",
    "seasonal_adjustment",
    "seasonal_adjustment_status",
    "price_basis",
    "price_basis_status",
    "definition",
    "definition_status",
    "release_date",
    "release_date_status",
    "vintage",
    "vintage_status",
    "p_date",
    "p_date_semantics",
]
_PARQUET_SCHEMA = pa.schema(
    [pa.field(column, pa.float64() if column == "value" else pa.string()) for column in _COLUMNS]
)
_PARQUET_BATCH_SIZE = 10_000
_BASE_ARTIFACTS = (
    "request_manifest.json",
    "raw_response.json",
    "data.csv",
    "data.parquet",
    "series_catalog.json",
    "quality_report.json",
)


def _write_json(path: Path, value: object) -> None:
    encoder = json.JSONEncoder(
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    with path.open("w", encoding="utf-8") as handle:
        for chunk in encoder.iterencode(value):
            handle.write(chunk)
        handle.write("\n")


def _sanitize_dict(value: dict[Any, Any]) -> dict[Any, Any]:
    result = value
    for key, item in value.items():
        if str(key).lower() in _SENSITIVE_KEYS:
            if result is value:
                result = dict(value)
            result.pop(key, None)
            continue
        sanitized_item = _sanitized(item)
        if sanitized_item is not item:
            if result is value:
                result = dict(value)
            result[key] = sanitized_item
    return result


def _sanitize_list(value: list[Any]) -> list[Any]:
    result = value
    for index, item in enumerate(value):
        sanitized_item = _sanitized(item)
        if sanitized_item is not item:
            if result is value:
                result = list(value)
            result[index] = sanitized_item
    return result


def _sanitized(value: Any) -> Any:
    if isinstance(value, dict):
        return _sanitize_dict(value)
    if isinstance(value, list):
        return _sanitize_list(value)
    return value


def _parquet_row(row: dict[str, Any]) -> dict[str, Any]:
    item = {}
    for column in _COLUMNS:
        value = row.get(column)
        if column != "value" and isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        item[column] = value
    return item


def _write_data_artifacts(
    *,
    items: list[dict[str, Any]],
    csv_path: Path,
    parquet_path: Path,
) -> None:
    parquet_batch: list[dict[str, Any]] = []
    with (
        csv_path.open("w", encoding="utf-8", newline="") as csv_handle,
        pq.ParquetWriter(
            parquet_path,
            _PARQUET_SCHEMA,
            compression="zstd",
        ) as parquet_writer,
    ):
        csv_writer = csv.DictWriter(csv_handle, fieldnames=_COLUMNS)
        csv_writer.writeheader()
        for item in sorted(items, key=item_sort_key):
            row = normalize_item(item)
            csv_writer.writerow(row)
            parquet_batch.append(_parquet_row(row))
            if len(parquet_batch) == _PARQUET_BATCH_SIZE:
                table = pa.Table.from_pylist(
                    parquet_batch,
                    schema=_PARQUET_SCHEMA,
                )
                parquet_writer.write_table(table)
                parquet_batch.clear()
        if parquet_batch:
            table = pa.Table.from_pylist(
                parquet_batch,
                schema=_PARQUET_SCHEMA,
            )
            parquet_writer.write_table(table)


def _p_date_semantics(items: list[dict[str, Any]]) -> str:
    semantics = {str(item.get("p_date", {}).get("semantics") or "unresolved") for item in items}
    if not semantics:
        return "unresolved"
    if len(semantics) == 1:
        return semantics.pop()
    return "mixed"


def _missingness(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "value_missing": sum(item.get("value") is None for item in items),
        "unit_unknown": sum(
            not is_documented_status(
                item["unit"]["status"],
                allow_not_applicable=True,
            )
            for item in items
        ),
        "seasonal_adjustment_unknown": sum(
            not is_documented_status(
                item["seasonal_adjustment"]["status"],
                allow_not_applicable=True,
            )
            for item in items
        ),
        "definition_unknown": sum(
            not is_documented_status(item["definition"]["status"]) for item in items
        ),
        "vintage_unresolved": sum(item["vintage"]["status"] != "source_provided" for item in items),
    }


def _quality_document(
    evaluation: dict[str, Any],
    missingness: dict[str, int],
) -> dict[str, Any]:
    selected_items = cast(list[dict[str, Any]], evaluation["selected_items"])
    return {
        "execution_status": evaluation["execution_status"],
        "research_readiness": evaluation["research_readiness"],
        "delivery_eligibility": evaluation["delivery_eligibility"],
        "eligible_for_estimation": evaluation["eligible_for_estimation"],
        "review_required": evaluation["review_required"],
        "issue_codes": evaluation["issue_codes"],
        "source_coverage": evaluation["source_coverage"],
        "selected_observations": len(selected_items),
        "filtered_candidates": evaluation["filtered_candidates"],
        "missingness": missingness,
    }


def _base_artifacts(
    request: dict[str, Any],
    evaluation: dict[str, Any],
    output_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    selected_items = cast(list[dict[str, Any]], evaluation["selected_items"])
    raw_response = _sanitized(evaluation["raw_response"])
    if not isinstance(raw_response, dict):
        raise TypeError("raw response must be an object")
    typed_raw = cast(dict[str, Any], raw_response)
    validate_document("request", request)
    _write_json(output_dir / "request_manifest.json", request)
    _write_json(output_dir / "raw_response.json", typed_raw)
    _write_data_artifacts(
        items=selected_items,
        csv_path=output_dir / "data.csv",
        parquet_path=output_dir / "data.parquet",
    )
    _write_json(
        output_dir / "series_catalog.json",
        build_series_catalog(selected_items),
    )
    missingness = _missingness(selected_items)
    _write_json(
        output_dir / "quality_report.json",
        _quality_document(evaluation, missingness),
    )
    checksums = {name: sha256_file(output_dir / name) for name in _BASE_ARTIFACTS}
    return typed_raw, selected_items, checksums


def _write_provenance_and_result(
    request: dict[str, Any],
    evaluation: dict[str, Any],
    output_dir: Path,
    input_mode: str,
    raw_response: dict[str, Any],
    selected_items: list[dict[str, Any]],
    checksums: dict[str, str],
) -> dict[str, Any]:
    fixture = evaluation.get("fixture_provenance") or {}
    provider = str(evaluation.get("provider", "datapro"))
    provenance = build_provenance(
        request=request,
        raw_response=raw_response,
        input_mode=input_mode,
        provider=provider,
        p_date_semantics=_p_date_semantics(selected_items),
        transformations=evaluation.get("transformations", []),
        artifact_checksums=checksums,
        generated_at=fixture.get("executed_at"),
    )
    validate_document("provenance", provenance)
    _write_json(output_dir / "provenance.json", provenance)
    checksums["provenance.json"] = sha256_file(output_dir / "provenance.json")
    result = build_result(
        request=request,
        evaluation=evaluation,
        provenance=provenance,
        checksums=checksums,
        provenance_checksum=checksums["provenance.json"],
        retrieved_at=provenance["generated_at"],
        missingness=_missingness(selected_items),
    )
    validate_document("result", result)
    _write_json(output_dir / "result.json", result)
    checksums["result.json"] = sha256_file(output_dir / "result.json")
    return provenance


def _write_run_manifest(
    request: dict[str, Any],
    evaluation: dict[str, Any],
    output_dir: Path,
    input_mode: str,
    raw_response: dict[str, Any],
    checksums: dict[str, str],
) -> None:
    fixture = evaluation.get("fixture_provenance") or {}
    manifest = {
        "schema_version": "0.2.0-beta",
        "run_id": build_run_id(request, raw_response),
        "macro_data_version": __version__,
        "request": request,
        "connector": str(evaluation.get("provider", "datapro")),
        "input_mode": input_mode,
        "fixture_provenance": fixture,
        "artifacts": dict(sorted(checksums.items())),
        "execution_status": evaluation["execution_status"],
        "research_readiness": evaluation["research_readiness"],
        "delivery_eligibility": evaluation["delivery_eligibility"],
        "eligible_for_estimation": evaluation["eligible_for_estimation"],
        "secrets_recorded": False,
    }
    validate_document("run_manifest", manifest)
    _write_json(output_dir / "run_manifest.json", manifest)


def export_bundle(
    *,
    request: dict[str, Any],
    evaluation: dict[str, Any],
    output_dir: Path,
    input_mode: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_response, selected_items, checksums = _base_artifacts(
        request,
        evaluation,
        output_dir,
    )
    _write_provenance_and_result(
        request,
        evaluation,
        output_dir,
        input_mode,
        raw_response,
        selected_items,
        checksums,
    )
    _write_run_manifest(
        request,
        evaluation,
        output_dir,
        input_mode,
        raw_response,
        checksums,
    )
    return evaluation
