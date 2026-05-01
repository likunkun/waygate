# 进度日志

## 会话：2026-04-29

### 阶段 9：Plannotator 与人工 Gate 集成
- **状态：** complete
- 背景：
  - 用户使用 Plannotator 审阅需求和 Unit Plan 时，期望浏览器 `Approve` 后 controller 自动继续。
  - 之前 controller 让 Plannotator 审阅的文件与 Claude 写入的 body artifact 不一致。
  - 用户需要启动 Plannotator 时直接看到打开网址。
- 已完成：
  - Plannotator `Approve` 输出 `decision=approved` 后，controller 自动调用对应 gate approval 并继续。
  - Plannotator `Close` 输出 `decision=dismissed` 后，controller 保持 gate pending。
  - 需求审阅文件改为 `artifacts/requirements-draft/requirements-body.md`。
  - Unit Plan 审阅文件改为 `artifacts/unit-plan-draft/unit-plan-body.md`。
  - `approvals/requirements-and-acceptance.md` 和 `approvals/unit-plan.md` 继续作为确认文件。
  - 启动 Plannotator 时输出 `打开网址：http://localhost:20000`。

### 阶段 10：Unit Plan Gate 校验与反馈闭环
- **状态：** complete
- 背景：
  - 用户按 `a` 后 Unit Plan 可能仍然 gate invalid，但旧流程会留下令人误解的确认状态。
  - Plannotator 多条反馈在终端短预览中看起来像只收到第一条。
- 已完成：
  - `approve_human_gate('unit-plan')` 先校验 Unit Plan，再写 approval。
  - 无效 Unit Plan 保持 pending，并在菜单中显示 `unit plan gate invalid: ...`。
  - Unit Plan 返工 prompt 包含 `Controller Validation Error`。
  - Plannotator 反馈显示 `共 N 条，完整反馈已写入 Claude 返工 prompt。`，并保留预览。
  - Plannotator 返回 `annotations` 数组时保留结构化信息。
- 已验证：
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py -q` -> `65 passed in 17.62s`
  - 实际运行目录单测：Plannotator feedback 回显用例通过。

### 阶段 11：Unit Plan Rollup 与历史单元兼容
- **状态：** complete
- 背景：
  - V2.2 当前只剩 `v2-2-u5-baidu-search` 需要执行。
  - Unit Plan 的 rollup objective `Complete V2.2...` 合理引用 `v2-2-u1` 到 `u5`，但旧校验要求 partial objective 的每个 unit 都必须出现在 `units`。
- 已完成：
  - 已完成历史单元可以出现在 `partial` 聚合目标里。
  - 未完成且未声明在 `units` 中的 unit 仍然被阻断。
  - Unit Plan drafter prompt 更新，说明 completed existing unit 可用于 rollup objective。
- 已验证：
  - 新增正向用例：partial rollup 可引用 completed existing units。
  - 新增反向用例：undeclared unfinished unit 仍然阻断。
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py -q` -> `67 passed in 17.44s`
  - 实际运行目录新增用例 -> `2 passed in 1.16s`

### 阶段 12：Unit Plan 确认后执行推进修复
- **状态：** complete
- 背景：
  - 用户在 V2.2 Unit Plan 菜单按 `a` 后，controller 输出 `[停止] 当前没有可执行的下一步。`
  - 现场 `session.json` 状态为 `currentStep=PLAN_CREATED`、`scopeApproved=True`、`unitPlanAccepted=True`、`lastVerifiedStep=VERIFY_UNIT`。
- 根因：
  - 状态机只处理 `PLAN_CREATED + scopeApproved=false -> require_scope_approval`。
  - `PLAN_CREATED + scopeApproved=true` 没有动作，导致 `compute_next_allowed_action()` 返回 `None`。
  - 新 Unit Plan 生效时没有重置上一单元留下的 `lastVerifiedStep=VERIFY_UNIT`。
- 已完成：
  - Unit Plan 确认后若 `scopeApproved=True`，直接进入 `PLAN_APPROVED`。
  - 新 Unit Plan 生效后将 `lastVerifiedStep` 重置为 `PLAN_CREATED`。
  - `reconcile_state()` 会自动把已落盘的 `PLAN_CREATED + scopeApproved=True + unitPlanAccepted=True` 修复为 `PLAN_APPROVED`。
  - 已同步 `rrc_controller.py`、`rrc_validators.py` 和相关测试到实际运行目录。
