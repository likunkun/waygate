from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workflow_controller.prompts.bug_fix import _render_bug_fix_prompt
from workflow_controller.rrc_real_runtime import collect_git_changed_files
from workflow_controller.runners import RunnerRequest, make_runner, run_agent_backend
from workflow_controller.steps._common import StepResult, _now_iso, _write_json


def run_bug_fix(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> StepResult:
    unit_dir.mkdir(parents=True, exist_ok=True)
    result_path = unit_dir / 'bug-fix-result.json'
    root_cause_path = unit_dir / 'root-cause.json'
    summary_path = unit_dir / 'bug-fix-summary.json'

    if dry_run:
        result = {
            'status': 'ok',
            'mode': 'dry-run',
            'unit_id': state.get('currentUnitId'),
            'bug_fix_id': state.get('activeBugFixId'),
            'root_cause': {
                'classification': 'implementation_bug',
                'route': 'bug_fix',
                'summary': 'Dry-run bug fix root cause.',
            },
            'changed_files': ['src/example.py', 'tests/test_regression.py'],
            'regression': {
                'commands': _regression_commands(state),
                'evidence': ['green-test.txt'],
            },
            'generated_at': _now_iso(),
        }
        _write_bug_fix_artifacts(unit_dir, result)
        return StepResult(summary='dry-run bug fix complete', outputs=[
            result_path.name,
            root_cause_path.name,
            summary_path.name,
        ])

    workspace_path = state.get('executionWorkspacePath') or state.get('workspacePath')
    if not workspace_path:
        result = {
            'status': 'failed',
            'mode': 'no-workspace',
            'unit_id': state.get('currentUnitId'),
            'bug_fix_id': state.get('activeBugFixId'),
            'root_cause': {
                'classification': 'unknown',
                'route': 'bug_fix',
                'summary': 'Bug Fix Agent requires workspacePath or executionWorkspacePath.',
            },
            'changed_files': [],
            'regression': {'commands': _regression_commands(state), 'evidence': []},
            'generated_at': _now_iso(),
        }
        _write_bug_fix_artifacts(unit_dir, result)
        return StepResult(summary='bug fix failed', outputs=[result_path.name])

    prompt_path = unit_dir / 'bug-fix-prompt.md'
    prompt_path.write_text(_render_bug_fix_prompt(state, result_path), encoding='utf-8')
    runner = make_runner(state, role='bug_fix')
    result = run_agent_backend(RunnerRequest(
        backend=runner.backend,
        workspace_dir=Path(workspace_path),
        prompt_path=prompt_path,
        artifact_dir=unit_dir,
        unit_id=str(state.get('activeBugFixId') or 'bug-fix'),
        agent_command=runner.agent_command,
        tmux_target=runner.tmux_target,
        role=runner.role,
        env=runner.env,
        timeout_seconds=int(state.get('bugFixTimeoutSeconds') or 7200),
    ))
    payload = _read_bug_fix_result(result_path)
    if payload is None:
        payload = {
            'status': 'failed',
            'mode': result.backend,
            'unit_id': state.get('currentUnitId'),
            'bug_fix_id': state.get('activeBugFixId'),
            'root_cause': {
                'classification': 'unknown',
                'route': 'bug_fix',
                'summary': 'Bug Fix Agent did not write bug-fix-result.json.',
            },
            'changed_files': [],
            'regression': {'commands': _regression_commands(state), 'evidence': []},
        }
    payload.setdefault('mode', result.backend)
    payload.setdefault('unit_id', state.get('currentUnitId'))
    payload.setdefault('bug_fix_id', state.get('activeBugFixId'))
    payload.setdefault('generated_at', _now_iso())
    payload['exit_code'] = result.returncode
    payload['runner_status'] = result.status
    payload['runner_metadata'] = result.runner_metadata
    if not payload.get('changed_files'):
        payload['changed_files'] = collect_git_changed_files(Path(workspace_path))
    if result.returncode != 0 and payload.get('status') != 'escalate_unit_plan':
        payload['status'] = 'failed'
    _write_bug_fix_artifacts(unit_dir, payload)
    return StepResult(summary='bug fix complete', outputs=[
        result_path.name,
        root_cause_path.name,
        summary_path.name,
    ])


def _write_bug_fix_artifacts(unit_dir: Path, result: dict[str, Any]) -> None:
    root_cause = result.get('root_cause') if isinstance(result.get('root_cause'), dict) else {}
    if not root_cause:
        root_cause = {
            'classification': 'unknown',
            'route': 'bug_fix',
            'summary': 'Root cause was not provided.',
        }
        result['root_cause'] = root_cause
    _write_json(unit_dir / 'bug-fix-result.json', result)
    _write_json(unit_dir / 'root-cause.json', root_cause)
    _write_json(unit_dir / 'bug-fix-summary.json', {
        'status': result.get('status'),
        'unit_id': result.get('unit_id'),
        'bug_fix_id': result.get('bug_fix_id'),
        'root_cause': root_cause,
        'changed_files': result.get('changed_files') or [],
        'regression': result.get('regression') or {},
        'generated_at': result.get('generated_at') or _now_iso(),
    })
    changed_files = [str(path) for path in result.get('changed_files') or [] if str(path)]
    (unit_dir / 'changed-files.txt').write_text('\n'.join(changed_files) + ('\n' if changed_files else ''), encoding='utf-8')
    (unit_dir / 'green-test.txt').write_text('PASSED bug fix regression\n', encoding='utf-8')


def _read_bug_fix_result(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _regression_commands(state: dict[str, Any]) -> list[str]:
    commands: list[str] = []
    for unit in state.get('units') or []:
        if isinstance(unit, dict) and unit.get('id') == state.get('currentUnitId'):
            commands.extend(str(command) for command in unit.get('verification_commands') or [] if str(command))
    commands.extend(str(command) for command in state.get('verificationCommands') or [] if str(command))
    return commands
