#!/usr/bin/env python3
"""Compile validated research intake and request documents into an audit bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from research_design.pipeline import run_research_design


def _load_document(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intake-json", type=Path, required=True)
    parser.add_argument("--request-json", type=Path, required=True)
    parser.add_argument("--macro-schema", type=Path, required=True)
    parser.add_argument("--macro-request-json", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        result = run_research_design(
            _load_document(args.intake_json),
            _load_document(args.request_json),
            args.output,
            args.macro_schema,
            macro_request_document=(
                _load_document(args.macro_request_json)
                if args.macro_request_json
                else None
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"research-design failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
