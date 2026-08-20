from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from robustness_audit.baseline_verifier import (
    compare_exact_bundles,
    exact_rerun,
    verify_baseline_inputs,
)
from robustness_audit.models import AuditPlan
from robustness_audit.plan_compiler import compile_audit_plan
from robustness_audit.time_series_adapter import TimeSeriesAdapter

ROOT = Path(__file__).resolve().parents[1]
TIME_SERIES_ROOT = ROOT.parent / "time-series-dynamics"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _input_paths() -> dict[str, Path]:
    fixtures = TIME_SERIES_ROOT / "fixtures" / "synthetic"
    return {
        "request": fixtures / "jel.causal.request.json",
        "research_plan": fixtures / "jel.causal.plan.json",
        "macro_data": fixtures / "jel.macro-result.json",
        "shock_artifact": fixtures / "jel.shock-artifact.json",
        "data": (
            TIME_SERIES_ROOT
            / ".cache"
            / "jorda-taylor-example5"
            / "aggregatedata_final.dta"
        ),
    }


def _adapter() -> TimeSeriesAdapter:
    return TimeSeriesAdapter(
        TIME_SERIES_ROOT,
        _load(ROOT / "fixtures" / "synthetic" / "adapter-capability.json"),
    )


def _plan() -> AuditPlan:
    document = compile_audit_plan(
        _load(ROOT / "fixtures" / "synthetic" / "audit-request.json"),
        _load(ROOT / "fixtures" / "external" / "jel-example5.robustness-handoff.json"),
        _load(
            TIME_SERIES_ROOT / "fixtures" / "synthetic" / "jel.causal.request.json"
        ),
        _load(ROOT / "fixtures" / "synthetic" / "adapter-capability.json"),
    )
    return AuditPlan.from_document(document)


def _baseline() -> Path:
    return TIME_SERIES_ROOT / ".artifacts" / "jel-example5-causal"


def _expected_checksums() -> dict[str, str]:
    manifest = _load(_baseline() / "run-manifest.json")
    return copy.deepcopy(manifest["input_checksums"])  # type: ignore[return-value]


def test_baseline_inputs_and_outputs_are_recomputed_from_real_files() -> None:
    report = verify_baseline_inputs(
        _baseline(),
        _input_paths(),
        _expected_checksums(),
    )

    assert report["valid"] is True
    assert report["request_id"] == "tsd-request-0123456789abcdef"
    assert report["input_checksums"] == _expected_checksums()


@pytest.mark.parametrize(
    "artifact",
    ["data", "research_plan", "macro_data", "shock_artifact"],
)
def test_baseline_input_tampering_is_rejected(
    artifact: str,
    tmp_path: Path,
) -> None:
    paths = _input_paths()
    source = paths[artifact]
    tampered = tmp_path / source.name
    if artifact == "data":
        tampered.write_bytes(source.read_bytes() + b"tampered")
    else:
        document = _load(source)
        document["tampered"] = True
        tampered.write_text(json.dumps(document), encoding="utf-8")
    paths[artifact] = tampered

    with pytest.raises(ValueError, match="baseline_input_checksum_mismatch"):
        verify_baseline_inputs(_baseline(), paths, _expected_checksums())


def test_baseline_output_or_manifest_tampering_is_rejected(tmp_path: Path) -> None:
    tampered = tmp_path / "bundle"
    shutil.copytree(_baseline(), tampered)
    with (tampered / "dynamic-path.csv").open("ab") as handle:
        handle.write(b"tampered")

    with pytest.raises(ValueError, match="baseline_result_checksum_mismatch"):
        verify_baseline_inputs(tampered, _input_paths(), _expected_checksums())

    (tampered / "run-manifest.json").unlink()
    with pytest.raises(ValueError, match="baseline_bundle_invalid"):
        verify_baseline_inputs(tampered, _input_paths(), _expected_checksums())


def test_exact_rerun_matches_real_baseline(tmp_path: Path) -> None:
    rerun = tmp_path / "exact-rerun"

    result = exact_rerun(
        _plan(),
        _adapter(),
        _input_paths()["request"],
        _input_paths(),
        _baseline(),
        rerun,
    )

    assert result["status"] == "passed"
    assert result["issue_codes"] == []
    assert compare_exact_bundles(_baseline(), rerun) == []


def test_exact_rerun_records_timeout_as_failed_stop_ship_evidence(
    tmp_path: Path,
) -> None:
    class TimeoutAdapter:
        def validate_baseline(self, bundle: Path) -> None:
            del bundle

        def execute(
            self,
            request_path: Path,
            input_paths: dict[str, Path],
            output_dir: Path,
            timeout_seconds: float,
        ) -> object:
            del request_path, input_paths, output_dir
            raise subprocess.TimeoutExpired(
                ["estimator"],
                timeout_seconds,
                output="partial stdout",
                stderr="partial stderr",
            )

    result = exact_rerun(
        _plan(),
        TimeoutAdapter(),  # type: ignore[arg-type]
        _input_paths()["request"],
        _input_paths(),
        _baseline(),
        tmp_path / "timeout",
    )

    assert result["status"] == "failed"
    assert result["issue_codes"] == ["exact_rerun_timeout"]
    assert result["execution_error"] == "partial stderr"
