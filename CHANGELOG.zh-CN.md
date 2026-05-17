# 变更日志

重要项目变更应记录在这里。

## 0.6.0d

- 即使存在 prototype review bundle，Requirements Plannotator 的审批目标也恢复为 `approvals/requirements-and-acceptance.md`。
- `plannotator-review.html` 保留为 controller preview server 提供的原型渲染辅助预览页。
- Plannotator review metadata 会记录审批文件、辅助预览文件、manifest 路径和临时 preview URL，但不会把临时 localhost URL 写入 approval 文件。

## 0.6.0c

- 目标项目基础设施 intake 现在适用于每个 Requirements draft，并固定输出 `## 4.9 目标项目基础设施信息`。
- Requirements preflight 会阻断缺失、不完整或仍是占位内容的基础设施类别。
- 新增 `waygate doctor`，输出 executable path、module path/version、dpkg version、PATH 候选和命令 shadow 警告。
- Debian 打包会强制 control `Version`、包内 `__version__` 和 `waygate --version` 保持一致。
- Debian post-install 会提示 `~/.local/bin/waygate` 等用户级 wrapper 的 shadow 风险，但不会删除用户文件。

## 0.6.0b

- 新增 Requirements、Unit Plan 和 Final Acceptance 的原型到生产 UI 一致性门禁。
- prototype manifest 中每个 UI/Web 原型必须通过 `implementation_targets` 或兼容别名映射真实实现目标。
- 一致性验收从整张 prototype target 扩展到 required `surface_contracts`，覆盖弹窗、抽屉、面板、选择器、管理 surface 和真实入口。
- Unit Plan 新增真实 route/page 一致性测试校验，要求具体断言。
- Final Acceptance 新增 `Prototype Conformance Matrix`，缺失或失败的一致性证据会阻断终验。
- Controller State Patch 保留 `currentUnitIsWebSystem`。

## 0.6.0a

- 新增 Requirements prototype review bundle，供 Plannotator 审阅原型证据。
- 新增 `prototype-manifest.json` 校验、规范化 review manifest、本地原型资产复制和只读 localhost 预览链接。
- approval 仍落在 `approvals/requirements-and-acceptance.md`；后续版本把渲染后的 prototype HTML 仅作为辅助预览。
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
