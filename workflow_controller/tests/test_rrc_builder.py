from __future__ import annotations

import json
from pathlib import Path

import pytest

from workflow_controller.gates.parsers import approve_gate_file, write_gate_file
from workflow_controller.rrc_real_runtime import AgentRunResult
from workflow_controller.steps.builder import prepare_builder_prompt, run_builder


def test_run_builder_generates_real_builder_artifacts_from_state(tmp_path: Path) -> None:
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    state = {
        'task_id': 'demo-login-flow',
        'currentUnitId': 'unit-01',
        'currentStep': 'EXECUTE_UNIT',
        'requestedOutcome': 'usable-system',
        'objectiveCoverage': [
            {
                'objective': '用户可以完成登录流程',
                'units': ['unit-01'],
                'status': 'partial',
            }
        ],
        'units': [
            {
                'id': 'unit-01',
                'name': 'login core flow',
                'scope': ['Implement login submit flow'],
                'non_goals': ['Do not touch signup'],
                'changed_files': ['src/login.py', 'tests/test_login.py'],
                'verification_commands': ['pytest tests/test_login.py -q'],
            }
        ],
    }

    result = run_builder(state, unit_dir, dry_run=False)

    assert result.summary == 'builder complete'
    summary = json.loads((unit_dir / 'builder-summary.json').read_text(encoding='utf-8'))
    assert summary['unit_id'] == 'unit-01'
    assert summary['task_id'] == 'demo-login-flow'
    assert summary['unit_name'] == 'login core flow'
    assert summary['changed_files'] == ['src/login.py', 'tests/test_login.py']
    assert summary['verification_commands'] == ['pytest tests/test_login.py -q']

    changed_files = (unit_dir / 'changed-files.txt').read_text(encoding='utf-8').splitlines()
    assert changed_files == ['src/login.py', 'tests/test_login.py']


def test_run_builder_falls_back_to_unit_specific_default_artifacts_when_state_is_sparse(tmp_path: Path) -> None:
    unit_dir = tmp_path / 'artifacts' / 'unit-09'
    state = {
        'currentUnitId': 'unit-09',
        'currentStep': 'EXECUTE_UNIT',
    }

    result = run_builder(state, unit_dir, dry_run=False)

    assert result.summary == 'builder complete'
    summary = json.loads((unit_dir / 'builder-summary.json').read_text(encoding='utf-8'))
    assert summary['unit_id'] == 'unit-09'
    assert summary['changed_files'] == ['src/unit-09.py']

    changed_files = (unit_dir / 'changed-files.txt').read_text(encoding='utf-8').splitlines()
    assert changed_files == ['src/unit-09.py']


def test_run_builder_failure_error_includes_agent_done_summary(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    prompt_path.write_text('Implement current unit.', encoding='utf-8')
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    blocker = '缺少已批准的 CLI Proxy Management API 契约与 AC-03 验证入口'

    def fake_run_agent_for_current_step(*_args, **_kwargs) -> AgentRunResult:
        return AgentRunResult(
            command=['tmux', 'send-keys', '-t', '%20', 'C-m'],
            returncode=1,
            stdout='',
            stderr='',
            backend='tmux-claude',
            status='blocked',
            run_dir=str(unit_dir / 'runs' / 'builder-run'),
            done_payload={'status': 'blocked', 'summary': blocker, 'run_id': 'builder-run'},
            runner_metadata={'backend': 'tmux-claude'},
        )

    monkeypatch.setattr(
        'workflow_controller.steps.builder.run_agent_for_current_step',
        fake_run_agent_for_current_step,
    )
    state = {
        'task_id': 'target-v1-8-1',
        'currentUnitId': 'unit-01',
        'workspacePath': str(workspace),
        'promptPath': str(prompt_path),
        'agentRunner': 'tmux-claude',
        'tmuxTarget': '%20',
    }

    with pytest.raises(RuntimeError) as exc_info:
        run_builder(state, unit_dir, dry_run=False)

    message = str(exc_info.value)
    assert 'Builder agent failed with exit code 1' in message
    assert 'tmux target %20 failed' in message
    assert blocker in message


def test_prepare_builder_prompt_includes_final_acceptance_rejection_feedback(tmp_path: Path) -> None:
    approvals_dir = tmp_path / 'approvals'
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    original_prompt = tmp_path / 'current-prompt.md'
    original_prompt.write_text('Original context.', encoding='utf-8')

    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    write_gate_file(requirements_path, '# Requirements & Acceptance Confirmation\n\nApproved requirement.\n')
    approve_gate_file(requirements_path, actor='tester')
    unit_plan_path = approvals_dir / 'unit-plan.md'
    write_gate_file(unit_plan_path, '# Unit Plan Confirmation\n\nApproved plan.\n')
    approve_gate_file(unit_plan_path, actor='tester')

    state = {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'humanGatesRequired': True,
        'workspacePath': str(tmp_path),
        'promptPath': str(original_prompt),
        'requestedOutcome': 'usable-system',
        'finalAcceptanceRejectionFeedback': (
            '# Final Acceptance Confirmation\n\n'
            'Reviewer note: import preview is missing retry state.\n'
        ),
        'objectiveCoverage': [
            {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
        ],
    }

    prompt_path = prepare_builder_prompt(state, approvals_dir, unit_dir)

    assert prompt_path is not None
    prompt = prompt_path.read_text(encoding='utf-8')
    assert 'Final acceptance rejection feedback' in prompt
    assert 'import preview is missing retry state' in prompt


def test_prepare_builder_prompt_includes_previous_verification_failure_feedback(tmp_path: Path) -> None:
    approvals_dir = tmp_path / 'approvals'
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    unit_dir.mkdir(parents=True)
    original_prompt = tmp_path / 'current-prompt.md'
    original_prompt.write_text('Original context.', encoding='utf-8')

    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    write_gate_file(requirements_path, '# Requirements & Acceptance Confirmation\n\nApproved requirement.\n')
    approve_gate_file(requirements_path, actor='tester')
    unit_plan_path = approvals_dir / 'unit-plan.md'
    write_gate_file(unit_plan_path, '# Unit Plan Confirmation\n\nApproved plan.\n')
    approve_gate_file(unit_plan_path, actor='tester')

    (unit_dir / 'verification.json').write_text(
        json.dumps({
            'unit_id': 'unit-01',
            'passed': False,
            'issues': [
                {
                    'severity': 'high',
                    'type': 'verification_command_failed',
                    'message': 'Command failed: pnpm exec playwright test',
                }
            ],
            'results': [
                {
                    'command': 'pnpm exec playwright test',
                    'returncode': 1,
                    'ok': False,
                    'stdout': 'Running 61 tests\nPrismaClientInitializationError\n',
                    'stderr': 'error: Environment variable not found: DATABASE_URL.\n',
                }
            ],
        }),
        encoding='utf-8',
    )

    state = {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'humanGatesRequired': True,
        'workspacePath': str(tmp_path),
        'promptPath': str(original_prompt),
        'requestedOutcome': 'usable-system',
        'objectiveCoverage': [
            {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
        ],
    }

    prompt_path = prepare_builder_prompt(state, approvals_dir, unit_dir)

    assert prompt_path is not None
    prompt = prompt_path.read_text(encoding='utf-8')
    assert 'Previous controller failure feedback' in prompt
    assert 'pnpm exec playwright test' in prompt
    assert 'returncode: 1' in prompt
    assert 'Environment variable not found: DATABASE_URL' in prompt
