"""Aggregate check outcomes without upgrading the baseline claim."""

from __future__ import annotations

from typing import cast

from robustness_audit.identifiers import content_id


def _required_checks(
    plan: dict[str, object],
) -> tuple[set[str], str | None]:
    checks = cast(list[dict[str, object]], plan["checks"])
    required = {
        str(item["check_id"]) for item in checks if bool(item.get("required"))
    }
    exact = next(
        (
            str(item["check_id"])
            for item in checks
            if item.get("check_family") == "exact_rerun"
        ),
        None,
    )
    return required, exact


def _base_result(
    plan: dict[str, object],
    check_results: list[dict[str, object]],
    baseline_claim_eligibility: str,
) -> dict[str, object]:
    required, _ = _required_checks(plan)
    observed = {str(item["check_id"]) for item in check_results}
    return {
        "schema_version": "0.1.0",
        "audit_plan_ref": plan["audit_plan_id"],
        "baseline_request_ref": plan["baseline_request_ref"],
        "plan_timing": plan["plan_timing"],
        "claim_eligibility": baseline_claim_eligibility,
        "causal_language_allowed": baseline_claim_eligibility == "causal_candidate",
        "required_check_count": len(required),
        "completed_required_check_count": len(required & observed),
        "check_result_refs": [
            item["check_result_id"]
            for item in check_results
            if isinstance(item.get("check_result_id"), str)
        ],
        "warnings": (
            ["post-result audit is exploratory"]
            if plan["plan_timing"] == "post_result_exploratory"
            else []
        ),
    }


def _validate_check_results(
    plan: dict[str, object],
    check_results: list[dict[str, object]],
) -> None:
    planned = {
        str(item["check_id"])
        for item in cast(list[dict[str, object]], plan["checks"])
    }
    observed = [str(item["check_id"]) for item in check_results]
    if len(observed) != len(set(observed)):
        raise ValueError("duplicate_check_result")
    if set(observed) - planned:
        raise ValueError("unknown_check_result")


def _state(
    plan: dict[str, object],
    check_results: list[dict[str, object]],
) -> tuple[str, str, str, str]:
    required, exact = _required_checks(plan)
    by_id = {str(item["check_id"]): item for item in check_results}
    if exact is not None and exact in by_id and by_id[exact]["status"] != "passed":
        return "failed", "blocked", "not_assessed", "stop_ship"
    missing = required - by_id.keys()
    required_statuses = {
        str(by_id[check_id]["status"])
        for check_id in required
        if check_id in by_id
    }
    if missing or required_statuses & {"error", "failed", "blocked"}:
        return "partial", "blocked", "inconclusive", "stop_ship"
    all_statuses = {str(item["status"]) for item in check_results}
    if "sensitive" in all_statuses:
        return "success", "review_required", "sensitive", "review_required"
    if "inconclusive" in required_statuses:
        return "partial", "review_required", "inconclusive", "review_required"
    if required_statuses <= {"passed", "not_applicable"}:
        if plan["plan_timing"] == "pre_result_bound":
            return "success", "ready", "passed_declared_checks", "proceed_with_caveats"
        return (
            "success",
            "review_required",
            "passed_declared_checks",
            "review_required",
        )
    return "partial", "review_required", "inconclusive", "review_required"


def assess_audit(
    plan: dict[str, object],
    check_results: list[dict[str, object]],
    baseline_claim_eligibility: str,
) -> dict[str, object]:
    _validate_check_results(plan, check_results)
    document = _base_result(plan, check_results, baseline_claim_eligibility)
    execution, readiness, assessment, release = _state(plan, check_results)
    document.update(
        {
            "execution_status": execution,
            "audit_readiness": readiness,
            "assessment": assessment,
            "release_recommendation": release,
        }
    )
    document["audit_result_id"] = content_id(
        "ra-result",
        {
            "audit_plan_ref": plan["audit_plan_id"],
            "check_result_refs": document["check_result_refs"],
            "assessment": assessment,
        },
    )
    return document
