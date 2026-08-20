#!/usr/bin/env python3
"""运行 research-synthesis 并生成唯一中文研究报告。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from research_synthesis.pipeline import run_research_synthesis


def _load(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} 必须包含 JSON object")
    return cast(dict[str, object], document)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-json", type=Path, required=True)
    parser.add_argument(
        "--adapter-capabilities-json",
        type=Path,
        required=True,
    )
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run_research_synthesis(
            _load(args.request_json),
            _load(args.adapter_capabilities_json),
            args.project_root,
            args.output,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"research-synthesis 运行失败: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["execution_status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
