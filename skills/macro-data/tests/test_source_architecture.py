import importlib
import json

import pytest
from conftest import FIXTURES, load_json


def test_datapro_implements_the_common_connector_contract(monkeypatch):
    base = importlib.import_module("macro_data.connectors.base")
    datapro = importlib.import_module("macro_data.connectors.datapro")
    monkeypatch.setenv("DATAPRO_AGENT_PLAN_KEY", "test-only-secret")

    connector = datapro.DataProConnector(
        transport=lambda query, key: {
            "code": 0,
            "msg": "success",
            "dataset_type": "macro",
            "items": [],
        }
    )
    response = connector.retrieve(
        base.ConnectorRequest(
            request_id="request-001",
            query="中国年度 CPI",
        )
    )

    assert isinstance(connector, base.Connector)
    assert response.provider == "datapro"
    assert response.request_id == "request-001"
    assert response.raw["dataset_type"] == "macro"
    assert "test-only-secret" not in json.dumps(response.as_dict())


def test_source_registry_has_datapro_primary_and_world_bank_official_connector():
    registry_module = importlib.import_module("macro_data.source_registry")
    registry = registry_module.SourceRegistry.default()

    assert registry.primary().code == "datapro"
    assert registry.primary().kind == "aggregator"
    assert registry.enabled_codes() == ["datapro", "world_bank"]
    assert registry.get("world_bank") == registry_module.SourceDescriptor(
        code="world_bank",
        kind="official",
        connector_name="WorldBankConnector",
        priority=10,
    )


def test_router_never_silently_falls_back_when_policy_is_ask():
    parser = importlib.import_module("macro_data.request_parser")
    registry_module = importlib.import_module("macro_data.source_registry")
    router_module = importlib.import_module("macro_data.source_router")
    request = parser.parse_research_request(
        "获取中国 2019—2024 年年度 CPI，严格使用 World Bank WDI 口径。"
    )
    request["fallback_policy"]["mode"] = "ask"
    request["fallback_policy"]["allowed_sources"] = ["world_bank"]

    plan = router_module.SourceRouter(registry_module.SourceRegistry.default()).plan(request)

    assert plan.primary == "datapro"
    assert plan.fallback_mode == "ask"
    assert plan.fallback_candidates == ["world_bank"]
    assert plan.review_required is True


def test_canonical_series_identity_is_order_independent_and_frequency_sensitive():
    models = importlib.import_module("macro_data.models")
    first = models.SeriesIdentity.from_native(
        provider="datapro",
        dataset_id="2",
        series_key="WORLD_BANK|WDI|CHN|FP.CPI.TOTL",
        entity_code="CHN",
        indicator_code="FP.CPI.TOTL",
        frequency="A",
    )
    same = models.SeriesIdentity.from_native(
        indicator_code="FP.CPI.TOTL",
        entity_code="CHN",
        series_key="WORLD_BANK|WDI|CHN|FP.CPI.TOTL",
        dataset_id="2",
        provider="datapro",
        frequency="A",
    )
    monthly = models.SeriesIdentity.from_native(
        provider="datapro",
        dataset_id="2",
        series_key="WORLD_BANK|WDI|CHN|FP.CPI.TOTL",
        entity_code="CHN",
        indicator_code="FP.CPI.TOTL",
        frequency="M",
    )

    assert first.identity_id == same.identity_id
    assert first.identity_id != monthly.identity_id
    assert first.identity_id.startswith("sha256:")


def test_pipeline_accepts_a_validated_structured_request_without_nlp_reparsing(
    tmp_path,
):
    parser = importlib.import_module("macro_data.request_parser")
    pipeline = importlib.import_module("macro_data.pipeline")
    request = parser.parse_research_request(
        "查询中国 2019-01 至 2024-12 的月度居民消费价格指数 CPI。"
    )
    fixture = load_json(FIXTURES / "sanitized-live" / "02_china_monthly_cpi.json")

    result = pipeline.run_macro_data_request(
        request=request,
        source_payload=fixture,
        output_dir=tmp_path / "structured",
        input_mode="sanitized-live-replay",
    )

    assert "frequency_mismatch" in result["issue_codes"]
    assert load_json(tmp_path / "structured" / "request_manifest.json") == request


