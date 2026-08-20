"""Validate 0.3 completion contracts and physical artifact bindings."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, cast

from macro_data.bundle_validation import _contains_secret, _read_json
from macro_data.completion_assembler import classify_contribution
from macro_data.completion_integrity import (
    document_consistency_findings,
    parquet_consistency_findings,
)
from macro_data.contracts import validation_errors
from macro_data.observation_matrix import build_expected_matrix
from macro_data.provenance import canonical_json, sha256_bytes, sha256_file

REQUIRED_ARTIFACTS = {
    "completion_manifest.json",
    "data.csv",
    "data.parquet",
    "provenance.json",
    "quality_report.json",
    "raw_response.json",
    "request_manifest.json",
    "result.json",
    "run_manifest.json",
    "series_catalog.json",
}
CHECKSUM_ARTIFACTS = REQUIRED_ARTIFACTS - {"run_manifest.json"}


def validate_completion_bundle(output_dir: Path) -> dict[str, Any]:
    """Return a structured fail-closed validation report."""
    present = {
        path.name
        for path in output_dir.iterdir()
        if path.is_file()
    }
    missing = sorted(REQUIRED_ARTIFACTS - present)
    schema_findings: list[dict[str, str]] = []
    documents = _contract_documents(output_dir, schema_findings)
    checksum_mismatches = _checksum_mismatches(output_dir, documents)
    consistency_findings = _consistency_findings(
        output_dir,
        documents,
    )
    secret_findings = _secret_findings(output_dir)
    return {
        "valid": not any(
            (
                missing,
                checksum_mismatches,
                secret_findings,
                schema_findings,
                consistency_findings,
            )
        ),
        "missing_artifacts": missing,
        "checksum_mismatches": checksum_mismatches,
        "secret_findings": secret_findings,
        "schema_findings": schema_findings,
        "consistency_findings": consistency_findings,
    }


def _contract_documents(
    output_dir: Path,
    findings: list[dict[str, str]],
) -> dict[str, dict[str, Any]]:
    contracts = {
        "request_manifest.json": "request",
        "result.json": "result",
        "completion_manifest.json": "completion_manifest",
    }
    documents: dict[str, dict[str, Any]] = {}
    for name, contract in contracts.items():
        document = _read_json(
            output_dir / name,
            artifact=name,
            findings=findings,
        )
        if document is None:
            continue
        documents[name] = document
        findings.extend(
            {"artifact": name, **finding}
            for finding in validation_errors(contract, document)
        )
    completion = documents.get("completion_manifest.json")
    if completion is not None:
        residual = completion.get("residual_gap_manifest")
        if isinstance(residual, dict):
            findings.extend(
                {
                    "artifact": "completion_manifest.json",
                    "path": f"residual_gap_manifest/{finding['path']}",
                    "message": finding["message"],
                }
                for finding in validation_errors(
                    "residual_gap_manifest",
                    cast(dict[str, Any], residual),
                )
            )
    for name in (
        "run_manifest.json",
        "quality_report.json",
        "provenance.json",
    ):
        document = _read_json(
            output_dir / name,
            artifact=name,
            findings=findings,
        )
        if document is not None:
            documents[name] = document
    return documents

def _checksum_mismatches(
    output_dir: Path,
    documents: dict[str, dict[str, Any]],
) -> list[str]:
    manifest = documents.get("run_manifest.json")
    if manifest is None or not isinstance(manifest.get("artifacts"), dict):
        return sorted(CHECKSUM_ARTIFACTS)
    recorded = cast(dict[str, Any], manifest["artifacts"])
    mismatches = set(CHECKSUM_ARTIFACTS - set(recorded))
    for name, expected in recorded.items():
        path = _safe_artifact_path(output_dir, name)
        if (
            path is None
            or not isinstance(expected, str)
            or not path.is_file()
            or sha256_file(path) != expected
        ):
            mismatches.add(name)
    return sorted(mismatches)

def _consistency_findings(
    output_dir: Path,
    documents: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    completion = documents.get("completion_manifest.json")
    request = documents.get("request_manifest.json")
    result = documents.get("result.json")
    if completion is None or request is None or result is None:
        return []
    findings: list[dict[str, str]] = []
    rows = _read_rows(output_dir / "data.csv", findings)
    findings.extend(parquet_consistency_findings(output_dir / "data.parquet", rows))
    _check_matrix_binding(request, completion, findings)
    _check_gap_binding(completion, findings)
    _check_cell_binding(rows, completion, findings)
    _check_contribution(rows, completion, result, findings)
    _check_raw_binding(output_dir, rows, completion, findings)
    findings.extend(document_consistency_findings(documents))
    return findings

def _read_rows(
    path: Path,
    findings: list[dict[str, str]],
) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        findings.append(_finding("data.csv", "<root>", str(exc)))
        return []

def _check_matrix_binding(
    request: dict[str, Any],
    completion: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    try:
        matrix = build_expected_matrix(request)
    except (KeyError, TypeError, ValueError) as exc:
        findings.append(_finding("completion_manifest.json", "matrix_id", str(exc)))
        return
    expected_checksum = sha256_bytes(canonical_json(matrix.as_document()))
    if completion.get("matrix_id") != matrix.matrix_id:
        findings.append(
            _finding(
                "completion_manifest.json",
                "matrix_id",
                "value differs from request-derived matrix",
            )
        )
    if completion.get("matrix_checksum") != expected_checksum:
        findings.append(
            _finding(
                "completion_manifest.json",
                "matrix_checksum",
                "value differs from request-derived matrix",
            )
        )
    if completion.get("expected_observation_count") != len(matrix.cells):
        findings.append(_finding("completion_manifest.json", "expected_observation_count", "value differs from request-derived matrix"))

def _check_gap_binding(
    completion: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    residual = completion.get("residual_gap_manifest")
    if not isinstance(residual, dict):
        return
    for field in ("gap_manifest_id", "matrix_id"):
        if completion.get(field) != residual.get(field):
            findings.append(
                _finding(
                    "completion_manifest.json",
                    field,
                    f"value differs from residual_gap_manifest/{field}",
                )
            )

def _check_cell_binding(
    rows: list[dict[str, str]],
    completion: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    row_ids = [row.get("cell_id", "") for row in rows]
    final_ids = completion.get("final_estimator_cell_ids")
    if len(row_ids) != completion.get("final_estimator_count"):
        findings.append(
            _finding(
                "completion_manifest.json",
                "final_estimator_count",
                "value differs from data.csv row count",
            )
        )
    if not isinstance(final_ids, list) or sorted(row_ids) != sorted(final_ids):
        findings.append(
            _finding(
                "completion_manifest.json",
                "final_estimator_cell_ids",
                "values differ from data.csv",
            )
        )
    datapro_ids = {
        row.get("cell_id", "")
        for row in rows
        if row.get("origin_role") == "datapro_primary"
    }
    recorded_datapro = set(completion.get("datapro_locked_cell_ids") or [])
    if not datapro_ids <= recorded_datapro:
        findings.append(
            _finding(
                "completion_manifest.json",
                "datapro_locked_cell_ids",
                "data.csv primary cells are not fully recorded",
            )
        )
    official_ids = {
        row.get("cell_id", "")
        for row in rows
        if row.get("origin_role") == "official_missing_only"
    }
    if official_ids != set(completion.get("official_fallback_cell_ids") or []):
        findings.append(
            _finding(
                "completion_manifest.json",
                "official_fallback_cell_ids",
                "values differ from data.csv",
            )
        )

def _check_contribution(
    rows: list[dict[str, str]],
    completion: dict[str, Any],
    result: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    datapro = sum(row.get("origin_role") == "datapro_primary" for row in rows)
    official = sum(
        row.get("origin_role") == "official_missing_only" for row in rows
    )
    total = datapro + official
    recorded = completion.get("provider_contribution")
    if not isinstance(recorded, dict):
        return
    if datapro == 0 and completion.get("datapro_attempted") is not True:
        findings.append(_finding("completion_manifest.json", "provider_contribution", "zero DataPro cells require an attempted retrieval"))
        return
    expected = {
        "classification": classify_contribution(
            datapro,
            official,
            datapro_attempted=completion.get("datapro_attempted") is True,
        ),
        "datapro_count": datapro,
        "official_fallback_count": official,
        "unresolved_count": completion.get("residual_gap_count"),
        "datapro_ratio": datapro / total if total else 0.0,
        "official_fallback_ratio": official / total if total else 0.0,
    }
    if not _contribution_equal(recorded, expected):
        findings.append(
            _finding(
                "completion_manifest.json",
                "provider_contribution",
                "value cannot be recomputed from data.csv",
            )
        )
    if result.get("provider_contribution") != recorded:
        findings.append(
            _finding(
                "result.json",
                "provider_contribution",
                "value differs from completion_manifest.json",
            )
        )

def _contribution_equal(
    recorded: dict[str, Any],
    expected: dict[str, Any],
) -> bool:
    for key in (
        "classification",
        "datapro_count",
        "official_fallback_count",
        "unresolved_count",
    ):
        if recorded.get(key) != expected[key]:
            return False
    try:
        return all(
            abs(float(recorded.get(key, -1)) - float(expected[key])) <= 1e-12
            for key in ("datapro_ratio", "official_fallback_ratio")
        )
    except (TypeError, ValueError):
        return False

def _check_raw_binding(
    output_dir: Path,
    rows: list[dict[str, str]],
    completion: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    bindings = [
        *rows,
        *cast(list[dict[str, str]], completion.get("retrievals") or []),
    ]
    for index, binding in enumerate(bindings):
        artifact = binding.get("raw_artifact")
        checksum = binding.get("raw_checksum")
        path = _safe_artifact_path(output_dir, artifact)
        if (
            path is None
            or not isinstance(checksum, str)
            or not path.is_file()
            or sha256_file(path) != checksum
        ):
            findings.append(
                _finding(
                    "completion_manifest.json",
                    f"raw_bindings/{index}",
                    "raw artifact or checksum binding is invalid",
                )
            )

def _safe_artifact_path(output_dir: Path, name: object) -> Path | None:
    if not isinstance(name, str) or not name:
        return None
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        return None
    return output_dir / path

def _secret_findings(output_dir: Path) -> list[str]:
    return sorted(
        str(path.relative_to(output_dir))
        for path in output_dir.rglob("*")
        if path.is_file()
        and path.suffix != ".parquet"
        and _contains_secret(path)
    )


def _finding(artifact: str, path: str, message: str) -> dict[str, str]:
    return {"artifact": artifact, "path": path, "message": message}
