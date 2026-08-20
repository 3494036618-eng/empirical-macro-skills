from __future__ import annotations

import hashlib
import json
import os
from importlib import import_module
from pathlib import Path

import pytest

from research_synthesis.claim_compiler import compile_claim_ledger
from research_synthesis.evidence_index import compile_evidence_index
from research_synthesis.identifiers import content_id
from research_synthesis.limitations import compile_limitations
from research_synthesis.models import ReportInputs
from research_synthesis.report_builder import build_report, copy_report_assets
from tests.conftest import FIXTURES, load_json
from tests.factories import (
    MODULES,
    ROOT,
    real_envelopes,
    real_resolved_bundles,
)


def test_reproduction_package_contains_code_data_and_chinese_guidance(
    tmp_path: Path,
) -> None:
    module = import_module("research_synthesis.reproduction")
    assert hasattr(module, "build_reproduction_package")
    source_roots = {
        "research-synthesis": ROOT,
        "research-design": MODULES / "research-design",
    }
    bundle_paths = {
        role: bundle.absolute_path
        for role, bundle in real_resolved_bundles().items()
    }

    summary = module.build_reproduction_package(
        tmp_path,
        source_roots,
        bundle_paths,
    )

    readme = (tmp_path / "reproduction" / "README.md").read_text(
        encoding="utf-8"
    )
    availability = (
        tmp_path / "reproduction" / "data-availability-statement.md"
    ).read_text(encoding="utf-8")
    assert "复现说明" in readme
    assert "Data and code for Local Projections, Example 5" in availability
    assert (tmp_path / "reproduction" / "code" / "research-synthesis").is_dir()
    assert (
        tmp_path
        / "reproduction"
        / "data-and-evidence"
        / "estimator"
        / "result.json"
    ).is_file()
    evidence_root = tmp_path / "reproduction" / "data-and-evidence"
    assert {
        path.name for path in evidence_root.iterdir() if path.is_dir()
    } == {
        "estimator",
        "macro-data",
        "research-design",
        "robustness-audit",
    }
    assert summary["bundle_count"] == 4


def test_reproduction_rejects_source_symlink(tmp_path: Path) -> None:
    module = import_module("research_synthesis.reproduction")
    source = tmp_path / "source"
    (source / "src").mkdir(parents=True)
    outside = tmp_path / "outside.py"
    outside.write_text("secret = 'outside'\n", encoding="utf-8")
    (source / "src" / "escape.py").symlink_to(outside)

    with pytest.raises(ValueError, match="source_symlink_forbidden"):
        module.build_reproduction_package(
            tmp_path / "package",
            {"research-synthesis": source},
            {},
        )


