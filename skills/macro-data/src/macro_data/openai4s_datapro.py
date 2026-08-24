"""OpenAI4S Host bridge for the managed professional-dataset connector."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from macro_data.completion_export import export_completion_bundle
from macro_data.completion_validation import validate_completion_bundle
from macro_data.connectors.base import ConnectorRequest, ConnectorResponse
from macro_data.contracts import validate_document
from macro_data.datapro_batch_plan import BatchPolicy
from macro_data.multi_source_pipeline import run_datapro_first_completion
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


def _publish(staging: Path, output: Path) -> None:
    backup: Path | None = None
    if output.exists():
        backup = output.with_name(f".{output.name}.backup")
        if backup.exists():
            shutil.rmtree(backup)
        os.replace(output, backup)
    try:
        os.replace(staging, output)
    except BaseException:
        if backup is not None and backup.exists() and not output.exists():
            os.replace(backup, output)
        raise
    finally:
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)


def run_with_openai4s_datapro(
    host: object,
    request: dict[str, object],
    output_dir: Path,
) -> dict[str, object]:
    validate_document("request", cast(dict[str, Any], request))
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.staging-",
            dir=output_dir.parent,
        )
    )
    try:
        run = run_datapro_first_completion(
            request=cast(dict[str, Any], request),
            datapro_connector=OpenAI4SDataProConnector(host),
            official_connectors={},
            output_dir=staging,
            input_mode="live",
            batch_policy=BatchPolicy(
                maximum_periods={"M": 12, "Q": 8, "A": 10},
                maximum_calls=200,
            ),
        )
        export_completion_bundle(
            request=cast(dict[str, Any], request),
            result=run["completion"],
            retrievals=run["retrievals"],
            gap_manifest=run["gap_manifest"],
            output_dir=staging,
            input_mode="live",
        )
        validation = validate_completion_bundle(staging)
        if validation["valid"] is not True:
            raise RuntimeError("completion bundle validation failed")
        _publish(staging, output_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return {
        "status": run["execution_status"],
        "research_readiness": run["research_readiness"],
        "delivery_eligibility": run["delivery_eligibility"],
        "eligible_for_estimation": run["eligible_for_estimation"],
        "provider_contribution": run["provider_contribution"],
        "issue_codes": run["issue_codes"],
        "bundle_valid": True,
    }
