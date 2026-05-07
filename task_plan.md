# 任务计划：Waygate 后续开发基线

## 目标
将当前 `workflow_controller` 功能、决策和进度固化到 `~/works/ai-works/worktrees/workflow-controller`，后续开发以该分支工作区为准。

## 当前阶段
已完成基础功能（阶段 1–18）、V0.1 Test Strategist 接入（阶段 19–21，全量测试 144 passed）、V0.3.1 Acceptance Obligation Ledger（阶段 22，全量测试 240 passed）、V0.3.2 CodeSimplifier 集成（阶段 23，全量测试 252 passed）、V0.3.3 Requirements Quality Gate（阶段 24，全量测试 259 passed）、V0.3.4 Product Design / Technical Architecture Traceability（阶段 25）、V0.3.5 Verifier Evidence Schema（阶段 26）、V0.3.6 Final Acceptance Evidence Matrix（阶段 27）、V0.4+ 路线图整合（阶段 28）、V0.4.0 Project Agent Operating Guide（阶段 29）、V0.4.1–V0.4.5a 控制平面收敛、V0.5.2 审批摘要优先 + Unit Plan 进度输出修复（阶段 37–38）、V0.5.3 Waygate 安装化与现场降噪（阶段 40），以及 V1.4.1/V1.5/V1.6 现场 controller gate 与 tmux runner 回归修复。V0.4.6 Strict Test Presence + Requirements-stage Test Strategist 仍是后续待办。

## 各阶段

### 阶段 1：需求与问题收敛
- [x] 确认 Plannotator 启动失败和超时问题
- [x] 确认 Unit Plan 审批后卡在确认阶段的问题
- [x] 确认 50 步上限过低、重复循环缺少保护的问题
- [x] 确认控制器输出信息过繁、需要紧凑中文状态的问题
- [x] 确认后续开发目录迁移到 `~/works/ai-works/`
- **状态：** complete

### 阶段 2：运行流程修复
- [x] Plannotator 启动改为非阻塞等待链接出现
- [x] Plannotator 默认使用 20000 端口，并支持命令行配置
- [x] Unit Plan gate 保留已确认状态，避免审批后反复检查
- [x] gate 内容异常时重新进入人工确认，而不是空转
- [x] 默认最大步数提高到 2000
- [x] 增加重复无进展 50 次保护
- **状态：** complete

### 阶段 3：终端输出体验
- [x] 默认使用紧凑状态面板
- [x] 重复循环时展示 attempt 摘要
- [x] 原始详细输出放到 `--verbose`
- [x] 状态、阶段、动作标签使用中文
- [x] 支持 `--color auto|always|never`
- [x] 保留面向 tmux 另一窗口的实际进展可见性
- **状态：** complete

### 阶段 4：新仓库分支工作区
- [x] 确认 `~/works/ai-works` 是 bare/manage repo
- [x] 创建孤儿分支 `workflow-controller`
- [x] 创建 worktree：`~/works/ai-works/worktrees/workflow-controller`
- [x] 复制当前项目到新工作区的 `workflow_controller/`
- [x] 清理 `__pycache__` 等生成文件
- [x] 添加 `.gitignore`
- [x] 完成初始提交
- **状态：** complete

### 阶段 5：计划与进度持久化
- [x] 在新工作区创建 `task_plan.md`
- [x] 在新工作区创建 `findings.md`
- [x] 在新工作区创建 `progress.md`
- [x] 提交计划与进度文件
- **状态：** complete

### 阶段 6：后续开发
- [x] 根据下一项用户需求继续实现
- [x] 每次阶段完成后更新 `progress.md`
- [x] 重大决策或已知限制更新 `findings.md`
- [x] 计划变化时更新 `task_plan.md`
- [x] 现场 V1.4.1 Requirements AO 污染恢复：修复 `out_of_scope` reason 判定，清理 live state 中 `requirements:revision-1` 伪 AO，并推进到 Unit Plan 确认。
- [x] 现场 V1.6 tmux-codex runner 自动发现修复：显式 `--runner tmux-codex` 无 `--tmux-target` 时发现当前 tmux session 中匹配 workspace 的 Codex pane，跳过当前 controller pane，避免把 `tmux-codex` runner 参数误判为 agent，并重新打包 `dist/waygate_0.5.3_all.deb`。
- [x] GitHub 发布文档整理：英文 README 作为默认入口，中文 `.zh-CN.md` 完整保留，拆分 docs/architecture 与 docs/workflow，补社区文件、LICENSE、GitHub templates 和双语 package docs。
- [x] GitHub 发布脱敏：移除已跟踪 `docs/superpowers/`，忽略后续 superpowers 目录；清理本机 venv 激活命令、用户目录和私有工作区绝对路径；更新 agent guide 模板的标准验证命令。
- **状态：** in_progress

