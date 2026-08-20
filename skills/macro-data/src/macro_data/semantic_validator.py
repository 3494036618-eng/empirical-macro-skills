"""Orchestrate deterministic research-readiness checks."""

from __future__ import annotations

from itertools import product
from typing import Any

from macro_data.metadata_gate import metadata_issues
from macro_data.semantic_conflicts import conflict_issues
from macro_data.semantic_constraints import request_constraint_issues
from macro_data.semantic_coverage import build_coverage
from macro_data.semantic_identity import select_candidates
from macro_data.semantic_readiness import (
    evaluated_result,
    failed_result,
    no_match_result,
    readiness_status,
)


def _semantic_issues(
    request: dict[str, Any],
    selected: list[dict[str, Any]],
) -> set[str]:
    issues: set[str] = set()
    requested_frequency = request["frequency"]
    if any(item.get("observed_frequency") != requested_frequency for item in selected):
        issues.add("frequency_mismatch")
    if any(item["p_date"]["semantics"] == "unresolved" for item in selected):
        issues.add("p_date_semantics_unresolved")
    issues.update(metadata_issues(request, selected))
    issues.update(request_constraint_issues(request, selected))
    return issues


def _requested_pairs(
    request: dict[str, Any],
) -> set[tuple[str, str]]:
    return set(
        product(
            (item["name_or_code"] for item in request["entities"]),
            (item["name_or_code"] for item in request["indicators"]),
        )
    )


def _as_of(request: dict[str, Any]) -> str | None:
    vintage = request["release_or_vintage"]
    if vintage["mode"] in {"as_of", "specific_vintage"}:
        value = vintage.get("value")
        return value if isinstance(value, str) else None
    return None


def evaluate_candidates(
    request: dict[str, Any],
    parsed: dict[str, Any],
) -> dict[str, Any]:
    provider = parsed.get("provider", "datapro")
    execution = parsed["execution"]
    candidates = parsed["candidates"]
    research_use = request["research_use"]
    requested_pairs = _requested_pairs(request)
    entities = {entity for entity, _ in requested_pairs}
    indicators = {indicator for _, indicator in requested_pairs}
    requested_scope = {f"{entity}|{indicator}" for entity, indicator in requested_pairs}

    if execution.get("provider_code") != 0:
        return failed_result(
            requested_scope=requested_scope,
            research_use=research_use,
            issue="provider_error",
            execution=execution,
            parsed=parsed,
        )
    if not candidates:
        return failed_result(
            requested_scope=requested_scope,
            research_use=research_use,
            issue="empty_result",
            execution=execution,
            parsed=parsed,
        )

    start = request["time_range"]["start"].replace("-Q", "Q")
    end = request["time_range"]["end"].replace("-Q", "Q")
    selected, filtered, issue_codes = select_candidates(
        candidates,
        entities=entities,
        indicators=indicators,
        constraints=request.get("native_source_constraints") or [],
        start=start,
        end=end,
        requested_frequency=request["frequency"],
        as_of=_as_of(request),
    )
    coverage, coverage_incomplete = build_coverage(
        requested_pairs,
        selected,
        start=start,
        end=end,
        frequency=request["frequency"],
    )
    if not selected:
        return no_match_result(
            provider=provider,
            research_use=research_use,
            filtered=filtered,
            issue_codes=issue_codes,
            coverage=coverage,
            execution=execution,
            parsed=parsed,
        )

    issue_codes.update(_semantic_issues(request, selected))
    issue_codes.update(conflict_issues(selected))
    if coverage_incomplete:
        issue_codes.add("time_coverage_incomplete")
    status = readiness_status(request, issue_codes, coverage)
    return evaluated_result(
        provider=provider,
        research_use=research_use,
        selected=selected,
        filtered=filtered,
        issue_codes=issue_codes,
        coverage=coverage,
        execution=execution,
        parsed=parsed,
        status=status,
    )