def _staging(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    staging = tmp_path / "staging"
    staging.mkdir()
    envelopes = real_envelopes()
    evidence = compile_evidence_index(envelopes)
    claims = compile_claim_ledger(envelopes, evidence)
    limits = compile_limitations(envelopes, claims, evidence)
    request = load_json(FIXTURES / "synthetic" / "request.valid.json")
    inputs = ReportInputs(request, evidence, claims, limits, envelopes)
    (staging / "research-report.md").write_text(
        build_report(inputs),
        encoding="utf-8",
    )
    estimator = (
        MODULES
        / "time-series-dynamics"
        / ".artifacts"
        / "jel-example5-causal"
    )
    copy_report_assets(estimator, staging)
    build_reproduction = import_module(
        "research_synthesis.reproduction"
    ).build_reproduction_package
    build_reproduction(
        staging,
        {"research-synthesis": ROOT},
        {
            role: bundle.absolute_path
            for role, bundle in real_resolved_bundles().items()
        },
    )
    reproduction_manifest = load_json(
        FIXTURES / "contracts" / "reproduction_manifest.valid.json"
    )
    reproduction_manifest["expected_outputs"] = {
        "research-report.md": (
            "sha256:"
            + hashlib.sha256(
                (staging / "research-report.md").read_bytes()
            ).hexdigest()
        )
    }
    result = load_json(FIXTURES / "contracts" / "result.valid.json")
    result_identity = {
        "request_ref": result["request_ref"],
        "claim_ledger_id": claims["claim_ledger_id"],
        "evidence_index_id": evidence["evidence_index_id"],
        "limitations_id": limits["limitations_id"],
    }
    result["result_id"] = content_id("rs-result", result_identity)
    documents = {
        "request.json": request,
        "result.json": result,
        "claim-ledger.json": claims,
        "evidence-index.json": evidence,
        "limitations.json": limits,
        "reproduction-manifest.json": reproduction_manifest,
        "references.json": {"sources": []},
    }
    return staging, documents


def _write_json(path: Path, document: dict[str, object]) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _resign_physical_manifest(package: Path) -> None:
    path = package / ".audit" / "run-manifest.json"
    manifest = _load_json(path)
    manifest["output_checksums"] = {
        item.relative_to(package).as_posix(): hashlib.sha256(
            item.read_bytes()
        ).hexdigest()
        for item in sorted(package.rglob("*"))
        if item.is_file() and item != path
    }
    _write_json(path, manifest)


def test_exporter_publishes_valid_research_package(tmp_path: Path) -> None:
    module = import_module("research_synthesis.exporter")
    assert hasattr(module, "export_bundle")
    assert hasattr(module, "validate_bundle")
    staging, documents = _staging(tmp_path)
    output = tmp_path / "package"

    result = module.export_bundle(staging, output, documents)

    assert result["valid"] is True
    assert module.validate_bundle(output) == {"valid": True, "errors": []}
    assert not [path for path in output.iterdir() if path.suffix == ".json"]


def test_exporter_detects_report_tamper(tmp_path: Path) -> None:
    module = import_module("research_synthesis.exporter")
    staging, documents = _staging(tmp_path)
    output = tmp_path / "package"
    module.export_bundle(staging, output, documents)
    report = output / "research-report.md"
    report.write_text(report.read_text(encoding="utf-8") + "篡改", encoding="utf-8")

    result = module.validate_bundle(output)

    assert result["valid"] is False
    assert "checksum_mismatch:research-report.md" in result["errors"]


def test_export_failure_preserves_previous_bundle(tmp_path: Path) -> None:
    module = import_module("research_synthesis.exporter")
    staging, documents = _staging(tmp_path)
    output = tmp_path / "package"
    output.mkdir()
    (output / "sentinel.txt").write_text("old", encoding="utf-8")
    documents["result.json"] = {"schema_version": "invalid"}

    with pytest.raises(ValueError, match="contract_violation"):
        module.export_bundle(staging, output, documents)

    assert (output / "sentinel.txt").read_text(encoding="utf-8") == "old"


def test_publish_failure_restores_previous_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("research_synthesis.exporter")
    output = tmp_path / "package"
    output.mkdir()
    (output / "sentinel.txt").write_text("old", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "sentinel.txt").write_text("new", encoding="utf-8")
    real_replace = os.replace

    def fail_staging_publish(source: Path, target: Path) -> None:
        if Path(source) == staging:
            raise OSError("publish failed")
        real_replace(source, target)

    monkeypatch.setattr(module.os, "replace", fail_staging_publish)

    with pytest.raises(OSError, match="publish failed"):
        module._publish(staging, output)

    assert (output / "sentinel.txt").read_text(encoding="utf-8") == "old"


def test_backup_cleanup_failure_keeps_new_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("research_synthesis.exporter")
    output = tmp_path / "package"
    output.mkdir()
    (output / "sentinel.txt").write_text("old", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "sentinel.txt").write_text("new", encoding="utf-8")

    def fail_cleanup(path: Path) -> None:
        raise OSError(f"cannot remove {path}")

    monkeypatch.setattr(module.shutil, "rmtree", fail_cleanup)

    module._publish(staging, output)

    assert (output / "sentinel.txt").read_text(encoding="utf-8") == "new"


def test_validate_bundle_reports_missing_directory(tmp_path: Path) -> None:
    module = import_module("research_synthesis.exporter")

    assert module.validate_bundle(tmp_path / "missing") == {
        "valid": False,
        "errors": ["bundle_missing"],
    }


@pytest.mark.parametrize(
    ("filename", "mutation", "issue"),
    [
        (
            "evidence-index.json",
            ("evidence", 0, "locator", "value", "/tampered"),
            "evidence_id_mismatch",
        ),
        (
            "limitations.json",
            ("limitations", 0, "mitigation", None, "tampered mitigation"),
            "limitation_id_mismatch",
        ),
        (
            "result.json",
            ("request_ref", None, None, None, "rs-request-" + "f" * 32),
            "result_id_mismatch",
        ),
    ],
)
def test_validator_recomputes_content_derived_ids(
    tmp_path: Path,
    filename: str,
    mutation: tuple[object, object, object, object, object],
    issue: str,
) -> None:
    module = import_module("research_synthesis.exporter")
    staging, documents = _staging(tmp_path)
    output = tmp_path / "package"
    module.export_bundle(staging, output, documents)
    path = output / ".audit" / filename
    document = _load_json(path)
    keys = [key for key in mutation[:-1] if key is not None]
    value = mutation[-1]
    target: object = document
    for key in keys[:-1]:
        target = target[key]  # type: ignore[index]
    assert isinstance(target, dict)
    target[str(keys[-1])] = value
    _write_json(path, document)
    _resign_physical_manifest(output)

    result = module.validate_bundle(output)

    assert result["valid"] is False
    assert issue in result["errors"]


def test_validator_recomputes_scientific_run_id(tmp_path: Path) -> None:
    module = import_module("research_synthesis.exporter")
    staging, documents = _staging(tmp_path)
    output = tmp_path / "package"
    module.export_bundle(staging, output, documents)
    readme = output / "reproduction" / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\ncoordinated tamper\n",
        encoding="utf-8",
    )
    _resign_physical_manifest(output)

    result = module.validate_bundle(output)

    assert result["valid"] is False
    assert "run_id_mismatch" in result["errors"]