- 已验证：
  - 新增用例：preapproved scope 的 Unit Plan approval 直接进入 builder-ready state。
  - 新增用例：已落盘卡住状态在 `get_status()` 中自动修复。
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py -q` -> `69 passed in 17.65s`
  - 实际运行目录新增用例 -> `2 passed in 1.19s`
  - 当前 V2.2 state 检查结果：
    - `currentStep=PLAN_APPROVED`
    - `nextAction=run_builder`
    - `currentUnitId=v2-2-u5-baidu-search`
    - `lastVerifiedStep=PLAN_CREATED`

### 阶段 13：Final Acceptance Defect Fix 流程
- **状态：** complete
- 背景：
  - 最终验收可能发现历史已完成单元的缺陷，例如 i18n、logo、主页、工作台没有真正改到位。
  - 当前 Builder 只允许执行当前 unit，不能越界修历史 covered unit。
  - 走需求变更太重，因为原需求可能是对的，只是实现没满足。
- 已完成：
  - 新增最终验收拒绝路由 `defect_fix`。
  - 最终验收 gate 的 Rejection Routing 增加 `Defect fix` 选项。
  - 终端路由菜单增加 `1  验收缺陷修复 -> Defect Fix`。
  - `defect_fix` 会保持 requirements accepted，不走 requirements draft。
  - `defect_fix` 会进入 Unit Plan revision，并设置 `unitPlanRevisionMode=defect_fix`。
  - Unit Plan drafter prompt 增加 `Final Acceptance Defect-Fix Mode`，要求生成 bug-fix units、不改变已批准需求、不重新解释目标。
  - Controller State Patch 支持已 covered objective 通过新增 bug-fix unit reopen 为 `partial`。
  - Builder prompt 对 defect-fix unit 携带最终验收缺陷清单，避免 Builder 缺少原始验收上下文。
  - 已同步 `rrc_controller.py`、`rrc_human_gates.py`、`rrc_steps.py` 和相关测试到实际运行目录。
- 已验证：
  - 新增用例：final acceptance `Defect fix` route 进入 Unit Plan revision。
  - 新增用例：Unit Plan defect-fix prompt 要求 bug-fix units 且不改需求。
  - 新增用例：Builder prompt 包含最终验收缺陷清单。
  - 新增用例：covered objective 可通过 defect-fix unit reopen 为 partial。
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py -q` -> `73 passed in 17.44s`
  - `python -m pytest workflow_controller/tests -q` -> `110 passed in 38.52s`
  - 实际运行目录新增关键用例 -> `4 passed in 1.27s`

### 阶段 14：Unit Plan 测试用例矩阵与测试策略预检
- **状态：** complete
- 背景：
  - 当前 controller 只能验证命令是否通过，不能判断测试用例是否覆盖验收标准。
  - 用户指出测试用例方面非常欠缺，尤其会出现“验证全绿但人工验收发现大量核心场景没测”的问题。
- 已完成：
  - Unit Plan drafter prompt 增加 `Use the test-strategy skill...`。
  - Unit Plan required structure 增加 `## Test Case Matrix`。
  - Test Case Matrix 明确映射：`Acceptance Criterion -> Test Case -> Layer -> Command/Evidence -> Expected Result`。
  - Controller State Patch unit 增加 `test_cases` 示例字段。
  - Unit Plan local template 会渲染 test case matrix 和每个 unit 的 test cases。
  - Unit Plan approval 新增 `validate_unit_plan_test_case_coverage()`。
  - 只有 `tsc`/lint/typecheck 等静态检查、且没有 `test_cases` 或 Test Case Matrix evidence 的 unit 会被拒绝。
  - Builder prompt 要求先补 mapped test cases；defect-fix unit 要补回归测试或人工证据。
  - `rrc_models.py` 增加 `UNIT_PLANNER` role hint：`test-strategy + writing-plans`。
  - 已同步 `rrc_controller.py`、`rrc_human_gates.py`、`rrc_steps.py`、`rrc_models.py` 和相关测试到实际运行目录。
