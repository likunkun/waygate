# Waygate 工作流

[English](workflow.md) | [README](../README.zh-CN.md)

Waygate 把一个 AI 编程目标变成分阶段交付循环。Controller 驱动循环，并在需要人工审阅的 gate 暂停。

## 高层流程

```text
Requirements Draft
  -> Requirements Gate
  -> Unit Plan Draft
  -> Unit Plan Gate
  -> Builder
  -> CodeSimplifier / Refiner
  -> Reviewer
  -> Verifier
  -> Final Acceptance Gate
  -> Agent Status Sync
  -> Done
```

如果最终验收发现已批准范围内的缺陷：

```text
Final Acceptance rejection
  -> Bug Fix Gate
  -> Bug Fix Agent
  -> Regression Verifier
  -> Final Acceptance Gate
```

## Requirements 阶段

Requirements drafter 会生成 Markdown gate，包含：

- 产品目标和范围；
- 验收标准；
- verification layers；
- 需要跨步骤验证时的 Journey；
- 设计和架构可追溯；
- `## 4.9` 中的目标项目基础设施事实；
- 假设和风险。

没有支持的 `--spec` 时，drafter 第一轮仍只能在 tmux pane 中直接提出澄清问题。收到用户的具体回答后，drafter 读取项目上下文，并盘点 7 类基础设施信息：代码仓库、运行环境、调试分析、参考环境、文档、架构/交互/接口和依赖。如果事实仍缺失，继续直接追问用户。

用户补充的基础设施事实默认不能当成已验证事实。Drafter 应通过本地 repo、配置文件、README/USAGE、docs、state-dir artifact、package manifest、测试命令或既有验证输出等非破坏性来源核对。外部系统、生产环境、私有 wiki/API 或其他无法访问的事实必须标注为用户提供且未能直接验证。`## 4.8` 记录追问、用户回答、核对方式、验证结论和残余风险；`## 4.9` 记录每类基础设施事实的来源和验证状态。

人类看到 gate 之前，controller 可以先做预检。缺 AC 映射、缺 verification layer、traceability 格式错误等问题会自动打回 drafter。
预检也会拒绝 `暂无`、`不清楚` 等空泛基础设施占位、缺少依据的 `未发现` / `没有` 声明，以及 4.9 声称“用户确认”或“已验证”但 4.8 没有对应留痕的内容。

如果 Requirements 声明或隐含真实 E2E / 浏览器验收，人工批准前必须审阅 `## 4.6 E2E 测试方法与前置依赖矩阵（E2E Test Method & Prerequisite Matrix）`。该矩阵把每个 E2E AC 或 active E2E Journey 映射到测试方法、真实入口、用户步骤、fixture/setup、具体命令、环境类型、依赖、mock policy 和预期断言。Controller 会拒绝缺行、泛化命令、非真实入口、`component_mock`/核心 API mock，以及把截图或人工观察当成唯一断言的写法。

V0.6.0m 还会在 Unit Plan approval 阶段继承这些 E2E 方法要求：每个 `golden_path: true` test case 必须是 `layer=e2e`，使用 `local_real` 或 `production_readonly`，声明 `entrypoint`/`real_entrypoint`，包含具体 fixture/setup、命令和断言，并且不得 mock 核心业务 API。E2E 不等于只支持浏览器；API-only 和 service-only golden path 可以使用 pytest/API/service E2E 命令。完整规则已登记在 [docs/workflow/requirements-e2e-review-policy.md](workflow/requirements-e2e-review-policy.md)。

UI、Web、可点击原型、prototype evidence 和生产 UI 一致性工作必须使用 `ui-ux-pro-max`。`frontend-design` 可以辅助全新视觉探索或局部润色，但不能替代 `ui-ux-pro-max` 做既有产品 UI/原型一致性工作。完整 V0.6.0k policy 已登记在 [docs/workflow/ui-ux-skill-policy.md](workflow/ui-ux-skill-policy.md)。

## Unit Plan 阶段

Unit Plan 定义 implementation agent 可以做什么。它应包含：

- objective coverage；
- execution units；
- `workflow_validation_level`；
- test cases；
- Journey mapping；
- verification commands；
- `Controller State Patch` JSON 块。

Controller 会在 approval 前校验计划。无效计划不会被标记为 approved。
如果已批准 Requirements 包含 4.6 E2E 审阅细节，Unit Plan 必须继承已批准的测试方法、真实入口、fixture/setup、命令依赖、环境类型、mock policy 和断言意图；除非先通过 Requirements change request，不能在 Unit Plan 中弱化这些结论。
Unit Plan 预检自动打回时，`unitPlanAutoRevisionMax` 限制的是同一个 normalized invalid reason 的连续修订次数。不同 invalid reason 视为有效推进并重置连续计数；request event 同时记录当前 reason 的连续 `attempt` 和本轮累计 `total_attempt`。

