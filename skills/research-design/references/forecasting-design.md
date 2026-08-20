# 预测与 Nowcasting 设计

历史预测必须冻结：

1. forecast target；
2. forecast origin；
3. horizon；
4. 当时可获得的target/data vintage；
5. rolling、expanding或fixed holdout时间切分；
6. naive、AR或季节性基线；
7. loss function与聚合规则；
8. 训练窗口内的预处理、特征选择和调参。

禁止：

- 用最终修订数据回填历史信息集；
- 随机切分时间序列；
- 根据测试集结果选择特征、模型或超参数；
- 只报告优于基线的窗口；
- 把预测准确解释为经济机制已识别。

当前 `research-design-request` 草案尚不能完整表达target vintage、
temporal split、baseline和loss。因此预测请求必须保持失败关闭，直至
合同版本化扩展并通过point-in-time数据验收。
