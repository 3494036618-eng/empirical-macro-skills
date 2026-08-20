"""Classify research readiness and assemble the evaluation contract."""

from __future__ import annotations

from typing import Any

_ALWAYS_BLOCKING = {
    "as_of_required",
    "concept_definition_mapping_unresolved",
    "currency_mismatch",
    "definition_mismatch",
    "definition_unknown",
    "entity_mapping_conflict",
    "indicator_ambiguity",
    "license_unresolved",
    "price_basis_conflict",
    "price_basis_mismatch",
    "release_date_required",
    "seasonal_adjustment_conflict",
    "seasonal_adjustment_mismatch",
    "unit_conflict",
    "unit_mismatch",
    "vintage_required",
}


def readiness_status(
    request: dict[str, Any],
    issue_codes: set[str],
    coverage: dict[str, Any],
) -> dict[str, Any]:
    blocking = issue_codes & _ALWAYS_BLOCKING
    if request["research_use"] in {"panel_analysis", "forecasting", "real_time"}:
        blocking.update(issue_codes & {"unit_unknown"})

    execution_status = "success" if coverage["complete"] else "partial"
    if request["release_or_vintage"]["mode"] in {"as_of", "specific_vintage"} and blocking & {
        "release_date_required",
        "vintage_required",
    }:
        execution_status = "failed"
    if blocking:
        research_readiness = "blocked"
        delivery_eligibility = "not_deliverable"
    elif issue_codes:
        research_readiness = "review_required"
        delivery_eligibility = "comparison_only"
    else:
        research_readiness = "ready"
        delivery_eligibility = "analysis_ready"
    return {
        "execution_status": execution_status,
        "research_readiness": research_readiness,
        "delivery_eligibility": delivery_eligibility,
        "eligible_for_estimation": delivery_eligibility == "analysis_ready",
        "review_required": delivery_eligibility != "analysis_ready",
    }


def failed_result(
    *,
    requested_scope: set[str],
    research_use: str,
    issue: str,
    execution: dict[str, Any],
    parsed: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider": parsed.get("provider", "datapro"),
        "research_use": research_use,
        "execution_status": "failed",
        "research_readiness": "blocked",
        "delivery_eligibility": "not_deliverable",
        "eligible_for_estimation": False,
        "review_required": True,
        "selected_items": [],
        "filtered_candidates": [],
        "issue_codes": [issue],
        "source_coverage": {
            "complete": False,
            "scope_reduced": False,
            "requested_count": len(requested_scope),
            "delivered_count": 0,
            "failures": sorted(requested_scope),
        },
        "execution": execution,
        "transformations": parsed.get("transformations", []),
        "raw_response": parsed["raw_response"],
        "fixture_provenance": parsed["fixture_provenance"],
    }


def no_match_result(
    *,
    provider: str,
    research_use: str,
    filtered: list[dict[str, Any]],
    issue_codes: set[str],
    coverage: dict[str, Any],
    execution: dict[str, Any],
    parsed: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider": provider,
        "research_use": research_use,
        "execution_status": "partial",
        "research_readiness": "review_required",
        "delivery_eligibility": "not_deliverable",
        "eligible_for_estimation": False,
        "review_required": True,
        "selected_items": [],
        "filtered_candidates": filtered,
        "issue_codes": sorted(issue_codes or {"no_matching_candidate"}),
        "source_coverage": coverage,
        "execution": execution,
        "transformations": parsed.get("transformations", []),
        "raw_response": parsed["raw_response"],
        "fixture_provenance": parsed["fixture_provenance"],
    }


def evaluated_result(
    *,
    provider: str,
    research_use: str,
    selected: list[dict[str, Any]],
    filtered: list[dict[str, Any]],
    issue_codes: set[str],
    coverage: dict[str, Any],
    execution: dict[str, Any],
    parsed: dict[str, Any],
    status: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider": provider,
        "research_use": research_use,
        **status,
        "selected_items": selected,
        "filtered_candidates": filtered,
        "issue_codes": sorted(issue_codes),
        "source_coverage": coverage,
        "execution": execution,
        "transformations": parsed.get("transformations", []),
        "raw_response": parsed["raw_response"],
        "fixture_provenance": parsed["fixture_provenance"],
    }
