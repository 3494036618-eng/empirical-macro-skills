from __future__ import annotations

import importlib.util
from dataclasses import FrozenInstanceError
from importlib import import_module
from pathlib import Path

import pytest


def test_identifier_and_model_modules_exist() -> None:
    assert importlib.util.find_spec("research_synthesis.identifiers") is not None
    assert importlib.util.find_spec("research_synthesis.models") is not None


def test_runtime_fields_do_not_change_scientific_identity() -> None:
    identifiers = import_module("research_synthesis.identifiers")
    required = {
        "canonical_json_bytes",
        "canonical_sha256",
        "content_id",
        "scientific_content_id",
        "sha256_file",
    }
    assert required <= set(dir(identifiers))
    first = {"value": 1, "generated_at": "2026-08-17T00:00:00Z"}
    second = {"value": 1, "generated_at": "2026-08-17T01:00:00Z"}

    assert identifiers.scientific_content_id("rs-result", first) == (
        identifiers.scientific_content_id("rs-result", second)
    )
    assert identifiers.content_id("rs-result", first) != (
        identifiers.content_id("rs-result", second)
    )


def test_semantic_changes_and_file_bytes_change_identity(tmp_path: Path) -> None:
    identifiers = import_module("research_synthesis.identifiers")
    assert identifiers.scientific_content_id(
        "rs-claim", {"estimate": 1.0}
    ) != identifiers.scientific_content_id(
        "rs-claim", {"estimate": 1.1}
    )
    path = tmp_path / "artifact.txt"
    path.write_bytes(b"evidence\n")

    assert identifiers.sha256_file(path) == (
        "bdcf4c994585af6dd6cb1cfbff78bcc73ab27dc30a299db5bb83766ca05b5de4"
    )


def test_boundary_models_are_frozen() -> None:
    models = import_module("research_synthesis.models")
    required = {
        "BundleReference",
        "ResolvedBundle",
        "ValidationEvidence",
        "EvidenceEnvelope",
        "ReportInputs",
    }
    assert required <= set(dir(models))
    reference = models.BundleReference(
        bundle_ref_id="rs-bundle-ref-" + "a" * 32,
        artifact_role="estimator",
        skill_name="time-series-dynamics",
        skill_version="0.1.0",
        bundle_path=Path("bundle"),
        manifest_path=Path("run-manifest.json"),
        expected_manifest_sha256="sha256:" + "a" * 64,
        expected_ids={"run_id": "tsd-run-example"},
        required=True,
    )

    with pytest.raises(FrozenInstanceError):
        reference.skill_name = "changed"
