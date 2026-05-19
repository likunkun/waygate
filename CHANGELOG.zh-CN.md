# 变更日志

重要项目变更应记录在这里。

## 0.6.0h

- `waygate doctor` 新增 `tmux_config` section，检查推荐 `~/.tmux.conf` 配置：`mouse on`、`history-limit 100000`、`@scroll-speed 5` 和 `@copy-mode-vi 'on'`。
- tmux 配置诊断保持只读：warning 会展示 expected/actual 和 manual action，但 Waygate 不修改也不 reload tmux 配置。
- Doctor 输出改为先展示 `summary:`、`focus:` 和 `action_required:`，再展示安装来源、PATH、环境、skills 和 Claude assets 等详细 section。
- 新增 `waygate doctor --color auto|always|never`，高亮状态、P1 关注项、manual action 和 section 标题，方便人工扫描；非 TTY 输出默认保持纯文本。
- 保留既有详细 section 便于排障，同时把 PATH shadow、版本不一致、缺工具、缺 skill 和 tmux 配置事项提升到顶部。
- README、USAGE、路线图、推荐环境文档和包版本同步到 `0.6.0h`。

## 0.6.0g

- `waygate doctor` 新增 `claude_assets` section，报告 `~/.claude/commands`、`agents`、`rules`、`plugins` 的路径、状态和数量，不读取内容。
- `skill_recommendations` 与 README 推荐基线对齐，补齐 code review、plan execution、webapp testing，以及 UI-heavy requirements 所需的 `frontend-design` / `ui-ux-pro-max`。
- Controller prototype preview server 默认绑定并展示 `0.0.0.0`，让原型审阅 URL 更适合远程浏览器访问。
- 默认向 Plannotator 子进程传入 `PLANNOTATOR_HOST=0.0.0.0`，并用同一 host 展示 Plannotator 审批页。
- 文档说明 `0.0.0.0` 是监听/展示地址，远程浏览器通常需要替换为运行 Waygate 主机的 IP。

## 0.6.0f

- Unit Plan 人工确认新增真实 E2E 证据门禁：mock/stub 核心业务 API 的浏览器测试不能覆盖 E2E、golden path、prototype conformance、Journey closure 或 Web 系统验收。
- Verifier evidence rows 新增 environment kind、真实入口、核心 API mock 状态、mocked routes、浏览器 console/page/request 运行错误和截图引用字段。
- 即使命令退出码为 0，带核心 API mock 的浏览器 E2E 证据也会标记为 `invalid`；真实 E2E 中记录到 console/page/request runtime error 时验证失败。
- Final Acceptance 与 Prototype Conformance 矩阵新增环境、mock 和 runtime error 列，并用真实 E2E 证据阻断非真实 prototype/golden-path 终验。
- 当 Requirements 或人工反馈要求远程日志、生产页面或部署后验证时，必须使用 `environment_kind=production_readonly` 的只读生产证据，不能用本地测试替代。

## 0.6.0e

- 扩展 `waygate doctor` 的 `environment_checks`，覆盖 Python、pytest、tmux、tmux session、Claude Code、Codex、Plannotator、`dpkg-deb` 和推荐 Plannotator port `20000`。
- 扩展 `waygate doctor`，扫描常见 agent skill 根目录、报告已安装 skills、输出推荐 workflow skill 缺口 warning，并支持 `WAYGATE_SKILL_ROOTS` 追加自定义根目录。
- Claude Code、Codex 和 Plannotator 保持可选，缺失时输出 warning/manual action，不让 `doctor` 失败。
- 新增 `docs/operations/` 双语推荐环境 recommended-environment 文档和 `docs/product/` 双语 Waygate introduction/best practices 文档，包含 PPT 大纲但不生成 `.pptx`。
- 更新 README、USAGE、ROADMAP 和包内文档入口，记录 V0.6.0e，同时保持 V0.6.1 和 V0.6.2 为后续范围。
- Debian 包会把新增 product 与 operations 文档安装到 `/usr/share/doc/waygate/docs/`，并与 `workflow_controller.__version__` 保持版本一致。

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
