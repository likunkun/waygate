# Waygate — 版本路线图（确认版）

## V0.1 — Test Strategist 接入（已完成）

- Test Strategist 配置、runner/env 隔离
- prompt/schema/artifacts 支持
- Controller 编排、Critical 自动返工、fallback 阻断
- Review Package 合并与现有 Unit Plan gate 校验
- 全链路回归验收，全量测试 144 passed

---

## V0.2 — 全面重构

架构分层，为后续版本留好扩展位置。

```
workflow_controller/
├── state_machine/        # 状态转移规则、allowed action 计算
├── gates/                # generators / parsers / validators 三层
├── runners/              # base 接口 + tmux_claude + codex + opencode（占位）
├── prompts/              # requirements / unit_plan / builder / bug_fix（占位）
├── steps/                # requirements / unit_plan / builder / bug_fix（占位）
├── controller.py         # 纯编排
├── cli.py                # CLI 入口
└── tests/                # 按模块拆分
```

---

## V0.3 — Acceptance-Driven Loop + 需求质量 + 证据标准化 + CodeSimplifier

**V0.3.1 Acceptance Obligation Ledger（已完成）：**

人工反馈、Plannotator annotations、Requirements/Unit Plan 返工和 Final Acceptance rejection 会进入结构化 AO Ledger，避免多条人工问题被压缩成单个 closure unit。

```
Human Feedback → AO Ledger → Requirements AC → Unit Plan Test Case → Verifier Evidence → Final Acceptance
```

- AO 使用稳定 id（如 `AO-001`）存入 controller state 的 `acceptanceObligations`
- AO artifacts 写入 `artifacts/acceptance-obligations/acceptance-obligations.json` 和 `.md`
- Requirements / Unit Plan prompt 注入 AO Ledger
- Unit Plan approval 阻断缺失 active must AO 覆盖的计划
- 全量测试：`240 passed in 32.12s`

**V0.3.2 CodeSimplifier 集成（已完成）：**

Builder 完成后、Reviewer/Verifier 启动前，controller 默认调用 CodeSimplifier 对本次改动文件做简化审查：

```
Builder → CodeSimplifier/Refiner → Reviewer → Verifier → Final Acceptance
```

- CodeSimplifier 以 runner 形式执行，输入为 `changed-files.txt`，输出写入 `artifacts/<unit-id>/simplifier-result.json`
- `ok/skipped` 进入 Reviewer；`changes_requested` 自动触发 Builder 返工；`failed` 停留在 Refiner retry/block，不进入 Reviewer
- 默认开启；可通过 `--no-code-simplifier` 关闭，并可用 `--code-simplifier-command` / `--code-simplifier-env` 覆盖 runner
- 全量测试：`252 passed in 30.76s`

**V0.3.3 Requirements Quality Gate（已完成）：**

- Requirements approval 前预检：每条 active `must` AO 必须映射到 AC，或显式 `deferred` / `rejected` / `out_of_scope` 且写明原因
- 每条 AC 必须声明 verification layer：`unit` / `integration` / `e2e` / `manual`
- Requirements draft prompt 和本地 template 新增 `Requirements Traceability Matrix`
- 无效 requirements 不会写入 approved，也不会进入 Unit Plan；阻断原因进入 requirements revision prompt
- 全量测试：`259 passed in 30.51s`

**V0.3.4 Product Design / Technical Architecture Traceability（已完成）：**

- Requirements approval 会在存在 `Design/Architecture Traceability Matrix` 时，要求每条 AC 同时映射 Product Design Ref 和 Technical Architecture Ref
- Requirements draft prompt 和本地 template 新增设计/架构可追溯矩阵
- Unit Plan approval 要求 test case 保留对应 AC 的 `product_design_refs` 和 `technical_architecture_refs`
- Unit Plan prompt 和本地 template 的 Test Case Matrix 增加产品设计引用和技术架构引用列
- 兼容旧 requirements：没有设计/架构可追溯矩阵的历史 gate 不会被 V0.3.4 新规则阻断
- 全量测试：`264 passed in 31.38s`

