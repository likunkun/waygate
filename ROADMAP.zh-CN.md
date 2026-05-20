# Waygate 路线图

[English](ROADMAP.md) | [README](README.zh-CN.md)

本文描述 Waygate 作为 AI 编程流程控制面的演进方向。这里的版本号是规划标签，不承诺外部发布节奏。

## 已完成基础

### V0.1 - Test Strategist

- Test Strategist runner 配置和 role-specific env 隔离。
- 测试策略 prompt、schema 和 artifacts。
- Controller 编排和 critical feedback 路由。
- Review package 与 Unit Plan gate 校验集成。

### V0.2 - 架构拆分

- 引入分层包结构：
  - `state_machine/`
  - `gates/`
  - `runners/`
  - `prompts/`
  - `steps/`
- 内部 Python package 继续保留 `workflow_controller` 名称，避免兼容性破坏。

### V0.3 - Acceptance-Driven Loop

- Acceptance Obligation Ledger，用于追踪人工反馈和最终验收问题。
- Requirements quality gate，校验 AO 到 AC 的映射和 verification layer。
- 产品设计与技术架构可追溯。
- Verifier evidence schema，输出结构化 evidence rows。
- Final Acceptance Evidence Matrix。
- CodeSimplifier/Refiner 在 review 和 verification 前介入。

### V0.4 - Control Plane

- 通过 `AGENTS.md` 初始化项目 agent 操作规约。
- Requirements negotiation loop 和 controller 预检。
- Change Request Ledger。
- 独立 Bug Fix Gate。
- Journey Acceptance Layer。
- Final Scope Audit。
- Requirements Dialogue Brief。

### V0.5 - Runner 与安装体验

- tmux target 自动识别 Claude 和 Codex pane。
- 在 tmux 内自动创建 Claude pane。
- 显式 `tmux-codex` runner 可发现已有 Codex pane。
- 审批摘要优先的 Markdown gate。
- 低噪声 compact 终端输出。
- Debian 包构建脚本和 `waygate` 命令 wrapper。

## 下一步优先级

### V0.5.6 - Spec Intake & Dependency Documentation

目标：先把本地需求 spec 输入和依赖文档做成可审计闭环，再扩展外部 spec 生态。

计划：

- 补齐本地运行、pytest、tmux、Claude/Codex runner、Plannotator、skills 和 Debian packaging 依赖说明。
- 为 `waygate init`、`waygate start`、`waygate go` 增加 Waygate Markdown `--spec <path>` 输入。
- `session.json` 只保存 `requirementsSpec.path`、`requirementsSpec.hash`、`requirementsSpec.sourceType`、`requirementsSpec.importedAt`。
- 将 spec metadata 注入 Requirements Dialogue Brief、Requirements Draft prompt 和 draft summary artifact。
- 保留 Requirements 人工审批和 controller quality preflight；`--spec` 不是审批绕过机制。

### V0.6.0 - Infrastructure Knowledge Base

目标：沉淀运维与基础设施知识，但不混入 V0.5.6 spec intake 范围。

计划：

- 建立 operations knowledge base，记录本地基础设施假设、服务依赖和排障路径。
- 将环境/runbook 事实与 Requirements、Unit Plan artifact 分开。
- 在该版本明确启动前，不把基础设施文档纳入 V0.5.6。

### V0.6.0a - Prototype Review Bundle for Plannotator

目标：让 V0.6.0 生成的 prototype evidence 在 Requirements 人工确认前可以被 Plannotator 直接、顺滑审阅。

状态：已在 package `0.6.0a` 实现。

已交付：

