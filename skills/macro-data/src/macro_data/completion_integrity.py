"""Cross-format and run-manifest integrity checks for completion bundles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

COMPLETION_COLUMNS = (
    "cell_id",
    "canonical_series_id",
    "indicator_code",
    "entity_code",
    "period",
    "value",
    "frequency",
    "retrieval_provider",
    "source_system",
    "dataset_id",
    "native_series_key",
    "origin_role",
    "raw_artifact",
    "raw_checksum",
    "retrieved_at",
    "authorization_ref",
    "license_ref",
)


def parquet_consistency_findings(
    path: Path,
    csv_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Compare every exported CSV field with its Parquet counterpart."""
    try:
        table = pq.read_table(path)
        parquet_rows = table.to_pylist()
    except (OSError, ValueError, TypeError, pa.ArrowException) as exc:
        return [_finding("data.parquet", "<root>", str(exc))]
    columns = list(csv_rows[0]) if csv_rows else list(table.column_names)
    if tuple(columns) != COMPLETION_COLUMNS or tuple(table.column_names) != COMPLETION_COLUMNS:
        return [
            _finding(
                "data.parquet",
                "columns",
                "CSV and Parquet must contain every completion provenance column",
            )
        ]
    try:
        csv_normalized = sorted(
            (_normalized(row, columns) for row in csv_rows),
            key=lambda row: str(row.get("cell_id")),
        )
        parquet_normalized = sorted(
            (_normalized(row, columns) for row in parquet_rows),
            key=lambda row: str(row.get("cell_id")),
        )
    except (ValueError, TypeError) as exc:
        return [_finding("data.parquet", "rows", str(exc))]
    if csv_normalized != parquet_normalized:
        return [
            _finding(
                "data.parquet",
                "rows",
                "values differ from data.csv",
            )
        ]
    return []


def document_consistency_findings(
    documents: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    """Bind quality and run status fields to the validated result."""
    result = documents["result.json"]
    findings: list[dict[str, str]] = []
    for artifact in ("quality_report.json", "run_manifest.json"):
        document = documents.get(artifact)
        if document is None:
            continue
        for field in (
            "execution_status",
            "research_readiness",
            "delivery_eligibility",
            "eligible_for_estimation",
        ):
            if document.get(field) != result.get(field):
                findings.append(
                    _finding(
                        artifact,
                        field,
                        "value differs from result.json",
                    )
                )
    run_manifest = documents.get("run_manifest.json")
    if run_manifest is not None:
        findings.extend(_run_manifest_findings(run_manifest))
    return findings


def _run_manifest_findings(
    manifest: dict[str, Any],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    expected = {
        "schema_version": "0.3.0-beta",
        "macro_data_version": "0.3.0-beta",
        "secrets_recorded": False,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            findings.append(
                _finding(
                    "run_manifest.json",
                    field,
                    f"must equal {value!r}",
                )
            )
    if not isinstance(manifest.get("artifacts"), dict):
        findings.append(
            _finding(
                "run_manifest.json",
                "artifacts",
                "must be an object",
            )
        )
    return findings


def _normalized(
    row: dict[str, Any],
    columns: list[str],
) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for column in columns:
        value = row.get(column)
        if column == "value":
            if not isinstance(value, (str, int, float)):
                raise TypeError("value must be numeric")
            normalized[column] = float(value)
        else:
            normalized[column] = "" if value is None else str(value)
    return normalized


def _finding(artifact: str, path: str, message: str) -> dict[str, str]:
    return {"artifact": artifact, "path": path, "message": message}