**V0.3.5 Verifier Evidence Schema（已完成）：**

- Verifier evidence schema 记录 AO/AC/Test Case/Evidence 对账矩阵
- Verifier artifact 从纯命令结果扩展为结构化 evidence rows
- 证据 schema 需要兼容手工证据、自动化测试命令和 golden path 结果
- Controller 在 Verifier 通过后校验 `evidence_schema_version` 和 `evidence_rows`，schema 无效时按验证失败返工，不进入 Unit Complete
- 定向测试：`169 passed in 17.97s`
- 全量测试：`267 passed in 29.94s`

**V0.3.6 Final Acceptance Evidence Matrix（已完成）：**

- 引入 evidence schema：最终验收 gate 按结构化模板渲染（AO id、AC 编号、验证层、命令、预期结果），替代纯文本 checklist
- 最终验收 gate 基于 Verifier evidence schema 渲染可审阅矩阵
- 拒绝时保留 AO/AC/Test Case/Evidence 定位，便于路由到 requirements、unit_plan、defect_fix 或 implementation
- patch list 返工路径会附带 evidence matrix context，避免 Builder/defect-fix unit 丢失验收定位
- 定向测试：`147 passed in 14.76s`
- 全量测试：`268 passed in 30.15s`

---

## V0.4+ Priority Backlog