- 在 Requirements draft artifacts 下生成结构化 prototype manifest，记录 prototype id、类型、路径或 URL、标题、关联 AC、关联 Journey、页面状态、点击路径、缩略图或预览提示，以及审阅重点。
- 渲染 Requirements 专用 Plannotator review bundle，把生成的原型图、本地 HTML 原型、外部原型 URL、AC/Journey 映射表组合成可审阅视图。
- `approvals/requirements-and-acceptance.md` 始终作为 approval gate 和确认状态事实源，prototype review bundle 提供辅助审阅上下文。
- 将本地原型资产路径规范化到 controller artifact tree，避免 Plannotator 依赖 agent 随手写出的任意文件系统路径。
- Requirements 预检增加原型文件缺失、可点击原型访问方式不完整、页面状态缺失、点击路径缺失、AC 映射缺失、未知 AC 引用和敏感 URL query 的阻断。
- 保持审批语义不变：Plannotator Approve 仍不能绕过 Requirements quality gate。

### V0.6.0b - Prototype Conformance Gate

目标：让 Requirements 阶段的原型成为 Unit Plan、Verifier 和 Final Acceptance 的生产 UI 验收合约，而不只是可点击 review artifact。

状态：已在 package `0.6.0b` 实现。

已交付：

- prototype manifest 中作为 UI/Web 合约的条目必须通过 `implementation_targets` 映射真实实现目标，并兼容 `production_targets` / `real_targets` 别名。
- 多 surface 的 UI/Web prototype 必须为每个 required route、page、component、dialog、drawer、panel、form、selector、management surface 和真实入口声明 `surface_contracts`。
- Requirements 正文即使没有打开 `currentUnitNeedsUiDesign` 等 state flag，只要声明原型义务或 UI contract，也会触发 manifest 和真实实现目标预检；保留 controller policy work 例外。
- Unit Plan approval 会拒绝只打开静态 prototype artifact、`prototype-review` 或 `file://...prototype` 的测试。
- prototype conformance test case 必须声明 `prototype_conformance`、适用时的 `prototype_surfaces`、`production_targets`、可执行 command、具体 expected 和真实入口 `user_steps`；浏览器 route/page/surface 必须是 E2E。
- Final Acceptance 渲染包含 Surface 和 Entry Point 列的 `Prototype Conformance Matrix`，缺失或未通过的原型到生产 UI 证据会阻断终验。
- Controller State Patch 支持并保留 `currentUnitIsWebSystem`，与 `currentUnitNeedsUiDesign` 一起进入后续 gate 判断。

### V0.6.0c - Target Infrastructure Intake and Install Diagnostics

目标：让每个目标项目都强制采集基础设施事实，并让已安装 `waygate` 的实际运行来源可诊断。

已交付：

- 目标项目基础设施 intake 适用于每个 Requirements draft，不再只服务 V0.6.0 controller policy work。
- Requirements 固定包含 `## 4.9 目标项目基础设施信息`，覆盖代码仓库、运行时、调试、参考环境、文档、架构/交互/接口和依赖事实。
- Requirements approval 会阻断缺失 4.9、缺基础设施类别或类别内容为空/占位。
- Debian package version、包内 `__version__` 和 `waygate --version` 保持一致。
- 新增 `waygate doctor`，并在 Debian post-install 对 `~/.local/bin/waygate` 等用户级 wrapper 给出 shadow warning。

### V0.6.0d - Requirements Plannotator Approval Source Correction

目标：让 Requirements approval 固定锚定 approval Markdown，同时保留原型渲染辅助预览。

已交付：

- Requirements Plannotator 即使在 `plannotator-review.html` 和 `prototype-review-manifest.json` 存在时，也只 annotate `approvals/requirements-and-acceptance.md`。
- Requirements review 期间继续启动 controller preview server，单独打印 `plannotator-review.html` 的辅助预览 URL，与 Plannotator 审批 URL 区分。
- Plannotator review metadata 记录审批文件、辅助预览文件、manifest 路径和临时 preview URL，但不把临时 localhost URL 注入 approval 文件。

### V0.6.0e - Environment Diagnostics and Introduction Materials

目标：让推荐本地环境和 Waygate 介绍材料在源码与安装包中都容易检查和使用。

已交付：

