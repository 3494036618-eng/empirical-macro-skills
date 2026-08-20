import importlib
import json
from pathlib import Path

import pytest
from conftest import FIXTURES, load_json


def _request():
    parser = importlib.import_module("macro_data.request_parser")
    return parser.parse_research_request("查询中国 2019—2024 年年度 CPI。")


def test_pipeline_does_not_leave_a_valid_bundle_after_connector_timeout(tmp_path):
    pipeline = importlib.import_module("macro_data.pipeline")

    class TimeoutConnector:
        code = "datapro"

        def retrieve(self, request):
            raise TimeoutError("synthetic timeout")

    output = tmp_path / "timeout"
    with pytest.raises(TimeoutError, match="synthetic timeout"):
        pipeline.run_with_connector(
            request=_request(),
            connector=TimeoutConnector(),
            output_dir=output,
            input_mode="mock",
        )

    assert not output.exists()


def test_pipeline_refuses_malformed_provider_payload_before_export(tmp_path):
    pipeline = importlib.import_module("macro_data.pipeline")
    malformed = {"response": {"code": 0, "dataset_type": "macro", "items": "bad"}}

    with pytest.raises(ValueError, match="items"):
        pipeline.run_macro_data_request(
            request=_request(),
            source_payload=malformed,
            output_dir=tmp_path / "malformed",
            input_mode="synthetic",
        )

    assert not (tmp_path / "malformed").exists()


def test_transactional_publish_restores_the_previous_bundle_on_replace_failure(
    monkeypatch,
    tmp_path,
):
    pipeline = importlib.import_module("macro_data.pipeline")
    output = tmp_path / "existing"
    output.mkdir()
    prior = output / "prior-valid.txt"
    prior.write_text("keep", encoding="utf-8")

    def fake_export_bundle(*, output_dir, **_):
        (output_dir / "new.txt").write_text("new", encoding="utf-8")
        return {"status": "new"}

    original_replace = pipeline.os.replace

    def fail_staging_publish(source, destination):
        source_path = Path(source)
        if source_path.name.startswith(f".{output.name}.staging-"):
            raise OSError("synthetic publish failure")
        return original_replace(source, destination)

    monkeypatch.setattr(pipeline, "export_bundle", fake_export_bundle)
    monkeypatch.setattr(pipeline.os, "replace", fail_staging_publish)

    with pytest.raises(OSError, match="synthetic publish failure"):
        pipeline._export_transactionally(
            request={},
            evaluation={},
            output_dir=output,
            input_mode="mock",
        )

    assert prior.read_text(encoding="utf-8") == "keep"
    assert not list(tmp_path.glob(f".{output.name}.staging-*"))
    assert not list(tmp_path.glob(f".{output.name}.backup-*"))


def test_bundle_validator_detects_result_status_tampering_even_with_new_checksum(
    tmp_path,
):
    pipeline = importlib.import_module("macro_data.pipeline")
    exporter = importlib.import_module("macro_data.exporter")
    provenance = importlib.import_module("macro_data.provenance")
    fixture = load_json(FIXTURES / "sanitized-live" / "02_china_monthly_cpi.json")
    output = tmp_path / "tampered-result"
    pipeline.run_macro_data_request(
        request=_request(),
        source_payload=fixture,
        output_dir=output,
        input_mode="sanitized-live-replay",
    )
    result_path = output / "result.json"
    result = load_json(result_path)
    result["delivery_eligibility"] = "analysis_ready"
    result["eligible_for_estimation"] = True
    result_path.write_text(
        __import__("json").dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_path = output / "run_manifest.json"
    manifest = load_json(manifest_path)
    manifest["artifacts"]["result.json"] = provenance.sha256_file(result_path)
    manifest_path.write_text(
        __import__("json").dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = exporter.validate_bundle(output)
    assert report["valid"] is False
    assert any(finding["artifact"] == "result.json" for finding in report["schema_findings"])


def test_bundle_validator_rejects_run_manifest_status_inconsistent_with_result(
    tmp_path,
):
    pipeline = importlib.import_module("macro_data.pipeline")
    exporter = importlib.import_module("macro_data.exporter")
    fixture = load_json(FIXTURES / "sanitized-live" / "02_china_monthly_cpi.json")
    output = tmp_path / "tampered-manifest"
    pipeline.run_macro_data_request(
        request=_request(),
        source_payload=fixture,
        output_dir=output,
        input_mode="sanitized-live-replay",
    )
    manifest_path = output / "run_manifest.json"
    manifest = load_json(manifest_path)
    manifest["delivery_eligibility"] = "analysis_ready"
    manifest["eligible_for_estimation"] = True
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = exporter.validate_bundle(output)

    assert report["valid"] is False
    assert any(
        finding["artifact"] == "run_manifest.json" for finding in report["consistency_findings"]
    )


def test_bundle_validator_rejects_run_manifest_missing_a_required_field(tmp_path):
    pipeline = importlib.import_module("macro_data.pipeline")
    exporter = importlib.import_module("macro_data.exporter")
    fixture = load_json(FIXTURES / "sanitized-live" / "02_china_monthly_cpi.json")
    output = tmp_path / "incomplete-manifest"
    pipeline.run_macro_data_request(
        request=_request(),
        source_payload=fixture,
        output_dir=output,
        input_mode="sanitized-live-replay",
    )
    manifest_path = output / "run_manifest.json"
    manifest = load_json(manifest_path)
    manifest.pop("macro_data_version")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = exporter.validate_bundle(output)

    assert report["valid"] is False
    assert any(
        finding["artifact"] == "run_manifest.json" and finding["path"] == "<root>"
        for finding in report["schema_findings"]
    )
