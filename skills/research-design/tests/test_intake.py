from __future__ import annotations

from research_design.intake import evaluate_intake


def test_idea_only_requires_two_candidates(
    valid_intake_document: dict[str, object],
) -> None:
    candidates = valid_intake_document["candidate_questions"]
    assert isinstance(candidates, list)
    valid_intake_document["candidate_questions"] = candidates[:1]

    result = evaluate_intake(valid_intake_document)

    assert result["status"] == "blocked"
    assert result["issue_codes"] == ["idea_only_requires_candidate_choice"]


def test_declined_clarification_applies_descriptive_safe_default(
    valid_intake_document: dict[str, object],
) -> None:
    clarifications = valid_intake_document["clarifications"]
    assert isinstance(clarifications, list)
    clarification = clarifications[0]
    assert isinstance(clarification, dict)
    clarification["status"] = "declined"
    valid_intake_document["status"] = "ready_to_compile"

    result = evaluate_intake(valid_intake_document)

    assert result["status"] == "ready_to_compile"
    assert result["safe_default"]["applied"] is True
    assert result["safe_default"]["downgraded_to"] == "descriptive"


def test_recommended_candidate_must_exist(
    valid_intake_document: dict[str, object],
) -> None:
    valid_intake_document["recommended_candidate_id"] = "rd-candidate-ffffffff"

    result = evaluate_intake(valid_intake_document)

    assert result["status"] == "blocked"
    assert result["issue_codes"] == ["recommended_candidate_not_found"]


def test_candidate_and_clarification_budgets_fail_closed(
    valid_intake_document: dict[str, object],
) -> None:
    candidates = valid_intake_document["candidate_questions"]
    clarifications = valid_intake_document["clarifications"]
    assert isinstance(candidates, list)
    assert isinstance(clarifications, list)
    candidates.extend([candidates[0], candidates[1]])
    clarifications.extend([clarifications[0], clarifications[0], clarifications[0]])

    result = evaluate_intake(valid_intake_document)

    assert result["status"] == "blocked"
    assert result["issue_codes"] == [
        "candidate_budget_exceeded",
        "clarification_budget_exceeded",
    ]
