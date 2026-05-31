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
- V0.6.1 External Spec Intake、V0.6.2 Staged Requirements Package，以及 V0.6.3 Strict Test Presence / Per-Role Runner Configuration 仍是后续 planned scope，不属于 V0.6.0e 当前交付。

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
- 推荐 skill warning 与当时 README 推荐基线对齐，覆盖 persistent planning、startup、brainstorming、writing plans、TDD、debugging、test strategy、refiner、verification、code review、plan execution、webapp/browser verification 和 UI-heavy skill coverage。V0.6.0k 后 `ui-ux-pro-max` 成为 UI/Web/prototype 必需 skill。
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

### V0.6.0k - UI/UX Skill Policy

目标：让 UI、Web、可点击原型、prototype evidence 和生产 UI 一致性工作使用正确的专业 skill。

已交付：

- Requirements、Unit Plan、Builder 和 UI Design Brief prompt contract 都明确 UI/Web/prototype 工作必须使用 `ui-ux-pro-max`。
- 明确 `frontend-design` 只能辅助全新视觉探索或局部润色，不能替代 `ui-ux-pro-max` 做既有产品 UI/原型一致性工作。
- 原型设计前必须盘点真实 UI：route、DOM/组件、既有页面结构、截图、历史设计或参考环境。
- `waygate doctor` 的 `skill_recommendations.ui_ux_design` 改为要求 `ui-ux-pro-max`；只安装 `frontend-design` 时输出 warning 和 manual action；两者都安装时优先展示 `ui-ux-pro-max`。
- 新增 `docs/workflow/ui-ux-skill-policy.md` 并随 Debian 文档打包。

### V0.6.0m - Golden Path E2E 前置校验

目标：在 Unit Plan approval 阶段提前发现非真实 golden path 证据，而不是等到 Final Acceptance 才暴露。

已交付：

- 阻断不满足真实 E2E 条件的 `golden_path: true` Unit Plan test case：必须是 `layer=e2e`，使用 `local_real` 或 `production_readonly`，声明真实入口，包含 fixture/setup，命令必须出现在 `verification_commands`，expected 必须是强断言，并且不得 mock/stub 核心业务 API。
- Requirements 中声明 E2E 的 AC 和 active E2E Journey 必须映射到 `layer=e2e` Unit Plan test case。
- 保持 API-only 和 service-only golden path 合法：可以使用 pytest/API/service E2E 调真实入口；非 UI 系统不要求浏览器字段。
- Unit Plan Test Case Matrix 显式展示 Golden Path，并与 Layer、Environment、Real Entry、Core API Mock 一起供人工审核。
- Final Acceptance 继续作为最后防线，阻断非 E2E golden evidence、缺真实入口、mock 核心 API、非真实环境或 runtime errors。

### V0.6.1 - External Spec Intake

目标：在 Waygate Markdown intake 稳定后，再增加外部 spec 生态的显式导入路径，并补齐 controller 验收要求的 gate 顺序、标注、提示词合同和灵活验收证据能力。

状态：Final Acceptance 已于 2026-05-23 批准。

已交付：

- 设计 OpenSpec 和 Spec Kit 的导入契约。
- 为受支持外部格式增加 parser、validation 和 conversion artifacts。
- 对已识别但未启用的格式继续给出清晰 unsupported/deferred 错误。
- 强化 gate 顺序：每个 gate 的人工审批必须是当前阶段最后一步；controller preflight、schema validation、evidence checks 和 annotation pass 都必须在人工审核文件呈现前完成。
- 为 `requirements_annotation`、`unit_plan_annotation` 和 `final_acceptance_verification_assist` 增加按 role 可配置的 annotation / verification-assist 配置。
- 通过 command、args、env key allowlist、timeout、artifact path、prompt template 和 failure policy 支持 `claude-code`、`opencode`、`codex` 三类 backend family。
- 定义共享 non-approval 提示词合同，以及 Requirements、Unit Plan、Final Acceptance 三个阶段的风险标注 prompt template。
- 允许 verification JSON 同时包含严格命令项、仍执行命令但补充 Agent 判断的 `descriptive_command` 行，以及显式声明 `verification_assist` 且不执行命令的 `agent_assisted_case` 行；辅助验证行必须记录结构化 evidence、`human_review_required` 和 assist artifact 路径。
- 保持人工审批语义不变：标注 Agent 和 agent-assisted verification 只能帮助人聚焦风险，不能批准、跳过或绕过 controller gate。
- 将长期流程规则沉淀到 `docs/workflow/external-spec-intake-and-annotation-policy.md`，将模块边界沉淀到 `docs/architecture/external-spec-intake-and-annotation-architecture.md`。

