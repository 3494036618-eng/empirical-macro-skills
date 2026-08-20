from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

from macro_data.connectors.base import ConnectorRequest, ConnectorResponse
from macro_data.connectors.world_bank import WorldBankConnector
from macro_data.multi_source_pipeline import run_datapro_first_completion

ROOT = Path(__file__).resolve().parents[1]
REQUEST_FIXTURE = ROOT / "fixtures" / "completion" / "request.valid.json"


class DataProFixtureConnector:
    code = "datapro"

    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self._candidates = candidates

    def retrieve(self, request: ConnectorRequest) -> ConnectorResponse:
        return ConnectorResponse(
            provider=self.code,
            request_id=request.request_id,
            raw={"code": 0, "items": []},
            retrieved_at="2026-08-19T00:00:00Z",
        )

    def parse_response(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": "datapro",
            "execution": {"provider_code": 0, "message": "success"},
            "candidates": copy.deepcopy(self._candidates),
            "raw_response": raw,
            "fixture_provenance": {},
        }


class WorldBankTransport:
    def __init__(self, periods: tuple[str, ...]) -> None:
        self.periods = periods
        self.urls: list[str] = []

    def __call__(self, url: str) -> Any:
        self.urls.append(url)
        parsed = urlparse(url)
        if "/country/" in parsed.path:
            return [
                {
                    "page": 1,
                    "pages": 1,
                    "per_page": 1000,
                    "total": len(self.periods),
                    "sourceid": "2",
                    "lastupdated": "2026-08-18",
                },
                [_observation(period) for period in self.periods],
            ]
        if "/indicator/" in parsed.path:
            return [
                {"page": 1, "pages": 1, "per_page": 50, "total": 1},
                [
                    {
                        "id": "FP.CPI.TOTL",
                        "name": "Consumer price index (2010 = 100)",
                        "source": {"id": "2"},
                        "sourceNote": "Consumer price index",
                        "sourceOrganization": "World Bank",
                    }
                ],
            ]
        return [
            {"page": 1, "pages": 1, "per_page": 50, "total": 1},
            [
                {
                    "id": "2",
                    "name": "World Development Indicators",
                    "code": "WDI",
                    "lastupdated": "2026-08-18",
                }
            ],
        ]


def _request() -> dict[str, Any]:
    document = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    return cast(dict[str, Any], document)


def _observation(period: str) -> dict[str, Any]:
    return {
        "indicator": {
            "id": "FP.CPI.TOTL",
            "value": "Consumer price index (2010 = 100)",
        },
        "country": {"id": "CN", "value": "China"},
        "countryiso3code": "CHN",
        "date": period,
        "value": 100.0 + int(period) - 2019,
        "unit": "",
        "obs_status": "",
        "decimal": 1,
    }


def _datapro_candidate(
    period: str,
    *,
    source_system: str = "WORLD_BANK",
    dataset_name: str = "World Development Indicators",
) -> dict[str, Any]:
    return {
        "provider": "datapro",
        "series_key": (
            f"{source_system}|{dataset_name}|CHN|FP.CPI.TOTL"
        ),
        "source_system": source_system,
        "dataset_id": "2",
        "dataset_name": dataset_name,
        "entity_code": "CHN",
        "entity_name": "China",
        "indicator_code": "FP.CPI.TOTL",
        "indicator_name": "Consumer price index (2010 = 100)",
        "time_raw": period,
        "time_grain": "year",
        "observed_frequency": "A",
        "value": 100.0 + int(period) - 2019,
        "unit": {
            "value": "index, 2010=100",
            "status": "source_documented",
        },
        "seasonal_adjustment": {"value": None, "status": "not_applicable"},
        "price_basis": {
            "value": {
                "type": "index",
                "base_period": "2010=100",
                "chain_linked": None,
            },
            "status": "source_documented",
        },
        "definition": {
            "value": "Consumer price index",
            "status": "source_provided",
        },
        "release_date": {"value": None, "status": "unresolved"},
        "vintage": {"value": None, "status": "unresolved"},
        "p_date": {
            "value": "2026-08-18",
            "semantics": "source_last_updated",
        },
        "license": {
            "id": "CC-BY-4.0",
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "attribution": "World Bank",
            "use_status": "allowed",
            "allows_requested_use": True,
        },
    }


