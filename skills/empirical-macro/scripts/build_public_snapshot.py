#!/usr/bin/env python3
"""Build the portable six-Skill public snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from empirical_macro.public_snapshot import build_public_snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_public_snapshot(
        project_root=args.project_root,
        output_dir=args.output,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
