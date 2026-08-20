#!/usr/bin/env python3
"""Plan or execute three-host routing acceptance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from empirical_macro.agent_acceptance import score_host_results, write_budget_plan


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host-config", type=Path)
    parser.add_argument("--host", choices=("trae", "codex", "claude-code"))
    parser.add_argument("--gold-cases", type=Path)
    parser.add_argument("--host-results", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--approved", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.dry_run:
        plan = write_budget_plan(snapshot=args.snapshot, output_dir=args.output)
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        return 0
    if not args.approved:
        print("explicit model-call approval required", file=sys.stderr)
        return 2
    if (
        args.host is not None
        and args.gold_cases is not None
        and args.host_results is not None
    ):
        report = score_host_results(
            gold_cases_path=args.gold_cases,
            results_dir=args.host_results,
            host=args.host,
        )
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / f"{args.host}-summary.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if report["status"] == "passed" else 1
    if args.host_config is None:
        print("approved execution requires --host-config", file=sys.stderr)
        return 2
    print("actual host execution is pending configured approval", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
