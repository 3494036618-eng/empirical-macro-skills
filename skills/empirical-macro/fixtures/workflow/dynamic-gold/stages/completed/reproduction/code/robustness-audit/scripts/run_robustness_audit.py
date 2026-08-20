#!/usr/bin/env python3
"""Run a declared robustness audit and publish its result bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from robustness_audit.pipeline import run_robustness_audit


def _load(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-request-json", type=Path, required=True)
    parser.add_argument("--audit-plan-json", type=Path, required=True)
    parser.add_argument("--handoff-json", type=Path, required=True)
    parser.add_argument("--baseline-bundle", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--research-plan", type=Path, required=True)
    parser.add_argument("--macro-result", type=Path, required=True)
    parser.add_argument("--shock-artifact", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--adapter-capability-json", type=Path, required=True)
    parser.add_argument("--adapter-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    input_paths = {
        "request": args.request,
        "research_plan": args.research_plan,
        "macro_data": args.macro_result,
        "shock_artifact": args.shock_artifact,
        "data": args.data,
    }
    try:
        result = run_robustness_audit(
            _load(args.audit_request_json),
            _load(args.audit_plan_json),
            _load(args.handoff_json),
            args.baseline_bundle,
            input_paths,
            _load(args.adapter_capability_json),
            args.adapter_root,
            args.output,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"robustness audit failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
