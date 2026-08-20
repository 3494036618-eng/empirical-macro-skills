"""Aggregate raw executions into one structured result per declared check."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from robustness_audit.comparison import compare_paths
from robustness_audit.contracts import validate_document
from robustness_audit.identifiers import content_id


def _load_result(bundle: Path) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((bundle / "result.json").read_text(encoding="utf-8")),
    )


def _rules(plan: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        str(item["rule_id"]): item
        for item in cast(list[dict[str, object]], plan["decision_rules"])
    }


def _observed(metric: str, metrics: dict[str, object]) -> object:
    if metric == "coefficient_delta":
        return metrics.get("max_coefficient_delta")
    return metrics.get(metric)


def _apply_rules(
    rule_ids: list[object],
    metrics: dict[str, object],
    rules: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for value in rule_ids:
        rule_id = str(value)
        rule = rules[rule_id]
        observed = _observed(str(rule["metric"]), metrics)
        operator = str(rule["operator"])
        if operator == "report_only":
            passed: bool | None = None
        elif operator == "equal":
            passed = observed == rule["threshold"]
        else:
            passed = float(cast(float, observed)) <= float(
                cast(float, rule["threshold"])
            )
        results.append(
            {"rule_id": rule_id, "passed": passed, "observed": observed}
        )
    return results


def _threat_refs(
    handoff: dict[str, object],
    family: str,
) -> list[str]:
    checks = cast(list[dict[str, object]], handoff["declared_checks"])
    source = next(item for item in checks if item["check_family"] == family)
    return [str(item) for item in cast(list[object], source["threat_refs"])]


def _base_check(
    plan_check: dict[str, object],
    plan: dict[str, object],
    handoff: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "check_id": plan_check["check_id"],
        "check_family": plan_check["check_family"],
        "required": plan_check["required"],
        "baseline_request_ref": plan["baseline_request_ref"],
        "alternative_request_ref": None,
        "alternative_result_ref": None,
        "same_estimand": True,
        "threat_refs": _threat_refs(handoff, str(plan_check["check_family"])),
        "threat_updates": [],
        "input_checksums": {},
        "output_checksums": {},
    }


def _exact_result(
    plan_check: dict[str, object],
    plan: dict[str, object],
    handoff: dict[str, object],
    exact_record: dict[str, object],
) -> dict[str, object]:
    document = _base_check(plan_check, plan, handoff)
    passed = exact_record["status"] == "passed"
    document.update(
        {
            "status": "passed" if passed else "failed",
            "changed_fields": [],
            "execution_error": exact_record.get("execution_error"),
            "metrics": {"canonical_result_equality": passed},
            "rule_results": [
                {
                    "rule_id": "exact_match_required",
                    "passed": passed,
                    "observed": passed,
                }
            ],
            "warnings": list(cast(list[str], exact_record["issue_codes"])),
            "evidence_refs": ["alternative-bundles/exact-rerun"],
        }
    )
    document["check_result_id"] = _check_result_id(document)
    validate_document("check_result", document)
    return document


def _comparison_rows(
    alternative_id: str,
    check_id: str,
    baseline: dict[str, object],
    alternative: dict[str, object],
) -> list[dict[str, object]]:
    base_rows = cast(list[dict[str, object]], baseline["horizon_results"])
    alt_rows = cast(list[dict[str, object]], alternative["horizon_results"])
    return [
        {
            "alternative_id": alternative_id,
            "check_id": check_id,
            "horizon": base["horizon"],
            "baseline_estimate": base["estimate"],
            "alternative_estimate": alt["estimate"],
            "estimate_delta": float(cast(float, alt["estimate"]))
            - float(cast(float, base["estimate"])),
            "baseline_standard_error": base["standard_error"],
            "alternative_standard_error": alt["standard_error"],
            "baseline_nobs": base["nobs"],
            "alternative_nobs": alt["nobs"],
        }
        for base, alt in zip(base_rows, alt_rows, strict=True)
    ]


def _aggregate_metrics(items: list[dict[str, object]]) -> dict[str, object]:
    return {
        "alternatives": items,
        "max_standardized_path_deviation": max(
            (
                float(cast(float, item["max_standardized_path_deviation"]))
                for item in items
            ),
            default=0.0,
        ),
        "max_coefficient_delta": max(
            (float(cast(float, item["max_coefficient_delta"])) for item in items),
            default=0.0,
        ),
        "anchor_sign_changes": sum(
            int(cast(int, item["anchor_sign_changes"])) for item in items
        ),
    }


def _execution_evidence(
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    fields = (
        "alternative_id",
        "check_id",
        "patch",
        "request",
        "request_id",
        "returncode",
        "stdout",
        "stderr",
        "duration_seconds",
        "status",
        "issue_codes",
        "execution_error",
        "result_id",
    )
    return [
        {field: record[field] for field in fields if field in record}
        for record in records
    ]


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


def _check_result_id(document: dict[str, object]) -> str:
    return content_id(
        "ra-check-result",
        _without_runtime_fields(document),
    )


def _derived_result(
    plan_check: dict[str, object],
    plan: dict[str, object],
    handoff: dict[str, object],
    baseline: dict[str, object],
    records: list[dict[str, object]],
    rules: dict[str, dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    document = _base_check(plan_check, plan, handoff)
    errors = [item for item in records if item["status"] != "success"]
    comparisons: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    evidence: list[str] = []
    for record in records:
        if record["status"] != "success":
            continue
        alternative = _load_result(Path(str(record["bundle_path"])))
        metrics = compare_paths(
            baseline,
            alternative,
            epsilon=1e-12,
            anchor_horizons=tuple(
                int(item)
                for item in cast(list[int], plan_check["anchor_horizons"])
            ),
        )
        comparisons.append(
            {"alternative_id": record["alternative_id"], **metrics}
        )
        rows.extend(
            _comparison_rows(
                str(record["alternative_id"]),
                str(plan_check["check_id"]),
                baseline,
                alternative,
            )
        )
        evidence.append(str(alternative["result_id"]))
    metrics = _aggregate_metrics(comparisons)
    metrics["execution_records"] = _execution_evidence(records)
    rule_results = _apply_rules(
        cast(list[object], plan_check["decision_rule_ids"]),
        metrics,
        rules,
    )
    if errors:
        status = "error"
    elif any(item["passed"] is False for item in rule_results):
        status = "sensitive"
    else:
        status = "passed"
    document.update(
        {
            "status": status,
            "changed_fields": sorted(
                {
                    str(field)
                    for record in records
                    for field in cast(dict[str, object], record["patch"])
                }
            ),
            "execution_error": (
                "; ".join(str(item["execution_error"]) for item in errors)
                if errors
                else None
            ),
            "metrics": metrics,
            "rule_results": rule_results,
            "warnings": [
                str(issue)
                for item in errors
                for issue in cast(list[object], item["issue_codes"])
            ],
            "evidence_refs": evidence,
        }
    )
    document["check_result_id"] = _check_result_id(document)
    validate_document("check_result", document)
    return document, rows


def build_check_results(
    plan: dict[str, object],
    handoff: dict[str, object],
    baseline: dict[str, object],
    exact_record: dict[str, object],
    execution_records: tuple[dict[str, object], ...],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    alternatives = cast(list[dict[str, object]], plan["alternatives"])
    planned = [str(item["alternative_id"]) for item in alternatives]
    observed = [str(item["alternative_id"]) for item in execution_records]
    if planned != observed:
        raise ValueError("alternative_set_mismatch")
    checks = cast(list[dict[str, object]], plan["checks"])
    rules = _rules(plan)
    results: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    for check in checks:
        family = str(check["check_family"])
        if family == "exact_rerun":
            results.append(_exact_result(check, plan, handoff, exact_record))
            continue
        matching = [
            record
            for record in execution_records
            if record["check_id"] == check["check_id"]
        ]
        result, current_rows = _derived_result(
            check,
            plan,
            handoff,
            baseline,
            matching,
            rules,
        )
        results.append(result)
        rows.extend(current_rows)
    return results, rows
