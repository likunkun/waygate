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
- 假设和风险。

人类看到 gate 之前，controller 可以先做预检。缺 AC 映射、缺 verification layer、traceability 格式错误等问题会自动打回 drafter。

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

## Implementation 阶段

Builder 会收到 prompt 文件，并只处理一个 unit。tmux 或 subprocess runner 派发 prompt，并等待完成信号。

完成信号不是最终证明。Controller 仍会校验 run ID、artifacts 和后续 verifier evidence。

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

## Final Acceptance

Final Acceptance 展示：

- target 和 objective coverage；
- evidence matrix；
- Journey matrix；
- scope audit；
- changed files；
- rejection routing。

只有这个 gate 被批准后，workflow 才进入 `DONE`。

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
