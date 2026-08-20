import json
from pathlib import Path

import pytest
from conftest import load_module


def test_connector_reads_key_from_environment_without_exposing_it(monkeypatch):
    connector_module = load_module("macro_data.connectors.datapro")
    monkeypatch.setenv("DATAPRO_AGENT_PLAN_KEY", "test-only-secret")

    connector = connector_module.DataProConnector(
        transport=lambda query, key: {
            "code": 0,
            "msg": "success",
            "trace_" + "id": "trace-sensitive",
            "dataset_type": "macro",
            "items": [],
            "_observed_key": key,
            "_observed_query": query,
        }
    )
    response = connector.search("中国年度 CPI")

    serialized = json.dumps(response)
    assert "test-only-secret" not in serialized
    assert "trace-sensitive" not in serialized
    assert response["trace_id_sha256"]
    assert response["query"] == "中国年度 CPI"


def test_connector_fails_without_a_secret_source(monkeypatch, tmp_path):
    connector_module = load_module("macro_data.connectors.datapro")
    monkeypatch.delenv("DATAPRO_AGENT_PLAN_KEY", raising=False)

    with pytest.raises(RuntimeError, match="DataPro credential"):
        connector_module.DataProConnector(config_path=tmp_path / "missing.json")


def test_connector_prefers_standard_trae_config_over_legacy_trae_cn_config(
    monkeypatch,
):
    connector_module = load_module("macro_data.connectors.datapro")
    monkeypatch.delenv("DATAPRO_AGENT_PLAN_KEY", raising=False)
    standard_path = Path.home() / ".trae" / "mcp.json"
    legacy_path = connector_module.DEFAULT_CONFIG

    def read_config(path, *args, **kwargs):
        keys = {
            standard_path: "current-test-key",
            legacy_path: "stale-test-key",
        }
        if path not in keys:
            raise FileNotFoundError(path)
        return json.dumps(
            {"mcpServers": {"dataPro-search": {"headers": {"X-Agent-Plan-Key": keys[path]}}}}
        )

    monkeypatch.setattr(Path, "read_text", read_config)
    connector = connector_module.DataProConnector(
        transport=lambda query, key: {
            "code": 0 if key == "current-test-key" else 4011,
            "msg": "success" if key == "current-test-key" else "auth failed",
            "dataset_type": "macro" if key == "current-test-key" else None,
            "items": [],
        }
    )

    assert connector.search("中国年度 CPI")["code"] == 0
