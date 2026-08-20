"""事务发布 research package 并验证物理 checksums。"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from jsonschema import ValidationError

from research_synthesis.bundle_semantics import semantic_errors
from research_synthesis.contracts import validate_document
from research_synthesis.identifiers import (
    scientific_content_id,
    scientific_sha256,
    sha256_file,
)

AUDIT_CONTRACTS = {
    "request.json": "request",
    "result.json": "result",
    "claim-ledger.json": "claim_ledger",
    "evidence-index.json": "evidence_index",
    "limitations.json": "limitations",
    "reproduction-manifest.json": "reproduction_manifest",
}
AUDIT_FILES = {
    *AUDIT_CONTRACTS,
    "references.json",
    "run-manifest.json",
}
TOP_LEVEL = {
    ".audit",
    "figures",
    "reproduction",
    "research-report.md",
    "tables",
}
SECRET_PATTERN = re.compile(
    (
        r"ark-[A-Za-z0-9-]{12,}"
        r"|Bearer\s+[A-Za-z0-9._-]{8,}"
        r"|sk-[A-Za-z0-9_-]{20,}"
        r"|AKIA[A-Z0-9]{16}"
        r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
        r"|ghp_[A-Za-z0-9]{36}"
        r"|github_pat_[A-Za-z0-9_]{20,}"
        r"|glpat-[A-Za-z0-9_-]{20,}"
        r"|AIza[A-Za-z0-9_-]{35}"
        r"|xox[baprs]-[A-Za-z0-9-]{20,}"
    ),
    re.IGNORECASE,
)
PERSONAL_PATH_PATTERN = re.compile(
    r"/"
    + r"Users/[^/\s]+|/"
    + r"home/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+"
)


def _json_bytes(document: object) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _load(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return cast(dict[str, object], document)


def _files(root: Path, exclude_manifest: bool = False) -> list[Path]:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if exclude_manifest:
        return [
            path
            for path in files
            if path.relative_to(root).as_posix() != ".audit/run-manifest.json"
        ]
    return files


def _checksums(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in _files(root, exclude_manifest=True)
    }


def _scientific_checksums(root: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in _files(root, exclude_manifest=True):
        relative = path.relative_to(root).as_posix()
        if relative.startswith("reproduction/environment/"):
            continue
        if path.suffix == ".json":
            try:
                checksums[relative] = scientific_sha256(
                    json.loads(path.read_text(encoding="utf-8"))
                )
                continue
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass
        checksums[relative] = sha256_file(path)
    return checksums


def _input_checksums(request: dict[str, object]) -> dict[str, str]:
    refs = cast(list[dict[str, object]], request["bundle_refs"])
    return {
        str(ref["artifact_role"]): str(
            ref["expected_manifest_sha256"]
        ).removeprefix("sha256:")
        for ref in refs
    }


def _write_audit_documents(
    staging: Path,
    documents: dict[str, object],
) -> None:
    audit_root = staging / ".audit"
    audit_root.mkdir(parents=True, exist_ok=True)
    for filename, document in documents.items():
        contract = AUDIT_CONTRACTS.get(filename)
        if contract is not None:
            try:
                validate_document(
                    contract,
                    cast(dict[str, object], document),
                )
            except (ValidationError, ValueError, KeyError) as exc:
                raise ValueError(f"contract_violation:{filename}") from exc
        (audit_root / filename).write_bytes(_json_bytes(document))


def _build_manifest(
    staging: Path,
    request: dict[str, object],
    result: dict[str, object],
) -> dict[str, object]:
    inputs = _input_checksums(request)
    outputs = _checksums(staging)
    identity = {
        "request_ref": request["request_id"],
        "result_ref": result["result_id"],
        "inputs": inputs,
        "outputs": _scientific_checksums(staging),
    }
    return {
        "schema_version": "0.1.0",
        "run_id": scientific_content_id("rs-run", identity),
        "request_ref": request["request_id"],
        "result_ref": result["result_id"],
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "runtime": {"python": platform.python_version()},
        "input_checksums": inputs,
        "output_checksums": outputs,
        "secrets_recorded": False,
    }


def _publish(staging: Path, output_dir: Path) -> None:
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


def _contract_errors(output_dir: Path) -> list[str]:
    errors: list[str] = []
    for filename, contract in AUDIT_CONTRACTS.items():
        try:
            validate_document(
                contract,
                _load(output_dir / ".audit" / filename),
            )
        except (
            OSError,
            ValueError,
            KeyError,
            ValidationError,
            json.JSONDecodeError,
        ):
            errors.append(f"contract_violation:{filename}")
    try:
        validate_document(
            "run_manifest",
            _load(output_dir / ".audit" / "run-manifest.json"),
        )
    except (
        OSError,
        ValueError,
        ValidationError,
        json.JSONDecodeError,
    ):
        errors.append("contract_violation:run-manifest.json")
    return errors


def _checksum_errors(output_dir: Path) -> list[str]:
    try:
        manifest = _load(output_dir / ".audit" / "run-manifest.json")
        expected = cast(dict[str, str], manifest["output_checksums"])
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        return []
    observed = _checksums(output_dir)
    errors = [
        f"checksum_mismatch:{name}"
        for name in sorted(set(expected) | set(observed))
        if expected.get(name) != observed.get(name)
    ]
    return errors


def _secret_errors(output_dir: Path) -> list[str]:
    errors: list[str] = []
    for path in _files(output_dir):
        if path.suffix.lower() in {".dta", ".png", ".pyc"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if SECRET_PATTERN.search(text):
            errors.append(f"secret_like_value:{path.relative_to(output_dir)}")
        if PERSONAL_PATH_PATTERN.search(text):
            errors.append(
                f"personal_path_like_value:{path.relative_to(output_dir)}"
            )
    return errors


def _symlink_errors(output_dir: Path) -> list[str]:
    return [
        f"symlink_forbidden:{path.relative_to(output_dir)}"
        for path in sorted(output_dir.rglob("*"))
        if path.is_symlink()
    ]


def _run_identity_errors(output_dir: Path) -> list[str]:
    try:
        manifest = _load(output_dir / ".audit" / "run-manifest.json")
        request = _load(output_dir / ".audit" / "request.json")
        result = _load(output_dir / ".audit" / "result.json")
        inputs = _input_checksums(request)
        identity = {
            "request_ref": request["request_id"],
            "result_ref": result["result_id"],
            "inputs": inputs,
            "outputs": _scientific_checksums(output_dir),
        }
        expected_run_id = scientific_content_id("rs-run", identity)
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        return []
    errors = []
    if manifest.get("run_id") != expected_run_id:
        errors.append("run_id_mismatch")
    if (
        manifest.get("request_ref") != request.get("request_id")
        or manifest.get("result_ref") != result.get("result_id")
        or manifest.get("input_checksums") != inputs
    ):
        errors.append("run_manifest_binding_mismatch")
    return errors


def validate_bundle(output_dir: Path) -> dict[str, object]:
    """验证完整 research package。"""
    if not output_dir.is_dir():
        return {"valid": False, "errors": ["bundle_missing"]}
    symlink_errors = _symlink_errors(output_dir)
    if symlink_errors:
        return {"valid": False, "errors": symlink_errors}
    observed = {path.name for path in output_dir.iterdir()}
    errors = [
        *(f"artifact_missing:{name}" for name in sorted(TOP_LEVEL - observed)),
        *(f"artifact_unexpected:{name}" for name in sorted(observed - TOP_LEVEL)),
    ]
    audit_root = output_dir / ".audit"
    if audit_root.is_dir():
        audit_files = {path.name for path in audit_root.iterdir() if path.is_file()}
        errors.extend(
            f"artifact_missing:.audit/{name}"
            for name in sorted(AUDIT_FILES - audit_files)
        )
        errors.extend(
            f"artifact_unexpected:.audit/{name}"
            for name in sorted(audit_files - AUDIT_FILES)
        )
    if errors:
        return {"valid": False, "errors": errors}
    errors.extend(_contract_errors(output_dir))
    if errors:
        return {"valid": False, "errors": sorted(set(errors))}
    errors.extend(_checksum_errors(output_dir))
    if errors:
        return {"valid": False, "errors": sorted(set(errors))}
    errors.extend(_secret_errors(output_dir))
    if errors:
        return {"valid": False, "errors": sorted(set(errors))}
    errors.extend(semantic_errors(output_dir))
    if errors:
        return {"valid": False, "errors": sorted(set(errors))}
    errors.extend(_run_identity_errors(output_dir))
    return {"valid": not errors, "errors": sorted(set(errors))}


def export_bundle(
    staging: Path,
    output_dir: Path,
    documents: dict[str, object],
) -> dict[str, object]:
    """完成 `.audit` 后验证 staging，再原子发布。"""
    required = {*AUDIT_CONTRACTS, "references.json"}
    if set(documents) != required:
        raise ValueError("audit_document_set_mismatch")
    _write_audit_documents(staging, documents)
    request = cast(dict[str, object], documents["request.json"])
    result = cast(dict[str, object], documents["result.json"])
    manifest = _build_manifest(staging, request, result)
    validate_document("run_manifest", manifest)
    (staging / ".audit" / "run-manifest.json").write_bytes(
        _json_bytes(manifest)
    )
    validation = validate_bundle(staging)
    if validation["valid"] is not True:
        raise ValueError(f"bundle_validation_failed:{validation['errors']}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    _publish(staging, output_dir)
    return validate_bundle(output_dir)
