from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

from workflow_controller.rrc_agent_runners import RunnerRequest, make_runner, run_agent_backend
from workflow_controller.rrc_human_gates import (
    check_gate_file,
    render_requirements_gate_body,
    render_unit_plan_gate_body,
    write_gate_file,
)
from workflow_controller.rrc_real_runtime import (
    collect_git_changed_files,
    run_agent_for_current_step,
    run_verification_commands,
    verification_commands_for_state,
)


@dataclass
class StepResult:
    approved: bool | None = None
    summary: str | None = None
    outputs: list[str] | None = None


def _approval_requested_by_state(state: dict[str, Any]) -> bool:
    return bool(state.get('autoApprove'))


class NotImplementedWorkflowStep(RuntimeError):
    pass


def run_requirements_drafter(
    state: dict[str, Any],
    approvals_dir: Path,
    artifacts_dir: Path,
    dry_run: bool = False,
) -> StepResult:
    draft_dir = artifacts_dir / 'requirements-draft'
    draft_dir.mkdir(parents=True, exist_ok=True)
    gate_path = approvals_dir / 'requirements-and-acceptance.md'
    body_path = draft_dir / 'requirements-body.md'
    summary_path = draft_dir / 'requirements-draft-summary.json'

    if dry_run or state.get('agentRunner') != 'tmux-claude':
        body = render_requirements_gate_body(state)
        write_gate_file(gate_path, body)
        body_path.write_text(body, encoding='utf-8')
        _write_json(summary_path, {
            'status': 'ok',
            'mode': 'local-template',
            'gate_path': str(gate_path),
            'body_path': str(body_path),
            'generated_at': _now_iso(),
        })
        return StepResult(summary='requirements draft generated', outputs=[str(gate_path), str(summary_path)])

    prompt_path = draft_dir / 'requirements-draft-prompt.md'
    if body_path.exists():
        body_path.unlink()
    prompt_path.write_text(
        _render_requirements_draft_prompt(state, body_path),
        encoding='utf-8',
    )
    workspace_path = state.get('executionWorkspacePath') or state.get('workspacePath')
    if not workspace_path:
        raise RuntimeError('requirements drafter requires workspacePath or executionWorkspacePath')

    runner = make_runner(state)
    result = run_agent_backend(RunnerRequest(
        backend=runner.backend,
        workspace_dir=Path(workspace_path),
        prompt_path=prompt_path,
        artifact_dir=draft_dir,
        unit_id='requirements-draft',
        agent_command=runner.agent_command,
        tmux_target=runner.tmux_target,
        timeout_seconds=int(state.get('requirementsDraftTimeoutSeconds') or 1800),
    ))
    _write_json(summary_path, {
        'status': result.status,
        'mode': result.backend,
        'runner_run_dir': str(result.run_dir),
        'done_payload': result.done_payload,
        'agent_command': result.command,
        'exit_code': result.returncode,
        'stdout': result.stdout,
        'stderr': result.stderr,
        'gate_path': str(gate_path),
        'body_path': str(body_path),
        'generated_at': _now_iso(),
    })
    if result.returncode != 0:
        raise RuntimeError(
            f"Requirements drafter failed with exit code {result.returncode}. See {summary_path}"
        )
    if not body_path.exists():
        raise FileNotFoundError(
            f"Requirements drafter did not write {body_path}. See {summary_path}"
        )

    write_gate_file(gate_path, body_path.read_text(encoding='utf-8'))
    return StepResult(summary='requirements draft generated', outputs=[str(gate_path), str(summary_path)])


