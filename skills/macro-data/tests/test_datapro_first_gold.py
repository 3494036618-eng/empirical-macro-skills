from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest

from macro_data.completion_assembler import (
    assemble_completion,
    classify_contribution,
)
from macro_data.connectors.base import ConnectorRequest, ConnectorResponse
from macro_data.contracts import validate_document
from macro_data.multi_source_pipeline import run_datapro_first_completion
from macro_data.observation_matrix import build_expected_matrix
from macro_data.primary_cell_ledger import LockedObservation, PrimaryCellLedger
from macro_data.request_migration import migrate_request_v02_to_v03
from macro_data.series_mapping import resolve_series_mapping, validate_overlap

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "completion"
LEGACY = ROOT / "fixtures" / "synthetic" / "schema-examples"
CASES = cast(
    list[dict[str, Any]],
    json.loads((FIXTURES / "gold" / "cases.json").read_text(encoding="utf-8")),
)


class RecordingConnector:
    def __init__(
        self,
        *,
        code: str,
        calls: list[str],
        candidates: list[dict[str, Any]],
        provider_code: int = 0,
    ) -> None:
        self.code = code
        self.calls = calls
        self.candidates = candidates
        self.provider_code = provider_code
        self.call_count = 0

    def retrieve(self, request: ConnectorRequest) -> ConnectorResponse:
        self.calls.append(self.code)
        self.call_count += 1
        return ConnectorResponse(
            provider=self.code,
            request_id=request.request_id,
            raw={"code": self.provider_code, "items": []},
            retrieved_at="2026-08-19T00:00:00Z",
        )

    def parse_response(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": self.code,
            "execution": {
                "provider_code": self.provider_code,
                "message": "success" if self.provider_code == 0 else "failed",
            },
            "candidates": copy.deepcopy(self.candidates),
            "raw_response": raw,
            "fixture_provenance": {},
        }


def _load(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], document)


def _request() -> dict[str, Any]:
    return _load(FIXTURES / "request.valid.json")


def _candidate(
    period: str,
    *,
    provider: str,
    source: str = "WORLD_BANK",
    value: float | None = None,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "series_key": (
            f"{source}|World Development Indicators|CHN|FP.CPI.TOTL"
        ),
        "source_system": source,
        "dataset_id": "2",
        "dataset_name": "World Development Indicators",
        "entity_code": "CHN",
        "entity_name": "China",
        "indicator_code": "FP.CPI.TOTL",
        "indicator_name": "Consumer price index",
        "time_raw": period,
        "time_grain": "year",
        "observed_frequency": "A",
        "value": (
            value if value is not None else 100.0 + int(period) - 2019
        ),
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
        "p_date": {"value": "2026-08-19", "semantics": "source_last_updated"},
        "license": {
            "id": "CC-BY-4.0",
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "attribution": "World Bank",
            "use_status": "allowed",
            "allows_requested_use": True,
        },
    }


def _locked(
    matrix: Any,
    period: str,
    *,
    provider: str,
    value: float,
) -> LockedObservation:
    cell = next(cell for cell in matrix.cells if cell.key.period == period)
    return LockedObservation(
        cell_id=cell.cell_id,
        key=cell.key,
        value=value,
        retrieval_provider=provider,
        source_system="WORLD_BANK",
        dataset_id="2",
        native_series_key=(
            "WORLD_BANK|World Development Indicators|CHN|FP.CPI.TOTL"
        ),
        canonical_series_id="macro-series-" + "a" * 32,
        origin_role=(
            "datapro_primary"
            if provider == "datapro"
            else "official_missing_only"
        ),
        raw_artifact=f"raw/{provider}.json",
        raw_checksum="sha256:" + "b" * 64,
        retrieved_at="2026-08-19T00:00:00Z",
        item={},
    )


def _pipeline_case(case: dict[str, Any], tmp_path: Path) -> None:
    request = _request()
    policy = case.get("policy")
    if policy == "never":
        request["preferred_sources"] = ["datapro"]
        request["fallback_policy"]["mode"] = "never"
        request["fallback_policy"]["allowed_sources"] = []
    elif policy == "ask":
        request["fallback_policy"]["mode"] = "ask"
    calls: list[str] = []
    datapro = RecordingConnector(
        code="datapro",
        calls=calls,
        candidates=[
            _candidate(period, provider="datapro")
            for period in case["datapro_periods"]
        ],
    )
    official_candidates = [
        _candidate(
            period,
            provider="world_bank",
            source=case.get("official_source", "WORLD_BANK"),
            value=(
                case["overlap_value"]
                if period == "2019" and "overlap_value" in case
                else None
            ),
        )
        for period in case["official_periods"]
    ]
    official = RecordingConnector(
        code="world_bank",
        calls=calls,
        candidates=official_candidates,
        provider_code=case.get("official_code", 0),
    )
    registry = (
        {"world_bank": official}
        if case.get("official_available", True)
        else {}
    )

    result = run_datapro_first_completion(
        request=request,
        datapro_connector=datapro,
        official_connectors=registry,
        output_dir=tmp_path / case["case_id"],
        input_mode="mock",
    )

    assert result["provider_contribution"]["classification"] == (
        case["expected_classification"]
    )
    assert result["delivery_eligibility"] == case["expected_delivery"]
    assert official.call_count == case["expected_official_calls"]
    if "expected_issue" in case:
        assert case["expected_issue"] in result["issue_codes"]


