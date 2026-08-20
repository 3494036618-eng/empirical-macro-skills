#!/usr/bin/env python3
"""Compile a validated audit plan without reading baseline result values."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import cast

from robustness_audit.plan_compiler import compile_audit_plan


def _load(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


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
    parser.add_argument("--audit-request-json", type=Path, required=True)
    parser.add_argument("--handoff-json", type=Path, required=True)
    parser.add_argument("--baseline-request-json", type=Path, required=True)
    parser.add_argument("--adapter-capability-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = compile_audit_plan(
            _load(args.audit_request_json),
            _load(args.handoff_json),
            _load(args.baseline_request_json),
            _load(args.adapter_capability_json),
        )
        _write_atomic(args.output, document)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"audit plan compilation failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "audit_plan_id": document["audit_plan_id"],
                "alternatives": len(cast(list[object], document["alternatives"])),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
