from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1] / "fixtures" / "gold"

CASES = [
    (
        "中国通胀过去二十年如何变化？",
        "descriptive_measurement",
        "descriptive",
        "descriptive_only",
        {},
        [],
    ),
    (
        "哪些国家的增长呈现何种收敛？",
        "descriptive_measurement",
        "descriptive",
        "descriptive_only",
        {"convergence_definition": "unresolved"},
        ["convergence_definition_required"],
    ),
    (
        "基期变化是否改变实际国内生产总值趋势？",
        "descriptive_measurement",
        "descriptive",
        "descriptive_only",
        {"price_basis_aligned": False},
        ["price_basis_alignment_required"],
    ),
    (
        "疫情前后失业率是否存在结构断点？",
        "descriptive_measurement",
        "descriptive",
        "descriptive_only",
        {"structural_break_evidence": "hypothesis"},
        ["structural_break_test_required"],
    ),
    (
        "国家边界变化后统计序列能否直接拼接？",
        "descriptive_measurement",
        "descriptive",
        "descriptive_only",
        {"entity_boundary_stitching": True},
        ["entity_version_alignment_required"],
    ),
    (
        "宏观指标最新值与首次发布值差异多大？",
        "descriptive_measurement",
        "descriptive",
        "descriptive_only",
        {"vintage_comparison_defined": False},
        ["vintage_definition_required"],
    ),
    (
        "投资率与经济增长之间是否存在稳定关系？",
        "panel_association",
        "associational",
        "associational_only",
        {},
        [],
    ),
    (
        "控制国家和年份固定效应后贸易与增长关系如何？",
        "panel_association",
        "associational",
        "associational_only",
        {},
        [],
    ),
    (
        "债务与增长是否存在预先设定的非线性关系？",
        "panel_association",
        "associational",
        "associational_only",
        {"functional_form_preregistered": False},
        ["functional_form_preregistration_required"],
    ),
    (
        "不同收入组的投资增长关系是否不同？",
        "panel_association",
        "associational",
        "associational_only",
        {"moderator_preregistered": False},
        ["moderator_preregistration_required"],
    ),
    (
        "加入滞后因变量后还能直接使用固定效应吗？",
        "panel_association",
        "associational",
        "associational_only",
        {"lagged_outcome_included": True, "dynamic_panel_review": False},
        ["direct_lagged_outcome_fe_rejected"],
    ),
    (
        "面板回归显著系数是否足以证明政策有效？",
        "panel_association",
        "associational",
        "associational_only",
        {"coefficient_used_as_causal_proof": True},
        ["causal_claim_from_association_rejected"],
    ),
    (
        "货币政策冲击后通胀未来八个季度如何响应？",
        "dynamic_shock_response",
        "causal",
        "causal_candidate",
        {"shock_identification": "explicit"},
        [],
    ),
    (
        "原油价格上涨与进口国产出动态变化有何关系？",
        "dynamic_shock_response",
        "associational",
        "associational_only",
        {"shock_identification": "unresolved"},
        ["shock_identification_unresolved"],
    ),
    (
        "财政乘数是否在衰退期更高并如何累计？",
        "dynamic_shock_response",
        "causal",
        "causal_candidate",
        {
            "shock_identification": "explicit",
            "state_timing": "ex_ante",
            "multiplier_definition": "specified",
        },
        [],
    ),
    (
        "局部投影和向量自回归哪个方法一定更好？",
        "dynamic_shock_response",
        "causal",
        "not_eligible",
        {"shock_identification": "explicit", "universal_method_claim": True},
        ["universal_method_choice_rejected"],
    ),
    (
        "政策利率原始变动能否直接作为外生冲击？",
        "dynamic_shock_response",
        "causal",
        "not_eligible",
        {"shock_identification": "raw_policy_change"},
        ["shock_identification_unresolved"],
    ),
    (
        "累计财政乘数的分母应该如何定义？",
        "descriptive_measurement",
        "descriptive",
        "descriptive_only",
        {"multiplier_definition": "unresolved"},
        ["multiplier_definition_required"],
    ),
    (
        "某省产业政策是否提高了当地投资水平？",
        "causal_policy_evaluation",
        "causal",
        "not_eligible",
        {
            "treatment_defined": False,
            "comparison_group_defined": False,
            "anticipation_assessed": False,
            "spillovers_assessed": False,
        },
        [
            "treatment_definition_required",
            "comparison_group_required",
            "anticipation_assessment_required",
            "spillover_assessment_required",
        ],
    ),
    (
        "分期实施政策能否默认使用普通双向固定效应？",
        "causal_policy_evaluation",
        "causal",
        "not_eligible",
        {
            "treatment_defined": True,
            "comparison_group_defined": True,
            "anticipation_assessed": True,
            "spillovers_assessed": True,
            "staggered_adoption": True,
            "heterogeneity_robust_design": False,
        },
        ["plain_twfe_rejected"],
    ),
    (
        "政策前趋势不显著是否足以证明平行趋势？",
        "causal_policy_evaluation",
        "causal",
        "not_eligible",
        {"parallel_trends_claimed_from_nonsignificance": True},
        ["parallel_trends_not_proven"],
    ),
    (
        "邻省受到政策影响时还能作为有效对照吗？",
        "causal_policy_evaluation",
        "causal",
        "not_eligible",
        {"spillovers_assessed": False},
        ["spillover_assessment_required"],
    ),
    (
        "能否寻找一个让政策结果显著的工具变量？",
        "causal_policy_evaluation",
        "causal",
        "not_eligible",
        {"instrument_selection": "significance_seeking"},
        ["significance_driven_instrument_rejected"],
    ),
    (
        "当前面板条件是否足以采用合成双重差分？",
        "causal_policy_evaluation",
        "causal",
        "not_eligible",
        {"synthetic_did_conditions_complete": False},
        ["synthetic_did_conditions_unresolved"],
    ),
    (
        "截至二零二零年底预测二零二一年国内生产总值？",
        "forecasting_nowcasting",
        "predictive",
        "predictive_only",
        {},
        [],
    ),
    (
        "能否用最终修订数据回测过去的历史预测？",
        "forecasting_nowcasting",
        "predictive",
        "not_eligible",
        {"final_vintage_used_for_backtest": True},
        ["future_information_leakage", "historical_vintage_required"],
    ),
    (
        "动态因子模型能否在样本外超过自回归基线？",
        "forecasting_nowcasting",
        "predictive",
        "predictive_only",
        {},
        [],
    ),
    (
        "能否随机划分时间序列的训练集和测试集？",
        "forecasting_nowcasting",
        "predictive",
        "not_eligible",
        {"random_temporal_split": True},
        ["temporal_split_required"],
    ),
    (
        "本次消费者价格发布改变了多少实时预测？",
        "forecasting_nowcasting",
        "predictive",
        "predictive_only",
        {"news_decomposition_defined": True},
        [],
    ),
    (
        "一次较高拟合优度能否证明预测模型有效？",
        "forecasting_nowcasting",
        "predictive",
        "not_eligible",
        {"single_fit_metric_only": True},
        ["forecast_evaluation_insufficient"],
    ),
]


