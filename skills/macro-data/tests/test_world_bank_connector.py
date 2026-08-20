import importlib
import json
from urllib.parse import parse_qs, urlparse

import pytest

from macro_data.connectors.base import ConnectorRequest
from macro_data.request_parser import parse_research_request

QUERY = "严格查询 World Bank WDI 口径：中国 2019—2024 年年度 CPI，indicator_code=FP.CPI.TOTL。"


def _response_for(url: str):
    parsed = urlparse(url)
    if parsed.path.endswith("/country/CHN/indicator/FP.CPI.TOTL"):
        return [
            {
                "page": 1,
                "pages": 1,
                "per_page": 1000,
                "total": 1,
                "sourceid": "2",
                "lastupdated": "2026-07-13",
            },
            [
                {
                    "indicator": {
                        "id": "FP.CPI.TOTL",
                        "value": "Consumer price index (2010 = 100)",
                    },
                    "country": {"id": "CN", "value": "China"},
                    "countryiso3code": "CHN",
                    "date": "2019",
                    "value": 125.083154382075,
                    "unit": "",
                    "obs_status": "",
                    "decimal": 1,
                }
            ],
        ]
    if parsed.path.endswith("/indicator/FP.CPI.TOTL"):
        return [
            {"page": 1, "pages": 1, "per_page": "50", "total": 1},
            [
                {
                    "id": "FP.CPI.TOTL",
                    "name": "Consumer price index (2010 = 100)",
                    "unit": "",
                    "source": {
                        "id": "2",
                        "value": "World Development Indicators",
                    },
                    "sourceNote": "Index with reference period 2010=100.",
                    "sourceOrganization": "International Monetary Fund",
                    "topics": [],
                }
            ],
        ]
    if parsed.path.endswith("/source/2"):
        return [
            {"page": "1", "pages": "1", "per_page": "50", "total": "1"},
            [
                {
                    "id": "2",
                    "lastupdated": "2026-07-13",
                    "name": "World Development Indicators",
                    "code": "WDI",
                    "dataavailability": "Y",
                    "metadataavailability": "Y",
                }
            ],
        ]
    raise AssertionError(f"unexpected URL: {url}")


def test_world_bank_connector_builds_exact_source2_requests_and_preserves_raw():
    module = importlib.import_module("macro_data.connectors.world_bank")
    seen_urls = []

    def transport(url):
        seen_urls.append(url)
        return _response_for(url)

    request = parse_research_request(QUERY)
    connector = module.WorldBankConnector(transport=transport)
    response = connector.retrieve(
        ConnectorRequest(
            request_id="request-world-bank",
            query=QUERY,
            research_request=request,
        )
    )

    observation_url = urlparse(seen_urls[0])
    assert observation_url.path.endswith("/v2/country/CHN/indicator/FP.CPI.TOTL")
    assert parse_qs(observation_url.query) == {
        "date": ["2019:2024"],
        "format": ["json"],
        "source": ["2"],
        "per_page": ["1000"],
        "footnote": ["y"],
    }
    assert len(seen_urls) == 3
    assert response.provider == "world_bank"
    assert response.raw["observations"] == _response_for(seen_urls[0])
    assert response.raw["indicator_metadata"] == _response_for(seen_urls[1])
    assert response.raw["source_metadata"] == _response_for(seen_urls[2])


