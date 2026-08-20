# 第三方软件与数据说明

## Runtime

- `jsonschema 4.26.0`：MIT License，用于 JSON Schema Draft 2020-12 合同验证。

## Development

- `Hatchling 1.32.0`：MIT License；
- `mypy`：MIT License；
- `pytest`、`pytest-cov`：MIT License；
- `Ruff`：MIT License；
- `types-jsonschema`：Apache-2.0 License。

精确版本和传递依赖冻结在 `uv.lock`。

## 上游证据

上游 evidence bundles 保留各自的许可证与 notice。JEL Example 5 数据和代码来自
Jordà–Taylor Local Projections replication package，固定 commit 为
`655696c1c576b7537c5a939d2c261f0a111ae663`，许可为 `CC0-1.0`。

Quarto、Pandoc、RO-Crate、BagIt 和 Frictionless Data 未作为 V0.1 runtime
dependency 打包。
