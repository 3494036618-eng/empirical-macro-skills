"""Transactional export and validation for robustness-audit bundles."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import matplotlib
import numpy as np
import pandas as pd

from robustness_audit.bundle_semantics import (
    plan_checksum_errors,
    planned_alternative_errors,
    semantic_errors,
    summary_errors,
)
from robustness_audit.claim_policy import assert_audit_summary_language
from robustness_audit.contracts import validate_document
from robustness_audit.identifiers import canonical_sha256

REQUIRED_FILES = {
    "audit-request.json",
    "audit-plan.json",
    "audit-result.json",
    "check-results.json",
    "comparison-paths.csv",
    "comparison-paths.png",
    "technical-summary.md",
    "plain-language-summary.md",
    "run-manifest.json",
}
CHECKSUM_FILES = REQUIRED_FILES - {"run-manifest.json"}


def _json_bytes(document: object) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode(
            "utf-8"
        )
        + b"\n"
    )


def write_json(path: Path, document: object) -> None:
    path.write_bytes(_json_bytes(document))


def write_comparison_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "alternative_id",
        "check_id",
        "horizon",
        "baseline_estimate",
        "alternative_estimate",
        "estimate_delta",
        "baseline_standard_error",
        "alternative_standard_error",
        "baseline_nobs",
        "alternative_nobs",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            {field: row[field] for field in fieldnames} for row in rows
        )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def directory_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    for item in files:
        digest.update(str(item.relative_to(path)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _without_runtime_fields(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_runtime_fields(item)
            for key, item in value.items()
            if key
            not in {
                "duration_seconds",
                "execution_error",
                "generated_at",
                "stderr",
                "stdout",
            }
        }
    if isinstance(value, list):
        return [_without_runtime_fields(item) for item in value]
    return value


def _semantic_file_bytes(path: Path) -> bytes:
    payload = path.read_bytes()
    if path.suffix != ".json":
        return payload
    try:
        document = json.loads(payload)
    except json.JSONDecodeError:
        return payload
    return _json_bytes(_without_runtime_fields(document))


def _semantic_file_sha256(path: Path) -> str:
    return hashlib.sha256(_semantic_file_bytes(path)).hexdigest()


def _semantic_directory_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(str(item.relative_to(path)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(_semantic_file_bytes(item))
        digest.update(b"\0")
    return digest.hexdigest()


def build_manifest(
    staging: Path,
    audit_request_id: str,
    audit_plan_id: str,
    input_checksums: dict[str, str],
) -> dict[str, object]:
    output_checksums = {
        filename: sha256_file(staging / filename)
        for filename in sorted(CHECKSUM_FILES)
    }
    alternative_root = staging / "alternative-bundles"
    alternative_checksums = {
        item.name: directory_sha256(item)
        for item in sorted(alternative_root.iterdir())
        if item.is_dir()
    }
    alternative_identities = {
        item.name: _semantic_directory_sha256(item)
        for item in sorted(alternative_root.iterdir())
        if item.is_dir()
    }
    output_identities = {
        filename: _semantic_file_sha256(staging / filename)
        for filename in sorted(CHECKSUM_FILES)
    }
    fingerprint = {
        "audit_request_ref": audit_request_id,
        "audit_plan_ref": audit_plan_id,
        "inputs": input_checksums,
        "outputs": output_identities,
        "alternatives": alternative_identities,
    }
    return {
        "schema_version": "0.1.0",
        "run_id": f"ra-run-{canonical_sha256(fingerprint)[:32]}",
        "audit_request_ref": audit_request_id,
        "audit_plan_ref": audit_plan_id,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "input_checksums": input_checksums,
        "output_checksums": output_checksums,
        "alternative_bundle_checksums": alternative_checksums,
        "secrets_recorded": False,
    }


def publish_directory(staging: Path, output_dir: Path) -> None:
    if not output_dir.exists():
        os.replace(staging, output_dir)
        return
    suffix = hashlib.sha256(str(output_dir).encode()).hexdigest()[:16]
    backup = output_dir.with_name(f".{output_dir.name}.backup-{suffix}")
    os.replace(output_dir, backup)
    try:
        os.replace(staging, output_dir)
    except OSError:
        os.replace(backup, output_dir)
        raise
    try:
        shutil.rmtree(backup)
    except OSError:
        pass


def _load(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _contract_errors(
    output_dir: Path,
) -> tuple[list[str], dict[str, object] | None]:
    errors: list[str] = []
    manifest: dict[str, object] | None = None
    for filename, contract in (
        ("audit-request.json", "audit_request"),
        ("audit-plan.json", "audit_plan"),
        ("audit-result.json", "audit_result"),
        ("run-manifest.json", "run_manifest"),
    ):
        try:
            document = _load(output_dir / filename)
            validate_document(contract, document)
            if filename == "run-manifest.json":
                manifest = document
        except (OSError, ValueError, json.JSONDecodeError):
            errors.append(f"contract_violation:{filename}")
    try:
        checks = json.loads(
            (output_dir / "check-results.json").read_text(encoding="utf-8")
        )
        if not isinstance(checks, list):
            raise ValueError("check results must be an array")
        for item in checks:
            validate_document("check_result", cast(dict[str, object], item))
    except (OSError, ValueError, json.JSONDecodeError):
        errors.append("contract_violation:check-results.json")
    return errors, manifest


def _checksum_errors(
    output_dir: Path,
    manifest: dict[str, object] | None,
) -> list[str]:
    if manifest is None:
        return []
    errors: list[str] = []
    outputs = cast(dict[str, object], manifest["output_checksums"])
    for filename in CHECKSUM_FILES:
        if outputs.get(filename) != sha256_file(output_dir / filename):
            errors.append(f"checksum_mismatch:{filename}")
    alternatives = cast(
        dict[str, object],
        manifest["alternative_bundle_checksums"],
    )
    root = output_dir / "alternative-bundles"
    observed = {item.name for item in root.iterdir() if item.is_dir()}
    if observed != set(alternatives):
        errors.append("alternative_set_mismatch")
    for name in observed & set(alternatives):
        if alternatives[name] != directory_sha256(root / name):
            errors.append(f"alternative_checksum_mismatch:{name}")
    return errors


def _content_errors(output_dir: Path) -> list[str]:
    errors: list[str] = []
    png = (output_dir / "comparison-paths.png").read_bytes()
    if len(png) < 1024 or not png.startswith(b"\x89PNG\r\n\x1a\n"):
        errors.append("png_invalid")
    try:
        result = _load(output_dir / "audit-result.json")
        summary = (output_dir / "plain-language-summary.md").read_text(
            encoding="utf-8"
        )
        assert_audit_summary_language(summary, str(result["claim_eligibility"]))
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        errors.append("claim_language_violation")
    return errors


def _manifest_identity_errors(
    output_dir: Path,
    manifest: dict[str, object] | None,
) -> list[str]:
    if manifest is None:
        return []
    fingerprint = {
        "audit_request_ref": manifest["audit_request_ref"],
        "audit_plan_ref": manifest["audit_plan_ref"],
        "inputs": manifest["input_checksums"],
        "outputs": {
            filename: _semantic_file_sha256(output_dir / filename)
            for filename in sorted(CHECKSUM_FILES)
        },
        "alternatives": {
            item.name: _semantic_directory_sha256(item)
            for item in sorted(
                (output_dir / "alternative-bundles").iterdir()
            )
            if item.is_dir()
        },
    }
    expected = f"ra-run-{canonical_sha256(fingerprint)[:32]}"
    if manifest.get("run_id") != expected:
        return ["manifest_identity_mismatch"]
    return []


def validate_bundle(output_dir: Path) -> dict[str, object]:
    if not output_dir.is_dir():
        return {"valid": False, "errors": ["bundle_missing"]}
    observed = {path.name for path in output_dir.iterdir() if path.is_file()}
    errors = [f"artifact_missing:{name}" for name in sorted(REQUIRED_FILES - observed)]
    errors.extend(f"artifact_unexpected:{name}" for name in sorted(observed - REQUIRED_FILES))
    alternative_root = output_dir / "alternative-bundles"
    if not alternative_root.is_dir():
        errors.append("alternative_bundles_missing")
    if errors:
        return {"valid": False, "errors": errors}
    contract_errors, manifest = _contract_errors(output_dir)
    errors.extend(contract_errors)
    errors.extend(_checksum_errors(output_dir, manifest))
    errors.extend(plan_checksum_errors(output_dir))
    errors.extend(_manifest_identity_errors(output_dir, manifest))
    errors.extend(semantic_errors(output_dir))
    errors.extend(planned_alternative_errors(output_dir))
    errors.extend(summary_errors(output_dir))
    errors.extend(_content_errors(output_dir))
    return {"valid": not errors, "errors": sorted(set(errors))}