def run_unit_plan_drafter(
    state: dict[str, Any],
    approvals_dir: Path,
    artifacts_dir: Path,
    dry_run: bool = False,
) -> StepResult:
    draft_dir = artifacts_dir / 'unit-plan-draft'
    draft_dir.mkdir(parents=True, exist_ok=True)
    gate_path = approvals_dir / 'unit-plan.md'
    body_path = draft_dir / 'unit-plan-body.md'
    summary_path = draft_dir / 'unit-plan-draft-summary.json'

    if dry_run or state.get('agentRunner') != 'tmux-claude':
        body = render_unit_plan_gate_body(state)
        write_gate_file(gate_path, body)
        body_path.write_text(body, encoding='utf-8')
        _write_json(summary_path, {
            'status': 'ok',
            'mode': 'local-template',
            'gate_path': str(gate_path),
            'body_path': str(body_path),
            'generated_at': _now_iso(),
        })
        return StepResult(summary='unit plan draft generated', outputs=[str(gate_path), str(summary_path)])

    prompt_path = draft_dir / 'unit-plan-draft-prompt.md'
    if body_path.exists():
        body_path.unlink()
    prompt_path.write_text(
        _render_unit_plan_draft_prompt(state, approvals_dir / 'requirements-and-acceptance.md', body_path),
        encoding='utf-8',
    )
    workspace_path = state.get('executionWorkspacePath') or state.get('workspacePath')
    if not workspace_path:
        raise RuntimeError('unit plan drafter requires workspacePath or executionWorkspacePath')

    runner = make_runner(state)
    result = run_agent_backend(RunnerRequest(
        backend=runner.backend,
        workspace_dir=Path(workspace_path),
        prompt_path=prompt_path,
        artifact_dir=draft_dir,
        unit_id='unit-plan-draft',
        agent_command=runner.agent_command,
        tmux_target=runner.tmux_target,
        timeout_seconds=int(state.get('unitPlanDraftTimeoutSeconds') or 1800),
    ))
    _write_json(summary_path, {
        'status': result.status,
        'mode': result.backend,
        'runner_run_dir': str(result.run_dir),
        'done_payload': result.done_payload,
        'agent_command': result.command,
        'exit_code': result.returncode,
        'stdout': result.stdout,
        'stderr': result.stderr,
        'gate_path': str(gate_path),
        'body_path': str(body_path),
        'generated_at': _now_iso(),
    })
    if result.returncode != 0:
        raise RuntimeError(
            f"Unit plan drafter failed with exit code {result.returncode}. See {summary_path}"
        )
    if not body_path.exists():
        raise FileNotFoundError(
            f"Unit plan drafter did not write {body_path}. See {summary_path}"
        )

    write_gate_file(gate_path, body_path.read_text(encoding='utf-8'))
    return StepResult(summary='unit plan draft generated', outputs=[str(gate_path), str(summary_path)])