### 阶段 7：控制器可靠性增强
- [x] 重复失败硬阻断：同一 unit/stage/fingerprint 连续失败后 block
- [x] run_id 防串线：DONE_FILE 必须包含并匹配当前 run_id
- [x] verification_env 机制：unit/state 环境变量统一注入 verifier
- [x] Unit Plan approval 预检：拒绝明显缺环境的验证计划
- [x] timeout/idle 诊断：区分 idle、无输出、wrong run、invalid done
- [x] 完整测试通过
- **状态：** complete

### 阶段 8：运行可见性优化
- [x] verifier 在状态变化时输出进度标志
- [x] 不使用固定 30 秒 heartbeat，避免无意义刷屏
- [x] 紧凑输出按当前目标单元显示进度，避免 V2.1 误显示为历史总单元数
- [x] 同步到实际运行目录 `<local-runtime-copy>`
- [x] 测试通过
- **状态：** complete

### 阶段 9：验证失败原因摘要
- [x] controller retry 输出显示失败命令摘要
- [x] controller retry 输出显示 exit code
- [x] controller retry 输出优先提取根因，如缺少 `DATABASE_URL`
- [x] 完整失败详情仍保留在 `verification.json`
- [x] 同步到实际运行目录 `<local-runtime-copy>`
- [x] 测试通过
- **状态：** complete

### 阶段 10：旧 Session 验证环境自动修复
- [x] verifier 前置检查 Playwright/Prisma/DATABASE_URL 环境需求
- [x] 可从 `prisma/dev.db` 推导时自动写入 `verification_env.DATABASE_URL`
- [x] 推导来源写入 `verification_env_inferred`
- [x] 推导失败时直接 `blocked`，不回 Builder 重试
- [x] 同步到实际运行目录 `<local-runtime-copy>`
- [x] 测试通过
- **状态：** complete

### 阶段 11：Plannotator 与人工 Gate 集成
- [x] Plannotator `Approve` 后 controller 自动继续，不再要求用户回终端再选一次
- [x] Plannotator `Close` 后保持 gate pending
- [x] controller 启动 Plannotator 时输出打开网址 `http://localhost:20000`
- [x] 审阅文件改为 Claude 生成的 body artifact，确认文件仍保留在 `approvals/`
- [x] 终端回显审阅文件和确认文件路径，避免审阅对象和落盘对象不一致
- [x] 同步到实际运行目录 `<local-runtime-copy>`
- **状态：** complete

### 阶段 12：Unit Plan Gate 校验与反馈闭环
- [x] Unit Plan approval 前先校验 Controller State Patch、测试策略和验证环境
- [x] 无效 Unit Plan 不写 `Status: approved`
- [x] 无效原因写入 `blockedReason` 并显示在人工确认菜单中
- [x] `r` 或 Plannotator 反馈返工时，将 controller validation error 一并写入 Claude 返工 prompt
- [x] Plannotator 多条反馈终端显示 `共 N 条`，完整反馈写入 Claude prompt
- [x] Plannotator `annotations` 数组保留为结构化信息
- **状态：** complete

### 阶段 13：Unit Plan Rollup 与历史单元兼容
- [x] 允许 `partial` 聚合目标引用已完成历史单元
- [x] 未完成且未声明在 `units` 中的单元仍然阻断
- [x] Unit Plan prompt 更新，说明 completed existing unit 可在 rollup objective 中引用
- [x] 修复 V2.2 只剩 `v2-2-u5-baidu-search` 时被 `u1-u4` 历史单元卡住的问题
- [x] 同步到实际运行目录 `<local-runtime-copy>`
- **状态：** complete

### 阶段 14：Unit Plan 确认后执行推进修复
- [x] 修复 `PLAN_CREATED + scopeApproved=True` 没有下一步动作的问题
- [x] Unit Plan 确认后若 scope 已批准，直接进入 `PLAN_APPROVED`
- [x] `lastVerifiedStep` 在新 Unit Plan 生效后重置为 `PLAN_CREATED`，避免继承上一单元 `VERIFY_UNIT`
- [x] 已落盘的卡住状态可在 `get_status()` 中自动修复为 Builder-ready
- [x] 用当前 V2.2 状态验证 `nextAction=run_builder`
- [x] 同步到实际运行目录 `<local-runtime-copy>`
- **状态：** complete

