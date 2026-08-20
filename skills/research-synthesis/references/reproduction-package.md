# 复现包说明

`reproduction/` 保存：

- `README.md`：中文执行说明；
- `data-availability-statement.md`：数据来源、许可和省略项；
- `code/`：各 Skill 的确定性源码、Schema、CLI 和 lockfile；
- `data-and-evidence/`：四个通过公共 validator 的上游 bundle；
- `environment/`：运行时版本；
- `licenses/`：第三方 notices。

`.venv/`、cache、pytest 临时文件和凭证不得进入复现包。所有执行命令使用 argv，
不得使用 shell interpolation。
