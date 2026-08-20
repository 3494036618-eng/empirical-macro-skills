#!/usr/bin/env python3
"""Materialize identified-shock evidence from public macro-data output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from time_series_dynamics.public_input_evidence import (
    materialize_public_input_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--macro-bundle", type=Path, required=True)
    parser.add_argument("--public-artifact-json", type=Path, required=True)
    parser.add_argument("--shock-artifact-json", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = materialize_public_input_evidence(
            macro_bundle=args.macro_bundle,
            public_manifest_path=args.public_artifact_json,
            shock_artifact_path=args.shock_artifact_json,
            data_path=args.data,
            output_dir=args.output,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"public input-evidence materialization failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