- 扩展 `waygate doctor` 的 `environment_checks`，覆盖 Python executable/version、`pytest`、`tmux`、tmux session、Claude Code、Codex、Plannotator、`dpkg-deb` 和推荐 Plannotator port `20000`。
- 扩展 `waygate doctor`，扫描常见 agent skill 根目录、报告已安装 skills、输出推荐 workflow skill 缺口 warning，并支持 `WAYGATE_SKILL_ROOTS`。
- Claude Code、Codex 和 Plannotator 保持可选；缺失时输出 warning/manual action，不让 `doctor` 失败。
- 在 `docs/operations/` 新增双语推荐环境 recommended-environment 文档，包括 `docs/operations/recommended-environment.zh-CN.md`。
- 在 `docs/product/` 新增双语 Waygate introduction and best practices 文档，包含 10-12 页 PPT 大纲，但不生成 `.pptx`。
- Debian 包会把新增 product 与 operations 文档安装到 `/usr/share/doc/waygate/docs/`。
- V0.6.1 External Spec Intake 和 V0.6.2 Strict Test Presence 仍是后续 planned scope，不属于 V0.6.0e 当前交付。

### V0.6.0f - Real E2E Evidence Gate

目标：防止带 mock/stub 的浏览器测试被当成真实 E2E、golden path、prototype conformance 或生产一致性证据。

已交付：

- Unit Plan 预检会阻断 E2E、golden path、prototype conformance、Journey closure 和 Web 系统验收测试中对 `**/api/...` 等核心业务 API 的 browser mock/stub。
- 规范 test case metadata：`environment_kind`、`entrypoint` / `real_entrypoint`、`allows_mock`、`mocked_routes`；mock 只能用于非 E2E 的 component/contract/visual 辅助测试。
- Verifier evidence rows 新增 environment kind、真实入口、核心 API mock 状态、mocked routes、browser console errors、page errors、request failures 和 screenshot refs。
- 命令退出码为 0 的 mocked browser E2E 也会被分类为 invalid evidence；真实 E2E 中记录到浏览器运行错误时验证失败。
- Final Acceptance 和 Prototype Conformance 矩阵展示环境、mock 状态与 runtime errors，并要求 prototype/golden path 必须有真实 E2E evidence。
- Requirements 或人工反馈要求远程日志、生产页面或部署后验证时，要求显式 `production_readonly` 证据。

### V0.6.0g - Doctor Coverage and Remote Review Reachability

目标：完成 V0.6.0f 人类可读收尾记录，并提升环境诊断和远程浏览器审阅原型的可达性。

已交付：

- 在人类可读项目记录中记录 V0.6.0f 已交付，不手工把历史 `.rrc-controller-v0.6.0f/session.json` 改成 `DONE`。
- `waygate doctor` 新增 `claude_assets` 检查，覆盖 `~/.claude/commands`、`~/.claude/agents`、`~/.claude/rules`、`~/.claude/plugins`；输出仅包含路径、状态和数量。
- 推荐 skill warning 与 README 推荐基线对齐，覆盖 persistent planning、startup、brainstorming、writing plans、TDD、debugging、test strategy、refiner、verification、code review、plan execution、webapp/browser verification，以及 `frontend-design` / `ui-ux-pro-max`。
- Controller prototype preview server 默认绑定 `0.0.0.0`，但浏览器 URL 使用本机主 IP 地址展示；`WAYGATE_PREVIEW_HOST` 覆盖 preview bind host，`WAYGATE_DISPLAY_HOST` 覆盖终端展示 host。
- 通过 `PLANNOTATOR_REMOTE=1` 请求 Plannotator 开启远程访问，但审批页 URL 使用本机主 IP 地址展示。
- 文档说明 `0.0.0.0` 是监听地址，不是浏览器目标；controller prototype preview 固定使用 `20001` 端口，便于 ACL 规划。

### V0.6.0h - tmux Recommended Config and Doctor Information Hierarchy

目标：把推荐 tmux 工作站配置纳入 `waygate doctor`，并让人工处理事项更容易扫描。

已交付：

