from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_VERSION = "0.1.0-beta"
SCHEMA_FILES = {
    "research_intent": "research-intent.schema.json",
    "route_decision": "route-decision.schema.json",
    "workflow_state": "workflow-state.schema.json",
    "checkpoint": "checkpoint.schema.json",
    "install_manifest": "install-manifest.schema.json",
}
PACKAGE_SCHEMA_ROOT = Path(__file__).resolve().parent / "schemas"
SOURCE_SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas"
SCHEMA_ROOT = (
    PACKAGE_SCHEMA_ROOT if PACKAGE_SCHEMA_ROOT.is_dir() else SOURCE_SCHEMA_ROOT
)


@cache
def load_schema(contract: str) -> dict[str, object]:
    try:
        filename = SCHEMA_FILES[contract]
    except KeyError as error:
        raise ValueError(f"unknown contract: {contract}") from error
    document = json.loads((SCHEMA_ROOT / filename).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"schema must be an object: {contract}")
    schema = cast(dict[str, object], document)
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
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    return [
        {
            "path": ".".join(str(part) for part in error.absolute_path) or "$",
            "message": error.message,
            "validator": str(error.validator),
        }
        for error in errors
    ]


def validate_document(contract: str, document: dict[str, object]) -> None:
    errors = validation_errors(contract, document)
    if not errors:
        return
    first = errors[0]
    raise ValueError(
        f"contract violation: {contract}: {first['path']}: {first['message']}"
    )
