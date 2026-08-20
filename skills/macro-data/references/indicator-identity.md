# 指标与序列身份

## 最小身份

一个宏观序列不能只由名称标识。至少保存：

```text
provider
source_system
dataset_id
dataset_name
series_key
entity_code
indicator_code
time_grain
unit
seasonal_adjustment
price_basis
currency
```

DataPro 当前已提供 `series_key`，但其长期稳定性仍待验证。

## 实体规则

- CHN、HKG、MAC、HK 是不同原生代码。
- 请求 CHN 时，其他实体只能进入 `filtered_candidates`。
- 地区聚合不得映射为国家。
- 多对多或历史边界映射需要人工复核。

## 频率规则

```text
day -> D
week -> W
month -> M
quarter -> Q
year -> A
```

请求频率与 observed frequency 不同即为 `frequency_mismatch`。
首版不进行上采样、插值或复制。

## 元数据来源

- 只有独立原生字段才能标记 `source_provided`。
- 名称中的 `2010=100`、`未季调`、`不变价`可以保存为
  `name_evidence`，不能自动升级为来源确认字段。
- `p_date` 原样保存，语义固定为 `unresolved`，直到获得官方定义。