def test_validator_structures_malformed_audit_document(
    tmp_path: Path,
) -> None:
    module = import_module("research_synthesis.exporter")
    staging, documents = _staging(tmp_path)
    output = tmp_path / "package"
    module.export_bundle(staging, output, documents)
    path = output / ".audit" / "claim-ledger.json"
    document = _load_json(path)
    claims = document["claims"]
    assert isinstance(claims, list)
    assert isinstance(claims[0], dict)
    claims[0].pop("claim_id")
    _write_json(path, document)
    _resign_physical_manifest(output)

    result = module.validate_bundle(output)

    assert result["valid"] is False
    assert "contract_violation:claim-ledger.json" in result["errors"]


def test_validator_requires_material_limitations_after_resign(
    tmp_path: Path,
) -> None:
    module = import_module("research_synthesis.exporter")
    staging, documents = _staging(tmp_path)
    output = tmp_path / "package"
    module.export_bundle(staging, output, documents)
    path = output / ".audit" / "limitations.json"
    document = _load_json(path)
    limitations = document["limitations"]
    assert isinstance(limitations, list)
    removed = next(
        item
        for item in limitations
        if str(item["statement"]).startswith("shock_exogeneity:")
    )
    document["limitations"] = [
        item for item in limitations if item is not removed
    ]
    document["limitations_id"] = content_id(
        "rs-limitations",
        {
            "schema_version": document["schema_version"],
            "limitations": document["limitations"],
        },
    )
    _write_json(path, document)
    result_path = output / ".audit" / "result.json"
    result_document = _load_json(result_path)
    claims_document = _load_json(output / ".audit" / "claim-ledger.json")
    evidence_document = _load_json(output / ".audit" / "evidence-index.json")
    result_document["result_id"] = content_id(
        "rs-result",
        {
            "request_ref": result_document["request_ref"],
            "claim_ledger_id": claims_document["claim_ledger_id"],
            "evidence_index_id": evidence_document["evidence_index_id"],
            "limitations_id": document["limitations_id"],
        },
    )
    _write_json(result_path, result_document)
    report = output / "research-report.md"
    report.write_text(
        report.read_text(encoding="utf-8").replace(
            f"- {removed['statement']}\n",
            "",
        ),
        encoding="utf-8",
    )
    _resign_physical_manifest(output)
    manifest_path = output / ".audit" / "run-manifest.json"
    manifest = _load_json(manifest_path)
    request = _load_json(output / ".audit" / "request.json")
    manifest["result_ref"] = result_document["result_id"]
    manifest["run_id"] = module.scientific_content_id(
        "rs-run",
        {
            "request_ref": request["request_id"],
            "result_ref": result_document["result_id"],
            "inputs": module._input_checksums(request),
            "outputs": module._scientific_checksums(output),
        },
    )
    _write_json(manifest_path, manifest)

    result = module.validate_bundle(output)

    assert result["valid"] is False
    assert "required_limitation_missing:shock_exogeneity" in result["errors"]