- 已验证：
  - 新增用例：Unit Plan prompt 要求 `test-strategy` 和 Test Case Matrix。
  - 新增用例：只有静态检查的 Unit Plan 被 approval 阻断。
  - 新增用例：有明确 Test Case Matrix/manual evidence 的计划可通过。
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py -q` -> `76 passed in 17.64s`
  - `python -m pytest workflow_controller/tests -q` -> `113 passed in 38.17s`
  - 实际运行目录新增关键用例 -> `3 passed in 1.20s`

### 当前未提交变更
- **状态：** pending
- `workflow_controller/rrc_controller.py`
- `workflow_controller/rrc_human_gates.py`
- `workflow_controller/rrc_models.py`
- `workflow_controller/rrc_steps.py`
- `workflow_controller/tests/test_rrc_controller.py`
- `workflow_controller/tests/test_rrc_human_gates.py`
- `task_plan.md`
- `findings.md`
- `progress.md`

### 阶段 17：旧 Final Acceptance Gate 路由迁移修复
- **状态：** complete
- 背景：
  - 用户在 Plannotator 最终验收反馈后选择 `1  验收缺陷修复 -> Defect Fix`。
  - controller 已回显 `[验收路由] 已选择：Defect fix`，但随后报错：`Final acceptance rejection routing must select one option...`。
- 根因：
  - 现场 `approvals/final-acceptance.md` 是旧格式，`Rejection Routing` 中没有 `Defect fix` 行。
  - 旧 `_write_final_acceptance_rejection_route()` 只会勾选已存在的 checklist 行，缺失 route 时不会补齐，也不会校验写入是否成功。
  - 终端选择 route 会重写 gate，mtime 晚于 Plannotator summary；如果继续按 stale 处理，会丢失本轮浏览器批注。
- 已完成：
  - `ensure_final_acceptance_gate()` 会规范化旧 Rejection Routing checklist，自动补齐 `Defect fix`。
  - 终端 route 写入改为重写 canonical checklist，并设置唯一选中项。
  - `reject_final_acceptance_gate()` 从 gate 文件读取路由，返工 prompt 仍使用 gate + Plannotator feedback 的完整组合内容。
  - final acceptance route 写入导致 gate mtime 变新时，仍读取本轮 Plannotator feedback。
  - 已同步 `rrc_controller.py`、`rrc_human_gates.py` 和 `tests/test_rrc_controller.py` 到实际运行目录。
- 已验证：
  - 新增红绿用例：旧 final acceptance gate 缺少 `Defect fix` 行时，选择 `1` 后进入 defect-fix，并保留 Plannotator 反馈。
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py -q` -> `77 passed in 17.46s`
  - `python -m pytest workflow_controller/tests -q` -> `114 passed in 38.31s`
  - 实际运行目录关键用例 -> `2 passed in 1.25s`

### 阶段 18：Defect Fix Unit Plan Prompt 显性化回滚
- **状态：** complete
- 背景：
  - 用户指出：既然实际 prompt 已经包含 Plannotator 反馈，就不需要额外改 prompt 结构。
- 已完成：
  - 回滚 defect-fix 模式下的专用 `Final Acceptance Defects From Plannotator/Human Review` 区块。
  - 保留原本已存在的数据流：`unitPlanRevisionFeedback` 仍进入 `Existing Unit Plan draft with human notes and requested changes` 区块。
  - 删除对应的显性化测试断言。
  - 保留旧 gate 缺 `Defect fix` 行的路由迁移修复。

### 阶段 19：非 Ralph 新目标初始化修复
- **状态：** complete
- 背景：
  - 用户执行 `init --workspace-dir /home/lichangkun/works/ai-works/worktrees/union --target "V3.0"`，随后 `start --target "V3.0"` 报 existing session mismatch。
  - 现场 `session.json` 为 demo state：`requestedOutcome=usable-system`、`currentUnitId=unit-01`。
- 根因：
  - `init_state()` 只有 `from_ralph=True` 时才使用 target/workspace 构建真实目标状态。
  - `from_ralph=False` 时直接落到 `DEFAULT_INITIAL_STATE`，导致 `--target` 被静默忽略。
