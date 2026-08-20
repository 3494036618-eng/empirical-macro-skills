from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import state_at, write_valid_state_and_artifact


def test_checkpoint_identity_is_deterministic() -> None:
    """Break caught: identical evidence creates different checkpoint IDs."""
    from empirical_macro.checkpoint import create_checkpoint

    first = create_checkpoint(state_at("data_ready"))
    second = create_checkpoint(state_at("data_ready"))
    assert first == second
    assert first.checkpoint_id.startswith("checkpoint-")


def test_resume_rejects_tampered_artifact(tmp_path: Path) -> None:
    """Break caught: resume accepts bytes that no longer match the state."""
    from empirical_macro.checkpoint import resume_workflow

    state_path = write_valid_state_and_artifact(tmp_path)
    (tmp_path / "artifacts" / "result.json").write_text(
        '{"tampered": true}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="checksum mismatch"):
        resume_workflow(
            state_path=state_path,
            project_root=tmp_path,
            registry_version="dynamic-beta-v1",
        )


def test_resume_rejects_capability_registry_drift(tmp_path: Path) -> None:
    """Break caught: resume executes under a different capability allowlist."""
    from empirical_macro.checkpoint import resume_workflow

    state_path = write_valid_state_and_artifact(tmp_path)
    with pytest.raises(ValueError, match="registry version mismatch"):
        resume_workflow(
            state_path=state_path,
            project_root=tmp_path,
            registry_version="different-version",
        )


def test_resume_rejects_state_tamper(tmp_path: Path) -> None:
    """Break caught: workflow state changes without a new checkpoint identity."""
    from empirical_macro.checkpoint import resume_workflow

    state_path = write_valid_state_and_artifact(tmp_path)
    content = state_path.read_text(encoding="utf-8")
    state_path.write_text(
        content.replace("request-12345678", "request-87654321"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="checkpoint identity mismatch"):
        resume_workflow(
            state_path=state_path,
            project_root=tmp_path,
            registry_version="dynamic-beta-v1",
        )


def test_transaction_failure_preserves_previous_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Break caught: a failed replace corrupts the last valid checkpoint."""
    import empirical_macro.checkpoint as checkpoint_module
    from empirical_macro.checkpoint import write_state_transactionally

    state_path = tmp_path / "workflow-state.json"
    previous = b'{"previous": true}\n'
    state_path.write_bytes(previous)

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(checkpoint_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        write_state_transactionally(state_at("data_ready"), state_path)
    assert state_path.read_bytes() == previous
    assert list(tmp_path.glob(".workflow-state.json.staging-*")) == []


def test_active_state_is_bound_to_checkpoint_before_persistence() -> None:
    """Break caught: a CLI-written active state cannot be resumed."""
    from empirical_macro.checkpoint import (
        create_checkpoint,
        prepare_state_for_persistence,
    )

    state = state_at("data_ready")
    prepared = prepare_state_for_persistence(state)
    assert prepared.resume_eligible is True
    assert prepared.checkpoint_id == create_checkpoint(prepared).checkpoint_id


def test_checkpoint_rejects_stage_with_incomplete_evidence() -> None:
    """Break caught: a data_ready checkpoint omits macro-data evidence."""
    from dataclasses import replace

    from empirical_macro.checkpoint import create_checkpoint

    state = state_at("data_ready")
    incomplete = replace(
        state,
        artifact_refs=(state.artifact_refs[0],),
    )
    with pytest.raises(ValueError, match="stage evidence incomplete"):
        create_checkpoint(incomplete)


def test_resume_requires_public_validators(tmp_path: Path) -> None:
    """Break caught: resume accepts a checksum-only bundle without validation."""
    from empirical_macro.checkpoint import resume_workflow

    state_path = write_valid_state_and_artifact(tmp_path)
    with pytest.raises(ValueError, match="validator commands are required"):
        resume_workflow(
            state_path=state_path,
            project_root=tmp_path,
            registry_version="dynamic-beta-v1",
        )
