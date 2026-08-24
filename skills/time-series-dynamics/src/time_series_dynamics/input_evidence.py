"""Materialize and validate estimator input evidence."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import cast
from uuid import uuid4

from jsonschema import ValidationError

from time_series_dynamics.contracts import validate_document

FILES = {
    "macro-data-handoff.json": "macro",
    "shock-identification-artifact.json": "shock",
    "source-manifest.json": "source",
    "aggregatedata_final.dta": "data",
}
MANIFEST = "input-evidence-manifest.json"
REQUIRED_FILES = {*FILES, MANIFEST}


def _load(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return cast(dict[str, object], document)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _evidence_id(
    macro_result_id: object,
    shock_id: object,
    source_commit: object,
    file_checksums: dict[str, str],
) -> str:
    identity = {
        "macro_result_id": macro_result_id,
        "shock_id": shock_id,
        "source_commit": source_commit,
        "file_checksums": file_checksums,
    }
    return f"tsd-input-evidence-{_canonical_sha256(identity)[:32]}"


def _source_errors(
    macro: dict[str, object],
    shock: dict[str, object],
    source: dict[str, object],
    data_checksum: str,
) -> list[str]:
    errors: list[str] = []
    expected_checksums = {
        str(macro.get("source_checksum")),
        str(shock.get("checksum")),
        str(source.get("member_sha256")),
    }
    if expected_checksums != {data_checksum}:
        errors.append("source_checksum_mismatch")
    macro_period = macro.get("observation_period")
    shock_period = shock.get("coverage")
    expected_period = {
        "start": source.get("sample_start"),
        "end": source.get("sample_end"),
    }
    if macro_period != expected_period or shock_period != expected_period:
        errors.append("sample_window_mismatch")
    frequencies = {macro.get("frequency"), shock.get("frequency")}
    source_frequency = source.get("frequency")
    if source_frequency is not None:
        frequencies.add(source_frequency)
    if len(frequencies) != 1 or next(iter(frequencies)) not in {"M", "Q"}:
        errors.append("frequency_mismatch")
    source_license = source.get("license")
    shock_license = shock.get("license")
    shock_identifier = shock_license.get("identifier") if isinstance(shock_license, dict) else None
    if source_license != "CC0-1.0" or shock_identifier != "CC0-1.0":
        errors.append("license_mismatch")
    return errors


def _publish(staging: Path, output_dir: Path) -> None:
    if not output_dir.exists():
        os.replace(staging, output_dir)
        return
    backup = output_dir.with_name(f".{output_dir.name}.backup-{uuid4().hex}")
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


def _write_staging_bundle(
    staging: Path,
    sources: dict[str, Path],
    macro: dict[str, object],
    shock: dict[str, object],
    source: dict[str, object],
) -> dict[str, object]:
    for filename, source_path in sources.items():
        shutil.copyfile(source_path, staging / filename)
    checksums = {filename: _sha256(staging / filename) for filename in sorted(sources)}
    manifest = {
        "schema_version": "0.1.0",
        "evidence_id": _evidence_id(
            macro["result_id"],
            shock["shock_id"],
            source["source_commit"],
            checksums,
        ),
        "macro_result_id": macro["result_id"],
        "shock_id": shock["shock_id"],
        "source_commit": source["source_commit"],
        "license": source["license"],
        "frequency": macro["frequency"],
        "sample_window": macro["observation_period"],
        "file_checksums": checksums,
        "secrets_recorded": False,
    }
    validate_document("input_evidence_manifest", manifest)
    (staging / MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def materialize_input_evidence(
    macro_handoff_path: Path,
    shock_artifact_path: Path,
    source_manifest_path: Path,
    data_path: Path,
    output_dir: Path,
) -> dict[str, object]:
    """物化估计器实际使用的数据与识别证据。"""
    macro = _load(macro_handoff_path)
    shock = _load(shock_artifact_path)
    source = _load(source_manifest_path)
    validate_document("macro_data_handoff", macro)
    validate_document("shock_artifact", shock)
    data_checksum = _sha256(data_path)
    errors = _source_errors(macro, shock, source, data_checksum)
    if errors:
        raise ValueError(",".join(sorted(errors)))
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.staging-",
            dir=output_dir.parent,
        )
    )
    sources = {
        "macro-data-handoff.json": macro_handoff_path,
        "shock-identification-artifact.json": shock_artifact_path,
        "source-manifest.json": source_manifest_path,
        "aggregatedata_final.dta": data_path,
    }
    try:
        manifest = _write_staging_bundle(
            staging,
            sources,
            macro,
            shock,
            source,
        )
        validation = validate_input_evidence(staging)
        if validation["valid"] is not True:
            raise ValueError(f"input_evidence_invalid:{validation['errors']}")
        _publish(staging, output_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {
        "valid": True,
        "evidence_id": manifest["evidence_id"],
        "data_sha256": data_checksum,
        "output_dir": str(output_dir),
    }


def _macro_validation_if_applicable(
    output_dir: Path,
) -> dict[str, object] | None:
    manifest_path = output_dir / MANIFEST
    if not manifest_path.is_file():
        return None
    try:
        candidate_manifest = _load(manifest_path)
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
    ):
        return None
    if candidate_manifest.get("evidence_kind") != "macro_data_association":
        return None
    from time_series_dynamics.macro_input_evidence import (
        validate_macro_input_evidence,
    )

    return cast(
        dict[str, object],
        validate_macro_input_evidence(output_dir),
    )


def validate_input_evidence(output_dir: Path) -> dict[str, object]:
    """验证 input-evidence bundle。"""
    if not output_dir.is_dir():
        return {"valid": False, "errors": ["bundle_missing"]}
    macro_validation = _macro_validation_if_applicable(output_dir)
    if macro_validation is not None:
        return macro_validation
    observed = {path.name for path in output_dir.iterdir() if path.is_file()}
    errors = [
        *(f"artifact_missing:{name}" for name in sorted(REQUIRED_FILES - observed)),
        *(f"artifact_unexpected:{name}" for name in sorted(observed - REQUIRED_FILES)),
    ]
    if errors:
        return {"valid": False, "errors": errors}
    try:
        manifest = _load(output_dir / MANIFEST)
        validate_document("input_evidence_manifest", manifest)
        macro = _load(output_dir / "macro-data-handoff.json")
        shock = _load(output_dir / "shock-identification-artifact.json")
        source = _load(output_dir / "source-manifest.json")
        validate_document("macro_data_handoff", macro)
        validate_document("shock_artifact", shock)
    except (OSError, ValueError, ValidationError, json.JSONDecodeError):
        return {"valid": False, "errors": ["contract_violation"]}
    checksums = manifest.get("file_checksums")
    if not isinstance(checksums, dict):
        return {"valid": False, "errors": ["manifest_checksums_invalid"]}
    observed_checksums = {filename: _sha256(output_dir / filename) for filename in FILES}
    for filename in FILES:
        if checksums.get(filename) != observed_checksums[filename]:
            errors.append(f"checksum_mismatch:{filename}")
    errors.extend(
        _source_errors(
            macro,
            shock,
            source,
            _sha256(output_dir / "aggregatedata_final.dta"),
        )
    )
    if manifest.get("macro_result_id") != macro.get("result_id"):
        errors.append("macro_result_id_mismatch")
    if manifest.get("shock_id") != shock.get("shock_id"):
        errors.append("shock_id_mismatch")
    if manifest.get("source_commit") != source.get("source_commit"):
        errors.append("source_commit_mismatch")
    if manifest.get("sample_window") != macro.get("observation_period"):
        errors.append("manifest_sample_window_mismatch")
    if manifest.get("frequency") != macro.get("frequency"):
        errors.append("manifest_frequency_mismatch")
    if manifest.get("license") != source.get("license"):
        errors.append("manifest_license_mismatch")
    expected_evidence_id = _evidence_id(
        macro.get("result_id"),
        shock.get("shock_id"),
        source.get("source_commit"),
        observed_checksums,
    )
    if manifest.get("evidence_id") != expected_evidence_id:
        errors.append("evidence_id_mismatch")
    return {"valid": not errors, "errors": sorted(set(errors))}
