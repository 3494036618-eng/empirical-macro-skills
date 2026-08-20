"""Match explicit request semantics against selected provider candidates."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _normalized_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"\s*=\s*", "=", text)
    return " ".join(text.split())


def _metadata_value(candidate: dict[str, Any], field: str) -> Any:
    metadata = candidate.get(field)
    return metadata.get("value") if isinstance(metadata, dict) else None


def _definition_matches(required: str, candidate: dict[str, Any]) -> bool:
    expected = _normalized_text(required)
    available = {
        _normalized_text(candidate.get("indicator_name")),
        _normalized_text(_metadata_value(candidate, "definition")),
    }
    return expected in available


def _price_basis_matches(
    requested: dict[str, Any],
    candidate: dict[str, Any],
) -> bool:
    if requested["type"] == "source_native":
        return True
    observed = _metadata_value(candidate, "price_basis")
    if not isinstance(observed, dict):
        return False
    return all(
        requested.get(field) is None or requested.get(field) == observed.get(field)
        for field in ("type", "base_period", "chain_linked")
    )


def request_constraint_issues(
    request: dict[str, Any],
    selected: list[dict[str, Any]],
) -> set[str]:
    """Return blocking mismatches for every explicit request constraint."""

    issues: set[str] = set()
    requested_unit = request.get("unit")
    if requested_unit is not None and any(
        _normalized_text(_metadata_value(item, "unit")) != _normalized_text(requested_unit)
        for item in selected
    ):
        issues.add("unit_mismatch")

    requested_adjustment = request["seasonal_adjustment"]
    if requested_adjustment != "source_native" and any(
        _normalized_text(_metadata_value(item, "seasonal_adjustment"))
        != _normalized_text(requested_adjustment)
        for item in selected
    ):
        issues.add("seasonal_adjustment_mismatch")

    if any(not _price_basis_matches(request["price_basis"], item) for item in selected):
        issues.add("price_basis_mismatch")

    requested_currency = request.get("currency")
    if requested_currency is not None and any(
        _normalized_text(item.get("currency")) != _normalized_text(requested_currency)
        for item in selected
    ):
        issues.add("currency_mismatch")

    definitions = {
        item["name_or_code"]: item.get("required_definition")
        for item in request["indicators"]
        if item.get("required_definition")
    }
    concept_constraints = {
        _normalized_text(constraint)
        for concept in request["concepts"]
        for constraint in concept["definition_constraints"]
    }
    mapped_definitions = {_normalized_text(definition) for definition in definitions.values()}
    if not concept_constraints <= mapped_definitions:
        issues.add("concept_definition_mapping_unresolved")
    if any(
        required is not None and not _definition_matches(required, item)
        for item in selected
        if (required := definitions.get(item.get("indicator_code")))
    ):
        issues.add("definition_mismatch")
    return issues
