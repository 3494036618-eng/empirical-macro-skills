"""End-to-end macro-data workflow."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from macro_data.connectors.base import Connector, ConnectorRequest
from macro_data.contracts import validate_document
from macro_data.exporter import export_bundle
from macro_data.provenance import canonical_json
from macro_data.request_parser import parse_research_request
from macro_data.result_parser import parse_datapro_response
from macro_data.semantic_validator import evaluate_candidates
from macro_data.source_registry import SourceRegistry
from macro_data.source_router import SourceRouter
from macro_data.transformation_engine import apply_transformations

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _validate_request(request: dict[str, Any]) -> None:
    validate_document("request", request)


def _validate_source_payload(source_payload: dict[str, Any]) -> None:
    response = source_payload.get("response", source_payload)
    if not isinstance(response, dict):
        raise ValueError("provider response must be an object")
    items = response.get("items", [])
    if not isinstance(items, list):
        raise ValueError("provider response items must be an array")
    if any(not isinstance(item, dict) for item in items):
        raise ValueError("provider response items must contain objects")


def _request_id(request: dict[str, Any]) -> str:
    return "request-" + hashlib.sha256(canonical_json(request)).hexdigest()[:24]


def _export_transactionally(
    *,
    request: dict[str, Any],
    evaluation: dict[str, Any],
    output_dir: Path,
    input_mode: str,
) -> dict[str, Any]:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.staging-",
            dir=output_dir.parent,
        )
    )
    backup_root: Path | None = None
    backup: Path | None = None
    try:
        result = export_bundle(
            request=request,
            evaluation=evaluation,
            output_dir=staging,
            input_mode=input_mode,
        )
        if output_dir.exists():
            backup_root = Path(
                tempfile.mkdtemp(
                    prefix=f".{output_dir.name}.backup-",
                    dir=output_dir.parent,
                )
            )
            backup = backup_root / "previous"
            os.replace(output_dir, backup)
        try:
            os.replace(staging, output_dir)
        except Exception:
            if backup is not None and backup.exists():
                os.replace(backup, output_dir)
            raise
        if backup_root is not None:
            shutil.rmtree(backup_root, ignore_errors=True)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if backup is not None and backup.exists() and not output_dir.exists():
            os.replace(backup, output_dir)
        if backup_root is not None:
            shutil.rmtree(backup_root, ignore_errors=True)
        raise


def run_macro_data_request(
    *,
    request: dict[str, Any],
    source_payload: dict[str, Any],
    output_dir: Path,
    input_mode: str,
) -> dict[str, Any]:
    _validate_request(request)
    _validate_source_payload(source_payload)
    parsed = parse_datapro_response(source_payload)
    parsed["candidates"], parsed["transformations"] = apply_transformations(
        request,
        parsed["candidates"],
    )
    evaluation = evaluate_candidates(request, parsed)
    fixture_query = parsed.get("fixture_provenance", {}).get("request", {}).get("query")
    if (
        input_mode == "sanitized-live-replay"
        and fixture_query
        and fixture_query.strip() != request["research_question"].strip()
    ):
        evaluation["issue_codes"] = sorted(
            set(evaluation["issue_codes"]) | {"fixture_request_mismatch"}
        )
        if evaluation["execution_status"] == "success":
            evaluation["execution_status"] = "partial"
        evaluation["research_readiness"] = "review_required"
        evaluation["delivery_eligibility"] = "not_deliverable"
        evaluation["eligible_for_estimation"] = False
        evaluation["review_required"] = True
    return _export_transactionally(
        request=request,
        evaluation=evaluation,
        output_dir=output_dir,
        input_mode=input_mode,
    )


def run_with_connector(
    *,
    request: dict[str, Any],
    connector: Connector,
    output_dir: Path,
    input_mode: str = "live",
) -> dict[str, Any]:
    _validate_request(request)
    SourceRouter(SourceRegistry.default()).authorize(request, connector.code)
    response = connector.retrieve(
        ConnectorRequest(
            request_id=_request_id(request),
            query=request["research_question"],
            research_request=request,
        )
    )
    parsed = connector.parse_response(response.raw)
    parsed["candidates"], parsed["transformations"] = apply_transformations(
        request,
        parsed["candidates"],
    )
    parsed["fixture_provenance"] = {
        "fixture_type": input_mode,
        "executed_at": response.retrieved_at,
        "request": {"query": request["research_question"]},
    }
    evaluation = evaluate_candidates(request, parsed)
    return _export_transactionally(
        request=request,
        evaluation=evaluation,
        output_dir=output_dir,
        input_mode=input_mode,
    )


def run_macro_data(
    *,
    research_question: str,
    source_payload: dict[str, Any],
    output_dir: Path,
    input_mode: str,
) -> dict[str, Any]:
    request = parse_research_request(research_question)
    return run_macro_data_request(
        request=request,
        source_payload=source_payload,
        output_dir=output_dir,
        input_mode=input_mode,
    )
