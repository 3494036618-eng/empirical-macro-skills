# 宏观经济实证研究 Skills

> 基于 **Agent Plan 模型、专业数据集和豆包搜索**，构建可审计、可复现、会主动
> 拒绝越界结论的宏观经济实证研究 Skill。

[中文](#中文介绍) | [English](#english)

## 中文介绍

这是一套开放的 Agent Skills 参考实现，不绑定某一个 Agent 产品。只要目标 Agent
支持 `SKILL.md` 或 Agent Skills 目录约定，就可以加载这六个 Skill；仓库同时提供
`generic` 安装模式，允许用户指定任意 Agent 的 Skills 目录。

Agent Plan 提供推荐的完整能力组合：

| Agent Plan 官方能力 | 在本项目中的作用 |
| --- | --- |
| **Agent Plan 模型** | 理解自然语言研究需求、澄清问题、编排 Skill 和解释结果 |
| **专业数据集** | 召回宏观经济指标候选数据 |
| **豆包搜索** | 补充统计机构资料、最新信息和开源项目调研 |

这些在线能力通过 MCP 或宿主工具配置接入。Skill 不保存 API 密钥，也不把模型输出
直接当作科研结论；数据资格、JSON Schema、数值计算、状态流转和文件校验由确定性
Python 代码控制。

### 为什么需要这套 Skill

宏观经济实证研究不只是“跑一次回归”。一条可公开复现的研究链需要同时完成：

1. 把模糊想法变成可检验、可审查的研究设计；
2. 从专业数据集中筛选实体、指标、频率、时期和口径完全匹配的数据；
3. 区分描述、关联、预测和因果，不让结论超过证据；
4. 保存来源、参数、替代规格、失败记录和 SHA-256 校验值；
5. 交付数据、表格、图形、报告和复现材料。

### 专业数据集如何参与

`macro-data` 默认先使用 **专业数据集**中的宏观经济数据能力进行候选召回，再执行
本地确定性筛选和科研质量门：

```text
研究问题
→ 明确实体、指标、频率和时期
→ 专业数据集分批查询
→ 筛选完全匹配的候选记录
→ 核验定义、单位、季调、价格口径、覆盖和来源
→ 形成可分析数据包，或明确停止并报告缺口
```

在一次独立短窗口验证中，专业数据集返回 104 条候选记录，系统筛选出 24 条目标
观测，覆盖欧元区总体调和消费者价格指数、实际国内生产总值和存款便利利率。
该验证证明了“候选召回 + 本地筛选”链路可用；8 个季度不足以支持正式动态估计，
因此系统没有生成研究结论。这个结果不代表所有指标、国家和历史窗口都稳定可用。

### 六个 Skill

| Skill | 用户获得什么 |
| --- | --- |
| `empirical-macro` | 统一入口、阶段路由、停止原因和断点恢复 |
| `research-design` | 研究问题、识别审核、数据需求和结论边界 |
| `macro-data` | 规范化数据、来源、质量报告和文件校验值 |
| `time-series-dynamics` | 逐期动态估计、区间、图形和诊断 |
| `robustness-audit` | 替代规格比较、敏感性判断和限制 |
| `research-synthesis` | 研究报告、表格、图形和复现材料 |

```text
自然语言研究问题
    ↓
research-design
    ↓
macro-data  ←  Agent Plan 专业数据集
    ↓
time-series-dynamics
    ↓
robustness-audit
    ↓
research-synthesis
```

### 安装到任意 Agent

前置条件：

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/)

将 `/path/to/your-agent/skills` 替换为目标 Agent 的 Skills 目录：

```bash
uv run --project skills/empirical-macro --locked --no-dev \
  python skills/empirical-macro/scripts/install_skill_suite.py install \
  --source-root skills \
  --host generic \
  --target-root /path/to/your-agent/skills
```

安装器会为六个 Skill 分别创建锁定依赖环境，并在写入目标目录前运行快速验证。
依赖安装或验证失败时，已有目录保持不变。已提供 Trae、Codex 和 Claude Code 的
目标目录预设，但这些预设不是使用本项目的前提。

