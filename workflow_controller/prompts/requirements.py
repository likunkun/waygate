from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from workflow_controller.acceptance_obligations import render_acceptance_obligations_markdown
from workflow_controller.requirements_dialogue_brief import render_requirements_dialogue_brief_prompt_section
from workflow_controller.steps._common import _find_unit


def _markdown_code_fence_for(text: str) -> str:
    longest = 2
    for match in re.finditer(r'`{3,}', text):
        longest = max(longest, len(match.group(0)))
    return '`' * max(3, longest + 1)


def _render_requirements_draft_prompt(state: dict[str, Any], body_path: Path) -> str:
    unit = _find_unit(state, state.get('currentUnitId'))
    context_files = '\n'.join(f'- {path}' for path in state.get('targetContextFiles') or [])
    verification_commands = '\n'.join(
        f"- `{command}`" for command in (unit.get('verification_commands') or state.get('verificationCommands') or [])
    ) or '- Not specified'
    done_when = '\n'.join(f"- {item}" for item in unit.get('done_when') or []) or '- Infer from the target and context files'
    scope = '\n'.join(f"- {item}" for item in unit.get('scope') or []) or '- Infer from the target and context files'
    non_goals = '\n'.join(f"- {item}" for item in unit.get('non_goals') or []) or '- Do not expand beyond the requested target'
    obligation_ledger = render_acceptance_obligations_markdown(state)
    obligation_section = ''
    if state.get('acceptanceObligations'):
        obligation_section = f"""
Acceptance Obligation Ledger:

```md
{obligation_ledger}
```

Every must AO must be covered by at least one Acceptance Criterion, or explicitly deferred/rejected/out_of_scope with reason.
Use the Requirements Traceability Matrix to record that decision for every active must AO.
Do not collapse multiple AO items into one vague requirement.
"""
    revision_feedback = state.get('requirementsRevisionFeedback')
    revision_section = ''
    if revision_feedback:
        revision_fence = _markdown_code_fence_for(str(revision_feedback))
        revision_section = f"""
已有草案及人工批注：

{revision_fence}md
{revision_feedback}
{revision_fence}

Controller 会记录本轮 requirements revision diff artifact；请解决这些反馈，但不要复制审阅评论。
除非审阅意见本身属于最终需求内容，否则不要把审阅者评论原样带入正文。
"""
    dialogue_brief_section = render_requirements_dialogue_brief_prompt_section(state)

    return f"""为 workflow-controller 生成"需求与验收确认"Markdown 正文。

将 Markdown 正文写入这个精确文件：
{body_path}
Write the Markdown body to this exact file:
{body_path}

使用简体中文展示所有面向人工审阅的标题、说明、表格、清单、证据和验收内容。
保留命令、路径、代码标识符、JSON key、HTTP route、枚举值、文件名和产品名的原文。
不要包含 `## Human Confirmation` 段落；controller 会自动追加确认段落和内容 hash。
不要修改应用源代码；这是规划/门禁文档生成任务。
使用 `test-strategy` skill 将每条验收标准映射到适当验证层级、具体测试用例、命令、fixture、环境和人工证据。
Requirements approval 会被 controller 预检：每条 AC 必须声明 verification layer；每个 active must AO 必须映射到 AC，或显式 deferred/rejected/out_of_scope 并写明原因。
V0.3.4 还要求每条 covered AC 在 Design/Architecture Traceability Matrix 中同时映射 Product Design Ref 和 Technical Architecture Ref。

Agent-side requirements clarification:
- 写正式 Requirements Gate 前，必须先提出简洁、集中的澄清问题，并在当前 tmux agent pane 里等待用户回答。
- 等待用户回答期间不得写 `DONE_FILE`；收到用户回答后，再继续生成 Requirements Gate。
- 用户回答后，将澄清结果写入本 Requirements Gate 的 `## 4.8 已澄清事项、关键假设与待确认风险`，并同步反映到需求、范围外、验收标准和测试策略中。
- 可用保守假设推进时必须推进，并在 gate 中写明关键假设和待确认风险。
- 不要因为一般不确定性反复提问；只有没有安全假设且无法继续时，才按 runner 要求写 blocked DONE_FILE。

目标：
- 请求目标：`{state.get('requestedOutcome')}`
- 可行目标：`{state.get('feasibleOutcome')}`
- 当前单元 id：`{state.get('currentUnitId')}`
- 当前单元名称：`{unit.get('name', state.get('currentUnitId'))}`

已知范围：
{scope}

已知非目标：
{non_goals}

已知完成条件 / 验收提示：
{done_when}

已知验证命令：
{verification_commands}

如存在，请读取这些上下文文件：
{context_files or '- None'}

{dialogue_brief_section}

{obligation_section}
{revision_section}

必须使用以下 Markdown 结构：

# 需求与验收确认

## 1. 需求

## 2. 用户旅程

覆盖正常路径、异常路径、角色/权限路径、重试/恢复路径、持久化/数据路径，以及适用的导入/导出或集成路径。

## 3. 验收标准

使用可观察、可测试的标准。每条标准都要说明可证明它的证据。
每条验收标准必须有稳定 ID（如 `AC-01`、`AC-02`），并描述可观察行为；不要写“体验良好”“流程正常”等不可测试表述。
每条验收标准必须声明 verification layer：unit / functional / integration / e2e / manual，推荐格式：`- AC-01 [verification: e2e]: ...`。
涉及用户可见闭环、数据流、导入导出、列表、状态流转、权限或持久化的 AC，必须包含固定测试数据或 fixture、操作路径、可断言的期望值（如字段值、数量、排序、状态、错误文案、导出内容）。
后续 E2E 必须从这些 AC 生成测试用例，不能用截图或人工观察替代断言。

## 4. 需求可追溯矩阵（Requirements Traceability Matrix）

必须包含这个表头：

| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |

规则：
- 每个 active must AO 必须有一行。
- `covered` 行必须填写 AC ID 和 verification layer。
- 不能在一个模糊 AC 里合并多个 AO；如果多个 AO 共享同一个 AC，也要逐行列出 AO。
- 如果 AO 不进入本版本，Status 必须是 `deferred`、`rejected` 或 `out_of_scope`，并在 Evidence/Reason 写明原因。
- Status 只能使用 covered/deferred/rejected/out_of_scope。
- Verification Layer 只能使用 unit / functional / integration / e2e / manual。

## 4.5 设计与架构可追溯矩阵（Design/Architecture Traceability Matrix）

必须包含这个表头：

| AC | Product Design Ref | Technical Architecture Ref | Notes |
| --- | --- | --- | --- |

规则：
- 每条 covered AC 必须有一行。
- Product Design Ref 必须指向本文件 `## 7. 产品设计概要` 中的具体用户流程、关键页面/状态、API/CLI 输出或产品行为说明。
- Technical Architecture Ref 必须指向本文件 `## 8. 架构概要` 中的具体模块边界、数据流、外部依赖或风险说明。
- 不要使用 `TBD`、`pending`、`待补`、`无` 作为引用值；不确定时应补完整设计/架构概要，而不是让 gate 通过。
- 这一节建立 requirements 层设计/架构引用；Verifier evidence schema 会在验证阶段消费 Unit Plan test cases，并进入最终验收矩阵。

## 4.7 Journey Acceptance Matrix

必须包含这个表头：

| Journey | Title | Status | Steps | AC | Verification Layer | Verification Command | Test Case | Unit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

规则：
- 如果出现 e2e 或 workflow_validation_level=closure，必须至少一行 active Journey。
- Status 只能使用 active / deferred / rejected / out_of_scope。
- active Journey 必须填写 Journey ID、Title、Steps、AC 和 Verification Layer。
- Steps 使用 `->` 分隔关键路径步骤；AC 必须列出关联的 AC ID。
- Verification Layer 只能使用 functional / integration / e2e / manual。
- Verification Command、Test Case、Unit 如尚未由 Unit Plan 生成，可写明预期命令、预期测试用例 ID 或待 Unit Plan 映射的说明。
- 不涉及跨页面、跨模块、端到端或 closure 验收时，可以保留表头并不填写数据行。

## 4.8 已澄清事项、关键假设与待确认风险

记录 agent-side clarification 的结果：
- 已澄清事项：如 agent 在 tmux pane 中向用户提问，必须列出用户回答形成的具体决策。
- 关键假设：列出为避免打断而采用的保守假设，并说明这些假设如何影响需求和验收。
- 待确认风险：列出仍需人工在 gate 审阅时重点确认的风险；不能把阻断性缺口藏在这里。

## 5. 测试策略（Test Strategy）

按适用情况区分单元测试、功能/API 测试、集成检查和 E2E/人工验收。

## 6. 范围外

## 7. 产品设计概要

描述核心用户流程（正常路径 + 主要异常路径）、关键页面或系统状态的文字/ASCII 示意；如果没有 UI，就描述 API 响应结构、CLI 输出或关键状态变化；再补充"完成后应该长什么样"的验收示意。

## 8. 架构概要

描述参与本次变更的模块边界与职责划分、核心数据流（输入 → 处理 → 输出）、外部依赖（系统/服务/API/环境），以及主要技术风险和约束。

## 9. 人工审阅清单

使用未勾选的 Markdown checkbox。
"""
