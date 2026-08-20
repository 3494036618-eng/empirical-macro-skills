import csv
import json
import tracemalloc

import pyarrow.parquet as pq
from conftest import FIXTURES, load_json, load_module

MONTHLY_CPI_REQUEST = (
    "查询中国 2019-01 至 2024-12 的月度居民消费价格指数 CPI。"
    "必须是月度，不要用年度数据替代；返回指标代码、实体代码、月份、单位和季调状态。"
)
STRICT_WDI_REQUEST = (
    "严格查询 World Bank World Development Indicators（WDI）口径："
    "中国 2019—2024 年年度居民消费价格指数 CPI"
    "（indicator_code=FP.CPI.TOTL）。只返回 CHN，按年返回。"
)

REQUIRED_ARTIFACTS = {
    "data.csv",
    "data.parquet",
    "request_manifest.json",
    "result.json",
    "series_catalog.json",
    "quality_report.json",
    "provenance.json",
    "run_manifest.json",
    "raw_response.json",
}


def _run_bundle(tmp_path, fixture_name="02_china_monthly_cpi.json"):
    pipeline = load_module("macro_data.pipeline")
    fixture = load_json(FIXTURES / "sanitized-live" / fixture_name)
    output = tmp_path / "output"
    result = pipeline.run_macro_data(
        research_question=(
            STRICT_WDI_REQUEST
            if fixture_name == "01_china_annual_cpi_wdi.json"
            else MONTHLY_CPI_REQUEST
        ),
        source_payload=fixture,
        output_dir=output,
        input_mode="sanitized-live-replay",
    )
    return output, result


def test_pipeline_exports_the_required_research_bundle_without_changing_values(tmp_path):
    output, result = _run_bundle(tmp_path)

    assert {path.name for path in output.iterdir()} == REQUIRED_ARTIFACTS
    with (output / "data.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    parquet_rows = pq.read_table(output / "data.parquet").to_pylist()

    assert len(rows) == 6
    assert len(parquet_rows) == 6
    assert {row["entity_code"] for row in rows} == {"CHN"}
    assert {row["indicator_code"] for row in rows} == {"FP.CPI.TOTL"}
    assert [float(row["value"]) for row in rows] == [
        125.083154,
        128.109444,
        129.366217,
        131.919357,
        132.229152,
        132.517582,
    ]
    assert result["research_readiness"] == "blocked"
    assert result["delivery_eligibility"] == "not_deliverable"
    assert result["eligible_for_estimation"] is False
    assert "frequency_mismatch" in result["issue_codes"]


def test_bundle_records_unknown_semantics_and_sanitized_live_provenance(tmp_path):
    output, _ = _run_bundle(tmp_path)

    catalog = json.loads((output / "series_catalog.json").read_text())
    quality = json.loads((output / "quality_report.json").read_text())
    provenance = json.loads((output / "provenance.json").read_text())
    manifest = json.loads((output / "run_manifest.json").read_text())
    raw = json.loads((output / "raw_response.json").read_text())

    assert catalog["series"][0]["unit"]["status"] == "unknown"
    assert catalog["series"][0]["seasonal_adjustment"]["status"] == "unknown"
    assert catalog["series"][0]["definition"]["status"] == "unknown"
    assert catalog["series"][0]["vintage"]["status"] == "unresolved"
    assert quality["eligible_for_estimation"] is False
    assert quality["filtered_candidates"] == []
    assert provenance["input_mode"] == "sanitized-live-replay"
    assert provenance["complete"] is True
    assert manifest["secrets_recorded"] is False
    assert "trace_id" not in raw
    assert "trace_id_sha256" in raw


def test_sanitizer_reuses_clean_branches_and_copies_only_redacted_paths():
    exporter = load_module("macro_data.exporter")
    items = [{"time_raw": "2024", "value": 1.0}]
    clean = {"code": 0, "items": items}

    assert exporter._sanitized(clean) is clean

    payload = {
        "response": clean,
        "metadata": {
            "trace_" + "id": "trace-must-not-be-persisted",
            "Authorization": "redacted-test-value",
        },
    }
    sanitized = exporter._sanitized(payload)

    assert sanitized is not payload
    assert sanitized["response"] is clean
    assert sanitized["response"]["items"] is items
    assert sanitized["metadata"] == {}


def test_bundle_validator_recomputes_checksums_and_detects_tampering(tmp_path):
    output, _ = _run_bundle(tmp_path)
    bundle_validator = load_module("macro_data.exporter")

    valid = bundle_validator.validate_bundle(output)
    assert valid["valid"] is True
    assert valid["checksum_mismatches"] == []

    with (output / "data.csv").open("a", encoding="utf-8") as handle:
        handle.write("tampered\\n")

    invalid = bundle_validator.validate_bundle(output)
    assert invalid["valid"] is False
    assert "data.csv" in invalid["checksum_mismatches"]


def test_bundle_secret_scan_does_not_load_large_artifacts_wholly_into_memory(
    tmp_path,
):
    output, _ = _run_bundle(tmp_path)
    with (output / "data.csv").open("a", encoding="utf-8") as handle:
        handle.write("x" * (8 * 1024 * 1024))

    bundle_validator = load_module("macro_data.exporter")
    tracemalloc.start()
    bundle_validator.validate_bundle(output)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert peak < 6 * 1024 * 1024


def test_bundle_secret_scan_detects_a_token_across_chunk_boundaries(tmp_path):
    exporter = load_module("macro_data.exporter")
    artifact = tmp_path / "artifact.json"
    marker = "Bear" + "er "
    prefix = "x" * (256 * 1024 - len(marker))
    artifact.write_text(
        prefix + marker + "split-token-value",
        encoding="utf-8",
    )

    assert exporter._contains_secret(artifact) is True


def test_strict_source_mismatch_still_generates_an_auditable_blocked_bundle(tmp_path):
    output, result = _run_bundle(tmp_path, "01_china_annual_cpi_wdi.json")

    assert result["delivery_eligibility"] == "not_deliverable"
    assert result["eligible_for_estimation"] is False
    assert "source_mismatch" in result["issue_codes"]
    quality = json.loads((output / "quality_report.json").read_text())
    assert quality["selected_observations"] == 0
    assert quality["filtered_candidates"]
    assert (output / "data.parquet").exists()


def test_sanitized_live_replay_fails_closed_when_request_does_not_match_fixture(tmp_path):
    pipeline = load_module("macro_data.pipeline")
    fixture = load_json(FIXTURES / "sanitized-live" / "02_china_monthly_cpi.json")

    result = pipeline.run_macro_data(
        research_question=STRICT_WDI_REQUEST,
        source_payload=fixture,
        output_dir=tmp_path / "mismatched-replay",
        input_mode="sanitized-live-replay",
    )

    assert "fixture_request_mismatch" in result["issue_codes"]
    assert result["delivery_eligibility"] == "not_deliverable"
    assert result["eligible_for_estimation"] is False
