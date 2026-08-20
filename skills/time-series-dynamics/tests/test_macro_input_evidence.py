from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "synthetic"


def _request_document() -> dict[str, object]:
    document = json.loads(
        (FIXTURES / "canonical-association.request.json").read_text(encoding="utf-8")
    )
    assert isinstance(document, dict)
    return cast(dict[str, object], document)


def _series(
    series_key: str,
    indicator: str,
) -> dict[str, object]:
    return {
        "series_id": series_key,
        "series_identity": {
            "identity_status": "verified",
            "critical_identity_complete": True,
        },
        "indicator_definition": {
            "code": indicator,
            "name": indicator,
        },
        "entity": {
            "canonical_code": "USA",
            "name": "United States",
        },
        "source": {
            "provider": "datapro",
            "native_source": "IMF_IFS",
        },
        "dataset": {
            "id": "IFS_QUARTERLY",
            "name": "International Financial Statistics",
        },
        "frequency": "Q",
        "use_authorization": {
            "authorization_ref": "product-auth-" + "a" * 32,
            "authorization_basis": "product_owner_directive",
            "scope": "controlled_public_demo",
            "status": "authorized",
        },
    }


def _macro_bundle(
    tmp_path: Path,
    *,
    delivery_eligibility: str = "analysis_ready",
) -> Path:
    bundle = tmp_path / f"macro-{delivery_eligibility}"
    bundle.mkdir()
    data_path = bundle / "data.csv"
    shutil.copyfile(FIXTURES / "canonical-quarterly.csv", data_path)
    data_sha = hashlib.sha256(data_path.read_bytes()).hexdigest()
    ready = delivery_eligibility == "analysis_ready"
    result = {
        "schema_version": "0.2.0-beta",
        "result_id": "macro-result-abcdef0123456789",
        "research_use": "dynamic_response",
        "execution_status": "success",
        "research_readiness": "ready" if ready else "review_required",
        "delivery_eligibility": delivery_eligibility,
        "eligible_for_estimation": ready,
        "review_required": not ready,
        "frequency": "Q",
        "observation_period": {
            "start": "2000Q1",
            "end": "2019Q4",
        },
        "source_checksum": data_sha,
        "data_use_scope": "controlled_public_demo",
        "public_payload_policy": "metadata_only",
        "product_authorization_ref": "product-auth-" + "a" * 32,
        "provenance": {
            "run_id": "run-" + "b" * 32,
            "complete": True,
            "unresolved_links": 0,
        },
        "series": [
            _series("DATASET|USA|CPI_INDEX", "CPI_INDEX"),
            _series("DATASET|USA|POLICY_RATE", "POLICY_RATE"),
            _series("DATASET|USA|REAL_GDP", "REAL_GDP"),
        ],
    }
    (bundle / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return bundle


def _load(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
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


def _mutate_result(
    bundle: Path,
    mutation: str,
) -> None:
    path = bundle / "result.json"
    result = _load(path)
    series = cast(list[dict[str, object]], result["series"])
    if mutation == "frequency":
        result["frequency"] = "M"
    elif mutation == "checksum":
        result["source_checksum"] = "f" * 64
    elif mutation == "binding_missing":
        result["series"] = series[:-1]
    elif mutation == "authorization_missing":
        series[0].pop("use_authorization")
    elif mutation == "authorization_denied":
        authorization = cast(
            dict[str, object],
            series[0]["use_authorization"],
        )
        authorization["status"] = "denied"
    elif mutation == "provider":
        source = cast(dict[str, object], series[0]["source"])
        source["provider"] = "world_bank"
    elif mutation == "dataset":
        dataset = cast(dict[str, object], series[0]["dataset"])
        dataset["name"] = "Another Dataset"
    else:
        raise AssertionError(f"unsupported mutation: {mutation}")
    _write(path, result)


def _resign_file(output: Path, filename: str) -> None:
    manifest_path = output / "input-evidence-manifest.json"
    manifest = _load(manifest_path)
    checksums = cast(dict[str, str], manifest["file_checksums"])
    checksums[filename] = hashlib.sha256((output / filename).read_bytes()).hexdigest()
    _write(manifest_path, manifest)


def test_materializes_association_without_shock(tmp_path: Path) -> None:
    from time_series_dynamics.macro_input_evidence import (
        materialize_macro_input_evidence,
    )

    output = tmp_path / "evidence"
    result = materialize_macro_input_evidence(
        macro_bundle=_macro_bundle(tmp_path),
        request_document=_request_document(),
        output_dir=output,
    )
    manifest = _load(output / "input-evidence-manifest.json")

    assert result["valid"] is True
    assert manifest["evidence_kind"] == "macro_data_association"
    assert manifest["shock_id"] is None
    assert manifest["data_profile"] == "canonical_long_table"
    assert not (output / "shock-identification-artifact.json").exists()
    assert set(cast(dict[str, str], manifest["file_checksums"])) == {
        "data.csv",
        "macro-data-handoff.json",
        "source-manifest.json",
    }


def test_materialized_association_validates(tmp_path: Path) -> None:
    from time_series_dynamics.input_evidence import (
        validate_input_evidence,
    )
    from time_series_dynamics.macro_input_evidence import (
        materialize_macro_input_evidence,
    )

    output = tmp_path / "evidence"
    materialize_macro_input_evidence(
        _macro_bundle(tmp_path),
        _request_document(),
        output,
    )

    assert validate_input_evidence(output) == {
        "valid": True,
        "errors": [],
    }


def test_rejects_comparison_only_macro_bundle(tmp_path: Path) -> None:
    from time_series_dynamics.macro_input_evidence import (
        materialize_macro_input_evidence,
    )

    with pytest.raises(
        ValueError,
        match="macro_bundle_not_analysis_ready",
    ):
        materialize_macro_input_evidence(
            _macro_bundle(
                tmp_path,
                delivery_eligibility="comparison_only",
            ),
            _request_document(),
            tmp_path / "evidence",
        )


def test_rejects_data_csv_tamper(tmp_path: Path) -> None:
    from time_series_dynamics.input_evidence import (
        validate_input_evidence,
    )
    from time_series_dynamics.macro_input_evidence import (
        materialize_macro_input_evidence,
    )

    output = tmp_path / "evidence"
    materialize_macro_input_evidence(
        _macro_bundle(tmp_path),
        _request_document(),
        output,
    )
    with (output / "data.csv").open("a", encoding="utf-8") as handle:
        handle.write("tamper\n")

    result = validate_input_evidence(output)

    assert result["valid"] is False
    assert "checksum_mismatch:data.csv" in result["errors"]


def test_handoff_binds_declared_series_and_authorization(
    tmp_path: Path,
) -> None:
    from time_series_dynamics.macro_input_evidence import (
        materialize_macro_input_evidence,
    )

    output = tmp_path / "evidence"
    materialize_macro_input_evidence(
        _macro_bundle(tmp_path),
        _request_document(),
        output,
    )
    handoff = _load(output / "macro-data-handoff.json")

    assert handoff["evidence_kind"] == "macro_data_association"
    assert handoff["data_profile"] == "canonical_long_table"
    assert handoff["product_authorization_ref"] == "product-auth-" + "a" * 32
    assert handoff["variables"] == [
        "cpi_log",
        "policy_change",
        "cpi_growth",
        "gdp_growth",
    ]


def test_repeated_materialization_replaces_previous_output(
    tmp_path: Path,
) -> None:
    from time_series_dynamics.macro_input_evidence import (
        materialize_macro_input_evidence,
    )

    bundle = _macro_bundle(tmp_path)
    output = tmp_path / "evidence"
    first = materialize_macro_input_evidence(
        bundle,
        _request_document(),
        output,
    )
    second = materialize_macro_input_evidence(
        bundle,
        _request_document(),
        output,
    )

    assert first["evidence_id"] == second["evidence_id"]


@pytest.mark.parametrize(
    ("mutation", "issue"),
    [
        ("frequency", "macro_frequency_not_quarterly"),
        ("checksum", "macro_data_checksum_mismatch"),
        ("binding_missing", "macro_series_binding_missing:gdp_growth"),
        ("authorization_missing", "series_authorization_missing:cpi_log"),
        ("authorization_denied", "series_authorization_denied:cpi_log"),
        ("provider", "macro_provider_not_datapro"),
        ("dataset", "cross_source_stitching_forbidden"),
    ],
)
def test_rejects_invalid_macro_bundle_semantics(
    tmp_path: Path,
    mutation: str,
    issue: str,
) -> None:
    from time_series_dynamics.macro_input_evidence import (
        materialize_macro_input_evidence,
    )

    bundle = _macro_bundle(tmp_path)
    _mutate_result(bundle, mutation)

    with pytest.raises(ValueError, match=issue):
        materialize_macro_input_evidence(
            bundle,
            _request_document(),
            tmp_path / "evidence",
        )


def test_rejects_non_association_request(tmp_path: Path) -> None:
    from time_series_dynamics.macro_input_evidence import (
        materialize_macro_input_evidence,
    )

    request = _load(FIXTURES / "jel.causal.request.json")

    with pytest.raises(ValueError, match="macro_association_track_required"):
        materialize_macro_input_evidence(
            _macro_bundle(tmp_path),
            request,
            tmp_path / "evidence",
        )


def test_rejects_noncanonical_association_request(tmp_path: Path) -> None:
    from time_series_dynamics.macro_input_evidence import (
        materialize_macro_input_evidence,
    )

    request = _load(FIXTURES / "jel.association.request.json")

    with pytest.raises(ValueError, match="canonical_data_profile_required"):
        materialize_macro_input_evidence(
            _macro_bundle(tmp_path),
            request,
            tmp_path / "evidence",
        )


def test_validator_rejects_missing_and_unexpected_files(
    tmp_path: Path,
) -> None:
    from time_series_dynamics.macro_input_evidence import (
        materialize_macro_input_evidence,
        validate_macro_input_evidence,
    )

    output = tmp_path / "evidence"
    materialize_macro_input_evidence(
        _macro_bundle(tmp_path),
        _request_document(),
        output,
    )
    (output / "source-manifest.json").unlink()
    (output / "unexpected.txt").write_text("unexpected", encoding="utf-8")

    result = validate_macro_input_evidence(output)

    assert "artifact_missing:source-manifest.json" in result["errors"]
    assert "artifact_unexpected:unexpected.txt" in result["errors"]


def test_validator_rejects_symlink(tmp_path: Path) -> None:
    from time_series_dynamics.macro_input_evidence import (
        materialize_macro_input_evidence,
        validate_macro_input_evidence,
    )

    output = tmp_path / "evidence"
    materialize_macro_input_evidence(
        _macro_bundle(tmp_path),
        _request_document(),
        output,
    )
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    target = output / "source-manifest.json"
    target.unlink()
    target.symlink_to(outside)

    result = validate_macro_input_evidence(output)

    assert result["errors"] == ["symlink_forbidden:source-manifest.json"]


def test_validator_rejects_contract_violation(tmp_path: Path) -> None:
    from time_series_dynamics.macro_input_evidence import (
        materialize_macro_input_evidence,
        validate_macro_input_evidence,
    )

    output = tmp_path / "evidence"
    materialize_macro_input_evidence(
        _macro_bundle(tmp_path),
        _request_document(),
        output,
    )
    manifest = _load(output / "input-evidence-manifest.json")
    manifest["schema_version"] = "9.9.9"
    _write(output / "input-evidence-manifest.json", manifest)

    assert validate_macro_input_evidence(output) == {
        "valid": False,
        "errors": ["contract_violation"],
    }


@pytest.mark.parametrize(
    ("artifact", "field", "value", "issue"),
    [
        (
            "macro-data-handoff.json",
            "source_checksum",
            "f" * 64,
            "source_checksum_mismatch",
        ),
        (
            "source-manifest.json",
            "data_sha256",
            "f" * 64,
            "source_manifest_checksum_mismatch",
        ),
        (
            "source-manifest.json",
            "source_version",
            "run-" + "f" * 32,
            "source_version_mismatch",
        ),
        (
            "source-manifest.json",
            "license_or_authorization",
            "product-auth-" + "f" * 32,
            "product_authorization_mismatch",
        ),
    ],
)
def test_validator_rejects_resigned_binding_drift(
    tmp_path: Path,
    artifact: str,
    field: str,
    value: str,
    issue: str,
) -> None:
    from time_series_dynamics.macro_input_evidence import (
        materialize_macro_input_evidence,
        validate_macro_input_evidence,
    )

    output = tmp_path / "evidence"
    materialize_macro_input_evidence(
        _macro_bundle(tmp_path),
        _request_document(),
        output,
    )
    path = output / artifact
    document = _load(path)
    document[field] = value
    _write(path, document)
    _resign_file(output, artifact)

    result = validate_macro_input_evidence(output)

    assert issue in result["errors"]
