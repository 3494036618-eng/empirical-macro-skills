"""Clarification selection under the guided-intake question budget."""

from __future__ import annotations

import copy


def next_clarification(document: dict[str, object]) -> dict[str, object] | None:
    clarifications = document.get("clarifications")
    if not isinstance(clarifications, list):
        return None
    for clarification in clarifications:
        if isinstance(clarification, dict) and clarification.get("status") == "pending":
            return {
                str(key): copy.deepcopy(value)
                for key, value in clarification.items()
            }
    return None
