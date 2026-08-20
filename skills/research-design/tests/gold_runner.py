from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from research_design.pipeline import run_research_design


def _load(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def run_gold(
    case_dir: Path,
    output_dir: Path,
    macro_schema_path: Path,
) -> dict[str, object]:
    summary = run_research_design(
        _load(case_dir / "intake.json"),
        _load(case_dir / "request.json"),
        output_dir,
        macro_schema_path,
    )
    plan = _load(output_dir / "research_plan.json")
    return {
        "family": plan["research_family"],
        "claim_eligibility": plan["claim_eligibility"],
        "design_readiness": plan["design_readiness"],
        "issue_codes": summary["issue_codes"],
    }
