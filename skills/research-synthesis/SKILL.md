---
name: research-synthesis
description: "Use when synthesis of validated design, data, estimator, and robustness bundles is the complete single-stage task; for end-to-end or multi-stage research, invoke empirical-macro first."
license: Apache-2.0
compatibility: "Requires Python 3.12; scripts use uv; OpenAI4S can load the optional kernel.py sidecar."
---

# 研究综合

本 Skill 把已验证的宏观实证 Artifact 编译为一份证据绑定的中文科研报告。它只做
综合与交付，不重新估计、不重新画图，也不升级上游 claim。

## 入口边界

只有在“汇总现有研究结果”本身就是完整任务，且所有上游 bundle 已验证时，才能
直接使用本 Skill。对于还需要设计、数据、估计或稳健性检验的新研究，必须先调用
`empirical-macro`，并仅在其 `RouteDecision` 选择
`route_research_synthesis` 后进入本阶段。

## 何时触发

- 用户要求汇总、交付或复现一项已经完成的宏观实证研究；
- 已存在 `research-design`、data evidence、estimator 和
  `robustness-audit` 四类 bundle；
- 用户询问最终研究输出、报告、表格、图形或复现包。

研究问题尚未形成时使用 `research-design`；数据尚未准备时使用 `macro-data`；
估计或稳健性尚未完成时，不得提前使用本 Skill 伪造最终报告。

## 必需输入

四个 bundle 都必须使用显式相对路径、manifest SHA-256 和 expected IDs：

| `artifact_role` | 必需内容 |
|---|---|
| `research_design` | 研究问题、estimand、claim boundary |
| `macro_data` | 数据身份、样本、许可、checksum |
| `estimator` | 结构化逐 horizon 结果、CSV、PNG |
| `robustness_audit` | assessment、全部 required checks、plan timing |

先完整读取 [上游 bundle 合同](references/upstream-bundle-contract.md)。

## 固定流程

1. 用各上游 Skill 的公共 CLI validator 验证四个 required bundles。
2. 核对 expected IDs、manifest SHA-256 和 cross-bundle binding。
3. 数值只读取结构化 JSON 或已校验 CSV；禁止从 Markdown、自由文本或 OCR 提取。
4. 保留上游频率和 horizon 单位；月度路径不得在报告中写成季度，季度路径不得写成
   月度。
5. 编译 evidence、claim 和 limitation ledgers，保持 claim 单调不升级。
6. 运行 `scripts/run_research_synthesis.py` 生成研究包。
7. 运行 `scripts/validate_bundle.py`；失败时不发布部分包。

## 唯一主输出

科研人员只接收：

```text
research-report.md
tables/
figures/
reproduction/
```

内部审计 JSON 只能放在隐藏的 `.audit/`。不得生成重复的“技术版”和“大白话版”
报告。完整规则见 [研究报告合同](references/report-contract.md)。

## Stop-Ship 与固定 issue codes

| 条件 | 行为 | issue code |
|---|---|---|
| required bundle 缺失 | `stop_ship=true` | `required_bundle_missing` |
| manifest checksum 不匹配 | `stop_ship=true` | `manifest_checksum_mismatch` |
| 只有 Markdown 数值 | `stop_ship=true` | `structured_numeric_evidence_missing` |
| 用户要求多份重复主报告 | 保持单报告 | `single_report_contract_enforced` |
| audit 为事后计划 | 保持审核边界 | `post_result_exploratory` |
| 只有 pointwise intervals | 禁止整条路径推断 | `pointwise_not_simultaneous` |

缺失 required bundle 或 checksum mismatch 时，`primary_output=none`、
`artifact_outputs=[]`、`claim_boundary=not_evaluated`。

## Claim Boundary

- 输入未声明 estimator claim class 时使用 `preserve_upstream_claim`；不得默认
  `causal_candidate`。
- `associational_only` 永远不能升级为 causal。
- `causal_candidate + passed_declared_checks` 仍是
  `causal_candidate_review_required`。
- `post_result_exploratory` 不能表述为预注册。
- pointwise intervals 不能推出 simultaneous 或 whole-path significance。
- 禁止“因果关系已经确定”“全面稳健”“所有规格一致”等表述。

完整措辞见 [claim 语言政策](references/claim-language-policy.md)。

## 公共 CLI

```bash
uv run python scripts/run_research_synthesis.py \
  --request-json request.json \
  --adapter-capabilities-json configs/local-upstream-adapters.json \
  --project-root ../../.. \
  --output output

uv run python scripts/validate_bundle.py output
```

复现目录规则见 [复现包说明](references/reproduction-package.md)。

## OpenAI4S Runtime

OpenAI4S may import `kernel.py` and call `run()`. Check
`kernel.requirements()["imports"]` with `host.env.list_dependencies()` first.
If packages are missing, ask the user before calling
`host.env.create(packages=kernel.requirements()["pip"])`. Runtime setup does
not relax required-bundle, checksum, or claim-boundary gates.