### V0.6.2 - Staged Requirements Package

目标：降低 Requirements 阶段一次性产物过载，把范围、产品设计、技术架构和测试策略拆成聚焦 checkpoint，同时保留一个最终人工 Requirements approval gate。

状态：Final Acceptance 已于 2026-05-25 批准；已在 package `0.6.2` 实施。

已交付：

- 将单个过载 Requirements draft 替换为分段 checkpoint：Requirements Scope、Product Design Brief、Technical Architecture Brief 和 Requirements Test Strategy Brief。
- 组装一个最终 `requirements-and-acceptance.md` 审批包，嵌入所有 checkpoint artifact 并记录 hash。
- 将详细 `## 4.9 目标项目基础设施信息` intake 从 Requirements 后移到 Unit Plan 的 Infrastructure / Execution Context Matrix；Requirements 只保留最小上下文门槛。
- 保留 V0.6.1 gate ordering：controller preflight 和 annotation 在最终人工 Requirements gate 前运行；已批准的 legacy gate 不强制迁移。
- 确保 Unit Plan 显式消费 staged artifact path/hash，让 scope、AC、Journey、产品设计、架构、prototype、E2E 和风险义务持续向下游传递。
- 将长期流程规则沉淀到 `docs/workflow/staged-requirements-package-policy.md`，将模块边界沉淀到 `docs/architecture/staged-requirements-package-architecture.md`。

### V0.6.2a - Staged Requirements 目标产品视角修复

目标：让 staged Requirements artifacts 始终围绕目标产品或目标系统，而不是 Waygate/controller 内部流程。

状态：patch release 已在 package `0.6.2a` 实施。

已交付：

- 新增 `requirementsSurfaceClassification`，包含 `product_ui`、`web_system`、`prototype_required`、`visible_surfaces` 和脱敏 `evidence_snippets`。
- 从 `--spec`、目标上下文、当前 unit metadata 和人工反馈识别目标产品表面；默认 `currentUnitNeedsUiDesign=false` / `currentUnitIsWebSystem=false` 只能作为 ignored context，不能证明不需要 UI。
- 更新 staged Scope、Product Design、Architecture 和 Test Strategy prompt 合同：Product Design 输出目标产品 UX / 原型 / 审阅表面，Architecture 输出目标系统交互、数据、API 和运行边界，Test Strategy 保持策略层，不提前写 Unit Plan 级 exact cases / commands。
- 保留 Requirements 硬预检：UI/Web/prototype 目标仍要求合法 prototype manifest，unknown classification 必须解释依据，backend/API/CLI-only 目标必须给出明确 no-UI 依据。
- 非 Waygate 目标项目中，Product Design 或 Architecture 如果主要描述 Waygate/controller staged package 操作而不是目标产品/系统，会被判 invalid。
- “产品原型/UI 怎么看”反馈路由到 Product Design，“架构交互/API/数据流缺失”反馈路由到 Architecture，测试策略反馈路由到 Test Strategy，不再所有 staged revision 都回到 Scope。

### V0.6.2b - Product Design 后常驻原型预览

目标：Product Design 成功后立即保持 Requirements-stage 原型预览可访问，而不是只在 Plannotator review 命令期间临时启动。

