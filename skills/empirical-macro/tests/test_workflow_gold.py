from __future__ import annotations

from pathlib import Path

import pytest


def test_dynamic_gold_reaches_completed_with_all_checkpoints(
    tmp_path: Path,
) -> None:
    """Break caught: the supported Gold cannot reach a complete research package."""
    from tests.workflow_gold_helpers import run_gold_workflow

    result = run_gold_workflow(tmp_path)
    assert result.state is not None
    assert result.state.current_stage == "completed"
    assert result.executed_stages == (
        "design_ready",
        "data_ready",
        "estimation_ready",
        "audit_ready",
        "synthesis_ready",
        "completed",
    )
    assert (tmp_path / "research-report.md").is_file()
    assert (tmp_path / "tables").is_dir()
    assert (tmp_path / "figures").is_dir()
    assert (tmp_path / "reproduction").is_dir()
    assert (tmp_path / "figures" / "dynamic-path.png").stat().st_size > 1024


@pytest.mark.parametrize(
    "mutation",
    (
        "macro_checksum_mismatch",
        "shock_artifact_missing",
        "estimator_result_tamper",
        "required_robustness_check_missing",
        "synthesis_manifest_mismatch",
    ),
)
def test_dynamic_gold_mutations_fail_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    """Break caught: tampered upstream evidence still publishes a report."""
    from tests.workflow_gold_helpers import run_gold_workflow

    result = run_gold_workflow(tmp_path, mutation=mutation)
    assert result.state is not None
    assert result.state.status == "blocked"
    assert not (tmp_path / "research-report.md").exists()


def test_dynamic_gold_resume_does_not_repeat_completed_stages(
    tmp_path: Path,
) -> None:
    """Break caught: resume reruns design or data after their checkpoint."""
    from tests.workflow_gold_helpers import run_gold_resume

    result, resumed_skills = run_gold_resume(tmp_path)
    assert resumed_skills == [
        "time-series-dynamics",
        "robustness-audit",
        "research-synthesis",
    ]
    assert result.state is not None
    assert result.state.current_stage == "completed"
    assert (tmp_path / "research-report.md").is_file()


def test_dynamic_gold_scientific_content_id_is_stable(tmp_path: Path) -> None:
    """Break caught: identical frozen evidence produces different content."""
    from tests.workflow_gold_helpers import gold_content_id, run_gold_workflow

    first = tmp_path / "first"
    second = tmp_path / "second"
    run_gold_workflow(first)
    run_gold_workflow(second)
    assert gold_content_id(first) == gold_content_id(second)
