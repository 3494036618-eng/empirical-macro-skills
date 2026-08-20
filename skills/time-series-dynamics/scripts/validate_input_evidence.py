#!/usr/bin/env python3
"""验证估计器 input-evidence bundle。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from time_series_dynamics.input_evidence import validate_input_evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    result = validate_input_evidence(args.bundle)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