def test_validator_rejects_symlinked_package_file(tmp_path: Path) -> None:
    module = import_module("research_synthesis.exporter")
    staging, documents = _staging(tmp_path)
    output = tmp_path / "package"
    module.export_bundle(staging, output, documents)
    report = output / "research-report.md"
    outside = tmp_path / "outside-report.md"
    outside.write_bytes(report.read_bytes())
    report.unlink()
    report.symlink_to(outside)
    _resign_physical_manifest(output)

    result = module.validate_bundle(output)

    assert result["valid"] is False
    assert "symlink_forbidden:research-report.md" in result["errors"]


@pytest.mark.parametrize(
    "secret",
    [
        "sk-" + "a" * 32,
        "AKIA" + "A" * 16,
        "-----BEGIN " + "PRIVATE KEY-----",
        "ghp_" + "a" * 36,
        "github_pat_" + "a" * 30,
        "glpat-" + "a" * 20,
        "AIza" + "a" * 35,
        "xoxb-" + "a" * 20,
    ],
)
def test_validator_rejects_common_secret_formats(
    tmp_path: Path,
    secret: str,
) -> None:
    module = import_module("research_synthesis.exporter")
    staging, documents = _staging(tmp_path)
    output = tmp_path / "package"
    module.export_bundle(staging, output, documents)
    readme = output / "reproduction" / "README.md"
    readme.write_text(secret, encoding="utf-8")
    _resign_physical_manifest(output)

    result = module.validate_bundle(output)

    assert result["valid"] is False
    assert "secret_like_value:reproduction/README.md" in result["errors"]


def test_validator_rejects_windows_personal_path(tmp_path: Path) -> None:
    module = import_module("research_synthesis.exporter")
    staging, documents = _staging(tmp_path)
    output = tmp_path / "package"
    module.export_bundle(staging, output, documents)
    readme = output / "reproduction" / "README.md"
    readme.write_text(
        "C:" + "\\Users\\alice\\research\\result.json",
        encoding="utf-8",
    )
    _resign_physical_manifest(output)

    result = module.validate_bundle(output)

    assert result["valid"] is False
    assert "personal_path_like_value:reproduction/README.md" in result["errors"]


def test_cleanup_failure_does_not_block_next_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("research_synthesis.exporter")
    output = tmp_path / "package"
    output.mkdir()
    (output / "sentinel.txt").write_text("old", encoding="utf-8")
    first = tmp_path / "first"
    first.mkdir()
    (first / "sentinel.txt").write_text("first", encoding="utf-8")
    real_rmtree = module.shutil.rmtree
    monkeypatch.setattr(
        module.shutil,
        "rmtree",
        lambda path: (_ for _ in ()).throw(OSError(str(path))),
    )
    module._publish(first, output)
    monkeypatch.setattr(module.shutil, "rmtree", real_rmtree)
    second = tmp_path / "second"
    second.mkdir()
    (second / "sentinel.txt").write_text("second", encoding="utf-8")

    module._publish(second, output)

    assert (output / "sentinel.txt").read_text(encoding="utf-8") == "second"


def test_scientific_checksums_exclude_environment_runtime(
    tmp_path: Path,
) -> None:
    module = import_module("research_synthesis.exporter")
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root, version in ((first, "3.11.9"), (second, "3.12.13")):
        path = root / "reproduction" / "environment"
        path.mkdir(parents=True)
        (path / "runtime.json").write_text(
            json.dumps({"python": version}),
            encoding="utf-8",
        )
        (root / "research-report.md").write_text("same", encoding="utf-8")

    assert module._scientific_checksums(first) == (
        module._scientific_checksums(second)
    )
