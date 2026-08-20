"""Run macro-data from a sanitized fixture or an explicitly enabled live call."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from macro_data.connectors.datapro import DataProConnector
from macro_data.connectors.world_bank import WorldBankConnector
from macro_data.pipeline import run_macro_data_request, run_with_connector
from macro_data.request_loader import load_request_json
from macro_data.request_parser import parse_research_request


def _prepare_request(text: str, source: str) -> dict[str, Any]:
    request = parse_research_request(text)
    if source == "world_bank":
        request["preferred_sources"].append("world_bank")
        request["fallback_policy"] = {
            "mode": "allow_official",
            "allowed_sources": ["world_bank"],
            "allow_semantic_substitute": False,
            "allow_cross_source_stitching": False,
        }
    return request


def main() -> int:
    parser = argparse.ArgumentParser()
    request_group = parser.add_mutually_exclusive_group(required=True)
    request_group.add_argument("--request")
    request_group.add_argument("--request-json", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--source",
        choices=("datapro", "world_bank"),
        default="datapro",
    )
    args = parser.parse_args()

    if bool(args.fixture) == bool(args.live):
        parser.error("choose exactly one of --fixture or --live")
    if args.fixture and args.source != "datapro":
        parser.error("saved fixtures currently support only --source datapro")

    request = (
        load_request_json(args.request_json)
        if args.request_json
        else _prepare_request(args.request, args.source)
    )
    if args.fixture:
        source_payload = json.loads(args.fixture.read_text(encoding="utf-8"))
        input_mode = "sanitized-live-replay"
        result = run_macro_data_request(
            request=request,
            source_payload=source_payload,
            output_dir=args.output,
            input_mode=input_mode,
        )
    else:
        input_mode = "live"
        connector = WorldBankConnector() if args.source == "world_bank" else DataProConnector()
        result = run_with_connector(
            request=request,
            connector=connector,
            output_dir=args.output,
            input_mode=input_mode,
        )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "execution_status": result["execution_status"],
                "research_readiness": result["research_readiness"],
                "delivery_eligibility": result["delivery_eligibility"],
                "eligible_for_estimation": result["eligible_for_estimation"],
                "issue_codes": result["issue_codes"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
