from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

import time_series_dynamics.input_evidence as input_evidence_module
from time_series_dynamics.input_evidence import (
    materialize_input_evidence,
    validate_input_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
DATA = ROOT / ".cache" / "jorda-taylor-example5" / "aggregatedata_final.dta"
SOURCE_SHA256 = "19ca23c02ff86dd1f7c78018e4052eea98de4ecca879f467c3a9d57f55b38d2c"


def _materialize(output: Path) -> dict[str, object]:
    return materialize_input_evidence(
        macro_handoff_path=FIXTURES / "synthetic" / "jel.macro-result.json",
        shock_artifact_path=FIXTURES / "synthetic" / "jel.shock-artifact.json",
        source_manifest_path=(
            FIXTURES / "external" / "jorda-taylor-example5.source.json"
        ),
        data_path=DATA,
        output_dir=output,
    )


def _load(path: Path) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(path.read_text(encoding="utf-8")),
    )


def _write(path: Path, document: dict[str, object]) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def test_input_evidence_public_surface_exists() -> None:
    assert importlib.util.find_spec("time_series_dynamics.input_evidence") is not None
    assert (ROOT / "scripts" / "materialize_input_evidence.py").is_file()
    assert (ROOT / "scripts" / "validate_input_evidence.py").is_file()
    assert (
        ROOT / "schemas" / "time-series-input-evidence-manifest.schema.json"
    ).is_file()


def test_input_evidence_functions_are_public() -> None:
    spec = importlib.util.find_spec("time_series_dynamics.input_evidence")
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "materialize_input_evidence")
    assert hasattr(module, "validate_input_evidence")


def test_input_evidence_binds_estimator_inputs(tmp_path: Path) -> None:
    result = _materialize(tmp_path / "evidence")

    assert result["valid"] is True
    assert result["data_sha256"] == SOURCE_SHA256
    assert validate_input_evidence(tmp_path / "evidence") == {
        "valid": True,
        "errors": [],
    }


def test_input_evidence_rejects_data_tamper(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    _materialize(output)
    data = output / "aggregatedata_final.dta"
    data.write_bytes(data.read_bytes() + b"tamper")

    result = validate_input_evidence(output)

    assert result["valid"] is False
    assert "checksum_mismatch:aggregatedata_final.dta" in result["errors"]


def test_input_evidence_rejects_stale_id_after_coordinated_resign(
    tmp_path: Path,
) -> None:
    output = tmp_path / "evidence"
    _materialize(output)
    data = output / "aggregatedata_final.dta"
    data.write_bytes(data.read_bytes() + b"coordinated tamper")
    data_sha = hashlib.sha256(data.read_bytes()).hexdigest()
    macro_path = output / "macro-data-handoff.json"
    macro = _load(macro_path)
    macro["source_checksum"] = data_sha
    _write(macro_path, macro)
    shock_path = output / "shock-identification-artifact.json"
    shock = _load(shock_path)
    shock["checksum"] = data_sha
    _write(shock_path, shock)
    source_path = output / "source-manifest.json"
    source = _load(source_path)
    source["member_sha256"] = data_sha
    _write(source_path, source)
    manifest_path = output / "input-evidence-manifest.json"
    manifest = _load(manifest_path)
    manifest["file_checksums"] = {
        filename: hashlib.sha256((output / filename).read_bytes()).hexdigest()
        for filename in (
            "aggregatedata_final.dta",
            "macro-data-handoff.json",
            "shock-identification-artifact.json",
            "source-manifest.json",
        )
    }
    _write(manifest_path, manifest)

    result = validate_input_evidence(output)

    assert result["valid"] is False
    assert "evidence_id_mismatch" in result["errors"]


def test_input_evidence_rejects_missing_and_unexpected_files(
    tmp_path: Path,
) -> None:
    output = tmp_path / "evidence"
    _materialize(output)
    (output / "macro-data-handoff.json").unlink()
    (output / "unexpected.txt").write_text("unexpected", encoding="utf-8")

    result = validate_input_evidence(output)

    assert "artifact_missing:macro-data-handoff.json" in result["errors"]
    assert "artifact_unexpected:unexpected.txt" in result["errors"]


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("macro_result_id", "macro-result-fedcba9876543210", "macro_result_id_mismatch"),
        ("shock_id", "shock-artifact-fedcba9876543210", "shock_id_mismatch"),
        (
            "source_commit",
            "fedcba9876543210fedcba9876543210fedcba98",
            "source_commit_mismatch",
        ),
    ],
)
def test_input_evidence_rejects_manifest_identity_tamper(
    tmp_path: Path,
    field: str,
    value: str,
    issue: str,
) -> None:
    output = tmp_path / "evidence"
    _materialize(output)
    manifest_path = output / "input-evidence-manifest.json"
    manifest = _load(manifest_path)
    manifest[field] = value
    _write(manifest_path, manifest)

    result = validate_input_evidence(output)

    assert issue in result["errors"]