### 阶段 15：Final Acceptance Defect Fix 流程
- [x] 最终验收拒绝时新增 `defect_fix` 路由
- [x] `defect_fix` 不走 requirements draft，直接进入 Unit Plan revision
- [x] Unit Plan revision prompt 明确要求根据验收缺陷生成 bug-fix units，不改变原需求目标
- [x] Controller State Patch 允许已 covered objective 被 bug-fix unit 重新打开为 `partial`
- [x] Builder prompt 在执行 defect-fix unit 时携带最终验收缺陷清单
- [x] 终端验收路由菜单加入“验收缺陷修复 -> Defect Fix”
- [x] 同步到实际运行目录 `<local-runtime-copy>`
- [x] 全量测试通过
- **状态：** complete

### 阶段 16：Unit Plan 测试用例矩阵与测试策略预检
- [x] Unit Plan drafter prompt 明确要求使用 `test-strategy` skill
- [x] Unit Plan 必须生成 `## Test Case Matrix`
- [x] Controller State Patch unit 支持 `test_cases`
- [x] Unit Plan approval 拒绝只有 tsc/lint/typecheck 等静态检查、没有测试用例或人工证据的计划
- [x] 静态检查可以作为补充，但不能单独证明行为验收
- [x] Builder prompt 要求优先补齐 mapped test cases，defect-fix unit 要补回归测试或人工证据
- [x] 同步到实际运行目录 `<local-runtime-copy>`
- [x] 全量测试通过
- **状态：** complete

### 阶段 17：旧 Final Acceptance Gate 路由迁移修复
- [x] 复现旧 `final-acceptance.md` 缺少 `Defect fix` 行时，终端选择 `1` 后仍无法返工的问题
- [x] `ensure_final_acceptance_gate()` 自动规范化旧 Rejection Routing checklist，补齐 `Defect fix`
- [x] 终端路由写入改为重写 canonical checklist，并校准唯一选中项
- [x] `reject_final_acceptance_gate()` 从 gate 文件读取路由，Plannotator 反馈只作为返工 prompt 内容
- [x] final acceptance 路由写入导致 gate mtime 变新时，仍保留本轮 Plannotator 反馈
- [x] 同步到实际运行目录 `<local-runtime-copy>`
- [x] 全量测试通过
- **状态：** complete

### 阶段 18：非 Ralph 新目标初始化修复
- [x] 复现 `init --target V3.0 --workspace-dir ...` 不带 `--from-ralph` 时落到 demo `usable-system/unit-01` 的问题
- [x] 新增 target acceptance 初始化路径，不依赖 `.plan-ralph/session.json`
- [x] 写入 `requestedOutcome=V3.0`、`currentUnitId=target-v3-0`、`workspacePath`、runner 和 tmux target
- [x] 生成 `target-acceptance-prompt.md`，并进入 `REQUIREMENTS_DRAFT -> run_requirements_drafter`
- [x] 保留无 target 的默认 demo 初始化兼容行为
- [x] 同步到实际运行目录 `<local-runtime-copy>`
- [x] 用真实 V3.0 state-dir 验证 init 输出正确
- [x] 全量测试通过
- **状态：** complete

### 阶段 19：V0.1 Test Strategist 接入与回归验收
- [x] 完成 Unit 1：配置、默认关闭与 role runner/env 隔离
- [x] 完成 Unit 2：Test Strategist prompt、schema 与 artifacts
- [x] 完成 Unit 3：Controller 编排、Critical 自动返工与 fallback 阻断
- [x] 完成 Unit 4：Review Package 合并与现有 Unit Plan gate 校验
- [x] 完成 Unit 5：全链路回归、默认兼容与审计验收
- [x] 新增并通过 `TC-E2E01-enabled-full-unit-plan-strategy-flow`
- [x] 全量 `workflow_controller/tests` 通过：`144 passed in 40.34s`
- [x] 确认未新增浏览器 UI 或页面
- **状态：** complete

