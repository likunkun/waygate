from __future__ import annotations

from pathlib import Path
from typing import Any

from workflow_controller.acceptance_obligations import render_acceptance_obligations_markdown
from workflow_controller.steps._common import _find_unit


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
Do not collapse multiple AO items into one vague requirement.
"""
    revision_feedback = state.get('requirementsRevisionFeedback')
    revision_section = ''
    if revision_feedback:
        revision_section = f"""
已有草案及人工批注：

```md
{revision_feedback}
```

请在重新生成的 Markdown 正文中解决这些人工批注。除非审阅意见本身属于最终需求内容，否则不要把审阅者评论原样带入正文。
"""

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
涉及用户可见闭环、数据流、导入导出、列表、状态流转、权限或持久化的 AC，必须包含固定测试数据或 fixture、操作路径、可断言的期望值（如字段值、数量、排序、状态、错误文案、导出内容）。
后续 E2E 必须从这些 AC 生成测试用例，不能用截图或人工观察替代断言。

## 4. 测试策略（Test Strategy）

按适用情况区分单元测试、功能/API 测试、集成检查和 E2E/人工验收。

## 5. 范围外

## 6. 产品设计概要

描述核心用户流程（正常路径 + 主要异常路径）、关键页面或系统状态的文字/ASCII 示意；如果没有 UI，就描述 API 响应结构、CLI 输出或关键状态变化；再补充"完成后应该长什么样"的验收示意。

## 7. 架构概要

描述参与本次变更的模块边界与职责划分、核心数据流（输入 → 处理 → 输出）、外部依赖（系统/服务/API/环境），以及主要技术风险和约束。

## 8. 人工审阅清单

使用未勾选的 Markdown checkbox。
"""
