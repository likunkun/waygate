# Recoverable Wait Go Resume Design

日期：2026-05-26

## 背景

Waygate 当前把 agent `timeout` 和 `agent_idle_without_done` 记录为 `recoverableAgentWait`，并要求操作者执行 `waygate retry` 后才继续同一阶段。这个设计能保护 Requirements、Unit Plan 和 Final Acceptance approval 不被误清除，但恢复入口过多：用户已经通过 `waygate go` 表达“继续推进 workflow”，不应再理解一个独立的 retry 命令。

本设计将公开恢复入口收敛到 `go/run/drive/start`：超时退出后，下一次运行读取 `session.json`，消费 `recoverableAgentWait`，继续同一阶段。

## 目标

- 移除用户可见的 `waygate retry` 入口。
- `go/run/drive/start` 自动恢复 timeout/idle 形成的 `recoverableAgentWait`。
- 保留 `recoverableAgentWait` 作为上次停止原因的审计记录，直到下一次运行消费它。
- 保持显式 `blocked` 的严格边界：`go` 不自动清除 blocked；环境类仍走 `unblock`，合同类仍走 `revise`。
- 更新终端 guidance 和正式文档，避免继续提示 `retry`。

## 非目标

- 不改变 Requirements、Unit Plan、Final Acceptance 的 approval 语义。
- 不让 `go` 自动解除 `status=blocked`。
- 不把 Unit Plan / Requirements 合同问题归类为 recoverable wait。
- 不改变 runner 对 timeout/idle 的判定来源。

## 行为设计

当某阶段 runner 返回 `timeout` 或 `agent_idle_without_done` 时，controller 继续写入：

- `status=active`
- `blockedReason=null`
- `recoverableAgentWait={stage, runner_status, action, summary_path, run_dir, done_path}`
- `agent_wait_recoverable` event

终端停止提示改为：本次 agent 未完成；下次运行 `waygate go --state-dir <dir>` 继续同一 workflow。提示不能再出现 `waygate retry`。

下一次 `go/run/drive/start` 进入 controller 时：

1. 读取当前 `session.json`。
2. 如果存在 `recoverableAgentWait`，记录 `agent_wait_auto_resumed` event。
3. 清除 `recoverableAgentWait`，保持 approvals、artifacts、current step、unit id 和已批准 gate 不变。
4. 重新计算当前阶段 next action，并继续执行。
5. 如果同一次运行再次 timeout/idle，重新写入新的 `recoverableAgentWait` 并停止，避免单次命令内无限重试。

## Blocked 边界

`status=blocked` 仍是显式阻塞，不由 `go` 自动清除。

- 环境、外部依赖和 annotation runtime 修复后，继续使用 `waygate unblock --state-dir <dir> --reason "<fixed condition>"`。
- Unit Plan 合同问题继续使用 `waygate revise --gate unit-plan --state-dir <dir> --reason "..."`。
- Requirements 合同问题继续使用 `waygate revise --gate requirements --state-dir <dir> --reason "..."`。
- Final Acceptance 的非环境返工继续由 rejection route 控制。

## 组件影响

- CLI：删除 `retry` 子命令和相关 help。
- Controller：新增或调整启动时的 recoverable wait 自动消费逻辑。
- Stop guidance：recoverable wait 提示改为 `go`，blocked 提示保持 `unblock` / `revise`。
- Tests：更新 retry 相关用例为 go 自动恢复用例，并新增 CLI 不再接受 retry 的断言。
- Docs：更新 recoverable timeout policy、stop guidance policy、workflow overview、USAGE。

## 测试策略

必须覆盖：

- Requirements drafter timeout 后写入 `recoverableAgentWait`，且提示 `go`。
- Builder timeout 后下一次 `go/run/drive/start` 自动清除 wait 并继续同一阶段。
- 自动恢复不改变 requirements approval、unit plan approval、final acceptance approval hash。
- 同一次运行再次 timeout/idle 时重新停止，不发生无限循环。
- `status=blocked` 不会被 `go` 自动清除。
- CLI `retry` 不再作为合法子命令。
- 文档和终端 guidance 中不再出现 `waygate retry` 作为恢复命令。

## 实施计划

1. 先同步 GitHub main：`git pull --ff-only github main`。
2. 修改 controller，使 `go/run/drive/start` 自动消费已有 `recoverableAgentWait`。
3. 删除 CLI `retry` 子命令和 `retry_recoverable_agent_wait()` 公共入口，或将内部逻辑改名为自动恢复 helper。
4. 更新 stop guidance，recoverable wait 只提示 `go`。
5. 保持 `unblock` / `revise` 的 blocked 边界不变。
6. 更新测试并跑 focused regression。
7. 更新正式文档和 docs registry。
8. 跑标准回归：`python3 -m pytest workflow_controller/tests -q`。

## 审计事件

新增或调整事件：

- `agent_wait_auto_resumed`：由下一次 `go/run/drive/start` 自动消费 recoverable wait 时写入。
- 保留 `agent_wait_recoverable`：记录 timeout/idle 停止事实。

旧的 `agent_wait_retry_requested` 不再作为用户动作事件产生。