### 阶段 22：V0.3.1 Acceptance Obligation Ledger
- [x] Phase 0: Initialize — 复用并更新现有 `task_plan.md`、`findings.md`、`progress.md`
- [x] Phase 1: Brainstorm — 完成 AO Ledger 最小可交付设计，并统一当前实施计划位置为 `<implementation-plan>`
- [x] Phase 1.5: Design System — skipped（非 UI 任务）
- [x] Phase 2: Write Plan — 完成 V0.3.1 实施计划
- [x] Phase 2.5: Plan Review — 用户确认按已讨论 V0.3.1 方向执行
- [x] Phase 3: Execute — 完成 AO helper、feedback 接入、prompt 注入、Unit Plan AO 覆盖 gate 和回归测试
  - Implementation plan: `<implementation-plan>`
  - Scale: single-unit
  - Completion promise: TASK COMPLETE
- [x] Phase 3.5: Simplify — 已完成最小实现整理，未引入额外抽象
- [x] Phase 3.7: Browser Verify — skipped（无用户可见 UI）
- [x] Phase 4: Verify and Finish — `python -m pytest workflow_controller/tests -q` -> `240 passed in 32.12s`
- **目标：** 新增 Acceptance Obligation Ledger，让人工反馈/验收失败问题以稳定 AO id 贯穿 Requirements、Unit Plan、Verifier evidence 和 Final Acceptance，避免多条问题被压缩成单个 closure unit。
- **状态：** complete

### 阶段 23：V0.3.2 CodeSimplifier 集成
- [x] 完成 Unit 1：默认开启配置、CLI opt-out、`roleRunners.refiner` env/command 覆盖和旧 state reconcile。
- [x] 完成 Unit 2：Refiner prompt、`role='refiner'` runner 调用、`simplifier-result.json` 和兼容 `refinement-summary.json`。
- [x] 完成 Unit 3：`ok/skipped -> Reviewer`、`changes_requested -> Builder rework`、`failed -> Refiner retry/block` 路由。
- [x] Builder 下一轮 prompt 注入 CodeSimplifier findings，避免返工缺少精修反馈。
- [x] runner metadata/env value redaction 覆盖测试。
- [x] 全量 `workflow_controller/tests` 通过：`252 passed in 30.76s`。
- [x] 确认未新增浏览器 UI 或页面。
- **状态：** complete

### 阶段 24：V0.3.3 Requirements Quality Gate
- [x] 完成 Unit 1：Requirements gate validator、controller approval/check 接线、invalid blockedReason 和 revision feedback 注入。
- [x] 完成 Unit 2：Requirements draft prompt、本地 gate template、roadmap/计划/进度/发现记录更新。
- [x] Requirements approval 阻断未映射 active must AO。
- [x] Requirements approval 阻断未声明 verification layer 的 AC。
- [x] 支持 AO 显式 `deferred` / `rejected` / `out_of_scope`，但必须填写原因。
- [x] 全量 `workflow_controller/tests` 通过：`259 passed in 30.51s`。
- [x] 确认未新增浏览器 UI 或页面。
- **状态：** complete

### 阶段 25：V0.3.4 Product Design / Technical Architecture Traceability
- [x] 完成 Unit 1：Requirements 设计/架构可追溯矩阵、approval 质量 gate、draft prompt 和本地 template 更新。
- [x] 完成 Unit 2：Unit Plan test case 设计/架构引用传播、approval gate、prompt 和本地 template 更新。
- [x] Requirements 中存在 `Design/Architecture Traceability Matrix` 时，每条 AC 必须同时映射 Product Design Ref 和 Technical Architecture Ref。
- [x] Unit Plan test case 必须保留对应 AC 的 `product_design_refs` 和 `technical_architecture_refs`。
- [x] 保持历史兼容：旧 requirements 没有设计/架构矩阵时不会被 V0.3.4 新 gate 阻断。
- [x] 定向测试通过：`159 passed in 15.06s`。
- [x] 全量 `workflow_controller/tests` 通过：`264 passed in 31.38s`。
- [x] 确认未新增浏览器 UI 或页面。
- **状态：** complete

### 阶段 26：V0.3.5 Verifier Evidence Schema
- [x] 完成 Unit 1：`verification.json` 新增 `evidence_schema_version=v0.3.5` 和结构化 `evidence_rows`。
- [x] Evidence rows 覆盖 test case id、AC、AO、layer、command/manual evidence、expected、status、result index、returncode、artifact refs 和 golden path。
- [x] 完成 Unit 2：新增 Verifier evidence schema validator，并接入 controller Verifier 通过路径。
- [x] malformed evidence schema 会按验证失败回到 `EXECUTE_UNIT`，不会进入 `UNIT_COMPLETE`。
- [x] 兼容既有 `passed/issues/results/evidence_files` 字段。
- [x] 定向测试通过：`169 passed in 17.97s`。
- [x] 全量 `workflow_controller/tests` 通过：`267 passed in 29.94s`。
- [x] 确认未新增浏览器 UI 或页面。
- **状态：** complete

