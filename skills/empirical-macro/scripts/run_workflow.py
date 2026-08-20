#!/usr/bin/env python3
"""Run one or more approved empirical-macro workflow stages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from empirical_macro.capability_registry import registry_version
from empirical_macro.checkpoint import (
    prepare_state_for_persistence,
    resume_workflow,
    write_state_transactionally,
)
from empirical_macro.intent_io import load_research_intent
from empirical_macro.models import WorkflowStage
from empirical_macro.orchestrator import (
    RunUntil,
    StageCommand,
    SubprocessStageRunner,
    run_intent,
)
from empirical_macro.validation import load_validator_commands

SKILL_SUITE_ROOT = Path(__file__).resolve().parents[2]


def _commands(path: Path | None) -> dict[WorkflowStage, StageCommand] | None:
    if path is None:
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    items = cast(list[dict[str, object]], document["commands"])
    return {
        cast(WorkflowStage, item["stage"]): StageCommand(
            stage=cast(WorkflowStage, item["stage"]),
            skill=cast(str, item["skill"]),
            command=tuple(cast(list[str], item["command"])),
            expected_artifacts=tuple(cast(list[str], item["expected_artifacts"])),
        )
        for item in items
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intent-json", type=Path, required=True)
    parser.add_argument("--workflow-state", type=Path)
    parser.add_argument("--commands-json", type=Path)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--run-until",
        choices=("blocked", "completed", "next"),
        default="next",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    intent = load_research_intent(args.intent_json)
    validators = load_validator_commands(SKILL_SUITE_ROOT)
    state = (
        resume_workflow(
            state_path=args.workflow_state,
            project_root=args.project_root,
            registry_version=registry_version(),
            validators=validators,
        )
        if args.workflow_state is not None
        else None
    )
    result = run_intent(
        intent=intent,
        runner=SubprocessStageRunner(),
        state=state,
        commands=_commands(args.commands_json),
        project_root=args.project_root,
        output_root=args.output,
        run_until=cast(RunUntil, args.run_until),
        validators=validators,
    )
    if result.user_message is not None:
        print(result.user_message)
        return 2
    if result.state is not None and result.stopped_reason != "route_only":
        persisted_state = prepare_state_for_persistence(result.state)
        args.output.mkdir(parents=True, exist_ok=True)
        write_state_transactionally(
            persisted_state,
            args.output / "workflow-state.json",
        )
    document: dict[str, object]
    if not result.executed_stages:
        document = {
            "action": result.route_decision.action,
            "executed": False,
            "target_skill": result.route_decision.target_skill,
        }
    else:
        document = {
            "action": result.route_decision.action,
            "artifact_outputs": list(result.artifact_outputs),
            "current_stage": result.state.current_stage if result.state else None,
            "executed_stages": list(result.executed_stages),
            "stopped_reason": result.stopped_reason,
        }
    print(json.dumps(document, ensure_ascii=False, sort_keys=True))
    return 0 if result.stopped_reason in {None, "route_only"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