def test_pipeline_can_execute_through_an_injected_connector(tmp_path):
    base = importlib.import_module("macro_data.connectors.base")
    parser = importlib.import_module("macro_data.request_parser")
    pipeline = importlib.import_module("macro_data.pipeline")
    request = parser.parse_research_request("查询中国 2019—2024 年年度 CPI。")
    fixture = load_json(FIXTURES / "sanitized-live" / "02_china_monthly_cpi.json")

    class FixtureConnector:
        code = "datapro"

        def retrieve(self, connector_request):
            return base.ConnectorResponse(
                provider=self.code,
                request_id=connector_request.request_id,
                raw=fixture["response"],
                retrieved_at=fixture["executed_at"],
            )

        @staticmethod
        def parse_response(raw):
            parser = importlib.import_module("macro_data.result_parser")
            return parser.parse_datapro_response(raw)

    result = pipeline.run_with_connector(
        request=request,
        connector=FixtureConnector(),
        output_dir=tmp_path / "connector",
        input_mode="mock",
    )

    assert result["execution_status"] == "success"
    assert (tmp_path / "connector" / "result.json").exists()


def test_route_plan_ignores_unknown_and_disabled_sources():
    registry_module = importlib.import_module("macro_data.source_registry")
    router_module = importlib.import_module("macro_data.source_router")
    registry = registry_module.SourceRegistry(
        [
            registry_module.SourceDescriptor(
                "datapro",
                "aggregator",
                "DataProConnector",
                0,
            ),
            registry_module.SourceDescriptor(
                "disabled",
                "official",
                "DisabledConnector",
                20,
                enabled=False,
            ),
        ]
    )
    request = load_json(FIXTURES / "synthetic" / "schema-examples" / "request.valid.json")
    request["fallback_policy"]["allowed_sources"] = ["missing", "disabled"]

    plan = router_module.SourceRouter(registry).plan(request)

    assert plan.fallback_candidates == []


def test_router_authorizes_v03_missing_only_world_bank() -> None:
    registry_module = importlib.import_module("macro_data.source_registry")
    router_module = importlib.import_module("macro_data.source_router")
    request = json.loads(
        (
            FIXTURES
            / "completion"
            / "request.valid.json"
        ).read_text(encoding="utf-8")
    )
    router = router_module.SourceRouter(registry_module.SourceRegistry.default())

    plan = router.authorize(request, "world_bank")

    assert plan.fallback_mode == "allow_official_missing_only"


def test_series_identity_as_dict_preserves_nullable_native_fields():
    models = importlib.import_module("macro_data.models")
    identity = models.SeriesIdentity.from_native(
        provider="datapro",
        dataset_id=None,
        series_key=None,
        entity_code=None,
        indicator_code=None,
        frequency=None,
    )

    assert identity.as_dict()["dataset_id"] is None


def _route_request(mode, allowed):
    return {
        "fallback_policy": {
            "mode": mode,
            "allowed_sources": allowed,
        }
    }


def _router(*, world_bank_enabled=True):
    registry_module = importlib.import_module("macro_data.source_registry")
    router_module = importlib.import_module("macro_data.source_router")
    return router_module.SourceRouter(
        registry_module.SourceRegistry(
            [
                registry_module.SourceDescriptor(
                    "datapro",
                    "aggregator",
                    "DataProConnector",
                    0,
                ),
                registry_module.SourceDescriptor(
                    "world_bank",
                    "official",
                    "WorldBankConnector",
                    10,
                    enabled=world_bank_enabled,
                ),
            ]
        )
    )


def test_authorize_rejects_disabled_source():
    with pytest.raises(ValueError, match="not enabled"):
        _router(world_bank_enabled=False).authorize(
            _route_request("allow_official", ["world_bank"]),
            "world_bank",
        )


def test_authorize_rejects_source_outside_request_policy():
    with pytest.raises(ValueError, match="not allowed"):
        _router().authorize(
            _route_request("allow_official", []),
            "world_bank",
        )


def test_authorize_rejects_never_fallback():
    with pytest.raises(ValueError, match="fallback is disabled"):
        _router().authorize(
            _route_request("never", ["world_bank"]),
            "world_bank",
        )


def test_authorize_allows_explicit_official_fallback():
    plan = _router().authorize(
        _route_request("allow_official", ["world_bank"]),
        "world_bank",
    )

    assert plan.primary == "datapro"
    assert plan.fallback_candidates == ["world_bank"]