### 阶段 27：V0.3.6 Final Acceptance Evidence Matrix
- [x] 完成 Unit 1：Final Acceptance gate 从 `verification.json.evidence_rows` 渲染 `## 验收证据矩阵（Final Acceptance Evidence Matrix）`。
- [x] 矩阵展示 AO、AC、Test Case、Layer、Status、Evidence、Expected、Artifacts 和 Golden Path。
- [x] 旧 verification 没有 `evidence_rows` 时保持兼容，显示 missing schema row 并保留原证据摘要。
- [x] 完成 Unit 2：最终验收 patch list 返工反馈附带 evidence matrix context。
- [x] 拒绝时保留 AO/AC/Test Case/Evidence 定位，便于路由到 requirements、unit_plan、defect_fix 或 implementation。
- [x] 定向测试通过：`147 passed in 14.76s`。
- [x] 全量 `workflow_controller/tests` 通过：`268 passed in 30.15s`。
- [x] 确认未新增浏览器 UI 或页面。
- **状态：** complete

### 阶段 28：V0.4+ 版本路线图整合
- [x] 将 `AGENTS.md` / `CLAUDE.md` 初始化规约纳入 V0.4.0。
- [x] 将标准项目文档目录、事实源表和 agent 操作规则纳入 V0.4.0。
- [x] 将详细 `V0.4+ Priority Backlog` 表格写入 `ROADMAP.md`，保留优先级、版本号、主题、任务说明和排序理由。
- [x] 将 Requirements 协商循环、Change Request Ledger、独立 Bug Fix Gate、Journey Acceptance Layer、Final Scope Audit、Requirements-stage Test Strategist 纳入 V0.4.1–V0.4.6。
- [x] 将 Journey Acceptance Layer 调整到 V0.4.4，明确 `journeys.json`、Journey Gate、Journey evidence 和 Final Acceptance Journey Matrix。
- [x] 将 per-role runner、opencode runner、task workspace/branch isolation、file/tool policy 和 clean verification 纳入 V0.5。
- [x] 将 checkpoint/time-travel、unified trace、evidence 类型扩展、failure taxonomy 和 automatic context repair 纳入 V0.6。
- [x] 将结构化契约文件、CI 权威验收和 lifecycle hooks 纳入 V0.7。
- **状态：** complete

### 阶段 29：V0.4.0 Project Agent Operating Guide
- [x] 完成 Unit 1：新增 agent guide 模板与初始化写入逻辑。
- [x] `init` 默认在工作区生成中文 `AGENTS.md` 和标准 docs 目录。
- [x] `--claude-md` 可生成中文 `CLAUDE.md` shim，指向 canonical `AGENTS.md`。
- [x] `AGENTS.md` 加入中文工程行为准则：先澄清、简洁实现、精准修改、避免无关重构、以证据验证 bugfix。
- [x] 已存在 `AGENTS.md` / `CLAUDE.md` 时不覆盖，改写 `.generated` 草稿。
- [x] 新增 `--no-agent-guides` opt-out。
- [x] `init` / `start` 初始化路径均接入 agent guide 配置。
- [x] 生成结果写入 `agentGuideArtifacts`，便于 controller state 审计。
- [x] 定向 RED：新增测试先失败于缺少 `AGENTS.md` 和 `--claude-md`。
- [x] 边界回归覆盖：`--no-agent-guides` 跳过生成，`start` 初始化路径生成 guide。
- [x] 定向 GREEN：新增测试通过；`test_rrc_controller.py` 全文件通过：`94 passed in 5.08s`。
- [x] 全量 `workflow_controller/tests` 通过：`272 passed in 30.72s`。
- **状态：** complete

### 阶段 30：V0.4.1 Requirements Negotiation Loop
- [x] Requirements Drafter 可在目标 tmux agent pane 中集中提出关键澄清问题，拿到回答后继续生成 gate。
- [x] 可用保守假设推进时不打断用户，必须把假设和待确认风险写入 Requirements Gate。
- [x] Requirements 草案生成后先跑 controller 预检；预检失败自动打回 drafter，不进入人工审核。
- [x] Requirements gate 支持多轮批注、返工、确认。
- [x] 每轮 requirements revision 写入 artifact，保留 diff summary、反馈来源和处理结果。
- [x] Requirements revision prompt 携带 controller validation error、Plannotator annotations 和历史 revision feedback。
- [x] 避免 implementation 阶段重新解释 requirements 范围。
- **状态：** complete

