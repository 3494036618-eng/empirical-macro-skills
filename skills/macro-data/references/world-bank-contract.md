# World Bank WDI Connector 合同

## 证据等级

- **已证实（E3）**：2026-08-14 在当前环境执行真实 Indicators API v2，
  成功获取 `CHN / FP.CPI.TOTL / 2019:2024 / source=2` 六条年度数据。
- **已证实（E1）**：World Bank 官方文档声明 Indicators API v2 无需 API Key，
  支持 `date`、`format=json`、`source`、`per_page` 和分页参数。
- **已证实（E1）**：World Bank Data Catalog 的 WDI 数据集页面明确标注
  `Creative Commons Attribution 4.0`。
- **待验证**：Indicators API 的正式限流、SLA、历史 observation vintage 和
  observation 级 release date。

## 官方入口

- Indicators API 文档：
  <https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-world-bank-data-program>
- 基本查询参数：
  <https://datahelpdesk.worldbank.org/knowledgebase/articles/898581>
- 指标元数据：
  <https://datahelpdesk.worldbank.org/knowledgebase/articles/898599-indicator-api-queries>
- WDI 数据集与许可证：
  <https://datacatalog.worldbank.org/search/dataset/0037712/world-development-indicators>
- 公共许可证说明：
  <https://datacatalog.worldbank.org/public-licenses>

## 首版受控范围

Connector Beta 接受：

- 一个或多个 ISO alpha-3 实体代码；
- 一个或多个官方 indicator code，最多 60 个；
- 年度频率；
- 四位年份起止范围；
- WDI `source=2`；
- 用户通过 `--source world_bank` 显式批准。

不支持：

- 自动从 DataPro 静默 fallback；
- 地区聚合、行业或非 ISO3 实体；
- 月度、季度或日度 WDI；
- 跨来源拼接；
- 自动频率转换、填补、季调、币种转换或 rebasing。

## 原始响应

一个 raw envelope 必须保留三份官方 JSON：

```text
observations
indicator_metadata
source_metadata
```

同时保存无凭证的请求 URL 和结构化参数。Connector 不改变 observation value，
不从名称推断 source-provided unit。

## 身份与语义

Canonical series key：

```text
WORLD_BANK|World Development Indicators|<ISO3>|<indicator_code>
```

World Bank observation 的 `lastupdated` 表示 source 最近更新时间，只记录为
`source_last_updated`，不得冒充 observation release date 或 vintage。

指标元数据中的 `sourceNote` 可作为 source-provided definition。若 `unit` 为空，
即使指标名称包含基期，也必须保持 `unit_status=unknown`。

## 许可

当前 Connector 只支持 Data Catalog 明确标注为 CC BY 4.0 的 WDI source=2：

```text
license.id=CC-BY-4.0
license.use_status=allowed
license.allows_requested_use=true
attribution=World Bank, World Development Indicators (WDI)
```

该结论不能外推到所有 World Bank 数据集、第三方数据或微观数据。

## 真实 E2E 结果

查询：

```text
CHN + USA / FP.CPI.TOTL / 2019—2024 / annual / source=2
```

结果：

```text
observations=12
entities=CHN,USA
indicator=FP.CPI.TOTL
frequency=A
source=World Development Indicators
execution_status=success
research_use=panel_analysis
research_readiness=ready
delivery_eligibility=analysis_ready
```
