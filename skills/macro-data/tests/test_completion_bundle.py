from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from macro_data.completion_assembler import assemble_completion
from macro_data.multi_source_pipeline import RetrievalRecord
from macro_data.observation_matrix import build_expected_matrix
from macro_data.primary_cell_ledger import LockedObservation, PrimaryCellLedger
from macro_data.provenance import canonical_json, sha256_bytes, sha256_file
from macro_data.residual_gap import build_residual_gaps
from macro_data.source_router import RoutePlan

ROOT = Path(__file__).resolve().parents[1]
REQUEST_FIXTURE = ROOT / "fixtures" / "completion" / "request.valid.json"


def _request() -> dict[str, Any]:
    document = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    return cast(dict[str, Any], document)


def _raw_binding(provider: str, request_id: str) -> tuple[str, str, dict[str, Any]]:
    raw = {"provider": provider, "request_id": request_id, "items": []}
    return (
        f"raw/{provider}-{request_id}.json",
        sha256_bytes(canonical_json(raw)),
        raw,
    )


def _observation(
    matrix: Any,
    period: str,
    *,
    provider: str,
    request_id: str,
) -> LockedObservation:
    cell = next(cell for cell in matrix.cells if cell.key.period == period)
    raw_artifact, raw_checksum, _ = _raw_binding(provider, request_id)
    item = {
        "entity_name": "China",
        "indicator_name": "Consumer price index",
        "license": {
            "id": "CC-BY-4.0",
            "allows_requested_use": True,
        },
    }
    return LockedObservation(
        cell_id=cell.cell_id,
        key=cell.key,
        value=100.0 + int(period) - 2019,
        retrieval_provider=provider,
        source_system="WORLD_BANK",
        dataset_id="2",
        native_series_key="WORLD_BANK|2|CHN|FP.CPI.TOTL|A",
        canonical_series_id="macro-series-" + "a" * 32,
        origin_role=(
            "datapro_primary"
            if provider == "datapro"
            else "official_missing_only"
        ),
        raw_artifact=raw_artifact,
        raw_checksum=raw_checksum,
        retrieved_at="2026-08-18T00:00:00Z",
        item=item,
    )


def _models() -> tuple[
    dict[str, Any],
    Any,
    PrimaryCellLedger,
    Any,
    Any,
    tuple[RetrievalRecord, ...],
]:
    request = _request()
    matrix = build_expected_matrix(request)
    datapro_request_id = matrix.request_id
    primary = PrimaryCellLedger(
        matrix_id=matrix.matrix_id,
        locked=(
            _observation(
                matrix,
                "2019",
                provider="datapro",
                request_id=datapro_request_id,
            ),
            _observation(
                matrix,
                "2021",
                provider="datapro",
                request_id=datapro_request_id,
            ),
        ),
        rejected=(),
        issue_codes=(),
    )
    gaps = build_residual_gaps(
        request=request,
        matrix=matrix,
        primary=primary,
        route_plan=RoutePlan(
            primary="datapro",
            fallback_mode="allow_official_missing_only",
            fallback_candidates=["world_bank"],
            review_required=False,
        ),
    )
    official_request_id = gaps.official_requests[0].gap_request_id
    fallback = (
        _observation(
            matrix,
            "2020",
            provider="world_bank",
            request_id=official_request_id,
        ),
    )
    completion = assemble_completion(
        matrix=matrix,
        primary=primary,
        fallback=fallback,
        overlaps=(),
    )
    retrievals = tuple(
        RetrievalRecord(
            provider=provider,
            request_id=request_id,
            raw=raw,
            parsed={"provider": provider},
            retrieved_at="2026-08-18T00:00:00Z",
        )
        for provider, request_id in (
            ("datapro", datapro_request_id),
            ("world_bank", official_request_id),
        )
        for _, _, raw in (_raw_binding(provider, request_id),)
    )
    return request, matrix, primary, gaps, completion, retrievals


def _export_mixed_bundle(tmp_path: Path) -> Path:
    module = importlib.import_module("macro_data.completion_export")
    request, _, _, gaps, completion, retrievals = _models()
    output = tmp_path / "completion-bundle"
    module.export_completion_bundle(
        request=request,
        result=completion,
        retrievals=retrievals,
        gap_manifest=gaps,
        output_dir=output,
        input_mode="mock",
    )
    return output


