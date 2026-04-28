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

### 当前未提交变更
- **状态：** pending
- `workflow_controller/rrc_controller.py`
- `workflow_controller/rrc_human_gates.py`
- `workflow_controller/rrc_steps.py`
- `workflow_controller/rrc_validators.py`
- `workflow_controller/tests/test_rrc_controller.py`
- `workflow_controller/tests/test_rrc_human_gates.py`
- `task_plan.md`
- `findings.md`
- `progress.md`

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
