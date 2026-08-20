# DataPro 宏观合同

## 证据等级

- `live`：本次直接调用 DataPro。
- `sanitized-live`：真实响应的最小脱敏副本。
- `synthetic`：人工构造的边界或故障数据。
- `mock`：替代外部调用的测试行为。

四类证据不得混报。

## 已证实字段

响应顶层至少出现：

```text
code
msg
trace_id
dataset_type
items
```

宏观 item 至少观察到：

```text
series_key
series_name
source_system
dataset_id
dataset_name
entity_code
entity_name
indicator_code
indicator_name
time_raw
time_grain
year
value
p_date
```

季度样本还出现 `quarter` 和 `unit_raw`。

## 已证实行为

- `dataset_type=macro` 可返回 World Bank WDI 和 IMF 序列。
- 2026-08-15 复验中，严格 WDI 查询连续两次精确返回
  `WORLD_BANK / WDI / CHN / FP.CPI.TOTL / 2019–2024`，两次语义指纹一致。
- 该结果取代“当前 WDI 必然召回失败”的状态判断，但历史响应证明来源约束曾
  返回 IMF，因此仍不能把自然语言来源要求视为通用硬过滤器。
- 请求 CHN 仍可能返回 HKG、MAC、HK 或其他国家。
- 请求月度 CPI 可能只返回年度 WDI。
- 请求较长季度范围可能只返回末段数据。
- 不支持的指标可返回 `code=0`、`items=[]` 和“不计费”消息。
- 显式字段约束、排除词和完整 `series_key` 不能被视为硬过滤器；同一精确
  Query 连续 3 次均可能只返回 IMF，并在月度/季度候选之间波动。
- 2026-08-15 首次观察到 BIS `WS_TC / QCNPAM770A`。相同查询两次均返回
  BIS，但字段 Schema 漂移，且同一系列 24/24 观测值冲突，最大绝对差 27.8；
  当前必须失败关闭。
- 请求国家统计局可返回 World Bank；请求 IMF BOP 可返回 WEO；请求 Eurostat
  和 FRED 可分别返回 IMF CPI 和 IMF Labor Statistics。

## 待验证

- `p_date` 的官方定义；
- unit、seasonal adjustment、price basis 和 definition 的稳定合同；
- release、revision 和 vintage；
- 分页、截断、排序和最大结果数；
- 同一 Query 的长期稳定性；
- 数据保存、派生和再分发权利；
- 限流、费用和完整错误码。

## Connector 规则

- 只从环境变量或 Trae MCP 配置读取 Key；默认顺序为
  `DATAPRO_AGENT_PLAN_KEY`、`~/.trae/mcp.json`、Trae CN 兼容配置。
- 不记录 Key、Header、Cookie 或完整 trace ID。
- 保留 DataPro 原始字段，不补造缺失字段。
- `code=0` 只表示 provider 执行，没有科研资格含义。
- live test 默认关闭，必须显式 `--live`。
