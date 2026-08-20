# 识别假设

## 状态语义

- `candidate_identified`：结构化识别前提已登记，不代表假设成立。
- `assumption_sensitive`：结构结论依赖尚需复核的模型或稳定性假设。
- `not_identified`：缺少必要识别结构，不得保留因果资格。

## 失败关闭规则

- 政策利率或其他政策变量的原始变化不是自动identified shock。
- DID必须登记处理、处理时点、比较组、anticipation和spillover风险。
- pre-trend不显著不能自动证明平行趋势。
- IV必须分别登记relevance、independence、exclusion与estimand解释。
- 第一阶段显著不能证明工具有效。
- LP和VAR只估计给定shock后的响应，不负责创造外生shock。
- 结构模型必须复核均衡概念、moments、参数稳定性和反事实范围。

所有 `causal_candidate` 和 `structural_candidate` 的
`review_required` 必须为 `true`。
