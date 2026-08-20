from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any, cast

from macro_data.connectors.base import ConnectorRequest, ConnectorResponse

ROOT = Path(__file__).resolve().parents[1]
REQUEST_FIXTURE = ROOT / "fixtures" / "completion" / "request.valid.json"


class RecordingConnector:
    def __init__(
        self,
        *,
        code: str,
        calls: list[str],
        parsed: dict[str, Any],
    ) -> None:
        self.code = code
        self.calls = calls
        self.parsed = parsed
        self.requests: list[ConnectorRequest] = []

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def retrieve(self, request: ConnectorRequest) -> ConnectorResponse:
        self.calls.append(self.code)
        self.requests.append(request)
        return ConnectorResponse(
            provider=self.code,
            request_id=request.request_id,
            raw={"parsed": copy.deepcopy(self.parsed)},
            retrieved_at="2026-08-18T00:00:00Z",
        )

    @staticmethod
    def parse_response(raw: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], copy.deepcopy(raw["parsed"]))


def _request() -> dict[str, Any]:
    document = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    return cast(dict[str, Any], document)


def _candidate(
    period: str,
    *,
    provider: str = "datapro",
    value: float = 100.0,
    source_system: str = "WORLD_BANK",
) -> dict[str, Any]:
    return {
        "provider": provider,
        "series_key": (
            f"{source_system}|World Development Indicators|CHN|FP.CPI.TOTL"
        ),
        "source_system": source_system,
        "dataset_id": "2",
        "dataset_name": "World Development Indicators",
        "entity_code": "CHN",
        "entity_name": "China",
        "indicator_code": "FP.CPI.TOTL",
        "indicator_name": "Consumer price index",
        "time_raw": period,
        "time_grain": "year",
        "observed_frequency": "A",
        "value": value,
        "unit": {"value": "index", "status": "source_documented"},
        "seasonal_adjustment": {"value": None, "status": "not_applicable"},
        "price_basis": {
            "value": {
                "type": "index",
                "base_period": None,
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
        "p_date": {"value": "2026-08-18", "semantics": "source_last_updated"},
        "license": {
            "id": "CC-BY-4.0",
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "attribution": "World Bank",
            "use_status": "allowed",
            "allows_requested_use": True,
        },
    }


def _parsed(
    provider: str,
    candidates: list[dict[str, Any]],
    *,
    provider_code: int = 0,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "execution": {
            "provider_code": provider_code,
            "message": "success" if provider_code == 0 else "provider failed",
        },
        "candidates": candidates,
        "raw_response": {"items": []},
        "fixture_provenance": {},
    }


def _datapro(
    calls: list[str],
    periods: tuple[str, ...],
) -> RecordingConnector:
    return RecordingConnector(
        code="datapro",
        calls=calls,
        parsed=_parsed("datapro", [_candidate(period) for period in periods]),
    )


def _official(
    calls: list[str],
    candidates: list[dict[str, Any]],
    *,
    provider_code: int = 0,
) -> RecordingConnector:
    return RecordingConnector(
        code="world_bank",
        calls=calls,
        parsed=_parsed(
            "world_bank",
            candidates,
            provider_code=provider_code,
        ),
    )


def _module() -> Any:
    return importlib.import_module("macro_data.multi_source_pipeline")


def test_datapro_runs_before_any_official_connector(tmp_path: Path) -> None:
    module = _module()
    calls: list[str] = []

    module.run_datapro_first_completion(
        request=_request(),
        datapro_connector=_datapro(calls, ("2019", "2021")),
        official_connectors={
            "world_bank": _official(
                calls,
                [_candidate("2020", provider="world_bank")],
            )
        },
        output_dir=tmp_path / "bundle",
        input_mode="mock",
    )

    assert calls == ["datapro", "world_bank"]


def test_complete_datapro_matrix_never_calls_official(tmp_path: Path) -> None:
    module = _module()
    calls: list[str] = []
    official = _official(calls, [_candidate("2020", provider="world_bank")])

    result = module.run_datapro_first_completion(
        request=_request(),
        datapro_connector=_datapro(calls, ("2019", "2020", "2021")),
        official_connectors={"world_bank": official},
        output_dir=tmp_path / "bundle",
        input_mode="mock",
    )

    assert official.call_count == 0
    assert result["provider_contribution"]["classification"] == "datapro_only"
    assert result["delivery_eligibility"] == "analysis_ready"


def test_official_connector_receives_only_gap_periods(tmp_path: Path) -> None:
    module = _module()
    calls: list[str] = []
    official = _official(calls, [_candidate("2020", provider="world_bank")])

    result = module.run_datapro_first_completion(
        request=_request(),
        datapro_connector=_datapro(calls, ("2019", "2021")),
        official_connectors={"world_bank": official},
        output_dir=tmp_path / "bundle",
        input_mode="mock",
    )

    assert official.requests[0].research_request is not None
    assert official.requests[0].research_request["time_range"] == {
        "start": "2020",
        "end": "2020",
    }
    assert result["provider_contribution"]["classification"] == "datapro_assisted"
    assert result["delivery_eligibility"] == "analysis_ready"


def test_absent_official_connector_keeps_primary_and_blocks_delivery(
    tmp_path: Path,
) -> None:
    module = _module()
    calls: list[str] = []

    result = module.run_datapro_first_completion(
        request=_request(),
        datapro_connector=_datapro(calls, ("2019", "2021")),
        official_connectors={},
        output_dir=tmp_path / "bundle",
        input_mode="mock",
    )

    assert len(result["primary"].locked) == 2
    assert "connector_unavailable" in result["issue_codes"]
    assert result["delivery_eligibility"] != "analysis_ready"


def test_official_provider_error_keeps_primary_and_blocks_delivery(
    tmp_path: Path,
) -> None:
    module = _module()
    calls: list[str] = []

    result = module.run_datapro_first_completion(
        request=_request(),
        datapro_connector=_datapro(calls, ("2019", "2021")),
        official_connectors={
            "world_bank": _official(calls, [], provider_code=500)
        },
        output_dir=tmp_path / "bundle",
        input_mode="mock",
    )

    assert len(result["primary"].locked) == 2
    assert "official_provider_error" in result["issue_codes"]
    assert result["delivery_eligibility"] != "analysis_ready"


def test_cross_source_official_candidate_is_rejected(tmp_path: Path) -> None:
    module = _module()
    calls: list[str] = []

    result = module.run_datapro_first_completion(
        request=_request(),
        datapro_connector=_datapro(calls, ("2019", "2021")),
        official_connectors={
            "world_bank": _official(
                calls,
                [
                    _candidate(
                        "2020",
                        provider="world_bank",
                        source_system="IMF",
                    )
                ],
            )
        },
        output_dir=tmp_path / "bundle",
        input_mode="mock",
    )

    assert "cross_source_mapping_rejected" in result["issue_codes"]
    assert "cross_source_mapping_rejected" in result["completion"].issue_codes
    assert result["delivery_eligibility"] != "analysis_ready"


def test_conflicting_official_overlap_blocks_the_conflicted_cell(
    tmp_path: Path,
) -> None:
    module = _module()
    calls: list[str] = []

    result = module.run_datapro_first_completion(
        request=_request(),
        datapro_connector=_datapro(calls, ("2019",)),
        official_connectors={
            "world_bank": _official(
                calls,
                [
                    _candidate("2019", provider="world_bank", value=999.0),
                    _candidate("2020", provider="world_bank"),
                    _candidate("2021", provider="world_bank"),
                ],
            )
        },
        output_dir=tmp_path / "bundle",
        input_mode="mock",
    )

    assert result["completion"].conflict_count == 1
    assert "overlap_value_conflict" in result["issue_codes"]
    assert result["delivery_eligibility"] != "analysis_ready"


def test_official_metadata_failure_cannot_fill_an_estimator_cell(
    tmp_path: Path,
) -> None:
    module = _module()
    calls: list[str] = []
    candidate = _candidate("2020", provider="world_bank")
    candidate["unit"]["status"] = "unresolved"

    result = module.run_datapro_first_completion(
        request=_request(),
        datapro_connector=_datapro(calls, ("2019", "2021")),
        official_connectors={
            "world_bank": _official(calls, [candidate])
        },
        output_dir=tmp_path / "bundle",
        input_mode="mock",
    )

    assert "unit_unknown" in result["issue_codes"]
    assert result["completion"].residual_gap_count == 1
    assert result["delivery_eligibility"] != "analysis_ready"


def test_official_unresolved_date_semantics_cannot_be_promoted(
    tmp_path: Path,
) -> None:
    module = _module()
    calls: list[str] = []
    candidate = _candidate("2020", provider="world_bank")
    candidate["p_date"]["semantics"] = "unresolved"

    result = module.run_datapro_first_completion(
        request=_request(),
        datapro_connector=_datapro(calls, ("2019", "2021")),
        official_connectors={
            "world_bank": _official(calls, [candidate])
        },
        output_dir=tmp_path / "bundle",
        input_mode="mock",
    )

    assert "p_date_semantics_unresolved" in result["issue_codes"]
    assert result["completion"].residual_gap_count == 1
    assert result["delivery_eligibility"] != "analysis_ready"
