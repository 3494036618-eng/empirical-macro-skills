#!/usr/bin/env python3
"""验证 research-synthesis research package。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_synthesis.exporter import validate_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    result = validate_bundle(args.bundle)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
