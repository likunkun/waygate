from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workflow_controller.acceptance_obligations import render_acceptance_obligations_markdown
from workflow_controller.steps._common import _find_unit


def _render_unit_plan_draft_prompt(state: dict[str, Any], requirements_path: Path, body_path: Path) -> str:
    requirements_content = ''
    if requirements_path.exists():
        requirements_content = requirements_path.read_text(encoding='utf-8')
    unit = _find_unit(state, state.get('currentUnitId'))
    context_files = '\n'.join(f'- {path}' for path in state.get('targetContextFiles') or [])
    units = json.dumps(state.get('units') or [], ensure_ascii=False, indent=2)
    coverage = json.dumps(state.get('objectiveCoverage') or [], ensure_ascii=False, indent=2)
    obligation_ledger = render_acceptance_obligations_markdown(state)
    obligation_section = ''
    if state.get('acceptanceObligations'):
        obligation_section = f"""
Acceptance Obligation Ledger:

```md
{obligation_ledger}
```

Acceptance Obligation Coverage:
- Every must AO must appear in the Unit Plan coverage matrix.
- Each covered AO must map to at least one test case or manual evidence.
- Do not collapse multiple AO items into one vague closure.
- Keep AO ids such as `AO-001` in Test Case Matrix rows and in `test_cases[].covers_obligations`.
"""
    revision_feedback = state.get('unitPlanRevisionFeedback')
    revision_section = ''
    if revision_feedback:
        revision_section = f"""
已有 Unit Plan 草案及人工批注：

```md
{revision_feedback}
```

请在重新生成的 Markdown 正文中解决这些人工批注。保持 `Controller State Patch` 与人工可读的 Unit Plan 章节一致。
"""
    defect_fix_section = ''
    if state.get('unitPlanRevisionMode') == 'defect_fix' or state.get('finalAcceptanceRejectionRoute') == 'defect_fix':
        defect_fix_section = """
最终验收缺陷修复模式：
- 将最终验收反馈视为已批准需求下的缺陷。
- 不要修改已批准需求，也不要重新解释请求目标。
- 生成一个或多个只聚焦最终验收缺陷的 bug-fix 单元。
- 将受影响的已覆盖目标重新打开为 `partial`，并在 objectiveCoverage 中加入新的 bug-fix unit id。
- 除非必须重新执行，否则已完成单元不要放回 `units`；`units` 应只包含下一步要执行的缺陷修复单元。
- 将 `currentUnitId` 设置为第一个缺陷修复单元。
"""

    return f"""为 workflow-controller 生成"单元计划确认"Markdown 正文。

将 Unit Plan Markdown 正文写入这个精确文件：
{body_path}
Write the Unit Plan Markdown body to this exact file:
{body_path}

使用简体中文展示所有面向人工审阅的标题、说明、表格、清单、证据和验收内容。
保留命令、路径、代码标识符、JSON key、HTTP route、枚举值、文件名和产品名的原文。
控制器状态补丁标题可使用 `## 控制器状态补丁` 或 `## Controller State Patch`，正文必须包含 fenced JSON patch。
不要包含 `## Human Confirmation` 段落；controller 会自动追加确认段落和内容 hash。
不要修改应用源代码；这是规划/门禁文档生成任务。
使用 `test-strategy` skill 将每条验收标准映射到适当验证层级、具体测试用例、命令、fixture、环境和人工证据。

E2E 单元约束（`workflow_validation_level: closure` 的单元必须遵守）：
- 测试用例矩阵必须以 AC 为主键；每个 test case 必须包含 `id`、`acceptance_criterion`、`layer`、`fixture` 或测试数据准备方式、`command`、`expected`。
- 至少一个 E2E test case 必须标记 `golden_path: true`，表示人工最终验收前必须先跑通的核心正常流程。
- `verification_commands` 必须是可执行的测试命令（如 `playwright test` / `pytest`），并包含实际执行这些 E2E 测试和 golden path 的命令；不接受"截图留证"或人工步骤作为完成条件。
- `done_when` 必须是"测试命令退出码为 0 且断言覆盖 AC"，不接受"截图已上传"、"人工确认"或"浏览器路径已验证"。
- 每个测试用例必须追溯到一条 AC，并在 `expected` 字段中描述可断言的具体值（如字段值、数组长度、排序关系），不接受"页面正常渲染"、"无报错"或"截图留存"作为唯一断言。
- 对不适合 E2E 的 AC，必须说明为什么降级到 unit/functional/integration，并保留可执行命令。
- 使用 `webapp-testing` skill 生成带真实数据断言的 Playwright 测试文件，而不是人工操作步骤清单。

以下已批准需求与验收门禁是事实来源：

```md
{requirements_content}
```

目标：
- 请求目标：`{state.get('requestedOutcome')}`
- 可行目标：`{state.get('feasibleOutcome')}`
- 当前单元 id：`{state.get('currentUnitId')}`
- 当前单元名称：`{unit.get('name', state.get('currentUnitId'))}`

controller state 中的已知目标覆盖：

```json
{coverage}
```

controller state 中的已知单元：

```json
{units}
```

如存在，请读取这些上下文文件：
{context_files or '- None'}

{obligation_section}
{revision_section}
{defect_fix_section}

必须使用以下 Markdown 结构：

# 单元计划确认（Unit Plan Confirmation）

## 目标覆盖矩阵

将每条需求和验收标准映射到一个或多个单元。

## 测试用例矩阵（Test Case Matrix）

创建一张表，表达以下精确映射：

Acceptance Criterion -> Test Case -> Layer -> Command/Evidence -> Expected Result

缺陷修复模式下，每条验收标准和每个最终验收缺陷都必须至少有一个具体测试用例或明确人工证据。typecheck/lint/tsc 等静态检查可以出现，但不能单独算作行为覆盖。
E2E 层的测试用例必须有可执行 `command`（Playwright/pytest 命令），并声明 `fixture` 或测试数据准备方式；`evidence` 字段留空；`expected` 必须描述具体可断言的值，不接受"页面渲染成功"、"无报错"或"截图留存"。

## 执行单元

每个单元必须包含：
- 范围
- 非目标
- 覆盖目标
- 覆盖验收标准
- 影响的工作流片段
- 工作流验证层级：`fragment` 或 `closure`
- 完成条件
- 映射到测试用例矩阵的测试用例
- 验证命令
- 命令依赖的验证环境，例如 Playwright/E2E 数据库测试需要的 `DATABASE_URL`
- 所需证据
- 风险

## 控制器状态补丁

包含一个 fenced `json` 对象，controller 会在人工批准后安全应用：

```json
{{
  "currentUnitId": "<first unit to execute>",
  "objectiveCoverage": [
    {{"objective": "<objective>", "units": ["<unit-id>"], "status": "partial"}}
  ],
  "units": [
    {{
      "id": "<unit-id>",
      "name": "<unit name>",
      "passes": false,
      "scope": ["<scope item>"],
      "non_goals": ["<non-goal item>"],
      "done_when": ["<observable completion condition>"],
      "workflow_validation_level": "fragment",
      "test_cases": [
        {{
          "id": "<stable test case id>",
          "acceptance_criterion": "<criterion or defect covered>",
          "layer": "unit|functional|integration|e2e|manual",
          "golden_path": true,
          "fixture": "<test data or setup path for runtime tests>",
          "command": "<verification command if automated>",
          "evidence": "<manual evidence if not automated>",
          "expected": "<observable expected result>"
        }}
      ],
      "verification_commands": ["<command>"],
      "verification_env": {{"DATABASE_URL": "<test database url if required>"}}
    }}
  ],
  "currentUnitNeedsUiDesign": false
}}
```

JSON 必须合法，且 `units` 必须列出下一步要执行的每个可执行单元。
每个未完成的 `partial` objectiveCoverage unit id 都必须存在于 `units`。
已完成的既有 unit id 如果在 objectiveCoverage 中标记为 `covered`，可以不出现在 `units` 中；这用于同时引用已完成和剩余工作的 rollup objective。
除非必须重新执行，否则不要把已经 covered 的历史单元重新加入 `units`。
如果用更小的可执行单元替换合成 target unit，请从 partial objectiveCoverage 中移除合成 target unit id，或将该 objective 映射到新的可执行 unit id。

## 人工审阅清单

使用未勾选的 Markdown checkbox。
"""


