from __future__ import annotations

import pytest

from tests.helpers import artifact_refs_for, initial_state, state_at


def test_dynamic_workflow_uses_every_required_stage() -> None:
    """Break caught: the workflow skips a required evidence checkpoint."""
    from empirical_macro.state_machine import transition_state

    state = initial_state()
    for stage in (
        "design_ready",
        "data_ready",
        "estimation_ready",
        "audit_ready",
        "synthesis_ready",
        "completed",
    ):
        state = transition_state(
            state,
            target_stage=stage,
            artifact_refs=artifact_refs_for(stage),
        )
    assert state.current_stage == "completed"
    assert state.status == "completed"
    assert state.resume_eligible is False
    assert len(state.artifact_refs) == 6


@pytest.mark.parametrize(
    ("source", "target"),
    (
        ("idea_received", "data_ready"),
        ("design_ready", "estimation_ready"),
        ("data_ready", "completed"),
        ("audit_ready", "completed"),
        ("completed", "data_ready"),
    ),
)
def test_illegal_transition_is_rejected(source: str, target: str) -> None:
    """Break caught: a caller jumps forward or rewinds workflow evidence."""
    from empirical_macro.state_machine import transition_state

    state = state_at(source)
    with pytest.raises(ValueError, match="illegal workflow transition"):
        transition_state(
            state,
            target_stage=target,
            artifact_refs=(),
        )


def test_success_transition_requires_new_artifact_refs() -> None:
    """Break caught: a stage advances without binding new evidence."""
    from empirical_macro.state_machine import transition_state

    with pytest.raises(ValueError, match="artifact refs are required"):
        transition_state(
            initial_state(),
            target_stage="design_ready",
            artifact_refs=(),
        )


@pytest.mark.parametrize(("target", "status"), (("blocked", "blocked"), ("failed", "failed")))
def test_failure_transition_is_terminal(target: str, status: str) -> None:
    """Break caught: a failed workflow remains eligible for silent resume."""
    from empirical_macro.state_machine import transition_state

    state = transition_state(
        state_at("data_ready"),
        target_stage=target,
        artifact_refs=(),
        issue_codes=("upstream_validation_failed",),
    )
    assert state.current_stage == target
    assert state.status == status
    assert state.resume_eligible is False
    with pytest.raises(ValueError, match="illegal workflow transition"):
        transition_state(
            state,
            target_stage="estimation_ready",
            artifact_refs=artifact_refs_for("estimation_ready"),
        )
