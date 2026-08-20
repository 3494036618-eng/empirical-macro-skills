"""解析并验证显式 bundle references。"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from research_synthesis.contracts import validate_document
from research_synthesis.identifiers import sha256_file
from research_synthesis.models import BundleReference, ResolvedBundle


def _safe_relative_path(value: object, field: str) -> Path:
    if not isinstance(value, str):
        raise ValueError(f"{field}_invalid")
    path = Path(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or any(marker in value for marker in ("*", "?"))
    ):
        raise ValueError(f"{field}_must_be_explicit")
    return path


def resolve_bundle_ref(
    document: dict[str, object],
    project_root: Path,
) -> ResolvedBundle:
    """解析 bundle 路径并验证 manifest 物理 checksum。"""
    relative_bundle = _safe_relative_path(
        document.get("bundle_path"),
        "bundle_path",
    )
    relative_manifest = _safe_relative_path(
        document.get("manifest_path"),
        "manifest_path",
    )
    validate_document("bundle_reference", document)
    root = project_root.resolve()
    bundle = (root / relative_bundle).resolve()
    try:
        bundle.relative_to(root)
    except ValueError as exc:
        raise ValueError("bundle_path_outside_project") from exc
    if not bundle.is_dir():
        raise ValueError("bundle_path_missing")
    manifest = (bundle / relative_manifest).resolve()
    try:
        manifest.relative_to(bundle)
    except ValueError as exc:
        raise ValueError("manifest_path_outside_bundle") from exc
    if not manifest.is_file():
        raise ValueError("manifest_path_missing")
    observed = sha256_file(manifest)
    expected = str(document["expected_manifest_sha256"]).removeprefix(
        "sha256:"
    )
    if observed != expected:
        raise ValueError("manifest_checksum_mismatch")
    reference = BundleReference(
        bundle_ref_id=str(document["bundle_ref_id"]),
        artifact_role=str(document["artifact_role"]),
        skill_name=str(document["skill_name"]),
        skill_version=str(document["skill_version"]),
        bundle_path=relative_bundle,
        manifest_path=relative_manifest,
        expected_manifest_sha256=str(document["expected_manifest_sha256"]),
        expected_ids=cast(dict[str, str], document["expected_ids"]),
        required=bool(document["required"]),
    )
    return ResolvedBundle(
        reference=reference,
        absolute_path=bundle,
        manifest_path=manifest,
        manifest_sha256=observed,
    )
