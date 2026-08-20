from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from macro_data.exporter import validate_bundle


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _request() -> dict[str, Any]:
    definition = "Quarterly CPI log price level from a fixed public archive"
    return {
        "schema_version": "0.2.0-beta",
        "research_question": "研究美国货币政策冲击后的季度通胀动态。",
        "research_use": "dynamic_response",
        "concepts": [
            {
                "concept": "美国 CPI 对数价格水平",
                "role": "outcome",
                "definition_constraints": [definition],
            }
        ],
        "indicators": [
            {
                "name_or_code": "lcpi",
                "required_definition": definition,
            }
        ],
        "entities": [
            {
                "name_or_code": "USA",
                "entity_type": "country",
                "code_scheme": "ISO-3166-1-alpha-3",
            }
        ],
        "time_range": {"start": "2000-Q1", "end": "2000-Q2"},
        "frequency": "Q",
        "unit": None,
        "seasonal_adjustment": "source_native",
        "price_basis": {
            "type": "source_native",
            "base_period": None,
            "chain_linked": None,
        },
        "currency": None,
        "release_or_vintage": {"mode": "latest", "value": None},
        "preferred_sources": ["datapro", "public_research_archive"],
        "native_source_constraints": [
            {
                "source_system": "JEL_REPLICATION_ARCHIVE",
                "dataset_name": "Example 5",
                "indicator_code": "lcpi",
            }
        ],
        "fallback_policy": {
            "mode": "allow_public_research_archive",
            "allowed_sources": ["public_research_archive"],
            "allow_semantic_substitute": False,
            "allow_cross_source_stitching": False,
        },
        "transformation_policy": {
            "allow_unit_scaling": False,
            "allow_currency_conversion": False,
            "allow_downsampling": False,
            "allow_upsampling": False,
            "allow_imputation": False,
            "allow_self_seasonal_adjustment": False,
            "allow_rebasing": False,
            "requested_transformations": [],
        },
        "output_format": ["csv", "parquet", "json"],
    }


def _write_import(tmp_path: Path) -> Path:
    raw = tmp_path / "source.dta"
    raw.write_bytes(b"fixed-public-source")
    data = tmp_path / "canonical.csv"
    with data.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("period", "lcpi"))
        writer.writeheader()
        writer.writerows(
            (
                {"period": "2000Q1", "lcpi": "100.0"},
                {"period": "2000Q2", "lcpi": "100.5"},
            )
        )
    document = {
        "schema_version": "0.2.0-beta",
        "provider": "public_research_archive",
        "retrieved_at": "2026-08-19T00:00:00Z",
        "source": {
            "source_system": "JEL_REPLICATION_ARCHIVE",
            "dataset_id": "E208590V1",
            "dataset_name": "Example 5",
            "title": "Data and code for Local Projections, Example 5",
            "url": "https://doi.org/10.3886/E208590V1",
            "version": "commit-0123456789abcdef",
            "source_last_updated": "2025-03-01",
            "license": {
                "id": "CC0-1.0",
                "url": "https://creativecommons.org/publicdomain/zero/1.0/",
                "attribution": "Jorda and Taylor, Local Projections",
                "use_status": "allowed",
                "allows_requested_use": True,
            },
        },
        "raw_artifact": {"path": raw.name, "sha256": _sha256(raw)},
        "data_artifact": {
            "path": data.name,
            "sha256": _sha256(data),
            "format": "csv",
            "period_column": "period",
        },
        "entity": {"code": "USA", "name": "United States"},
        "frequency": "Q",
        "series": [
            {
                "column": "lcpi",
                "series_key": "JEL|E208590V1|USA|lcpi|Q",
                "indicator_code": "lcpi",
                "indicator_name": "U.S. CPI log price level",
                "definition": (
                    "Quarterly CPI log price level from a fixed public archive"
                ),
                "unit": "log points x 100",
                "seasonal_adjustment": "source_native",
                "price_basis": None,
            }
        ],
    }
    manifest = tmp_path / "public-artifact.json"
    manifest.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def test_public_artifact_import_exports_standard_macro_bundle(
    tmp_path: Path,
) -> None:
    """Break caught: pinned public data bypasses the macro-data contract."""
    from macro_data.public_artifact_import import import_public_artifact_bundle

    output = tmp_path / "bundle"
    result = import_public_artifact_bundle(
        request=_request(),
        manifest_path=_write_import(tmp_path),
        output_dir=output,
    )

    assert result["delivery_eligibility"] == "analysis_ready"
    assert validate_bundle(output)["valid"] is True
    result_document = json.loads(
        (output / "result.json").read_text(encoding="utf-8")
    )
    assert result_document["series"][0]["source"]["provider"] == (
        "public_research_archive"
    )


def test_public_artifact_import_rejects_tampered_source(
    tmp_path: Path,
) -> None:
    """Break caught: imported values are no longer bound to the raw source."""
    from macro_data.public_artifact_import import import_public_artifact_bundle

    manifest = _write_import(tmp_path)
    (tmp_path / "source.dta").write_bytes(b"tampered")
    output = tmp_path / "bundle"

    with pytest.raises(ValueError, match="raw artifact checksum mismatch"):
        import_public_artifact_bundle(
            request=_request(),
            manifest_path=manifest,
            output_dir=output,
        )
    assert not output.exists()