- 新增 `tmux_config` 检查，固定读取 `~/.tmux.conf`，覆盖 `mouse on`、`history-limit 100000`、`@scroll-speed 5` 和 `@copy-mode-vi 'on'`。
- 支持解析 `set -g key value` 与 `set-option -g key value`，包括简单引号值；doctor 只报告推荐 key，不输出无关配置行。
- `doctor` 保持只读：缺失或不匹配的 tmux 配置只产生 warning 和 manual action，Waygate 不修改也不 reload tmux 配置。
- Doctor 输出顶部新增 `summary:`、`focus:` 和 `action_required:`，再展示安装来源、环境与详细清单。
- 新增 `waygate doctor --color auto|always|never`，让 TTY 用户能用颜色识别状态、P1 关注项、manual action 和 section 标题；非 TTY 输出默认保持纯文本。
- 保留既有详细 section，包括 `environment_checks`、`skill_recommendations` 和 `claude_assets`，方便继续排障。

### V0.6.0i - Documentation Lifecycle

目标：让正式文档可发现、文档更新可审计，同时避免把所有历史文档缺口都变成本轮终验阻断。

已交付：

- `waygate init/start` 生成 `docs/README.md` 作为文档入口和轻量登记表；已有用户文件时写 `.generated` 草案，不覆盖原文件。
- 生成的 `AGENTS.md` 要求读取 `docs/README.md`，区分正式文档、过程状态文档，并明确 `.rrc-controller-*` 是审计证据。
- Requirements `文档地址` intake 改为结构化盘点：正式维护文档、Controller 过程证据、外部 Agent / 人工沟通文档、外部 wiki / 设计稿 / API 文档、缺失但需要沉淀的文档。
- Unit Plan 新增 Document Deliverables Matrix prompt 和校验，覆盖长期产品、架构、流程、运维、证据规则和文档生命周期变更。
- Final Acceptance 展示文档交付状态，并且只阻断 `Required For Acceptance = true` 的文档动作。

### V0.6.0j - Requirements Infrastructure Follow-up and Validation

目标：保留无 `--spec` Requirements intake 的直接对话体验，同时防止未验证的基础设施事实被复制进 approval gate。

已交付：

- 无 `--spec` 时，Requirements drafter 第一轮仍只能提出澄清问题；用户给出具体回答后，才读取项目上下文。
- 首次澄清后要求 drafter 盘点 `## 4.9 目标项目基础设施信息` 的 7 类事实；如果仍缺基础设施事实，继续在 tmux pane 中直接追问用户。
- 对用户补充的代码仓库、运行环境、调试入口、参考环境、文档、接口和依赖事实要求非破坏性核对。
- 外部系统、生产环境、私有 wiki/API 或其他无法访问的事实必须标注为用户提供且未能直接验证，不能伪造证据。
- `## 4.8` 记录基础设施追问、用户回答、核对方式、验证结论和残余风险；`## 4.9` 为每类基础设施事实记录来源和验证状态。
- Requirements 预检加强对“未发现/没有/不涉及”等声明的校验；当 4.9 声称“用户确认”或“已验证”时，要求 4.8 有对应记录。

### V0.6.1 - External Spec Intake

目标：在 Waygate Markdown intake 稳定后，再增加外部 spec 生态的显式导入路径。

计划：

- 设计 OpenSpec 和 Spec Kit 的导入契约。
- 为受支持外部格式增加 parser、validation 和 conversion artifacts。
- 对已识别但未启用的格式继续给出清晰 unsupported/deferred 错误。

### V0.6.2 - Strict Test Presence

目标：非 manual 验收标准不能在缺少可执行测试或明确证据时通过。

计划：

- 将 Test Strategist 前移到 requirements 阶段。
- 要求每条非 manual AC 都有可执行测试用例。
- Unit Plan test case 必须包含 fixture/setup、command 和 expected assertion。
- Verifier 和 Final Acceptance 的 evidence rows 必须能映射回 Test Case ID。

测试用例契约强化路线：

