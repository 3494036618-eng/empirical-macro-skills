"""Validate an exported time-series-dynamics bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from time_series_dynamics.exporter import validate_bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    result = validate_bundle(args.bundle)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if result["valid"] is not True:
        sys.exit(1)


if __name__ == "__main__":
    main()
