"""Compile predeclared checks without reading baseline result values."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from robustness_audit.contracts import validate_document
from robustness_audit.identifiers import (
    canonical_sha256,
    content_id,
    estimand_fingerprint,
)

FORBIDDEN_ESTIMAND_FIELDS = {
    "analysis_track",
    "claim_eligibility",
    "estimand_type",
    "exposure_variable_id",
    "horizons",
    "macro_data_bundle_refs",
    "outcome_variable_id",
    "output_unit",
    "shock_identification_artifact_ref",
}
RULES: dict[str, dict[str, object]] = {
    "exact_match_required": {
        "metric": "canonical_result_equality",
        "operator": "equal",
        "threshold": True,
    },
    "max_standardized_deviation_le_1_96": {
        "metric": "max_standardized_path_deviation",
        "operator": "less_than_or_equal",
        "threshold": 1.96,
    },
    "coefficient_delta_le_1e_12": {
        "metric": "coefficient_delta",
        "operator": "less_than_or_equal",
        "threshold": 1e-12,
    },
    "report_only": {
        "metric": "max_standardized_path_deviation",
        "operator": "report_only",
        "threshold": None,
    },
}


def _quarter_key(value: str) -> int:
    if len(value) != 6 or value[4] != "Q" or value[5] not in "1234":
        raise ValueError("invalid quarter")
    return int(value[:4]) * 4 + int(value[5])


def _valid_patch_value(field: str, value: object) -> bool:
    if field in {"lags", "hac_maxlags"}:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if field == "sample_policy":
        return value in {"common_sample", "horizon_specific"}
    if field == "control_variable_ids":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if field == "sample_window" and isinstance(value, dict):
        return set(value) == {"start", "end"} and all(
            isinstance(value.get(key), str) for key in ("start", "end")
        )
    return False


def _control_patch_attested(
    handoff: dict[str, object],
    patch: dict[str, object],
) -> bool:
    if "control_variable_ids" not in patch:
        return True
    checks = cast(list[dict[str, object]], handoff["declared_checks"])
    return any(
        cast(dict[str, object], candidate).get("control_variable_ids")
        == patch["control_variable_ids"]
        for check in checks
        for candidate in cast(list[object], check["patches"])
    )


def _window_within_baseline(
    baseline: dict[str, object],
    patch: dict[str, object],
) -> bool:
    if "sample_window" not in patch:
        return True
    try:
        base = cast(dict[str, str], baseline["sample_window"])
        window = cast(dict[str, str], patch["sample_window"])
        return (
            _quarter_key(base["start"])
            <= _quarter_key(window["start"])
            <= _quarter_key(window["end"])
            <= _quarter_key(base["end"])
        )
    except (KeyError, TypeError, ValueError):
        return False


def validate_patch(
    baseline_request: dict[str, object],
    patch: dict[str, object],
    capability: dict[str, object],
    handoff: dict[str, object],
) -> list[str]:
    fields = set(patch)
    if fields & FORBIDDEN_ESTIMAND_FIELDS:
        return ["forbidden_estimand_change"]
    supported = {str(item) for item in cast(list[object], capability["supported_patch_fields"])}
    if fields - supported:
        return ["patch_field_not_allowed"]
    if not _control_patch_attested(handoff, patch):
        return ["control_patch_not_attested"]
    if not _window_within_baseline(baseline_request, patch):
        return ["sample_window_out_of_coverage"]
    if any(not _valid_patch_value(field, value) for field, value in patch.items()):
        return ["invalid_patch_value"]
    return []


def _same_as_baseline(
    baseline: dict[str, object],
    patch: dict[str, object],
) -> bool:
    return all(baseline.get(field) == value for field, value in patch.items())


def _check_document(
    handoff_id: str,
    check: dict[str, object],
) -> dict[str, object]:
    family = str(check["check_family"])
    check_id = content_id(
        "ra-check",
        {"handoff_id": handoff_id, "check_family": family},
    )
    return {
        "check_id": check_id,
        "check_family": family,
        "required": bool(check["required"]),
        "same_estimand_required": True,
        "anchor_horizons": check["anchor_horizons"],
        "metrics": check["metrics"],
        "decision_rule_ids": check["decision_rules"],
        "failure_policy": "stop_ship" if family == "exact_rerun" else "review_required",
        "uses_randomness": False,
    }


def _materialize(
    handoff: dict[str, object],
    baseline: dict[str, object],
    capability: dict[str, object],
    checks: list[dict[str, object]],
) -> list[dict[str, object]]:
    handoff_checks = cast(list[dict[str, object]], handoff["declared_checks"])
    alternatives: list[dict[str, object]] = []
    for source, compiled in zip(handoff_checks, checks, strict=True):
        for value in cast(list[object], source["patches"]):
            patch = cast(dict[str, object], value)
            if not patch or _same_as_baseline(baseline, patch):
                continue
            issues = validate_patch(baseline, patch, capability, handoff)
            if issues:
                raise ValueError(",".join(issues))
            identity = {
                "baseline_request_id": baseline["request_id"],
                "patch": patch,
                "check_id": compiled["check_id"],
            }
            alternatives.append(
                {
                    "alternative_id": content_id("ra-alt", identity),
                    "check_id": compiled["check_id"],
                    "patch": patch,
                }
            )
    ids = [str(item["alternative_id"]) for item in alternatives]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_alternative")
    return alternatives


def _decision_rules(checks: list[dict[str, object]]) -> list[dict[str, object]]:
    ids = {
        str(rule_id)
        for check in checks
        for rule_id in cast(list[object], check["decision_rule_ids"])
    }
    return [{"rule_id": rule_id, **RULES[rule_id]} for rule_id in sorted(ids)]


def _validate_alternative_coverage(
    checks: list[dict[str, object]],
    alternatives: list[dict[str, object]],
) -> None:
    covered = {str(item["check_id"]) for item in alternatives}
    missing = [
        str(item["check_id"])
        for item in checks
        if item["check_family"] != "exact_rerun"
        and str(item["check_id"]) not in covered
    ]
    if missing:
        required = {
            str(item["check_id"])
            for item in checks
            if item["required"] is True
        }
        issue = (
            "required_check_has_no_alternative"
            if required.intersection(missing)
            else "check_has_no_alternative"
        )
        raise ValueError(issue)


def _validate_bindings(
    audit_request: dict[str, object],
    handoff: dict[str, object],
    baseline: dict[str, object],
    capability: dict[str, object],
) -> str:
    if audit_request["robustness_handoff_ref"] != handoff["handoff_id"]:
        raise ValueError("robustness_handoff_reference_mismatch")
    identity_payload = {
        key: value
        for key, value in handoff.items()
        if key not in {"handoff_id", "checksum"}
    }
    expected_id = f"rd-robustness-{canonical_sha256(identity_payload)[:32]}"
    if handoff["handoff_id"] != expected_id:
        raise ValueError("robustness_handoff_id_mismatch")
    if audit_request["baseline_request_ref"] != baseline["request_id"]:
        raise ValueError("baseline_request_reference_mismatch")
    if baseline["claim_eligibility"] != handoff["claim_eligibility"]:
        raise ValueError("claim_eligibility_mismatch")
    expected = str(handoff["checksum"])
    payload = {key: value for key, value in handoff.items() if key != "checksum"}
    if expected != f"sha256:{canonical_sha256(payload)}":
        raise ValueError("robustness_handoff_checksum_mismatch")
    fields = tuple(str(item) for item in cast(list[object], capability["estimand_fields"]))
    fingerprint = estimand_fingerprint(baseline, fields)
    if fingerprint != handoff["estimand_fingerprint"]:
        raise ValueError("estimand_fingerprint_mismatch")
    return fingerprint


def compile_audit_plan(
    audit_request: dict[str, object],
    handoff: dict[str, object],
    baseline_request: dict[str, object],
    adapter_capability: dict[str, object],
) -> dict[str, object]:
    validate_document("audit_request", audit_request)
    validate_document("adapter_capability", adapter_capability)
    fingerprint = _validate_bindings(
        audit_request,
        handoff,
        baseline_request,
        adapter_capability,
    )
    checks = [
        _check_document(str(handoff["handoff_id"]), check)
        for check in cast(list[dict[str, object]], handoff["declared_checks"])
    ]
    alternatives = _materialize(
        handoff,
        baseline_request,
        adapter_capability,
        checks,
    )
    _validate_alternative_coverage(checks, alternatives)
    payload: dict[str, object] = {
        "schema_version": "0.1.0",
        "audit_request_id": audit_request["audit_request_id"],
        "adapter_id": adapter_capability["adapter_id"],
        "adapter_contract_version": adapter_capability["adapter_version"],
        "baseline_request_ref": baseline_request["request_id"],
        "baseline_bundle_ref": audit_request["baseline_bundle_ref"],
        "baseline_estimand_fingerprint": fingerprint,
        "analysis_track": baseline_request["analysis_track"],
        "claim_eligibility": baseline_request["claim_eligibility"],
        "plan_timing": "post_result_exploratory",
        "pre_result_binding": None,
        "checks": checks,
        "alternatives": alternatives,
        "decision_rules": _decision_rules(checks),
        "execution_budget": {
            "max_variants": len(alternatives) + 1,
            "max_runtime_seconds": 600,
            "max_parallel_jobs": 1,
        },
        "randomness": {"required": False, "seed": None},
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "provenance": {"complete": True, "source": "research-design-handoff"},
    }
    payload["audit_plan_id"] = content_id("ra-plan", payload)
    payload["checksum"] = f"sha256:{canonical_sha256(payload)}"
    validate_document("audit_plan", payload)
    return payload
