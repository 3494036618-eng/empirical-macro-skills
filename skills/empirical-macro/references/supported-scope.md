# 当前支持范围

## 可执行

| Method family | Executor | 结论边界 |
| --- | --- | --- |
| `dynamic_shock_response` | `time-series-dynamics` | 因果候选，仍需识别审核 |
| `conditional_dynamic_association` | `time-series-dynamics` | 仅条件动态关联 |

可执行工作流：

```text
research-design
→ macro-data
→ time-series-dynamics
→ robustness-audit
→ research-synthesis
```

## 不可执行

- `panel_association`
- `causal_policy_evaluation`
- `forecasting_nowcasting`
- `structural_modeling`
- 对应的 panel、DID、IV、RDD、Synthetic Control、forecast、Nowcast、
  DFM、DSGE 等方法

上述方法不得进入 research design、数据准备或替代方案生成。

## 非承诺

- 不支持全部宏观经济实证方法。
- 不自动证明因果关系。
- 不保证 DataPro 覆盖任意指标和历史范围。
- 不把已有方法卡、数据字段或设计能力宣传成估计器能力。
