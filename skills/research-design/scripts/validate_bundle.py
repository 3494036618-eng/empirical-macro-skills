#!/usr/bin/env python3
"""Validate a research-design bundle through its public CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_design.exporter import validate_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    result = validate_bundle(args.bundle)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
