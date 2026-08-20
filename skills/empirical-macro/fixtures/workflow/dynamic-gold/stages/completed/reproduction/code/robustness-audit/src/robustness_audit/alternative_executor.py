"""Execute every planned alternative serially and retain failure evidence."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import cast

from robustness_audit.adapter_protocol import EstimatorAdapter
from robustness_audit.models import AuditAlternativeSpec, AuditPlan
from robustness_audit.subprocess_runner import CommandResult


def _write_request(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _record(
    alternative: AuditAlternativeSpec,
    request: dict[str, object],
    bundle: Path,
    *,
    status: str,
    issue_codes: list[str],
    execution_error: str | None,
    duration_seconds: float,
    returncode: int | None,
    stdout: str,
    stderr: str,
) -> dict[str, object]:
    return {
        "alternative_id": alternative.alternative_id,
        "check_id": alternative.check_id,
        "patch": dict(alternative.patch),
        "request": request,
        "request_id": request["request_id"],
        "request_path": f".requests/{alternative.alternative_id}.json",
        "bundle_path": str(bundle),
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "duration_seconds": duration_seconds,
        "status": status,
        "issue_codes": issue_codes,
        "execution_error": execution_error,
    }


def _validated_result(
    adapter: EstimatorAdapter,
    bundle: Path,
    request: dict[str, object],
) -> dict[str, object]:
    adapter.validate_result_bundle(bundle)
    documents = {
        filename: json.loads((bundle / filename).read_text(encoding="utf-8"))
        for filename in (
            "request.json",
            "result.json",
            "diagnostics.json",
            "run-manifest.json",
        )
    }
    result = cast(dict[str, object], documents["result.json"])
    if not isinstance(result.get("result_id"), str):
        raise ValueError("result_id missing")
    if documents["request.json"] != request:
        raise ValueError("bundle request content mismatch")
    request_id = request["request_id"]
    if any(document.get("request_id") != request_id for document in documents.values()):
        raise ValueError("bundle request_id mismatch")
    return result


def _effective_request(
    request_path: Path,
    fallback: dict[str, object],
) -> dict[str, object]:
    try:
        document = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
    return cast(dict[str, object], document) if isinstance(document, dict) else fallback


def _execute_command(
    alternative: AuditAlternativeSpec,
    adapter: EstimatorAdapter,
    request: dict[str, object],
    request_path: Path,
    input_paths: dict[str, Path],
    bundle: Path,
    timeout_seconds: float,
) -> CommandResult | dict[str, object]:
    started = time.monotonic()
    try:
        result = adapter.execute(
            request_path,
            input_paths,
            bundle,
            timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        request = _effective_request(request_path, request)
        return _record(
            alternative,
            request,
            bundle,
            status="error",
            issue_codes=["alternative_timeout"],
            execution_error=str(exc),
            duration_seconds=round(time.monotonic() - started, 6),
            returncode=None,
            stdout=str(exc.output or ""),
            stderr=str(exc.stderr or ""),
        )
    if result.returncode == 0:
        return result
    request = _effective_request(request_path, request)
    return _record(
        alternative,
        request,
        bundle,
        status="error",
        issue_codes=["alternative_execution_failed"],
        execution_error=result.stderr or result.stdout,
        duration_seconds=result.duration_seconds,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _execute_one(
    alternative: AuditAlternativeSpec,
    adapter: EstimatorAdapter,
    baseline_request: dict[str, object],
    input_paths: dict[str, Path],
    staging_dir: Path,
    timeout_seconds: float,
) -> dict[str, object]:
    patch = dict(alternative.patch)
    request = adapter.derive_request(
        baseline_request,
        patch,
        alternative.alternative_id,
    )
    request_path = (
        staging_dir / ".requests" / f"{alternative.alternative_id}.json"
    )
    bundle = staging_dir / "alternative-bundles" / alternative.alternative_id
    _write_request(request_path, request)
    result = _execute_command(
        alternative,
        adapter,
        request,
        request_path,
        input_paths,
        bundle,
        timeout_seconds,
    )
    if isinstance(result, dict):
        return result
    request = _effective_request(request_path, request)
    try:
        result_document = _validated_result(
            adapter,
            bundle,
            request,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issue = (
            "alternative_bundle_request_mismatch"
            if str(exc).startswith("bundle request")
            else "alternative_bundle_invalid"
        )
        return _record(
            alternative,
            request,
            bundle,
            status="error",
            issue_codes=[issue],
            execution_error=str(exc),
            duration_seconds=result.duration_seconds,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    record = _record(
        alternative,
        request,
        bundle,
        status="success",
        issue_codes=[],
        execution_error=None,
        duration_seconds=result.duration_seconds,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
    record["result_id"] = result_document["result_id"]
    return record


def execute_alternatives(
    plan: AuditPlan,
    adapter: EstimatorAdapter,
    baseline_request: dict[str, object],
    input_paths: dict[str, Path],
    staging_dir: Path,
) -> tuple[dict[str, object], ...]:
    if len(plan.alternatives) + 1 > plan.max_variants:
        raise ValueError("variant_budget_exceeded")
    deadline = time.monotonic() + plan.max_runtime_seconds
    records: list[dict[str, object]] = []
    for alternative in plan.alternatives:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            request = adapter.derive_request(
                baseline_request,
                dict(alternative.patch),
                alternative.alternative_id,
            )
            records.append(
                _record(
                    alternative,
                    request,
                    staging_dir
                    / "alternative-bundles"
                    / alternative.alternative_id,
                    status="error",
                    issue_codes=["runtime_budget_exceeded"],
                    execution_error="runtime budget exhausted",
                    duration_seconds=0.0,
                    returncode=None,
                    stdout="",
                    stderr="runtime budget exhausted",
                )
            )
            continue
        records.append(
            _execute_one(
                alternative,
                adapter,
                baseline_request,
                input_paths,
                staging_dir,
                remaining,
            )
        )
    planned = [item.alternative_id for item in plan.alternatives]
    observed = [str(item["alternative_id"]) for item in records]
    if planned != observed:
        raise ValueError("alternative_set_mismatch")
    request_ids = [str(item["request_id"]) for item in records]
    if len(request_ids) != len(set(request_ids)):
        raise ValueError("alternative_request_id_reuse")
    return tuple(records)
