# 来源与数据权利政策

## DataPro-first

- DataPro 是默认主数据源和候选召回入口。
- 官方开放数据不是 DataPro 的隐式镜像。
- 合格 DataPro observation 写入 primary ledger 后不可被官方值替换。
- 当前只实现 World Bank WDI 官方 Connector；它只能补
  `ResidualGapManifest` 中的年度 country/territory WDI cell。
- IMF official Connector 尚未实现；不得宣传 IMF 自动补全。

## Fallback 门禁

只有同时满足以下条件才能执行官方 missing-only completion：

1. 请求的 `fallback_policy` 为 `allow_official_missing_only`，或 `ask`
   已取得明确批准；
2. DataPro 已先执行，且合格 cell 已锁定；
3. 官方来源在显式 allowlist；
4. 官方请求只包含 residual gap，不得包含已锁定 DataPro cell；
5. `source_system`、dataset、indicator、entity、frequency、单位、季调、
   价格基础和币种完成 exact identity 核对；
6. 原生 key 不一致时必须使用版本化 `SeriesIdentityMapping`，名称相似
   不能作为映射依据；
7. overlap 只用于核验，不进入 estimator，也不得替换 DataPro；
8. 许可证允许当前使用和输出方式；
9. 每行 provenance 记录真实 retrieval provider 和 source system；
10. 不执行跨统计来源拼接。

`SourceRouter` 在 `ask` 模式只返回候选和 `review_required=true`，不会
执行网络调用。`scripts/run_datapro_first.py` 默认 dry-run；fixture 模式
离线执行；只有显式 `--live` 才调用 DataPro，且 World Bank 仍只处理
允许的 gap。

## 贡献率与科研可用性

- `datapro_only`：DataPro 比例为 100%；
- `datapro_primary`：DataPro 比例不低于 80% 且低于 100%；
- `datapro_assisted`：DataPro 比例大于 0 且低于 80%；
- `datapro_attempted`：DataPro 已调用但没有 estimator cell。

贡献等级只决定宣传口径。完整 exact matrix 即使 DataPro 低于 80%，仍
可以 `analysis_ready`；反之，100% DataPro 但元数据、许可、provenance
或冲突未通过时仍不得进入估计。

## 数据保存

- 当前 sanitized-live fixture 只保留最小结构证据和有限 observation。
- DataPro 保存、派生和再分发权利尚未确认。
- 未确认前不得公开发布完整真实响应或大规模 observation。
- 每个公开数据源仍需逐数据集检查许可证，不能按机构名称统一推断。
- WDI source=2 已由数据集页面确认采用 CC BY 4.0；必须保留 World Bank
  attribution，并标明任何修改。

## 代码复用

- DBnomics、OpenEcon Data 等 AGPL 代码当前只借鉴设计，不复制。
- mcp-statdb 的许可证声明存在 MIT/Apache-2.0 不一致，不直接复用。
- 商业产品能力仅视为厂商声明，没有源码复用含义。
