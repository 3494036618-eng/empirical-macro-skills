import pytest
from conftest import FIXTURES, load_json, load_module

ANNUAL_WDI_REQUEST = (
    "获取中国 2019—2024 年年度 CPI，严格使用 World Bank WDI 口径，并生成可审计科研数据包。"
)


def test_parser_builds_a_machine_readable_series_request_for_the_neutral_case():
    parser = load_module("macro_data.request_parser")

    request = parser.parse_research_request(ANNUAL_WDI_REQUEST)

    assert request["research_question"] == ANNUAL_WDI_REQUEST
    assert request["entities"] == [
        {
            "name_or_code": "CHN",
            "entity_type": "country",
            "code_scheme": "ISO-3166-1-alpha-3",
        }
    ]
    assert request["time_range"] == {"start": "2019", "end": "2024"}
    assert request["frequency"] == "A"
    assert request["native_source_constraints"] == [
        {
            "source_system": "WORLD_BANK",
            "dataset_name": "World Development Indicators",
            "indicator_code": "FP.CPI.TOTL",
        }
    ]
    assert request["fallback_policy"]["allow_semantic_substitute"] is False
    assert request["fallback_policy"]["allow_cross_source_stitching"] is False
    assert request["transformation_policy"]["allow_upsampling"] is False
    assert request["transformation_policy"]["allow_imputation"] is False


def test_parser_preserves_monthly_frequency_instead_of_downgrading_to_annual():
    parser = load_module("macro_data.request_parser")

    request = parser.parse_research_request(
        "查询中国 2019-01 至 2024-12 的月度居民消费价格指数 CPI。"
    )

    assert request["frequency"] == "M"
    assert request["time_range"] == {"start": "2019-01", "end": "2024-12"}


def test_parser_enforces_structured_world_bank_source_constraints():
    parser = load_module("macro_data.request_parser")

    request = parser.parse_research_request(
        "精确查找中国 2019—2024 年年度 CPI："
        "source_system=WORLD_BANK；"
        "dataset_name=World Development Indicators；"
        "indicator_code=FP.CPI.TOTL。"
    )

    assert request["native_source_constraints"] == [
        {
            "source_system": "WORLD_BANK",
            "dataset_name": "World Development Indicators",
            "indicator_code": "FP.CPI.TOTL",
        }
    ]


@pytest.mark.parametrize(
    "text, expected_range, expected_frequency",
    [
        pytest.param(
            "比较中国从2019年到2024年的年度居民消费价格变化。",
            {"start": "2019", "end": "2024"},
            "A",
            id="normal_chinese_years",
        ),
        pytest.param(
            "整理中国2019年1月至2020年12月的每月CPI。",
            {"start": "2019-01", "end": "2020-12"},
            "M",
            id="normal_chinese_months",
        ),
        pytest.param(
            "获取中国2019年第一季度至2020年第四季度的季度GDP。",
            {"start": "2019-Q1", "end": "2020-Q4"},
            "Q",
            id="normal_chinese_quarters",
        ),
    ],
)
def test_candidate_parser_understands_normal_chinese_time_expressions(
    text,
    expected_range,
    expected_frequency,
):
    parser = load_module("macro_data.request_parser")

    request = parser.build_candidate_request(text)

    assert request["time_range"] == expected_range
    assert request["frequency"] == expected_frequency


def test_candidate_parser_extracts_multiple_countries_indicators_and_source():
    parser = load_module("macro_data.request_parser")

    request = parser.build_candidate_request(
        "比较中国、美国和日本从2019年到2024年的年度CPI与实际GDP，"
        "数据使用世界银行WDI，形成跨国面板。"
    )

    assert [item["name_or_code"] for item in request["entities"]] == [
        "CHN",
        "USA",
        "JPN",
    ]
    assert [item["name_or_code"] for item in request["indicators"]] == [
        "FP.CPI.TOTL",
        "NY.GDP.MKTP.KD",
    ]
    assert request["research_use"] == "panel_analysis"
    assert len(request["native_source_constraints"]) == 2


def test_parser_fails_closed_when_entity_or_time_range_is_missing():
    parser = load_module("macro_data.request_parser")

    with pytest.raises(ValueError, match="entity"):
        parser.parse_research_request("查询 2019—2024 年年度 CPI")

    with pytest.raises(ValueError, match="time range"):
        parser.parse_research_request("查询中国年度 CPI")


def test_parser_does_not_map_hong_kong_to_mainland_china_by_substring():
    parser = load_module("macro_data.request_parser")

    request = parser.parse_research_request("查询中国香港 2019—2024 年年度 CPI。")

    assert request["entities"] == [
        {
            "name_or_code": "HKG",
            "entity_type": "territory",
            "code_scheme": "ISO-3166-1-alpha-3",
        }
    ]


def test_response_parser_keeps_only_source_fields_and_never_derives_unit_from_names():
    response_parser = load_module("macro_data.result_parser")
    fixture = load_json(FIXTURES / "sanitized-live" / "02_china_monthly_cpi.json")

    parsed = response_parser.parse_datapro_response(fixture)

    assert parsed["execution"]["provider_code"] == 0
    assert len(parsed["candidates"]) == 6
    first = parsed["candidates"][0]
    assert first["indicator_code"] == "FP.CPI.TOTL"
    assert first["time_grain"] == "year"
    assert first["unit"]["value"] is None
    assert first["unit"]["status"] == "unknown"
    assert first["name_evidence"]["unit_hint"] == "2010 = 100"
    assert first["seasonal_adjustment"]["status"] == "unknown"
    assert first["definition"]["status"] == "unknown"
    assert first["vintage"]["status"] == "unresolved"
    assert first["p_date"]["semantics"] == "unresolved"


def test_response_parser_preserves_explicit_p_date_semantics():
    response_parser = load_module("macro_data.result_parser")
    fixture = load_json(FIXTURES / "sanitized-live" / "02_china_monthly_cpi.json")
    for item in fixture["response"]["items"]:
        item["p_date_semantics"] = "source_last_updated"

    parsed = response_parser.parse_datapro_response(fixture)

    assert parsed["candidates"][0]["p_date"]["semantics"] == ("source_last_updated")
