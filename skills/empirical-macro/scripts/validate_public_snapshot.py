#!/usr/bin/env python3
"""Validate public snapshot structure, privacy, and license status."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from empirical_macro.public_snapshot import validate_public_snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    report = validate_public_snapshot(args.snapshot)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
