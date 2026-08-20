# 研究分类

## 输入成熟度

| 状态 | 含义 |
|---|---|
| `idea_only` | 只有主题或现象，需要2-3个候选问题 |
| `question_ready` | 问题基本明确，关键设计仍未冻结 |
| `design_ready` | estimand、范围和主要识别思路由用户明确 |
| `execution_ready` | 结构化执行字段完整，但仍需机器门禁 |

成熟度描述当前输入，不评价用户专业水平。

## 研究族

| 研究族 | 允许的默认主张 | 首版边界 |
|---|---|---|
| `descriptive_measurement` | `descriptive_only` | 描述、分解、事实测量 |
| `panel_association` | `associational_only` | 条件相关，不自动因果化 |
| `dynamic_shock_response` | `causal_candidate` | 必须先定义可辩护的shock |
| `causal_policy_evaluation` | `causal_candidate` | 必须有处理、时点、比较与假设 |
| `forecasting_nowcasting` | `predictive_only` | 必须使用point-in-time协议 |
| `structural_modeling` | `structural_candidate` | 只分类并强制独立复核 |

分类只读取结构化字段。缺少因果比较结构时返回 `undetermined`，
不得用关键词分数猜测研究族。
