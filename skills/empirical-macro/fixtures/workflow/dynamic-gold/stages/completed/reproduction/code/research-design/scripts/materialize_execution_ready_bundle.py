#!/usr/bin/env python3
"""Materialize an approved execution-ready research design bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from research_design.execution_ready_bundle import (
    materialize_execution_ready_bundle,
)


def _load(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return cast(dict[str, object], document)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intake-json", type=Path, required=True)
    parser.add_argument("--request-json", type=Path, required=True)
    parser.add_argument("--research-plan-json", type=Path, required=True)
    parser.add_argument("--identification-audit-json", type=Path)
    parser.add_argument("--data-requirements-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = materialize_execution_ready_bundle(
            _load(args.intake_json),
            _load(args.request_json),
            _load(args.research_plan_json),
            (
                _load(args.identification_audit_json)
                if args.identification_audit_json
                else None
            ),
            _load(args.data_requirements_json),
            args.output,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"execution-ready materialization failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
