"""Semantic completeness checks for field provenance ledgers."""

from __future__ import annotations

CORE_FIELDS = (
    "research_question",
    "intended_claim",
    "target_population",
    "unit_of_analysis",
    "time_scope",
)


def _ledger_paths(request: dict[str, object]) -> set[str]:
    ledger = request.get("field_provenance")
    if not isinstance(ledger, list):
        return set()
    return {
        path
        for entry in ledger
        if isinstance(entry, dict)
        and isinstance((path := entry.get("field_path")), str)
    }


def _required_paths(request: dict[str, object]) -> set[str]:
    required = {field for field in CORE_FIELDS if field in request}
    variables = request.get("variables")
    if not isinstance(variables, list):
        return required
    required.update(
        f"variables[{index}].role"
        for index, variable in enumerate(variables)
        if isinstance(variable, dict) and "role" in variable
    )
    return required


def audit_field_provenance(request: dict[str, object]) -> list[str]:
    missing = _required_paths(request) - _ledger_paths(request)
    return sorted(f"field_provenance_missing:{path}" for path in missing)
