import importlib
import json

import pytest
from conftest import FIXTURES, SCHEMAS, load_json
from jsonschema import Draft202012Validator, FormatChecker

MONTHLY_REQUEST = (
    "查询中国 2019-01 至 2024-12 的月度居民消费价格指数 CPI。"
    "必须是月度，不要用年度数据替代；返回指标代码、实体代码、月份、单位和季调状态。"
)


def _run_bundle(tmp_path):
    pipeline = importlib.import_module("macro_data.pipeline")
    fixture = load_json(FIXTURES / "sanitized-live" / "02_china_monthly_cpi.json")
    output = tmp_path / "bundle"
    pipeline.run_macro_data(
        research_question=MONTHLY_REQUEST,
        source_payload=fixture,
        output_dir=output,
        input_mode="sanitized-live-replay",
    )
    return output


def _validate(schema_name: str, instance: dict) -> None:
    schema = load_json(SCHEMAS / schema_name)
    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(instance)


def test_exported_request_provenance_and_result_conform_to_their_schemas(tmp_path):
    output = _run_bundle(tmp_path)

    request = load_json(output / "request_manifest.json")
    provenance = load_json(output / "provenance.json")
    result = load_json(output / "result.json")

    _validate("macro-data-request.schema.json", request)
    _validate("provenance.schema.json", provenance)
    _validate("macro-data-result.schema.json", result)
    assert result["provenance"] == provenance


def test_bundle_validator_rejects_schema_invalid_provenance_even_with_new_checksum(
    tmp_path,
):
    output = _run_bundle(tmp_path)
    provenance_path = output / "provenance.json"
    provenance = load_json(provenance_path)
    provenance.pop("activities")
    provenance_path.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    provenance_module = importlib.import_module("macro_data.provenance")
    manifest_path = output / "run_manifest.json"
    manifest = load_json(manifest_path)
    manifest["artifacts"]["provenance.json"] = provenance_module.sha256_file(provenance_path)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    exporter = importlib.import_module("macro_data.exporter")
    report = exporter.validate_bundle(output)
    assert report["valid"] is False
    assert any(finding["artifact"] == "provenance.json" for finding in report["schema_findings"])


def test_request_manifest_is_immutable_and_checksum_bound(tmp_path):
    output = _run_bundle(tmp_path)
    manifest = load_json(output / "run_manifest.json")

    assert "request_manifest.json" in manifest["artifacts"]
    assert manifest["artifacts"]["request_manifest.json"].startswith("sha256:")


def test_contract_registry_rejects_unknown_schema_versions():
    contracts = importlib.import_module("macro_data.contracts")
    request = load_json(FIXTURES / "synthetic" / "schema-examples" / "request.valid.json")
    contracts.validate_document("request", request)

    request["schema_version"] = "99.0.0"
    with pytest.raises(ValueError, match="unsupported schema_version"):
        contracts.validate_document("request", request)
