from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import cast

import pytest
from jsonschema import ValidationError

from research_synthesis.contracts import load_schema, validate_document

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "fixtures" / "contracts"
EXPECTED = {
    "adapter-capability.schema.json",
    "bundle-reference.schema.json",
    "claim-ledger.schema.json",
    "evidence-index.schema.json",
    "limitations.schema.json",
    "reproduction-manifest.schema.json",
    "research-synthesis-request.schema.json",
    "research-synthesis-result.schema.json",
    "research-synthesis-run-manifest.schema.json",
}
CONTRACTS = {
    "adapter_capability",
    "bundle_reference",
    "claim_ledger",
    "evidence_index",
    "limitations",
    "reproduction_manifest",
    "request",
    "result",
    "run_manifest",
}


def _load(path: Path) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(path.read_text(encoding="utf-8")),
    )


def test_contract_surface_is_complete() -> None:
    assert importlib.util.find_spec("research_synthesis.contracts") is not None
    assert {path.name for path in SCHEMAS.glob("*.schema.json")} == EXPECTED


def test_contract_functions_are_public() -> None:
    spec = importlib.util.find_spec("research_synthesis.contracts")
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "load_schema")
    assert hasattr(module, "validate_document")


@pytest.mark.parametrize("contract", sorted(CONTRACTS))
def test_contract_positive_and_negative_fixtures(contract: str) -> None:
    load_schema(contract)
    validate_document(contract, _load(FIXTURES / f"{contract}.valid.json"))
    with pytest.raises(ValidationError):
        validate_document(
            contract,
            _load(FIXTURES / f"{contract}.invalid.json"),
        )


def test_runtime_configs_match_contracts() -> None:
    validate_document(
        "request",
        _load(ROOT / "fixtures" / "synthetic" / "request.valid.json"),
    )
    for path in (
        ROOT / "configs" / "local-upstream-adapters.json",
        ROOT / "fixtures" / "synthetic" / "adapter-capabilities.json",
    ):
        capabilities = _load(path)
        for capability in capabilities.values():
            assert isinstance(capability, dict)
            validate_document("adapter_capability", capability)
