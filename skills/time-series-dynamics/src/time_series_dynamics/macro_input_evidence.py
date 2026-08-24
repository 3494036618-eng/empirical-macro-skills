"""Materialize association input evidence from an analysis-ready macro bundle."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import TypedDict, cast
from uuid import uuid4

from jsonschema import ValidationError

from time_series_dynamics.contracts import validate_document
from time_series_dynamics.models import DynamicsRequest, SeriesBinding

FILES = (
    "macro-data-handoff.json",
    "source-manifest.json",
    "data.csv",
)
MANIFEST = "input-evidence-manifest.json"
REQUIRED_FILES = {*FILES, MANIFEST}


class ValidationResult(TypedDict):
    valid: bool
    errors: list[str]


def _load(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError(f"{path.name} must contain a JSON object")
    return cast(dict[str, object], document)


def _write(path: Path, document: object) -> None:
    path.write_text(
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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


def _series_index(
    result: dict[str, object],
) -> dict[tuple[str, str], dict[str, object]]:
    index: dict[tuple[str, str], dict[str, object]] = {}
    for raw in cast(list[dict[str, object]], result["series"]):
        entity = cast(dict[str, object], raw["entity"])
        key = (
            str(raw["series_id"]),
            str(entity["canonical_code"]),
        )
        index[key] = raw
    return index


def _validate_bindings(
    result: dict[str, object],
    bindings: tuple[SeriesBinding, ...],
) -> None:
    series = _series_index(result)
    for binding in bindings:
        item = series.get((binding.series_key, binding.entity_code))
        if item is None:
            raise ValueError(f"macro_series_binding_missing:{binding.variable_id}")
        authorization = item.get("use_authorization")
        if not isinstance(authorization, dict):
            raise ValueError(f"series_authorization_missing:{binding.variable_id}")
        if authorization.get("status") != "authorized":
            raise ValueError(f"series_authorization_denied:{binding.variable_id}")


def _source_summary(
    result: dict[str, object],
) -> dict[str, str]:
    series = cast(list[dict[str, object]], result["series"])
    providers = {str(cast(dict[str, object], item["source"])["provider"]) for item in series}
    datasets = {str(cast(dict[str, object], item["dataset"])["name"]) for item in series}
    if providers != {"datapro"}:
        raise ValueError("macro_provider_not_datapro")
    if len(datasets) != 1:
        raise ValueError("cross_source_stitching_forbidden")
    provenance = cast(dict[str, object], result["provenance"])
    return {
        "provider": "datapro",
        "dataset": next(iter(datasets)),
        "version": str(provenance["run_id"]),
        "license": str(result["product_authorization_ref"]),
    }


def build_macro_handoff(
    result: dict[str, object],
    data_checksum: str,
    bindings: tuple[SeriesBinding, ...],
    frequency: str,
) -> dict[str, object]:
    ready = (
        result.get("execution_status") == "success"
        and result.get("research_readiness") == "ready"
        and result.get("delivery_eligibility") == "analysis_ready"
        and result.get("eligible_for_estimation") is True
        and result.get("review_required") is False
    )
    if not ready:
        raise ValueError("macro_bundle_not_analysis_ready")
    if result.get("frequency") != frequency:
        raise ValueError("frequency_mismatch")
    if result.get("source_checksum") != data_checksum:
        raise ValueError("macro_data_checksum_mismatch")
    _validate_bindings(result, bindings)
    return {
        "schema_version": "0.2.0-beta",
        "evidence_kind": "macro_data_association",
        "result_id": result["result_id"],
        "research_use": "dynamic_response",
        "execution_status": result["execution_status"],
        "research_readiness": result["research_readiness"],
        "delivery_eligibility": result["delivery_eligibility"],
        "eligible_for_estimation": result["eligible_for_estimation"],
        "review_required": result["review_required"],
        "frequency": frequency,
        "observation_period": result["observation_period"],
        "source_checksum": data_checksum,
        "source": _source_summary(result),
        "variables": [binding.variable_id for binding in bindings],
        "provenance_complete": True,
        "data_profile": "canonical_long_table",
        "data_use_scope": result["data_use_scope"],
        "public_payload_policy": result["public_payload_policy"],
        "product_authorization_ref": result["product_authorization_ref"],
        "series_bindings": [asdict(binding) for binding in bindings],
    }


def _source_manifest(
    handoff: dict[str, object],
    data_checksum: str,
) -> dict[str, object]:
    source = cast(dict[str, object], handoff["source"])
    window = cast(dict[str, object], handoff["observation_period"])
    return {
        "schema_version": "0.2.0",
        "source_title": "DataPro professional dataset live result",
        "provider": "datapro",
        "source_version": source["version"],
        "license_or_authorization": handoff["product_authorization_ref"],
        "sample_start": window["start"],
        "sample_end": window["end"],
        "frequency": handoff["frequency"],
        "data_sha256": data_checksum,
    }


def _evidence_id(
    handoff: dict[str, object],
    source: dict[str, object],
    checksums: dict[str, str],
) -> str:
    identity = {
        "macro_result_id": handoff["result_id"],
        "source_version": source["source_version"],
        "product_authorization_ref": handoff["product_authorization_ref"],
        "file_checksums": checksums,
    }
    return f"tsd-input-evidence-{_canonical_sha256(identity)[:32]}"


def _manifest(
    handoff: dict[str, object],
    source: dict[str, object],
    checksums: dict[str, str],
) -> dict[str, object]:
    return {
        "schema_version": "0.2.0",
        "evidence_kind": "macro_data_association",
        "evidence_id": _evidence_id(handoff, source, checksums),
        "macro_result_id": handoff["result_id"],
        "shock_id": None,
        "source_version": source["source_version"],
        "license_or_authorization": source["license_or_authorization"],
        "frequency": handoff["frequency"],
        "sample_window": handoff["observation_period"],
        "file_checksums": checksums,
        "data_profile": "canonical_long_table",
        "product_authorization_ref": handoff["product_authorization_ref"],
        "series_bindings": handoff["series_bindings"],
        "secrets_recorded": False,
    }


def materialize_macro_input_evidence(
    macro_bundle: Path,
    request_document: dict[str, object],
    output_dir: Path,
) -> dict[str, object]:
    validate_document("request", request_document)
    request = DynamicsRequest.from_document(request_document)
    if request.analysis_track != "conditional_dynamic_association":
        raise ValueError("macro_association_track_required")
    if request.data_profile != "canonical_long_table":
        raise ValueError("canonical_data_profile_required")
    result = _load(macro_bundle / "result.json")
    data_path = macro_bundle / "data.csv"
    data_checksum = _sha256(data_path)
    handoff = build_macro_handoff(
        result,
        data_checksum,
        request.series_bindings,
        request.frequency,
    )
    validate_document("macro_data_handoff", handoff)
    source = _source_manifest(handoff, data_checksum)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.staging-",
            dir=output_dir.parent,
        )
    )
    try:
        _write(staging / "macro-data-handoff.json", handoff)
        _write(staging / "source-manifest.json", source)
        shutil.copyfile(data_path, staging / "data.csv")
        checksums = {filename: _sha256(staging / filename) for filename in FILES}
        manifest = _manifest(handoff, source, checksums)
        validate_document("input_evidence_manifest", manifest)
        _write(staging / MANIFEST, manifest)
        validation = validate_macro_input_evidence(staging)
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


def _binding_errors(
    handoff: dict[str, object],
    source: dict[str, object],
    manifest: dict[str, object],
    observed_checksums: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    data_checksum = observed_checksums["data.csv"]
    if handoff.get("source_checksum") != data_checksum:
        errors.append("source_checksum_mismatch")
    if source.get("data_sha256") != data_checksum:
        errors.append("source_manifest_checksum_mismatch")
    if manifest.get("macro_result_id") != handoff.get("result_id"):
        errors.append("macro_result_id_mismatch")
    if manifest.get("source_version") != source.get("source_version"):
        errors.append("source_version_mismatch")
    if manifest.get("product_authorization_ref") != handoff.get(
        "product_authorization_ref"
    ) or manifest.get("license_or_authorization") != source.get("license_or_authorization"):
        errors.append("product_authorization_mismatch")
    if manifest.get("sample_window") != handoff.get("observation_period"):
        errors.append("manifest_sample_window_mismatch")
    if manifest.get("frequency") != handoff.get("frequency"):
        errors.append("manifest_frequency_mismatch")
    return errors


def validate_macro_input_evidence(
    output_dir: Path,
) -> ValidationResult:
    if not output_dir.is_dir():
        return {"valid": False, "errors": ["bundle_missing"]}
    observed = {path.name for path in output_dir.iterdir()}
    errors = [
        *(f"artifact_missing:{name}" for name in sorted(REQUIRED_FILES - observed)),
        *(f"artifact_unexpected:{name}" for name in sorted(observed - REQUIRED_FILES)),
    ]
    if errors:
        return {"valid": False, "errors": errors}
    symlinks = [
        f"symlink_forbidden:{path.name}" for path in output_dir.iterdir() if path.is_symlink()
    ]
    if symlinks:
        return {"valid": False, "errors": sorted(symlinks)}
    try:
        manifest = _load(output_dir / MANIFEST)
        handoff = _load(output_dir / "macro-data-handoff.json")
        source = _load(output_dir / "source-manifest.json")
        validate_document("input_evidence_manifest", manifest)
        validate_document("macro_data_handoff", handoff)
    except (
        OSError,
        TypeError,
        ValueError,
        ValidationError,
        json.JSONDecodeError,
    ):
        return {"valid": False, "errors": ["contract_violation"]}
    recorded = manifest.get("file_checksums")
    if not isinstance(recorded, dict):
        return {
            "valid": False,
            "errors": ["manifest_checksums_invalid"],
        }
    observed_checksums = {filename: _sha256(output_dir / filename) for filename in FILES}
    for filename, checksum in observed_checksums.items():
        if recorded.get(filename) != checksum:
            errors.append(f"checksum_mismatch:{filename}")
    errors.extend(
        _binding_errors(
            handoff,
            source,
            manifest,
            observed_checksums,
        )
    )
    expected_id = _evidence_id(
        handoff,
        source,
        observed_checksums,
    )
    if manifest.get("evidence_id") != expected_id:
        errors.append("evidence_id_mismatch")
    return {"valid": not errors, "errors": sorted(set(errors))}
