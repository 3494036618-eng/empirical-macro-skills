"""Import a checksum-pinned public research artifact into macro-data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from macro_data.public_artifact_import import import_public_artifact_bundle


def _load(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return cast(dict[str, Any], document)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-json", type=Path, required=True)
    parser.add_argument("--artifact-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = import_public_artifact_bundle(
            request=_load(args.request_json),
            manifest_path=args.artifact_json,
            output_dir=args.output,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"public research artifact import failed: {exc}", file=sys.stderr)
        return 1
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
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