def test_world_bank_parser_builds_exact_candidates_without_inventing_metadata():
    connector_module = importlib.import_module("macro_data.connectors.world_bank")
    parser_module = importlib.import_module("macro_data.result_parser")
    request = parse_research_request(QUERY)
    response = connector_module.WorldBankConnector(transport=_response_for).retrieve(
        ConnectorRequest(
            request_id="request-world-bank",
            query=QUERY,
            research_request=request,
        )
    )

    parsed = parser_module.parse_world_bank_response(response.raw)

    assert parsed["provider"] == "world_bank"
    assert parsed["execution"]["provider_code"] == 0
    assert len(parsed["candidates"]) == 1
    candidate = parsed["candidates"][0]
    assert candidate["provider"] == "world_bank"
    assert candidate["series_key"] == ("WORLD_BANK|World Development Indicators|CHN|FP.CPI.TOTL")
    assert candidate["entity_code"] == "CHN"
    assert candidate["indicator_code"] == "FP.CPI.TOTL"
    assert candidate["observed_frequency"] == "A"
    assert candidate["time_raw"] == "2019"
    assert candidate["value"] == 125.083154382075
    assert candidate["unit"] == {
        "value": "index, 2010=100",
        "status": "source_documented",
    }
    assert candidate["seasonal_adjustment"] == {
        "value": None,
        "status": "not_applicable",
    }
    assert candidate["definition"] == {
        "value": "Index with reference period 2010=100.",
        "status": "source_provided",
    }
    assert candidate["release_date"]["status"] == "unresolved"
    assert candidate["vintage"]["status"] == "unresolved"
    assert candidate["p_date"] == {
        "value": "2026-07-13",
        "semantics": "source_last_updated",
    }
    assert candidate["license"]["id"] == "CC-BY-4.0"
    assert candidate["license"]["allows_requested_use"] is True


def test_world_bank_parser_does_not_assign_index_basis_to_non_index_indicator():
    parser_module = importlib.import_module("macro_data.result_parser")
    observations = _response_for("https://api.worldbank.org/v2/country/CHN/indicator/FP.CPI.TOTL")
    observations[1][0]["indicator"] = {
        "id": "NY.GDP.MKTP.CD",
        "value": "GDP (current US$)",
    }
    raw = {
        "observations": observations,
        "indicator_metadata": [
            {"page": 1, "pages": 1, "total": 1},
            [
                {
                    "id": "NY.GDP.MKTP.CD",
                    "name": "GDP (current US$)",
                    "unit": "current US$",
                    "source": {
                        "id": "2",
                        "value": "World Development Indicators",
                    },
                    "sourceNote": "GDP at purchaser's prices.",
                    "sourceOrganization": "World Bank national accounts data.",
                }
            ],
        ],
        "source_metadata": _response_for("https://api.worldbank.org/v2/source/2"),
    }

    parsed = parser_module.parse_world_bank_response(raw)

    assert parsed["candidates"][0]["price_basis"] == {
        "value": None,
        "status": "unknown",
    }


def test_world_bank_connector_rejects_region_aggregates():
    module = importlib.import_module("macro_data.connectors.world_bank")
    request = parse_research_request(QUERY)
    request["entities"] = [
        {
            "name_or_code": "WLD",
            "entity_type": "region",
            "code_scheme": "World Bank",
        }
    ]

    with pytest.raises(ValueError, match="country or territory"):
        module.WorldBankConnector(transport=_response_for).retrieve(
            ConnectorRequest(
                request_id="aggregate",
                query=QUERY,
                research_request=request,
            )
        )


