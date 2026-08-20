from __future__ import annotations

from research_design.clarification import next_clarification


def test_next_clarification_returns_first_pending_question(
    pending_intake_document: dict[str, object],
) -> None:
    result = next_clarification(pending_intake_document)

    assert result is not None
    assert result["question_id"] == "clarify-aaaaaaaa"


def test_three_registered_questions_do_not_hide_existing_pending_question(
    pending_intake_document: dict[str, object],
) -> None:
    clarifications = pending_intake_document["clarifications"]
    assert isinstance(clarifications, list)
    template = clarifications[0]
    assert isinstance(template, dict)
    clarifications.extend(
        [
            {**template, "question_id": "clarify-bbbbbbbb"},
            {**template, "question_id": "clarify-cccccccc"},
        ]
    )

    result = next_clarification(pending_intake_document)

    assert result is not None
    assert result["question_id"] == "clarify-aaaaaaaa"


def test_no_pending_clarification_returns_none(
    pending_intake_document: dict[str, object],
) -> None:
    clarifications = pending_intake_document["clarifications"]
    assert isinstance(clarifications, list)
    clarification = clarifications[0]
    assert isinstance(clarification, dict)
    clarification["status"] = "answered"
    clarification["answer"] = "拆解通胀构成"

    assert next_clarification(pending_intake_document) is None