| 优先级 | 版本 | 主题 | 要做什么 | 为什么先后这样排 |
|---|---|---|---|---|
| P0 | V0.4.0 | 项目初始化规约 | `init` 自动生成 `AGENTS.md`、可选 `CLAUDE.md`、标准文档目录结构、事实源表、Agent 操作规则 | 这是所有后续 agent 正确工作的入口，先补 |
| P0 | V0.4.1 | 需求协商循环 | Requirements Drafter 可在目标 agent pane 中集中澄清关键缺口；Requirements gate 支持多轮批注、返工、确认并记录差异 | 对应 ROADMAP V0.4，解决需求被重解释 |
| P0 | V0.4.2 | `change_requests.jsonl` | 所有需求变更必须生成 change request，记录来源、原因、影响 AO/AC/Test Case/Journey | 防止偷偷改需求或弱化验收 |
| P0 | V0.4.3 | 独立 Bug Fix Gate | `defect_fix` 从 Unit Plan revision 升级为：Bug gate → Root cause → Bug Fix Agent → 回归验证 | 对应 ROADMAP V0.4，补齐缺陷修复控制流 |
| P0 | V0.4.4 | Journey Acceptance Layer | 新增 `journeys.json`、Journey gate、Journey evidence、Final Acceptance Journey Matrix | 先解决“局部 unit 都通过，但整体流程不通”的任务粒度问题 |
| P0 | V0.4.5 | Final Scope Audit | 最终验收前生成覆盖/未覆盖/超范围改动/未解释 diff 审计，并纳入 Journey 覆盖 | Journey 成为审计对象后再做最终范围审计 |
| P1 | V0.4.5a | Requirements Dialogue Brief | Requirements Draft 前生成 requirements dialogue brief 上下文压缩，帮助 drafter 保留用户原始语境 | 作为后续需求体验增强记录，不插队、不影响 V0.4.5 Final Scope Audit |
| P1 | V0.4.6 | Strict Test Presence + Requirements Test Strategist | 把 optional Test Strategist 接到 requirements 阶段；新增“非 manual AC 必须有可执行 test case，没有 test case 不能 pass”的 gate | 先补用户最担心的“根本没有测试”，再让测试策略前移 |
| P1 | V0.5.1 | tmux agent detection + auto Claude pane | `--tmux-target` 自动识别 Codex/Claude pane；无 target 且在 tmux 内自动右侧创建 Claude pane | 先让当前 tmux agent 调度可用，执行隔离规划后移 |
| P1 | V0.5.2 | 审批摘要优先 + Unit Plan 进度输出 | Requirements/Unit Plan 审批 Markdown 顶部先展示摘要，controller 可预检问题自动打回，compact 输出恢复 Unit Plan 草案/预检/打回/等待状态 | 降低人工 gate 审阅成本，并避免按 approve 后才暴露 controller 可判定错误 |
| P1 | V0.5.3 | Waygate 安装化与现场降噪 | 对外品牌改为 Waygate，提供 `waygate` deb 包和命令，去重 compact 重复状态卡，清理测试产物泄漏 | 在继续 V0.5.6 执行隔离前，先让工具可安装、可识别、现场输出更安静 |
| P1 | V0.5.6 | per-role runner 完整化 | Builder、Refiner、Reviewer、Verifier、Bug Fix Agent 都支持独立 runner/command/env/timeout | 对应 ROADMAP V0.5，为执行隔离打基础 |
| P1 | V0.5.7 | opencode runner | 实现 opencode runner，统一 runner metadata 与 artifacts | 对应 ROADMAP V0.5 的 Agent 灵活性目标 |
| P1 | V0.5.8 | task workspace/branch 隔离 | 每个 unit 独立 workspace 或 branch，产出 patch/checkpoint | 降低越界修改和历史状态污染 |
| P1 | V0.5.9 | file/tool policy | 不同 role 限制可写文件、可用工具；Implementer 不允许改 approved requirements/acceptance/journeys | 把流程约束从 prompt 提升为 harness 规则 |
| P1 | V0.5.10 | clean verification | Verifier 支持 clean checkout / clean env 验证 | 避免本地残留导致假通过 |
| P2 | V0.6.1 | checkpoint/time-travel | 每个状态转移保存 checkpoint，支持恢复、回放、对比 | 强化长任务恢复能力 |
| P2 | V0.6.2 | unified trace | 统一 run_id、unit_id、AO、AC、Journey、evidence、logs 查询 | 提升可审计性 |
| P2 | V0.6.3 | evidence 类型扩展 | 标准化截图、Playwright trace、API response、coverage、DB query result | 让不同项目类型都有可靠证据 |
| P2 | V0.6.4 | failure taxonomy | 失败分类：需求缺失、测试缺失、环境缺失、实现错误、runner 异常、权限阻断 | 后续才能做智能恢复 |
| P2 | V0.6.5 | 自动上下文补全 | 根据 failure taxonomy 注入缺失上下文，而不是盲目 retry | 提升返工质量 |
| P3 | V0.7.0 | 结构化契约一等化 | `requirements.json`、`acceptance.json`、`tasks.json`、`journeys.json` 成为事实源，Markdown 只做审阅视图 | 从 Markdown gate 过渡到真正数据模型 |
| P3 | V0.7.1 | CI 集成 | Verifier 最终权威源接 CI，本地验证作为预检 | 让验收证据更不可伪造 |
| P3 | V0.7.2 | lifecycle hooks | `BeforeToolUse`、`BeforeFileWrite`、`BeforeMarkDone`、`AfterCommit` 等生命周期拦截 | 完成真正的工程控制系统 |

---

## V0.4 — 初始化规约 + 需求协商 + Journey Acceptance + Bug Fix

V0.4 的目标是补齐控制平面的上游入口与跨任务验收：让 agent 进入项目时先读正确文档，让需求变更可追踪，让“小任务通过但整体流程不通”的问题被 Journey Acceptance 拦住，并把最终验收缺陷从 Unit Plan 重路径升级为独立 Bug Fix 环节。

**V0.4.0 Project Agent Operating Guide（已完成）：**

