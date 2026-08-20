from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import (
    RecordingRunner,
    initial_state,
    recording_commands,
    recording_validators,
    run_supported_gold,
)


def test_unsupported_method_executes_no_skill() -> None:
    """Break caught: an unsupported method starts any atomic Skill."""
    from empirical_macro.models import ResearchIntent
    from empirical_macro.orchestrator import run_intent

    runner = RecordingRunner()
    result = run_intent(
        intent=ResearchIntent(
            domain="empirical_macro",
            request_kind="final_report",
            method_family="panel_association",
            has_research_plan=True,
            has_macro_data_bundle=True,
            has_estimator_bundle=True,
            has_robustness_bundle=True,
            has_workflow_state=False,
        ),
        runner=runner,
    )
    assert runner.calls == []
    assert result.user_message == "当前版本不能执行该方法"
    assert result.artifact_outputs == ()
    assert result.state is None


def test_supported_workflow_executes_in_frozen_order(tmp_path: Path) -> None:
    """Break caught: a supported workflow omits or reorders an atomic Skill."""
    runner = RecordingRunner(tmp_path)
    result = run_supported_gold(runner)
    assert runner.skills == [
        "research-design",
        "macro-data",
        "time-series-dynamics",
        "robustness-audit",
        "research-synthesis",
    ]
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


def test_macro_data_failure_stops_before_estimation(tmp_path: Path) -> None:
    """Break caught: downstream estimation runs after the data gate rejects."""
    from empirical_macro.models import ResearchIntent
    from empirical_macro.orchestrator import run_intent

    runner = RecordingRunner(tmp_path)
    result = run_intent(
        intent=ResearchIntent(
            domain="empirical_macro",
            request_kind="final_report",
            method_family="dynamic_shock_response",
            has_research_plan=False,
            has_macro_data_bundle=False,
            has_estimator_bundle=False,
            has_robustness_bundle=False,
            has_workflow_state=False,
        ),
        runner=runner,
        commands=recording_commands(),
        project_root=tmp_path,
        run_until="completed",
        validators=recording_validators(tmp_path, invalid_skill="macro-data"),
    )
    assert runner.skills == ["research-design", "macro-data"]
    assert result.state is not None
    assert result.state.current_stage == "blocked"
    assert "macro_bundle_not_analysis_ready" in result.state.issue_codes
    assert result.stopped_reason == "macro_bundle_not_analysis_ready"


def test_next_mode_executes_at_most_one_external_stage(tmp_path: Path) -> None:
    """Break caught: the safe default executes a full workflow in one call."""
    from empirical_macro.models import ResearchIntent
    from empirical_macro.orchestrator import run_intent

    runner = RecordingRunner(tmp_path)
    result = run_intent(
        intent=ResearchIntent(
            domain="empirical_macro",
            request_kind="final_report",
            method_family="conditional_dynamic_association",
            has_research_plan=False,
            has_macro_data_bundle=False,
            has_estimator_bundle=False,
            has_robustness_bundle=False,
            has_workflow_state=False,
        ),
        runner=runner,
        commands=recording_commands(),
        project_root=tmp_path,
        run_until="next",
        validators=recording_validators(tmp_path),
    )
    assert runner.skills == ["research-design"]
    assert result.executed_stages == ("design_ready",)


def test_non_design_route_without_state_does_not_execute_wrong_stage() -> None:
    """Break caught: a data-only request incorrectly starts research-design."""
    from empirical_macro.models import ResearchIntent
    from empirical_macro.orchestrator import run_intent

    runner = RecordingRunner()
    result = run_intent(
        intent=ResearchIntent(
            domain="empirical_macro",
            request_kind="data_preparation",
            method_family="conditional_dynamic_association",
            has_research_plan=False,
            has_macro_data_bundle=False,
            has_estimator_bundle=False,
            has_robustness_bundle=False,
            has_workflow_state=False,
        ),
        runner=runner,
        commands=recording_commands(),
        run_until="completed",
    )
    assert runner.calls == []
    assert result.route_decision.action == "route_macro_data"
    assert result.stopped_reason == "route_only"