def _write(path: Path, document: dict[str, object]) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _roles(family: str, claim: str, number: int) -> list[str]:
    if family == "panel_association":
        return ["outcome", "exposure"]
    if family == "dynamic_shock_response":
        return ["outcome", "exposure" if claim == "associational" else "shock"]
    if family == "causal_policy_evaluation":
        return ["outcome", "exposure" if number == 23 else "treatment"]
    if family == "forecasting_nowcasting":
        return ["forecast_target"]
    return ["outcome"]


def _variables(roles: list[str], number: int) -> list[dict[str, object]]:
    variables = [
        {
            "variable_id": f"variable_{index + 1}",
            "role": role,
            "concept": f"RD{number:02d} {role}",
            "definition_constraints": [],
        }
        for index, role in enumerate(roles)
    ]
    if number == 23:
        variables.append(
            {
                "variable_id": "candidate_instrument",
                "role": "instrument",
                "concept": "候选工具变量",
                "definition_constraints": [],
            }
        )
    return variables


def _forecast(number: int) -> dict[str, object] | None:
    if number < 25:
        return None
    return {
        "target_variable_id": "variable_1",
        "horizons": [1],
        "forecast_origin_policy": "rolling",
        "point_in_time_required": True,
        "target_vintage_policy": "latest" if number == 26 else "as_released",
        "temporal_split": "random" if number == 28 else "rolling",
        "baseline_model": "ar1",
        "loss_function": "rmse",
    }


