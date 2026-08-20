"""JSON Schema loading plus cross-field semantic validation."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

SCHEMA_FILES = {
    "adapter_capability": "adapter-capability.schema.json",
    "audit_request": "robustness-audit-request.schema.json",
    "audit_plan": "robustness-audit-plan.schema.json",
    "check_result": "robustness-check-result.schema.json",
    "audit_result": "robustness-audit-result.schema.json",
    "run_manifest": "robustness-run-manifest.schema.json",
}
SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas"


@lru_cache(maxsize=len(SCHEMA_FILES))
def load_schema(contract: str) -> dict[str, object]:
    filename = SCHEMA_FILES.get(contract)
    if filename is None:
        raise KeyError(f"unsupported contract: {contract}")
    document = cast(
        dict[str, object],
        json.loads((SCHEMA_ROOT / filename).read_text(encoding="utf-8")),
    )
    Draft202012Validator.check_schema(document)
    return document


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _plan_semantic_errors(document: dict[str, object]) -> list[tuple[str, str]]:
    checks = cast(list[dict[str, object]], document["checks"])
    alternatives = cast(list[dict[str, object]], document["alternatives"])
    rules = cast(list[dict[str, object]], document["decision_rules"])
    errors: list[tuple[str, str]] = []
    check_ids = [str(item["check_id"]) for item in checks]
    alternative_ids = [str(item["alternative_id"]) for item in alternatives]
    rule_ids = [str(item["rule_id"]) for item in rules]
    if duplicates := _duplicates(check_ids):
        errors.append(("/checks", f"duplicate check_id: {sorted(duplicates)[0]}"))
    if duplicates := _duplicates(alternative_ids):
        errors.append(
            ("/alternatives", f"duplicate alternative_id: {sorted(duplicates)[0]}")
        )
    if duplicates := _duplicates(rule_ids):
        errors.append(
            ("/decision_rules", f"duplicate rule_id: {sorted(duplicates)[0]}")
        )
    if any(str(item["check_id"]) not in check_ids for item in alternatives):
        errors.append(("/alternatives", "alternative references unknown check_id"))
    covered = {str(item["check_id"]) for item in alternatives}
    uncovered = [
        str(item["check_id"])
        for item in checks
        if item["check_family"] != "exact_rerun"
        and str(item["check_id"]) not in covered
    ]
    if uncovered:
        errors.append(
            (
                "/alternatives",
                f"non-exact check has no alternative: {uncovered[0]}",
            )
        )
    known_rules = set(rule_ids)
    if any(
        not {
            str(value)
            for value in cast(list[object], item["decision_rule_ids"])
        }.issubset(known_rules)
        for item in checks
    ):
        errors.append(("/checks", "check references unknown decision rule"))
    random_required = any(bool(item["uses_randomness"]) for item in checks)
    randomness = cast(dict[str, object], document["randomness"])
    if random_required and (
        randomness.get("required") is not True
        or not isinstance(randomness.get("seed"), int)
    ):
        errors.append(("/randomness", "random checks require an integer seed"))
    return errors


def _result_semantic_errors(document: dict[str, object]) -> list[tuple[str, str]]:
    required = int(cast(int, document["required_check_count"]))
    completed = int(cast(int, document["completed_required_check_count"]))
    errors: list[tuple[str, str]] = []
    if completed > required:
        errors.append(
            (
                "/completed_required_check_count",
                "completed required checks cannot exceed required checks",
            )
        )
    if document["assessment"] == "passed_declared_checks" and completed != required:
        errors.append(
            (
                "/assessment",
                "passed_declared_checks requires every required check",
            )
        )
    return errors


def _semantic_errors(
    contract: str,
    document: dict[str, object],
) -> list[tuple[str, str]]:
    if contract == "audit_plan":
        return _plan_semantic_errors(document)
    if contract == "audit_result":
        return _result_semantic_errors(document)
    return []


def validation_errors(
    contract: str,
    document: dict[str, object],
) -> list[dict[str, str]]:
    validator = Draft202012Validator(
        load_schema(contract),
        format_checker=FormatChecker(),
    )
    schema_errors = sorted(
        validator.iter_errors(document),
        key=lambda item: list(item.absolute_path),
    )
    errors = [
        {
            "path": "/" + "/".join(str(part) for part in error.absolute_path),
            "message": error.message,
        }
        for error in schema_errors
    ]
    errors.extend(
        {"path": path, "message": message}
        for path, message in _semantic_errors(contract, document)
    )
    return errors


def validate_document(contract: str, document: dict[str, object]) -> None:
    errors = validation_errors(contract, document)
    if errors:
        first = errors[0]
        raise ValidationError(f"{first['path']}: {first['message']}")
