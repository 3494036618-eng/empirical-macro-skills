from __future__ import annotations

import json
from pathlib import Path

import pytest

from robustness_audit.time_series_adapter import TimeSeriesAdapter

ROOT = Path(__file__).resolve().parents[1]
TIME_SERIES_ROOT = ROOT.parent / "time-series-dynamics"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _adapter() -> TimeSeriesAdapter:
    capability = _load(ROOT / "fixtures" / "synthetic" / "adapter-capability.json")
    return TimeSeriesAdapter(TIME_SERIES_ROOT, capability)


def _baseline_request() -> dict[str, object]:
    return _load(
        TIME_SERIES_ROOT / "fixtures" / "synthetic" / "jel.causal.request.json"
    )


def test_adapter_derives_new_request_without_changing_estimand() -> None:
    baseline = _baseline_request()
    adapter = _adapter()

    derived = adapter.derive_request(
        baseline,
        {"lags": 3},
        "ra-alt-0123456789abcdef0123456789abcdef",
    )

    assert derived["request_id"] == "tsd-request-0123456789abcdef0123456789abcdef"
    assert derived["request_id"] != baseline["request_id"]
    assert derived["lags"] == 3
    assert derived["outcome_variable_id"] == baseline["outcome_variable_id"]
    assert derived["analysis_track"] == baseline["analysis_track"]


@pytest.mark.parametrize(
    "patch",
    [
        {"outcome_variable_id": "lrgdp"},
        {"shock_identification_artifact_ref": "shock-artifact-fedcba9876543210"},
        {"horizons": [0, 1]},
        {"claim_eligibility": "associational_only"},
        {"unknown_field": 1},
    ],
)
def test_adapter_rejects_forbidden_or_unknown_patch(
    patch: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="adapter patch field is not allowed"):
        _adapter().derive_request(
            _baseline_request(),
            patch,
            "ra-alt-0123456789abcdef0123456789abcdef",
        )


def test_adapter_executes_and_validates_real_time_series_cli(tmp_path: Path) -> None:
    adapter = _adapter()
    request = adapter.derive_request(
        _baseline_request(),
        {"lags": 3},
        "ra-alt-0123456789abcdef0123456789abcdef",
    )
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    output = tmp_path / "alternative"
    fixtures = TIME_SERIES_ROOT / "fixtures" / "synthetic"
    inputs = {
        "research_plan": fixtures / "jel.causal.plan.json",
        "macro_result": fixtures / "jel.macro-result.json",
        "shock_artifact": fixtures / "jel.shock-artifact.json",
        "data": (
            TIME_SERIES_ROOT
            / ".cache"
            / "jorda-taylor-example5"
            / "aggregatedata_final.dta"
        ),
    }

    result = adapter.execute(
        request_path,
        inputs,
        output,
        timeout_seconds=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    adapter.validate_result_bundle(output)
    assert (output / "result.json").is_file()


def test_adapter_derives_macro_scope_for_sample_window(tmp_path: Path) -> None:
    adapter = _adapter()
    request = adapter.derive_request(
        _baseline_request(),
        {"sample_window": {"start": "1986Q1", "end": "2007Q4"}},
        "ra-alt-fedcba9876543210fedcba9876543210",
    )
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    fixtures = TIME_SERIES_ROOT / "fixtures" / "synthetic"
    inputs = {
        "research_plan": fixtures / "jel.causal.plan.json",
        "macro_result": fixtures / "jel.macro-result.json",
        "shock_artifact": fixtures / "jel.shock-artifact.json",
        "data": (
            TIME_SERIES_ROOT
            / ".cache"
            / "jorda-taylor-example5"
            / "aggregatedata_final.dta"
        ),
    }
    output = tmp_path / "sample-window"

    result = adapter.execute(
        request_path,
        inputs,
        output,
        timeout_seconds=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads((output / "request.json").read_text())["sample_window"] == {
        "start": "1986Q1",
        "end": "2007Q4",
    }
    adapter.validate_result_bundle(output)


def test_adapter_validates_existing_baseline_bundle() -> None:
    _adapter().validate_baseline(
        TIME_SERIES_ROOT / ".artifacts" / "jel-example5-causal"
    )
