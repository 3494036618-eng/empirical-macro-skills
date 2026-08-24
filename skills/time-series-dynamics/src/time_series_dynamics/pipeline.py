"""End-to-end dynamic-analysis pipeline."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from time_series_dynamics.artifact_validation import validate_handoff
from time_series_dynamics.canonical_loader import load_canonical_time_series
from time_series_dynamics.claim_policy import claim_policy
from time_series_dynamics.contracts import validate_document
from time_series_dynamics.exporter import (
    build_manifest,
    publish_directory,
    sha256_document,
    sha256_file,
    validate_bundle,
    write_csv,
    write_json,
)
from time_series_dynamics.horizon_regression import estimate_path
from time_series_dynamics.models import DynamicsRequest, HorizonEstimate
from time_series_dynamics.plotting import write_dynamic_path
from time_series_dynamics.reporting import plain_language_summary, technical_summary
from time_series_dynamics.result_builder import build_result
from time_series_dynamics.source_loader import load_jel_example5, verify_file_checksum


def _diagnostics(
    request: DynamicsRequest,
    estimates: tuple[HorizonEstimate, ...],
    original_nobs: int,
) -> dict[str, object]:
    minimum_nobs = min(item.nobs for item in estimates)
    lead_loss = max(request.horizons)
    lag_loss = max(1, request.lags)
    missing_loss = max(0, original_nobs - lead_loss - lag_loss - minimum_nobs)
    columns = 2 + len(request.control_variable_ids) * request.lags
    warnings = (
        ["effective sample varies by horizon"]
        if request.sample_policy == "horizon_specific"
        else []
    )
    return {
        "schema_version": "0.1.0",
        "request_id": request.request_id,
        "sample_alignment": {
            "start": request.sample_start,
            "end": request.sample_end,
            "original_nobs": original_nobs,
            "common_nobs": minimum_nobs,
            "dropped_for_lags": lag_loss,
            "dropped_for_leads": lead_loss,
            "dropped_for_missing": missing_loss,
        },
        "design_matrix": {"columns": columns, "rank": columns},
        "covariance": {
            "type": "HAC",
            "kernel": "bartlett",
            "maxlags": request.hac_maxlags,
        },
        "warnings": warnings,
    }


def _write_staging_bundle(
    staging: Path,
    request_document: dict[str, object],
    request: DynamicsRequest,
    result: dict[str, object],
    diagnostics: dict[str, object],
    estimates: tuple[HorizonEstimate, ...],
    input_checksums: dict[str, str],
    source_label: str,
    source_checksum: str,
) -> None:
    policy = claim_policy(request.analysis_track)
    write_json(staging / "request.json", request_document, "request")
    write_json(staging / "result.json", result, "result")
    write_json(staging / "diagnostics.json", diagnostics, "diagnostics")
    write_csv(staging / "dynamic-path.csv", estimates)
    (staging / "technical-summary.md").write_text(
        technical_summary(request, estimates, source_label, source_checksum),
        encoding="utf-8",
    )
    (staging / "plain-language-summary.md").write_text(
        plain_language_summary(request, estimates, policy),
        encoding="utf-8",
    )
    write_dynamic_path(staging / "dynamic-path.png", request, estimates, policy)
    manifest = build_manifest(staging, request.request_id, input_checksums)
    write_json(staging / "run-manifest.json", manifest, "run_manifest")


def _input_checksums(
    request: dict[str, object],
    research_plan: dict[str, object],
    macro_result: dict[str, object],
    data_path: Path,
    shock_artifact: dict[str, object] | None,
) -> dict[str, str]:
    checksums = {
        "data": sha256_file(data_path),
        "request": sha256_document(request),
        "research_plan": sha256_document(research_plan),
        "macro_data": sha256_document(macro_result),
    }
    if shock_artifact is not None:
        checksums["shock_artifact"] = sha256_document(shock_artifact)
    return checksums


def run_time_series_dynamics(
    request: dict[str, object],
    research_plan: dict[str, object],
    macro_results: list[dict[str, object]],
    data_path: Path,
    output_dir: Path,
    shock_artifact: dict[str, object] | None = None,
) -> dict[str, object]:
    issues = validate_handoff(
        request,
        research_plan,
        macro_results,
        shock_artifact,
    )
    if issues:
        raise ValueError(",".join(issues))
    validate_document("request", request)
    parsed = DynamicsRequest.from_document(request)
    verify_file_checksum(
        data_path,
        str(macro_results[0]["source_checksum"]),
    )
    if parsed.data_profile == "precomputed_columns":
        frame = load_jel_example5(
            data_path,
            start=parsed.sample_start,
            end=parsed.sample_end,
        )
    elif parsed.data_profile == "canonical_long_table":
        frame = load_canonical_time_series(data_path, parsed)
    else:
        raise ValueError(f"unsupported_data_profile:{parsed.data_profile}")
    estimates = estimate_path(frame, parsed)
    result = build_result(parsed, estimates)
    diagnostics = _diagnostics(parsed, estimates, len(frame))
    validate_document("diagnostics", diagnostics)
    source_label = (
        str(shock_artifact.get("source_title"))
        if shock_artifact is not None
        else "validated macro-data dynamic_response Artifact"
    )
    input_checksums = _input_checksums(
        request,
        research_plan,
        macro_results[0],
        data_path,
        shock_artifact,
    )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        _write_staging_bundle(
            staging,
            request,
            parsed,
            result,
            diagnostics,
            estimates,
            input_checksums,
            source_label,
            str(macro_results[0]["source_checksum"]),
        )
        validation = validate_bundle(staging)
        if validation["valid"] is not True:
            raise ValueError(f"bundle validation failed: {validation['errors']}")
        publish_directory(staging, output_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {
        "result_id": result["result_id"],
        "analysis_track": parsed.analysis_track,
        "output_dir": str(output_dir),
    }
