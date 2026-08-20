import importlib

import pytest

from macro_data.connectors.base import ConnectorRequest
from macro_data.contracts import validate_document
from macro_data.source_registry import SourceRegistry


def _request(
    *,
    research_use="panel_analysis",
    entities=("CHN",),
    indicators=("FP.CPI.TOTL",),
    start="2019",
    end="2021",
    frequency="A",
):
    return {
        "schema_version": "0.2.0-beta",
        "research_question": "比较中国和美国近三年的居民消费价格变化。",
        "research_use": research_use,
        "concepts": [
            {
                "concept": "居民消费价格",
                "role": "outcome",
                "definition_constraints": [],
            }
        ],
        "indicators": [{"name_or_code": code, "required_definition": None} for code in indicators],
        "entities": [
            {
                "name_or_code": code,
                "entity_type": "country",
                "code_scheme": "ISO-3166-1-alpha-3",
            }
            for code in entities
        ],
        "time_range": {"start": start, "end": end},
        "frequency": frequency,
        "unit": None,
        "seasonal_adjustment": "source_native",
        "price_basis": {
            "type": "source_native",
            "base_period": None,
            "chain_linked": None,
        },
        "currency": None,
        "release_or_vintage": {"mode": "latest", "value": None},
        "preferred_sources": ["datapro", "world_bank"],
        "native_source_constraints": [
            {
                "source_system": "WORLD_BANK",
                "dataset_name": "World Development Indicators",
                "indicator_code": code,
            }
            for code in indicators
        ],
        "fallback_policy": {
            "mode": "allow_official",
            "allowed_sources": ["world_bank"],
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


def _candidate(entity, indicator, period):
    return {
        "provider": "world_bank",
        "series_key": (f"WORLD_BANK|World Development Indicators|{entity}|{indicator}"),
        "source_system": "WORLD_BANK",
        "dataset_id": "2",
        "dataset_name": "World Development Indicators",
        "entity_code": entity,
        "entity_name": entity,
        "indicator_code": indicator,
        "indicator_name": indicator,
        "time_raw": period,
        "time_grain": "year",
        "observed_frequency": "A",
        "value": 100.0,
        "unit": {"value": "index, 2010=100", "status": "source_documented"},
        "seasonal_adjustment": {"value": None, "status": "not_applicable"},
        "price_basis": {"value": None, "status": "not_applicable"},
        "definition": {"value": "Official definition", "status": "source_provided"},
        "release_date": {"value": None, "status": "unresolved"},
        "vintage": {"value": None, "status": "unresolved"},
        "p_date": {
            "value": "2026-07-13",
            "semantics": "source_last_updated",
        },
        "license": {
            "id": "CC-BY-4.0",
            "url": "https://example.test/license",
            "attribution": "World Bank",
            "use_status": "allowed",
            "allows_requested_use": True,
        },
    }


def _parsed(candidates):
    return {
        "provider": "world_bank",
        "execution": {"provider_code": 0, "message": "success"},
        "candidates": candidates,
        "raw_response": {"observations": []},
        "fixture_provenance": {},
    }


def test_request_contract_accepts_explicit_research_use():
    validate_document("request", _request())


def test_request_contract_requires_at_least_one_explicit_indicator():
    request = _request()
    request["indicators"] = []

    with pytest.raises(ValueError, match="indicators"):
        validate_document("request", request)


def test_request_contract_requires_parameters_for_requested_transformation():
    request = _request()
    request["transformation_policy"]["allow_unit_scaling"] = True
    request["transformation_policy"]["requested_transformations"] = ["unit_scale"]

    with pytest.raises(ValueError, match="transformation_parameters"):
        validate_document("request", request)


def test_multi_indicator_panel_tracks_every_entity_indicator_pair():
    validator = importlib.import_module("macro_data.semantic_validator")
    request = _request(
        entities=("CHN", "USA"),
        indicators=("FP.CPI.TOTL", "NY.GDP.MKTP.CD"),
    )
    candidates = [
        _candidate(entity, indicator, str(year))
        for entity in ("CHN", "USA")
        for indicator in ("FP.CPI.TOTL", "NY.GDP.MKTP.CD")
        for year in range(2019, 2022)
    ]

    result = validator.evaluate_candidates(request, _parsed(candidates))

    assert result["source_coverage"]["requested_count"] == 4
    assert result["source_coverage"]["delivered_count"] == 4
    assert result["source_coverage"]["failures"] == []
    assert "indicator_ambiguity" not in result["issue_codes"]


def test_world_bank_connector_supports_multi_country_annual_panel():
    module = importlib.import_module("macro_data.connectors.world_bank")
    request = _request(entities=("CHN", "USA"))
    seen = []

    def transport(url):
        seen.append(url)
        return [
            {
                "page": 1,
                "pages": 1,
                "per_page": 1000,
                "total": 0,
                "sourceid": "2",
            },
            [],
        ]

    module.WorldBankConnector(transport=transport).retrieve(
        ConnectorRequest(
            request_id="panel",
            query=request["research_question"],
            research_request=request,
        )
    )

    assert "/country/CHN%3BUSA/indicator/FP.CPI.TOTL" in seen[0]


def test_router_requires_approval_before_official_source_execution():
    router_module = importlib.import_module("macro_data.source_router")
    request = _request()
    request["fallback_policy"]["mode"] = "ask"
    router = router_module.SourceRouter(SourceRegistry.default())

    with pytest.raises(router_module.SourceApprovalRequired):
        router.authorize(request, "world_bank")


def test_latest_panel_can_be_analysis_ready_without_historical_vintage():
    validator = importlib.import_module("macro_data.semantic_validator")
    request = _request(research_use="panel_analysis")
    candidates = [_candidate("CHN", "FP.CPI.TOTL", str(year)) for year in range(2019, 2022)]

    result = validator.evaluate_candidates(request, _parsed(candidates))

    assert result["research_readiness"] == "ready"
    assert result["delivery_eligibility"] == "analysis_ready"
    assert result["eligible_for_estimation"] is True
    assert "vintage_unresolved" not in result["issue_codes"]
    assert "release_date_unresolved" not in result["issue_codes"]


def test_panel_detects_a_missing_middle_period():
    validator = importlib.import_module("macro_data.semantic_validator")
    request = _request(start="2019", end="2021")
    candidates = [
        _candidate("CHN", "FP.CPI.TOTL", "2019"),
        _candidate("CHN", "FP.CPI.TOTL", "2021"),
    ]

    result = validator.evaluate_candidates(request, _parsed(candidates))

    assert "time_coverage_incomplete" in result["issue_codes"]
    assert result["source_coverage"]["complete"] is False
    assert result["source_coverage"]["failures"] == ["CHN|FP.CPI.TOTL|missing:2020"]
    assert result["delivery_eligibility"] != "analysis_ready"