- 已完成：
  - 新增 `build_state_from_target_acceptance()`，无需 Ralph session 也能从 `workspace_dir + target` 构建 target acceptance state。
  - `init_state()` 在非 Ralph 且传入 `--target` 时使用新路径，生成 `target-acceptance-prompt.md`。
  - 初始化后进入 `REQUIREMENTS_DRAFT`，下一步为 `run_requirements_drafter`，避免 demo dry-run 直接完成。
  - 保留不传 target 的默认 demo 初始化行为，兼容现有测试和演示用法。
  - 已同步 `rrc_controller.py`、`rrc_real_runtime.py` 和 `tests/test_rrc_controller.py` 到实际运行目录。
  - 已用真实 V3.0 state-dir 重新执行 `init --force`，当前 state 正确：
    - `requestedOutcome=V3.0`
    - `currentUnitId=target-v3-0`
    - `currentStep=REQUIREMENTS_DRAFT`
    - `nextAllowedActions=['run_requirements_drafter']`
- 已验证：
  - 新增红绿用例：`init --target V3.0 --workspace-dir ...` 不带 `--from-ralph` 时创建真实 target state。
  - 相关初始化/start/Ralph 用例 -> `7 passed in 0.60s`
  - 实际运行目录关键用例 -> `2 passed in 2.49s`
  - `python -m pytest workflow_controller/tests -q` -> `115 passed in 40.82s`

### 阶段 20：V0.1 Unit 1 配置、runner 与 env 隔离
- **状态：** complete
- 背景：
  - 执行 approved unit `v0-1-u1-config-runner-isolation`。
  - 上轮 controller verifier 在 `/bin/sh` 下执行 `source ...` 导致 approved verification commands 返回 127。
- 已确认：
  - 默认 `testStrategistEnabled=false` 已覆盖。
  - `roleRunners.test_strategist` 默认 `subprocess + codex exec --dangerously-bypass-approvals-and-sandbox -`，并支持 role-specific override。
  - `roleRunners.test_strategist.env` 只通过 role runner request 注入，不污染 builder 等非 Test Strategist runner。
  - runner metadata 只记录 role、runner 和 env keys，不记录代理、token 或 secret value。
  - verifier 已用 bash 执行 shell verification command，并有 `source ./activate` 回归用例覆盖。
- 已验证：
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `19 passed in 10.94s`
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_real_runtime.py -q` -> `15 passed in 6.44s`
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `50 passed in 3.92s`
- Review note：
  - 独立 review 提醒 Test Strategist production orchestration path 尚未接入 role 参数；该接入属于后续 controller orchestration unit，当前 unit 已完成 runner/config/env 隔离基础能力。

### 阶段 21：V0.1 Unit 5 回归验收
- **状态：** complete
- 背景：
  - 执行 approved unit `v0-1-u5-regression-acceptance`。
  - 核心缺口是完整 E2E 用例 `TC-E2E01-enabled-full-unit-plan-strategy-flow` 尚未落到 `test_rrc_controller.py` 中。
- 已完成：
  - 新增 `test_e2e_test_strategist_unit_plan_flow`，覆盖默认关闭 baseline、启用 Test Strategist、首轮 Critical gap 自动返工、第二轮 Major/Minor 进入现有 Unit Plan gate、summary/gap/review artifacts、env key-only 记录、无 `WAITING_TEST_STRATEGY_APPROVAL`。
  - 确认 disabled flow 不生成 `test-strategy.json` / `unit-plan-gap-report.json` / `unit-plan-review-package.json`。
  - 确认 enabled flow 生成完整 strategist artifacts，且最终 `approvals/unit-plan.md` 不包含 unresolved Critical gap。
  - 确认本单元没有新增浏览器 UI 或 browser-visible page，不需要浏览器验收。
- 已验证：
  - RED：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_controller.py::test_e2e_test_strategist_unit_plan_flow -q` -> `ERROR: not found`。
  - GREEN：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_controller.py::test_e2e_test_strategist_unit_plan_flow -q` -> `1 passed in 0.22s`。
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `19 passed in 11.03s`。
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `66 passed in 4.40s`。
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `33 passed in 14.74s`。
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_real_runtime.py -q` -> `15 passed in 6.52s`。
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `144 passed in 40.34s`。
- Review note：
  - simplify skill required three subagent reviews, but all three Agent calls returned API 503; local simplify pass found no cleanup worth changing.

## 会话：2026-04-28