def _intervention(family: str, number: int) -> dict[str, object] | None:
    if family not in {"dynamic_shock_response", "causal_policy_evaluation"}:
        return None
    mechanism = "observational" if number in {14, 17, 19, 20, 21, 22, 23, 24} else "narrative"
    return {
        "name": f"RD{number:02d} intervention",
        "timing_known": number not in {19},
        "assignment_mechanism": mechanism,
    }


def _provenance(variables: list[dict[str, object]]) -> list[dict[str, object]]:
    paths = [
        "research_question",
        "intended_claim",
        "target_population",
        "unit_of_analysis",
        "time_scope",
        *[f"variables[{index}].role" for index in range(len(variables))],
    ]
    return [
        {
            "field_path": path,
            "source": "user_provided",
            "evidence_text": "Gold fixture",
            "confidence": "high",
        }
        for path in paths
    ]


def _documents(
    number: int, case: tuple[object, ...]
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    question, family, claim, expected_claim, audit_inputs, issue_codes = case
    suffix = f"{number:016x}"
    candidate_suffix = f"{number:08x}"
    candidate_id = f"rd-candidate-{candidate_suffix}"
    roles = _roles(str(family), str(claim), number)
    variables = _variables(roles, number)
    intake: dict[str, object] = {
        "schema_version": "0.1.0-draft",
        "intake_id": f"rd-intake-{suffix}",
        "raw_user_input": question,
        "input_maturity": "design_ready",
        "candidate_questions": [
            {
                "candidate_id": candidate_id,
                "research_question": question,
                "intended_claim_candidate": claim,
                "research_family_candidate": family,
                "plain_language_explanation": "Gold场景的结构化候选研究问题。",
                "risk_level": "high" if claim in {"causal", "predictive"} else "low",
                "locked_user_fields": ["research_question"],
                "unresolved_decisions": [],
            }
        ],
        "recommended_candidate_id": candidate_id,
        "field_provenance": [
            {
                "field_path": "research_question",
                "source": "user_provided",
                "evidence_text": question,
                "confidence": "high",
            }
        ],
        "clarifications": [],
        "safe_default": {"applied": False, "downgraded_to": "none", "reason": None},
        "status": "ready_to_compile",
        "output_language": "zh-CN",
    }
    request: dict[str, object] = {
        "schema_version": "0.1.0-draft",
        "source_intake_id": intake["intake_id"],
        "selected_candidate_id": candidate_id,
        "request_id": f"rd-request-{suffix}",
        "research_question": question,
        "input_maturity": "design_ready",
        "intended_claim": claim,
        "target_population": {
            "description": "Gold场景目标总体",
            "entity_types": ["country"],
            "inclusion_rules": ["按预注册范围纳入"],
            "exclusion_rules": [],
        },
        "unit_of_analysis": "country_time",
        "time_scope": {
            "start": "2000",
            "end": "2025",
            "frequency": "Q"
            if family in {"dynamic_shock_response", "forecasting_nowcasting"}
            else "A",
        },
        "variables": variables,
        "intervention_or_shock": _intervention(str(family), number),
        "forecast": _forecast(number),
        "field_provenance": _provenance(variables),
        "unresolved_decisions": [],
        "safe_downgrade_applied": False,
        "output_language": "zh-CN",
        "design_audit_inputs": audit_inputs,
    }
    if family == "dynamic_shock_response":
        request["response_horizons"] = list(range(9))
    readiness = "review_required" if expected_claim == "causal_candidate" else "blocked"
    forbidden = ["structural_candidate"]
    if expected_claim != "causal_candidate":
        forbidden.append("causal_candidate")
    expected: dict[str, object] = {
        "gold_id": f"RD{number:02d}",
        "expected_family": family,
        "expected_claim_eligibility": expected_claim,
        "required_issue_codes": issue_codes,
        "forbidden_claim_eligibility": forbidden,
        "expected_readiness": readiness,
    }
    return intake, request, expected


def main() -> None:
    for number, case in enumerate(CASES, start=1):
        case_dir = ROOT / f"rd{number:02d}"
        case_dir.mkdir(parents=True, exist_ok=True)
        intake, request, expected = _documents(number, case)
        _write(case_dir / "intake.json", intake)
        _write(case_dir / "request.json", request)
        _write(case_dir / "expected.json", expected)


if __name__ == "__main__":
    main()