def _matrix_case(case: dict[str, Any]) -> None:
    request = _request()
    request["frequency"] = case["frequency"]
    request["time_range"] = {"start": case["start"], "end": case["end"]}
    request["entities"] = [
        {
            "name_or_code": entity,
            "entity_type": "country",
            "code_scheme": "ISO-3166-1-alpha-3",
        }
        for entity in case["entities"]
    ]
    request["indicators"] = [
        {
            "name_or_code": indicator,
            "required_definition": f"Definition for {indicator}",
        }
        for indicator in case["indicators"]
    ]
    assert len(build_expected_matrix(request).cells) == case["expected_count"]


def _mapping_item(source: str) -> dict[str, Any]:
    item = _candidate("2020", provider="datapro", source=source)
    item["series_key"] = f"{source}|2|CHN|FP.CPI.TOTL|A"
    return item


def _overlap_case(case: dict[str, Any]) -> None:
    matrix = build_expected_matrix(_request())
    primary = _locked(
        matrix,
        "2019",
        provider="datapro",
        value=case["primary_value"],
    )
    fallback = _locked(
        matrix,
        "2019",
        provider="world_bank",
        value=case["fallback_value"],
    )
    result = validate_overlap(
        (primary,),
        (fallback,),
        absolute_tolerance=0.00001,
        relative_tolerance=0.0,
    )
    assert result.status == case["expected"]


def _primary_preservation(case: dict[str, Any]) -> None:
    request = _request()
    request["time_range"] = {"start": "2019", "end": "2019"}
    matrix = build_expected_matrix(request)
    primary_observation = _locked(
        matrix,
        "2019",
        provider="datapro",
        value=case["primary_value"],
    )
    primary = PrimaryCellLedger(
        matrix_id=matrix.matrix_id,
        locked=(primary_observation,),
        rejected=(),
        issue_codes=(),
    )
    result = assemble_completion(
        matrix=matrix,
        primary=primary,
        fallback=(
            _locked(
                matrix,
                "2019",
                provider="world_bank",
                value=case["fallback_value"],
            ),
        ),
        overlaps=(),
    )
    assert result.observations[0].value == case["expected_value"]


@pytest.mark.parametrize("case", CASES, ids=[item["case_id"] for item in CASES])
def test_datapro_first_gold(case: dict[str, Any], tmp_path: Path) -> None:
    operation = case["operation"]
    if operation == "pipeline":
        _pipeline_case(case, tmp_path)
    elif operation == "classification":
        assert classify_contribution(
            case["datapro"],
            case["official"],
            datapro_attempted=True,
        ) == case["expected"]
    elif operation == "matrix":
        _matrix_case(case)
    elif operation == "mapping":
        mapping = resolve_series_mapping(
            _mapping_item(case["primary_source"]),
            _mapping_item(case["fallback_source"]),
        )
        assert mapping.status == case["expected"]
    elif operation == "overlap":
        _overlap_case(case)
    elif operation == "overlap_none":
        assert validate_overlap(
            (),
            (),
            absolute_tolerance=0.0,
            relative_tolerance=0.0,
        ).status == case["expected"]
    elif operation == "contract":
        document = _load(FIXTURES / case["fixture"])
        if case["expected"] == "valid":
            validate_document(case["contract"], document)
        else:
            with pytest.raises(ValueError):
                validate_document(case["contract"], document)
    elif operation == "migration":
        legacy = _load(LEGACY / "request.valid.json")
        legacy["preferred_sources"].append("world_bank")
        legacy["fallback_policy"] = {
            "mode": "allow_official",
            "allowed_sources": ["world_bank"],
            "allow_semantic_substitute": False,
            "allow_cross_source_stitching": False,
        }
        assert migrate_request_v02_to_v03(legacy)["fallback_policy"]["mode"] == (
            case["expected_mode"]
        )
    else:
        _primary_preservation(case)
