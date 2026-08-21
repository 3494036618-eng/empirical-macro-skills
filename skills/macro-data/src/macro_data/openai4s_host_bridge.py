"""Translate the OpenAI4S MCP host contract into a macro-data connector."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, cast

from macro_data.connectors.base import ConnectorRequest, ConnectorResponse
from macro_data.result_parser import parse_datapro_response

SERVER = "volcengine-datapro"
TOOL = "dataPro_search"
_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "x-agent-plan-key",
    "api_key",
    "apikey",
    "token",
    "secret",
}


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in _SENSITIVE_KEYS:
                continue
            if key == "trace_id" and isinstance(item, str):
                digest = hashlib.sha256(item.encode()).hexdigest()
                output["trace_id_sha256"] = f"sha256:{digest}"
                continue
            output[key] = _sanitize(item)
        return output
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _mcp(host: object) -> object:
    mcp = getattr(host, "mcp", None)
    if mcp is None:
        raise RuntimeError("OpenAI4S host.mcp is unavailable")
    return mcp


def _index_complete(index: object) -> bool:
    if not isinstance(index, dict):
        return False
    source_count = index.get("source_leaf_count")
    indexed_count = index.get("indexed_leaf_count")
    source_digest = index.get("source_digest")
    indexed_digest = index.get("indexed_digest")
    return (
        index.get("complete") is True
        and type(source_count) is int
        and type(indexed_count) is int
        and source_count == indexed_count
        and isinstance(source_digest, str)
        and bool(source_digest)
        and source_digest == indexed_digest
    )


class OpenAI4SDataProConnector:
    code = "datapro"

    def __init__(self, host: object) -> None:
        self._mcp = _mcp(host)
        discovery = getattr(self._mcp, "tools")(SERVER)
        tools = discovery.get("tools") if isinstance(discovery, dict) else None
        if not isinstance(tools, list) or not any(
            isinstance(tool, dict) and tool.get("name") == TOOL for tool in tools
        ):
            raise RuntimeError("dataPro_search is not available on volcengine-datapro")

    def retrieve(self, request: ConnectorRequest) -> ConnectorResponse:
        result = getattr(self._mcp, "call")(
            SERVER,
            TOOL,
            {"query": request.query},
        )
        raw = result.get("raw") if isinstance(result, dict) else None
        structured = raw.get("structuredContent") if isinstance(raw, dict) else None
        if not isinstance(structured, dict):
            raise RuntimeError("professional dataset returned no structured content")
        code = structured.get("code")
        if type(code) is not int or code != 0:
            raise RuntimeError(f"professional dataset unavailable: code={code!r}")
        if not _index_complete(result.get("index")):
            raise RuntimeError("professional dataset response index is incomplete")
        sanitized = cast(dict[str, Any], _sanitize(structured))
        sanitized["query"] = request.query
        return ConnectorResponse(
            provider=self.code,
            request_id=request.request_id,
            raw=sanitized,
            retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    @staticmethod
    def parse_response(raw: dict[str, Any]) -> dict[str, Any]:
        return parse_datapro_response(raw)
