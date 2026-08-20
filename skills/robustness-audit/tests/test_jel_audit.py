from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from robustness_audit.exporter import validate_bundle

ROOT = Path(__file__).resolve().parents[1]
TIME_SERIES_ROOT = ROOT.parent / "time-series-dynamics"
AUDIT_BUNDLE = ROOT / ".artifacts" / "jel-example5-robustness"


def _load_object(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _load_array(path: Path) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], json.loads(path.read_text(encoding="utf-8")))


def _family(
    checks: list[dict[str, object]],
    name: str,
) -> dict[str, object]:
    return next(item for item in checks if item["check_family"] == name)


def test_real_jel_audit_preserves_declared_scope_and_matches_manual_metric() -> None:
    assert validate_bundle(AUDIT_BUNDLE) == {"valid": True, "errors": []}
    result = _load_object(AUDIT_BUNDLE / "audit-result.json")
    plan = _load_object(AUDIT_BUNDLE / "audit-plan.json")
    checks = _load_array(AUDIT_BUNDLE / "check-results.json")
    alternatives = [
        path
        for path in (AUDIT_BUNDLE / "alternative-bundles").iterdir()
        if path.is_dir()
    ]

    assert result["plan_timing"] == "post_result_exploratory"
    assert len(checks) == 5
    assert len(alternatives) == 7
    assert _family(checks, "exact_rerun")["status"] == "passed"
    assert result["release_recommendation"] != "proceed_with_caveats"
    assert result["claim_eligibility"] == "causal_candidate"
    for check in checks:
        if check["check_family"] == "exact_rerun":
            continue
        metrics = cast(dict[str, object], check["metrics"])
        records = cast(list[dict[str, object]], metrics["execution_records"])
        assert records
        assert all("alternative_id" in item for item in records)
        assert all(isinstance(item.get("request"), dict) for item in records)
        assert all("request_id" in item for item in records)
        assert all("bundle_path" not in item for item in records)
        assert all("request_path" not in item for item in records)
        for record in records:
            bundle_request = _load_object(
                AUDIT_BUNDLE
                / "alternative-bundles"
                / str(record["alternative_id"])
                / "request.json"
            )
            assert record["request"] == bundle_request

    hac_check = _family(checks, "covariance_sensitivity")
    metrics = cast(dict[str, object], hac_check["metrics"])
    assert float(cast(float, metrics["max_coefficient_delta"])) <= 1e-12
    hac_alternative = next(
        item
        for item in cast(list[dict[str, object]], plan["alternatives"])
        if "hac_maxlags" in cast(dict[str, object], item["patch"])
    )
    baseline = _load_object(
        TIME_SERIES_ROOT / ".artifacts" / "jel-example5-causal" / "result.json"
    )
    alternative = _load_object(
        AUDIT_BUNDLE
        / "alternative-bundles"
        / str(hac_alternative["alternative_id"])
        / "result.json"
    )
    base_rows = cast(list[dict[str, object]], baseline["horizon_results"])
    alt_rows = cast(list[dict[str, object]], alternative["horizon_results"])
    manual_max_delta = max(
        abs(float(cast(float, alt["estimate"])) - float(cast(float, base["estimate"])))
        for base, alt in zip(base_rows, alt_rows, strict=True)
    )
    assert float(cast(float, metrics["max_coefficient_delta"])) == pytest.approx(
        manual_max_delta,
        abs=1e-15,
    )
