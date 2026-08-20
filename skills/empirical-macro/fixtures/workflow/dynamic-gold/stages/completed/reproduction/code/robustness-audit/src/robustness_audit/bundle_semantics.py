"""Cross-document semantic validation for published audit bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from robustness_audit.assessment import assess_audit
from robustness_audit.identifiers import canonical_sha256, content_id
from robustness_audit.reporting import plain_language_summary


def _load(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("JSON document must be an object")
    return cast(dict[str, object], document)


def _without_runtime_fields(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_runtime_fields(item)
            for key, item in value.items()
            if key
            not in {
                "duration_seconds",
                "execution_error",
                "stderr",
                "stdout",
            }
        }
    if isinstance(value, list):
        return [_without_runtime_fields(item) for item in value]
    return value


def plan_checksum_errors(output_dir: Path) -> list[str]:
    try:
        plan = _load(output_dir / "audit-plan.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    payload = {key: value for key, value in plan.items() if key != "checksum"}
    expected = f"sha256:{canonical_sha256(payload)}"
    return (
        []
        if plan.get("checksum") == expected
        else ["audit_plan_checksum_mismatch"]
    )


def semantic_errors(output_dir: Path) -> list[str]:
    try:
        plan = _load(output_dir / "audit-plan.json")
        result = _load(output_dir / "audit-result.json")
        raw_checks = json.loads(
            (output_dir / "check-results.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(raw_checks, list) or any(
        not isinstance(item, dict) for item in raw_checks
    ):
        return []
    checks = cast(list[dict[str, object]], raw_checks)
    errors: list[str] = []
    for check in checks:
        payload = {
            key: value
            for key, value in check.items()
            if key != "check_result_id"
        }
        if check.get("check_result_id") != content_id(
            "ra-check-result",
            _without_runtime_fields(payload),
        ):
            errors.append("check_result_identity_mismatch")
            break
    if result.get("claim_eligibility") != plan.get("claim_eligibility"):
        errors.append("claim_eligibility_mismatch")
    try:
        expected = assess_audit(plan, checks, str(plan["claim_eligibility"]))
    except (KeyError, TypeError, ValueError):
        return [*errors, "assessment_validation_error"]
    state_fields = {
        "execution_status",
        "audit_readiness",
        "assessment",
        "release_recommendation",
        "causal_language_allowed",
        "required_check_count",
        "completed_required_check_count",
        "check_result_refs",
        "warnings",
    }
    if any(result.get(field) != expected.get(field) for field in state_fields):
        errors.append("assessment_mismatch")
    if result.get("audit_result_id") != expected.get("audit_result_id"):
        errors.append("audit_result_identity_mismatch")
    return errors


def planned_alternative_errors(output_dir: Path) -> list[str]:
    try:
        plan = _load(output_dir / "audit-plan.json")
        alternatives = cast(list[dict[str, object]], plan["alternatives"])
        raw_checks = json.loads(
            (output_dir / "check-results.json").read_text(encoding="utf-8")
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(raw_checks, list):
        return []
    planned = {
        str(item["alternative_id"]) for item in alternatives
    }
    root = output_dir / "alternative-bundles"
    observed = {item.name for item in root.iterdir() if item.is_dir()}
    exact_status = next(
        (
            str(check.get("status"))
            for check in raw_checks
            if isinstance(check, dict)
            and check.get("check_family") == "exact_rerun"
        ),
        None,
    )
    if (
        ("exact-rerun" not in observed and exact_status == "passed")
        or observed - {"exact-rerun"} - planned
    ):
        return ["planned_alternative_set_mismatch"]
    statuses = {
        str(record["alternative_id"]): str(record["status"])
        for check in raw_checks
        if isinstance(check, dict)
        for record in cast(
            list[dict[str, object]],
            cast(dict[str, object], check.get("metrics", {})).get(
                "execution_records",
                [],
            ),
        )
    }
    missing = planned - (observed - {"exact-rerun"})
    if any(statuses.get(item) == "success" for item in missing):
        return ["planned_alternative_set_mismatch"]
    if any(item not in statuses for item in missing):
        return ["planned_alternative_set_mismatch"]
    return []


def summary_errors(output_dir: Path) -> list[str]:
    try:
        result = _load(output_dir / "audit-result.json")
        raw_checks = json.loads(
            (output_dir / "check-results.json").read_text(encoding="utf-8")
        )
        if not isinstance(raw_checks, list) or any(
            not isinstance(item, dict) for item in raw_checks
        ):
            return []
        checks = cast(list[dict[str, object]], raw_checks)
        expected = plain_language_summary(result, checks)
        observed = (output_dir / "plain-language-summary.md").read_text(
            encoding="utf-8"
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return []
    return [] if observed == expected else ["plain_summary_mismatch"]
