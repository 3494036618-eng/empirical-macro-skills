#!/usr/bin/env python3
"""Validate a saved workflow state before further execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from empirical_macro.capability_registry import registry_version
from empirical_macro.checkpoint import resume_workflow, state_to_document
from empirical_macro.validation import load_validator_commands

SKILL_SUITE_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow-state", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    validators = load_validator_commands(SKILL_SUITE_ROOT)
    state = resume_workflow(
        state_path=args.workflow_state,
        project_root=args.project_root,
        registry_version=registry_version(),
        validators=validators,
    )
    print(json.dumps(state_to_document(state), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
