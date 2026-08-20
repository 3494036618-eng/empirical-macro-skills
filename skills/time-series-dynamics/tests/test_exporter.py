from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image
from test_artifact_validation import _macro_result, _plan
from test_contracts import association_request, causal_request, valid_shock_artifact

from time_series_dynamics.exporter import validate_bundle
from time_series_dynamics.pipeline import run_time_series_dynamics

EXPECTED_FILES = {
    "request.json",
    "result.json",
    "diagnostics.json",
    "dynamic-path.csv",
    "dynamic-path.png",
    "technical-summary.md",
    "plain-language-summary.md",
    "run-manifest.json",
}


def _write_data(path: Path) -> None:
    rng = np.random.default_rng(20260816)
    periods = 92
    frame = pd.DataFrame(
        {
            "qdate": pd.date_range("1985-01-01", periods=periods, freq="QS"),
            "rr_shock": rng.normal(0.0, 0.3, periods),
            "lcpi": rng.normal(0.0, 0.01, periods).cumsum(),
            "lrgdp": rng.normal(0.0, 0.01, periods).cumsum(),
            "stir": rng.normal(5.0, 0.5, periods),
            "dlcpi": rng.normal(0.0, 1.0, periods),
            "dlrgdp": rng.normal(0.0, 1.0, periods),
            "dstir": rng.normal(0.0, 0.2, periods),
        }
    )
    frame.to_stata(path, write_index=False)