- TC1 - Test Case Contract v1：定义稳定的 Unit Plan `test_cases[]` 契约，包含 `acceptance_criteria[]`、`covers_obligations[]`、`covers_journeys[]`、`layer`、`path_type`、`golden_path`、`setup[]`、`entrypoint`、可选 `cleanup[]`、`command_id`、`manual_evidence` 和 `assertions[]`。
- TC2 - 事实源收敛：以 Controller State Patch 中的 `test_cases[]` 作为权威事实源；Markdown Test Case Matrix 只从结构化数据渲染，不再让 prose 和 JSON 各自成为事实源。
- TC3 - 旧格式兼容与迁移：继续读取 `acceptance_criterion`、`fixture`、`command`、`evidence`、`expected`、`journey_refs`、`journeyRefs` 等旧字段，但归一化到 v1 契约，并输出迁移 warning。
- TC4 - 严格 Unit Plan 预检：阻断缺失或未知 AC/AO/Journey 引用、无法解析的 `command_id`、static-only 冒充行为覆盖、弱断言、E2E 缺少 `user_steps`、缺少 setup/entrypoint，以及 manual evidence 冒充自动化通过。
- TC5 - 人工确认前 Test Case Review Agent：在 Unit Plan 人工确认前运行不具备批准权的审阅 agent，标注浅断言、假 fixture、过宽命令、只覆盖 happy path 的 E2E、AO 只挂名覆盖，以及不能证明所映射 AC 的测试用例。
- TC6 - Verifier evidence 对齐：每个计划中的 test case 都产出 evidence row，包含 command ID 和结构化 assertions；未执行的计划 test case 明确标记为 `missing`；manual evidence 与自动化 `passed` 结果分开。
- TC7 - Final Acceptance 矩阵升级：展示从 Requirement / Use Case / Journey / AC / AO 到 Test Case 和 Evidence 的完整链路，让人工审的是可追踪证据而不是 agent 总结。

### V0.6.3 - Per-Role Runner Configuration

目标：Builder、Refiner、Reviewer、Verifier 和 Bug Fix Agent 都可以独立配置。

计划：

- 增加 role-specific runner、command、env 和 timeout 配置。
- 标准化 artifacts 中的 role metadata。
- 避免 secrets value 出现在 logs 和 artifacts 中。

### V0.6.4 - OpenCode Runner

目标：实现一等 OpenCode runner。

计划：

- 实现 runner 调用和完成信号。
- 统一 metadata 和 artifacts 契约。
- 增加 dispatch、completion 和 failure mode 回归测试。

### V0.6.5 - Task Workspace / Branch Isolation

目标：降低跨任务修改和旧状态污染。

计划：

- 每个 unit 可以在独立 workspace 或 branch 中执行。
- 每个 unit 产出 patch/checkpoint artifacts。
- 状态转移绑定到隔离执行上下文。

### V0.6.6 - File and Tool Policy

目标：把 role 约束从 prompt 提升到可执行策略。

计划：

- 按 role 限制可写路径。
- implementation 阶段禁止修改已批准 requirements / acceptance。
- 将 policy decision 记录到 artifacts。

### V0.6.7 - Clean Verification

目标：减少 verifier 结果对本地残留的依赖。

计划：

- 支持 clean checkout 或 clean environment verification。
- 区分本地预检和权威验证证据。
- 捕获可复现的 verifier context。

## 长期方向

### V0.7 - 恢复能力与可观测性

- checkpoint 和 time-travel。
- 跨 run、unit、AO、AC、Journey、evidence、log 的统一 trace id。
- 标准化截图、trace、API response、coverage、DB check 等 evidence 类型。
- failure taxonomy：需求缺失、测试缺口、环境问题、实现 bug、runner 失败、权限阻断。
- 基于 failure taxonomy 自动补上下文。

### V0.8 - 结构化契约与 CI 权威验收

- `requirements.json`、`acceptance.json`、`tasks.json`、`journeys.json` 成为一等契约。
- Markdown 变成 review view，而不是唯一结构化事实源。
- CI 成为最终验证权威源。
- 增加 before-tool-use、before-file-write、before-mark-done、after-commit 等生命周期 hooks。

## 当前非目标

- Waygate 不是托管 SaaS。
- Waygate 不替代人类 code review。
- Waygate 不能在缺少有效测试和验收标准时保证正确性。
- Waygate 目前还不是完整 sandbox 或全 role policy engine。
