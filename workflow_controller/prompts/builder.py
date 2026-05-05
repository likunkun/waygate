from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workflow_controller.steps._common import (
    _find_unit,
    _find_objective_for_unit,
    _read_json_object,
    _tail_text,
)


def _render_builder_execution_prompt(
    *,
    state: dict[str, Any],
    requirements_path: Path,
    requirements_content: str,
    unit_plan_path: Path,
    unit_plan_content: str,
    original_prompt_path: Path,
    original_prompt: str,
    previous_failure_feedback: str,
) -> str:
    unit = _find_unit(state, state.get('currentUnitId'))
    coverage = [
        item
        for item in state.get('objectiveCoverage') or []
        if state.get('currentUnitId') in (item.get('units') or [])
    ]
    final_rejection_feedback = state.get('finalAcceptanceRejectionFeedback')
    final_rejection_route = state.get('finalAcceptanceRejectionRoute')
    final_rejection_section = ''
    if final_rejection_feedback and final_rejection_route in {None, 'implementation', 'defect_fix'}:
        if final_rejection_route == 'defect_fix':
            heading = 'Final acceptance defect-fix feedback from the previous attempt'
            route_instruction = (
                '\nThis is an approved defect-fix unit generated from final acceptance. '
                'Fix only the defects in this unit scope and the feedback below; do not treat this as a requirements change.\n'
            )
        else:
            heading = 'Final acceptance rejection feedback from the previous attempt'
            route_instruction = ''
        final_rejection_section = f"""
{heading}:

```md
{final_rejection_feedback}
```
{route_instruction}
"""
    previous_failure_section = ''
    if previous_failure_feedback:
        previous_failure_section = f"""
Previous controller failure feedback:

The controller rejected the previous attempt after running its own checks. Treat this as primary debugging context.
The controller will rerun the approved verification commands exactly; do not mark DONE only because a manually modified command passed.

{previous_failure_feedback}
"""
    return f"""You are executing one approved workflow-controller unit.

Use the approved human gate documents as the source of truth. Do not expand scope beyond them.
If the approved requirements, Unit Plan, or current workspace make the task impossible, stop and report BLOCKED with the exact missing decision.

Execution workspace: {state.get('executionWorkspacePath') or state.get('workspacePath')}
Task id: {state.get('task_id')}
Current unit id: {state.get('currentUnitId')}
Requested outcome: {state.get('requestedOutcome')}

Current unit from approved Controller State Patch:

```json
{json.dumps(unit, ensure_ascii=False, indent=2)}
```

Objectives covered by this unit:

```json
{json.dumps(coverage, ensure_ascii=False, indent=2)}
```

Approved requirements gate: {requirements_path}

```md
{requirements_content}
```

Approved unit plan gate: {unit_plan_path}

```md
{unit_plan_content}
```

Original target prompt/context: {original_prompt_path}

```md
{original_prompt}
```
{final_rejection_section}
{previous_failure_section}

Builder rules:
- Implement the shortest verifiable path for the current unit only.
- Follow the Unit Plan scope, non-goals, done_when, and verification_commands.
- 先读取 Unit Plan Test Case Matrix；在实现功能前，创建或更新 command 指向的测试文件。
- 优先创建并跑通标记为 `golden_path: true` 的测试；这是交给人工最终验收前必须先通过的核心正常流程。
- Treat the main goal as making the AC-mapped tests pass, not merely producing implementation changes.
- For defect-fix units, add a regression test for each defect when feasible; if not feasible, leave explicit manual evidence.
- Preserve already accepted work.
- Leave clear evidence for the verifier.

E2E unit rules (applies when workflow_validation_level is "closure"):
- Use the `webapp-testing` skill to generate Playwright test files with real data assertions.
- Use the real application entrypoint and real fixture/setup data from the test case; do not replace runtime behavior with mocked UI-only checks unless the Unit Plan explicitly scopes it that way.
- Every test function must map to one AC and assert the specific value described in that AC's `expected` field (e.g. array ordering, field values, counts, status changes, error text, exported content) — not just that the page renders, a button exists, there is no console error, or the response is 200.
- `verification_commands` must run the Playwright test suite (e.g. `npx playwright test`); the unit is done only when this command exits 0.
- 如果数据准备、服务启动或验证命令无法运行，写 BLOCKED 并说明精确阻塞原因；不要伪造通过证据，也不要用截图结论标记 done。
- Do not use screenshots as the sole acceptance evidence. Screenshots may supplement but cannot replace programmatic assertions.
- 完成 summary 必须说明覆盖了哪些 AC、创建或修改了哪些测试文件、实际运行了哪些 verification commands。
"""


