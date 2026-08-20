"""Versioned JSON Schema contracts for macro-data boundaries."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILES = {
    "request": {
        "0.2.0-beta": "macro-data-request.schema.json",
        "0.3.0-beta": "macro-data-request-v0.3.schema.json",
    },
    "series_specification": {
        "0.2.0-beta": "series-specification.schema.json",
    },
    "provenance": {
        "0.2.0-beta": "provenance.schema.json",
    },
    "result": {
        "0.2.0-beta": "macro-data-result.schema.json",
        "0.3.0-beta": "macro-data-result-v0.3.schema.json",
    },
    "run_manifest": {
        "0.2.0-beta": "run-manifest.schema.json",
    },
    "expected_observation_matrix": {
        "0.3.0-beta": "expected-observation-matrix.schema.json",
    },
    "residual_gap_manifest": {
        "0.3.0-beta": "residual-gap-manifest.schema.json",
    },
    "completion_manifest": {
        "0.3.0-beta": "completion-manifest.schema.json",
    },
    "public_research_artifact": {
        "0.2.0-beta": "public-research-artifact.schema.json",
    },
}
SUPPORTED_SCHEMA_VERSION = "0.2.0-beta"
SUPPORTED_SCHEMA_VERSIONS = frozenset({"0.2.0-beta", "0.3.0-beta"})


@cache
def load_schema(contract: str, version: str | None = None) -> dict[str, Any]:
    try:
        versions = SCHEMA_FILES[contract]
    except KeyError as exc:
        raise ValueError(f"unknown contract: {contract}") from exc
    selected_version = version or next(iter(versions))
    try:
        filename = versions[selected_version]
    except KeyError as exc:
        raise ValueError(
            f"unsupported schema_version for {contract}: {selected_version!r}"
        ) from exc
    schema = json.loads((PROJECT_ROOT / "schemas" / filename).read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise TypeError(f"{filename} must contain a JSON object")
    Draft202012Validator.check_schema(schema)
    return cast(dict[str, Any], schema)


def validation_errors(contract: str, document: dict[str, Any]) -> list[dict[str, str]]:
    validator = Draft202012Validator(
        load_schema(contract, schema_version(document)),
        format_checker=FormatChecker(),
    )
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    return [
        {
            "path": "/".join(map(str, error.absolute_path)) or "<root>",
            "message": error.message,
        }
        for error in errors
    ]


def validate_document(contract: str, document: dict[str, Any]) -> None:
    errors = validation_errors(contract, document)
    if errors:
        first = errors[0]
        raise ValueError(f"{contract} contract violation at {first['path']}: {first['message']}")


def schema_version(document: dict[str, Any]) -> str:
    version = document.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported schema_version: {version!r}")
    return cast(str, version)