def test_world_bank_connector_fetches_only_one_contiguous_gap_window() -> None:
    request = _request()
    request["time_range"] = {"start": "2020", "end": "2020"}
    transport = WorldBankTransport(("2020",))
    connector = WorldBankConnector(transport=transport)

    connector.retrieve(
        ConnectorRequest(
            request_id="gap-2020",
            query=request["research_question"],
            research_request=request,
        )
    )

    observation_url = next(url for url in transport.urls if "/country/" in url)
    assert parse_qs(urlparse(observation_url).query)["date"] == ["2020:2020"]


def test_datapro_partial_and_wdi_fill_only_the_missing_cell(
    tmp_path: Path,
) -> None:
    transport = WorldBankTransport(("2020",))

    result = run_datapro_first_completion(
        request=_request(),
        datapro_connector=DataProFixtureConnector(
            [_datapro_candidate("2019"), _datapro_candidate("2021")]
        ),
        official_connectors={
            "world_bank": WorldBankConnector(transport=transport)
        },
        output_dir=tmp_path / "bundle",
        input_mode="mock",
    )

    observations = {
        item.key.period: item
        for item in result["completion"].observations
    }
    assert observations["2019"].retrieval_provider == "datapro"
    assert observations["2020"].retrieval_provider == "world_bank"
    assert observations["2021"].retrieval_provider == "datapro"
    assert result["provider_contribution"] == {
        "classification": "datapro_assisted",
        "datapro_count": 2,
        "official_fallback_count": 1,
        "unresolved_count": 0,
        "datapro_ratio": 2 / 3,
        "official_fallback_ratio": 1 / 3,
    }
    observation_url = next(url for url in transport.urls if "/country/" in url)
    assert parse_qs(urlparse(observation_url).query)["date"] == ["2020:2020"]


def test_official_full_response_cannot_replace_datapro_cells(
    tmp_path: Path,
) -> None:
    transport = WorldBankTransport(("2019", "2020", "2021"))

    result = run_datapro_first_completion(
        request=_request(),
        datapro_connector=DataProFixtureConnector(
            [_datapro_candidate("2019"), _datapro_candidate("2021")]
        ),
        official_connectors={
            "world_bank": WorldBankConnector(transport=transport)
        },
        output_dir=tmp_path / "bundle",
        input_mode="mock",
    )

    observations = {
        item.key.period: item.retrieval_provider
        for item in result["completion"].observations
    }
    assert observations == {
        "2019": "datapro",
        "2020": "world_bank",
        "2021": "datapro",
    }
    assert result["completion"].conflict_count == 0


def test_world_bank_cannot_complete_an_imf_native_series(
    tmp_path: Path,
) -> None:
    request = _request()
    request["native_source_constraints"] = [
        {
            "source_system": "IMF",
            "dataset_name": "IMF CPI",
            "indicator_code": "FP.CPI.TOTL",
        }
    ]
    transport = WorldBankTransport(("2020",))

    result = run_datapro_first_completion(
        request=request,
        datapro_connector=DataProFixtureConnector(
            [
                _datapro_candidate(
                    "2019",
                    source_system="IMF",
                    dataset_name="IMF CPI",
                ),
                _datapro_candidate(
                    "2021",
                    source_system="IMF",
                    dataset_name="IMF CPI",
                ),
            ]
        ),
        official_connectors={
            "world_bank": WorldBankConnector(transport=transport)
        },
        output_dir=tmp_path / "bundle",
        input_mode="mock",
    )

    assert "cross_source_mapping_rejected" in result["issue_codes"]
    assert result["delivery_eligibility"] != "analysis_ready"