### 阶段 31：V0.4.2 Change Request Ledger
- [x] 新增 `change_requests.jsonl`，记录需求变更来源、原因、影响 AO/AC/Test Case/Journey、状态和审批人。
- [x] Requirements approval 会记录 pending/approved change request 审计信息。
- [x] Final Acceptance requirements 路由会写入 change request，并保留 before/after hash。
- [x] 实现阶段直接弱化或删除已批准 AC 的路径被要求回到 requirements/unit_plan gate。
- **状态：** complete

### 阶段 32：V0.4.3 Independent Bug Fix Gate
- [x] `defect_fix` 路由进入独立 Bug Fix Gate，而不是直接退回 Unit Plan revision。
- [x] Bug Fix Gate 记录 expected behavior、actual behavior、root cause 和 regression verification。
- [x] Bug Fix Agent 输出 `root-cause.json` 和 `bug-fix-summary.json`，并把证据回写 Final Acceptance。
- [x] 架构/计划类根因会升级回 Unit Plan 路由。
- **状态：** complete

### 阶段 33：V0.4.4 Journey Acceptance Layer
- [x] 新增 Journey contract artifact：`artifacts/journeys/journeys.json`。
- [x] Requirements gate 在 E2E/closure 验收时要求 Journey Acceptance Matrix。
- [x] Unit Plan gate 要求 active Journey 映射到 closure/E2E test case。
- [x] Verifier 根据真实命令结果生成 `journey-evidence.json`。
- [x] Final Acceptance gate 展示 Journey Matrix，并阻断缺失或失败的 active Journey evidence。
- **状态：** complete

### 阶段 34：V0.4.5 Final Scope Audit
- [x] Final Acceptance 前生成 `artifacts/final-scope-audit/scope-audit.json` 和 `.md`。
- [x] Scope audit 汇总 AO/AC/Journey 覆盖、未覆盖项、声明变更文件和未解释 diff。
- [x] Final Acceptance gate 渲染 scope audit 摘要。
- [x] 存在 blocker 时阻断最终验收 approval。
- **状态：** complete

### 阶段 35：V0.4.5a Requirements Dialogue Brief
- [x] Requirements Draft 前生成 `artifacts/requirements-dialogue-brief/requirements-dialogue-brief.json` 和 `.md`。
- [x] brief 汇总原始用户目标、可行目标、当前 unit、target context、AO ledger 和 revision feedback。
- [x] 明确 brief 是上下文压缩，不是提问机制；提问发生在目标 agent pane。
- [x] Requirements prompt 注入 brief path、hash 和 markdown 摘要，降低需求背景被 progress 误解释的风险。
- **状态：** complete

### 阶段 36：V0.4.6 Strict Test Presence + Requirements-stage Test Strategist
- [x] Unit Plan Test Strategist prompt 已强化 fake/mock E2E 风险识别。
- [ ] Requirements-stage Test Strategist 接入。
- [ ] Requirements approval 前检查 AC 可验证性、测试层级合理性和 Journey/E2E coverage 需求。
- [ ] Unit Plan approval 阶段强制每条非 manual AC 至少映射一个可执行 test case。
- **状态：** pending

### 阶段 37：V0.5.2 审批摘要优先 + Unit Plan 进度输出修复
- [x] Requirements approval Markdown 顶部新增 `## 审批摘要`，完整正文、矩阵和 Journey 映射保留在同一文件附录区。
- [x] Unit Plan approval Markdown 顶部新增 `## 审批摘要`，目标覆盖、测试矩阵、执行单元和 `## Controller State Patch` 保留在同一文件附录区。
- [x] `## Human Confirmation` 仍由 `write_gate_file()` / `approve_gate_file()` 自动追加，生成正文不包含确认段落。
- [x] Plannotator 改为打开 approval Markdown 本身，review summary 记录 review path、approval gate path 和 full path。
- [x] Unit Plan controller 预检失败时在人工审批前自动打回，并把完整原因写入 state 和 `artifacts/unit-plan-draft/controller-validation-error.json`。
- [x] compact drive 输出覆盖 Unit Plan 草案生成、预检、自动打回、等待确认，以及 controller-validation-only / human feedback revision 状态卡。
- [x] 定向 RED/GREEN 覆盖 summary-first、appendix parser、Plannotator approval path、Unit Plan 自动预检打回和 compact Unit Plan 状态。
- [x] 全量 `workflow_controller/tests` 通过：`332 passed in 43.67s`。
- **状态：** complete

