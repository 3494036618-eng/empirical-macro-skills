"""Deterministic path comparison metrics."""

from __future__ import annotations

from typing import cast


def _rows(document: dict[str, object]) -> list[dict[str, object]]:
    rows = document.get("horizon_results")
    if not isinstance(rows, list) or any(not isinstance(item, dict) for item in rows):
        raise ValueError("horizon_results are required")
    return cast(list[dict[str, object]], rows)


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def compare_paths(
    baseline: dict[str, object],
    alternative: dict[str, object],
    *,
    epsilon: float,
    anchor_horizons: tuple[int, ...],
) -> dict[str, object]:
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    base_rows = _rows(baseline)
    alt_rows = _rows(alternative)
    base_horizons = [int(cast(int, item["horizon"])) for item in base_rows]
    alt_horizons = [int(cast(int, item["horizon"])) for item in alt_rows]
    if base_horizons != alt_horizons:
        raise ValueError("horizon mismatch")
    estimate_delta: list[float] = []
    absolute_delta: list[float] = []
    standard_error_ratio: list[float] = []
    interval_overlap: list[bool] = []
    sign_concordance: list[bool] = []
    nobs_delta: list[int] = []
    standardized: list[float] = []
    signs: dict[int, tuple[int, int]] = {}
    for base, alt in zip(base_rows, alt_rows, strict=True):
        base_estimate = float(cast(float, base["estimate"]))
        alt_estimate = float(cast(float, alt["estimate"]))
        base_se = float(cast(float, base["standard_error"]))
        alt_se = float(cast(float, alt["standard_error"]))
        delta = alt_estimate - base_estimate
        estimate_delta.append(delta)
        absolute_delta.append(abs(delta))
        standard_error_ratio.append(alt_se / max(base_se, epsilon))
        interval_overlap.append(
            max(
                float(cast(float, base["confidence_lower"])),
                float(cast(float, alt["confidence_lower"])),
            )
            <= min(
                float(cast(float, base["confidence_upper"])),
                float(cast(float, alt["confidence_upper"])),
            )
        )
        base_sign, alt_sign = _sign(base_estimate), _sign(alt_estimate)
        sign_concordance.append(base_sign == alt_sign)
        horizon = int(cast(int, base["horizon"]))
        signs[horizon] = (base_sign, alt_sign)
        nobs_delta.append(
            int(cast(int, alt["nobs"])) - int(cast(int, base["nobs"]))
        )
        standardized.append(abs(delta) / max(base_se, alt_se, epsilon))
    anchor_changes = sum(
        signs[horizon][0] != signs[horizon][1]
        for horizon in anchor_horizons
        if horizon in signs
    )
    return {
        "horizons": base_horizons,
        "estimate_delta": estimate_delta,
        "absolute_estimate_delta": absolute_delta,
        "standard_error_ratio": standard_error_ratio,
        "interval_overlap": interval_overlap,
        "sign_concordance": sign_concordance,
        "nobs_delta": nobs_delta,
        "max_standardized_path_deviation": max(standardized, default=0.0),
        "max_coefficient_delta": max(absolute_delta, default=0.0),
        "anchor_sign_changes": anchor_changes,
    }