完整安装、升级和卸载命令见 [INSTALL.md](INSTALL.md)。

### Agent Plan 配置

需要在线模型、专业数据集或搜索能力时，请先准备可用的 Agent Plan 套餐，并按官方
文档启用相应能力：

- [Agent Plan 套餐概览](https://www.volcengine.com/docs/82379/2366394?lang=zh)
- [Agent Plan 快速开始](https://www.volcengine.com/docs/82379/2373738?lang=zh)
- [专业数据集配置与使用](https://www.volcengine.com/docs/82379/2479086?lang=zh)
- [豆包搜索配置与使用](https://www.volcengine.com/docs/82379/2301412?lang=zh)
- [套餐内 AFP 抵扣规则](https://www.volcengine.com/docs/82379/2516283?lang=zh)

API 密钥不得写入提示词、文档、代码仓库或研究 Artifact。

### 使用示例

```text
我想研究美联储意外收紧货币政策以后，美国通货膨胀在未来四年会怎么变化。
请完成一项可以公开复现的实证研究，并交付研究报告、结果图和复现材料。
```

```text
请优先使用 Agent Plan 专业数据集中的宏观经济数据，核对指标、地区、频率、
时期、单位和价格口径。数据不足或识别条件不成立时停止，不要编造结果。
```

### 科研边界

- 未通过识别审核时，只能报告条件关联，不能声称因果效应。
- 数据返回成功不等于科研可用，必须通过口径、覆盖、许可和质量检查。
- 专业数据集的短窗口验证不能外推为所有指标和历史区间均可用。
- 使用者负责最终审核数据许可、识别假设、模型诊断和研究结论。

---

## English

**Empirical Macro Skills** are an open-source Beta suite
of six host-neutral Agent Skills for auditable empirical macroeconomic
research.

The Skills can be installed into any Agent that supports the `SKILL.md` or
Agent Skills directory convention. A `generic` installer mode accepts any
user-supplied Skills directory.

The recommended Agent Plan capability stack is:

- **Agent Plan 模型** for natural-language understanding, orchestration, and
  explanation;
- **专业数据集** for macroeconomic data candidate retrieval;
- **豆包搜索** for official sources, current information, and open-source
  research.

Online capabilities are connected through MCP or host tools. Deterministic
Python code controls schemas, data eligibility, numerical calculations,
workflow state, and artifact checksums.

### Research workflow

```text
research question
→ research-design
→ macro-data and Agent Plan 专业数据集
→ time-series-dynamics
→ robustness-audit
→ research-synthesis
```

The suite separates identified-shock responses from noncausal conditional
associations, fails closed when required evidence is missing, and preserves
data provenance and unfavorable robustness results.

### Generic installation

```bash
uv run --project skills/empirical-macro --locked --no-dev \
  python skills/empirical-macro/scripts/install_skill_suite.py install \
  --source-root skills \
  --host generic \
  --target-root /path/to/your-agent/skills
```

See [INSTALL.md](INSTALL.md) for known host presets, upgrades, and uninstall.

### Beta status

The public package has passed privacy scanning, plugin-schema validation,
clean installation, six post-install validators, upgrade, and managed
uninstall. Full live routing certification across every Agent host is still
pending and is not claimed by this Beta.

## Repository structure

```text
.
├── README.md
├── INSTALL.md
├── SECURITY.md
├── CONTRIBUTING.md
├── LICENSE
├── THIRD_PARTY_NOTICES.md
├── plugin.json
├── scripts/
└── skills/
    ├── empirical-macro/
    ├── research-design/
    ├── macro-data/
    ├── time-series-dynamics/
    ├── robustness-audit/
    └── research-synthesis/
```

Each Skill contains a `SKILL.md` entry point and may include scripts, source
code, schemas, references, tests, and redistributable public fixtures.

## Security, contribution, and license

- [Security policy](SECURITY.md)
- [Contribution guide](CONTRIBUTING.md)
- [Publication checklist](docs/PUBLICATION_CHECKLIST.md)

Run the standalone release scan before publishing:

```bash
python scripts/scan_public_release.py .
```

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
