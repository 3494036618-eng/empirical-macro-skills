"""生成科研人员使用的唯一中文研究报告。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import cast

from research_synthesis.claim_policy import assert_report_language
from research_synthesis.identifiers import sha256_file
from research_synthesis.models import ReportInputs


def _claims(
    inputs: ReportInputs,
    claim_type: str,
) -> list[dict[str, object]]:
    claims = cast(list[dict[str, object]], inputs.claim_ledger["claims"])
    return [item for item in claims if item["claim_type"] == claim_type]


def _limitation_lines(inputs: ReportInputs) -> list[str]:
    limitations = cast(
        list[dict[str, object]],
        inputs.limitations["limitations"],
    )
    return [f"- {item['statement']}" for item in limitations]


def _research_question(inputs: ReportInputs) -> str:
    design = inputs.envelopes["research_design"]
    return str(design.statuses["research_question"])


def _confidence_label(inputs: ReportInputs) -> str:
    value = float(
        cast(float, inputs.envelopes["estimator"].statuses["confidence_level"])
    )
    return f"{value * 100:g}%"


def _data_section(inputs: ReportInputs) -> list[str]:
    data = inputs.envelopes["macro_data"]
    sample = cast(dict[str, object], data.statuses["sample_window"])
    source = cast(dict[str, object], data.statuses["source"])
    lines = [
        f"- 数据：{source['source_title']}",
        f"- 固定版本：`{source['source_commit']}`",
        f"- 许可：`{source['license']}`",
        f"- 频率：`{data.statuses['frequency']}`",
        f"- 样本：`{sample['start']}` 至 `{sample['end']}`",
        f"- 变量：{', '.join(cast(list[str], data.statuses['variables']))}",
    ]
    lines.extend(f"- {claim['report_text']}" for claim in _claims(inputs, "data"))
    return lines


def _method_section(inputs: ReportInputs) -> list[str]:
    design = inputs.envelopes["research_design"]
    estimator = inputs.envelopes["estimator"]
    eligibility = str(
        inputs.claim_ledger["effective_claim_eligibility"]
    )
    if eligibility == "associational_only":
        estimand = "conditional_projection_path"
        boundary = (
            "- 当前分析为条件动态关联，只描述给定信息集下的动态路径。"
        )
    else:
        estimand = str(estimator.statuses["estimand_type"])
        boundary = "- 当前识别状态为因果候选，仍保留 shock exogeneity 人工审核。"
    lines = [
        "- 估计方法：Local Projection",
        f"- method profile：`{estimator.statuses['method_profile']}`",
        f"- analysis track：`{design.statuses['analysis_track']}`",
        f"- estimand：`{estimand}`",
        (
            f"- 区间：{_confidence_label(inputs)} pointwise interval，"
            "不代表 simultaneous inference。"
        ),
        boundary,
    ]
    lines.extend(
        f"- {claim['report_text']}" for claim in _claims(inputs, "design")
    )
    return lines


def _path_table(inputs: ReportInputs) -> list[str]:
    fields = (
        "horizon",
        "estimate",
        "standard_error",
        "confidence_lower",
        "confidence_upper",
        "nobs",
        "df_resid",
    )
    rows = cast(
        list[dict[str, object]],
        inputs.envelopes["estimator"].statuses["horizon_results"],
    )
    lines = [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    lines.extend(
        "| " + " | ".join(str(row[field]) for field in fields) + " |"
        for row in rows
    )
    return lines


def _result_section(inputs: ReportInputs) -> list[str]:
    claims = cast(list[dict[str, object]], inputs.claim_ledger["claims"])
    result_claims = [
        claim
        for claim in claims
        if claim["claim_type"]
        in {"descriptive", "associational", "causal_candidate"}
    ]
    lines = [f"- {claim['report_text']}" for claim in result_claims]
    lines.extend(
        (
            "",
            "完整动态路径：",
            "",
            *_path_table(inputs),
            "",
            "机器可读结果：[dynamic-path.csv](tables/dynamic-path.csv)",
            "",
            "结果图：[dynamic-path.png](figures/dynamic-path.png)",
        )
    )
    return lines


def _robustness_section(inputs: ReportInputs) -> list[str]:
    audit = inputs.envelopes["robustness_audit"]
    claims = _claims(inputs, "robustness")
    timing = str(audit.statuses["plan_timing"]).replace("_", "-")
    return [
        f"- assessment：`{audit.statuses['assessment']}`",
        f"- plan timing：`{timing}`",
        f"- audit readiness：`{audit.statuses['audit_readiness']}`",
        f"- release recommendation：`{audit.statuses['release_recommendation']}`",
        *(f"- {claim['report_text']}" for claim in claims),
    ]


def build_report(inputs: ReportInputs) -> str:
    """从同一组 ledgers 生成唯一研究报告。"""
    title = str(inputs.request["research_title"])
    readiness = inputs.envelopes["research_design"].statuses["design_readiness"]
    eligibility = str(inputs.claim_ledger["effective_claim_eligibility"])
    sections = [
        f"# {title}",
        "",
        "## 1. 研究问题",
        "",
        _research_question(inputs),
        "",
        f"当前设计状态：`{readiness}`。",
        "",
        "## 2. 数据",
        "",
        *_data_section(inputs),
        "",
        "## 3. 方法",
        "",
        *_method_section(inputs),
        "",
        "## 4. 主要结果",
        "",
        *_result_section(inputs),
        "",
        "## 5. 稳健性",
        "",
        *_robustness_section(inputs),
        "",
        "## 6. 结论与限制",
        "",
        f"本研究报告保留 `{eligibility}` 和 `review_required` 边界。",
        "",
        *_limitation_lines(inputs),
        "",
    ]
    report = "\n".join(sections)
    assert_report_language(
        report,
        str(inputs.claim_ledger["effective_claim_eligibility"]),
    )
    return report


def copy_report_assets(
    estimator_bundle: Path,
    output_dir: Path,
) -> dict[str, str]:
    """原样复制 estimator 的机器可读表格和图形。"""
    destinations = {
        "tables/dynamic-path.csv": estimator_bundle / "dynamic-path.csv",
        "figures/dynamic-path.png": estimator_bundle / "dynamic-path.png",
    }
    checksums: dict[str, str] = {}
    for relative, source in destinations.items():
        target = output_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        checksums[relative] = sha256_file(target)
    return checksums
