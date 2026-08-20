"""Inspect a saved fixture or explicitly execute one DataPro query."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from macro_data.connectors.datapro import DataProConnector


def _summary(payload: dict[str, Any]) -> dict[str, object]:
    response = payload.get("response", payload)
    return {
        "fixture_type": payload.get("fixture_type", "live"),
        "provider_code": response.get("code"),
        "message": response.get("msg"),
        "dataset_type": response.get("dataset_type"),
        "item_count": len(response.get("items") or []),
        "item_fields": sorted(
            {key for item in response.get("items") or [] if isinstance(item, dict) for key in item}
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect-fixture", type=Path)
    parser.add_argument("--query")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.inspect_fixture:
        if args.query or args.live:
            parser.error("--inspect-fixture cannot be combined with live query options")
        payload = json.loads(args.inspect_fixture.read_text(encoding="utf-8"))
    elif args.query:
        if not args.live:
            parser.error("--live is required for a DataPro network call")
        payload = DataProConnector().search(args.query)
        if args.output:
            args.output.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    else:
        parser.error("provide --inspect-fixture or --query with --live")

    print(json.dumps(_summary(payload), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
