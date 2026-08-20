"""Versioned JSON Schema contracts for research-design artifacts."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILES = {
    "intake": "research-intake.schema.json",
    "request": "research-design-request.schema.json",
    "identification_audit": "identification-audit.schema.json",
    "data_requirements": "data-requirements.schema.json",
    "plan": "research-plan.schema.json",
    "robustness_handoff": "robustness-handoff.schema.json",
    "run_manifest": "research-design-run-manifest.schema.json",
}
SUPPORTED_SCHEMA_VERSION = "0.1.0-draft"


@cache
def load_schema(contract: str) -> dict[str, object]:
    try:
        filename = SCHEMA_FILES[contract]
    except KeyError as exc:
        raise ValueError(f"unknown contract: {contract}") from exc
    schema = cast(
        dict[str, object],
        json.loads((PROJECT_ROOT / "schemas" / filename).read_text(encoding="utf-8")),
    )
    Draft202012Validator.check_schema(schema)
    return schema


def validation_errors(
    contract: str,
    document: dict[str, object],
) -> list[dict[str, str]]:
    validator = Draft202012Validator(
        load_schema(contract),
        format_checker=FormatChecker(),
    )
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (
            tuple(map(str, error.absolute_path)),
            error.message,
        ),
    )
    return [
        {
            "path": "/".join(map(str, error.absolute_path)) or "<root>",
            "message": error.message,
        }
        for error in errors
    ]


def validate_document(contract: str, document: dict[str, object]) -> None:
    version = document.get("schema_version")
    if version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {version!r}")
    errors = validation_errors(contract, document)
    if errors:
        first = errors[0]
        raise ValueError(
            f"{contract} contract violation at {first['path']}: {first['message']}"
        )