def _render_test_strategist_prompt(
    *,
    state: dict[str, Any],
    requirements_path: Path,
    unit_plan_body_path: Path,
    draft_dir: Path,
) -> str:
    requirements_content = requirements_path.read_text(encoding='utf-8') if requirements_path.exists() else ''
    unit = _find_unit(state, state.get('currentUnitId'))
    unit_plan_body = unit_plan_body_path.read_text(encoding='utf-8') if unit_plan_body_path.exists() else ''
    return f"""Create Test Strategist artifacts for the workflow-controller Unit Plan draft.

Write these exact artifacts in this directory:
{draft_dir}

Required files:
- test-strategy.json
- test-strategy.md
- unit-plan-gap-report.json
- unit-plan-review-package.json

Use the requirements context, Unit Plan body target path, target context, constraints, and verification requirements below.
Validate every acceptance criterion has at least one concrete behavioral test case or manual evidence.
Reject static-only strategy coverage by reporting a Critical gap.
Do not modify source code.

CRITICAL: test-strategy.json MUST use this exact top-level schema or the controller will reject it:
{{
  "acceptance_criteria": [
    {{
      "id": "AC-X-Y",
      "test_cases": [
        {{
          "id": "TC-X-Y-a",
          "layer": "unit|functional|integration|e2e|manual",
          "command": "the exact shell command to run",
          "evidence": "manual evidence description (use instead of command for manual cases)",
          "expected": "expected result"
        }}
      ]
    }}
  ]
}}
The top-level key must be "acceptance_criteria" (a list). Each entry must have "id" and "test_cases" (a non-empty list). Each test case must have either "command" or "evidence". Do not rename these keys or wrap them in another structure.

Requirements context:

```md
{requirements_content}
```

Unit Plan body path:
{unit_plan_body_path}

Unit Plan body:

```md
{unit_plan_body}
```

Target context:
- requestedOutcome: {state.get('requestedOutcome')}
- feasibleOutcome: {state.get('feasibleOutcome')}
- currentUnitId: {state.get('currentUnitId')}
- currentUnit: {json.dumps(unit, ensure_ascii=False, indent=2)}
- objectiveCoverage: {json.dumps(state.get('objectiveCoverage') or [], ensure_ascii=False, indent=2)}
- targetContextFiles: {json.dumps(state.get('targetContextFiles') or [], ensure_ascii=False, indent=2)}

Constraints:
- Keep planner and strategist outputs independent.
- Static checks such as lint, typecheck, eslint, prettier, biome, or tsc cannot be the only coverage for an acceptance criterion.
- Prefer user-visible or behavior-visible verification when the requirement has observable runtime behavior.
- For E2E or closure coverage, derive test cases directly from AC IDs and include executable commands plus concrete assertions over real fixture data.
- Do not use screenshots, page-load checks, or manual observation as the only E2E evidence.

verification requirements:
- Include test case id, acceptance criterion, layer, fixture or setup data, command or evidence, and expected result.
- Include gap severity as Critical, Major, or Minor.
- For every gap, include a "suggested_fix" field with a concrete, actionable instruction for the Planner: specify which AC needs what kind of test, what layer (unit/integration/e2e/manual), and an example command or evidence format.
- Summarize review readiness in unit-plan-review-package.json.
"""