def _export_official_only_bundle(tmp_path: Path) -> Path:
    module = importlib.import_module("macro_data.completion_export")
    request = _request()
    matrix = build_expected_matrix(request)
    primary = PrimaryCellLedger(
        matrix_id=matrix.matrix_id,
        locked=(),
        rejected=(),
        issue_codes=("empty_result",),
    )
    gaps = build_residual_gaps(
        request=request,
        matrix=matrix,
        primary=primary,
        route_plan=RoutePlan(
            primary="datapro",
            fallback_mode="allow_official_missing_only",
            fallback_candidates=["world_bank"],
            review_required=False,
        ),
    )
    official_request_id = gaps.official_requests[0].gap_request_id
    completion = assemble_completion(
        matrix=matrix,
        primary=primary,
        fallback=tuple(
            _observation(
                matrix,
                period,
                provider="world_bank",
                request_id=official_request_id,
            )
            for period in ("2019", "2020", "2021")
        ),
        overlaps=(),
    )
    retrievals = tuple(
        RetrievalRecord(
            provider=provider,
            request_id=request_id,
            raw=raw,
            parsed={"provider": provider},
            retrieved_at="2026-08-18T00:00:00Z",
        )
        for provider, request_id in (
            ("datapro", matrix.request_id),
            ("world_bank", official_request_id),
        )
        for _, _, raw in (_raw_binding(provider, request_id),)
    )
    output = tmp_path / "official-only"
    module.export_completion_bundle(
        request=request,
        result=completion,
        retrievals=retrievals,
        gap_manifest=gaps,
        output_dir=output,
        input_mode="mock",
    )
    return output


def _load(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], document)


