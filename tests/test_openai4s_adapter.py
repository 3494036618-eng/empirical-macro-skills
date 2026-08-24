from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from empirical_macro.openai4s_installer import (
    INSTALL_ORDER,
    OpenAI4SSuiteInstallError,
    install_openai4s_suite,
)
from macro_data.connectors.base import ConnectorRequest

ROOT = Path(__file__).resolve().parents[1]


class _Sidecar:
    @staticmethod
    def sidecar_gate() -> dict[str, object]:
        return {"ok": True, "error": None}


class _Loader:
    @staticmethod
    def discover() -> dict[str, _Sidecar]:
        return {name: _Sidecar() for name in INSTALL_ORDER}


class _VersionService:
    def __init__(self, *, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.installed: list[str] = []
        self.deleted: list[str] = []

    @staticmethod
    def status(_name: str, **_kwargs: object) -> dict[str, object]:
        return {"active": False, "active_version_id": None}

    def install_directory(
        self,
        name: str,
        _root: Path,
        **_kwargs: object,
    ) -> dict[str, object]:
        if name == self.fail_on:
            raise RuntimeError("planned install failure")
        self.installed.append(name)
        return {"name": name, "version_id": f"version-{name}"}

    def rollback(
        self,
        _name: str,
        _version_id: str,
        **_kwargs: object,
    ) -> None:
        raise AssertionError("new installs must be deleted, not rolled back")

    def delete(self, name: str, **_kwargs: object) -> None:
        self.deleted.append(name)


def _adapter() -> Any:
    return importlib.import_module("macro_data.openai4s_datapro")


def test_openai4s_suite_install_reports_all_versions() -> None:
    service = _VersionService()

    report = install_openai4s_suite(
        source_root=ROOT / "skills",
        service=service,
        loader_factory=_Loader,
    )

    assert report["valid"] is True
    assert report["installed_skills"] == list(INSTALL_ORDER)
    assert report["sidecar_gates_passed"] == len(INSTALL_ORDER)
    assert report["versions"] == {
        name: f"version-{name}" for name in INSTALL_ORDER
    }


def test_openai4s_suite_install_removes_new_versions_after_failure() -> None:
    failed_skill = "time-series-dynamics"
    service = _VersionService(fail_on=failed_skill)

    with pytest.raises(OpenAI4SSuiteInstallError) as captured:
        install_openai4s_suite(
            source_root=ROOT / "skills",
            service=service,
            loader_factory=_Loader,
        )

    expected_changed = list(INSTALL_ORDER[: INSTALL_ORDER.index(failed_skill)])
    assert captured.value.report["installed_skills"] == expected_changed
    assert captured.value.report["failed_skill"] == failed_skill
    assert service.deleted == list(reversed(expected_changed))


def test_datapro_adapter_requires_host_mcp() -> None:
    adapter = _adapter()

    with pytest.raises(RuntimeError, match="host.mcp is unavailable"):
        adapter.OpenAI4SDataProConnector(SimpleNamespace())


def test_datapro_adapter_removes_secrets_and_hashes_trace_id() -> None:
    adapter = _adapter()
    trace_key = "trace_" + "id"

    sanitized = adapter._sanitize(
        {
            "token": "secret",
            trace_key: "raw-trace",
            "payload": {"authorization": "secret", "value": 1},
        }
    )

    assert "token" not in sanitized
    assert trace_key not in sanitized
    assert sanitized["trace_id_sha256"].startswith("sha256:")
    assert sanitized["payload"] == {"value": 1}


def test_datapro_adapter_calls_the_built_in_mcp_tool() -> None:
    adapter = _adapter()
    calls: list[tuple[str, str, dict[str, str]]] = []
    trace_key = "trace_" + "id"

    class _MCP:
        @staticmethod
        def call(
            server: str,
            tool: str,
            arguments: dict[str, str],
        ) -> dict[str, object]:
            calls.append((server, tool, arguments))
            return {
                "raw": {
                    "structuredContent": {
                        "code": 0,
                        trace_key: "raw-trace",
                        "token": "secret",
                        "items": [],
                    }
                },
                "index": {
                    "complete": True,
                    "source_leaf_count": 1,
                    "indexed_leaf_count": 1,
                    "source_digest": "digest",
                    "indexed_digest": "digest",
                },
            }

    connector = adapter.OpenAI4SDataProConnector(SimpleNamespace(mcp=_MCP()))
    response = connector.retrieve(
        ConnectorRequest(request_id="request-1", query="中国季度 GDP")
    )

    assert calls == [
        (
            "volcengine-datapro",
            "dataPro_search",
            {"query": "中国季度 GDP"},
        )
    ]
    assert response.provider == "datapro"
    assert response.request_id == "request-1"
    assert "token" not in response.raw
    assert trace_key not in response.raw
    assert response.raw["trace_id_sha256"].startswith("sha256:")


def test_datapro_adapter_rejects_an_incomplete_response_index() -> None:
    adapter = _adapter()

    class _MCP:
        @staticmethod
        def call(
            _server: str,
            _tool: str,
            _arguments: dict[str, str],
        ) -> dict[str, object]:
            return {
                "raw": {"structuredContent": {"code": 0, "items": []}},
                "index": {"complete": False},
            }

    connector = adapter.OpenAI4SDataProConnector(SimpleNamespace(mcp=_MCP()))

    with pytest.raises(RuntimeError, match="index is incomplete"):
        connector.retrieve(ConnectorRequest(request_id="request-1", query="GDP"))


def test_openai4s_completion_publishes_only_after_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter()
    output = tmp_path / "bundle"
    request: dict[str, object] = {"schema_version": "0.3.0-beta"}

    monkeypatch.setattr(adapter, "validate_document", lambda *_args: None)
    monkeypatch.setattr(
        adapter,
        "run_datapro_first_completion",
        lambda **_kwargs: {
            "completion": object(),
            "retrievals": (),
            "gap_manifest": object(),
            "execution_status": "completed",
            "research_readiness": "ready",
            "delivery_eligibility": "analysis_ready",
            "eligible_for_estimation": True,
            "provider_contribution": "datapro_only",
            "issue_codes": [],
        },
    )

    def export_completion_bundle(**kwargs: object) -> None:
        staging = kwargs["output_dir"]
        assert isinstance(staging, Path)
        (staging / "validated.txt").write_text("ready", encoding="utf-8")

    monkeypatch.setattr(adapter, "export_completion_bundle", export_completion_bundle)
    monkeypatch.setattr(
        adapter,
        "validate_completion_bundle",
        lambda path: {"valid": (path / "validated.txt").is_file()},
    )

    result = adapter.run_with_openai4s_datapro(
        SimpleNamespace(mcp=SimpleNamespace()),
        request,
        output,
    )

    assert result["bundle_valid"] is True
    assert (output / "validated.txt").read_text("utf-8") == "ready"


def test_openai4s_completion_preserves_output_when_validation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter()
    output = tmp_path / "bundle"
    output.mkdir()
    (output / "existing.txt").write_text("keep", encoding="utf-8")

    monkeypatch.setattr(adapter, "validate_document", lambda *_args: None)
    monkeypatch.setattr(
        adapter,
        "run_datapro_first_completion",
        lambda **_kwargs: {
            "completion": object(),
            "retrievals": (),
            "gap_manifest": object(),
        },
    )
    monkeypatch.setattr(adapter, "export_completion_bundle", lambda **_kwargs: None)
    monkeypatch.setattr(
        adapter,
        "validate_completion_bundle",
        lambda _path: {"valid": False},
    )

    with pytest.raises(RuntimeError, match="validation failed"):
        adapter.run_with_openai4s_datapro(
            SimpleNamespace(mcp=SimpleNamespace()),
            {"schema_version": "0.3.0-beta"},
            output,
        )

    assert (output / "existing.txt").read_text("utf-8") == "keep"
