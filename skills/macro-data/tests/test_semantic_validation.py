from conftest import FIXTURES, load_json, load_module


def _parse_request(text: str) -> dict:
    return load_module("macro_data.request_parser").parse_research_request(text)


def _parse_fixture(name: str) -> dict:
    parser = load_module("macro_data.result_parser")
    return parser.parse_datapro_response(load_json(FIXTURES / "sanitized-live" / name))


def _evaluate(request: dict, parsed: dict) -> dict:
    validator = load_module("macro_data.semantic_validator")
    return validator.evaluate_candidates(request, parsed)


def test_monthly_request_with_annual_response_is_not_analysis_ready():
    request = _parse_request("查询中国 2019-01 至 2024-12 的月度居民消费价格指数 CPI。")
    parsed = _parse_fixture("02_china_monthly_cpi.json")
    result = _evaluate(request, parsed)

    assert result["execution_status"] == "partial"
    assert result["research_readiness"] == "blocked"
    assert result["delivery_eligibility"] == "not_deliverable"
    assert result["eligible_for_estimation"] is False
    assert "frequency_mismatch" in result["issue_codes"]
    assert "time_range_mismatch" not in result["issue_codes"]
    assert len(result["selected_items"]) == 6
    assert result["selected_items"][0] is parsed["candidates"][0]
    assert {row["observed_frequency"] for row in result["selected_items"]} == {"A"}
    assert all(row["requested_frequency"] == "M" for row in result["selected_items"])


def test_non_requested_hong_kong_candidates_are_filtered_and_audited():
    request = _parse_request("查询中国 2015Q1—2024Q4 的季度实际 GDP。")
    result = _evaluate(
        request,
        _parse_fixture("03_china_quarterly_real_gdp.json"),
    )

    assert {row["entity_code"] for row in result["selected_items"]} <= {"CHN"}
    assert any(
        item["entity_code"] == "HK" and "entity_mismatch" in item["reasons"]
        for item in result["filtered_candidates"]
    )
    assert "entity_candidates_filtered" in result["issue_codes"]
    assert result["eligible_for_estimation"] is False


def test_strict_wdi_request_does_not_accept_imf_or_related_entities():
    request = _parse_request("获取中国 2019—2024 年年度 CPI，严格使用 World Bank WDI 口径。")
    result = _evaluate(
        request,
        _parse_fixture("01_china_annual_cpi_wdi.json"),
    )

    assert result["selected_items"] == []
    assert result["delivery_eligibility"] == "not_deliverable"
    assert "source_mismatch" in result["issue_codes"]
    assert any(item["entity_code"] in {"HKG", "MAC"} for item in result["filtered_candidates"])


def test_multiple_cpi_series_are_reported_as_indicator_ambiguity():
    request = _parse_request("查询中国 2019—2024 年年度 CPI（FP.CPI.TOTL）。")
    parsed = _parse_fixture("02_china_monthly_cpi.json")
    duplicate_identity = dict(parsed["candidates"][0])
    duplicate_identity["series_key"] = "WORLD_BANK|WDI|CHN|FP.CPI.TOTL|ALT"
    duplicate_identity["dataset_id"] = "alternate"
    parsed["candidates"].append(duplicate_identity)
    result = _evaluate(request, parsed)

    assert len({item["series_key"] for item in result["selected_items"]}) > 1
    assert "indicator_ambiguity" in result["issue_codes"]
    assert result["eligible_for_estimation"] is False


def test_missing_semantics_remain_unknown_and_reduce_research_readiness():
    request = _parse_request("获取中国 2019—2024 年年度 CPI，严格使用 World Bank WDI 口径。")
    result = _evaluate(
        request,
        _parse_fixture("02_china_monthly_cpi.json"),
    )

    assert {
        "unit_unknown",
        "seasonal_adjustment_unknown",
        "definition_unknown",
    } <= set(result["issue_codes"])
    assert "vintage_unresolved" not in result["issue_codes"]
    assert result["research_readiness"] == "blocked"
    assert result["eligible_for_estimation"] is False


def test_empty_success_response_is_failed_closed_without_shrinking_request_scope():
    request = _parse_request("查询中国 2019—2024 年年度量子消费景气魔法指数 QCMI-9999。")
    result = _evaluate(
        request,
        _parse_fixture("05_ambiguous_nonexistent_indicator.json"),
    )

    assert result["execution_status"] == "failed"
    assert result["research_readiness"] == "blocked"
    assert result["delivery_eligibility"] == "not_deliverable"
    assert result["source_coverage"]["requested_count"] == 1
    assert result["source_coverage"]["delivered_count"] == 0
    assert result["source_coverage"]["scope_reduced"] is False
    assert "empty_result" in result["issue_codes"]


def test_synthetic_provider_error_is_distinct_from_an_empty_success():
    request = _parse_request("查询中国 2019—2024 年年度量子消费景气魔法指数 QCMI-9999。")
    parser = load_module("macro_data.result_parser")
    parsed = parser.parse_datapro_response(
        load_json(FIXTURES / "synthetic" / "provider_error.json")
    )
    result = _evaluate(request, parsed)

    assert result["execution_status"] == "failed"
    assert result["issue_codes"] == ["provider_error"]
    assert "empty_result" not in result["issue_codes"]


def test_as_of_returns_none_for_latest_request():
    request = load_json(FIXTURES / "synthetic" / "schema-examples" / "request.valid.json")
    request["release_or_vintage"] = {"mode": "latest", "value": None}
    validator = load_module("macro_data.semantic_validator")

    assert validator._as_of(request) is None
