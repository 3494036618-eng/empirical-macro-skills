"""Run a validated time-series-dynamics request."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from time_series_dynamics.pipeline import run_time_series_dynamics


def _load(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-json", required=True, type=Path)
    parser.add_argument("--research-plan-json", required=True, type=Path)
    parser.add_argument("--macro-result-json", required=True, type=Path, action="append")
    parser.add_argument("--shock-artifact-json", type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    shock = _load(args.shock_artifact_json) if args.shock_artifact_json else None
    result = run_time_series_dynamics(
        _load(args.request_json),
        _load(args.research_plan_json),
        [_load(path) for path in args.macro_result_json],
        args.data,
        args.output,
        shock,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
