"""JSON Schema contract loading and validation."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_FILES = {
    "research_plan_handoff": "research-plan-handoff.schema.json",
    "macro_data_handoff": "macro-data-handoff.schema.json",
    "shock_artifact": "shock-identification-artifact.schema.json",
    "request": "time-series-dynamics-request.schema.json",
    "result": "time-series-dynamics-result.schema.json",
    "diagnostics": "time-series-diagnostics.schema.json",
    "run_manifest": "time-series-run-manifest.schema.json",
    "input_evidence_manifest": "time-series-input-evidence-manifest.schema.json",
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


def validation_errors(
    contract: str,
    document: dict[str, object],
) -> list[dict[str, str]]:
    validator = Draft202012Validator(
        load_schema(contract),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    return [
        {
            "path": "/" + "/".join(str(part) for part in error.absolute_path),
            "message": error.message,
        }
        for error in errors
    ]


def validate_document(contract: str, document: dict[str, object]) -> None:
    validator = Draft202012Validator(
        load_schema(contract),
        format_checker=FormatChecker(),
    )
    validator.validate(document)
