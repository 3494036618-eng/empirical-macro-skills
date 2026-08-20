from __future__ import annotations

import importlib.util
import json
from importlib import import_module
from pathlib import Path

import pytest

from research_synthesis.identifiers import sha256_file


def test_validation_boundary_modules_exist() -> None:
    assert importlib.util.find_spec("research_synthesis.bundle_refs") is not None
    assert importlib.util.find_spec("research_synthesis.subprocess_runner") is not None
    assert importlib.util.find_spec("research_synthesis.validator_adapters") is not None


def _bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "run-manifest.json").write_text(
        json.dumps({"run_id": "run-1"}) + "\n",
        encoding="utf-8",
    )
    return bundle


def _reference(bundle: Path, project_root: Path) -> dict[str, object]:
    manifest = bundle / "run-manifest.json"
    return {
        "bundle_ref_id": "rs-bundle-ref-" + "a" * 32,
        "artifact_role": "estimator",
        "skill_name": "time-series-dynamics",
        "skill_version": "0.1.0",
        "bundle_path": str(bundle.relative_to(project_root)),
        "manifest_path": "run-manifest.json",
        "expected_manifest_sha256": f"sha256:{sha256_file(manifest)}",
        "expected_ids": {"run_id": "run-1"},
        "required": True,
    }


def test_resolver_accepts_explicit_bound_bundle(tmp_path: Path) -> None:
    module = import_module("research_synthesis.bundle_refs")
    assert hasattr(module, "resolve_bundle_ref")
    bundle = _bundle(tmp_path)

    resolved = module.resolve_bundle_ref(_reference(bundle, tmp_path), tmp_path)

    assert resolved.absolute_path == bundle.resolve()
    assert resolved.manifest_sha256 == sha256_file(
        bundle / "run-manifest.json"
    )


@pytest.mark.parametrize("relative", ["../outside", "/absolute", "bundle/*"])
def test_resolver_rejects_unsafe_paths(
    tmp_path: Path,
    relative: str,
) -> None:
    module = import_module("research_synthesis.bundle_refs")
    assert hasattr(module, "resolve_bundle_ref")
    bundle = _bundle(tmp_path)
    document = _reference(bundle, tmp_path)
    document["bundle_path"] = relative

    with pytest.raises(ValueError, match="bundle_path"):
        module.resolve_bundle_ref(document, tmp_path)


def test_resolver_rejects_manifest_checksum_mismatch(tmp_path: Path) -> None:
    module = import_module("research_synthesis.bundle_refs")
    assert hasattr(module, "resolve_bundle_ref")
    bundle = _bundle(tmp_path)
    document = _reference(bundle, tmp_path)
    document["expected_manifest_sha256"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="manifest_checksum_mismatch"):
        module.resolve_bundle_ref(document, tmp_path)


def test_resolver_rejects_non_string_path(tmp_path: Path) -> None:
    module = import_module("research_synthesis.bundle_refs")
    bundle = _bundle(tmp_path)
    document = _reference(bundle, tmp_path)
    document["bundle_path"] = None

    with pytest.raises(ValueError, match="bundle_path_invalid"):
        module.resolve_bundle_ref(document, tmp_path)


def test_resolver_rejects_missing_bundle_and_manifest(tmp_path: Path) -> None:
    module = import_module("research_synthesis.bundle_refs")
    bundle = _bundle(tmp_path)
    missing_bundle = _reference(bundle, tmp_path)
    missing_bundle["bundle_path"] = "missing"
    missing_manifest = _reference(bundle, tmp_path)
    missing_manifest["manifest_path"] = "missing.json"

    with pytest.raises(ValueError, match="bundle_path_missing"):
        module.resolve_bundle_ref(missing_bundle, tmp_path)
    with pytest.raises(ValueError, match="manifest_path_missing"):
        module.resolve_bundle_ref(missing_manifest, tmp_path)


def test_resolver_rejects_manifest_symlink_escape(tmp_path: Path) -> None:
    module = import_module("research_synthesis.bundle_refs")
    bundle = _bundle(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    (bundle / "escape.json").symlink_to(outside)
    document = _reference(bundle, tmp_path)
    document["manifest_path"] = "escape.json"

    with pytest.raises(ValueError, match="manifest_path_outside_bundle"):
        module.resolve_bundle_ref(document, tmp_path)
