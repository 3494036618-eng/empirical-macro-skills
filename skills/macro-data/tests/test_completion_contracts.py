from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

from macro_data.contracts import load_schema, validate_document

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "completion"
LEGACY = ROOT / "fixtures" / "synthetic" / "schema-examples"
V03_CASES = {
    "request": "request",
    "result": "result",
    "expected_observation_matrix": "matrix",
    "residual_gap_manifest": "gaps",
    "completion_manifest": "completion",
}


def _load(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return cast(dict[str, Any], document)


def test_contract_loader_routes_request_by_document_version() -> None:
    validate_document("request", _load(FIXTURES / "request.valid.json"))
    validate_document("request", _load(LEGACY / "request.valid.json"))


def test_unknown_version_is_rejected() -> None:
    document = _load(FIXTURES / "request.valid.json")
    document["schema_version"] = "9.9.9"

    with pytest.raises(ValueError, match="unsupported schema_version"):
        validate_document("request", document)


def test_invalid_v03_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="request contract violation"):
        validate_document("request", _load(FIXTURES / "request.invalid.json"))


def test_all_v03_contracts_accept_positive_examples() -> None:
    for contract, fixture in V03_CASES.items():
        validate_document(contract, _load(FIXTURES / f"{fixture}.valid.json"))


def test_all_v03_contracts_reject_negative_examples() -> None:
    for contract, fixture in V03_CASES.items():
        with pytest.raises(ValueError, match=f"{contract} contract violation"):
            validate_document(contract, _load(FIXTURES / f"{fixture}.invalid.json"))


def test_datapro_primary_requires_ratio_at_least_eighty_percent() -> None:
    with pytest.raises(ValueError, match="provider_contribution"):
        validate_document("result", _load(FIXTURES / "result.invalid.json"))


def test_completion_manifest_rejects_replaced_primary_cell() -> None:
    with pytest.raises(ValueError, match="replaced_primary_count"):
        validate_document(
            "completion_manifest",
            _load(FIXTURES / "completion.invalid.json"),
        )


def test_allow_official_migrates_to_missing_only_without_mutating_input() -> None:
    from macro_data.request_migration import migrate_request_v02_to_v03

    legacy = _load(LEGACY / "request.valid.json")
    legacy["preferred_sources"].append("world_bank")
    legacy["fallback_policy"] = {
        "mode": "allow_official",
        "allowed_sources": ["world_bank"],
        "allow_semantic_substitute": False,
        "allow_cross_source_stitching": False,
    }
    before = copy.deepcopy(legacy)

    migrated = migrate_request_v02_to_v03(legacy)

    assert legacy == before
    assert migrated["schema_version"] == "0.3.0-beta"
    assert migrated["fallback_policy"] == {
        "mode": "allow_official_missing_only",
        "allowed_sources": ["world_bank"],
        "completion_scope": "missing_cells_only",
        "preserve_datapro_observations": True,
        "replace_primary_observations": False,
        "allow_semantic_substitute": False,
        "allow_cross_source_stitching": False,
        "identity_match_policy": "exact_native_or_approved_mapping",
        "overlap_policy": "validate_without_replacement",
    }
    validate_document("request", migrated)


@pytest.mark.parametrize(
    ("mode", "allowed_sources"),
    (("never", []), ("ask", ["world_bank"])),
)
def test_migration_preserves_never_and_ask_approval_semantics(
    mode: str,
    allowed_sources: list[str],
) -> None:
    from macro_data.request_migration import migrate_request_v02_to_v03

    legacy = _load(LEGACY / "request.valid.json")
    legacy["preferred_sources"] = ["datapro", *allowed_sources]
    legacy["fallback_policy"] = {
        "mode": mode,
        "allowed_sources": allowed_sources,
        "allow_semantic_substitute": False,
        "allow_cross_source_stitching": False,
    }

    migrated = migrate_request_v02_to_v03(legacy)

    assert migrated["fallback_policy"]["mode"] == mode
    assert migrated["fallback_policy"]["allowed_sources"] == allowed_sources
    assert migrated["fallback_policy"]["completion_scope"] == "missing_cells_only"
    assert migrated["fallback_policy"]["preserve_datapro_observations"] is True
    assert migrated["fallback_policy"]["replace_primary_observations"] is False
    validate_document("request", migrated)


def test_legacy_load_schema_default_remains_v02() -> None:
    schema = load_schema("request")

    assert schema["$id"].endswith(":0.2.0-beta")


def test_all_v03_schemas_are_valid_draft_2020_12_documents() -> None:
    for contract in V03_CASES:
        schema = load_schema(contract, version="0.3.0-beta")

        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False
