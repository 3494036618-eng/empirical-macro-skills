from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "fixtures" / "routing" / "gold-cases.json"
FIXED_MESSAGE = "当前版本不能执行该方法"


def intent(
    *,
    domain: str = "empirical_macro",
    kind: str = "research_idea",
    method: str | None = "conditional_dynamic_association",
    plan: bool = False,
    data: bool = False,
    estimator: bool = False,
    robustness: bool = False,
    state: bool = False,
) -> dict[str, object]:
    return {
        "schema_version": "0.1.0-beta",
        "domain": domain,
        "request_kind": kind,
        "method_family": method,
        "has_research_plan": plan,
        "has_macro_data_bundle": data,
        "has_estimator_bundle": estimator,
        "has_robustness_bundle": robustness,
        "has_workflow_state": state,
    }


def case(
    case_id: str,
    category: str,
    prompt: str,
    candidate: dict[str, object],
    action: str,
    target: str | None,
    *,
    message: str | None = None,
    state_stage: str | None = None,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "category": category,
        "prompt": prompt,
        "intent": candidate,
        "state_stage": state_stage,
        "expected_action": action,
        "expected_target_skill": target,
        "expected_user_message": message,
    }


def vague_cases() -> list[dict[str, object]]:
    prompts = [
        "我想研究货币政策与通胀，但还没想好国家和指标。",
        "利率上升后经济通常怎么变化？我想把它做成实证研究。",
        "帮我把能源价格和产出波动这个方向变成可检验问题。",
        "我想研究金融条件对实体经济的动态影响，从哪里开始？",
        "能不能设计一个关于通胀持续性的宏观研究？",
        "我有个想法：政策收紧可能影响就业，请先帮我定研究问题。",
        "想比较一次宏观冲击发生后消费和产出的变化。",
        "我还没有变量表，只知道想研究需求冲击。",
        "请把汇率变化与国内价格这个主题整理成研究方案。",
        "重新审视我的宏观研究想法，即使目录里有旧结果也先从设计开始。",
    ]
    cases = []
    for index, prompt in enumerate(prompts, 1):
        stale = index == 10
        cases.append(
            case(
                f"vague-{index:02d}",
                "vague_research_idea",
                prompt,
                intent(
                    plan=stale,
                    data=stale,
                    estimator=stale,
                    robustness=stale,
                ),
                "route_research_design",
                "research-design",
            )
        )
    return cases


def data_cases() -> list[dict[str, object]]:
    prompts = [
        "整理中国季度 CPI 数据并给出口径和来源。",
        "准备美国季度实际 GDP 的科研数据包。",
        "我要欧元区政策利率和通胀的季度数据，只做数据准备。",
        "构建日本年度通胀与产出数据，不要开始估计。",
        "核对英国失业率序列的频率、单位和时间覆盖。",
        "准备多个国家的宏观指标并记录缺失期。",
        "查询一组季度宏观数据并保留原始来源与校验和。",
        "先帮我检查数据口径，不需要研究结论。",
        "把现有宏观数据需求转成可审计的数据包。",
        "只完成指标、实体、频率和时期的精确数据匹配。",
    ]
    return [
        case(
            f"data-{index:02d}",
            "data_preparation",
            prompt,
            intent(kind="data_preparation"),
            "route_macro_data",
            "macro-data",
        )
        for index, prompt in enumerate(prompts, 1)
    ]


def dynamic_cases() -> list[dict[str, object]]:
    prompts = [
        "研究已识别货币政策冲击后的季度通胀响应。",
        "估计政策利率变化与未来产出的条件动态关联。",
        "基于现有研究计划和数据运行季度动态响应。",
        "我已经准备好外生冲击和季度数据，开始动态分析。",
        "研究一次供给冲击的动态路径，但还没有正式研究计划。",
        "分析利率和通胀的季度关系，我只有一个初步问题。",
        "我明确要做动态响应，但变量角色还没冻结。",
        "研究冲击后的产出路径，计划已有但数据还没准备好。",
        "继续动态关联分析，先补齐研究所需季度数据。",
        "计划已确认，请在数据合格后估计动态路径。",
    ]
    cases = []
    for index, prompt in enumerate(prompts, 1):
        if index <= 4:
            candidate = intent(kind="dynamic_analysis", plan=True, data=True)
            action, target = "route_time_series_dynamics", "time-series-dynamics"
        elif index <= 7:
            candidate = intent(kind="dynamic_analysis")
            action, target = "route_research_design", "research-design"
        else:
            candidate = intent(kind="dynamic_analysis", plan=True)
            action, target = "route_macro_data", "macro-data"
        cases.append(
            case(
                f"dynamic-{index:02d}",
                "supported_dynamic",
                prompt,
                candidate,
                action,
                target,
            )
        )
    return cases


def robustness_cases() -> list[dict[str, object]]:
    prompts = [
        "基线动态结果已有，请执行预先声明的稳健性检查。",
        "检查不同滞后阶数和 HAC 设定是否改变结论。",
        "对现有动态估计做样本窗口敏感性审计。",
        "我要做稳健性检查，但当前数据包还没有完成。",
        "研究设计和数据都已有，先完成基线估计再审计。",
    ]
    settings = [
        (True, True, True, "route_robustness_audit", "robustness-audit"),
        (True, True, True, "route_robustness_audit", "robustness-audit"),
        (True, True, True, "route_robustness_audit", "robustness-audit"),
        (True, False, False, "route_macro_data", "macro-data"),
        (True, True, False, "route_time_series_dynamics", "time-series-dynamics"),
    ]
    return [
        case(
            f"robustness-{index:02d}",
            "robustness",
            prompt,
            intent(
                kind="robustness",
                plan=plan,
                data=data,
                estimator=estimator,
            ),
            action,
            target,
        )
        for index, (prompt, (plan, data, estimator, action, target)) in enumerate(
            zip(prompts, settings, strict=True),
            1,
        )
    ]


