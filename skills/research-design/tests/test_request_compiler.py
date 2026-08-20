from __future__ import annotations

import pytest

from research_design.field_provenance import audit_field_provenance
from research_design.models import (
    FieldConfidence,
    FieldProvenance,
    FieldSource,
    InputMaturity,
)
from research_design.request_compiler import compile_request


def test_present_core_field_must_have_provenance_entry() -> None:
    request: dict[str, object] = {
        "research_question": "研究贸易开放与增长的关系",
        "field_provenance": [],
    }

    assert audit_field_provenance(request) == [
        "field_provenance_missing:research_question"
    ]


def test_every_variable_role_must_have_provenance_entry() -> None:
    request: dict[str, object] = {
        "variables": [
            {"variable_id": "growth", "role": "outcome"},
            {"variable_id": "trade", "role": "exposure"},
        ],
        "field_provenance": [],
    }

    assert audit_field_provenance(request) == [
        "field_provenance_missing:variables[0].role",
        "field_provenance_missing:variables[1].role",
    ]


def test_complete_provenance_ledger_has_no_issues() -> None:
    request: dict[str, object] = {
        "research_question": "研究贸易开放与增长的关系",
        "intended_claim": "associational",
        "variables": [{"variable_id": "growth", "role": "outcome"}],
        "field_provenance": [
            {"field_path": "research_question", "source": "user_provided"},
            {"field_path": "intended_claim", "source": "inferred_from_text"},
            {"field_path": "variables[0].role", "source": "recommended_default"},
        ],
    }

    assert audit_field_provenance(request) == []


def test_missing_provenance_ledger_fails_closed() -> None:
    request: dict[str, object] = {
        "research_question": "研究贸易开放与增长的关系",
    }

    assert audit_field_provenance(request) == [
        "field_provenance_missing:research_question"
    ]


def test_contract_enums_reject_values_outside_the_allowlist() -> None:
    assert InputMaturity("idea_only") is InputMaturity.IDEA_ONLY
    with pytest.raises(ValueError):
        FieldSource("model_guess")


def test_field_provenance_record_is_immutable() -> None:
    record = FieldProvenance(
        field_path="research_question",
        source=FieldSource.USER_PROVIDED,
        evidence_text="用户原始问题",
        confidence=FieldConfidence.HIGH,
    )

    with pytest.raises(AttributeError):
        record.__setattr__("field_path", "intended_claim")


def test_compiler_rejects_candidate_not_selected_in_intake(
    valid_intake_document: dict[str, object],
    valid_request_document: dict[str, object],
) -> None:
    valid_request_document["selected_candidate_id"] = "rd-candidate-ffffffff"

    with pytest.raises(ValueError, match="selected candidate is not present"):
        compile_request(valid_intake_document, valid_request_document)


def test_compiler_rejects_pending_intake(
    pending_intake_document: dict[str, object],
    valid_request_document: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="intake is not ready to compile"):
        compile_request(pending_intake_document, valid_request_document)


def test_compiler_rejects_request_for_different_intake(
    valid_intake_document: dict[str, object],
    valid_request_document: dict[str, object],
) -> None:
    valid_request_document["source_intake_id"] = "rd-intake-bbbbbbbbbbbbbbbb"

    with pytest.raises(ValueError, match="source_intake_id does not match"):
        compile_request(valid_intake_document, valid_request_document)


def test_compiler_preserves_expert_locked_fields(
    valid_intake_document: dict[str, object],
    valid_request_document: dict[str, object],
) -> None:
    valid_intake_document["input_maturity"] = "design_ready"

    result = compile_request(valid_intake_document, valid_request_document)

    assert result["intended_claim"] == valid_request_document["intended_claim"]
    assert result["safe_downgrade_applied"] is False


def test_compiler_applies_only_registered_safe_downgrade(
    valid_intake_document: dict[str, object],
    valid_request_document: dict[str, object],
) -> None:
    valid_request_document["input_maturity"] = "idea_only"
    valid_intake_document["safe_default"] = {
        "applied": True,
        "downgraded_to": "descriptive",
        "reason": "用户无法确认因果设计。",
    }

    result = compile_request(valid_intake_document, valid_request_document)

    assert result["intended_claim"] == "descriptive"
    assert result["safe_downgrade_applied"] is True
    provenance = result["field_provenance"]
    assert isinstance(provenance, list)
    intended_claim_entries = [
        entry
        for entry in provenance
        if isinstance(entry, dict) and entry.get("field_path") == "intended_claim"
    ]
    assert intended_claim_entries[0]["source"] == "recommended_default"


def test_safe_downgrade_never_overwrites_user_provided_claim(
    valid_intake_document: dict[str, object],
    valid_request_document: dict[str, object],
) -> None:
    valid_request_document["input_maturity"] = "idea_only"
    provenance = valid_request_document["field_provenance"]
    assert isinstance(provenance, list)
    provenance.append(
        {
            "field_path": "intended_claim",
            "source": "user_provided",
            "evidence_text": "用户明确要求因果问题",
            "confidence": "high",
        }
    )
    valid_intake_document["safe_default"] = {
        "applied": True,
        "downgraded_to": "descriptive",
        "reason": "用户无法确认其他设计细节。",
    }

    result = compile_request(valid_intake_document, valid_request_document)

    assert result["intended_claim"] == "causal"
    assert result["safe_downgrade_applied"] is False