- `init` 自动生成中文 `AGENTS.md` 作为 canonical agent 操作规约
- 可选生成中文 `CLAUDE.md` shim，但 `CLAUDE.md` 只引用 `AGENTS.md`，避免双份规则漂移
- 规范项目文档目录结构与事实源表：`ROADMAP.md`、`task_plan.md`、`progress.md`、`findings.md`、`.plan-ralph/session.json`、`.plan-ralph/events.jsonl`、`approvals/`、`artifacts/`
- 明确 agent 规则：先读版本规划和 controller state，一次只做一个 unit，不能绕过 Verifier/Final Acceptance，不能把自然语言总结当完成
- 加入中文工程行为准则：先澄清、简洁实现、精准修改、避免无关重构、以证据验证 bugfix
- 已存在 `AGENTS.md` / `CLAUDE.md` 时不覆盖；生成 merge proposal 或 `.generated` 草稿
- 默认生成标准 docs 目录：`docs/product`、`docs/architecture`、`docs/workflow`、`docs/operations`
- 新增 `--claude-md` 和 `--no-agent-guides` CLI 配置，`init` / `start` 初始化路径均可用
- 生成结果写入 state 的 `agentGuideArtifacts`，便于审计
- 定向测试：`94 passed in 5.08s`
- 全量测试：`272 passed in 30.72s`

**V0.4.1 Requirements Negotiation Loop（已完成）：**

- Requirements Drafter 在生成 gate 前可在目标 tmux agent pane 中集中提出关键澄清问题，拿到用户回答后继续
- 可用保守假设推进时不打断用户，必须把关键假设和待确认风险写入 Requirements Gate
- Requirements 草案生成后先跑 controller 预检；可自动判定的 gate invalid 会自动打回 drafter，不进入人工审核
- Requirements gate 支持多轮批注返工，满意后正式 approve
- 每轮 requirements 返工保留差异摘要、反馈来源和处理结果
- Requirements revision prompt 必须携带上一轮 controller validation error 与 Plannotator annotations
- 避免 implementation 阶段重新解释需求范围
- Requirements revision artifact 记录 diff summary、feedback source 和处理状态

**V0.4.2 Change Request Ledger（已完成）：**

- 新增 `change_requests.jsonl`
- 需求变更必须记录来源、原因、影响的 AO/AC/Test Case/Journey、处理状态和审批人
- 实现阶段不得直接弱化或删除已批准 AC；必须创建 change request 后回到 requirements/unit_plan gate
- Requirements approval 和 Final Acceptance requirements 路由会写入 change request，并保留 approver

**V0.4.3 Independent Bug Fix Gate（已完成）：**

现有 `defect_fix -> Unit Plan revision` 升级为独立 Bug Fix 环节：


```
defect_fix 路由触发
  → bug-fix gate（人工填写：预期行为 vs 实际行为）
  → Bug Fix Agent（定位根因 + 修复 + 补回归测试）
  → 验证（跑已有 test cases）
  → 通过 → 回最终验收
  → 失败 → 返工
  → 根因是架构问题 → 升级到 unit_plan 路由
```

- Bug Fix Agent 只能修复已批准需求下的缺陷，不能扩展需求
- 必须补回归测试或人工证据
- Bug fix evidence 回写到 Final Acceptance gate
- 根因分类为架构或计划问题时会升级回 Unit Plan 路由

**V0.4.4 Journey Acceptance Layer（已完成）：**

- 新增 `journeys.json` 或等价 artifacts，表达跨 unit 的用户旅程验收
- Journey schema 包含 `journey_id`、`title`、`steps`、`linked_requirements`、`linked_acceptance_criteria`、`linked_units`、`verification_layer`、`verification_command`、`status`
- Requirements gate：有跨模块用户流程时必须生成 Journey
- Unit Plan gate：每个 Journey 必须映射到至少一个 `workflow_validation_level=closure` 或 E2E test case
- Verifier：Journey 对应命令必须真实通过，并生成 Journey evidence row
- Final Acceptance：展示 Journey Matrix，防止“局部 unit 都通过，但整体流程不通”
- 已保留设计文档：`docs/superpowers/specs/2026-05-04-v0.4.4-journey-acceptance-design.md`

**V0.4.5 Final Scope Audit（已完成）：**

- Final Acceptance 前生成 scope audit artifact
- 输出已覆盖需求、未覆盖需求、超范围实现、被弱化验收项、未解释 diff
- 任一 active must AO / AC / Journey 没有 evidence 时不能进入最终完成
- Final Acceptance gate 渲染 scope audit 摘要，并在存在 blocker 时阻断 approval

