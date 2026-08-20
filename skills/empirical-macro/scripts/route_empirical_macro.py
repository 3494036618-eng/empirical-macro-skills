#!/usr/bin/env python3
"""Route a validated empirical-macro intent without executing a Skill."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from empirical_macro.contracts import validate_document
from empirical_macro.intent_io import load_research_intent
from empirical_macro.router import route_intent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intent-json", type=Path, required=True)
    args = parser.parse_args()
    decision = route_intent(load_research_intent(args.intent_json))
    document: dict[str, object] = {
        "schema_version": "0.1.0-beta",
        "action": decision.action,
        "target_skill": decision.target_skill,
        "issue_codes": list(decision.issue_codes),
        "user_message": decision.user_message,
    }
    validate_document("route_decision", document)
    print(json.dumps(document, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