def _render_test_strategist_patch_prompt(
    *,
    state: dict[str, Any],
    draft_dir: Path,
    gap_report: dict[str, Any],
) -> str:
    strategy_path = draft_dir / 'test-strategy.json'
    strategy_content = strategy_path.read_text(encoding='utf-8') if strategy_path.exists() else '{}'
    return f"""你是 Test Strategist。初始测试策略存在以下空缺，请直接填补，不要发送反馈。

当前 test-strategy.json 路径：
{strategy_path}

当前 test-strategy.json 内容：
```json
{strategy_content}
```

需要修复的空缺（gap report）：
```json
{json.dumps(gap_report, ensure_ascii=False, indent=2)}
```

操作要求：
1. 对每个 gap，在对应 acceptance_criteria 条目中添加或补全 test_cases。
2. 对每个你【新增或修改】以填补空缺的 test_case，在该对象上加 `"codex_patch": true`。
3. 将完整更新后的 test-strategy.json 写回：{strategy_path}
4. 对原本已有效的 test_case，不要加 `"codex_patch"` 标记。
5. 如果某条 AC 描述过于模糊，你无法生成有意义的测试用例，则保持该 gap 条目不变。
6. 不要修改 unit-plan-gap-report.json 或其他任何文件。
7. 不要修改源代码。

已修补的 test_case 示例结构：
{{
  "id": "TC-X-Y-a",
  "layer": "unit|functional|integration|e2e|manual",
  "command": "具体的 shell 命令",
  "expected": "预期结果",
  "codex_patch": true
}}
"""


def _gap_identifier(gap: dict[str, Any]) -> str:
    return str(gap.get('id') or gap.get('type') or gap.get('message') or 'unknown-critical-gap')


