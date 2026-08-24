"""Deterministic technical and plain-language result summaries."""

from __future__ import annotations

from time_series_dynamics.claim_policy import assert_summary_language
from time_series_dynamics.models import ClaimPolicy, DynamicsRequest, HorizonEstimate
from time_series_dynamics.time_axis import horizon_unit_zh


def technical_summary(
    request: DynamicsRequest,
    estimates: tuple[HorizonEstimate, ...],
    source_label: str,
    source_checksum: str,
) -> str:
    nobs = [item.nobs for item in estimates]
    return (
        "# Technical Summary\n\n"
        f"- Analysis track: `{request.analysis_track}`\n"
        f"- Estimand: `{request.estimand_type}`\n"
        f"- Method profile: `{request.method_profile}`\n"
        f"- Outcome: `{request.outcome_variable_id}`\n"
        f"- Exposure: `{request.exposure_variable_id}`\n"
        f"- Controls: `{', '.join(request.control_variable_ids)}`\n"
        f"- Sample: `{request.sample_start}` to `{request.sample_end}`\n"
        f"- Sample policy: `{request.sample_policy}`\n"
        f"- Horizons: `{min(request.horizons)}` to `{max(request.horizons)}`\n"
        f"- Lags: `{request.lags}`\n"
        f"- Covariance: `HAC`, Bartlett kernel, maxlags `{request.hac_maxlags}`\n"
        f"- Interval: `{request.confidence_level:.0%}` pointwise\n"
        f"- Nobs range: `{min(nobs)}` to `{max(nobs)}`\n"
        f"- Source: {source_label}\n"
        f"- Source checksum: `{source_checksum}`\n\n"
        "The dependent variable at horizon h is "
        "`100 * (outcome[t+h] - outcome[t-1])`. "
        "The exposure coefficient is estimated separately at each horizon.\n"
    )


def _interval_statement(estimate: HorizonEstimate) -> str:
    if estimate.confidence_lower <= 0 <= estimate.confidence_upper:
        return "该期区间包含零，不能排除零关联。"
    return "该期区间不包含零；这只描述该 horizon，不代表整条路径联合显著。"


def plain_language_summary(
    request: DynamicsRequest,
    estimates: tuple[HorizonEstimate, ...],
    policy: ClaimPolicy,
) -> str:
    extreme = max(estimates, key=lambda item: abs(item.estimate))
    summary = (
        f"# {policy.title_zh}\n\n"
        f"{policy.required_disclaimer_zh}\n\n"
        "## 主要数值\n\n"
        f"估计路径中绝对值最大的系数出现在第 {extreme.horizon} "
        f"{horizon_unit_zh(request.frequency)}，"
        f"点估计为 {extreme.estimate:.3f} {request.output_unit}，"
        f"{request.confidence_level:.0%} 区间为 "
        f"[{extreme.confidence_lower:.3f}, {extreme.confidence_upper:.3f}]。"
        f"{_interval_statement(extreme)}\n\n"
        "## 如何理解\n\n"
        "图中的实线是逐期估计，阴影是逐期不确定性区间。"
        "不同 horizon 的样本量会在结果表和技术说明中单独报告；"
        "不能只挑选显著或方向符合预期的时期作为结论。\n"
    )
    assert_summary_language(summary, policy)
    return summary
