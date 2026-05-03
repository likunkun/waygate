# 任务计划：Workflow Controller 后续开发基线

## 目标
将当前 `workflow_controller` 功能、决策和进度固化到 `~/works/ai-works/worktrees/workflow-controller`，后续开发以该分支工作区为准。

## 当前阶段
已完成基础功能（阶段 1–18）、V0.1 Test Strategist 接入（阶段 19–21，全量测试 144 passed）和 V0.3.1 Acceptance Obligation Ledger（阶段 22，全量测试 240 passed）。当前继续以 `ROADMAP.md` 为版本规划基线推进 workflow-controller。

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
- [x] 同步到实际运行目录 `/home/lichangkun/.hermes/hermes-agent/workflow_controller`
- [x] 测试通过
- **状态：** complete

### 阶段 9：验证失败原因摘要
- [x] controller retry 输出显示失败命令摘要
- [x] controller retry 输出显示 exit code
- [x] controller retry 输出优先提取根因，如缺少 `DATABASE_URL`
- [x] 完整失败详情仍保留在 `verification.json`
- [x] 同步到实际运行目录 `/home/lichangkun/.hermes/hermes-agent/workflow_controller`
- [x] 测试通过
- **状态：** complete

### 阶段 10：旧 Session 验证环境自动修复
- [x] verifier 前置检查 Playwright/Prisma/DATABASE_URL 环境需求
- [x] 可从 `prisma/dev.db` 推导时自动写入 `verification_env.DATABASE_URL`
- [x] 推导来源写入 `verification_env_inferred`
- [x] 推导失败时直接 `blocked`，不回 Builder 重试
- [x] 同步到实际运行目录 `/home/lichangkun/.hermes/hermes-agent/workflow_controller`
- [x] 测试通过
- **状态：** complete

### 阶段 11：Plannotator 与人工 Gate 集成
- [x] Plannotator `Approve` 后 controller 自动继续，不再要求用户回终端再选一次
- [x] Plannotator `Close` 后保持 gate pending
- [x] controller 启动 Plannotator 时输出打开网址 `http://localhost:20000`
- [x] 审阅文件改为 Claude 生成的 body artifact，确认文件仍保留在 `approvals/`
- [x] 终端回显审阅文件和确认文件路径，避免审阅对象和落盘对象不一致
- [x] 同步到实际运行目录 `/home/lichangkun/.hermes/hermes-agent/workflow_controller`
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
- [x] 同步到实际运行目录 `/home/lichangkun/.hermes/hermes-agent/workflow_controller`
- **状态：** complete

### 阶段 14：Unit Plan 确认后执行推进修复
- [x] 修复 `PLAN_CREATED + scopeApproved=True` 没有下一步动作的问题
- [x] Unit Plan 确认后若 scope 已批准，直接进入 `PLAN_APPROVED`
- [x] `lastVerifiedStep` 在新 Unit Plan 生效后重置为 `PLAN_CREATED`，避免继承上一单元 `VERIFY_UNIT`
- [x] 已落盘的卡住状态可在 `get_status()` 中自动修复为 Builder-ready
- [x] 用当前 V2.2 状态验证 `nextAction=run_builder`
- [x] 同步到实际运行目录 `/home/lichangkun/.hermes/hermes-agent/workflow_controller`
- **状态：** complete

### 阶段 15：Final Acceptance Defect Fix 流程
- [x] 最终验收拒绝时新增 `defect_fix` 路由
- [x] `defect_fix` 不走 requirements draft，直接进入 Unit Plan revision
- [x] Unit Plan revision prompt 明确要求根据验收缺陷生成 bug-fix units，不改变原需求目标
- [x] Controller State Patch 允许已 covered objective 被 bug-fix unit 重新打开为 `partial`
- [x] Builder prompt 在执行 defect-fix unit 时携带最终验收缺陷清单
- [x] 终端验收路由菜单加入“验收缺陷修复 -> Defect Fix”
- [x] 同步到实际运行目录 `/home/lichangkun/.hermes/hermes-agent/workflow_controller`
- [x] 全量测试通过
- **状态：** complete