**V0.4.5a Requirements Dialogue Brief（已完成）：**

- Requirements Draft 前生成一份 requirements dialogue brief，用于压缩 controller state、原始目标和上下文文件
- brief 聚合用户原始目标、上下文约束、明确反复强调的非目标、AO ledger 和 revision feedback；它不是提问机制
- Requirements drafter 后续可消费该 brief，减少需求重解释；V0.4.5a 不改变 Final Scope Audit 的版本顺序和验收范围
- brief 写入 `artifacts/requirements-dialogue-brief/`，requirements prompt 会注入其摘要和 hash

**V0.4.6 Strict Test Presence + Requirements-stage Test Strategist（下一步）：**

- 将 V0.3.x 剩余 optional 项纳入正式版本：Codex Test Strategist 接入 requirements 阶段
- 在 Requirements approval 前检查 AC 是否具备可验证性、测试层级是否合理、是否需要 Journey / E2E coverage
- Unit Plan approval 阶段要求每条非 `manual` AC 至少映射一个可执行 test case，且 test case 必须包含 command、fixture/setup 和具体 expected assertion
- Verifier / Final Acceptance 阶段要求每条非 `manual` AC 都有对应 evidence row；只有命令级 summary、没有 Test Case ID 的证据不能算完整通过
- 输出 requirements test strategy artifact，供 Unit Plan drafter 继续消费
- 已预先完成 Unit Plan Test Strategist prompt 强化：fake runner / mock-only / stubbed API-only evidence 不能作为目标项目 E2E 证据

**最终验收路由语义（更新后）：**

| 路由 | 行为 |
|------|------|
| `requirements` | 退回需求重写 |
| `unit_plan` | 退回 Unit Plan 修订 |
| `defect_fix` | 进入 Bug Fix 环节（问题描述 → 诊断修复） |
| `implementation` | 退回 Builder 返工（修改清单或完整 gate） |
| `blocked` | 挂起等待解除 |

---

## V0.5 — Agent 灵活性 + 执行隔离 + 权限策略

V0.5 的目标是强化 Execution Plane：把不同 role 的执行环境、runner、权限和验证环境隔离开。

**V0.5.1 tmux agent detection + auto Claude pane：**

- 指定 `--tmux-target` 时检测目标 pane 是 Codex 还是 Claude，并分别使用 `tmux-codex` / `tmux-claude`
- 显式 `--runner` 与检测结果冲突时阻断
- 未指定 `--tmux-target` 且 controller 运行在 tmux 内时，右半屏自动创建 Claude pane，并写入 `tmuxTarget` / `agentRunner=tmux-claude`
- 未指定 `--tmux-target` 且不在 tmux 内时，要求用户传入 tmux target 或显式 `--runner subprocess`

**V0.5.2 审批摘要优先 + Unit Plan 进度输出（已完成）：**

- `approvals/requirements-and-acceptance.md` 和 `approvals/unit-plan.md` 保持单文件结构，顶部新增 `## 审批摘要`
- 详细 Requirements 矩阵、Journey 映射、Unit Plan 测试矩阵和 `## Controller State Patch` 留在同一 Markdown 的附录区
- `## Human Confirmation` 仍只由 controller 自动追加，agent 生成正文不会成为确认事实源
- Plannotator 改为打开同一个 approval Markdown，默认先看到顶部摘要；review summary 记录 review/approval/full path
- Unit Plan 进入人工确认前会执行 controller 预检；可判定错误自动写入 state/artifact 并打回 drafter，不显示人工审批菜单
- compact drive 输出覆盖 Requirements/Unit Plan 生成、预检、自动打回、等待确认、Builder/Verifier 等长动作状态
- 全量测试：`332 passed in 43.67s`

**V0.5.3 Waygate 安装化与现场降噪：**