def test_stage_command_must_use_frozen_atomic_skill(tmp_path: Path) -> None:
    """Break caught: macro-data is accepted as the research-design executor."""
    from empirical_macro.orchestrator import StageCommand, run_next_stage

    state = initial_state()
    commands = recording_commands()
    commands["design_ready"] = StageCommand(
        stage="design_ready",
        skill="macro-data",
        command=("record", "macro-data"),
        expected_artifacts=("artifacts/design_ready/result.json",),
    )
    with pytest.raises(ValueError, match="stage skill mismatch"):
        run_next_stage(
            state=state,
            commands=commands,
            project_root=Path("."),
            output_root=Path("."),
            runner=RecordingRunner(),
            validators=recording_validators(tmp_path),
        )


def test_stage_execution_requires_validator_commands() -> None:
    """Break caught: a library caller advances workflow with self-reported refs."""
    from empirical_macro.orchestrator import run_next_stage

    runner = RecordingRunner()
    with pytest.raises(ValueError, match="validator commands are required"):
        run_next_stage(
            state=initial_state(),
            commands=recording_commands(),
            project_root=Path("."),
            output_root=Path("."),
            runner=runner,
        )
    assert runner.calls == []


def test_existing_state_method_must_match_intent(tmp_path: Path) -> None:
    """Break caught: a supported intent executes an unsupported saved method."""
    from dataclasses import replace

    from empirical_macro.models import ResearchIntent
    from empirical_macro.orchestrator import run_intent

    state = replace(
        initial_state(),
        supported_method="panel_association",
    )
    runner = RecordingRunner(tmp_path)
    with pytest.raises(ValueError, match="workflow method mismatch"):
        run_intent(
            intent=ResearchIntent(
                domain="empirical_macro",
                request_kind="resume",
                method_family="dynamic_shock_response",
                has_research_plan=True,
                has_macro_data_bundle=True,
                has_estimator_bundle=False,
                has_robustness_bundle=False,
                has_workflow_state=True,
            ),
            runner=runner,
            state=state,
            commands=recording_commands(),
            project_root=tmp_path,
            validators=recording_validators(tmp_path),
        )
    assert runner.calls == []


def test_existing_state_requires_declared_resume_intent(tmp_path: Path) -> None:
    """Break caught: an undeclared state overrides a fresh user request."""
    from empirical_macro.models import ResearchIntent
    from empirical_macro.orchestrator import run_intent

    with pytest.raises(ValueError, match="workflow state declaration mismatch"):
        run_intent(
            intent=ResearchIntent(
                domain="empirical_macro",
                request_kind="final_report",
                method_family="dynamic_shock_response",
                has_research_plan=True,
                has_macro_data_bundle=True,
                has_estimator_bundle=False,
                has_robustness_bundle=False,
                has_workflow_state=False,
            ),
            runner=RecordingRunner(tmp_path),
            state=initial_state(),
            commands=recording_commands(),
            project_root=tmp_path,
            validators=recording_validators(tmp_path),
        )


def test_existing_state_requires_cumulative_stage_evidence(tmp_path: Path) -> None:
    """Break caught: audit-ready state has no evidence from earlier stages."""
    from dataclasses import replace

    from empirical_macro.models import ResearchIntent
    from empirical_macro.orchestrator import run_intent
    from tests.helpers import state_at

    state = replace(state_at("audit_ready"), artifact_refs=())
    with pytest.raises(ValueError, match="stage is not checkpoint eligible"):
        run_intent(
            intent=ResearchIntent(
                domain="empirical_macro",
                request_kind="resume",
                method_family="dynamic_shock_response",
                has_research_plan=True,
                has_macro_data_bundle=True,
                has_estimator_bundle=True,
                has_robustness_bundle=True,
                has_workflow_state=True,
            ),
            runner=RecordingRunner(tmp_path),
            state=state,
            commands=recording_commands(),
            project_root=tmp_path,
            validators=recording_validators(tmp_path),
        )


