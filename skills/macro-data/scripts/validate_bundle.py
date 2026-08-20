"""Validate required artifacts, checksums, and secret absence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from macro_data.exporter import validate_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()

    result = validate_bundle(args.bundle)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