- 对外项目名、安装包名和命令名统一为 Waygate / `waygate`
- 内部 Python package 暂保留 `workflow_controller`，避免大规模 import 重命名
- 新增 Debian 包构建脚本，输出 `dist/waygate_0.5.3_all.deb`
- 安装后提供 `/usr/bin/waygate`，调用内部 `workflow_controller.cli`
- compact drive 输出按最终渲染状态卡去重，避免 Plannotator approve 后重复打印相同 `检查 Unit Plan 确认`
- 测试中相对 artifact 目录必须隔离在 `tmp_path`，避免全量测试污染 repo root
- 全量测试：`339 passed in 40.64s`

**V0.5.6 per-role runner 完整化：**

- Builder、Refiner、Reviewer、Verifier、Bug Fix Agent、Requirements/Test Strategist 都支持独立 runner/command/env/timeout
- runner metadata 统一记录 role、backend、command、env keys、run id、artifact path

**V0.5.7 opencode runner：**

- 实现 opencode runner
- 与 tmux_claude/subprocess 使用同一 `RunnerRequest` / `RunnerResult` 语义
- 保留 stdout/stderr、done payload、run events 和 redaction

**V0.5.8 Task Workspace / Branch Isolation：**

- 每个 unit 可选独立 workspace 或 branch
- 每个 agent run 生成 patch/checkpoint
- Controller 只合并通过 Refiner/Reviewer/Verifier 的 patch

**V0.5.9 File / Tool Policy：**

- 不同 role 限制可读写文件和可调用工具
- Implementer/Builder 不能修改 approved requirements、acceptance、journeys 或 verifier-only artifacts
- Verifier 默认不能修改生产代码，只能写 evidence/artifacts

**V0.5.10 Clean Verification：**

- Verifier 支持 clean checkout / clean env 验证
- 验证结果绑定 commit hash、unit id、run id、command、exit code、artifact refs
- 本地残留状态不能作为最终通过依据

---

## V0.6 — 恢复能力 + 可观测性 + 证据扩展

V0.6 的目标是把长任务运行变成可恢复、可回放、可审计。

**V0.6.1 Checkpoint / Time Travel：**

- 每个状态转移保存 checkpoint
- 支持从最后成功 checkpoint 恢复
- 支持对比两个 checkpoint 的 state/artifact/diff

**V0.6.2 Unified Trace / Run Viewer：**

- 统一 run_id、unit_id、AO、AC、Journey、Evidence、logs 查询
- 支持生成人类可读报告和机器可读 JSON

**V0.6.3 Evidence Type Expansion：**

- 标准化 Playwright trace、截图、视频、API response snapshot、coverage report、DB query result、build artifact
- Final Acceptance Evidence Matrix 和 Journey Matrix 可展示这些证据类型

**V0.6.4 Failure Taxonomy：**

- 失败分类：需求缺失、测试缺失、环境缺失、实现错误、runner 异常、权限阻断、证据 schema 错误
- 每类失败有默认路由：补上下文、返工、阻断、需求协商或人工升级

**V0.6.5 Automatic Context Repair：**

- 根据 failure taxonomy 注入缺失上下文
- 避免重复失败后盲目 retry
- 与现有 repeated-failure guard 结合

---

## V0.7 — 结构化契约 + CI 权威验收 + 生命周期 Hooks

V0.7 的目标是从 Markdown gate 为主，升级到结构化事实源为主；Markdown 只做审阅视图。

**V0.7.0 Structured Contract Files：**

- `requirements.json`
- `acceptance.json`
- `tasks.json`
- `journeys.json`
- `traceability.json`
- Markdown gate 从结构化事实源渲染，不再作为唯一事实源

**V0.7.1 CI Integration：**

- Verifier 最终权威源接入 CI
- 本地验证作为预检
- CI artifact 回写 evidence rows / journey evidence rows

**V0.7.2 Lifecycle Hooks：**

- `BeforeTaskStart`
- `BeforeToolUse`
- `AfterToolUse`
- `BeforeFileWrite`
- `AfterFileWrite`
- `BeforeTestRun`
- `AfterTestRun`
- `BeforeMarkDone`
- `AfterCommit`
- `OnFailure`
- `OnResume`
