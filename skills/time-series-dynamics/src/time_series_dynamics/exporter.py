"""Transactional export and validation of dynamic-analysis bundles."""

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

import numpy as np
import pandas as pd
import statsmodels  # type: ignore[import-untyped]

from time_series_dynamics.claim_policy import assert_summary_language, claim_policy
from time_series_dynamics.contracts import validate_document
from time_series_dynamics.models import HorizonEstimate

REQUIRED_FILES = {
    "request.json",
    "result.json",
    "diagnostics.json",
    "dynamic-path.csv",
    "dynamic-path.png",
    "technical-summary.md",
    "plain-language-summary.md",
    "run-manifest.json",
}
CHECKSUM_FILES = REQUIRED_FILES - {"run-manifest.json"}


def _json_bytes(document: dict[str, object]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode()
        + b"\n"
    )


def write_json(
    path: Path,
    document: dict[str, object],
    contract: str | None = None,
) -> None:
    if contract is not None:
        validate_document(contract, document)
    path.write_bytes(_json_bytes(document))


def write_csv(path: Path, estimates: tuple[HorizonEstimate, ...]) -> None:
    fieldnames = [
        "horizon",
        "estimate",
        "standard_error",
        "confidence_lower",
        "confidence_upper",
        "nobs",
        "df_resid",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in estimates:
            writer.writerow({field: getattr(item, field) for field in fieldnames})


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_document(document: dict[str, object]) -> str:
    return hashlib.sha256(_json_bytes(document)).hexdigest()


def _runtime_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "statsmodels": statsmodels.__version__,
    }


def build_manifest(
    staging: Path,
    request_id: str,
    input_checksums: dict[str, str],
) -> dict[str, object]:
    output_checksums = {
        filename: sha256_file(staging / filename)
        for filename in sorted(CHECKSUM_FILES)
    }
    fingerprint = json.dumps(
        {
            "request_id": request_id,
            "inputs": input_checksums,
            "outputs": output_checksums,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "schema_version": "0.1.0",
        "run_id": f"tsd-run-{hashlib.sha256(fingerprint).hexdigest()[:32]}",
        "request_id": request_id,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "runtime": _runtime_versions(),
        "input_checksums": input_checksums,
        "output_checksums": output_checksums,
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
    shutil.rmtree(backup)


def _load_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _contract_errors(output_dir: Path) -> tuple[list[str], dict[str, object] | None]:
    errors: list[str] = []
    manifest: dict[str, object] | None = None
    for filename, contract in (
        ("request.json", "request"),
        ("result.json", "result"),
        ("diagnostics.json", "diagnostics"),
        ("run-manifest.json", "run_manifest"),
    ):
        try:
            document = _load_json(output_dir / filename)
            validate_document(contract, document)
            if filename == "run-manifest.json":
                manifest = document
        except (OSError, ValueError, json.JSONDecodeError):
            errors.append(f"contract_violation:{filename}")
    return errors, manifest


def _checksum_errors(
    output_dir: Path,
    manifest: dict[str, object] | None,
) -> list[str]:
    if manifest is None:
        return []
    expected = manifest.get("output_checksums")
    if not isinstance(expected, dict):
        return ["manifest_output_checksums_invalid"]
    errors = []
    for filename in CHECKSUM_FILES:
        actual = sha256_file(output_dir / filename)
        if expected.get(filename) != actual:
            errors.append(f"checksum_mismatch:{filename}")
    return errors


def _content_errors(output_dir: Path) -> list[str]:
    errors: list[str] = []
    png = (output_dir / "dynamic-path.png").read_bytes()
    if len(png) < 1024 or not png.startswith(b"\x89PNG\r\n\x1a\n"):
        errors.append("png_invalid")
    try:
        request = _load_json(output_dir / "request.json")
        policy = claim_policy(str(request["analysis_track"]))
        summary = (output_dir / "plain-language-summary.md").read_text(
            encoding="utf-8"
        )
        assert_summary_language(summary, policy)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        errors.append("claim_language_violation")
    return errors


def validate_bundle(output_dir: Path) -> dict[str, object]:
    if not output_dir.is_dir():
        return {"valid": False, "errors": ["bundle_missing"]}
    observed = {path.name for path in output_dir.iterdir() if path.is_file()}
    errors = [f"artifact_missing:{name}" for name in sorted(REQUIRED_FILES - observed)]
    errors.extend(f"artifact_unexpected:{name}" for name in sorted(observed - REQUIRED_FILES))
    if errors:
        return {"valid": False, "errors": errors}
    contract_errors, manifest = _contract_errors(output_dir)
    errors.extend(contract_errors)
    errors.extend(_checksum_errors(output_dir, manifest))
    errors.extend(_content_errors(output_dir))
    return {"valid": not errors, "errors": sorted(set(errors))}