def _write(path: Path, document: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _refresh_run_checksum(bundle: Path, artifact: str) -> None:
    manifest_path = bundle / "run_manifest.json"
    manifest = _load(manifest_path)
    manifest["artifacts"][artifact] = sha256_file(bundle / artifact)
    _write(manifest_path, manifest)


def test_completion_csv_records_provider_per_observation(tmp_path: Path) -> None:
    bundle = _export_mixed_bundle(tmp_path)

    with (bundle / "data.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 3
    assert {
        "retrieval_provider",
        "source_system",
        "native_series_key",
        "canonical_series_id",
        "origin_role",
        "raw_artifact",
        "raw_checksum",
    } <= set(rows[0])
    assert [row["retrieval_provider"] for row in rows] == [
        "datapro",
        "world_bank",
        "datapro",
    ]


def test_manifest_binds_matrix_gaps_retrievals_and_final_cells(
    tmp_path: Path,
) -> None:
    bundle = _export_mixed_bundle(tmp_path)
    manifest = _load(bundle / "completion_manifest.json")

    assert manifest["expected_observation_count"] == 3
    assert len(manifest["datapro_locked_cell_ids"]) == 2
    assert len(manifest["official_fallback_cell_ids"]) == 1
    assert manifest["final_estimator_count"] == 3
    assert manifest["residual_gap_manifest"]["gap_manifest_id"] == (
        manifest["gap_manifest_id"]
    )
    assert len(manifest["retrievals"]) == 2


def test_completion_bundle_validates_before_tampering(tmp_path: Path) -> None:
    bundle = _export_mixed_bundle(tmp_path)
    exporter = importlib.import_module("macro_data.exporter")

    report = exporter.validate_bundle(bundle)
    run_manifest = _load(bundle / "run_manifest.json")

    assert report["valid"] is True
    assert run_manifest["macro_data_version"] == "0.3.0-beta"


@pytest.mark.parametrize(
    "mutation",
    (
        "provider",
        "primary_cell",
        "datapro_ratio",
        "fallback_raw_checksum",
        "replaced_primary",
    ),
)
def test_completion_bundle_rejects_bound_artifact_tampering(
    tmp_path: Path,
    mutation: str,
) -> None:
    bundle = _export_mixed_bundle(tmp_path)
    if mutation == "provider":
        data_path = bundle / "data.csv"
        text = data_path.read_text(encoding="utf-8")
        data_path.write_text(text.replace("world_bank", "datapro", 1), encoding="utf-8")
    else:
        manifest_path = bundle / "completion_manifest.json"
        manifest = _load(manifest_path)
        if mutation == "primary_cell":
            manifest["datapro_locked_cell_ids"].pop()
        elif mutation == "datapro_ratio":
            manifest["provider_contribution"]["datapro_ratio"] = 0.99
        elif mutation == "fallback_raw_checksum":
            manifest["retrievals"][1].pop("raw_checksum")
        elif mutation == "replaced_primary":
            manifest["replaced_primary_count"] = 1
        _write(manifest_path, manifest)
        _refresh_run_checksum(bundle, "completion_manifest.json")

    exporter = importlib.import_module("macro_data.exporter")
    assert exporter.validate_bundle(bundle)["valid"] is False


def test_completion_bundle_rejects_expected_matrix_count_tampering(
    tmp_path: Path,
) -> None:
    bundle = _export_mixed_bundle(tmp_path)
    manifest_path = bundle / "completion_manifest.json"
    manifest = _load(manifest_path)
    manifest["expected_observation_count"] = 999
    _write(manifest_path, manifest)
    _refresh_run_checksum(bundle, "completion_manifest.json")

    exporter = importlib.import_module("macro_data.exporter")
    report = exporter.validate_bundle(bundle)

    assert report["valid"] is False
    assert any(
        finding["path"] == "expected_observation_count"
        for finding in report["consistency_findings"]
    )


def test_validator_returns_invalid_for_false_datapro_attempt_flag(
    tmp_path: Path,
) -> None:
    bundle = _export_official_only_bundle(tmp_path)
    path = bundle / "completion_manifest.json"
    manifest = _load(path)
    manifest["datapro_attempted"] = False
    _write(path, manifest)
    _refresh_run_checksum(bundle, "completion_manifest.json")

    exporter = importlib.import_module("macro_data.exporter")
    report = exporter.validate_bundle(bundle)

    assert report["valid"] is False
    assert any(
        finding["path"] == "provider_contribution"
        for finding in report["consistency_findings"]
    )


def test_completion_bundle_rejects_run_manifest_version_tampering(
    tmp_path: Path,
) -> None:
    bundle = _export_mixed_bundle(tmp_path)
    path = bundle / "run_manifest.json"
    manifest = _load(path)
    manifest["macro_data_version"] = "9.9.9"
    _write(path, manifest)

    exporter = importlib.import_module("macro_data.exporter")
    report = exporter.validate_bundle(bundle)

    assert report["valid"] is False
    assert any(
        finding["path"] == "macro_data_version"
        for finding in report["consistency_findings"]
    )


def test_completion_bundle_rejects_rehashed_parquet_value_tampering(
    tmp_path: Path,
) -> None:
    bundle = _export_mixed_bundle(tmp_path)
    path = bundle / "data.parquet"
    table = pq.read_table(path)
    rows = table.to_pylist()
    rows[0]["value"] += 999.0
    pq.write_table(
        pa.Table.from_pylist(rows, schema=table.schema),
        path,
        compression="zstd",
    )
    _refresh_run_checksum(bundle, "data.parquet")

    exporter = importlib.import_module("macro_data.exporter")
    report = exporter.validate_bundle(bundle)

    assert report["valid"] is False
    assert any(
        finding["artifact"] == "data.parquet"
        for finding in report["consistency_findings"]
    )


def test_validator_returns_invalid_for_empty_csv_value(
    tmp_path: Path,
) -> None:
    bundle = _export_mixed_bundle(tmp_path)
    path = bundle / "data.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["value"] = ""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    _refresh_run_checksum(bundle, "data.csv")

    exporter = importlib.import_module("macro_data.exporter")
    report = exporter.validate_bundle(bundle)

    assert report["valid"] is False
    assert any(
        finding["artifact"] == "data.parquet"
        for finding in report["consistency_findings"]
    )


def test_validator_returns_invalid_for_non_numeric_contribution_ratio(
    tmp_path: Path,
) -> None:
    bundle = _export_mixed_bundle(tmp_path)
    path = bundle / "completion_manifest.json"
    manifest = _load(path)
    manifest["provider_contribution"]["datapro_ratio"] = "not-a-number"
    _write(path, manifest)
    _refresh_run_checksum(bundle, "completion_manifest.json")

    exporter = importlib.import_module("macro_data.exporter")
    report = exporter.validate_bundle(bundle)

    assert report["valid"] is False
    assert report["schema_findings"]


@pytest.mark.parametrize("column", ("license_ref", "cell_id"))
def test_validator_rejects_missing_provenance_column_in_both_formats(
    tmp_path: Path,
    column: str,
) -> None:
    bundle = _export_mixed_bundle(tmp_path)
    csv_path = bundle / "data.csv"
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row.pop(column)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)

    parquet_path = bundle / "data.parquet"
    table = pq.read_table(parquet_path)
    keep = [name for name in table.column_names if name != column]
    pq.write_table(table.select(keep), parquet_path, compression="zstd")
    _refresh_run_checksum(bundle, "data.csv")
    _refresh_run_checksum(bundle, "data.parquet")

    exporter = importlib.import_module("macro_data.exporter")
    report = exporter.validate_bundle(bundle)

    assert report["valid"] is False
    assert any(
        finding["path"] == "columns"
        for finding in report["consistency_findings"]
    )


@pytest.mark.parametrize(
    ("mutation", "expected_path"),
    (
        ("matrix_checksum", "matrix_checksum"),
        ("gap_manifest_id", "gap_manifest_id"),
        ("official_cells", "official_fallback_cell_ids"),
        ("raw_file", "raw_bindings/"),
        ("quality_status", "delivery_eligibility"),
    ),
)
def test_completion_bundle_rejects_cross_artifact_binding_tampering(
    tmp_path: Path,
    mutation: str,
    expected_path: str,
) -> None:
    bundle = _export_mixed_bundle(tmp_path)
    if mutation in {"matrix_checksum", "gap_manifest_id", "official_cells"}:
        path = bundle / "completion_manifest.json"
        document = _load(path)
        if mutation == "matrix_checksum":
            document["matrix_checksum"] = "sha256:" + "f" * 64
        elif mutation == "gap_manifest_id":
            document["gap_manifest_id"] = "macro-gaps-" + "f" * 32
        else:
            document["official_fallback_cell_ids"] = []
        _write(path, document)
        _refresh_run_checksum(bundle, "completion_manifest.json")
    elif mutation == "raw_file":
        manifest = _load(bundle / "completion_manifest.json")
        (bundle / manifest["retrievals"][1]["raw_artifact"]).unlink()
    else:
        path = bundle / "quality_report.json"
        document = _load(path)
        document["delivery_eligibility"] = "not_deliverable"
        _write(path, document)
        _refresh_run_checksum(bundle, "quality_report.json")

    exporter = importlib.import_module("macro_data.exporter")
    report = exporter.validate_bundle(bundle)

    assert report["valid"] is False
    assert any(
        expected_path in finding["path"]
        for finding in report["consistency_findings"]
    )


def test_existing_v02_bundle_checksums_and_validation_do_not_change(
    tmp_path: Path,
) -> None:
    pipeline = importlib.import_module("macro_data.pipeline")
    exporter = importlib.import_module("macro_data.exporter")
    fixture = _load(ROOT / "fixtures" / "sanitized-live" / "02_china_monthly_cpi.json")
    query = cast(dict[str, str], fixture["request"])["query"]
    first = tmp_path / "first"
    second = tmp_path / "second"

    pipeline.run_macro_data(
        research_question=query,
        source_payload=fixture,
        output_dir=first,
        input_mode="sanitized-live-replay",
    )
    pipeline.run_macro_data(
        research_question=query,
        source_payload=fixture,
        output_dir=second,
        input_mode="sanitized-live-replay",
    )

    first_checksums = {
        path.name: sha256_file(path) for path in first.iterdir() if path.is_file()
    }
    second_checksums = {
        path.name: sha256_file(path) for path in second.iterdir() if path.is_file()
    }
    assert first_checksums == second_checksums
    assert exporter.validate_bundle(first)["valid"] is True
