# 变更日志

重要项目变更应记录在这里。

## Unreleased (0.6.0)

- Python 包新增 `__version__`，CLI 新增 `--version` flag。
- 清理路线图版本编号：下一步优先级从 V0.6.0 开始。
- 整理 GitHub 对外英文和中文文档。
- 新增 contribution、security、issue 和 pull request 社区文件。

## 0.5.4

- Requirements Gate 写入前必须先做简洁需求澄清，澄清结论记录到 4.8 小节。
- Requirements、Unit Plan、Final Acceptance 和 Bug Fix 人工评审阶段新增 tmux 防串聊提醒，不提交输入、不推进 workflow state。
- 正常 tmux 派发默认先清空 agent 输入框，并支持 `WAYGATE_TMUX_CLEAR_INPUT_BEFORE_DISPATCH=0` 关闭。
- compact/status 输出把当前项目目标版本与 Waygate 包版本分开展示。
- 项目 agent guide 补充版本规划事实源规则。

## 0.5.3

- 新增 Waygate Debian 包和 `/usr/bin/waygate` wrapper。
- 改进 compact 终端输出和 approval gate 状态展示。
- 修复 tmux runner 可靠性问题，包括 Codex pane 自动发现和 Claude pane 默认启动命令。
- 改进 Requirements 与 Unit Plan 中 AO、traceability 和 Journey mapping 校验。

## 更早历史

更早开发历史保留在 `progress.md`、`findings.md` 和 `task_plan.md` 中。这些文件是维护者历史，不是使用 Waygate 必需的用户文档。