def _render_codex_patch_summary(draft_dir: Path, strategy: dict[str, Any]) -> str:
    patched: list[tuple[str, dict[str, Any]]] = []
    for ac in strategy.get('acceptance_criteria') or []:
        ac_id = ac.get('id') or '?'
        for tc in ac.get('test_cases') or []:
            if tc.get('codex_patch'):
                patched.append((ac_id, tc))
    if not patched:
        return ''
    lines = [
        '',
        '## 📝 Codex Test Strategist 自动补充',
        '',
        '以下测试用例由 Codex 自动填补策略空缺，请确认合理性（不影响后续执行）：',
        '',
    ]
    for ac_id, tc in patched:
        tc_id = tc.get('id') or '?'
        layer = tc.get('layer') or '?'
        cmd = tc.get('command') or tc.get('evidence') or '(no command)'
        expected = tc.get('expected') or ''
        lines.append(f'- **{tc_id}** (AC: {ac_id} · {layer})')
        lines.append(f'  - 命令/证据: `{cmd}`')
        if expected:
            lines.append(f'  - 预期: {expected}')
    return '\n'.join(lines)


def _render_critical_gap_escalation(gaps: list[dict[str, Any]], gap_report: dict[str, Any], *, retry_count: int) -> str:
    lines = [
        '## ⚠️ Unresolved Critical Test Strategy Gaps — Human Review Required',
        '',
        f'Automatic retry exhausted after {retry_count} attempt(s). The following Critical gaps remain unresolved.',
        'Please review, annotate this gate with concrete fixes, and trigger a revision (r).',
        '',
    ]
    for gap in gaps:
        gap_id = _gap_identifier(gap)
        message = str(gap.get('message') or gap.get('type') or 'No detail provided')
        criterion = gap.get('acceptance_criterion') or gap.get('acceptanceCriterion') or gap.get('criterion')
        suffix = f" (AC: {criterion})" if criterion else ''
        lines.append(f'- `Critical` `{gap_id}`{suffix}: {message}')
        fix = gap.get('suggested_fix')
        if fix:
            lines.append(f'  - Suggested fix: {fix}')
    lines.append('')
    return '\n'.join(lines)


def _render_test_strategy_gap_report(gaps: list[dict[str, Any]], gap_report: dict[str, Any], *, retry_count: int) -> str:
    counts = gap_report.get('gap_counts') if isinstance(gap_report.get('gap_counts'), dict) else _gap_counts_from_list(gaps)
    lines = [
        '## Test Strategy Gap Report',
        '',
        f"- Critical: {int(counts.get('critical') or 0)}",
        f"- Major: {int(counts.get('major') or 0)}",
        f"- Minor: {int(counts.get('minor') or 0)}",
        f'- Planner retry count: {retry_count}',
        '',
    ]
    for gap in gaps:
        gap_id = _gap_identifier(gap)
        severity = str(gap.get('severity') or 'Unknown')
        message = str(gap.get('message') or gap.get('type') or 'No detail provided')
        criterion = gap.get('acceptance_criterion') or gap.get('acceptanceCriterion') or gap.get('criterion')
        suffix = f" (AC: {criterion})" if criterion else ''
        lines.append(f'- `{severity}` `{gap_id}`{suffix}: {message}')
        fix = gap.get('suggested_fix')
        if fix:
            lines.append(f'  - Suggested fix: {fix}')
    lines.append('')
    return '\n'.join(lines)


def _render_critical_gap_feedback(gaps: list[dict[str, Any]], next_retry_count: int) -> str:
    lines = [
        '## Critical Test Strategy Gap Feedback',
        '',
        f'Planner retry count after this revision: {next_retry_count}',
        '',
        'Resolve these Critical gaps before the Unit Plan can enter human approval:',
    ]
    for gap in gaps:
        criterion = gap.get('acceptance_criterion') or gap.get('acceptanceCriterion') or gap.get('criterion')
        suffix = f" (AC: {criterion})" if criterion else ''
        lines.append(f"- {_gap_identifier(gap)}{suffix}: {gap.get('message') or gap.get('type') or 'Critical gap'}")
        fix = gap.get('suggested_fix')
        if fix:
            lines.append(f"  Suggested fix: {fix}")
    lines.append('')
    return '\n'.join(lines)


def _gap_counts_from_list(gaps: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {'critical': 0, 'major': 0, 'minor': 0}
    for gap in gaps:
        severity = str(gap.get('severity') or '').lower()
        if severity in counts:
            counts[severity] += 1
    return counts
