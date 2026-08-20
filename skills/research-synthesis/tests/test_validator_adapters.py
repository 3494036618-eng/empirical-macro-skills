from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import pytest

from research_synthesis.models import BundleReference, ResolvedBundle


def _bundle(tmp_path: Path) -> ResolvedBundle:
    path = tmp_path / "bundle"
    path.mkdir()
    manifest = path / "run-manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    reference = BundleReference(
        bundle_ref_id="rs-bundle-ref-" + "a" * 32,
        artifact_role="estimator",
        skill_name="time-series-dynamics",
        skill_version="0.1.0",
        bundle_path=Path("bundle"),
        manifest_path=Path("run-manifest.json"),
        expected_manifest_sha256="sha256:" + "a" * 64,
        expected_ids={"run_id": "run-1"},
        required=True,
    )
    return ResolvedBundle(reference, path, manifest, "a" * 64)


def _capability(script: Path) -> dict[str, object]:
    return {
        "artifact_role": "estimator",
        "skill_name": "time-series-dynamics",
        "skill_version": "0.1.0",
        "working_directory": ".",
        "validator_argv": [sys.executable, str(script), "{bundle}"],
        "timeout_seconds": 10,
    }


def test_adapter_accepts_valid_public_validator(tmp_path: Path) -> None:
    module = import_module("research_synthesis.validator_adapters")
    assert hasattr(module, "validate_upstream_bundle")
    script = tmp_path / "validator.py"
    script.write_text("print('{\"valid\": true, \"errors\": []}')\n")

    evidence = module.validate_upstream_bundle(
        _bundle(tmp_path),
        _capability(script),
    )

    assert evidence.status == "success"
    assert evidence.issue_codes == ()


def test_adapter_rejects_invalid_validator_output(tmp_path: Path) -> None:
    module = import_module("research_synthesis.validator_adapters")
    assert hasattr(module, "validate_upstream_bundle")
    script = tmp_path / "validator.py"
    script.write_text("print('not-json')\n")

    evidence = module.validate_upstream_bundle(
        _bundle(tmp_path),
        _capability(script),
    )

    assert evidence.status == "failed"
    assert evidence.issue_codes == ("validator_output_invalid",)


def test_adapter_rejects_validator_reported_failure(tmp_path: Path) -> None:
    module = import_module("research_synthesis.validator_adapters")
    assert hasattr(module, "validate_upstream_bundle")
    script = tmp_path / "validator.py"
    script.write_text("print('{\"valid\": false, \"errors\": [\"bad\"]}')\n")

    evidence = module.validate_upstream_bundle(
        _bundle(tmp_path),
        _capability(script),
    )

    assert evidence.status == "failed"
    assert evidence.issue_codes == ("upstream_bundle_invalid",)


def test_adapter_rejects_capability_binding_mismatch(tmp_path: Path) -> None:
    module = import_module("research_synthesis.validator_adapters")
    script = tmp_path / "validator.py"
    script.write_text("print('{\"valid\": true}')\n")
    capability = _capability(script)
    capability["skill_name"] = "wrong-skill"

    with pytest.raises(
        ValueError,
        match="adapter_capability_binding_mismatch",
    ):
        module.validate_upstream_bundle(_bundle(tmp_path), capability)


def test_adapter_rejects_missing_working_directory(tmp_path: Path) -> None:
    module = import_module("research_synthesis.validator_adapters")
    script = tmp_path / "validator.py"
    script.write_text("print('{\"valid\": true}')\n")
    capability = _capability(script)
    capability["working_directory"] = "missing"

    with pytest.raises(
        ValueError,
        match="adapter_working_directory_missing",
    ):
        module.validate_upstream_bundle(_bundle(tmp_path), capability)


def test_adapter_preserves_nonzero_validator_failure(tmp_path: Path) -> None:
    module = import_module("research_synthesis.validator_adapters")
    script = tmp_path / "validator.py"
    script.write_text("raise SystemExit(3)\n")

    evidence = module.validate_upstream_bundle(
        _bundle(tmp_path),
        _capability(script),
    )

    assert evidence.status == "failed"
    assert evidence.issue_codes == ("validator_nonzero_exit",)


def test_adapter_rejects_json_without_valid_boolean(tmp_path: Path) -> None:
    module = import_module("research_synthesis.validator_adapters")
    script = tmp_path / "validator.py"
    script.write_text("print('{\"valid\": \"yes\"}')\n")

    evidence = module.validate_upstream_bundle(
        _bundle(tmp_path),
        _capability(script),
    )

    assert evidence.status == "failed"
    assert evidence.issue_codes == ("validator_output_invalid",)
