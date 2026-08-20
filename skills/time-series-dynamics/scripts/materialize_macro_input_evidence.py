"""Materialize association evidence from a validated macro-data bundle."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

from time_series_dynamics.macro_input_evidence import (
    materialize_macro_input_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
MACRO_ROOT = ROOT.parent / "macro-data"


def _load(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError(f"{path.name} must contain a JSON object")
    return cast(dict[str, object], document)


def _validate_macro_bundle(bundle: Path) -> None:
    python = MACRO_ROOT / ".venv" / "bin" / "python"
    if not python.is_file():
        raise ValueError("macro_data_validator_python_missing")
    environment = dict(os.environ)
    environment.pop("VIRTUAL_ENV", None)
    completed = subprocess.run(  # noqa: S603
        [
            str(python),
            str(MACRO_ROOT / "scripts" / "validate_bundle.py"),
            str(bundle),
        ],
        cwd=MACRO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        raise ValueError("macro_data_bundle_validation_failed")
    result = json.loads(completed.stdout)
    if not isinstance(result, dict) or result.get("valid") is not True:
        raise ValueError("macro_data_bundle_validation_failed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--macro-bundle", type=Path, required=True)
    parser.add_argument("--request-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        _validate_macro_bundle(args.macro_bundle)
        result = materialize_macro_input_evidence(
            args.macro_bundle,
            _load(args.request_json),
            args.output,
        )
    except (
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(f"macro input-evidence 物化失败: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
