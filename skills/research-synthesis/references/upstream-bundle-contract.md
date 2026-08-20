# 上游 Bundle 合同

## Source of Truth

权威顺序固定为：

```text
upstream structured Artifact
> checksummed CSV / PNG
> claim / evidence / limitation JSON
> generated research-report.md
```

不得根据目录时间、文件名中的 latest、mtime 或 glob 猜测权威 bundle。每个输入必须
在 request 中显式提供 `bundle_path`、`manifest_path`、
`expected_manifest_sha256` 和 `expected_ids`。

## 公共 Validator

| `artifact_role` | Skill | Validator |
|---|---|---|
| `research_design` | `research-design` | `scripts/validate_bundle.py` |
| `macro_data` | `time-series-dynamics` input evidence | `scripts/validate_input_evidence.py` |
| `estimator` | `time-series-dynamics` | `scripts/validate_bundle.py` |
| `robustness_audit` | `robustness-audit` | `scripts/validate_bundle.py` |

validator 必须使用 argv 调用，不得使用 shell interpolation。只有 return code 为 `0`
且 JSON stdout 中 `valid=true` 才算通过。

## Cross-Bundle Binding

至少核对：

- research plan、research request、analysis track 和 estimand；
- macro result、shock Artifact、数据 checksum、样本窗口；
- estimator request、result 和 run IDs；
- robustness baseline request、baseline run 和 claim eligibility。

canonical document digest 与物理文件 digest 不得混用。任何身份、checksum 或语义
不一致都必须 Stop-Ship，不得缩小样本或替换来源来掩盖失败。

## 禁止事项

- 不导入上游 Skill 的内部 Python 模块；
- 不从上游 Markdown 或图片 OCR 复制数值；
- 不重新估计或重新生成图形；
- 不自动修补、重签或改写上游 bundle；
- 不在 required evidence 缺失时发布部分研究报告。
