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
- 读取 Unit Plan Document Deliverables Matrix；`Required For Acceptance = true` 的文档动作必须在本 unit 中落到对应 `docs/*` 或登记入口，纯代码小修则保持 Unit Plan 中的“不需要正式文档变更”说明。
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


def _render_previous_controller_failure_feedback(unit_dir: Path, *, state: dict[str, Any] | None = None) -> str:
    sections: list[str] = []

    protocol = _render_controller_verification_failure_protocol(unit_dir, state=state)
    if protocol:
        sections.append(protocol)

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


def _render_controller_verification_failure_protocol(
    unit_dir: Path,
    *,
    state: dict[str, Any] | None,
) -> str:
    if not isinstance(state, dict):
        return ''
    last_failure = state.get('lastFailure')
    if not isinstance(last_failure, dict) or last_failure.get('stage') != 'VERIFY_UNIT':
        return ''
    details = last_failure.get('details') if isinstance(last_failure.get('details'), dict) else {}
    failed_command = str(details.get('command') or '').strip()
    verification_path = unit_dir / 'verification.json'
    verification = _read_json_object(verification_path) or {}
    failed_result, failed_index = _matching_failed_verification_result(verification, failed_command)
    if not failed_command and failed_result:
        failed_command = str(failed_result.get('command') or '').strip()
    if not failed_command:
        return ''

    cwd = state.get('executionWorkspacePath') or state.get('workspacePath') or 'unknown'
    returncode = failed_result.get('returncode') if failed_result else details.get('returncode')
    stdout = (
        str(failed_result.get('stdout') or '').strip()
        if failed_result
        else str(details.get('stdout_tail') or '').strip()
    )
    stderr = (
        str(failed_result.get('stderr') or '').strip()
        if failed_result
        else str(details.get('stderr_tail') or '').strip()
    )
    env_keys = _verification_env_keys_for_prompt(state, failed_result)

    stdout_block = _tail_text(stdout)
    stderr_block = _tail_text(stderr)
    output_sections = []
    if stdout_block:
        output_sections.append(f"stdout tail:\n```text\n{stdout_block}\n```")
    if stderr_block:
        output_sections.append(f"stderr tail:\n```text\n{stderr_block}\n```")
    output_text = '\n\n'.join(output_sections) or 'No stdout/stderr tail recorded.'
    env_text = ', '.join(env_keys) if env_keys else 'none recorded'
    index_text = str(failed_index) if failed_index is not None else 'unknown'

    return f"""## Controller Verification Failure Protocol

The previous Builder attempt was rejected by the controller Verifier. The controller failure is the debugging source of truth.

- failed command index: {index_text}
- exact failed command: {failed_command}
- controller cwd: {cwd}
- returncode: {returncode}
- failure artifact: {verification_path}
- env keys: {env_text}

{output_text}

Required debugging protocol:
- First action: run the exact failed command above from the controller cwd.
- Do not change grep filters, cwd, test file, command flags, worker settings, environment keys, or substitute an adjacent test before this reproduction attempt.
- If the exact command passes locally, explain the controller/agent environment mismatch before changing code.
- If the exact command fails locally, fix the root cause and rerun the exact same command until it exits 0.
- Before DONE, record controller failure resolution in DONE_FILE and then run the full approved verification list.

DONE_FILE contract for this retry:
```json
{{
  "status": "done",
  "summary": "<summary>",
  "run_id": "<current run id>",
  "controller_failure_resolution": {{
    "failed_command": "{failed_command}",
    "reproduced": true,
    "reproduction_exit_code": 124,
    "root_cause": "<required if reproduced>",
    "mismatch_analysis": "<required instead of root_cause if exact command passed locally>",
    "fix_summary": "<what changed>",
    "rerun_exit_code": 0,
    "full_verification_run": "<approved verification list command(s) and result>"
  }}
}}
```
"""


def _matching_failed_verification_result(
    verification: dict[str, Any],
    failed_command: str,
) -> tuple[dict[str, Any] | None, int | None]:
    first_failed: tuple[dict[str, Any], int] | None = None
    for index, result in enumerate(verification.get('results') or [], start=1):
        if not isinstance(result, dict) or result.get('ok'):
            continue
        if first_failed is None:
            first_failed = (result, index)
        if failed_command and str(result.get('command') or '').strip() == failed_command:
            return result, index
    return first_failed if first_failed is not None else (None, None)


def _verification_env_keys_for_prompt(
    state: dict[str, Any],
    failed_result: dict[str, Any] | None,
) -> list[str]:
    env_keys: set[str] = set()
    if failed_result:
        raw_env_keys = failed_result.get('env_keys')
        if isinstance(raw_env_keys, list):
            env_keys.update(str(key) for key in raw_env_keys if str(key).strip())
    for payload in (state, _find_unit(state, state.get('currentUnitId'))):
        if not isinstance(payload, dict):
            continue
        for field in ('verification_env', 'verificationEnv'):
            raw_env = payload.get(field)
            if isinstance(raw_env, dict):
                env_keys.update(str(key) for key in raw_env if str(key).strip())
    return sorted(env_keys)


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
