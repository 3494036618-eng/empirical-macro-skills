from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator

from research_design.data_requirements_builder import write_macro_data_request
from research_design.exporter import validate_bundle
from research_design.pipeline import run_research_design

FIXTURES = Path(__file__).parents[1] / "fixtures" / "gold"


def _load(name: str) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((FIXTURES / name).read_text(encoding="utf-8")),
    )


def test_macro_data_request_is_validated_by_external_schema(
    tmp_path: Path,
    valid_macro_request_document: dict[str, object],
    macro_schema_path: Path,
) -> None:
    output = tmp_path / "macro-data-requests" / "request.json"

    reference = write_macro_data_request(
        valid_macro_request_document,
        output,
        macro_schema_path,
    )

    assert reference["schema_id"] == (
        "urn:empirical-macro:macro-data:request:0.2.0-beta"
    )
    assert reference["validation_status"] == "validated"
    assert reference["checksum_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


def test_invalid_macro_data_request_is_not_written(
    tmp_path: Path,
    macro_schema_path: Path,
) -> None:
    output = tmp_path / "request.json"
    invalid_macro_request: dict[str, object] = {"schema_version": "0.2.0-beta"}

    with pytest.raises(ValueError, match="macro-data request contract violation"):
        write_macro_data_request(
            invalid_macro_request,
            output,
            macro_schema_path,
        )

    assert not output.exists()


def test_annual_panel_emits_valid_macro_request(
    tmp_path: Path,
    macro_schema_path: Path,
) -> None:
    output = tmp_path / "annual-panel"

    result = run_research_design(
        _load("annual-panel-intake.json"),
        _load("annual-panel-request.json"),
        output,
        macro_schema_path,
        macro_request_document=_load("annual-panel-macro-request.json"),
    )

    assert result["design_readiness"] == "ready_for_data"
    macro_request_path = Path(str(result["macro_request_path"]))
    macro_schema = json.loads(macro_schema_path.read_text(encoding="utf-8"))
    macro_request = json.loads(macro_request_path.read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(macro_schema).iter_errors(macro_request))


def test_flagship_does_not_invent_monetary_shock(
    tmp_path: Path,
    macro_schema_path: Path,
) -> None:
    result = run_research_design(
        _load("monetary-flagship-intake.json"),
        _load("monetary-flagship-request.json"),
        tmp_path / "flagship",
        macro_schema_path,
    )

    assert result["design_readiness"] == "blocked"
    assert "shock_identification_unresolved" in result["issue_codes"]


def test_macro_request_tamper_invalidates_research_bundle(
    tmp_path: Path,
    macro_schema_path: Path,
) -> None:
    output = tmp_path / "annual-panel"
    result = run_research_design(
        _load("annual-panel-intake.json"),
        _load("annual-panel-request.json"),
        output,
        macro_schema_path,
        macro_request_document=_load("annual-panel-macro-request.json"),
    )
    macro_path = Path(str(result["macro_request_path"]))
    macro_path.write_bytes(macro_path.read_bytes() + b" ")

    validation = validate_bundle(output)

    assert validation["valid"] is False
    assert "checksum_mismatch:macro_data_request" in validation["errors"]


def test_unrelated_macro_request_cannot_make_research_ready(
    tmp_path: Path,
    macro_schema_path: Path,
) -> None:
    macro_request = _load("annual-panel-macro-request.json")
    concepts = macro_request["concepts"]
    assert isinstance(concepts, list)
    exposure = concepts[1]
    assert isinstance(exposure, dict)
    exposure["concept"] = "与研究无关的指标"

    with pytest.raises(ValueError, match="macro-data request does not match"):
        run_research_design(
            _load("annual-panel-intake.json"),
            _load("annual-panel-request.json"),
            tmp_path / "misaligned",
            macro_schema_path,
            macro_request_document=macro_request,
        )

    assert not (tmp_path / "misaligned").exists()


def test_macro_data_cannot_bypass_missing_design_prerequisites(
    tmp_path: Path,
    macro_schema_path: Path,
) -> None:
    request = _load("annual-panel-request.json")
    variables = request["variables"]
    provenance = request["field_provenance"]
    assert isinstance(variables, list)
    assert isinstance(provenance, list)
    request["variables"] = variables[:1]
    request["field_provenance"] = [
        item
        for item in provenance
        if not isinstance(item, dict)
        or item.get("field_path") != "variables[1].role"
    ]
    macro_request = _load("annual-panel-macro-request.json")
    concepts = macro_request["concepts"]
    indicators = macro_request["indicators"]
    assert isinstance(concepts, list)
    assert isinstance(indicators, list)
    macro_request["concepts"] = concepts[:1]
    macro_request["indicators"] = indicators[:1]

    result = run_research_design(
        _load("annual-panel-intake.json"),
        request,
        tmp_path / "missing-design",
        macro_schema_path,
        macro_request_document=macro_request,
    )

    assert result["design_readiness"] == "blocked"
    assert "no_eligible_design" in result["issue_codes"]


def test_macro_handoff_requires_exact_entity_identity(
    tmp_path: Path,
    macro_schema_path: Path,
) -> None:
    request = _load("annual-panel-request.json")
    entities = request["data_entities"]
    assert isinstance(entities, list)
    first_entity = entities[0]
    assert isinstance(first_entity, dict)
    first_entity["name_or_code"] = "JPN"

    with pytest.raises(ValueError, match="entity_identity_mismatch"):
        run_research_design(
            _load("annual-panel-intake.json"),
            request,
            tmp_path / "wrong-entities",
            macro_schema_path,
            macro_request_document=_load("annual-panel-macro-request.json"),
        )


def test_macro_handoff_requires_indicator_coverage(
    tmp_path: Path,
    macro_schema_path: Path,
) -> None:
    macro_request = _load("annual-panel-macro-request.json")
    indicators = macro_request["indicators"]
    assert isinstance(indicators, list)
    macro_request["indicators"] = indicators[:1]

    with pytest.raises(ValueError, match="indicator_coverage_mismatch"):
        run_research_design(
            _load("annual-panel-intake.json"),
            _load("annual-panel-request.json"),
            tmp_path / "missing-indicator",
            macro_schema_path,
            macro_request_document=macro_request,
        )