状态：patch release 已在 package `0.6.2b` 实施。

已交付：

- Product Design checkpoint 校验通过后立即生成 `plannotator-review.html` 和 `prototype-review-manifest.json`。
- 为显式 `status=blocked` workflow 增加可选 Blocked Assist 对话层，写入 summary artifact，要求人工确认 `human_reason`，并由 controller 菜单选择恢复路线。
- final Requirements approval gate 尚未装配时，使用 Scope checkpoint 作为 requirements reference。
- 启动一个随 controller 进程常驻的 prototype preview server，Architecture、Test Strategy、final assembly、Requirements 人工评审和 Plannotator 辅助审阅期间复用同一 URL。
- final Requirements assembly 后重新生成 review bundle，让 manifest 记录真实 approval gate path，同时保留当前 preview port。
- 预览端口从 `WAYGATE_PREVIEW_PORT` 或默认 `20001` 起步，被占用时自动递增。
- Plannotator Close 后保持预览服务可访问，并在 controller 进程退出时关闭。

### V0.6.2c - 中文 Checkpoint 命名与定点 Revise

目标：让 staged Requirements checkpoint 的用户可见名称以中文为主，并允许 operator 带原因回撤到指定 checkpoint。

状态：patch release 已在 package `0.6.2c` 实施。

已交付：

- final gate 附录、hash table、prompt、compact output 和 guidance 使用中文主名：需求范围检查点、产品设计简报、技术架构简报、需求测试策略简报。
- 保留英文内部 state key、artifact key 和状态机 step，避免历史 session 迁移风险。
- 增加 `waygate revise --gate requirements --checkpoint scope|product-design|architecture|test-strategy --reason ...`，并支持 `需求范围`、`产品设计`、`技术架构`、`测试策略` 等中文别名。
- `--checkpoint` 只适用于 Requirements revision；`--gate unit-plan` 保持现有 Unit Plan revision 行为。
- 指定 checkpoint 及其下游 staged artifacts 会标记 stale；Requirements / Unit Plan approval 会被清除，当前 Unit Plan gate 会被删除，并在 audit event 中记录 explicit checkpoint route。

### V0.6.2d - Unit Continuity Gate

目标：在 Unit Plan approval 前拒绝模糊的多单元 handoff，并在下游 Builder 启动前要求上游 producer evidence。

状态：patch release 已在 package `0.6.2d` 实施。

已交付：

- 多单元 Unit Plan 必须包含 `## 单元连贯性摘要` 和 `## Handoff Matrix`，记录上游单元、下游单元、产出 artifact/readiness、消费输入、证据路径和失败路线。
- Controller State Patch unit metadata 新增 `depends_on` 和 `handoff.human_summary`、`produces`、`requires`、`ready_checks`、`evidence_artifacts`。
- Unit Plan validation 新增缺失依赖、缺失 producer handoff、循环依赖、consumer `requires[]` 不匹配、ready checks 未映射到命令/测试用例，以及 `environment ready` 等占位摘要检查。
- Verifier 会为 producer unit 写入 `artifacts/<unit-id>/handoff-evidence.json`；声明的 handoff 证据缺失或 failed 时 producer verification 失败。
- 下游 Builder preflight 在依赖 handoff evidence 缺失、无效、failed 或无法满足下游 `requires[]` 时，以 `blockedContext.category=unit_handoff` 阻塞。
- 长期 workflow 规则沉淀到 `docs/workflow/unit-continuity-handoff-policy.md`。

### V0.6.3 - Strict Test Presence and Per-Role Runner Configuration

目标：非 manual 验收标准不能在缺少可执行测试或明确证据时通过。

计划：