def test_completed_state_requires_all_stage_evidence(tmp_path: Path) -> None:
    """Break caught: an empty completed state is accepted as a research result."""
    from dataclasses import replace

    from empirical_macro.models import ResearchIntent
    from empirical_macro.orchestrator import run_intent
    from tests.helpers import state_at

    state = replace(state_at("completed"), artifact_refs=())
    with pytest.raises(ValueError, match="stage is not checkpoint eligible"):
        run_intent(
            intent=ResearchIntent(
                domain="empirical_macro",
                request_kind="resume",
                method_family="dynamic_shock_response",
                has_research_plan=True,
                has_macro_data_bundle=True,
                has_estimator_bundle=True,
                has_robustness_bundle=True,
                has_workflow_state=True,
            ),
            runner=RecordingRunner(tmp_path),
            state=state,
            commands=recording_commands(),
            project_root=tmp_path,
            validators=recording_validators(tmp_path),
        )


def test_nonzero_stage_exit_transitions_to_failed(tmp_path: Path) -> None:
    """Break caught: an execution failure is mislabeled as missing evidence."""
    from empirical_macro.models import ResearchIntent
    from empirical_macro.orchestrator import run_intent

    runner = RecordingRunner(tmp_path, fail_skill="research-design")
    result = run_intent(
        intent=ResearchIntent(
            domain="empirical_macro",
            request_kind="final_report",
            method_family="dynamic_shock_response",
            has_research_plan=False,
            has_macro_data_bundle=False,
            has_estimator_bundle=False,
            has_robustness_bundle=False,
            has_workflow_state=False,
        ),
        runner=runner,
        commands=recording_commands(),
        project_root=tmp_path,
        validators=recording_validators(tmp_path),
    )
    assert result.state is not None
    assert result.state.current_stage == "failed"
    assert result.state.status == "failed"


def test_stage_runner_exception_transitions_to_failed(tmp_path: Path) -> None:
    """Break caught: a process startup error escapes without a failed state."""
    from empirical_macro.orchestrator import run_next_stage

    class RaisingRunner:
        def run(self, command: object) -> object:
            raise OSError("injected startup failure")

    result = run_next_stage(
        state=initial_state(),
        commands=recording_commands(),
        project_root=tmp_path,
        output_root=tmp_path,
        runner=RaisingRunner(),  # type: ignore[arg-type]
        validators=recording_validators(tmp_path),
    )
    assert result.state is not None
    assert result.state.current_stage == "failed"


def test_missing_stage_validator_transitions_to_failed(tmp_path: Path) -> None:
    """Break caught: incomplete validator configuration silently advances."""
    from empirical_macro.orchestrator import run_next_stage

    result = run_next_stage(
        state=initial_state(),
        commands=recording_commands(),
        project_root=tmp_path,
        output_root=tmp_path,
        runner=RecordingRunner(tmp_path),
        validators={},
    )
    assert result.state is not None
    assert result.state.current_stage == "failed"


def test_validator_process_error_transitions_to_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Break caught: validator startup failure escapes without a failed state."""
    import empirical_macro.orchestrator as orchestrator

    def fail_validation(**kwargs: object) -> dict[str, object]:
        raise OSError("injected validator failure")

    monkeypatch.setattr(orchestrator, "validate_artifact_ref", fail_validation)
    result = orchestrator.run_next_stage(
        state=initial_state(),
        commands=recording_commands(),
        project_root=tmp_path,
        output_root=tmp_path,
        runner=RecordingRunner(tmp_path),
        validators=recording_validators(tmp_path),
    )
    assert result.state is not None
    assert result.state.current_stage == "failed"
