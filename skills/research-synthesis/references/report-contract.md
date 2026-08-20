# 研究报告合同

V0.1 只生成一份 `research-report.md`，固定包含：

1. 研究问题；
2. 数据；
3. 方法；
4. 主要结果；
5. 稳健性；
6. 结论与限制。

报告中的数值必须来自结构化 `result.json` 或 CSV。Markdown、图片 OCR 和上游说明
文件不能作为数值证据。`tables/` 与 `figures/` 必须和已验证 estimator bundle
保持 byte equality。
