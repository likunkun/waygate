# Waygate 架构

[English](architecture.md) | [README](../README.zh-CN.md)

Waygate 的核心边界很简单：agent 负责产出，controller 负责工作流状态、gate、路由和完成证据。

## 核心原则

1. **状态是事实源。** 聊天总结不是完成证据。
2. **关键 gate 由人批准。** Requirements、Unit Plan、Bug Fix 和 Final Acceptance 都是 Markdown 审阅点。
3. **实现按 unit 推进。** Controller 一次只推进一个 unit。
4. **证据结构化。** Verifier 结果要映射回 AC 和 Test Case。
5. **失败要明确路由。** 缺陷可以回 requirements、unit planning、implementation、bug-fix 或 blocked。

## 包结构

```text
workflow_controller/
  cli.py
  rrc_controller.py
  acceptance_obligations.py
  journeys.py
  requirements_dialogue_brief.py
  scope_audit.py

  gates/
    generators/
    parsers/
    validators/

  prompts/
    requirements.py
    unit_plan.py
    builder.py
    bug_fix.py

  runners/
    base.py
    codex.py
    tmux_claude.py
    opencode.py

  state_machine/
    actions.py
    store.py
    transitions.py

  steps/
    requirements.py
    unit_plan.py
    builder.py
    bug_fix.py

  tests/
```

## 运行状态

每个 target 都有自己的 state 目录，通常是：

```text
<target-project>/.rrc-controller-v1.0/
```

关键文件：

| 路径 | 用途 |
| --- | --- |
| `session.json` | 当前 workflow state。 |
| `events.jsonl` | 追加式事件历史。 |
| `change_requests.jsonl` | 需求和验收变更 ledger。 |
| `approvals/*.md` | 人工 gate 审阅文件。 |
| `artifacts/` | Prompt、runner 输出、验证证据、审计结果。 |

State 目录是本地运行数据，不应提交。

## Controller 层

`rrc_controller.py` 是主编排层，负责：

- 初始化和已有 session 兼容性检查；
- 状态转移和 next allowed actions；
- 人工 gate 的生成、批准、拒绝和返工；
- runner 选择和 tmux target 解析；
- builder、refiner、reviewer、verifier 和 final acceptance 路由；
- scope audit 和 evidence 校验。

Controller 是完成判定的权威。Agent 可以通过写 `done.json` 请求完成，但 controller 仍会校验 run ID、reviewer/verifier artifacts、gate 状态和 evidence。

## Gate 层

`gates/` 分成三层：

| 层 | 职责 |
| --- | --- |
| `generators` | 渲染人类可读的 Markdown gate。 |
| `parsers` | 解析确认状态、state patch 和审阅输入。 |
| `validators` | 校验 traceability、test presence、Journey 映射和 gate 质量。 |

Markdown 是人类审阅视图。路线图会逐步把结构化契约提升为一等事实源，同时保留 Markdown 作为 review surface。

## Runner 层

Runner 执行 agent 工作，并返回 metadata 和 artifacts。

当前 runner：

- `subprocess`：运行本地命令。
- `tmux-claude`：把 prompt 派发到 Claude Code tmux pane。
- `tmux-codex`：把 prompt 派发到 Codex tmux pane。
- `opencode`：未来一等 runner 的占位。

tmux runner 使用 prompt 文件和 `DONE_FILE` JSON 完成信号。Controller 会校验 `run_id`，避免上一轮残留信号串线。

## Evidence 层

Verifier 输出写入 `verification.json`。现代 verifier artifact 包含：

- schema version；
- 命令结果；
- evidence rows；
- acceptance criterion IDs；
- test case IDs；
- journey IDs；
- artifact refs。

Final Acceptance 使用这些证据渲染矩阵，而不是依赖自由文本 summary。

## 人工审阅模型

Waygate 有四类主要人工 gate：

| Gate | 目的 |
| --- | --- |
| Requirements | 确认范围、AC、设计/架构引用和 Journey。 |
| Unit Plan | 确认 unit 拆分、测试用例、验证命令和 state patch。 |
| Bug Fix | 确认缺陷范围、预期行为、实际行为、根因和回归证据。 |
| Final Acceptance | 确认证据、Journey 覆盖、scope audit 和返工路由。 |

Plannotator 可以作为浏览器辅助审阅界面，但 canonical gate 文件仍在 `approvals/`。

## 安全与数据处理

Waygate 为了可复现性会记录环境变量 key，但不应把 secret value 写入 artifact。当前实现已经包含 runner stdout/stderr redaction 和 metadata 规则，后续会补强 file/tool policy。

不要发布本地 state 目录。它们可能包含项目相关 prompt、生成 artifact 和审阅上下文。