## Implementation 阶段

Builder 会收到 prompt 文件，并只处理一个 unit。tmux 或 subprocess runner 派发 prompt，并等待完成信号。

完成信号不是最终证明。Controller 仍会校验 run ID、artifacts 和后续 verifier evidence。

如果 agent 派发后超时，或 pane 已 idle 但没有写 DONE，Waygate 会记录可恢复等待，而不是阻塞或回滚。Workflow 保持在同一阶段，`status=active`，不写 `blockedReason`，并在 `session.json` 记录 `recoverableAgentWait`；当前自动循环会停止。下一次运行 `waygate go` / `run` / `drive` / `start` 会读取该状态、记录自动恢复事件、清除等待标记，并继续同一阶段。这不是 Requirements 或 Unit Plan 合同返工，因此 `waygate revise` 仍只用于真实的 Requirements / Unit Plan rework。完整策略已登记在 [docs/workflow/recoverable-agent-timeout-policy.md](workflow/recoverable-agent-timeout-policy.md)。

如果上一轮 controller Verifier 失败于某条具体命令，下一轮 Builder prompt 会包含 `Controller Verification Failure Protocol`。Builder 第一动作必须在 controller cwd 下复跑同一条 exact command，不能先改 grep、换 cwd、拆命令或跑相邻测试。DONE 前，Builder 必须在 `done_payload.controller_failure_resolution` 记录 failed command、复现结果、root cause 或 mismatch analysis、修复摘要、同命令复跑 exit code 和完整 approved verification list 运行结果。缺少或命令不匹配会在进入 Refiner 前阻塞；最终验收事实源仍是 controller Verifier。

## 精修与评审

Builder 完成后：

1. CodeSimplifier/Refiner 可以要求清理，或返回 OK/skipped。
2. Reviewer 检查风险、缺失测试和明显回归。
3. Reviewer 发现的问题会路由回 Builder 或阻塞 workflow。

## Verification

Verifier 执行 unit 中列出的命令，并写入 `verification.json`。Evidence rows 会把命令结果映射回：

- unit IDs；
- test case IDs；
- acceptance criteria；
- acceptance obligations；
- journeys；
- artifact references。

Malformed evidence 会被当作验证失败。

重复 verifier 失败使用稳定 fingerprint：stage、issue type、command、return code，以及 Playwright test title、error class 等稳定失败特征会参与判定。stdout/stderr tail 仍保留在摘要和 artifact 中供人和 agent 排查，但不会单独让同一失败看起来像新的失败。

## Final Acceptance

Final Acceptance 展示：

- target 和 objective coverage；
- evidence matrix；
- Journey matrix；
- scope audit；
- changed files；
- rejection routing。

如果配置了 live tmux agent pane，批准后会先触发 Agent Status Sync。这个 prompt 会告知 agent 最终验收已批准，并要求它在 release 前更新 `task_plan.md`、`progress.md`、`findings.md` 等状态文档。

最终验收批准且必要的状态同步完成后，workflow 才进入 `DONE`。

## 返工路由

最终验收拒绝时，应选择最窄且正确的路由：

| 路由 | 使用场景 |
| --- | --- |
| `requirements` | 已批准需求本身错误或不完整。 |
| `unit_plan` | 计划缺覆盖、顺序、测试用例或 Journey 映射。 |
| `implementation` | Unit Plan 正确，但实现不完整或错误。 |
| `defect_fix` | 已批准范围内存在 bug，需要聚焦修复。 |
| `blocked` | 没有外部输入无法继续。 |

## 人的职责

Waygate 不移除人的判断，而是把人的判断集中在关键点：

- 确认需求符合真实意图；
- 确认 Unit Plan 有足够证据覆盖；
- 确认最终证据可信；
- 诚实地选择失败路由。

## 应检查的 artifacts

| Artifact | 作用 |
| --- | --- |
| `approvals/requirements-and-acceptance.md` | 已批准需求和验收标准。 |
| `approvals/unit-plan.md` | 已批准 unit 拆分和测试矩阵。 |
| `artifacts/*/prompt.md` | Agent 收到的精确任务 prompt。 |
| `artifacts/*/done.json` | 带 run ID 的 agent 完成信号。 |
| `artifacts/*/verification.json` | Verifier 证据和命令结果。 |
| `approvals/final-acceptance.md` | 最终验收 gate 和证据矩阵。 |
