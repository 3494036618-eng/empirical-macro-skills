"""Deterministic technical and plain-language audit summaries."""

from __future__ import annotations

from robustness_audit.claim_policy import assert_audit_summary_language


def technical_summary(
    plan: dict[str, object],
    result: dict[str, object],
    check_results: list[dict[str, object]],
    threat_ledger: list[dict[str, object]],
) -> str:
    lines = [
        "# Robustness Audit Technical Summary",
        "",
        f"- Audit plan: `{plan['audit_plan_id']}`",
        f"- Plan timing: `{plan['plan_timing']}`",
        f"- Baseline request: `{plan['baseline_request_ref']}`",
        f"- Assessment: `{result['assessment']}`",
        f"- Release recommendation: `{result['release_recommendation']}`",
        f"- Claim eligibility: `{result['claim_eligibility']}`",
        "",
        "## Declared Checks",
        "",
    ]
    for check in check_results:
        lines.append(
            f"- `{check['check_family']}`: `{check['status']}` "
            f"(check `{check['check_id']}`)"
        )
    lines.extend(["", "## Threat Ledger", ""])
    for threat in threat_ledger:
        lines.append(
            f"- `{threat['threat_code']}`: `{threat['audit_status']}`; "
            f"upstream remains `{threat['upstream_status']}`"
        )
    lines.extend(
        [
            "",
            "Pointwise sensitivity checks do not provide whole-path inference.",
            "No audit result upgrades the baseline identification claim.",
            "",
        ]
    )
    return "\n".join(lines)


def plain_language_summary(
    result: dict[str, object],
    check_results: list[dict[str, object]],
) -> str:
    assessment = str(result["assessment"])
    if assessment == "passed_declared_checks":
        finding = (
            "在已声明且实际完成的检查范围内，没有观察到超过冻结判据的敏感性。"
        )
    elif assessment == "sensitive":
        finding = "至少一项已声明检查显示结果敏感，需要审查后才能继续。"
    elif assessment == "inconclusive":
        finding = "部分必要检查未完成或失败，当前无法判断结果是否敏感。"
    else:
        finding = "基线复现或完整性检查失败，本次没有形成稳健性判断。"
    statuses = {
        str(item["check_family"]): str(item["status"]) for item in check_results
    }
    detail = "；".join(f"{key}={value}" for key, value in sorted(statuses.items()))
    boundary = (
        "这不证明识别假设成立，也不覆盖未执行的规格。"
        if result["claim_eligibility"] == "causal_candidate"
        else "这不是因果效应估计，审计不会把条件关联升级为因果。"
    )
    text = (
        "# 已声明稳健性检查\n\n"
        f"{finding}{boundary}\n\n"
        "## 检查状态\n\n"
        f"{detail}。\n\n"
        "该审计只描述计划中列明的检查，不代表所有可能规格。\n"
    )
    assert_audit_summary_language(text, str(result["claim_eligibility"]))
    return text
