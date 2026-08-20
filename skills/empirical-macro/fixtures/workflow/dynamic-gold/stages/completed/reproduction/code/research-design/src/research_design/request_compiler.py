"""Compile a selected intake candidate into a validated research request."""

from __future__ import annotations

import copy

from research_design.contracts import validate_document
from research_design.intake import evaluate_intake

EXPERT_MATURITIES = {"design_ready", "execution_ready"}


def _candidate_ids(intake: dict[str, object]) -> set[str]:
    candidates = intake.get("candidate_questions")
    if not isinstance(candidates, list):
        return set()
    return {
        candidate_id
        for candidate in candidates
        if isinstance(candidate, dict)
        and isinstance((candidate_id := candidate.get("candidate_id")), str)
    }


def _safe_downgrade(intake: dict[str, object]) -> str | None:
    safe_default = intake.get("safe_default")
    if not isinstance(safe_default, dict) or safe_default.get("applied") is not True:
        return None
    downgrade = safe_default.get("downgraded_to")
    if downgrade in {"descriptive", "associational"}:
        return str(downgrade)
    return None


def _field_is_user_provided(request: dict[str, object], field_path: str) -> bool:
    provenance = request.get("field_provenance")
    if not isinstance(provenance, list):
        return False
    return any(
        isinstance(entry, dict)
        and entry.get("field_path") == field_path
        and entry.get("source") == "user_provided"
        for entry in provenance
    )


def _record_safe_downgrade(
    compiled: dict[str, object],
    intake: dict[str, object],
) -> None:
    provenance = compiled.get("field_provenance")
    if not isinstance(provenance, list):
        return
    provenance[:] = [
        entry
        for entry in provenance
        if not isinstance(entry, dict) or entry.get("field_path") != "intended_claim"
    ]
    safe_default = intake.get("safe_default")
    reason = safe_default.get("reason") if isinstance(safe_default, dict) else None
    provenance.append(
        {
            "field_path": "intended_claim",
            "source": "recommended_default",
            "evidence_text": reason,
            "confidence": "medium",
        }
    )


def compile_request(
    intake: dict[str, object],
    candidate_request: dict[str, object],
) -> dict[str, object]:
    validate_document("intake", intake)
    validate_document("request", candidate_request)
    if evaluate_intake(intake)["status"] != "ready_to_compile":
        raise ValueError("intake is not ready to compile")
    if candidate_request.get("source_intake_id") != intake.get("intake_id"):
        raise ValueError("request source_intake_id does not match intake")
    selected = candidate_request.get("selected_candidate_id")
    if selected not in _candidate_ids(intake):
        raise ValueError("selected candidate is not present in intake")

    compiled = copy.deepcopy(candidate_request)
    maturity = compiled.get("input_maturity")
    locked = _field_is_user_provided(compiled, "intended_claim")
    downgrade = (
        None
        if maturity in EXPERT_MATURITIES or locked
        else _safe_downgrade(intake)
    )
    if downgrade is not None:
        compiled["intended_claim"] = downgrade
        compiled["safe_downgrade_applied"] = True
        _record_safe_downgrade(compiled, intake)
    validate_document("request", compiled)
    return compiled
