"""Fail-closed checks for point-in-time forecasting design."""

from __future__ import annotations

VALID_ORIGIN_POLICIES = {"rolling", "expanding", "single_origin"}
VALID_VINTAGE_POLICIES = {"as_released", "first_release", "fixed_vintage"}
VALID_TEMPORAL_SPLITS = {"rolling", "expanding", "fixed_holdout"}


def forecasting_issues(request: dict[str, object]) -> list[str]:
    forecast = request.get("forecast")
    if not isinstance(forecast, dict):
        return ["forecast_specification_required"]

    issues: list[str] = []
    horizons = forecast.get("horizons")
    if not isinstance(horizons, list) or not horizons:
        issues.append("forecast_horizon_required")
    if forecast.get("forecast_origin_policy") not in VALID_ORIGIN_POLICIES:
        issues.append("forecast_origin_required")
    if forecast.get("point_in_time_required") is not True:
        issues.append("point_in_time_data_required")
    if forecast.get("target_vintage_policy") not in VALID_VINTAGE_POLICIES:
        issues.append("historical_vintage_required")
    if forecast.get("temporal_split") not in VALID_TEMPORAL_SPLITS:
        issues.append("temporal_split_required")
    if not isinstance(forecast.get("baseline_model"), str):
        issues.append("forecast_baseline_required")
    if not isinstance(forecast.get("loss_function"), str):
        issues.append("forecast_loss_required")
    return sorted(issues)
