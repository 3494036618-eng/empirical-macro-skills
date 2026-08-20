# Artifact 交接

## 通用规则

每个阶段只通过公共 CLI、JSON Schema、相对路径和 SHA-256 交接。不得导入其他
原子 Skill 的 Python 私有模块，也不得把自由文本或截图作为数值合同。

## 阶段要求

| From | To | 必需证据 |
| --- | --- | --- |
| `research-design` | `macro-data` | research plan、data requirements、macro request、field provenance |
| `macro-data` | `time-series-dynamics` | `analysis_ready`、data、result、completion/provenance/run manifest |
| `time-series-dynamics` | `robustness-audit` | estimator bundle、request、plan、macro result、必要 shock Artifact、handoff |
| `robustness-audit` | `research-synthesis` | baseline、required checks、assessment、alternatives、audit manifest |
| `research-synthesis` | 用户 | report、tables、figures、reproduction |

## Checkpoint

成功阶段生成 checkpoint identity，但不复制 Artifact。恢复时重新验证：

1. workflow-state Schema；
2. capability registry version；
3. checkpoint identity；
4. 每个 Artifact checksum；
5. 对应原子 Skill 的公共 validator。

任一失败时停止，不回退到未验证文本。
