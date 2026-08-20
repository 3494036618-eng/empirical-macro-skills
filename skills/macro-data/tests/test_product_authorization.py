from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from macro_data.connectors.base import ConnectorRequest, ConnectorResponse
from macro_data.contracts import validate_document
from macro_data.exporter import validate_bundle
from macro_data.pipeline import run_with_connector


def _authorization(scope: str = "controlled_public_demo") -> dict[str, Any]:
    return {
        "authorization_id": "product-auth-" + "a" * 32,
        "authorization_basis": "product_owner_directive",
        "data_use_scope": scope,
        "allowed_scopes": [
            "first_party_product_development",
            "internal_research",
            "controlled_public_demo",
        ],
        "public_payload_policy": "metadata_only",
    }


def _request(scope: str = "controlled_public_demo") -> dict[str, Any]:
    return {
        "schema_version": "0.2.0-beta",
        "research_question": "分析美国季度价格指数的动态变化。",
        "research_use": "dynamic_response",
        "concepts": [
            {
                "concept": "消费者价格指数",
                "role": "outcome",
                "definition_constraints": ["Consumer price index."],
            }
        ],
        "indicators": [
            {
                "name_or_code": "CPI_INDEX",
                "required_definition": "Consumer price index.",
            }
        ],
        "entities": [
            {
                "name_or_code": "USA",
                "entity_type": "country",
                "code_scheme": "ISO-3166-1-alpha-3",
            }
        ],
        "time_range": {"start": "2000-Q1", "end": "2009-Q4"},
        "frequency": "Q",
        "unit": None,
        "seasonal_adjustment": "source_native",
        "price_basis": {
            "type": "source_native",
            "base_period": None,
            "chain_linked": None,
        },
        "currency": None,
        "release_or_vintage": {"mode": "latest", "value": None},
        "preferred_sources": ["datapro"],
        "fallback_policy": {
            "mode": "never",
            "allowed_sources": [],
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
        "product_authorization": _authorization(scope),
    }


def _candidate(period: str, value: float) -> dict[str, Any]:
    return {
        "provider": "datapro",
        "series_key": "DATAPRO|IMF_IFS|USA|CPI_INDEX",
        "source_system": "IMF_IFS",
        "dataset_id": "IFS_QUARTERLY",
        "dataset_name": "International Financial Statistics",
        "dataset_code": "IFS",
        "entity_code": "USA",
        "entity_name": "United States",
        "indicator_code": "CPI_INDEX",
        "indicator_name": "Consumer Price Index",
        "time_raw": period,
        "time_grain": "quarter",
        "observed_frequency": "Q",
        "requested_frequency": "Q",
        "value": value,
        "unit": {"value": "index", "status": "source_documented"},
        "seasonal_adjustment": {
            "value": "SA",
            "status": "source_documented",
        },
        "price_basis": {"value": None, "status": "not_applicable"},
        "definition": {
            "value": "Consumer price index.",
            "status": "source_provided",
        },
        "release_date": {"value": None, "status": "unresolved"},
        "vintage": {"value": None, "status": "unresolved"},
        "p_date": {
            "value": "2026-08-18",
            "semantics": "source_last_updated",
        },
        "license": {
            "id": None,
            "url": None,
            "attribution": None,
            "use_status": "unknown",
            "allows_requested_use": False,
        },
        "evidence_references": [],
    }


def _candidates() -> list[dict[str, Any]]:
    periods = [f"{year}Q{quarter}" for year in range(2000, 2010) for quarter in range(1, 5)]
    return [_candidate(period, 100.0 + index) for index, period in enumerate(periods)]


@dataclass
class _DataProConnector:
    code: str = "datapro"

    def retrieve(self, request: ConnectorRequest) -> ConnectorResponse:
        return ConnectorResponse(
            provider=self.code,
            request_id=request.request_id,
            raw={"response": {"code": 0, "items": []}},
            retrieved_at="2026-08-18T00:00:00Z",
        )

    def parse_response(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": self.code,
            "execution": {"provider_code": 0, "message": "success"},
            "candidates": _candidates(),
            "raw_response": raw,
            "fixture_provenance": {},
        }


def test_request_contract_accepts_product_authorization() -> None:
    validate_document("request", _request())


def test_controlled_demo_authorization_allows_datapro_research_use() -> None:
    from macro_data.product_authorization import authorization_issues

    assert authorization_issues(_request(), _candidate("2000Q1", 100.0)) == set()


def test_unknown_scope_fails_closed() -> None:
    from macro_data.product_authorization import authorization_issues

    assert authorization_issues(
        _request("public_payload_redistribution"),
        _candidate("2000Q1", 100.0),
    ) == {"scope_not_authorized"}


def test_authorized_datapro_pipeline_is_analysis_ready(tmp_path: Path) -> None:
    output = tmp_path / "authorized-datapro"

    evaluation = run_with_connector(
        request=_request(),
        connector=_DataProConnector(),
        output_dir=output,
        input_mode="mock",
    )

    assert evaluation["delivery_eligibility"] == "analysis_ready"
    assert evaluation["eligible_for_estimation"] is True
    assert "license_unresolved" not in evaluation["issue_codes"]
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["data_use_scope"] == "controlled_public_demo"
    assert result["public_payload_policy"] == "metadata_only"
    assert result["product_authorization_ref"] == "product-auth-" + "a" * 32
    assert result["series"][0]["license"]["use_status"] == "unknown"
    assert result["series"][0]["use_authorization"] == {
        "authorization_ref": "product-auth-" + "a" * 32,
        "authorization_basis": "product_owner_directive",
        "scope": "controlled_public_demo",
        "status": "authorized",
    }
    provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["authorization_ref"] == "product-auth-" + "a" * 32
    assert provenance["credentials_recorded"] is False
    assert validate_bundle(output)["valid"] is True


def test_authorized_result_requires_top_level_authorization_binding(
    tmp_path: Path,
) -> None:
    output = tmp_path / "authorized-datapro"
    run_with_connector(
        request=_request(),
        connector=_DataProConnector(),
        output_dir=output,
        input_mode="mock",
    )
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    result.pop("product_authorization_ref")

    with pytest.raises(ValueError, match="product_authorization_ref"):
        validate_document("result", result)
