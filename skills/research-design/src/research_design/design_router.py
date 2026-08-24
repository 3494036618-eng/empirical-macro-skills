"""Boolean prerequisite routing for versioned design cards."""

from __future__ import annotations

from research_design.design_cards import DESIGN_CARDS, DesignCard

IDENTIFIED_SHOCK_MECHANISMS = {
    "randomized",
    "narrative",
    "external_instrument",
    "statistical_innovation",
}
DEFERRED_DESIGNS = {"var_svar"}


def _roles(request: dict[str, object]) -> set[str]:
    variables = request.get("variables")
    if not isinstance(variables, list):
        return set()
    return {
        role
        for variable in variables
        if isinstance(variable, dict)
        and isinstance((role := variable.get("role")), str)
    }


def _requirement_satisfied(
    requirement: str,
    request: dict[str, object],
    roles: set[str],
) -> bool:
    role_requirements = {
        "outcome_role": "outcome",
        "exposure_role": "exposure",
        "treatment_role": "treatment",
        "shock_role": "shock",
        "instrument_role": "instrument",
        "forecast_target_role": "forecast_target",
    }
    if requirement in role_requirements:
        return role_requirements[requirement] in roles
    intervention = request.get("intervention_or_shock")
    if requirement == "treatment_timing":
        return isinstance(intervention, dict) and intervention.get("timing_known") is True
    if requirement == "identified_shock":
        return (
            isinstance(intervention, dict)
            and intervention.get("assignment_mechanism")
            in IDENTIFIED_SHOCK_MECHANISMS
        )
    if requirement == "comparison_group":
        return isinstance(request.get("comparison"), str)
    if requirement == "forecast_specification":
        return isinstance(request.get("forecast"), dict)
    return False


def _evaluate_card(
    card: DesignCard,
    request: dict[str, object],
    roles: set[str],
) -> dict[str, object]:
    missing = [
        requirement
        for requirement in card.required_fields
        if not _requirement_satisfied(requirement, request, roles)
    ]
    decision = "adopt" if not missing else "reject"
    if (
        card.code in DEFERRED_DESIGNS
        or card.allowed_claim == "structural_candidate"
    ) and not missing:
        decision = "defer"
    return {
        "code": card.code,
        "decision": decision,
        "missing_prerequisites": missing,
        "forbidden_shortcuts": list(card.forbidden_shortcuts),
        "required_diagnostics": list(card.required_diagnostics),
        "allowed_claim": card.allowed_claim,
    }


def eligible_designs(
    request: dict[str, object],
    family: str,
) -> list[dict[str, object]]:
    roles = _roles(request)
    cards = sorted(
        (card for card in DESIGN_CARDS if family in card.families),
        key=lambda card: card.code,
    )
    return [_evaluate_card(card, request, roles) for card in cards]
