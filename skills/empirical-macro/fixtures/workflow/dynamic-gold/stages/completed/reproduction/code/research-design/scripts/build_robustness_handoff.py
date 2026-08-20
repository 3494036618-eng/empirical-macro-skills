#!/usr/bin/env python3
"""Build a validated robustness-audit handoff from research-design artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import cast

from research_design.robustness_handoff import build_robustness_handoff


def _load_object(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _load_checks(path: Path) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], json.loads(path.read_text(encoding="utf-8")))


def _write_atomic(path: Path, document: dict[str, object]) -> None:
    payload = (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-plan-json", type=Path, required=True)
    parser.add_argument("--identification-audit-json", type=Path, required=True)
    parser.add_argument("--declared-checks-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = build_robustness_handoff(
            _load_object(args.research_plan_json),
            _load_object(args.identification_audit_json),
            _load_checks(args.declared_checks_json),
        )
        _write_atomic(args.output, document)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"robustness handoff failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "handoff_id": document["handoff_id"],
                "checksum": document["checksum"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