def _render_ui_design_brief(payload: dict[str, Any]) -> str:
    scope = '\n'.join(f"- {item}" for item in payload.get('scope') or []) or '- Not specified'
    non_goals = '\n'.join(f"- {item}" for item in payload.get('non_goals') or []) or '- Not specified'
    checks = '\n'.join(f"- {item}" for item in payload.get('design_checks') or [])
    return f"""# UI Design Brief

Unit: `{payload.get('unit_id')}` - {payload.get('unit_name')}
Requested outcome: `{payload.get('requested_outcome')}`
Objective: {payload.get('objective') or 'Not specified'}

## Scope
{scope}

## Non-goals
{non_goals}

## Design Checks
{checks}
"""


def _render_previous_controller_failure_feedback(unit_dir: Path) -> str:
    sections: list[str] = []

    review = _read_json_object(unit_dir / 'review.json')
    if review and review.get('passed') is False:
        sections.append(_format_failed_review_feedback(review))

    verification = _read_json_object(unit_dir / 'verification.json')
    if verification and verification.get('passed') is False:
        sections.append(_format_failed_verification_feedback(verification))

    simplifier = _read_json_object(unit_dir / 'simplifier-result.json')
    if simplifier and simplifier.get('status') in {'changes_requested', 'failed'}:
        sections.append(_format_simplifier_feedback(simplifier))

    return '\n\n'.join(section for section in sections if section)


def _format_failed_review_feedback(review: dict[str, Any]) -> str:
    issues = review.get('issues') or []
    issue_lines = '\n'.join(
        f"- {issue.get('severity', 'unknown')} {issue.get('type', 'issue')}: {issue.get('message', '')}"
        for issue in issues
        if isinstance(issue, dict)
    )
    if not issue_lines:
        issue_lines = '- Review failed without structured issues.'
    return f"""## Previous review failure

Issues:
{issue_lines}"""


def _format_failed_verification_feedback(verification: dict[str, Any]) -> str:
    issues = verification.get('issues') or []
    issue_lines = '\n'.join(
        f"- {issue.get('severity', 'unknown')} {issue.get('type', 'issue')}: {issue.get('message', '')}"
        for issue in issues
        if isinstance(issue, dict)
    )
    if not issue_lines:
        issue_lines = '- Verification failed without structured issues.'

    results = [
        result for result in verification.get('results') or []
        if isinstance(result, dict) and not result.get('ok')
    ]
    result_blocks = '\n\n'.join(_format_failed_command_result(result) for result in results[:3])
    if len(results) > 3:
        result_blocks += f'\n\n... {len(results) - 3} additional failed command result(s) omitted.'
    if not result_blocks:
        result_blocks = 'No failed command result payload was recorded.'

    return f"""## Previous verification failure

Issues:
{issue_lines}

Failed command results:
{result_blocks}"""


def _format_simplifier_feedback(simplifier: dict[str, Any]) -> str:
    findings = simplifier.get('findings') or []
    finding_lines = '\n'.join(
        f"- {finding.get('severity', 'unknown')} {finding.get('type', 'finding')}: {finding.get('message', '')}"
        for finding in findings
        if isinstance(finding, dict)
    )
    if not finding_lines:
        finding_lines = '- CodeSimplifier returned no structured findings.'

    changed_files = '\n'.join(
        f"- {path}"
        for path in simplifier.get('changed_files') or []
        if str(path).strip()
    )
    if not changed_files:
        changed_files = '- No changed files reported.'

    stdout = _tail_text(str(simplifier.get('stdout') or '').strip())
    stderr = _tail_text(str(simplifier.get('stderr') or '').strip())
    output_blocks = []
    if stdout:
        output_blocks.append(f"stdout tail:\n```text\n{stdout}\n```")
    if stderr:
        output_blocks.append(f"stderr tail:\n```text\n{stderr}\n```")
    output_text = '\n\n'.join(output_blocks) or 'No runner output recorded.'

    return f"""## Previous CodeSimplifier feedback

Status: {simplifier.get('status')}

Changed files:
{changed_files}

Findings:
{finding_lines}

Runner output:
{output_text}"""


def _format_failed_command_result(result: dict[str, Any]) -> str:
    lines = [
        f"- command: {result.get('command', '')}",
        f"- returncode: {result.get('returncode')}",
    ]
    stdout = _tail_text(str(result.get('stdout') or '').strip())
    stderr = _tail_text(str(result.get('stderr') or '').strip())
    if stdout:
        lines.append(f"- stdout tail:\n```text\n{stdout}\n```")
    if stderr:
        lines.append(f"- stderr tail:\n```text\n{stderr}\n```")
    return '\n'.join(lines)
