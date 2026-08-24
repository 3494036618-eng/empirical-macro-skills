# 方法资格卡

方法资格由 `src/research_design/design_cards.py` 中的不可变卡片控制。
卡片只判断硬前提，不比较估计结果，也不执行方法。

| 方法 | 研究族 | 关键前提 | 禁止捷径 |
|---|---|---|---|
| `descriptive_trend` | 描述测量 | outcome | 使用因果语言 |
| `panel_fixed_effects` | 面板关联 | outcome、exposure | 滞后因变量直接FE；因果化 |
| `event_study_did` | 政策因果 | treatment、timing、comparison | 默认普通TWFE；自动认定平行趋势 |
| `instrumental_variables` | 政策因果 | instrument、exposure、outcome | 第一阶段显著证明排除限制 |
| `local_projection` | 动态响应 | identified shock、outcome | 原始政策变化冒充shock |
| `var_svar` | 动态响应 | identified shock、outcome | 当前执行器未实现，固定为 `defer`；不得手写绕过 |
| `forecast_backtest` | 预测 | target、完整预测协议 | 随机时间切分；未来信息泄漏 |
| `nowcast` | 预测 | target、完整预测协议 | 最终修订值冒充实时数据 |
| `structural_model` | 结构 | outcome | 自动进入ready |

`adopt`仅表示结构化前提齐全；因果和结构设计仍必须
`review_required`。

当前套件只有 `local_projection` 和 `conditional_projection` 可以映射到可执行
动态分析。`var_svar` 只用于记录未来方法候选。
