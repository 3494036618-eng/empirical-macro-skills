from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from robustness_audit.check_builder import build_check_results
from robustness_audit.plan_compiler import compile_audit_plan

ROOT = Path(__file__).resolve().parents[1]
TIME_SERIES_ROOT = ROOT.parent / "time-series-dynamics"


def _load(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def test_check_builder_rejects_missing_alternative_execution_records() -> None:
    baseline = _load(
        TIME_SERIES_ROOT / "fixtures" / "synthetic" / "jel.causal.request.json"
    )
    handoff = _load(
        ROOT / "fixtures" / "external" / "jel-example5.robustness-handoff.json"
    )
    plan = compile_audit_plan(
        _load(ROOT / "fixtures" / "external" / "jel-example5.audit-request.json"),
        handoff,
        baseline,
        _load(ROOT / "fixtures" / "synthetic" / "adapter-capability.json"),
    )

    with pytest.raises(ValueError, match="alternative_set_mismatch"):
        build_check_results(
            plan,
            handoff,
            {"horizon_results": []},
            {"status": "passed", "issue_codes": []},
            (),
        )
