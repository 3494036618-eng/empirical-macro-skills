"""Minimal DataPro MCP connector with credential redaction."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from macro_data.connectors.base import ConnectorRequest, ConnectorResponse
from macro_data.result_parser import parse_datapro_response

ENDPOINT = "https://datapro.hqd.cn-beijing.volces.com/mcp"
TRAE_CONFIG = Path.home() / ".trae" / "mcp.json"
DEFAULT_CONFIG = Path.home() / "Library" / "Application Support" / "Trae CN" / "User" / "mcp.json"
DEFAULT_CONFIGS = (TRAE_CONFIG, DEFAULT_CONFIG)
_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "x-agent-plan-key",
    "api_key",
    "apikey",
    "token",
    "secret",
    "_observed_key",
    "_observed_query",
}


def _load_key(config_path: Path | None = None) -> str:
    environment = os.environ.get("DATAPRO_AGENT_PLAN_KEY")
    if environment:
        return environment
    config_paths = (config_path,) if config_path is not None else DEFAULT_CONFIGS
    for candidate in config_paths:
        try:
            document = json.loads(candidate.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                continue
            servers = document["mcpServers"]
            if not isinstance(servers, dict):
                continue
            entry = servers.get("dataPro-search") or servers.get("datapro") or servers.get(ENDPOINT)
            if not isinstance(entry, dict):
                continue
            headers = entry["headers"]
            if not isinstance(headers, dict):
                continue
            key = headers["X-Agent-Plan-Key"]
        except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError):
            continue
        if isinstance(key, str) and key:
            return key
    raise RuntimeError("DataPro credential is unavailable")


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key.lower() in _SENSITIVE_KEYS:
                continue
            if key == "trace_id" and isinstance(item, str):
                result["trace_id_sha256"] = hashlib.sha256(item.encode()).hexdigest()
                continue
            result[key] = _sanitize(item)
        return result
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


class DataProConnector:
    code = "datapro"

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        transport: Callable[[str, str], dict[str, Any]] | None = None,
    ) -> None:
        self._key = _load_key(config_path)
        self._transport = transport or self._http_transport

    def search(self, query: str) -> dict[str, Any]:
        response = _sanitize(self._transport(query, self._key))
        if not isinstance(response, dict):
            raise TypeError("DataPro transport response must be an object")
        response["query"] = query
        return cast(dict[str, Any], response)

    def retrieve(self, request: ConnectorRequest) -> ConnectorResponse:
        return ConnectorResponse(
            provider=self.code,
            request_id=request.request_id,
            raw=self.search(request.query),
            retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    @staticmethod
    def parse_response(raw: dict[str, Any]) -> dict[str, Any]:
        return parse_datapro_response(raw)

    @staticmethod
    def _http_transport(query: str, key: str) -> dict[str, Any]:
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "dataPro_search",
                    "arguments": {"query": query},
                },
            },
            ensure_ascii=False,
        ).encode()
        request = urllib.request.Request(
            ENDPOINT,
            data=payload,
            method="POST",
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "MCP-Protocol-Version": "2025-03-26",
                "X-Agent-Plan-Key": key,
            },
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        if not isinstance(decoded, dict):
            raise RuntimeError("DataPro MCP envelope must be an object")
        outer = cast(dict[str, Any], decoded)
        if "error" in outer:
            raise RuntimeError(f"DataPro MCP error: {outer['error']}")
        for content in outer.get("result", {}).get("content", []):
            if content.get("type") == "text":
                try:
                    payload = json.loads(content.get("text", ""))
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    return cast(dict[str, Any], payload)
        raise RuntimeError("DataPro MCP response did not contain JSON text")
