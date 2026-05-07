# 参与 Waygate 贡献

[English](CONTRIBUTING.md)

感谢你愿意改进 Waygate。本项目是 workflow controller，因此任何改动都应保留可审计性、状态安全和显式验证。

## 开发环境

```bash
git clone <repo-url>
cd workflow-controller
python -m pytest workflow_controller/tests -q
```

如果不使用项目虚拟环境，请准备一个包含测试依赖的 Python 环境。

## 提交 PR 前

请确认：

- 改动范围聚焦于一个行为或一个文档目标；
- 不提交 `.rrc-controller-*` 这类本地 controller state 目录；
- 不提交 `dist/`、`.build/` 等生成产物；
- 行为变更尽量补回归测试；
- CLI 行为、workflow 语义或 artifact 改变时同步更新文档；
- 全量测试通过。

推荐验证：

```bash
python -m pytest workflow_controller/tests -q
```

打包验证：

```bash
python -m pytest workflow_controller/tests/test_packaging.py -q
```

## PR 说明

PR 内容请包含：

- 改了什么；
- 为什么改；
- 如何验证；
- 迁移或兼容性说明；
- 是否影响 state artifacts 或 gate 格式。

## 代码风格

Waygate 偏向小而明确的改动，不鼓励无关大重构。添加新抽象前，优先复用项目已有 patterns、parsers、validators 和 runner 抽象。

不要把 secret 写入 artifacts、logs、tests 或 examples。
