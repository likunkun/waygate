# 变更日志

重要项目变更应记录在这里。

## 0.6.0a

- 新增 Requirements prototype review bundle，供 Plannotator 审阅原型证据。
- 新增 `prototype-manifest.json` 校验、规范化 review manifest、本地原型资产复制和只读 localhost 预览链接。
- Requirements 的 Plannotator 审阅对象改为 review bundle，同时 approval 仍落在 `approvals/requirements-and-acceptance.md`。
- 强化 UI/UX 和 Web 原型预检：阻断缺文件、未知 AC、缺页面状态、缺点击路径、缺 AC 映射和敏感 URL query。

## 0.6.0

- Python 包新增 `__version__`，CLI 新增 `--version` flag。
- 清理路线图版本编号：下一步优先级从 V0.6.0 开始。
- 整理 GitHub 对外英文和中文文档。
- 新增 contribution、security、issue 和 pull request 社区文件。
- Requirements 草案修订后，controller 预检仍会先于人工确认执行。

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