### 阶段 38：V0.5.2 现场 tmux-codex 派发竞态与关键信息着色修复
- [x] 现场定位 7 号窗口“回车发不出去”的直接原因：Codex 已写 `DONE_FILE`，但 pane 仍处于 `Working`，controller 过早派发下一轮 prompt，导致 prompt 进入 Codex 排队输入框。
- [x] `tmux-codex` runner 在看到 `DONE_FILE status=done` 后等待 pane 离开 `Working` 状态，再向 controller 返回完成。
- [x] runner event log 新增 `tmux_agent_busy_after_done` / `tmux_agent_idle_after_done`，便于后续诊断类似竞态。
- [x] compact 输出在有色模式下突出自动打回、阻塞和 AO/AC/Test Case/Journey/unit 定位符；默认 `--color auto` 保持不变。
- [x] README 补充 tmux-codex post-done 等待和 compact 关键信息着色说明。
- [x] 定向测试覆盖 tmux-codex post-done 工作态等待、自动打回着色和默认 auto 颜色兼容。
- [x] 全量 `workflow_controller/tests` 通过：`334 passed in 38.87s`。
- **状态：** complete

### 阶段 39：Unit Plan 自动打回默认次数调整
- [x] Unit Plan controller 预检失败后的默认自动打回预算从 2 次提高到 5 次。
- [x] 保留 `unitPlanAutoRevisionMax` 显式覆盖机制，已有 state 可继续按字段覆盖。
- [x] README 补充默认最多自动打回 5 次说明。
- [x] 全量 `workflow_controller/tests` 通过：`335 passed in 40.40s`。
- **状态：** complete

### 阶段 40：V0.5.3 Waygate 安装化与现场降噪
- [x] 对外项目名、deb 包名和安装后命令名统一为 `waygate` / Waygate。
- [x] 内部 Python package 保留 `workflow_controller`，避免大规模 import 重命名。
- [x] 新增 deb 构建脚本，输出 `dist/waygate_0.5.3_all.deb`。
- [x] compact reporter 按最终渲染状态卡去重，避免重复 `检查 Unit Plan 确认` 噪声。
- [x] 相对 artifact 目录测试改为隔离在 `tmp_path`，避免生成 `relative-artifacts/` 污染 repo root。
- [x] README / USAGE / ROADMAP 同步 Waygate 安装和使用方式。
- [x] 全量 `workflow_controller/tests` 通过：`339 passed in 40.64s`。
- **状态：** complete

### 阶段 41：auto Claude pane 权限模式与 tmux 派发可靠性修复
- [x] 复现首次派发 prompt 停在 tmux pane 输入框、缺少提交键时只能靠 idle nudge 驱动的问题。
- [x] tmux runner 派发后捕获 pane；当 dispatch prompt 和当前 `RUN_ID` 仍在输入框时自动补发一次提交键。
- [x] 复现自动启动 Claude Code 因默认交互权限模式停在文件创建确认的问题。
- [x] 自动创建 Claude pane 默认启动 `claude --permission-mode bypassPermissions`，避免 worker 交互式确认卡住。
- [x] 支持 `WAYGATE_AUTO_CLAUDE_PERMISSION_MODE` 和 `WAYGATE_AUTO_CLAUDE_COMMAND` 覆盖 auto pane 启动方式。
- [x] runner 预创建 pending `done.json` 作为兜底，等待循环忽略 pending 并继续等待真实 `done` / `blocked` 信号。
- [x] 保留 Codex submit retry 事件兼容和 post-done `Working` 等待逻辑。
- [x] README / USAGE 同步 auto Claude 权限模式、环境变量覆盖、tmux pending `DONE_FILE` 和补交行为。
- [x] 全量 `workflow_controller/tests` 通过：`343 passed in 47.44s`。
- **状态：** complete

