# 科研可用性与交付门禁

## 三轴状态

### execution_status

- `success`：provider 与本地处理成功执行。
- `partial`：有响应，但没有完整满足请求。
- `failed`：外部或本地执行失败，或空结果无法形成候选。

### research_readiness

- `ready`：关键语义与审计信息完整。
- `review_required`：存在可见但尚未解决的语义或覆盖问题。
- `blocked`：不能形成可审查研究数据。

### delivery_eligibility

- `analysis_ready`：允许进入后续计量模块。
- `comparison_only`：仅用于候选比较和人工复核。
- `not_deliverable`：不得交给后续估计。

## 强制关系

- `analysis_ready` 必须同时是 `success + ready`。
- `comparison_only` 和 `not_deliverable` 必须
  `eligible_for_estimation=false`。
- HTTP 200、`code=0`、文件生成成功都不能覆盖科研门禁。
- 部分成功不得删除失败实体或时间范围后伪装完整成功。

## 研究用途分级

### descriptive_latest

- 允许使用 latest；
- 完整身份、定义、许可、coverage 和 checksum/provenance 必须满足；
- 单位未知会降级为人工复核，但不默认要求历史 vintage。

### panel_analysis

- 实体×指标×期间 coverage 必须完整；
- 单位、价格口径和频率必须明确；
- latest 年度面板不因缺少历史 vintage 永久阻断；
- 缺失值、结构断点或跨源冲突只能 comparison-only。

### forecasting

- 必须有 observation release date 和 vintage；
- 必须排除 forecast origin 之后发布的数据；
- latest-only 不得替代 point-in-time 数据。

### real_time

- 必须提供 `as_of` 或 `specific_vintage`；
- release、vintage 和 future-information 检查全部通过；
- 不满足即 not-deliverable。

## Beta 失败关闭

以下情况不得 `analysis_ready`：

- 来源、数据集或指标身份不匹配；
- entity mismatch；
- frequency mismatch；
- 时间覆盖不完整；
- 当前研究用途要求的 unit、seasonal adjustment、price basis 或 definition 未知；
- forecasting/real_time 要求的 release/vintage 不可用；
- 许可证或数据权利未确认；
- checksum 或 provenance 不完整；
- 多候选未消歧；
- 请求包含上采样、插值、填补、自行季调、自动币种转换、
  rebasing 或跨来源拼接。
