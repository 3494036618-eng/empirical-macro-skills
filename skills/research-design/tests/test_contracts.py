from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_design.contracts import (
    load_schema,
    validate_document,
    validation_errors,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "contracts"


@pytest.mark.parametrize(
    ("contract", "positive", "negative"),
    [
        ("intake", "intake.valid.json", "intake.invalid.json"),
        ("request", "request.valid.json", "request.invalid.json"),
        (
            "identification_audit",
            "identification-audit.valid.json",
            "identification-audit.invalid.json",
        ),
        (
            "data_requirements",
            "data-requirements.valid.json",
            "data-requirements.invalid.json",
        ),
        ("plan", "research-plan.valid.json", "research-plan.invalid.json"),
        ("run_manifest", "run-manifest.valid.json", "run-manifest.invalid.json"),
    ],
)
def test_contract_examples(contract: str, positive: str, negative: str) -> None:
    valid = json.loads((FIXTURES / positive).read_text(encoding="utf-8"))
    invalid = json.loads((FIXTURES / negative).read_text(encoding="utf-8"))

    validate_document(contract, valid)
    with pytest.raises(ValueError, match="contract violation"):
        validate_document(contract, invalid)


def test_unknown_contract_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown contract"):
        load_schema("unknown")


def test_unsupported_schema_version_is_rejected() -> None:
    document = json.loads(
        (FIXTURES / "intake.valid.json").read_text(encoding="utf-8")
    )
    document["schema_version"] = "0.2.0"

    with pytest.raises(ValueError, match="unsupported schema_version"):
        validate_document("intake", document)


def test_validation_errors_have_stable_public_shape() -> None:
    invalid = json.loads(
        (FIXTURES / "request.invalid.json").read_text(encoding="utf-8")
    )

    errors = validation_errors("request", invalid)

    assert errors
    assert set(errors[0]) == {"path", "message"}
