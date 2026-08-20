from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator

from tests.helpers import load_contract_fixture

CONTRACT_CASES = {
    "research_intent": "research-intent",
    "route_decision": "route-decision",
    "workflow_state": "workflow-state",
    "checkpoint": "checkpoint",
    "install_manifest": "install-manifest",
}


def test_contracts_accept_positive_and_reject_negative_examples() -> None:
    """Break caught: a contract accepts malformed workflow documents."""
    from empirical_macro.contracts import validate_document

    for contract, prefix in CONTRACT_CASES.items():
        validate_document(contract, load_contract_fixture(f"{prefix}.valid.json"))
        with pytest.raises(ValueError, match="contract violation"):
            validate_document(contract, load_contract_fixture(f"{prefix}.invalid.json"))


def test_contract_schemas_are_valid_draft_2020_12_documents() -> None:
    """Break caught: a schema uses invalid or permissive top-level syntax."""
    from empirical_macro.contracts import load_schema

    for contract in CONTRACT_CASES:
        schema = load_schema(contract)
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False