def _handoffs_for_data(
    data: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    checksum = hashlib.sha256(data.read_bytes()).hexdigest()
    macro = _macro_result()
    macro["source_checksum"] = checksum
    shock = valid_shock_artifact()
    shock["checksum"] = checksum
    return macro, shock


def _run(
    tmp_path: Path,
    *,
    association: bool = False,
) -> Path:
    request = association_request() if association else causal_request()
    track = str(request["analysis_track"])
    output = tmp_path / ("association" if association else "causal")
    data = tmp_path / "data.dta"
    _write_data(data)
    macro, shock = _handoffs_for_data(data)
    run_time_series_dynamics(
        request,
        _plan(track),
        [macro],
        data,
        output,
        None if association else shock,
    )
    return output


def test_pipeline_exports_complete_valid_nonblank_bundle(tmp_path: Path) -> None:
    output = _run(tmp_path)

    assert {path.name for path in output.iterdir()} == EXPECTED_FILES
    assert validate_bundle(output) == {"valid": True, "errors": []}
    manifest = json.loads(
        (output / "run-manifest.json").read_text(encoding="utf-8")
    )
    assert set(manifest["input_checksums"]) == {
        "data",
        "macro_data",
        "request",
        "research_plan",
        "shock_artifact",
    }
    technical = (output / "technical-summary.md").read_text(encoding="utf-8")
    assert manifest["input_checksums"]["data"] in technical
    with Image.open(output / "dynamic-path.png") as image:
        assert image.size == (1200, 720)
        extrema = image.convert("RGB").getextrema()
        assert any(low != high for low, high in extrema)


def test_association_bundle_contains_required_noncausal_summary(tmp_path: Path) -> None:
    output = _run(tmp_path, association=True)
    summary = (output / "plain-language-summary.md").read_text(encoding="utf-8")
    manifest = json.loads(
        (output / "run-manifest.json").read_text(encoding="utf-8")
    )

    assert "这是一项条件关联分析，不是因果效应估计" in summary
    assert "加息导致" not in summary
    assert "shock_artifact" not in manifest["input_checksums"]
    assert validate_bundle(output)["valid"] is True


@pytest.mark.parametrize(
    "filename",
    ["dynamic-path.csv", "dynamic-path.png", "result.json"],
)
def test_bundle_validation_detects_output_tampering(
    tmp_path: Path,
    filename: str,
) -> None:
    output = _run(tmp_path)
    with (output / filename).open("ab") as handle:
        handle.write(b"tampered")

    result = validate_bundle(output)

    assert result["valid"] is False
    assert f"checksum_mismatch:{filename}" in result["errors"]


def test_bundle_validation_detects_manifest_checksum_tampering(
    tmp_path: Path,
) -> None:
    output = _run(tmp_path)
    manifest_path = output / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["output_checksums"]["result.json"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = validate_bundle(output)

    assert result["valid"] is False
    assert "checksum_mismatch:result.json" in result["errors"]


def test_same_input_rerun_is_deterministic_except_generated_at(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = _run(first_root)
    second = _run(second_root)

    for filename in EXPECTED_FILES - {"run-manifest.json"}:
        assert (first / filename).read_bytes() == (second / filename).read_bytes()
    first_manifest = json.loads(
        (first / "run-manifest.json").read_text(encoding="utf-8")
    )
    second_manifest = json.loads(
        (second / "run-manifest.json").read_text(encoding="utf-8")
    )
    first_manifest.pop("generated_at")
    second_manifest.pop("generated_at")
    assert first_manifest == second_manifest


def test_invalid_handoff_preserves_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    (output / "sentinel.txt").write_text("old", encoding="utf-8")
    data = tmp_path / "data.dta"
    _write_data(data)
    request = causal_request()
    macro = copy.deepcopy(_macro_result())
    macro["delivery_eligibility"] = "comparison_only"
    macro["research_readiness"] = "review_required"
    macro["eligible_for_estimation"] = False
    macro["review_required"] = True

    with pytest.raises(ValueError, match="macro_bundle_not_analysis_ready"):
        run_time_series_dynamics(
            request,
            _plan("identified_shock_irf"),
            [macro],
            data,
            output,
            valid_shock_artifact(),
        )

    assert (output / "sentinel.txt").read_text(encoding="utf-8") == "old"


def test_data_checksum_tampering_preserves_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    (output / "sentinel.txt").write_text("old", encoding="utf-8")
    data = tmp_path / "data.dta"
    _write_data(data)
    expected_checksum = hashlib.sha256(data.read_bytes()).hexdigest()
    macro = _macro_result()
    macro["source_checksum"] = expected_checksum
    shock = valid_shock_artifact()
    shock["checksum"] = expected_checksum
    frame = pd.read_stata(data)
    frame.loc[0, "lcpi"] = float(frame.loc[0, "lcpi"]) + 0.01
    frame.to_stata(data, write_index=False)

    with pytest.raises(ValueError, match="checksum mismatch"):
        run_time_series_dynamics(
            causal_request(),
            _plan("identified_shock_irf"),
            [macro],
            data,
            output,
            shock,
        )

    assert (output / "sentinel.txt").read_text(encoding="utf-8") == "old"


def test_cli_runs_pipeline_and_validator(tmp_path: Path) -> None:
    request = causal_request()
    data = tmp_path / "data.dta"
    output = tmp_path / "cli-output"
    _write_data(data)
    macro, shock = _handoffs_for_data(data)
    documents = {
        "request.json": request,
        "plan.json": _plan("identified_shock_irf"),
        "macro.json": macro,
        "shock.json": shock,
    }
    for filename, document in documents.items():
        (tmp_path / filename).write_text(
            json.dumps(document),
            encoding="utf-8",
        )
    run = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/run_time_series_dynamics.py",
            "--request-json",
            str(tmp_path / "request.json"),
            "--research-plan-json",
            str(tmp_path / "plan.json"),
            "--macro-result-json",
            str(tmp_path / "macro.json"),
            "--shock-artifact-json",
            str(tmp_path / "shock.json"),
            "--data",
            str(data),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    validation = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/validate_bundle.py", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert run.returncode == 0, run.stderr
    assert run.stderr == ""
    assert json.loads(run.stdout)["analysis_track"] == "identified_shock_irf"
    assert validation.returncode == 0, validation.stderr
    assert json.loads(validation.stdout) == {"valid": True, "errors": []}
