from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from time_series_dynamics.horizon_regression import estimate_path
from time_series_dynamics.models import DynamicsRequest
from time_series_dynamics.source_loader import load_jel_example5

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE = PROJECT_ROOT / ".cache" / "jorda-taylor-example5"
DATA = CACHE / "aggregatedata_final.dta"
PROGRAM = CACHE / "sbands_RR.do"
STATA_LOG = CACHE / "all.log"
REQUEST = PROJECT_ROOT / "fixtures" / "synthetic" / "jel.causal.request.json"


def _independent_hac(
    x: np.ndarray,
    residuals: np.ndarray,
    maxlags: int,
) -> np.ndarray:
    scores = x * residuals[:, None]
    middle = scores.T @ scores
    for lag in range(1, maxlags + 1):
        weight = 1.0 - lag / (maxlags + 1.0)
        cross = scores[lag:].T @ scores[:-lag]
        middle += weight * (cross + cross.T)
    bread = np.linalg.inv(x.T @ x)
    return bread @ middle @ bread


def _independent_path(frame: pd.DataFrame) -> list[tuple[float, float, int]]:
    results: list[tuple[float, float, int]] = []
    for horizon in range(18):
        y = 100.0 * (frame["lcpi"].shift(-horizon) - frame["lcpi"].shift(1))
        columns: dict[str, object] = {
            "constant": np.ones(len(frame)),
            "exposure": frame["rr_shock"],
        }
        for control in ("dlrgdp", "dlcpi", "dstir"):
            for lag in range(1, 5):
                columns[f"{control}_{lag}"] = frame[control].shift(lag)
        x_frame = pd.DataFrame(columns)
        combined = pd.concat([y.rename("y"), x_frame], axis=1).dropna()
        x = combined.drop(columns="y").to_numpy(dtype=float)
        dependent = combined["y"].to_numpy(dtype=float)
        beta = np.linalg.solve(x.T @ x, x.T @ dependent)
        residuals = dependent - x @ beta
        covariance = _independent_hac(x, residuals, maxlags=17)
        results.append((float(beta[1]), float(np.sqrt(covariance[1, 1])), len(x)))
    return results


@pytest.mark.external
def test_jel_current_program_matches_independent_numpy_baseline() -> None:
    if not DATA.is_file():
        pytest.skip("run scripts/fetch_jel_example5.py before external replication")
    request = DynamicsRequest.from_document(
        json.loads(REQUEST.read_text(encoding="utf-8"))
    )
    frame = load_jel_example5(DATA)
    expected = _independent_path(frame)

    actual = estimate_path(frame, request)

    assert len(actual) == 18
    for estimate, (expected_beta, expected_se, expected_nobs) in zip(
        actual,
        expected,
        strict=True,
    ):
        assert estimate.estimate == pytest.approx(expected_beta, abs=1e-10)
        assert estimate.standard_error == pytest.approx(expected_se, abs=1e-10)
        assert estimate.nobs == expected_nobs


@pytest.mark.external
def test_replication_package_code_log_lag_drift_is_preserved_as_evidence() -> None:
    if not PROGRAM.is_file() or not STATA_LOG.is_file():
        pytest.skip("run scripts/fetch_jel_example5.py before external replication")
    program = PROGRAM.read_text(encoding="utf-8")
    log = STATA_LOG.read_text(encoding="utf-8", errors="replace")

    assert "local lags = 4" in program
    assert "local lags = 6" in log
