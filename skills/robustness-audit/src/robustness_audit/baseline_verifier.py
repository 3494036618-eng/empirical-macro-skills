"""Verify immutable baseline artifacts and execute an exact rerun."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import cast

from robustness_audit.models import AuditPlan
from robustness_audit.time_series_adapter import TimeSeriesAdapter


def _load(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _artifact_checksum(name: str, path: Path) -> str:
    if name == "data":
        return hashlib.sha256(path.read_bytes()).hexdigest()
    payload = (
        json.dumps(
            _load(path),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    return hashlib.sha256(payload).hexdigest()


def _manifest(output_dir: Path) -> dict[str, object]:
    try:
        return _load(output_dir / "run-manifest.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("baseline_bundle_invalid") from exc


def _verify_outputs(
    baseline_bundle: Path,
    manifest: dict[str, object],
) -> None:
    outputs = manifest.get("output_checksums")
    if not isinstance(outputs, dict):
        raise ValueError("baseline_bundle_invalid")
    for filename, expected in outputs.items():
        path = baseline_bundle / str(filename)
        if not path.is_file():
            raise ValueError("baseline_bundle_invalid")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("baseline_result_checksum_mismatch")


def verify_baseline_inputs(
    baseline_bundle: Path,
    input_paths: dict[str, Path],
    expected_checksums: dict[str, str],
) -> dict[str, object]:
    manifest = _manifest(baseline_bundle)
    recorded = manifest.get("input_checksums")
    if not isinstance(recorded, dict):
        raise ValueError("baseline_bundle_invalid")
    if set(input_paths) != set(expected_checksums) or set(recorded) != set(
        expected_checksums
    ):
        raise ValueError("baseline_input_missing")
    actual: dict[str, str] = {}
    for name, expected in expected_checksums.items():
        path = input_paths[name]
        if not path.is_file():
            raise ValueError("baseline_input_missing")
        actual[name] = _artifact_checksum(name, path)
        if actual[name] != expected or recorded.get(name) != expected:
            raise ValueError("baseline_input_checksum_mismatch")
    _verify_outputs(baseline_bundle, manifest)
    return {
        "valid": True,
        "request_id": manifest.get("request_id"),
        "input_checksums": actual,
    }


def _normalized_manifest(path: Path) -> dict[str, object]:
    document = _load(path)
    document.pop("generated_at", None)
    return document


def compare_exact_bundles(
    baseline: Path,
    rerun: Path,
) -> list[str]:
    baseline_files = {path.name for path in baseline.iterdir() if path.is_file()}
    rerun_files = {path.name for path in rerun.iterdir() if path.is_file()}
    if baseline_files != rerun_files:
        return ["bundle_file_set_mismatch"]
    issues: list[str] = []
    for filename in sorted(baseline_files):
        left = baseline / filename
        right = rerun / filename
        if filename == "run-manifest.json":
            equal = _normalized_manifest(left) == _normalized_manifest(right)
        else:
            equal = left.read_bytes() == right.read_bytes()
        if not equal:
            issues.append(f"exact_rerun_mismatch:{filename}")
    return issues


def _adapter_inputs(input_paths: dict[str, Path]) -> dict[str, Path]:
    result = {
        "research_plan": input_paths["research_plan"],
        "macro_result": input_paths["macro_data"],
        "data": input_paths["data"],
    }
    if "shock_artifact" in input_paths:
        result["shock_artifact"] = input_paths["shock_artifact"]
    return result


def exact_rerun(
    plan: AuditPlan,
    adapter: TimeSeriesAdapter,
    baseline_request_path: Path,
    input_paths: dict[str, Path],
    baseline_bundle: Path,
    output_dir: Path,
) -> dict[str, object]:
    adapter.validate_baseline(baseline_bundle)
    manifest = _manifest(baseline_bundle)
    expected = cast(dict[str, str], manifest["input_checksums"])
    report = verify_baseline_inputs(baseline_bundle, input_paths, expected)
    if report["request_id"] != plan.baseline_request_ref:
        raise ValueError("baseline_request_mismatch")
    try:
        result = adapter.execute(
            baseline_request_path,
            _adapter_inputs(input_paths),
            output_dir,
            timeout_seconds=float(plan.max_runtime_seconds),
        )
    except subprocess.TimeoutExpired as exc:
        error = exc.stderr or exc.output or str(exc)
        return {
            "check_id": next(
                item.check_id
                for item in plan.checks
                if item.check_family == "exact_rerun"
            ),
            "status": "failed",
            "issue_codes": ["exact_rerun_timeout"],
            "execution_error": str(error),
        }
    if result.returncode != 0:
        return {
            "check_id": next(
                item.check_id
                for item in plan.checks
                if item.check_family == "exact_rerun"
            ),
            "status": "failed",
            "issue_codes": ["exact_rerun_execution_failed"],
            "execution_error": result.stderr or result.stdout,
        }
    adapter.validate_result_bundle(output_dir)
    issues = compare_exact_bundles(baseline_bundle, output_dir)
    return {
        "check_id": next(
            item.check_id for item in plan.checks if item.check_family == "exact_rerun"
        ),
        "status": "passed" if not issues else "failed",
        "issue_codes": issues,
        "execution_error": None,
    }
