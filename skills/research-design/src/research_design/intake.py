"""Deterministic evaluation of guided research intake state."""

from __future__ import annotations

ALLOWED_TRANSITIONS = {
    "candidate_set": {"clarification_needed", "ready_to_compile", "blocked"},
    "clarification_needed": {"clarification_needed", "ready_to_compile", "blocked"},
    "ready_to_compile": set(),
    "blocked": set(),
}
MAX_CANDIDATES = 3
MAX_CLARIFICATIONS = 3


def _candidate_ids(document: dict[str, object]) -> set[str]:
    candidates = document.get("candidate_questions")
    if not isinstance(candidates, list):
        return set()
    return {
        candidate_id
        for candidate in candidates
        if isinstance(candidate, dict)
        and isinstance((candidate_id := candidate.get("candidate_id")), str)
    }


def _clarification_statuses(document: dict[str, object]) -> list[str]:
    clarifications = document.get("clarifications")
    if not isinstance(clarifications, list):
        return []
    return [
        status
        for clarification in clarifications
        if isinstance(clarification, dict)
        and isinstance((status := clarification.get("status")), str)
    ]


def _intake_issues(document: dict[str, object]) -> list[str]:
    issues: list[str] = []
    candidate_ids = _candidate_ids(document)
    if document.get("input_maturity") == "idea_only" and len(candidate_ids) < 2:
        issues.append("idea_only_requires_candidate_choice")
    candidates = document.get("candidate_questions")
    if isinstance(candidates, list) and len(candidates) > MAX_CANDIDATES:
        issues.append("candidate_budget_exceeded")
    recommended = document.get("recommended_candidate_id")
    if isinstance(recommended, str) and recommended not in candidate_ids:
        issues.append("recommended_candidate_not_found")
    clarifications = document.get("clarifications")
    if isinstance(clarifications, list) and len(clarifications) > MAX_CLARIFICATIONS:
        issues.append("clarification_budget_exceeded")
    return sorted(issues)


def _safe_default(document: dict[str, object], declined: bool) -> dict[str, object]:
    if declined:
        return {
            "applied": True,
            "downgraded_to": "descriptive",
            "reason": "A required clarification was declined.",
        }
    current = document.get("safe_default")
    if isinstance(current, dict):
        return {str(key): value for key, value in current.items()}
    return {"applied": False, "downgraded_to": "none", "reason": None}


def evaluate_intake(document: dict[str, object]) -> dict[str, object]:
    issues = _intake_issues(document)
    statuses = _clarification_statuses(document)
    declined = "declined" in statuses
    if issues:
        status = "blocked"
    elif "pending" in statuses:
        status = "clarification_needed"
    elif document.get("recommended_candidate_id") is not None:
        status = "ready_to_compile"
    else:
        status = "candidate_set"
    return {
        "status": status,
        "issue_codes": issues,
        "safe_default": _safe_default(document, declined),
    }