### 阶段 5：控制器可靠性增强
- **状态：** complete
- 开始时间：2026-04-28
- 目标：
  - 防止同一 verification/review/builder timeout 死循环。
  - 防止 tmux Claude 写错旧 run 的 done.json。
  - 将验证环境从命令字符串中抽离为 `verification_env`。
  - 在 Unit Plan approval 阶段预检明显不可运行的验证配置。
  - 改善 timeout/idle 诊断信息。
- 计划测试：
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q`
- 已完成：
  - 重复 verification/review 失败会按 unit/stage/fingerprint 计数；默认第一次返工，第二次相同失败直接 `blocked`。
  - tmux runner 为每个 run 注入 `RRC_RUN_ID`，prompt 要求 `done.json` 携带 `run_id`，控制器拒绝 wrong-run done signal。
  - verifier 支持 state/unit 级 `verification_env`/`verificationEnv`，运行时注入 subprocess，artifact 只记录 env key。
  - Unit Plan approval 会拒绝明显缺 `verification_env` 的 Playwright/E2E/Prisma 验证命令，并在 drafter prompt 中提示填写 `verification_env`。
  - tmux timeout 现在区分普通 timeout、idle-without-done、wrong-run done signal、invalid done.json，并保存 pane tail。
- 已验证：
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_repeated_verification_failure_blocks_before_another_retry -q`
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q`
  - `python -m pytest workflow_controller/tests/test_rrc_real_runtime.py::test_run_verifier_injects_unit_verification_env_without_inlining_it_in_command -q`
  - `python -m pytest workflow_controller/tests/test_rrc_human_gates.py::test_unit_plan_approval_rejects_playwright_command_without_database_env -q`
  - `python -m pytest workflow_controller/tests -q` -> `76 passed in 19.91s`

### 阶段 6：控制器运行可见性优化
- **状态：** complete
- 开始时间：2026-04-28
- 背景：
  - Claude 写入 `done.json` 后，controller 会继续执行自己的 verifier。
  - verifier 使用捕获输出，长 Playwright 命令运行时终端没有新日志，容易误判为 controller 没反应。
  - 紧凑输出将历史 covered units 纳入分母，导致 V2.1 显示为 `1/10`，实际当前目标只有 4 个单元。
- 已完成：
  - verifier 仅在状态变化时输出标志：验证开始、每条命令开始、每条命令结束、验证完成。
  - 不做 30 秒 heartbeat，不刷命令 stdout/stderr，避免输出噪声。
  - 紧凑 roadmap 对当前 requestedOutcome 优先按目标相关 objectiveCoverage 计算单元进度，V2.1 显示为 `1/4`、`2/4`。
- 已验证：
  - `python -m pytest workflow_controller/tests -q` -> `79 passed in 21.05s`
  - 实际运行目录新增行为测试 -> `3 passed in 1.40s`

### 阶段 7：验证失败原因摘要
- **状态：** complete
- 开始时间：2026-04-28
- 背景：
  - controller 验证失败时紧凑输出只显示“验证未通过”，用户需要打开 artifact 才能看到失败命令和根因。
  - 本次实际失败根因是 Playwright 验证命令缺少 `DATABASE_URL`，Next.js warning 只是噪声。
- 已完成：
  - retry 输出会追加 compact failure reason：失败命令、exit code、优先提取的根因行。
  - 对 `Environment variable not found: DATABASE_URL` 这类错误会压缩成 `missing env DATABASE_URL`。
  - 保留完整 stdout/stderr 在 `verification.json`。
- 已验证：
  - `python -m pytest workflow_controller/tests -q` -> `80 passed in 19.99s`
  - 实际运行目录失败摘要测试 -> `1 passed in 1.15s`

### 阶段 8：旧 Session 验证环境自动修复
- **状态：** complete
- 开始时间：2026-04-28
- 背景：
  - 同类 `DATABASE_URL` 缺失问题已第二次出现，上一次靠手工修改 session 收场。
  - 新 Unit Plan approval 预检无法覆盖已经批准的旧 session。
- 已完成：
  - verifier 运行前会检查 verification command 所需环境。
  - 对 Playwright/Prisma/显式 `DATABASE_URL` 命令，若 state/unit 未配置 `DATABASE_URL`，会尝试从 `executionWorkspacePath/prisma/dev.db` 或 `workspacePath/prisma/dev.db` 自动推导。
  - 推导成功会写入 state-level `verification_env` 和 `verification_env_inferred`，后续验证复用，不需要手改 session。
  - 推导失败会直接 `blocked`，提示 `verification environment is incomplete`，不会回 Builder 重试。
- 已验证：
  - `python -m pytest workflow_controller/tests -q` -> `82 passed in 20.37s`
  - 实际运行目录新增验证环境测试 -> `2 passed in 1.33s`

### 阶段 1：运行问题修复
- **状态：** complete
- 执行的操作：
  - 修复 Plannotator 启动方式，避免控制器等待前台进程直到超时。
  - 增加 Plannotator 端口配置，默认使用 20000。
  - 修复 Unit Plan 确认后状态不推进的问题。
  - 提高默认最大步数到 2000。
  - 增加重复无进展 50 次保护。
- 创建/修改的文件：
  - `workflow_controller/rrc_plannotator.py`
  - `workflow_controller/rrc_controller.py`
  - `workflow_controller/rrc_human_gates.py`
  - `workflow_controller/rrc_steps.py`
  - 相关测试文件

### 阶段 2：输出体验优化
- **状态：** complete
- 执行的操作：
  - 默认切换为紧凑输出。
  - 将重复循环信息聚合为 attempt 摘要。
  - 保留 `--verbose` 作为原始详细日志开关。
  - 增加颜色参数 `--color auto|always|never`。
  - 状态、阶段、动作展示改为中文。
- 创建/修改的文件：
  - `workflow_controller/rrc_controller.py`
  - `workflow_controller/rrc_steps.py`
  - 相关测试文件

### 阶段 3：迁移到 ai-works 分支工作区
- **状态：** complete
- 开始时间：2026-04-28 10:31 +0800
- 执行的操作：
  - 确认 `~/works/ai-works` 是 bare/manage repo。
  - 创建 `workflow-controller` 孤儿分支 worktree。
  - 将当前项目复制到 `~/works/ai-works/worktrees/workflow-controller/workflow_controller/`。
  - 清理误提交的 `__pycache__`。
  - 新增 `.gitignore`。
  - 提交初始项目基线。
- 创建/修改的文件：
  - `.gitignore`
  - `workflow_controller/`
- 提交：
  - `fd27a54 Add workflow controller project`

### 阶段 4：计划与进度文件
- **状态：** complete
- 开始时间：2026-04-28 10:45 +0800
- 执行的操作：
  - 在新工作区根目录写入计划、发现、进度三份持久化上下文文件。
  - 将计划与进度文件提交到 `workflow-controller` 分支。
- 创建/修改的文件：
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

## 测试结果
| 测试 | 输入 | 预期结果 | 实际结果 | 状态 |
|------|------|---------|---------|------|
| 新工作区单元测试 | `python -m pytest workflow_controller/tests -q` | 全部通过 | `76 passed in 19.91s` | 通过 |
| Git 工作区状态 | `git status --short` | 无未提交变更 | 计划文件提交后无输出 | 通过 |
| Worktree 注册 | `git --git-dir=~/works/ai-works/.git worktree list` | 出现 `workflow-controller` | 已注册 `workflow-controller` worktree | 通过 |

## 错误日志
| 时间戳 | 错误 | 尝试次数 | 解决方案 |
|--------|------|---------|---------|
| 2026-04-28 10:31 +0800 | `git worktree add --orphan workflow-controller <path>` 参数形式错误 | 1 | 改用 `git worktree add --orphan -b workflow-controller <path>` |
| 2026-04-28 10:33 +0800 | 初始提交包含 `__pycache__` 和 `.pyc` | 1 | `git rm -r` 删除缓存文件，新增 `.gitignore`，执行 `git commit --amend --no-edit` |

## 五问重启检查
| 问题 | 答案 |
|------|------|
| 我在哪里？ | `~/works/ai-works/worktrees/workflow-controller` 的 `workflow-controller` 分支 |
| 我要去哪里？ | 后续所有 Workflow Controller 开发都在此 worktree 继续 |
| 目标是什么？ | 保留当前已修复功能，并以可测试、可提交的新工作区作为开发基线 |
| 我学到了什么？ | 见 `findings.md` |
| 我做了什么？ | 见上方阶段记录 |

---
*每个阶段完成后或遇到错误时更新此文件*