### 阶段 42：Requirements revision AO Ledger 污染修复
- [x] 定位 V1.4.1 现场阻塞根因：完整 Requirements gate 正文被当作 requirements feedback 写入 AO Ledger。
- [x] Requirements / Unit Plan revision 继续把完整 gate 正文传给 drafter，但 AO Ledger 只消费 Plannotator feedback 或 structured annotations。
- [x] Plannotator 纯文本 `# File Feedback` 输出按反馈章节拆成独立 AO。
- [x] Requirements / Unit Plan AO id 识别兼容 `AO-01` / `AO-1` 并规范化到 `AO-001`。
- [x] 已确认 `<target-project>/.rrc-controller-v1.4.1` 是受污染现场 state；本阶段代码修复不静默改写历史 state。
- [x] 定向测试通过：`4 passed in 1.59s`。
- [x] AO / Human gate 回归通过：`59 passed in 16.51s`。
- [x] 全量 `workflow_controller/tests` 通过：`347 passed in 45.63s`。
- **状态：** complete

### 阶段 43：GitHub 发布文档与社区文件整理
- [x] 将 `README.md` 改为英文 GitHub 默认入口，顶部提供中文入口和核心 docs 链接。
- [x] 新增 `README.zh-CN.md`，保留中文项目入口。
- [x] 将 `USAGE.md` / `ROADMAP.md` 调整为英文默认文档，并新增 `USAGE.zh-CN.md` / `ROADMAP.zh-CN.md`。
- [x] 新增双语架构与工作流文档：`docs/architecture*.md`、`docs/workflow*.md`。
- [x] 新增 `LICENSE`、`CONTRIBUTING*.md`、`CHANGELOG*.md`、`SECURITY.md`、GitHub issue templates 和 PR template。
- [x] `.gitignore` 补充本地 controller state、虚拟环境、coverage/cache 忽略规则。
- [x] Debian packaging 安装双语 docs，并更新 packaging 测试覆盖。
- [x] 源码 Markdown 本地链接检查通过：`checked 23 source markdown files; all local links resolve`。
- [x] 打包测试通过：`1 passed in 0.58s`。
- [x] 全量 `workflow_controller/tests` 通过：`354 passed in 51.27s`。
- **状态：** complete

### 阶段 44：GitHub 发布脱敏与远程同步
- [x] 移除已跟踪 `docs/superpowers/` 文档，并将 `docs/superpowers/` 写入 `.gitignore`。
- [x] 全文移除本机 venv 激活命令，标准测试命令统一为 `python -m pytest workflow_controller/tests -q` 或对应定向 pytest 命令。
- [x] 清理公开文档和维护历史中的本机绝对路径，保留通用占位如 `<target-project>`。
- [x] 更新 `AGENTS.md` 和 `workflow_controller/agent_guides.py`，避免后续生成 guide 时携带本机路径。
- [x] 发布脱敏扫描通过：无本机绝对路径、私有环境标识或本机 venv 激活命令残留；tracked 文件中无 `docs/superpowers/`。
- [x] 打包测试通过：`1 passed in 0.49s`。
- [x] 全量 `workflow_controller/tests` 通过：`354 passed in 48.50s`。
- **状态：** complete

## 关键问题
1. 多实例同时运行是否要在控制器层面增加显式实例隔离或锁文件策略，仍需结合真实运行方式验证。
2. 是否需要为新工作区补充独立的打包配置、入口脚本或 CI，后续按开发需要决定。
3. 当前工作区有未提交变更，下一步需要根据用户要求决定是否提交到 `workflow-controller` 分支。

## 已做决策
| 决策 | 理由 |
|------|------|
| 后续开发目录使用 `~/works/ai-works/worktrees/workflow-controller` | 和现有 `ai-works` worktree 管理方式一致，便于长期开发 |
| 使用孤儿分支 `workflow-controller` | 当前项目来自历史工作目录，不适合混入现有业务分支历史 |
| 保留包目录 `workflow_controller/` | 现有测试以该包路径运行，复制后无需改导入结构 |
| 默认紧凑输出，`--verbose` 查看原始日志 | 常规运行只看进展，排错时仍能看到完整细节 |
| 终端状态使用中文 | 用户明确要求展示状态中文化 |
| Plannotator 默认 20000 端口 | 用户本机 Plannotator 使用该端口 |

## 遇到的错误
| 错误 | 尝试次数 | 解决方案 |
|------|---------|---------|
| `git worktree add --orphan workflow-controller <path>` 语法不匹配 | 1 | 改用 `git worktree add --orphan -b workflow-controller <path>` |
| 首次提交误包含 `__pycache__` | 1 | `git rm` 删除生成文件，新增 `.gitignore`，并 amend 初始提交 |

## 备注
- 进入新工作区：`cd ~/works/ai-works/worktrees/workflow-controller`
- 测试命令：`python -m pytest workflow_controller/tests -q`
- 当前初始功能提交：`fd27a54 Add workflow controller project`
