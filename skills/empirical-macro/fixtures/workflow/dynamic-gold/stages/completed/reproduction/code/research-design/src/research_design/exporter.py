"""Atomic artifact writing and cross-artifact bundle validation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import cast
from uuid import uuid4

from research_design.contracts import load_schema, validate_document

ARTIFACT_CONTRACTS = {
    "research_intake": "intake",
    "research_request": "request",
    "research_plan": "plan",
    "data_requirements": "data_requirements",
    "identification_audit": "identification_audit",
}


def _json_bytes(document: dict[str, object]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode()
        + b"\n"
    )


def write_artifact(
    path: Path,
    document: dict[str, object],
    contract: str,
) -> None:
    validate_document(contract, document)
    payload = _json_bytes(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def artifact_reference(path: Path, contract: str) -> dict[str, str]:
    schema_id = load_schema(contract).get("$id")
    if not isinstance(schema_id, str):
        raise ValueError(f"{contract} schema is missing $id")
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "path": path.name,
        "schema_id": schema_id,
        "sha256": f"sha256:{checksum}",
    }


def _load_document(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _validate_artifact(
    output_dir: Path,
    name: str,
    reference: object,
) -> list[str]:
    if reference is None and name == "identification_audit":
        return []
    if not isinstance(reference, dict):
        return [f"artifact_reference_invalid:{name}"]
    relative = reference.get("path")
    if not isinstance(relative, str):
        return [f"artifact_path_invalid:{name}"]
    path = output_dir / relative
    if output_dir.resolve() not in path.resolve().parents or not path.is_file():
        return [f"artifact_missing:{name}"]
    checksum = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    errors = [] if reference.get("sha256") == checksum else [f"checksum_mismatch:{name}"]
    contract = ARTIFACT_CONTRACTS[name]
    schema_id = load_schema(contract).get("$id")
    if reference.get("schema_id") != schema_id:
        errors.append(f"schema_id_mismatch:{name}")
    try:
        validate_document(contract, _load_document(path))
    except (ValueError, json.JSONDecodeError):
        errors.append(f"artifact_contract_violation:{name}")
    return errors


def _state_errors(output_dir: Path, manifest: dict[str, object]) -> list[str]:
    try:
        plan = _load_document(output_dir / "research_plan.json")
    except (OSError, json.JSONDecodeError):
        return ["research_plan_unreadable"]
    state_fields = ("design_readiness", "claim_eligibility", "review_required")
    if any(manifest.get(field) != plan.get(field) for field in state_fields):
        return ["manifest_plan_state_mismatch"]
    return []


def _macro_reference_errors(output_dir: Path) -> list[str]:
    try:
        requirements = _load_document(output_dir / "data_requirements.json")
    except (OSError, json.JSONDecodeError):
        return ["data_requirements_unreadable"]
    references = requirements.get("macro_data_requests")
    if not isinstance(references, list):
        return ["macro_data_references_invalid"]
    errors: list[str] = []
    for reference in references:
        if not isinstance(reference, dict):
            errors.append("macro_data_reference_invalid")
            continue
        relative = reference.get("artifact_path")
        if not isinstance(relative, str):
            errors.append("macro_data_path_invalid")
            continue
        path = output_dir / relative
        if output_dir.resolve() not in path.resolve().parents or not path.is_file():
            errors.append("artifact_missing:macro_data_request")
            continue
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if reference.get("checksum_sha256") != checksum:
            errors.append("checksum_mismatch:macro_data_request")
        try:
            _load_document(path)
        except (OSError, json.JSONDecodeError):
            errors.append("artifact_contract_violation:macro_data_request")
    return errors


def publish_directory(staging: Path, output_dir: Path) -> None:
    if not output_dir.exists():
        os.replace(staging, output_dir)
        return
    backup = output_dir.with_name(
        f".{output_dir.name}.backup-{uuid4().hex}"
    )
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


def validate_bundle(output_dir: Path) -> dict[str, object]:
    errors: list[str] = []
    manifest_path = output_dir / "research-design-run-manifest.json"
    try:
        manifest = _load_document(manifest_path)
        validate_document("run_manifest", manifest)
    except (OSError, ValueError, json.JSONDecodeError):
        return {"valid": False, "errors": ["manifest_contract_violation"]}
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return {"valid": False, "errors": ["manifest_artifacts_invalid"]}
    for name in ARTIFACT_CONTRACTS:
        errors.extend(_validate_artifact(output_dir, name, artifacts.get(name)))
    errors.extend(_state_errors(output_dir, manifest))
    errors.extend(_macro_reference_errors(output_dir))
    return {"valid": not errors, "errors": sorted(set(errors))}