- 原 V0.6.2 Strict Test Presence 范围并入 V0.6.3。
- 将 Test Strategist 前移到 requirements 阶段。
- 要求每条非 manual AC 都有可执行测试用例。
- Unit Plan test case 必须包含 fixture/setup、command 和 expected assertion。
- Verifier 和 Final Acceptance 的 evidence rows 必须能映射回 Test Case ID。
- 将 Final Scope Audit 的 evidence row 缺口前移：Unit Plan 预检必须阻断那些 command 不能被精确执行、不能通过 `command_id` 解析，或只被聚合命令模糊覆盖但无法为每个映射 test case 产出 passed evidence row 的测试用例。
- 为 Builder、Refiner、Reviewer、Verifier 和 Bug Fix Agent 增加 role-specific runner、command、env 和 timeout 配置。
- 标准化 artifacts 中的 role metadata。
- 避免 secrets value 出现在 logs 和 artifacts 中。

测试用例契约强化路线：

- TC1 - Test Case Contract v1：定义稳定的 Unit Plan `test_cases[]` 契约，包含 `acceptance_criteria[]`、`covers_obligations[]`、`covers_journeys[]`、`layer`、`path_type`、`golden_path`、`setup[]`、`entrypoint`、可选 `cleanup[]`、`command_id`、`manual_evidence` 和 `assertions[]`。
- TC2 - 事实源收敛：以 Controller State Patch 中的 `test_cases[]` 作为权威事实源；Markdown Test Case Matrix 只从结构化数据渲染，不再让 prose 和 JSON 各自成为事实源。
- TC3 - 旧格式兼容与迁移：继续读取 `acceptance_criterion`、`fixture`、`command`、`evidence`、`expected`、`journey_refs`、`journeyRefs` 等旧字段，但归一化到 v1 契约，并输出迁移 warning。
- TC4 - 严格 Unit Plan 预检：阻断缺失或未知 AC/AO/Journey 引用、无法解析的 `command_id`、static-only 冒充行为覆盖、弱断言、E2E 缺少 `user_steps`、缺少 setup/entrypoint、manual evidence 冒充自动化通过，以及无法在人工 Unit Plan approval 前声明精确 test-case 覆盖关系的聚合命令。
- TC5 - 人工确认前 Test Case Review Agent：在 Unit Plan 人工确认前运行不具备批准权的审阅 agent，标注浅断言、假 fixture、过宽命令、只覆盖 happy path 的 E2E、AO 只挂名覆盖，以及不能证明所映射 AC 的测试用例。
- TC6 - Verifier evidence 对齐：每个计划中的 test case 都产出 evidence row，包含 command ID 和结构化 assertions；未执行的计划 test case 明确标记为 `missing`；manual evidence 与自动化 `passed` 结果分开。不再依赖命令字符串模糊包含匹配；通过 `command_id`、计划 test case id 和结构化 assertions 绑定 evidence row。聚合 pytest 命令必须展开为每个 test case 的 evidence row，否则在 Unit Plan 人工批准前阻断。
- TC7 - Final Acceptance 矩阵升级：展示从 Requirement / Use Case / Journey / AC / AO 到 Test Case 和 Evidence 的完整链路，让人工审的是可追踪证据而不是 agent 总结。

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

### V0.6.8 - Cross-Platform and QAgent Runner Support

目标：让 Waygate 可用于 Windows 工作站，并把 QAgent 增加为一等 runner family。

计划：

- 增加 Windows 平台支持规划，在保持现有 Linux/tmux 行为稳定的同时，记录平台特定约束。
- 引入 `psmux` 作为 Windows 下的 pane/session 编排层，承担当前 `tmux` 在 Linux 工作流中的角色。
- 增加 QAgent runner 支持，并复用现有 runner 的 role runner、dispatch、completion signaling、artifact、metadata、timeout、env allowlist 和 secret redaction 契约。
- 扩展 `waygate doctor` 诊断，报告 Windows、`psmux` 和 QAgent 可用性，同时不暴露 secret value。
- 增加 Windows/psmux runner selection、QAgent dispatch、completion、timeout 和 failure mode 回归测试。

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
