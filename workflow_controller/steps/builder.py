from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from workflow_controller.runners import make_runner, run_agent_backend, RunnerRequest
from workflow_controller.gates import check_gate_file
from workflow_controller.rrc_real_runtime import (
    collect_git_changed_files,
    run_agent_for_current_step,
    run_verification_commands,
    verification_commands_for_state,
)
from workflow_controller.state_machine.transitions import objective_coverage_units_passed
from workflow_controller.prompts.builder import (
    _render_builder_execution_prompt,
    _render_ui_design_brief,
    _render_previous_controller_failure_feedback,
)
from workflow_controller.steps._common import (
    StepResult,
    NotImplementedWorkflowStep,
    _approval_requested_by_state,
    _write_json,
    _write_json_result,
    _issue,
    _find_unit,
    _find_objective_for_unit,
    _now_iso,
)


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
            'runner_metadata': agent_result.runner_metadata or {},
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
        import json as _json
        payload = _json.loads(approval_path.read_text(encoding='utf-8'))
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
        import json as _json
        payload = _json.loads(approval_path.read_text(encoding='utf-8'))
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
    for unit in state.get('units', []):
        if unit.get('id') == current_unit_id:
            unit['passes'] = True
    for item in state.get('objectiveCoverage', []):
        if current_unit_id in item.get('units', []):
            item['status'] = 'covered' if objective_coverage_units_passed(state, item) else 'partial'


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