def test_world_bank_connector_fetches_all_observation_and_metadata_pages():
    module = importlib.import_module("macro_data.connectors.world_bank")
    indicator_codes = [f"X.TEST.{index:02d}" for index in range(51)]
    request = parse_research_request(QUERY)
    request["time_range"] = {"start": "2019", "end": "2020"}
    request["indicators"] = [
        {"name_or_code": code, "required_definition": None} for code in indicator_codes
    ]
    seen_urls = []

    def transport(url):
        seen_urls.append(url)
        parsed = urlparse(url)
        page = int(parse_qs(parsed.query).get("page", ["1"])[0])
        if "/country/" in parsed.path:
            code = indicator_codes[page - 1]
            return [
                {
                    "page": page,
                    "pages": 2,
                    "per_page": 1,
                    "total": 2,
                    "sourceid": "2",
                    "lastupdated": "2026-07-13",
                },
                [
                    {
                        "indicator": {"id": code, "value": code},
                        "country": {"id": "CN", "value": "China"},
                        "countryiso3code": "CHN",
                        "date": str(2018 + page),
                        "value": float(page),
                    }
                ],
            ]
        if "/indicator/" in parsed.path:
            start = 0 if page == 1 else 50
            end = 50 if page == 1 else 51
            return [
                {
                    "page": page,
                    "pages": 2,
                    "per_page": 50,
                    "total": 51,
                },
                [
                    {
                        "id": code,
                        "name": code,
                        "unit": "index",
                        "source": {
                            "id": "2",
                            "value": "World Development Indicators",
                        },
                        "sourceNote": f"Definition for {code}",
                    }
                    for code in indicator_codes[start:end]
                ],
            ]
        if parsed.path.endswith("/source/2"):
            return _response_for(url)
        raise AssertionError(f"unexpected URL: {url}")

    connector = module.WorldBankConnector(transport=transport)
    raw = connector.retrieve(
        ConnectorRequest(
            request_id="paginated",
            query=QUERY,
            research_request=request,
        )
    ).raw
    parsed = connector.parse_response(raw)

    assert len(parsed["candidates"]) == 2
    assert {item["indicator_code"] for item in parsed["candidates"]} == {
        indicator_codes[0],
        indicator_codes[1],
    }
    assert sum("page=2" in url for url in seen_urls) == 2


def test_world_bank_connector_rejects_more_than_100_pages_before_fetching_more():
    module = importlib.import_module("macro_data.connectors.world_bank")
    calls = []

    def transport(url):
        calls.append(url)
        return [{"page": 1, "pages": 101}, []]

    connector = module.WorldBankConnector(transport=transport)

    with pytest.raises(ValueError, match="page limit"):
        connector._fetch_pages("https://example.test/data?format=json")

    assert len(calls) == 1


def test_pipeline_records_world_bank_provider_and_verified_wdi_license(tmp_path):
    connector_module = importlib.import_module("macro_data.connectors.world_bank")
    pipeline_module = importlib.import_module("macro_data.pipeline")
    request = parse_research_request(QUERY)
    request["preferred_sources"].append("world_bank")
    request["fallback_policy"] = {
        "mode": "allow_official",
        "allowed_sources": ["world_bank"],
        "allow_semantic_substitute": False,
        "allow_cross_source_stitching": False,
    }
    output = tmp_path / "world-bank"

    result = pipeline_module.run_with_connector(
        request=request,
        connector=connector_module.WorldBankConnector(transport=_response_for),
        output_dir=output,
        input_mode="mock",
    )

    manifest = json.loads((output / "run_manifest.json").read_text())
    provenance = json.loads((output / "provenance.json").read_text())
    catalog = json.loads((output / "series_catalog.json").read_text())
    quality = json.loads((output / "quality_report.json").read_text())
    contract = json.loads((output / "result.json").read_text())

    assert result["provider"] == "world_bank"
    assert manifest["connector"] == "world_bank"
    assert provenance["activities"][0]["parameters"]["provider"] == "world_bank"
    assert catalog["series"][0]["provider"] == "world_bank"
    assert contract["series"][0]["source"]["provider"] == "world_bank"
    assert contract["series"][0]["license"] == {
        "id": "CC-BY-4.0",
        "url": (
            "https://datacatalog.worldbank.org/search/dataset/0037712/world-development-indicators"
        ),
        "attribution": "World Bank, World Development Indicators (WDI)",
        "use_status": "allowed",
        "allows_requested_use": True,
    }
    assert "license_unresolved" not in result["issue_codes"]
    assert "definition_unknown" not in result["issue_codes"]
    assert quality["missingness"]["unit_unknown"] == 0
    assert quality["missingness"]["seasonal_adjustment_unknown"] == 0
    assert provenance["activities"][1]["parameters"]["p_date_semantics"] == ("source_last_updated")
