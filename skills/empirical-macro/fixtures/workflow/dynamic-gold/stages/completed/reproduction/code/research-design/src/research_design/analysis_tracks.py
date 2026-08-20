"""Deterministic dynamic-analysis track and audit-design selection."""

from __future__ import annotations

ANALYSIS_TRACK_BY_DESIGN = {
    "local_projection": "identified_shock_irf",
    "conditional_projection": "conditional_dynamic_association",
}


def analysis_track_for_design(design: str) -> str:
    return ANALYSIS_TRACK_BY_DESIGN.get(design, "not_applicable")


def audit_design(
    primary: str,
    candidates: list[dict[str, object]],
) -> str:
    if primary != "unresolved":
        return primary
    adopted = next(
        (
            item.get("design")
            for item in candidates
            if item.get("decision") == "adopt"
            and isinstance(item.get("design"), str)
        ),
        None,
    )
    if isinstance(adopted, str):
        return adopted
    return str(candidates[0]["design"])
