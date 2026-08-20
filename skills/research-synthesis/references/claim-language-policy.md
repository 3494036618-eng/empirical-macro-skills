# Claim 语言政策

## 单调性

`research-synthesis` 只能保留或收紧上游 `claim_eligibility`，不能升级：

| estimator claim | audit assessment | 最终边界 |
|---|---|---|
| `associational_only` | 任意 | `associational_only` |
| `causal_candidate` | `passed_declared_checks` | `causal_candidate` |
| `causal_candidate` | `sensitive` | `causal_candidate` + sensitivity warning |
| `causal_candidate` | `inconclusive` | `causal_candidate` + no broad robustness claim |

## 允许表述

```text
在给定已识别冲击及仍未解决的外生性假设下，估计路径显示……
```

```text
在已声明并实际执行的检查范围内，没有发现超过冻结阈值的敏感性。
```

## 禁止表述

- 因果关系已经确定；
- 证明因果；
- 全面稳健；
- 所有规格一致；
- 整条路径显著；
- 联合显著；
- `whole-path significance`；
- `simultaneous significance`。

`associational_only` 还禁止“因果效应”“冲击响应”“导致”“引起”等措辞。

## Pointwise 边界

逐 horizon 的 95% pointwise intervals 只描述各 horizon 的边际不确定性。没有
simultaneous band 或预先冻结的联合检验时，不得推断整条路径联合显著。

## Post-Result Audit

`post_result_exploratory` 必须在报告中明确显示。即使所有 required checks 均完成且
assessment 为 `passed_declared_checks`，也不能改写成预注册或全面稳健。