def test_input_evidence_rejects_manifest_metadata_drift(
    tmp_path: Path,
) -> None:
    output = tmp_path / "evidence"
    _materialize(output)
    manifest_path = output / "input-evidence-manifest.json"
    manifest = _load(manifest_path)
    manifest["sample_window"] = {
        "start": "1990Q1",
        "end": "1999Q4",
    }
    _write(manifest_path, manifest)

    result = validate_input_evidence(output)

    assert result["valid"] is False
    assert "manifest_sample_window_mismatch" in result["errors"]


def test_input_evidence_rejects_contract_violation(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    _materialize(output)
    manifest_path = output / "input-evidence-manifest.json"
    manifest = _load(manifest_path)
    manifest["schema_version"] = "9.9.9"
    _write(manifest_path, manifest)

    assert validate_input_evidence(output) == {
        "valid": False,
        "errors": ["contract_violation"],
    }


def test_input_evidence_rejects_source_data_mismatch(tmp_path: Path) -> None:
    tampered = tmp_path / "data.dta"
    tampered.write_bytes(DATA.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="source_checksum_mismatch"):
        materialize_input_evidence(
            FIXTURES / "synthetic" / "jel.macro-result.json",
            FIXTURES / "synthetic" / "jel.shock-artifact.json",
            FIXTURES / "external" / "jorda-taylor-example5.source.json",
            tampered,
            tmp_path / "evidence",
        )


def test_input_evidence_can_replace_previous_output(tmp_path: Path) -> None:
    output = tmp_path / "evidence"

    first = _materialize(output)
    second = _materialize(output)

    assert first["evidence_id"] == second["evidence_id"]
    assert validate_input_evidence(output)["valid"] is True


def test_input_evidence_cleanup_failure_does_not_block_next_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "bundle"
    output.mkdir()
    (output / "sentinel.txt").write_text("old", encoding="utf-8")
    first = tmp_path / "first"
    first.mkdir()
    (first / "sentinel.txt").write_text("first", encoding="utf-8")
    real_rmtree = input_evidence_module.shutil.rmtree
    monkeypatch.setattr(
        input_evidence_module.shutil,
        "rmtree",
        lambda path: (_ for _ in ()).throw(OSError(str(path))),
    )
    input_evidence_module._publish(first, output)
    monkeypatch.setattr(
        input_evidence_module.shutil,
        "rmtree",
        real_rmtree,
    )
    second = tmp_path / "second"
    second.mkdir()
    (second / "sentinel.txt").write_text("second", encoding="utf-8")

    input_evidence_module._publish(second, output)

    assert (output / "sentinel.txt").read_text(encoding="utf-8") == "second"


def test_input_evidence_reports_missing_bundle(tmp_path: Path) -> None:
    assert validate_input_evidence(tmp_path / "missing") == {
        "valid": False,
        "errors": ["bundle_missing"],
    }


def test_input_evidence_cli_round_trip(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    materialize = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/materialize_input_evidence.py",
            "--macro-handoff-json",
            str(FIXTURES / "synthetic" / "jel.macro-result.json"),
            "--shock-artifact-json",
            str(FIXTURES / "synthetic" / "jel.shock-artifact.json"),
            "--source-manifest-json",
            str(FIXTURES / "external" / "jorda-taylor-example5.source.json"),
            "--data",
            str(DATA),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    validation = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/validate_input_evidence.py",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert materialize.returncode == 0, materialize.stderr
    assert json.loads(materialize.stdout)["valid"] is True
    assert validation.returncode == 0, validation.stderr
    assert json.loads(validation.stdout) == {"valid": True, "errors": []}


def _public_macro_inputs(
    tmp_path: Path,
) -> tuple[Path, Path]:
    macro_bundle = tmp_path / "macro"
    macro_bundle.mkdir()
    result = {
        "result_id": "macro-result-1234567890abcdef",
        "research_use": "dynamic_response",
        "execution_status": "success",
        "research_readiness": "ready",
        "delivery_eligibility": "analysis_ready",
        "eligible_for_estimation": True,
        "review_required": False,
        "frequency": "Q",
        "observation_period": {"start": "1985Q1", "end": "2007Q4"},
        "series": [
            {
                "indicator_definition": {"code": code},
                "source": {"provider": "public_research_archive"},
                "dataset": {
                    "name": "Example 5",
                    "version": "655696c1c576b7537c5a939d2c261f0a111ae663",
                },
                "license": {
                    "id": "CC0-1.0",
                    "allows_requested_use": True,
                },
            }
            for code in ("lcpi", "rr_shock", "dlrgdp", "dlcpi", "dstir")
        ],
        "provenance": {"complete": True},
    }
    (macro_bundle / "result.json").write_text(
        json.dumps(result),
        encoding="utf-8",
    )
    public_manifest = tmp_path / "public-artifact.json"
    public_manifest.write_text(
        json.dumps(
            {
                "source": {
                    "title": "Data and code for Local Projections, Example 5",
                    "url": "https://doi.org/10.3886/E208590V1",
                    "version": "655696c1c576b7537c5a939d2c261f0a111ae663",
                    "license": {
                        "id": "CC0-1.0",
                        "allows_requested_use": True,
                    },
                },
                "raw_artifact": {
                    "sha256": SOURCE_SHA256,
                    "path": "aggregatedata_final.dta",
                },
            }
        ),
        encoding="utf-8",
    )
    return macro_bundle, public_manifest


def test_public_macro_bundle_materializes_identified_shock_evidence(
    tmp_path: Path,
) -> None:
    """Break caught: standard macro-data output needs a hand-written second result."""
    from time_series_dynamics.public_input_evidence import (
        materialize_public_input_evidence,
    )

    macro_bundle, public_manifest = _public_macro_inputs(tmp_path)

    materialize_public_input_evidence(
        macro_bundle=macro_bundle,
        public_manifest_path=public_manifest,
        shock_artifact_path=FIXTURES / "synthetic" / "jel.shock-artifact.json",
        data_path=DATA,
        output_dir=tmp_path / "evidence",
    )

    assert validate_input_evidence(tmp_path / "evidence") == {
        "valid": True,
        "errors": [],
    }


def test_public_input_evidence_cli_is_exposed() -> None:
    """Break caught: the public adapter cannot be called by a host Agent."""
    assert (ROOT / "scripts" / "materialize_public_input_evidence.py").is_file()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("not_ready", "not analysis-ready"),
        ("provenance", "provenance is incomplete"),
        ("provider", "not a public research archive"),
        ("version", "version must be a commit"),
        ("license", "not CC0-approved"),
        ("checksum", "source checksum mismatch"),
    ),
)
def test_public_input_evidence_fails_closed(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    """Break caught: unverified public evidence enters identified-shock estimation."""
    from time_series_dynamics.public_input_evidence import (
        materialize_public_input_evidence,
    )

    macro_bundle, public_manifest = _public_macro_inputs(tmp_path)
    result_path = macro_bundle / "result.json"
    result = _load(result_path)
    public = _load(public_manifest)
    if mutation == "not_ready":
        result["delivery_eligibility"] = "not_deliverable"
    elif mutation == "provenance":
        result["provenance"] = {"complete": False}
    elif mutation == "provider":
        series = cast(list[dict[str, object]], result["series"])
        series[0]["source"] = {"provider": "datapro"}
    elif mutation == "version":
        cast(dict[str, object], public["source"])["version"] = "latest"
    elif mutation == "license":
        license_document = cast(
            dict[str, object],
            cast(dict[str, object], public["source"])["license"],
        )
        license_document["allows_requested_use"] = False
    elif mutation == "checksum":
        cast(dict[str, object], public["raw_artifact"])["sha256"] = "0" * 64
    _write(result_path, result)
    _write(public_manifest, public)

    with pytest.raises(ValueError, match=message):
        materialize_public_input_evidence(
            macro_bundle=macro_bundle,
            public_manifest_path=public_manifest,
            shock_artifact_path=FIXTURES / "synthetic" / "jel.shock-artifact.json",
            data_path=DATA,
            output_dir=tmp_path / "evidence",
        )


def test_quick_validate_checks_input_evidence_artifact() -> None:
    run = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/quick_validate.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(run.stdout)

    assert run.returncode == 0, run.stderr
    assert report["input_evidence"]["valid"] is True