def test_public_artifact_import_rejects_incomplete_time_axis(
    tmp_path: Path,
) -> None:
    """Break caught: a shortened archive is mislabeled analysis-ready."""
    from macro_data.public_artifact_import import import_public_artifact_bundle

    manifest = _write_import(tmp_path)
    data = tmp_path / "canonical.csv"
    rows = data.read_text(encoding="utf-8").splitlines()
    data.write_text("\n".join(rows[:2]) + "\n", encoding="utf-8")
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["data_artifact"]["sha256"] = _sha256(data)
    manifest.write_text(json.dumps(document), encoding="utf-8")
    output = tmp_path / "bundle"

    result = import_public_artifact_bundle(
        request=_request(),
        manifest_path=manifest,
        output_dir=output,
    )

    assert result["delivery_eligibility"] == "not_deliverable"
    assert result["eligible_for_estimation"] is False


def test_public_artifact_import_requires_redistribution_rights(
    tmp_path: Path,
) -> None:
    """Break caught: a public URL is treated as permission to redistribute."""
    from macro_data.public_artifact_import import import_public_artifact_bundle

    manifest = _write_import(tmp_path)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["source"]["license"]["allows_requested_use"] = False
    manifest.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="source license does not allow requested use"):
        import_public_artifact_bundle(
            request=_request(),
            manifest_path=manifest,
            output_dir=tmp_path / "bundle",
        )


def test_public_artifact_import_cli_publishes_valid_bundle(
    tmp_path: Path,
) -> None:
    """Break caught: the public import exists only as a private Python API."""
    root = Path(__file__).resolve().parents[1]
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request()), encoding="utf-8")
    output = tmp_path / "bundle"

    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "import_public_research_artifact.py"),
            "--request-json",
            str(request_path),
            "--artifact-json",
            str(_write_import(tmp_path)),
            "--output",
            str(output),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["delivery_eligibility"] == "analysis_ready"
    assert validate_bundle(output)["valid"] is True


def test_public_artifact_import_rejects_non_object_manifest(
    tmp_path: Path,
) -> None:
    """Break caught: an array manifest reaches field access and crashes."""
    from macro_data.public_artifact_import import import_public_artifact_bundle

    manifest = tmp_path / "manifest.json"
    manifest.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest must be an object"):
        import_public_artifact_bundle(
            request=_request(),
            manifest_path=manifest,
            output_dir=tmp_path / "bundle",
        )


def test_public_artifact_import_rejects_linked_artifact(
    tmp_path: Path,
) -> None:
    """Break caught: the import dereferences a file outside the evidence root."""
    from macro_data.public_artifact_import import import_public_artifact_bundle

    manifest = _write_import(tmp_path)
    raw = tmp_path / "source.dta"
    raw.unlink()
    raw.symlink_to(tmp_path / "canonical.csv")
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["raw_artifact"]["sha256"] = _sha256(tmp_path / "canonical.csv")
    manifest.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="missing or linked"):
        import_public_artifact_bundle(
            request=_request(),
            manifest_path=manifest,
            output_dir=tmp_path / "bundle",
        )


def test_public_artifact_import_rejects_missing_or_invalid_values(
    tmp_path: Path,
) -> None:
    """Break caught: missing columns and invalid numbers reach estimation."""
    from macro_data.public_artifact_import import import_public_artifact_bundle

    manifest = _write_import(tmp_path)
    data = tmp_path / "canonical.csv"
    data.write_text("period,other\n2000Q1,1\n", encoding="utf-8")
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["data_artifact"]["sha256"] = _sha256(data)
    manifest.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="columns are missing"):
        import_public_artifact_bundle(
            request=_request(),
            manifest_path=manifest,
            output_dir=tmp_path / "missing",
        )

    for value, message in (("bad", "non-numeric"), ("nan", "non-finite")):
        data.write_text(f"period,lcpi\n2000Q1,{value}\n", encoding="utf-8")
        document["data_artifact"]["sha256"] = _sha256(data)
        manifest.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            import_public_artifact_bundle(
                request=_request(),
                manifest_path=manifest,
                output_dir=tmp_path / value,
            )


def test_public_artifact_import_replaces_previous_bundle_transactionally(
    tmp_path: Path,
) -> None:
    """Break caught: a repeated import leaves stale files in the output."""
    from macro_data.public_artifact_import import import_public_artifact_bundle

    output = tmp_path / "bundle"
    manifest = _write_import(tmp_path)
    import_public_artifact_bundle(
        request=_request(),
        manifest_path=manifest,
        output_dir=output,
    )
    (output / "stale.txt").write_text("remove", encoding="utf-8")

    import_public_artifact_bundle(
        request=_request(),
        manifest_path=manifest,
        output_dir=output,
    )

    assert not (output / "stale.txt").exists()
    assert validate_bundle(output)["valid"] is True


def test_public_artifact_import_blocks_complete_but_undocumented_series(
    tmp_path: Path,
) -> None:
    """Break caught: complete coverage hides unresolved research metadata."""
    from macro_data.public_artifact_import import import_public_artifact_bundle

    manifest = _write_import(tmp_path)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["series"][0]["unit"] = None
    manifest.write_text(json.dumps(document), encoding="utf-8")

    result = import_public_artifact_bundle(
        request=_request(),
        manifest_path=manifest,
        output_dir=tmp_path / "bundle",
    )

    assert result["execution_status"] == "partial"
    assert result["delivery_eligibility"] == "not_deliverable"
    assert "unit_unknown" in result["issue_codes"]