def synthesis_cases() -> list[dict[str, object]]:
    prompts = [
        "所有上游结果都齐了，请生成最终中文研究报告和复现材料。",
        "把已验证的设计、数据、估计和稳健性证据编译成研究包。",
        "我想要最终报告，但研究设计还没有完成。",
        "数据和计划已有，先完成动态估计再生成报告。",
        "估计结果已有，但稳健性审计还没做完。",
    ]
    settings = [
        (True, True, True, True, "route_research_synthesis", "research-synthesis"),
        (True, True, True, True, "route_research_synthesis", "research-synthesis"),
        (False, False, False, False, "route_research_design", "research-design"),
        (True, True, False, False, "route_time_series_dynamics", "time-series-dynamics"),
        (True, True, True, False, "route_robustness_audit", "robustness-audit"),
    ]
    return [
        case(
            f"synthesis-{index:02d}",
            "final_report",
            prompt,
            intent(
                kind="final_report",
                plan=plan,
                data=data,
                estimator=estimator,
                robustness=robustness,
            ),
            action,
            target,
        )
        for index, (
            prompt,
            (plan, data, estimator, robustness, action, target),
        ) in enumerate(zip(prompts, settings, strict=True), 1)
    ]


def unsupported_cases() -> list[dict[str, object]]:
    methods = [
        ("请执行跨国面板固定效应回归。", "panel_association"),
        ("用动态面板模型分析债务和增长。", "panel_association"),
        ("做一个双重差分评估政策效果。", "causal_policy_evaluation"),
        ("请执行事件研究并估计政策因果效应。", "causal_policy_evaluation"),
        ("使用工具变量法解决内生性。", "causal_policy_evaluation"),
        ("用 RDD 识别政策影响。", "causal_policy_evaluation"),
        ("建立模型预测明年通胀。", "forecasting_nowcasting"),
        ("做实时 Nowcasting。", "forecasting_nowcasting"),
        ("估计 DSGE 结构模型。", "structural_modeling"),
        ("求解一般均衡并模拟政策反事实。", "structural_modeling"),
    ]
    return [
        case(
            f"unsupported-{index:02d}",
            "unsupported_method",
            prompt,
            intent(kind="final_report", method=method, plan=True, data=True),
            "method_not_implemented",
            None,
            message=FIXED_MESSAGE,
        )
        for index, (prompt, method) in enumerate(methods, 1)
    ]


def out_of_scope_cases() -> list[dict[str, object]]:
    prompts = [
        ("帮我规划一条有机合成路线。", "chemistry"),
        ("审查这个 React 组件。", "software_engineering"),
        ("给销售团队生成客户跟进建议。", "sales"),
        ("比较两款家用汽车。", "car_decision"),
        ("分析我的个人股票组合。", "personal_finance"),
        ("翻译这段英文。", "translation"),
        ("生成一张产品海报。", "design"),
        ("检查数据库慢查询。", "database"),
        ("整理一次用户访谈。", "ux_research"),
        ("写一份旅行行程。", "travel"),
    ]
    return [
        case(
            f"out-of-scope-{index:02d}",
            "out_of_scope",
            prompt,
            intent(domain=domain, method=None),
            "out_of_scope",
            None,
        )
        for index, (prompt, domain) in enumerate(prompts, 1)
    ]


def resume_cases() -> list[dict[str, object]]:
    stages = [
        ("设计已确认，从保存状态继续准备数据。", "design_ready", "route_macro_data", "macro-data"),
        (
            "数据已经验证，从检查点继续动态估计。",
            "data_ready",
            "route_time_series_dynamics",
            "time-series-dynamics",
        ),
        (
            "基线估计完成，继续稳健性审计。",
            "estimation_ready",
            "route_robustness_audit",
            "robustness-audit",
        ),
        (
            "稳健性结果完成，继续生成最终交付。",
            "audit_ready",
            "route_research_synthesis",
            "research-synthesis",
        ),
        ("检查这个已经完成的工作流。", "completed", "completed", None),
    ]
    return [
        case(
            f"resume-{index:02d}",
            "resume",
            prompt,
            intent(
                kind="resume",
                method="dynamic_shock_response",
                plan=True,
                data=True,
                estimator=True,
                robustness=True,
                state=True,
            ),
            action,
            target,
            state_stage=stage,
        )
        for index, (prompt, stage, action, target) in enumerate(stages, 1)
    ]


def main() -> None:
    cases: list[dict[str, Any]] = [
        *vague_cases(),
        *data_cases(),
        *dynamic_cases(),
        *robustness_cases(),
        *synthesis_cases(),
        *unsupported_cases(),
        *out_of_scope_cases(),
        *resume_cases(),
    ]
    assert len(cases) == 65
    assert all("$" not in str(item["prompt"]) for item in cases)
    OUTPUT.write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
