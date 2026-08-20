# 路由策略

## 输入边界

宿主 Agent 只把自然语言编译为候选 `ResearchIntent`。Router 不读取原始提示词，
不运行关键词正则，也不调用模型。

## 固定优先级

1. 未实现方法：`method_not_implemented`
2. 非宏观实证：`out_of_scope`
3. 已有 workflow state：按当前 stage
4. 明确数据准备：`route_macro_data`
5. 缺少研究设计：`route_research_design`
6. 缺少合格数据：`route_macro_data`
7. 缺少估计结果：`route_time_series_dynamics`
8. 缺少稳健性结果：`route_robustness_audit`
9. 最终报告：`route_research_synthesis`
10. 已完成：`completed`

## 用户输出

`method_not_implemented` 的唯一用户输出：

```text
当前版本不能执行该方法
```

内部 issue code、method family、替代建议和解释不得附加到该输出。

## 状态优先

存在 `workflow-state.json` 时，已验证状态优先于自然语言中的“继续”“重跑”或
“已经完成”等表述。state 缺失、checksum 漂移或 registry version 不一致时，
不得猜测恢复位置。
