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
- Requirements gate 在存在 review bundle 时让 Plannotator 打开该 bundle；`approvals/requirements-and-acceptance.md` 仍作为 approval gate 和确认状态事实源。
- 将本地原型资产路径规范化到 controller artifact tree，避免 Plannotator 依赖 agent 随手写出的任意文件系统路径。
- Requirements 预检增加原型文件缺失、可点击原型访问方式不完整、页面状态缺失、点击路径缺失、AC 映射缺失、未知 AC 引用和敏感 URL query 的阻断。
- 保持审批语义不变：Plannotator Approve 仍不能绕过 Requirements quality gate。

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