### 阶段 16：Unit Plan 测试用例矩阵与测试策略预检
- [x] Unit Plan drafter prompt 明确要求使用 `test-strategy` skill
- [x] Unit Plan 必须生成 `## Test Case Matrix`
- [x] Controller State Patch unit 支持 `test_cases`
- [x] Unit Plan approval 拒绝只有 tsc/lint/typecheck 等静态检查、没有测试用例或人工证据的计划
- [x] 静态检查可以作为补充，但不能单独证明行为验收
- [x] Builder prompt 要求优先补齐 mapped test cases，defect-fix unit 要补回归测试或人工证据
- [x] 同步到实际运行目录 `/home/lichangkun/.hermes/hermes-agent/workflow_controller`
- [x] 全量测试通过
- **状态：** complete

### 阶段 17：旧 Final Acceptance Gate 路由迁移修复
- [x] 复现旧 `final-acceptance.md` 缺少 `Defect fix` 行时，终端选择 `1` 后仍无法返工的问题
- [x] `ensure_final_acceptance_gate()` 自动规范化旧 Rejection Routing checklist，补齐 `Defect fix`
- [x] 终端路由写入改为重写 canonical checklist，并校准唯一选中项
- [x] `reject_final_acceptance_gate()` 从 gate 文件读取路由，Plannotator 反馈只作为返工 prompt 内容
- [x] final acceptance 路由写入导致 gate mtime 变新时，仍保留本轮 Plannotator 反馈
- [x] 同步到实际运行目录 `/home/lichangkun/.hermes/hermes-agent/workflow_controller`
- [x] 全量测试通过
- **状态：** complete

### 阶段 18：非 Ralph 新目标初始化修复
- [x] 复现 `init --target V3.0 --workspace-dir ...` 不带 `--from-ralph` 时落到 demo `usable-system/unit-01` 的问题
- [x] 新增 target acceptance 初始化路径，不依赖 `.plan-ralph/session.json`
- [x] 写入 `requestedOutcome=V3.0`、`currentUnitId=target-v3-0`、`workspacePath`、runner 和 tmux target
- [x] 生成 `target-acceptance-prompt.md`，并进入 `REQUIREMENTS_DRAFT -> run_requirements_drafter`
- [x] 保留无 target 的默认 demo 初始化兼容行为
- [x] 同步到实际运行目录 `/home/lichangkun/.hermes/hermes-agent/workflow_controller`
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
- [x] Phase 1: Brainstorm — 完成 AO Ledger 最小可交付设计，并统一当前实施计划位置为 `/home/lichangkun/.claude/plans/glowing-kindling-engelbart.md`
- [x] Phase 1.5: Design System — skipped（非 UI 任务）
- [x] Phase 2: Write Plan — 完成 V0.3.1 实施计划
- [x] Phase 2.5: Plan Review — 用户确认按已讨论 V0.3.1 方向执行
- [x] Phase 3: Execute — 完成 AO helper、feedback 接入、prompt 注入、Unit Plan AO 覆盖 gate 和回归测试
  - Implementation plan: `/home/lichangkun/.claude/plans/glowing-kindling-engelbart.md`
  - Scale: single-unit
  - Completion promise: TASK COMPLETE
- [x] Phase 3.5: Simplify — 已完成最小实现整理，未引入额外抽象
- [x] Phase 3.7: Browser Verify — skipped（无用户可见 UI）
- [x] Phase 4: Verify and Finish — `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `240 passed in 32.12s`
- **目标：** 新增 Acceptance Obligation Ledger，让人工反馈/验收失败问题以稳定 AO id 贯穿 Requirements、Unit Plan、Verifier evidence 和 Final Acceptance，避免多条问题被压缩成单个 closure unit。
- **状态：** complete

## 关键问题
1. 多实例同时运行是否要在控制器层面增加显式实例隔离或锁文件策略，仍需结合真实运行方式验证。
2. 是否需要为新工作区补充独立的打包配置、入口脚本或 CI，后续按开发需要决定。
3. 当前工作区有未提交变更，下一步需要根据用户要求决定是否提交到 `workflow-controller` 分支。

## 已做决策
| 决策 | 理由 |
|------|------|
| 后续开发目录使用 `~/works/ai-works/worktrees/workflow-controller` | 和现有 `ai-works` worktree 管理方式一致，便于长期开发 |
| 使用孤儿分支 `workflow-controller` | 当前项目来自 Hermes 子目录，不适合混入现有业务分支历史 |
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
- 测试命令：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q`
- 当前初始功能提交：`fd27a54 Add workflow controller project`