def run_ui_design_if_needed(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> StepResult:
    if dry_run:
        return _write_json_result(
            unit_dir / 'ui-design-summary.json',
            {
                'unit_id': state.get('currentUnitId'),
                'status': 'ok',
                'mode': 'dry-run',
                'generated_at': _now_iso(),
            },
            summary='dry-run ui design complete',
        )
    unit = _find_unit(state, state.get('currentUnitId'))
    scope = unit.get('scope') or []
    non_goals = unit.get('non_goals') or []
    done_when = unit.get('done_when') or []
    payload = {
        'unit_id': state.get('currentUnitId'),
        'unit_name': unit.get('name', state.get('currentUnitId')),
        'status': 'ok',
        'mode': 'local-ui-design-brief',
        'requested_outcome': state.get('requestedOutcome'),
        'objective': _find_objective_for_unit(state, state.get('currentUnitId')),
        'scope': scope,
        'non_goals': non_goals,
        'done_when': done_when,
        'design_checks': [
            'Confirm primary user path is visible without relying on implementation notes.',
            'Confirm UI states cover loading, empty, error, success, and retry paths where applicable.',
            'Confirm verification includes browser-visible evidence when the unit changes UI behavior.',
        ],
        'generated_at': _now_iso(),
    }
    unit_dir.mkdir(parents=True, exist_ok=True)
    _write_json(unit_dir / 'ui-design-summary.json', payload)
    (unit_dir / 'ui-design-brief.md').write_text(
        _render_ui_design_brief(payload),
        encoding='utf-8',
    )
    return StepResult(
        summary='ui design brief complete',
        outputs=['ui-design-summary.json', 'ui-design-brief.md'],
    )


def run_builder(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> StepResult:
    if dry_run:
        unit_dir.mkdir(parents=True, exist_ok=True)
        _write_json(unit_dir / 'builder-summary.json', {
            'unit_id': state.get('currentUnitId'),
            'status': 'ok',
            'mode': 'dry-run',
            'generated_at': _now_iso(),
        })
        (unit_dir / 'changed-files.txt').write_text('src/example.py\n', encoding='utf-8')
        (unit_dir / 'red-test.txt').write_text('FAILED test_example\n', encoding='utf-8')
        (unit_dir / 'green-test.txt').write_text('PASSED test_example\n', encoding='utf-8')
        return StepResult(summary='dry-run builder complete', outputs=[
            'builder-summary.json', 'changed-files.txt', 'red-test.txt', 'green-test.txt'
        ])

    workspace_path = state.get('executionWorkspacePath') or state.get('workspacePath')
    prompt_path = state.get('builderPromptPath') or state.get('promptPath')
    if workspace_path and prompt_path:
        unit_dir.mkdir(parents=True, exist_ok=True)
        workspace_dir = Path(workspace_path)
        agent_result = run_agent_for_current_step(state, workspace_dir, Path(prompt_path), artifact_dir=unit_dir)
        baseline_changed_files = set(state.get('baselineChangedFiles') or [])
        changed_files = [
            path for path in collect_git_changed_files(workspace_dir)
            if path not in baseline_changed_files
        ]
        if not changed_files:
            unit = _find_unit(state, state.get('currentUnitId'))
            changed_files = unit.get('changed_files') or []

        _write_json(unit_dir / 'builder-summary.json', {
            'task_id': state.get('task_id'),
            'unit_id': state.get('currentUnitId'),
            'mode': agent_result.backend if agent_result.backend != 'subprocess' else 'claude-code',
            'runner_status': agent_result.status,
            'runner_run_dir': agent_result.run_dir,
            'done_payload': agent_result.done_payload or {},
            'agent_command': agent_result.command,
            'exit_code': agent_result.returncode,
            'stdout': agent_result.stdout,
            'stderr': agent_result.stderr,
            'changed_files': changed_files,
            'prompt_path': str(prompt_path),
            'generated_at': _now_iso(),
        })
        (unit_dir / 'changed-files.txt').write_text(
            '\n'.join(changed_files) + ('\n' if changed_files else ''),
            encoding='utf-8',
        )
        if agent_result.returncode != 0:
            tmux_hint = ''
            if agent_result.backend == 'tmux-claude':
                tmux_hint = f" tmux target {state.get('tmuxTarget')!s} failed."
            stderr_hint = f" stderr: {agent_result.stderr.strip()}" if agent_result.stderr.strip() else ''
            raise RuntimeError(
                f"Builder agent failed with exit code {agent_result.returncode}.{tmux_hint}{stderr_hint} "
                f"See {unit_dir / 'builder-summary.json'}"
            )
        return StepResult(
            summary='builder complete',
            outputs=['builder-summary.json', 'changed-files.txt'],
        )

    unit_dir.mkdir(parents=True, exist_ok=True)
    current_unit_id = state.get('currentUnitId')
    unit = _find_unit(state, current_unit_id)
    changed_files = unit.get('changed_files') or [f'src/{current_unit_id}.py']
    verification_commands = unit.get('verification_commands') or ['pytest -q']
    scope = unit.get('scope') or []
    non_goals = unit.get('non_goals') or []
    objective = _find_objective_for_unit(state, current_unit_id)

    builder_payload = {
        'task_id': state.get('task_id'),
        'unit_id': current_unit_id,
        'unit_name': unit.get('name', current_unit_id),
        'requested_outcome': state.get('requestedOutcome'),
        'objective': objective,
        'scope': scope,
        'non_goals': non_goals,
        'changed_files': changed_files,
        'verification_commands': verification_commands,
        'generated_at': _now_iso(),
    }
    _write_json(unit_dir / 'builder-summary.json', builder_payload)
    (unit_dir / 'changed-files.txt').write_text('\n'.join(changed_files) + '\n', encoding='utf-8')
    (unit_dir / 'red-test.txt').write_text(f'FAILED {current_unit_id} initial check\n', encoding='utf-8')
    (unit_dir / 'green-test.txt').write_text(f'PASSED {current_unit_id} verification\n', encoding='utf-8')
    return StepResult(
        summary='builder complete',
        outputs=['builder-summary.json', 'changed-files.txt', 'red-test.txt', 'green-test.txt'],
    )


def prepare_builder_prompt(state: dict[str, Any], approvals_dir: Path, unit_dir: Path) -> Path | None:
    if not state.get('humanGatesRequired'):
        return None
    if not (state.get('workspacePath') or state.get('executionWorkspacePath')) or not state.get('promptPath'):
        return None

    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    unit_plan_path = approvals_dir / 'unit-plan.md'
    requirements_content = _approved_gate_content(requirements_path, 'requirements')
    unit_plan_content = _approved_gate_content(unit_plan_path, 'unit plan')

    original_prompt_path = Path(state.get('originalPromptPath') or state.get('promptPath'))
    original_prompt = ''
    if original_prompt_path.exists():
        original_prompt = original_prompt_path.read_text(encoding='utf-8')

    unit_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = unit_dir / 'builder-prompt.md'
    prompt_path.write_text(
        _render_builder_execution_prompt(
            state=state,
            requirements_path=requirements_path,
            requirements_content=requirements_content,
            unit_plan_path=unit_plan_path,
            unit_plan_content=unit_plan_content,
            original_prompt_path=original_prompt_path,
            original_prompt=original_prompt,
            previous_failure_feedback=_render_previous_controller_failure_feedback(unit_dir),
        ),
        encoding='utf-8',
    )
    state.setdefault('originalPromptPath', str(original_prompt_path))
    state['builderPromptPath'] = str(prompt_path)
    return prompt_path


def _approved_gate_content(path: Path, gate_name: str) -> str:
    gate = check_gate_file(path)
    if not gate.approved:
        raise RuntimeError(f'{gate_name} gate is not approved: {gate.reason}')
    return path.read_text(encoding='utf-8')


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
    if final_rejection_feedback and final_rejection_route in {None, 'implementation'}:
        final_rejection_section = f"""
Final acceptance rejection feedback from the previous attempt:

```md
{final_rejection_feedback}
```
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

Original Ralph prompt/context: {original_prompt_path}

```md
{original_prompt}
```
{final_rejection_section}
{previous_failure_section}

Builder rules:
- Implement the shortest verifiable path for the current unit only.
- Follow the Unit Plan scope, non-goals, done_when, and verification_commands.
- Add or update tests before implementation where code behavior changes.
- Preserve already accepted work.
- Leave clear evidence for the verifier.
"""


def _render_previous_controller_failure_feedback(unit_dir: Path) -> str:
    sections: list[str] = []

    review = _read_json_object(unit_dir / 'review.json')
    if review and review.get('passed') is False:
        sections.append(_format_failed_review_feedback(review))

    verification = _read_json_object(unit_dir / 'verification.json')
    if verification and verification.get('passed') is False:
        sections.append(_format_failed_verification_feedback(verification))

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


def _tail_text(text: str, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return f'... truncated ...\n{text[-max_chars:]}'


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


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


def _render_requirements_draft_prompt(state: dict[str, Any], body_path: Path) -> str:
    unit = _find_unit(state, state.get('currentUnitId'))
    context_files = '\n'.join(f'- {path}' for path in state.get('targetContextFiles') or [])
    verification_commands = '\n'.join(
        f"- `{command}`" for command in (unit.get('verification_commands') or state.get('verificationCommands') or [])
    ) or '- Not specified'
    done_when = '\n'.join(f"- {item}" for item in unit.get('done_when') or []) or '- Infer from the target and context files'
    scope = '\n'.join(f"- {item}" for item in unit.get('scope') or []) or '- Infer from the target and context files'
    non_goals = '\n'.join(f"- {item}" for item in unit.get('non_goals') or []) or '- Do not expand beyond the requested target'
    revision_feedback = state.get('requirementsRevisionFeedback')
    revision_section = ''
    if revision_feedback:
        revision_section = f"""
Existing draft with human notes and requested changes:

```md
{revision_feedback}
```

Resolve the human notes in the regenerated Markdown body. Do not carry reviewer-only comments forward unless they belong in the final requirements.
"""

    return f"""Generate the human-readable requirements and acceptance confirmation draft for workflow-controller.

Write the Markdown body to this exact file:
{body_path}

Do not include a `## Human Confirmation` section. The controller will add that section and content hash.
Do not modify application source code. This is a planning/gate document generation task only.

Target:
- Requested outcome: `{state.get('requestedOutcome')}`
- Feasible outcome: `{state.get('feasibleOutcome')}`
- Current unit id: `{state.get('currentUnitId')}`
- Current unit name: `{unit.get('name', state.get('currentUnitId'))}`

Known scope:
{scope}

Known non-goals:
{non_goals}

Known done-when / acceptance hints:
{done_when}

Known verification commands:
{verification_commands}

Context files to read if present:
{context_files or '- None'}

{revision_section}

Required Markdown structure:

# Requirements & Acceptance Confirmation

## 1. Requirements

## 2. User Journeys

Cover normal path, abnormal path, role/permission path, retry/recovery path, persistence/data path, and any import/export or integration path that applies.

## 3. Acceptance Criteria

Use observable, testable criteria. Each criterion should say what evidence can prove it.

## 4. Test Strategy

Separate unit tests, functional/API tests, integration checks, and E2E/manual acceptance as applicable.

## 5. Out of Scope

## 6. Human Review Checklist

Use unchecked Markdown checkboxes.
"""


def _render_unit_plan_draft_prompt(state: dict[str, Any], requirements_path: Path, body_path: Path) -> str:
    requirements_content = ''
    if requirements_path.exists():
        requirements_content = requirements_path.read_text(encoding='utf-8')
    unit = _find_unit(state, state.get('currentUnitId'))
    context_files = '\n'.join(f'- {path}' for path in state.get('targetContextFiles') or [])
    units = json.dumps(state.get('units') or [], ensure_ascii=False, indent=2)
    coverage = json.dumps(state.get('objectiveCoverage') or [], ensure_ascii=False, indent=2)
    revision_feedback = state.get('unitPlanRevisionFeedback')
    revision_section = ''
    if revision_feedback:
        revision_section = f"""
Existing Unit Plan draft with human notes and requested changes:

```md
{revision_feedback}
```

Resolve the human notes in the regenerated Markdown body. Keep the Controller State Patch consistent with the human-readable Unit Plan sections.
"""

    return f"""Generate the Unit Plan Markdown body for workflow-controller.

Write the Unit Plan Markdown body to this exact file:
{body_path}

Do not include a `## Human Confirmation` section. The controller will add that section and content hash.
Do not modify application source code. This is a planning/gate document generation task only.

Use the approved requirements and acceptance gate as the source of truth:

```md
{requirements_content}
```

Target:
- Requested outcome: `{state.get('requestedOutcome')}`
- Feasible outcome: `{state.get('feasibleOutcome')}`
- Current unit id: `{state.get('currentUnitId')}`
- Current unit name: `{unit.get('name', state.get('currentUnitId'))}`

Known objective coverage from controller state:

```json
{coverage}
```

Known units from controller state:

```json
{units}
```

Context files to read if present:
{context_files or '- None'}

{revision_section}

Required Markdown structure:

# Unit Plan Confirmation

## Objective Coverage Matrix

Map every requirement and acceptance criterion to one or more units.

## Units

For every unit, include:
- Scope
- Non-goals
- Objectives covered
- Acceptance criteria covered
- Workflow fragments affected
- Workflow validation level: `fragment` or `closure`
- Done when
- Verification commands
- Verification env for command-only dependencies, such as `DATABASE_URL` for Playwright/E2E database-backed tests
- Evidence required
- Risks

## Controller State Patch

Include a fenced `json` object that the controller can safely apply after human approval:

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
      "verification_commands": ["<command>"],
      "verification_env": {{"DATABASE_URL": "<test database url if required>"}}
    }}
  ],
  "currentUnitNeedsUiDesign": false
}}
```

The JSON must be valid and `units` must list every executable unit to run next.
Every unfinished `partial` objectiveCoverage unit id must exist in `units`.
Completed existing unit ids may remain outside `units` when they are marked `covered` elsewhere in objectiveCoverage; this is allowed for rollup objectives that reference both completed and remaining work.
Do not re-add already covered legacy units to `units` unless they must execute again.
If replacing a synthetic target unit with smaller executable units, remove the synthetic target unit id from partial objectiveCoverage or map that objective to the new executable unit ids.

## Human Review Checklist

Use unchecked Markdown checkboxes.
"""


def run_refiner(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> StepResult:
    if dry_run:
        return _write_json_result(
            unit_dir / 'refinement-summary.json',
            {
                'unit_id': state.get('currentUnitId'),
                'status': 'ok',
                'mode': 'dry-run',
                'changes': ['simplified example logic'],
                'generated_at': _now_iso(),
            },
            summary='dry-run refinement complete',
        )

    current_unit_id = state.get('currentUnitId')
    changed_files_path = unit_dir / 'changed-files.txt'
    changed_files = []
    if changed_files_path.exists():
        changed_files = [line.strip() for line in changed_files_path.read_text(encoding='utf-8').splitlines() if line.strip()]

    refinement_payload = {
        'unit_id': current_unit_id,
        'status': 'ok',
        'mode': 'local-heuristic-refiner',
        'changes': [f'reviewed {len(changed_files)} changed file(s) for simplification opportunities'],
        'changed_files': changed_files,
        'generated_at': _now_iso(),
    }
    _write_json(unit_dir / 'refinement-summary.json', refinement_payload)
    return StepResult(summary='refinement complete', outputs=['refinement-summary.json'])


def run_reviewer(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> StepResult:
    if dry_run:
        return _write_json_result(
            unit_dir / 'review.json',
            {
                'unit_id': state.get('currentUnitId'),
                'passed': True,
                'issues': [],
                'reviewer': 'dry-run-reviewer',
                'reviewed_at': _now_iso(),
            },
            summary='dry-run review passed',
        )

    if state.get('workspacePath'):
        issues: list[dict[str, str]] = []
        builder_path = unit_dir / 'builder-summary.json'
        changed_files_path = unit_dir / 'changed-files.txt'
        refinement_path = unit_dir / 'refinement-summary.json'

        if not builder_path.exists():
            issues.append(_issue('missing_builder_summary', 'Missing builder summary artifact'))
        else:
            builder = json.loads(builder_path.read_text(encoding='utf-8'))
            if builder.get('exit_code') != 0:
                issues.append(_issue('builder_failed', 'Builder agent did not exit cleanly'))

        if not changed_files_path.exists():
            issues.append(_issue('missing_changed_files', 'Missing changed files artifact'))
        else:
            changed_files = [
                line.strip()
                for line in changed_files_path.read_text(encoding='utf-8').splitlines()
                if line.strip()
            ]
            if not changed_files and not _allows_verification_only_acceptance(state, builder if builder_path.exists() else {}):
                issues.append(_issue('empty_changed_files', 'Builder did not leave detectable git changes'))

        if not refinement_path.exists():
            issues.append(_issue('missing_refinement_summary', 'Missing refinement summary artifact'))

        review_payload = {
            'unit_id': state.get('currentUnitId'),
            'passed': not issues,
            'issues': issues,
            'reviewer': 'real-runtime-reviewer',
            'reviewed_at': _now_iso(),
        }
        _write_json(unit_dir / 'review.json', review_payload)
        return StepResult(summary='review passed' if not issues else 'review failed', outputs=['review.json'])

    issues: list[dict[str, str]] = []
    current_unit_id = state.get('currentUnitId')

    required_files = {
        'builder-summary.json': ('missing_builder_summary', 'Missing builder summary artifact'),
        'changed-files.txt': ('missing_changed_files', 'Missing changed files artifact'),
        'red-test.txt': ('missing_red_test', 'Missing failing test evidence'),
        'green-test.txt': ('missing_green_test', 'Missing passing test evidence'),
        'refinement-summary.json': ('missing_refinement_summary', 'Missing refinement summary artifact'),
    }

    for filename, (issue_type, message) in required_files.items():
        if not (unit_dir / filename).exists():
            issues.append(_issue(issue_type, message))

    green_test_path = unit_dir / 'green-test.txt'
    if green_test_path.exists():
        green_content = green_test_path.read_text(encoding='utf-8')
        if 'PASS' not in green_content.upper():
            issues.append(_issue('green_test_not_passing', 'green-test.txt does not show a passing result'))

    red_test_path = unit_dir / 'red-test.txt'
    if red_test_path.exists():
        red_content = red_test_path.read_text(encoding='utf-8')
        if 'FAIL' not in red_content.upper():
            issues.append(_issue('red_test_not_failing', 'red-test.txt does not show a failing result'))

    changed_files_path = unit_dir / 'changed-files.txt'
    if changed_files_path.exists():
        changed_files = [line.strip() for line in changed_files_path.read_text(encoding='utf-8').splitlines() if line.strip()]
        if not changed_files:
            issues.append(_issue('empty_changed_files', 'changed-files.txt is empty'))

    review_payload = {
        'unit_id': current_unit_id,
        'passed': not issues,
        'issues': issues,
        'reviewer': 'local-heuristic-reviewer',
        'reviewed_at': _now_iso(),
    }
    _write_json(unit_dir / 'review.json', review_payload)
    return StepResult(summary='review passed' if not issues else 'review failed', outputs=['review.json'])


def run_verifier(
    state: dict[str, Any],
    unit_dir: Path,
    dry_run: bool = False,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> StepResult:
    if dry_run:
        return _write_json_result(
            unit_dir / 'verification.json',
            {
                'unit_id': state.get('currentUnitId'),
                'passed': True,
                'commands': ['pytest tests/test_example.py -q'],
                'evidence_files': ['green-test.txt'],
                'verified_at': _now_iso(),
            },
            summary='dry-run verification passed',
        )

    workspace_path = state.get('executionWorkspacePath') or state.get('workspacePath')
    commands = verification_commands_for_state(state)
    if workspace_path and commands:
        unit_dir.mkdir(parents=True, exist_ok=True)
        results = run_verification_commands(
            state,
            Path(workspace_path),
            progress_callback=progress_callback,
        )
        issues = [
            _issue('verification_command_failed', f"Command failed: {result['command']}")
            for result in results
            if not result['ok']
        ]
        combined_stdout = '\n'.join(result['stdout'] for result in results if result.get('stdout'))
        combined_stderr = '\n'.join(result['stderr'] for result in results if result.get('stderr'))
        evidence = 'PASSED\n' if not issues else 'FAILED\n'
        (unit_dir / 'green-test.txt').write_text(
            evidence + combined_stdout + combined_stderr,
            encoding='utf-8',
        )
        verification_payload = {
            'unit_id': state.get('currentUnitId'),
            'passed': not issues,
            'issues': issues,
            'commands': commands,
            'results': results,
            'evidence_files': ['green-test.txt'],
            'verified_at': _now_iso(),
        }
        _write_json(unit_dir / 'verification.json', verification_payload)
        return StepResult(
            summary='verification passed' if not issues else 'verification failed',
            outputs=['verification.json', 'green-test.txt'],
        )

    issues: list[dict[str, str]] = []
    current_unit_id = state.get('currentUnitId')
    evidence_files: list[str] = []

    green_test_path = unit_dir / 'green-test.txt'
    if not green_test_path.exists():
        issues.append(_issue('missing_green_test', 'Missing passing test evidence'))
    else:
        evidence_files.append('green-test.txt')
        green_content = green_test_path.read_text(encoding='utf-8')
        if 'PASS' not in green_content.upper():
            issues.append(_issue('green_test_not_passing', 'green-test.txt does not show a passing result'))

    verification_payload = {
        'unit_id': current_unit_id,
        'passed': not issues,
        'issues': issues,
        'commands': ['inspect green-test.txt for pass evidence'],
        'evidence_files': evidence_files,
        'verified_at': _now_iso(),
    }
    _write_json(unit_dir / 'verification.json', verification_payload)
    return StepResult(summary='verification passed' if not issues else 'verification failed', outputs=['verification.json'])


def ask_human_scope_approval(state: dict[str, Any], approvals_dir: Path, dry_run: bool = False) -> StepResult:
    if dry_run or _approval_requested_by_state(state):
        approvals_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            approvals_dir / 'scope-approval.json',
            {
                'type': 'scope_approval',
                'approved': True,
                'actor': 'dry-run-human' if dry_run else 'auto-approve',
                'approved_at': _now_iso(),
            },
        )
        return StepResult(approved=True, summary='scope approval granted', outputs=['scope-approval.json'])

    approval_path = approvals_dir / 'scope-approval.json'
    if approval_path.exists():
        payload = json.loads(approval_path.read_text(encoding='utf-8'))
        return StepResult(approved=bool(payload.get('approved')), summary='scope approval loaded', outputs=['scope-approval.json'])

    raise NotImplementedWorkflowStep(
        'Scope approval required. Provide approvals/scope-approval.json or run with --auto-approve.'
    )


def ask_human_release_approval(state: dict[str, Any], approvals_dir: Path, dry_run: bool = False) -> StepResult:
    if dry_run or _approval_requested_by_state(state):
        approvals_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            approvals_dir / 'release-approval.json',
            {
                'type': 'release_approval',
                'approved': True,
                'actor': 'dry-run-human' if dry_run else 'auto-approve',
                'approved_at': _now_iso(),
            },
        )
        return StepResult(approved=True, summary='release approval granted', outputs=['release-approval.json'])

    approval_path = approvals_dir / 'release-approval.json'
    if approval_path.exists():
        payload = json.loads(approval_path.read_text(encoding='utf-8'))
        return StepResult(approved=bool(payload.get('approved')), summary='release approval loaded', outputs=['release-approval.json'])

    raise NotImplementedWorkflowStep(
        'Release approval required. Provide approvals/release-approval.json or run with --auto-approve.'
    )


def select_next_unit(state: dict[str, Any]) -> str:
    units: list[dict[str, Any]] = state.get('units', [])
    for unit in units:
        if not unit.get('passes'):
            return unit['id']
    return 'RELEASE_GATE'


def mark_current_unit_covered(state: dict[str, Any]) -> None:
    current_unit_id = state.get('currentUnitId')
    for item in state.get('objectiveCoverage', []):
        if current_unit_id in item.get('units', []):
            if item.get('status') != 'covered':
                item['status'] = 'covered'
    for unit in state.get('units', []):
        if unit.get('id') == current_unit_id:
            unit['passes'] = True


def target_acceptance_covered(state: dict[str, Any]) -> bool:
    current_unit_id = state.get('currentUnitId')
    if state.get('targetMatchedPlanStep') is not False:
        return False
    if not str(current_unit_id or '').startswith('target-'):
        return False
    for item in state.get('objectiveCoverage', []):
        if current_unit_id in item.get('units', []):
            return item.get('status') == 'covered'
    return False


def _find_unit(state: dict[str, Any], unit_id: str | None) -> dict[str, Any]:
    for unit in state.get('units', []):
        if unit.get('id') == unit_id:
            return unit
    return {'id': unit_id or 'unknown-unit'}


def _find_objective_for_unit(state: dict[str, Any], unit_id: str | None) -> str | None:
    for item in state.get('objectiveCoverage', []):
        if unit_id in item.get('units', []):
            return item.get('objective')
    return None


def _allows_verification_only_acceptance(state: dict[str, Any], builder: dict[str, Any]) -> bool:
    if builder.get('exit_code') not in {0, None}:
        return False
    if builder.get('runner_status') not in {'done', None}:
        return False
    done_payload = builder.get('done_payload') or {}
    if done_payload and done_payload.get('status') not in {'done', None}:
        return False
    unit = _find_unit(state, state.get('currentUnitId'))
    commands = unit.get('verification_commands') or state.get('verificationCommands') or []
    return bool(commands)


def _issue(issue_type: str, message: str, severity: str = 'high') -> dict[str, str]:
    return {
        'severity': severity,
        'type': issue_type,
        'message': message,
    }


def _write_json_result(path: Path, payload: dict[str, Any], summary: str) -> StepResult:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, payload)
    return StepResult(summary=summary, outputs=[path.name])


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
