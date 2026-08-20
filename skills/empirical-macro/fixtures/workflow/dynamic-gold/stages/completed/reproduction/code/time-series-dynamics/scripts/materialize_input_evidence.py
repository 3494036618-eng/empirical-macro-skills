#!/usr/bin/env python3
"""物化估计器实际使用的数据、冲击和来源证据。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from time_series_dynamics.input_evidence import materialize_input_evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--macro-handoff-json", type=Path, required=True)
    parser.add_argument("--shock-artifact-json", type=Path, required=True)
    parser.add_argument("--source-manifest-json", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = materialize_input_evidence(
            args.macro_handoff_json,
            args.shock_artifact_json,
            args.source_manifest_json,
            args.data,
            args.output,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"input-evidence 物化失败: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
