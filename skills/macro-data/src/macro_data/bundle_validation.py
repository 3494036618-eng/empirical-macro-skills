"""Validate macro-data bundle contracts, bindings, and secret absence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from macro_data.contracts import validation_errors
from macro_data.provenance import sha256_file

REQUIRED_ARTIFACTS = {
    "data.csv",
    "data.parquet",
    "request_manifest.json",
    "result.json",
    "series_catalog.json",
    "quality_report.json",
    "provenance.json",
    "run_manifest.json",
    "raw_response.json",
}
CHECKSUM_ARTIFACTS = REQUIRED_ARTIFACTS - {"run_manifest.json"}
_SECRET_PATTERN = re.compile(
    r"ark-[A-Za-z0-9-]{12,}|Authorization\s*:|"
    r"Bearer\s+[A-Za-z0-9._-]{8,}",
    re.IGNORECASE,
)
_SECRET_SCAN_CHUNK_SIZE = 256 * 1024
_SECRET_SCAN_OVERLAP = 128
_STATUS_FIELDS = (
    "execution_status",
    "research_readiness",
    "delivery_eligibility",
    "eligible_for_estimation",
)


def _contains_secret(path: Path) -> bool:
    carry = ""
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        while chunk := handle.read(_SECRET_SCAN_CHUNK_SIZE):
            text = carry + chunk
            if _SECRET_PATTERN.search(text):
                return True
            carry = text[-_SECRET_SCAN_OVERLAP:]
    return False


def _read_json(
    path: Path,
    *,
    artifact: str,
    findings: list[dict[str, str]],
) -> dict[str, Any] | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        findings.append({"artifact": artifact, "path": "<root>", "message": str(exc)})
        return None
    if not isinstance(document, dict):
        findings.append(
            {
                "artifact": artifact,
                "path": "<root>",
                "message": "artifact must contain a JSON object",
            }
        )
        return None
    return document


def _manifest_consistency_findings(
    *,
    manifest: dict[str, Any],
    documents: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def compare(
        artifact_name: str,
        field: str,
    ) -> None:
        artifact = documents.get(artifact_name)
        if artifact is not None and manifest.get(field) != artifact.get(field):
            findings.append(
                {
                    "artifact": "run_manifest.json",
                    "path": field,
                    "message": f"value differs from {artifact_name}",
                }
            )

    request = documents.get("request_manifest.json")
    if request is not None and manifest.get("request") != request:
        findings.append(
            {
                "artifact": "run_manifest.json",
                "path": "request",
                "message": "value differs from request_manifest.json",
            }
        )
    for field in _STATUS_FIELDS:
        compare("result.json", field)
        compare("quality_report.json", field)
    compare("provenance.json", "run_id")
    compare("provenance.json", "input_mode")
    findings.extend(_provider_and_secret_findings(manifest, documents))
    return findings


def _provider_and_secret_findings(
    manifest: dict[str, Any],
    documents: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    provenance = documents.get("provenance.json")
    if provenance is not None:
        activities = provenance.get("activities") or []
        provider = (
            activities[0].get("parameters", {}).get("provider")
            if activities and isinstance(activities[0], dict)
            else None
        )
        if manifest.get("connector") != provider:
            findings.append(
                {
                    "artifact": "run_manifest.json",
                    "path": "connector",
                    "message": "value differs from provenance provider",
                }
            )
    if manifest.get("secrets_recorded") is not False:
        findings.append(
            {
                "artifact": "run_manifest.json",
                "path": "secrets_recorded",
                "message": "must be false",
            }
        )
    return findings


def _read_manifest(
    output_dir: Path,
    schema_findings: list[dict[str, str]],
) -> dict[str, Any] | None:
    path = output_dir / "run_manifest.json"
    if not path.exists():
        return None
    manifest = _read_json(
        path,
        artifact="run_manifest.json",
        findings=schema_findings,
    )
    if manifest is not None:
        schema_findings.extend(
            {"artifact": "run_manifest.json", **finding}
            for finding in validation_errors("run_manifest", manifest)
        )
    return manifest


def _checksum_findings(
    output_dir: Path,
    manifest: dict[str, Any] | None,
) -> tuple[
    list[str],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    if manifest is None:
        return [], [], []
    recorded = manifest.get("artifacts")
    if not isinstance(recorded, dict):
        return (
            [],
            [],
            [
                {
                    "artifact": "run_manifest.json",
                    "path": "artifacts",
                    "message": "must be an object",
                }
            ],
        )
    names = set(recorded)
    mismatches = sorted(CHECKSUM_ARTIFACTS - names)
    unexpected = [
        {
            "artifact": "run_manifest.json",
            "path": f"artifacts/{name}",
            "message": "unexpected artifact checksum",
        }
        for name in sorted(names - CHECKSUM_ARTIFACTS)
    ]
    for name in sorted(CHECKSUM_ARTIFACTS & names):
        expected = recorded[name]
        path = output_dir / name
        if not isinstance(expected, str) or not path.exists() or sha256_file(path) != expected:
            mismatches.append(name)
    return mismatches, unexpected, []


def _contract_documents(
    output_dir: Path,
    schema_findings: list[dict[str, str]],
) -> dict[str, dict[str, Any]]:
    contracts = {
        "request_manifest.json": "request",
        "provenance.json": "provenance",
        "result.json": "result",
    }
    documents: dict[str, dict[str, Any]] = {}
    for name, contract in contracts.items():
        path = output_dir / name
        if not path.exists():
            continue
        document = _read_json(
            path,
            artifact=name,
            findings=schema_findings,
        )
        if document is None:
            continue
        documents[name] = document
        schema_findings.extend(
            {"artifact": name, **finding} for finding in validation_errors(contract, document)
        )
    quality_path = output_dir / "quality_report.json"
    if quality_path.exists():
        quality = _read_json(
            quality_path,
            artifact="quality_report.json",
            findings=schema_findings,
        )
        if quality is not None:
            documents["quality_report.json"] = quality
    return documents


def _secret_findings(output_dir: Path, present: set[str]) -> list[str]:
    return [
        name for name in sorted(present - {"data.parquet"}) if _contains_secret(output_dir / name)
    ]


def validate_bundle(output_dir: Path) -> dict[str, Any]:
    present = {path.name for path in output_dir.iterdir() if path.is_file()}
    missing = sorted(REQUIRED_ARTIFACTS - present)
    schema_findings: list[dict[str, str]] = []
    manifest = _read_manifest(output_dir, schema_findings)
    mismatches, consistency_findings, checksum_schema_findings = _checksum_findings(
        output_dir,
        manifest,
    )
    schema_findings.extend(checksum_schema_findings)
    documents = _contract_documents(output_dir, schema_findings)
    if manifest is not None:
        consistency_findings.extend(
            _manifest_consistency_findings(
                manifest=manifest,
                documents=documents,
            )
        )
    secret_findings = _secret_findings(output_dir, present)
    return {
        "valid": not any(
            (
                missing,
                mismatches,
                secret_findings,
                schema_findings,
                consistency_findings,
            )
        ),
        "missing_artifacts": missing,
        "checksum_mismatches": sorted(mismatches),
        "secret_findings": secret_findings,
        "schema_findings": schema_findings,
        "consistency_findings": consistency_findings,
    }
