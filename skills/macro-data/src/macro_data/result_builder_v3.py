"""Build the 0.3 completion result document."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from macro_data.completion_assembler import CompletionResult
from macro_data.contracts import validate_document


def build_result_v3(
    *,
    request: dict[str, Any],
    result: CompletionResult,
    checksums: dict[str, str],
    raw_artifacts: list[dict[str, str]],
) -> dict[str, Any]:
    """Build and validate the public 0.3 result summary."""
    complete = (
        result.residual_gap_count == 0
        and result.conflict_count == 0
        and len(result.observations) == len(result.matrix.cells)
    )
    execution_status = "success" if complete else (
        "partial" if result.observations else "failed"
    )
    document = {
        "schema_version": "0.3.0-beta",
        "research_use": request["research_use"],
        "request_manifest": {
            "path": "request_manifest.json",
            "sha256": checksums["request_manifest.json"],
        },
        "series": [],
        "raw_artifacts": raw_artifacts,
        "normalized_artifacts": [
            {"path": name, "sha256": checksums[name]}
            for name in ("data.csv", "data.parquet")
        ],
        "transformations": [],
        "missingness": {
            "missing_count": result.residual_gap_count,
        },
        "provenance": {
            "complete": complete,
            "unresolved_links": 0 if complete else result.residual_gap_count,
        },
        "evidence_references": [],
        "execution_status": execution_status,
        "research_readiness": "ready" if complete else "blocked",
        "delivery_eligibility": (
            "analysis_ready" if complete else "not_deliverable"
        ),
        "eligible_for_estimation": complete,
        "source_coverage": {
            "complete": complete,
            "scope_reduced": False,
            "requested_count": len(result.matrix.cells),
            "delivered_count": len(result.observations),
            "failures": [] if complete else ["expected_observation_matrix_incomplete"],
        },
        "expected_observation_count": len(result.matrix.cells),
        "final_estimator_observation_count": len(result.observations),
        "provider_contribution": asdict(result.contribution),
        "completion_status": "complete" if complete else "blocked",
        "residual_gap_count": result.residual_gap_count,
        "conflict_count": result.conflict_count,
        "completion_manifest_ref": "completion_manifest.json",
        "warnings": list(result.issue_codes),
        "review_required": not complete,
    }
    validate_document("result", document)
    return document
