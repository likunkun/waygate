from __future__ import annotations

import json
import re
import subprocess
import sys

import pytest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import workflow_controller.rrc_controller as rrc_controller_module
from workflow_controller.rrc_controller import RalphRefinerController, parse_args, run_unit_plan_drafter
from workflow_controller.steps._common import TestStrategistBlocked as StrategistBlocked
from workflow_controller.state_machine.transitions import reconcile_state, validate_objective_coverage


ROOT = Path(__file__).resolve().parents[2]


def run_rrc(*args: str, cwd: Path | None = None, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'workflow_controller.rrc_controller', *args],
        cwd=str(cwd or ROOT),
        text=True,
        input=input_text,
        capture_output=True,
        check=False,
    )


def test_init_creates_session_and_events_files(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'

    result = run_rrc('init', '--state-dir', str(state_dir))

    assert result.returncode == 0, result.stderr
    assert (state_dir / 'session.json').exists()
    assert (state_dir / 'events.jsonl').exists()

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'PLAN_CREATED'
    assert state['status'] == 'active'
    assert state['testStrategistEnabled'] is False
    assert state['codeSimplifierEnabled'] is True


def test_init_with_target_and_workspace_without_ralph_creates_target_acceptance_state(tmp_path: Path) -> None:
    workspace = tmp_path / 'union'
    workspace.mkdir()
    (workspace / 'task_plan.md').write_text('# Plan\n\nV3.0 target acceptance.\n', encoding='utf-8')
    state_dir = workspace / '.rrc-controller-v3.0'

    result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--target',
        'V3.0',
        '--runner',
        'tmux-claude',
        '--tmux-target',
        '3.0',
        '--force',
    )

    assert result.returncode == 0, result.stderr
    assert 'currentStep=REQUIREMENTS_DRAFT' in result.stdout
    assert 'nextAction=run_requirements_drafter' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['requestedOutcome'] == 'V3.0'
    assert state['feasibleOutcome'] == 'V3.0'
    assert state['workspacePath'] == str(workspace)
    assert state['currentUnitId'] == 'target-v3-0'
    assert state['units'][0]['id'] == 'target-v3-0'
    assert state['objectiveCoverage'][0]['units'] == ['target-v3-0']
    assert state['humanGatesRequired'] is True
    assert state['requirementsAccepted'] is False
    assert state['unitPlanAccepted'] is False
    assert state['agentRunner'] == 'tmux-claude'
    assert state['tmuxTarget'] == '3.0'
    assert str(workspace / 'task_plan.md') in state['targetContextFiles']
    assert Path(state['promptPath']).exists()
    assert 'Target acceptance: V3.0' in Path(state['promptPath']).read_text(encoding='utf-8')


def test_init_with_test_strategist_flag_enables_it_in_session(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'

    result = run_rrc(
        'init',
        '--state-dir', str(state_dir),
        '--test-strategist',
        '--test-strategist-command', 'my-codex exec -',
        '--test-strategist-env', 'HTTP_PROXY=http://127.0.0.1:7890',
        '--test-strategist-env', 'NO_PROXY=localhost',
    )

    assert result.returncode == 0, result.stderr
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['testStrategistEnabled'] is True
    ts = state['roleRunners']['test_strategist']
    assert ts['command'] == 'my-codex exec -'
    assert ts['env']['HTTP_PROXY'] == 'http://127.0.0.1:7890'
    assert ts['env']['NO_PROXY'] == 'localhost'


def test_init_test_strategist_flag_without_extras_uses_defaults(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'

    result = run_rrc('init', '--state-dir', str(state_dir), '--test-strategist')

    assert result.returncode == 0, result.stderr
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['testStrategistEnabled'] is True
    assert 'roleRunners' not in state or 'test_strategist' not in state.get('roleRunners', {})


def test_init_with_code_simplifier_flag_configures_refiner_runner_only(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'

    result = run_rrc(
        'init',
        '--state-dir', str(state_dir),
        '--runner', 'tmux-claude',
        '--tmux-target', '1.2',
        '--code-simplifier',
        '--code-simplifier-command', 'codex exec -',
        '--code-simplifier-env', 'SECRET_TOKEN',
        '--test-strategist',
        '--test-strategist-env', 'HTTP_PROXY=http://127.0.0.1:7890',
    )

    assert result.returncode == 0, result.stderr
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['codeSimplifierEnabled'] is True
    assert state['testStrategistEnabled'] is True
    assert state['roleRunners']['refiner'] == {
        'runner': 'subprocess',
        'command': 'codex exec -',
        'env': {'SECRET_TOKEN': ''},
    }
    assert state['roleRunners']['test_strategist'] == {
        'runner': 'subprocess',
        'env': {'HTTP_PROXY': 'http://127.0.0.1:7890'},
    }
    assert 'refiner' in state['roleRunners']
    assert 'test_strategist' in state['roleRunners']


def test_init_can_disable_default_code_simplifier(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'

    result = run_rrc('init', '--state-dir', str(state_dir), '--no-code-simplifier')

    assert result.returncode == 0, result.stderr
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['codeSimplifierEnabled'] is False


def test_status_reports_current_step_and_next_action(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir))
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc('status', '--state-dir', str(state_dir))

    assert result.returncode == 0, result.stderr
    assert 'currentStep=PLAN_CREATED' in result.stdout
    assert 'nextAction=require_scope_approval' in result.stdout


def _fake_agent_result(request, *, status: str = 'done', returncode: int = 0, stderr: str = ''):
    return SimpleNamespace(
        backend=request.backend,
        status=status,
        command=[request.agent_command or 'fake'],
        returncode=returncode,
        stdout='',
        stderr=stderr,
        run_dir=request.artifact_dir,
        prompt_path=request.prompt_path,
        done_payload={},
        runner_metadata={
            'role': request.role,
            'backend': request.backend,
            'agent_command': request.agent_command,
            'tmux_target': request.tmux_target,
            'env_keys': sorted(request.env),
        },
    )


def _write_valid_unit_plan(path: Path, *, command: str = 'pytest tests/test_delivery.py -q') -> None:
    path.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Test Case Matrix\n'
        '| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |\n'
        '| --- | --- | --- | --- | --- |\n'
        f'| AC-1 | TC-AC1 | integration | {command} | Delivery behavior works |\n\n'
        '## Controller State Patch\n\n'
        '```json\n'
        + json.dumps(
            {
                'currentUnitId': 'unit-01',
                'objectiveCoverage': [
                    {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'}
                ],
                'units': [
                    {
                        'id': 'unit-01',
                        'name': 'Delivery unit',
                        'passes': False,
                        'test_cases': [
                            {
                                'id': 'TC-AC1',
                                'acceptance_criterion': 'AC-1',
                                'layer': 'integration',
                                'command': command,
                                'expected': 'Delivery behavior works',
                            }
                        ],
                        'verification_commands': [command],
                    }
                ],
            }
        )
        + '\n```\n',
        encoding='utf-8',
    )


def _controller_state_for_unit_plan(workspace: Path) -> dict[str, Any]:
    return {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'currentStep': 'UNIT_PLAN_DRAFT',
        'lastVerifiedStep': 'REQUIREMENTS_DRAFT',
        'status': 'active',
        'requestedOutcome': 'usable-system',
        'feasibleOutcome': 'usable-system',
        'agentRunner': 'tmux-claude',
        'workspacePath': str(workspace),
        'testStrategistEnabled': True,
        'humanGatesRequired': True,
        'requirementsAccepted': True,
        'unitPlanAccepted': False,
        'objectiveCoverage': [
            {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {'id': 'unit-01', 'name': 'Delivery unit', 'scope': ['Implement delivery behavior'], 'passes': False},
        ],
    }


def test_unit_plan_drafter_persists_test_strategist_artifacts(tmp_path: Path, monkeypatch) -> None:
    approvals_dir = tmp_path / 'approvals'
    artifacts_dir = tmp_path / 'artifacts'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(
        '# Requirements & Acceptance Confirmation\n\n'
        '## 3. Acceptance Criteria\n'
        '- AC-1: Import retry state is visible.\n\n'
        '## 4. Test Strategy\n'
        '- E2E covers AC-1.\n',
        encoding='utf-8',
    )
    state = {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'requestedOutcome': 'usable-system',
        'feasibleOutcome': 'usable-system',
        'agentRunner': 'tmux-claude',
        'workspacePath': str(workspace),
        'testStrategistEnabled': True,
        'unitPlanRetryCount': 2,
        'roleRunners': {
            'test_strategist': {
                'runner': 'subprocess',
                'command': 'fake-strategist -',
                'env': {'SECRET_TOKEN': 'redacted-value'},
            },
        },
        'objectiveCoverage': [
            {'objective': 'Import retry state is visible', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {
                'id': 'unit-01',
                'name': 'Import retry visibility',
                'scope': ['Expose retry state in import UI'],
                'done_when': ['AC-1 is visible in browser'],
            },
        ],
    }

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            prompt = request.prompt_path.read_text(encoding='utf-8')
            assert 'AC-1: Import retry state is visible' in prompt
            assert 'Expose retry state in import UI' in prompt
            assert 'verification requirements' in prompt
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC1-E2E',
                                        'layer': 'e2e',
                                        'command': 'pnpm exec playwright test import-retry.spec.ts --workers=1',
                                        'evidence': '',
                                        'expected': 'Retry state is visible in the browser',
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
            (request.artifact_dir / 'test-strategy.md').write_text(
                '# Test Strategy\n\nAC-1 -> TC-AC1-E2E via browser-visible E2E.\n',
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': []}),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-review-package.json').write_text(
                json.dumps({'ready_for_review': True, 'acceptance_criteria': ['AC-1']}),
                encoding='utf-8',
            )
        else:
            (request.artifact_dir / 'unit-plan-body.md').write_text(
                '# Unit Plan Confirmation\n\n'
                '## Test Case Matrix\n'
                '| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |\n'
                '| --- | --- | --- | --- | --- |\n'
                '| AC-1 | TC-AC1-E2E | e2e | pnpm exec playwright test import-retry.spec.ts --workers=1 | Retry state visible |\n\n'
                '## Controller State Patch\n\n'
                '```json\n'
                '{"currentUnitId":"unit-01","objectiveCoverage":[{"objective":"Import retry state is visible","units":["unit-01"],"status":"partial"}],"units":[{"id":"unit-01","name":"Import retry visibility","passes":false,"test_cases":[{"id":"TC-AC1-E2E","acceptance_criterion":"AC-1","layer":"e2e","command":"pnpm exec playwright test import-retry.spec.ts --workers=1","expected":"Retry state visible"}],"verification_commands":["pnpm exec playwright test import-retry.spec.ts --workers=1"],"verification_env":{"DATABASE_URL":"file:test.db"}}]}\n'
                '```\n',
                encoding='utf-8',
            )
        return SimpleNamespace(
            backend=request.backend,
            status='done',
            command=[request.agent_command or 'fake'],
            returncode=0,
            stdout='',
            stderr='',
            run_dir=request.artifact_dir,
            prompt_path=request.prompt_path,
            done_payload={},
            runner_metadata={
                'role': request.role,
                'backend': request.backend,
                'agent_command': request.agent_command,
                'tmux_target': request.tmux_target,
                'env_keys': sorted(request.env),
            },
        )

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    run_unit_plan_drafter(state, approvals_dir, artifacts_dir)

    draft_dir = artifacts_dir / 'unit-plan-draft'
    assert (draft_dir / 'test-strategy.json').exists()
    assert (draft_dir / 'unit-plan-gap-report.json').exists()
    assert (draft_dir / 'unit-plan-review-package.json').exists()
    assert (draft_dir / 'test-strategy.md').read_text(encoding='utf-8').startswith('# Test Strategy')
    summary = json.loads((draft_dir / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['test_strategist']['enabled'] is True
    assert summary['test_strategist']['actual_independence'] == 'role-runner'
    assert summary['test_strategist']['gap_counts'] == {'critical': 0, 'major': 0, 'minor': 0}
    assert summary['test_strategist']['planner_retry_count'] == 2
    assert summary['test_strategist']['fallback']['used'] is False
    assert summary['test_strategist']['runner']['env_keys'] == ['SECRET_TOKEN']
    assert 'redacted-value' not in json.dumps(summary)


def test_unit_plan_drafter_records_critical_gap_for_static_only_strategy(tmp_path: Path, monkeypatch) -> None:
    approvals_dir = tmp_path / 'approvals'
    artifacts_dir = tmp_path / 'artifacts'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(
        '# Requirements & Acceptance Confirmation\n\n'
        '## 3. Acceptance Criteria\n'
        '- AC-1: Browser retry state is visible.\n',
        encoding='utf-8',
    )
    state = {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'requestedOutcome': 'usable-system',
        'feasibleOutcome': 'usable-system',
        'agentRunner': 'tmux-claude',
        'workspacePath': str(workspace),
        'testStrategistEnabled': True,
        'objectiveCoverage': [
            {'objective': 'Browser retry state is visible', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {'id': 'unit-01', 'name': 'Import retry visibility', 'scope': ['Expose retry state']},
        ],
    }

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC1-STATIC',
                                        'layer': 'static',
                                        'command': 'pnpm exec tsc --noEmit',
                                        'expected': 'Types compile',
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
        else:
            (request.artifact_dir / 'unit-plan-body.md').write_text('# Unit Plan Confirmation\n', encoding='utf-8')
        return SimpleNamespace(
            backend=request.backend,
            status='done',
            command=[request.agent_command or 'fake'],
            returncode=0,
            stdout='',
            stderr='',
            run_dir=request.artifact_dir,
            prompt_path=request.prompt_path,
            done_payload={},
            runner_metadata={'role': request.role, 'backend': request.backend, 'env_keys': []},
        )

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    run_unit_plan_drafter(state, approvals_dir, artifacts_dir)

    draft_dir = artifacts_dir / 'unit-plan-draft'
    gap_report = json.loads((draft_dir / 'unit-plan-gap-report.json').read_text(encoding='utf-8'))
    assert gap_report['gap_counts']['critical'] == 1
    assert gap_report['gaps'][0]['severity'] == 'Critical'
    assert gap_report['gaps'][0]['type'] == 'static_only_coverage'
    summary = json.loads((draft_dir / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['test_strategist']['gap_counts']['critical'] == 1
    gate_path = approvals_dir / 'unit-plan.md'
    assert gate_path.exists(), 'Gate must be generated for human review even when critical gaps remain'
    gate_body = gate_path.read_text(encoding='utf-8')
    assert 'Unresolved Critical' in gate_body
    assert 'static_only_coverage' in gate_body


def test_unit_plan_drafter_materializes_strategy_artifacts_when_strategist_fails(tmp_path: Path, monkeypatch) -> None:
    approvals_dir = tmp_path / 'approvals'
    artifacts_dir = tmp_path / 'artifacts'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(
        '# Requirements & Acceptance Confirmation\n\n'
        '## 3. Acceptance Criteria\n'
        '- AC-1: Browser retry state is visible.\n',
        encoding='utf-8',
    )
    state = {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'requestedOutcome': 'usable-system',
        'feasibleOutcome': 'usable-system',
        'agentRunner': 'tmux-claude',
        'workspacePath': str(workspace),
        'testStrategistEnabled': True,
        'objectiveCoverage': [
            {'objective': 'Browser retry state is visible', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {'id': 'unit-01', 'name': 'Import retry visibility', 'scope': ['Expose retry state']},
        ],
    }

    def fake_run_agent_backend(request):
        if request.role is None:
            (request.artifact_dir / 'unit-plan-body.md').write_text('# Unit Plan Confirmation\n', encoding='utf-8')
        return SimpleNamespace(
            backend=request.backend,
            status='failed' if request.role == 'test_strategist' else 'done',
            command=[request.agent_command or 'fake'],
            returncode=1 if request.role == 'test_strategist' else 0,
            stdout='',
            stderr='strategist crashed',
            run_dir=request.artifact_dir,
            prompt_path=request.prompt_path,
            done_payload={},
            runner_metadata={'role': request.role, 'backend': request.backend, 'env_keys': []},
        )

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    run_unit_plan_drafter(state, approvals_dir, artifacts_dir)

    draft_dir = artifacts_dir / 'unit-plan-draft'
    assert json.loads((draft_dir / 'test-strategy.json').read_text(encoding='utf-8')) == {
        'acceptance_criteria': []
    }
    gap_report = json.loads((draft_dir / 'unit-plan-gap-report.json').read_text(encoding='utf-8'))
    assert gap_report['gap_counts']['critical'] == 0
    summary = json.loads((draft_dir / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['test_strategist']['actual_independence'] == 'same_family_fallback'
    assert summary['test_strategist']['independence'] == 'degraded'
    assert summary['test_strategist']['fallback'] == {
        'used': True,
        'reason': 'Test strategist failed with exit code 1',
    }


def test_unit_plan_drafter_rewrites_stale_strategist_artifacts_on_rerun(tmp_path: Path, monkeypatch) -> None:
    approvals_dir = tmp_path / 'approvals'
    artifacts_dir = tmp_path / 'artifacts'
    draft_dir = artifacts_dir / 'unit-plan-draft'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    draft_dir.mkdir(parents=True)
    (draft_dir / 'unit-plan-gap-report.json').write_text(
        json.dumps(
            {
                'gap_counts': {'critical': 1, 'major': 0, 'minor': 0},
                'gaps': [{'severity': 'Critical', 'type': 'stale_gap', 'message': 'old gap'}],
            }
        ),
        encoding='utf-8',
    )
    (draft_dir / 'unit-plan-review-package.json').write_text(
        json.dumps({'ready_for_review': True, 'stale': True}),
        encoding='utf-8',
    )
    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(
        '# Requirements & Acceptance Confirmation\n\n'
        '## 3. Acceptance Criteria\n'
        '- AC-1: Browser retry state is visible.\n',
        encoding='utf-8',
    )
    state = {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'requestedOutcome': 'usable-system',
        'feasibleOutcome': 'usable-system',
        'agentRunner': 'tmux-claude',
        'workspacePath': str(workspace),
        'testStrategistEnabled': True,
        'objectiveCoverage': [
            {'objective': 'Browser retry state is visible', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {'id': 'unit-01', 'name': 'Import retry visibility', 'scope': ['Expose retry state']},
        ],
    }

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            static_gap = {
                'severity': 'Critical',
                'type': 'static_only_coverage',
                'message': 'AC-1 is covered only by static checks',
            }
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {'id': 'TC-AC1-STATIC', 'layer': 'static', 'command': 'pnpm exec tsc --noEmit'}
                                ],
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gap_counts': {'critical': 1, 'major': 0, 'minor': 0}, 'gaps': [static_gap]}),
                encoding='utf-8',
            )
        else:
            (request.artifact_dir / 'unit-plan-body.md').write_text('# Unit Plan Confirmation\n', encoding='utf-8')
        return SimpleNamespace(
            backend=request.backend,
            status='done',
            command=[request.agent_command or 'fake'],
            returncode=0,
            stdout='',
            stderr='',
            run_dir=request.artifact_dir,
            prompt_path=request.prompt_path,
            done_payload={},
            runner_metadata={'role': request.role, 'backend': request.backend, 'env_keys': []},
        )

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    run_unit_plan_drafter(state, approvals_dir, artifacts_dir)

    gap_report = json.loads((draft_dir / 'unit-plan-gap-report.json').read_text(encoding='utf-8'))
    assert gap_report['gap_counts']['critical'] == 1
    assert gap_report['gaps'] == [
        {
            'severity': 'Critical',
            'type': 'static_only_coverage',
            'message': 'AC-1 is covered only by static checks',
        }
    ]
    review_package = json.loads((draft_dir / 'unit-plan-review-package.json').read_text(encoding='utf-8'))
    assert review_package['ready_for_review'] is False
    assert 'stale' not in review_package


def test_unit_plan_drafter_runs_planner_before_strategist_and_passes_body_in_prompt(tmp_path: Path, monkeypatch) -> None:
    approvals_dir = tmp_path / 'approvals'
    artifacts_dir = tmp_path / 'artifacts'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(
        '# Requirements & Acceptance Confirmation\n\n- AC-1: Delivery behavior works.\n',
        encoding='utf-8',
    )
    state = _controller_state_for_unit_plan(workspace)
    calls: list[str | None] = []

    def fake_run_agent_backend(request):
        calls.append(request.role)
        if request.role == 'test_strategist':
            prompt = request.prompt_path.read_text(encoding='utf-8')
            assert '# Unit Plan Confirmation' in prompt
            assert 'TC-AC1' in prompt
            assert 'Test Strategist internal state' not in prompt
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC1',
                                        'layer': 'integration',
                                        'command': 'pytest tests/test_delivery.py -q',
                                        'expected': 'Delivery behavior works',
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': []}),
                encoding='utf-8',
            )
        else:
            planner_prompt = request.prompt_path.read_text(encoding='utf-8')
            assert 'unit-plan-gap-report' not in planner_prompt
            assert 'Test Strategist internal state' not in planner_prompt
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    run_unit_plan_drafter(state, approvals_dir, artifacts_dir)

    assert calls == [None, 'test_strategist']


def test_codex_patcher_fills_critical_gap_and_enters_unit_plan_gate(tmp_path: Path, monkeypatch) -> None:
    """When initial strategist finds a Critical gap, the Codex patcher (2nd run) fills it.
    No Planner revision loop occurs."""
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')
    strategist_calls = 0
    planner_prompts: list[str] = []

    def fake_run_agent_backend(request):
        nonlocal strategist_calls
        if request.role == 'test_strategist':
            strategist_calls += 1
            # Initial run: returns a Critical gap; patcher (2nd run): returns no gaps
            gaps = [] if strategist_calls == 2 else [
                {
                    'id': 'GAP-AC1',
                    'severity': 'Critical',
                    'type': 'missing_acceptance_criterion_mapping',
                    'message': 'AC-1 has no mapped behavioral test',
                }
            ]
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC1',
                                        'layer': 'integration',
                                        'command': 'pytest tests/test_delivery.py -q',
                                        'expected': 'Delivery behavior works',
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': gaps}),
                encoding='utf-8',
            )
        else:
            planner_prompts.append(request.prompt_path.read_text(encoding='utf-8'))
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['status'] == 'active'
    assert state['testStrategistPlannerRetryCount'] == 0, 'Planner is no longer retried; patcher handles gaps'
    assert strategist_calls == 2, 'initial strategist run + patcher run'
    assert not any('Critical Test Strategy Gap Feedback' in p for p in planner_prompts), \
        'No Planner revision prompt should be sent; Codex patcher handles gap remediation'
    assert not (state_dir / 'approvals' / 'unit-plan.md').read_text(encoding='utf-8').count('GAP-AC1')
    summary = json.loads((state_dir / 'artifacts' / 'unit-plan-draft' / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['test_strategist']['planner_retry_count'] == 0
    assert summary['test_strategist']['gap_counts']['critical'] == 0


def test_controller_renders_major_minor_gap_report_in_existing_unit_plan_gate(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC1',
                                        'layer': 'integration',
                                        'command': 'pytest tests/test_delivery.py -q',
                                        'expected': 'Delivery behavior works',
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps(
                    {
                        'gaps': [
                            {
                                'id': 'MAJOR-AC1',
                                'severity': 'Major',
                                'type': 'weak_manual_evidence',
                                'message': 'Manual evidence should name the approval artifact',
                            },
                            {
                                'id': 'MINOR-AC1',
                                'severity': 'Minor',
                                'type': 'wording_gap',
                                'message': 'Expected result could be more specific',
                            },
                        ]
                    }
                ),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['nextAllowedActions'] == ['check_unit_plan_approval']
    gate_body = (state_dir / 'approvals' / 'unit-plan.md').read_text(encoding='utf-8')
    review_package = json.loads(
        (state_dir / 'artifacts' / 'unit-plan-draft' / 'unit-plan-review-package.json').read_text(encoding='utf-8')
    )
    assert review_package['gap_report']['gaps'] == [
        {
            'id': 'MAJOR-AC1',
            'severity': 'Major',
            'type': 'weak_manual_evidence',
            'message': 'Manual evidence should name the approval artifact',
        },
        {
            'id': 'MINOR-AC1',
            'severity': 'Minor',
            'type': 'wording_gap',
            'message': 'Expected result could be more specific',
        },
    ]
    assert '## Test Strategy Gap Report' in gate_body
    assert 'MAJOR-AC1' in gate_body
    assert 'Manual evidence should name the approval artifact' in gate_body
    assert 'MINOR-AC1' in gate_body
    assert 'Expected result could be more specific' in gate_body
    assert 'WAITING_TEST_STRATEGY_APPROVAL' not in json.dumps(state)


def test_suggested_fix_appears_in_major_minor_gap_report_in_gate(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': [{'id': 'AC-1', 'test_cases': [{'id': 'TC-1', 'layer': 'unit', 'command': 'pytest', 'expected': 'pass'}]}]}),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': [{
                    'id': 'MAJOR-AC1',
                    'severity': 'Major',
                    'type': 'weak_manual_evidence',
                    'message': 'Manual evidence should name the approval artifact',
                    'suggested_fix': 'Add a screenshot path or artifact name as evidence for AC-1',
                }]}),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)
    controller.run_once()

    gate_body = (state_dir / 'approvals' / 'unit-plan.md').read_text(encoding='utf-8')
    assert 'Add a screenshot path or artifact name as evidence for AC-1' in gate_body


def test_suggested_fix_appears_in_codex_patcher_prompt(tmp_path: Path, monkeypatch) -> None:
    """suggested_fix from the gap report is forwarded to the Codex patcher prompt
    so Codex knows exactly how to fill the gap."""
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Behavior works.\n', encoding='utf-8')

    patcher_prompts: list[str] = []

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': [{'id': 'AC-1', 'test_cases': []}]}),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': [{
                    'id': 'CRIT-AC1',
                    'severity': 'Critical',
                    'type': 'missing_acceptance_criterion_mapping',
                    'message': 'AC-1 has no mapped test cases',
                    'suggested_fix': 'Add a Playwright E2E test that verifies AC-1 behavior end-to-end',
                }]}),
                encoding='utf-8',
            )
            prompt = request.prompt_path.read_text(encoding='utf-8')
            if 'codex_patch' in prompt:
                patcher_prompts.append(prompt)
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)
    controller.run_once()

    assert patcher_prompts, 'Expected Codex patcher to be invoked'
    assert 'Add a Playwright E2E test that verifies AC-1 behavior end-to-end' in patcher_prompts[0]


def test_critical_gap_escalates_to_human_review_after_max_retries(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(workspace)
    initial_state['testStrategistCriticalMaxReworks'] = 0
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': []}),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': [{
                    'id': 'CRITICAL-AC1',
                    'severity': 'Critical',
                    'type': 'missing_acceptance_criterion_mapping',
                    'message': 'AC-1 has no mapped behavioral test',
                    'suggested_fix': 'Add a pytest integration test for AC-1',
                }]}),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL', f"Expected human review, got: {state['currentStep']}"
    assert state.get('status') != 'blocked'
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    assert gate_path.exists(), 'Gate file must exist for human review'
    gate_body = gate_path.read_text(encoding='utf-8')
    assert 'CRITICAL-AC1' in gate_body
    assert 'AC-1 has no mapped behavioral test' in gate_body
    assert 'Add a pytest integration test for AC-1' in gate_body



def test_e2e_test_strategist_unit_plan_flow(tmp_path: Path, monkeypatch) -> None:
    disabled_workspace = tmp_path / 'disabled-workspace'
    disabled_workspace.mkdir()
    disabled_state_dir = tmp_path / 'disabled-state'
    disabled_controller = RalphRefinerController(state_dir=disabled_state_dir, auto_approve=True)
    disabled_state = _controller_state_for_unit_plan(disabled_workspace)
    disabled_state['testStrategistEnabled'] = False
    disabled_controller.init_state(disabled_state, force=True)
    disabled_requirements = disabled_state_dir / 'approvals' / 'requirements-and-acceptance.md'
    disabled_requirements.parent.mkdir(parents=True, exist_ok=True)
    disabled_requirements.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')

    enabled_workspace = tmp_path / 'enabled-workspace'
    enabled_workspace.mkdir()
    enabled_state_dir = tmp_path / 'enabled-state'
    enabled_controller = RalphRefinerController(state_dir=enabled_state_dir, auto_approve=True)
    enabled_state = _controller_state_for_unit_plan(enabled_workspace)
    enabled_state['roleRunners'] = {
        'test_strategist': {
            'runner': 'subprocess',
            'command': 'codex exec --dangerously-bypass-approvals-and-sandbox -',
            'env': {
                'HTTP_PROXY': 'http://127.0.0.1:7890',
                'HTTPS_PROXY': 'http://127.0.0.1:7890',
                'NO_PROXY': 'localhost,127.0.0.1',
                'SECRET_TOKEN': 'super-secret-token',
            },
        }
    }
    enabled_controller.init_state(enabled_state, force=True)
    enabled_requirements = enabled_state_dir / 'approvals' / 'requirements-and-acceptance.md'
    enabled_requirements.parent.mkdir(parents=True, exist_ok=True)
    enabled_requirements.write_text(
        '# Requirements\n\n'
        '- AC-1: Delivery behavior works.\n'
        '- AC-2: Test strategy gaps are visible to humans.\n',
        encoding='utf-8',
    )

    calls: list[tuple[str | None, dict[str, str]]] = []
    planner_prompts: list[str] = []
    strategist_prompts: list[str] = []
    strategist_calls_by_state: dict[Path, int] = {}

    def fake_run_agent_backend(request):
        calls.append((request.role, dict(request.env)))
        if request.role == 'test_strategist':
            strategist_prompts.append(request.prompt_path.read_text(encoding='utf-8'))
            call_number = strategist_calls_by_state.get(request.artifact_dir, 0) + 1
            strategist_calls_by_state[request.artifact_dir] = call_number
            gaps = [
                {
                    'id': 'GAP-AC1',
                    'severity': 'Critical',
                    'type': 'missing_acceptance_criterion_mapping',
                    'message': 'AC-1 has no mapped behavioral test',
                }
            ] if call_number == 1 else [
                {
                    'id': 'MAJOR-AC2',
                    'severity': 'Major',
                    'type': 'weak_manual_evidence',
                    'message': 'Human evidence should name approvals/unit-plan.md',
                },
                {
                    'id': 'MINOR-AC2',
                    'severity': 'Minor',
                    'type': 'wording_gap',
                    'message': 'Expected result can be more specific',
                },
            ]
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC1',
                                        'layer': 'integration',
                                        'command': 'pytest tests/test_delivery.py -q',
                                        'fixture': 'fake unit planner and strategist',
                                        'environment': 'temporary state dir',
                                        'evidence': 'approvals/unit-plan.md',
                                        'expected': 'Delivery behavior works',
                                    }
                                ],
                            },
                            {
                                'id': 'AC-2',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC2',
                                        'layer': 'manual',
                                        'command': 'manual approval artifact inspection',
                                        'fixture': 'Major and Minor gap report',
                                        'environment': 'temporary state dir',
                                        'evidence': 'approvals/unit-plan.md contains Test Strategy Gap Report',
                                        'expected': 'Gaps are visible in the existing Unit Plan gate',
                                    }
                                ],
                            },
                        ]
                    }
                ),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(json.dumps({'gaps': gaps}), encoding='utf-8')
        else:
            planner_prompts.append(request.prompt_path.read_text(encoding='utf-8'))
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    disabled_result = disabled_controller.run_once()

    assert disabled_result['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    disabled_draft_dir = disabled_state_dir / 'artifacts' / 'unit-plan-draft'
    assert (disabled_state_dir / 'approvals' / 'unit-plan.md').exists()
    assert not (disabled_draft_dir / 'test-strategy.json').exists()
    assert not (disabled_draft_dir / 'unit-plan-gap-report.json').exists()
    assert not (disabled_draft_dir / 'unit-plan-review-package.json').exists()

    enabled_result = enabled_controller.run_once()

    assert enabled_result['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert enabled_result['status'] == 'active'
    assert enabled_result['testStrategistPlannerRetryCount'] == 0, 'Planner runs once; patcher handles gaps'
    assert 'WAITING_TEST_STRATEGY_APPROVAL' not in json.dumps(enabled_result)
    role_calls = [role for role, _env in calls]
    # disabled planner, enabled planner, initial strategist, patcher (no Planner revision loop)
    assert role_calls == [None, None, 'test_strategist', 'test_strategist']
    strategist_envs = [env for role, env in calls if role == 'test_strategist']
    non_strategist_envs = [env for role, env in calls if role is None]
    assert all(env['HTTP_PROXY'] == 'http://127.0.0.1:7890' for env in strategist_envs)
    assert all('HTTP_PROXY' not in env for env in non_strategist_envs)
    assert not any('Critical Test Strategy Gap Feedback' in prompt for prompt in planner_prompts), \
        'Planner should not receive gap feedback; Codex patcher handles remediation'
    assert any('AC-1: Delivery behavior works' in prompt and '# Unit Plan Confirmation' in prompt for prompt in strategist_prompts)

    enabled_draft_dir = enabled_state_dir / 'artifacts' / 'unit-plan-draft'
    gate_body = (enabled_state_dir / 'approvals' / 'unit-plan.md').read_text(encoding='utf-8')
    summary = json.loads((enabled_draft_dir / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    review_package = json.loads((enabled_draft_dir / 'unit-plan-review-package.json').read_text(encoding='utf-8'))
    gap_report = json.loads((enabled_draft_dir / 'unit-plan-gap-report.json').read_text(encoding='utf-8'))
    assert (enabled_draft_dir / 'test-strategy.json').exists()
    assert (enabled_draft_dir / 'test-strategy.md').exists()
    assert summary['test_strategist']['enabled'] is True
    assert summary['test_strategist']['runner']['env_keys'] == [
        'HTTPS_PROXY',
        'HTTP_PROXY',
        'NO_PROXY',
        'SECRET_TOKEN',
    ]
    assert summary['test_strategist']['gap_counts'] == {'critical': 0, 'major': 1, 'minor': 1}
    assert summary['test_strategist']['planner_retry_count'] == 0
    assert review_package['ready_for_review'] is True
    assert gap_report['gap_counts'] == {'critical': 0, 'major': 1, 'minor': 1}
    assert 'GAP-AC1' not in gate_body
    assert '## Test Strategy Gap Report' in gate_body
    assert 'MAJOR-AC2' in gate_body
    assert 'MINOR-AC2' in gate_body
    serialized_artifacts = json.dumps(summary) + json.dumps(review_package) + gate_body
    assert 'super-secret-token' not in serialized_artifacts
    assert 'http://127.0.0.1:7890' not in serialized_artifacts



def test_controller_escalates_to_human_review_after_third_unresolved_critical_gap(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')
    strategist_calls = 0

    def fake_run_agent_backend(request):
        nonlocal strategist_calls
        if request.role == 'test_strategist':
            strategist_calls += 1
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': []}),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': [{
                    'id': 'GAP-AC1',
                    'severity': 'Critical',
                    'type': 'missing_acceptance_criterion_mapping',
                    'message': 'AC-1 has no mapped behavioral test',
                }]}),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state.get('status') != 'blocked'
    assert state['testStrategistPlannerRetryCount'] == 0, 'Planner is no longer retried for test strategy gaps'
    assert strategist_calls == 2, 'initial strategist run + patcher run (both return gappy strategy)'
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    assert gate_path.exists()
    gate_body = gate_path.read_text(encoding='utf-8')
    assert 'GAP-AC1' in gate_body
    assert 'Unresolved Critical' in gate_body


def test_controller_blocks_when_test_strategist_fallback_is_not_allowed(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(workspace)
    initial_state['allowTestStrategistFallback'] = False
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            return _fake_agent_result(request, status='failed', returncode=127, stderr='codex: not found')
        _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['status'] == 'blocked'
    assert state['currentStep'] == 'UNIT_PLAN_DRAFT'
    assert 'Test strategist failed with exit code 127' in state['blockedReason']
    assert 'fallback is not allowed' in state['blockedReason']


def test_controller_continues_with_degraded_independence_when_strategist_fallback_allowed(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')
    strategist_calls = 0

    def fake_run_agent_backend(request):
        nonlocal strategist_calls
        if request.role == 'test_strategist':
            strategist_calls += 1
            return _fake_agent_result(request, status='failed', returncode=127, stderr='codex: not found')
        _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['status'] == 'active'
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['testStrategistPlannerRetryCount'] == 0
    assert strategist_calls == 1
    draft_dir = state_dir / 'artifacts' / 'unit-plan-draft'
    gap_report = json.loads((draft_dir / 'unit-plan-gap-report.json').read_text(encoding='utf-8'))
    assert gap_report['gap_counts']['critical'] == 0
    summary = json.loads((draft_dir / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['test_strategist']['actual_independence'] == 'same_family_fallback'
    assert summary['test_strategist']['independence'] == 'degraded'
    assert summary['test_strategist']['fallback'] == {
        'used': True,
        'reason': 'Test strategist failed with exit code 127',
    }



def test_controller_ignores_partial_critical_artifacts_when_strategist_fallback_allowed(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')
    strategist_calls = 0

    def fake_run_agent_backend(request):
        nonlocal strategist_calls
        if request.role == 'test_strategist':
            strategist_calls += 1
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps(
                    {
                        'gap_counts': {'critical': 1, 'major': 0, 'minor': 0},
                        'gaps': [
                            {
                                'id': 'PARTIAL-GAP',
                                'severity': 'Critical',
                                'type': 'partial_failed_strategist_output',
                                'message': 'partial output before crash',
                            }
                        ],
                    }
                ),
                encoding='utf-8',
            )
            return _fake_agent_result(request, status='failed', returncode=1, stderr='strategist crashed')
        _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['status'] == 'active'
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert strategist_calls == 1
    draft_dir = state_dir / 'artifacts' / 'unit-plan-draft'
    gap_report = json.loads((draft_dir / 'unit-plan-gap-report.json').read_text(encoding='utf-8'))
    assert gap_report['gap_counts']['critical'] == 0
    assert gap_report['gaps'] == []
    assert 'PARTIAL-GAP' not in json.dumps(gap_report)
    summary = json.loads((draft_dir / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['test_strategist']['actual_independence'] == 'same_family_fallback'
    assert summary['test_strategist']['fallback']['reason'] == 'Test strategist failed with exit code 1'



def test_controller_resets_stale_strategist_retry_count_for_fresh_unit_plan_cycle(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(workspace)
    initial_state['testStrategistPlannerRetryCount'] = 2
    initial_state['unitPlanRetryCount'] = 2
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC1',
                                        'layer': 'integration',
                                        'command': 'pytest tests/test_delivery.py -q',
                                        'expected': 'Delivery behavior works',
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': []}),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['testStrategistPlannerRetryCount'] == 0
    assert state['unitPlanRetryCount'] == 0
    summary = json.loads((state_dir / 'artifacts' / 'unit-plan-draft' / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['test_strategist']['planner_retry_count'] == 0


def test_controller_escalates_unit_plan_gate_revision_to_human_after_unresolved_critical_gap(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(workspace)
    initial_state['currentStep'] = 'WAITING_UNIT_PLAN_APPROVAL'
    initial_state['unitPlanDraftGenerated'] = True
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')
    (approvals_dir / 'unit-plan.md').write_text('# Unit Plan Confirmation\n\nReviewer note: add behavioral coverage.\n', encoding='utf-8')
    strategist_calls = 0

    def fake_run_agent_backend(request):
        nonlocal strategist_calls
        if request.role == 'test_strategist':
            strategist_calls += 1
            (request.artifact_dir / 'test-strategy.json').write_text(json.dumps({'acceptance_criteria': []}), encoding='utf-8')
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps(
                    {
                        'gaps': [
                            {
                                'id': 'GAP-REVISION',
                                'severity': 'Critical',
                                'type': 'missing_acceptance_criterion_mapping',
                                'message': 'AC-1 has no mapped behavioral test',
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    controller.revise_human_gate('unit-plan')

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state.get('status') != 'blocked'
    assert state['testStrategistPlannerRetryCount'] == 0, 'Planner is no longer retried for test strategy gaps'
    assert strategist_calls == 2, 'initial strategist run + patcher run (both return gappy strategy)'
    gate_body = (state_dir / 'approvals' / 'unit-plan.md').read_text(encoding='utf-8')
    assert 'GAP-REVISION' in gate_body
    assert 'Unresolved Critical' in gate_body


def test_controller_escalates_final_acceptance_unit_plan_reroute_to_human_after_unresolved_critical_gap(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(workspace)
    initial_state.update(
        {
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'scopeApproved': True,
            'unitPlanAccepted': True,
            'unitPlanDraftGenerated': True,
            'finalAcceptanceAccepted': False,
        }
    )
    initial_state['objectiveCoverage'][0]['status'] = 'covered'
    initial_state['units'][0]['passes'] = True
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')
    (approvals_dir / 'unit-plan.md').write_text('# Unit Plan Confirmation\n', encoding='utf-8')
    (approvals_dir / 'final-acceptance.md').write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [x] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [ ] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        'Reviewer note: final acceptance shows verification commands need broader coverage.\n',
        encoding='utf-8',
    )
    strategist_calls = 0

    def fake_run_agent_backend(request):
        nonlocal strategist_calls
        if request.role == 'test_strategist':
            strategist_calls += 1
            (request.artifact_dir / 'test-strategy.json').write_text(json.dumps({'acceptance_criteria': []}), encoding='utf-8')
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps(
                    {
                        'gaps': [
                            {
                                'id': 'GAP-FINAL',
                                'severity': 'Critical',
                                'type': 'missing_acceptance_criterion_mapping',
                                'message': 'AC-1 has no mapped behavioral test',
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    controller.reject_final_acceptance_gate()

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state.get('status') != 'blocked'
    assert state['testStrategistPlannerRetryCount'] == 0, 'Planner is no longer retried for test strategy gaps'
    assert strategist_calls == 2, 'initial strategist run + patcher run (both return gappy strategy)'
    gate_body = (state_dir / 'approvals' / 'unit-plan.md').read_text(encoding='utf-8')
    assert 'GAP-FINAL' in gate_body
    assert 'Unresolved Critical' in gate_body


def test_dry_run_until_done_advances_workflow_and_writes_artifacts(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir))
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc('run', '--state-dir', str(state_dir), '--dry-run', '--until-done')

    assert result.returncode == 0, result.stderr
    assert 'currentStep=DONE status=done' in result.stdout

    session = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert session['currentStep'] == 'DONE'
    assert session['status'] == 'done'

    unit_dir = state_dir / 'artifacts' / 'unit-01'
    assert (unit_dir / 'builder-summary.json').exists()
    assert (unit_dir / 'review.json').exists()
    assert (unit_dir / 'verification.json').exists()
    assert (state_dir / 'approvals' / 'scope-approval.json').exists()
    assert (state_dir / 'approvals' / 'release-approval.json').exists()


def test_non_dry_run_until_done_with_auto_approve_advances_to_done(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir), '--auto-approve')
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc('run', '--state-dir', str(state_dir), '--until-done', '--auto-approve')

    assert result.returncode == 0, result.stderr
    assert 'currentStep=DONE status=done' in result.stdout

    session = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert session['currentStep'] == 'DONE'
    assert session['status'] == 'done'
    assert (state_dir / 'approvals' / 'release-approval.json').exists()


def test_cli_rejects_abbreviated_long_options(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir))
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approv')

    assert result.returncode != 0
    assert 'unrecognized arguments: --auto-approv' in result.stderr


def test_drive_and_start_default_to_2000_max_steps(monkeypatch) -> None:
    monkeypatch.setattr(sys, 'argv', ['rrc_controller.py', 'drive'])
    drive_args = parse_args()

    monkeypatch.setattr(sys, 'argv', ['rrc_controller.py', 'start'])
    start_args = parse_args()

    monkeypatch.setattr(sys, 'argv', ['rrc_controller.py', 'run', '--until-done'])
    run_args = parse_args()

    assert drive_args.max_steps == 2000
    assert start_args.max_steps == 2000
    assert run_args.max_steps == 2000


def test_drive_stops_when_same_action_repeats_without_progress(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    initial_state = controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'PLAN_CREATED',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    calls = 0

    def unchanged_run_once() -> dict:
        nonlocal calls
        calls += 1
        return dict(initial_state)

    monkeypatch.setattr(controller, 'run_once', unchanged_run_once)
    output: list[str] = []

    controller.drive(
        max_steps=2000,
        max_no_progress_steps=3,
        output_func=output.append,
        timestamp_output=False,
    )

    assert calls == 3
    assert any('连续 3 次执行未推进' in line for line in output)
    assert not any('已达到最大自动步数：2000' in line for line in output)


def test_drive_compact_output_shows_unit_roadmap_and_attempt_summary(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'EXECUTE_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    output: list[str] = []

    controller.drive(output_func=output.append, timestamp_output=False)
    rendered = '\n'.join(output)

    assert '▶ usable-system' in rendered
    assert '单元   1/1  unit-01' in rendered
    assert '阶段 [构建*] [精修] [评审] [验证] [单元完成]' in rendered
    assert '第 1 轮' in rendered
    assert '构建' in rendered
    assert '精修 通过' in rendered
    assert '评审 通过' in rendered
    assert '验证 通过' in rendered
    assert '[进度]' not in rendered
    assert '[执行]' not in rendered


def test_complete_unit_keeps_multi_unit_objective_partial_until_all_units_pass(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'multi-unit-delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'UNIT_COMPLETE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {
                    'objective': 'Complete usable system',
                    'units': ['unit-01', 'unit-02', 'unit-03'],
                    'status': 'partial',
                },
            ],
            'units': [
                {'id': 'unit-01', 'name': 'First unit', 'passes': False},
                {'id': 'unit-02', 'name': 'Second unit', 'passes': False},
                {'id': 'unit-03', 'name': 'Third unit', 'passes': False},
            ],
        },
        force=True,
    )

    state = controller.run_once()

    assert state['objectiveCoverage'][0]['status'] == 'partial'
    assert state['units'][0]['passes'] is True
    assert state['currentUnitId'] == 'unit-02'
    assert state['currentStep'] == 'EXECUTE_UNIT'
    assert not (state_dir / 'approvals' / 'final-acceptance.md').exists()


def test_reconcile_reopens_early_final_acceptance_when_units_are_incomplete(tmp_path: Path) -> None:
    state = {
        'task_id': 'multi-unit-delivery',
        'currentUnitId': 'unit-01',
        'currentStep': 'WAITING_FINAL_ACCEPTANCE',
        'lastVerifiedStep': 'VERIFY_UNIT',
        'status': 'active',
        'requestedOutcome': 'usable-system',
        'feasibleOutcome': 'usable-system',
        'scopeApproved': True,
        'humanGatesRequired': True,
        'requirementsAccepted': True,
        'unitPlanAccepted': True,
        'finalAcceptanceAccepted': False,
        'objectiveCoverage': [
            {
                'objective': 'Complete usable system',
                'units': ['unit-01', 'unit-02', 'unit-03'],
                'status': 'covered',
            },
        ],
        'units': [
            {'id': 'unit-01', 'name': 'First unit', 'passes': True},
            {'id': 'unit-02', 'name': 'Second unit', 'passes': False},
            {'id': 'unit-03', 'name': 'Third unit', 'passes': False},
        ],
    }

    reconciled = reconcile_state(state, tmp_path / 'artifacts')

    assert validate_objective_coverage(reconciled) is False
    assert reconciled['objectiveCoverage'][0]['status'] == 'partial'
    assert reconciled['currentUnitId'] == 'unit-02'
    assert reconciled['currentStep'] == 'EXECUTE_UNIT'
    assert reconciled['finalAcceptanceAccepted'] is False


def test_drive_compact_output_shows_planning_roadmap_before_unit_execution(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'target-v2-2',
            'currentStep': 'REQUIREMENTS_DRAFT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'V2.2',
            'feasibleOutcome': 'V2.2',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'unitPlanAccepted': False,
            'objectiveCoverage': [
                {'objective': 'V2.2 target acceptance', 'units': ['target-v2-2'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'target-v2-2', 'name': 'V2.2 target', 'passes': False},
            ],
        },
        force=True,
    )
    output: list[str] = []

    controller.drive(max_steps=0, output_func=output.append, timestamp_output=False)
    rendered = '\n'.join(output)

    assert '当前   生成需求与验收草案' in rendered
    assert '阶段 [需求草案*] [需求确认] [Unit Plan] [Unit Plan确认] [构建]' in rendered
    assert '阶段 [构建] [精修] [评审] [验证] [单元完成]' not in rendered


def test_compact_output_counts_units_for_requested_target_not_historical_units(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'v2-1-first',
            'currentStep': 'EXECUTE_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'V2.1',
            'feasibleOutcome': 'V2.1',
            'scopeApproved': True,
            'objectiveCoverage': [
                {'objective': 'V2.0 historical objective', 'units': ['old-1'], 'status': 'covered'},
                {'objective': 'V2.0 another historical objective', 'units': ['old-2'], 'status': 'covered'},
                {'objective': 'V2.1 first objective', 'units': ['v2-1-first'], 'status': 'partial'},
                {'objective': 'V2.1 second objective', 'units': ['v2-1-second'], 'status': 'partial'},
                {'objective': 'V2.1 third objective', 'units': ['v2-1-third'], 'status': 'partial'},
                {'objective': 'V2.1 fourth objective', 'units': ['v2-1-fourth'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'v2-1-first', 'passes': False},
                {'id': 'v2-1-second', 'passes': False},
                {'id': 'v2-1-third', 'passes': False},
                {'id': 'v2-1-fourth', 'passes': False},
                {'id': 'old-1', 'passes': True},
                {'id': 'old-2', 'passes': True},
            ],
        },
        force=True,
    )
    output: list[str] = []

    controller.drive(max_steps=0, output_func=output.append, timestamp_output=False)

    rendered = '\n'.join(output)
    assert '单元   1/4  v2-1-first' in rendered
    assert '单元   1/6  v2-1-first' not in rendered


def test_drive_prints_verification_state_change_markers(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'VERIFY_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'workspacePath': str(workspace),
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {
                    'id': 'unit-01',
                    'name': 'Delivery',
                    'passes': False,
                    'verification_commands': ["python -c \"print('verified')\""],
                },
            ],
        },
        force=True,
    )
    output: list[str] = []

    controller.drive(max_steps=1, output_func=output.append, timestamp_output=False)

    rendered = '\n'.join(output)
    assert '[验证] 开始 1 个命令' in rendered
    assert '[验证] ... 1/1 python -c' in rendered
    assert '[验证] 通过 1/1 exit=0' in rendered
    assert '[验证] 完成 通过' in rendered


def test_drive_prints_compact_verification_failure_reason(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'VERIFY_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'workspacePath': str(workspace),
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {
                    'id': 'unit-01',
                    'name': 'Delivery',
                    'passes': False,
                    'verification_commands': [
                        "DATABASE_URL=file:test.db python -c \"import sys; print('error: Environment variable not found: DATABASE_URL'); sys.exit(1)\"",
                    ],
                },
            ],
        },
        force=True,
    )
    output: list[str] = []

    controller.drive(max_steps=1, output_func=output.append, timestamp_output=False)

    rendered = '\n'.join(output)
    assert '原因 验证未通过' in rendered
    assert 'DATABASE_URL' in rendered
    assert 'exit 1' in rendered


def test_drive_compact_output_groups_failed_attempt_and_retry(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    states = [
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'EXECUTE_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        {
            'currentStep': 'REFINE_UNIT',
        },
        {
            'currentStep': 'REVIEW_UNIT',
        },
        {
            'currentStep': 'VERIFY_UNIT',
        },
        {
            'currentStep': 'EXECUTE_UNIT',
        },
    ]
    base = states[0]
    controller.init_state(base, force=True)
    transitions = iter(states[1:])

    def advance_once() -> dict:
        next_state = dict(base)
        next_state.update(next(transitions))
        return next_state

    monkeypatch.setattr(controller, 'run_once', advance_once)
    output: list[str] = []

    controller.drive(max_steps=4, output_func=output.append, timestamp_output=False)
    rendered = '\n'.join(output)

    assert '第 1 轮' in rendered
    assert '验证 未通过' in rendered
    assert '重试第 2 轮' in rendered
    assert '原因 验证未通过' in rendered


def test_repeated_verification_failure_blocks_before_another_retry(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'VERIFY_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'workspacePath': str(workspace),
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {
                    'id': 'unit-01',
                    'name': 'Delivery',
                    'passes': False,
                    'verification_commands': [
                        'python -c "import sys; print(\'runtime database missing\'); sys.exit(1)"',
                    ],
                },
            ],
        },
        force=True,
    )

    first = controller.run_once()

    assert first['status'] == 'active'
    assert first['currentStep'] == 'EXECUTE_UNIT'
    assert first['lastFailure']['stage'] == 'VERIFY_UNIT'
    assert first['lastFailure']['count'] == 1

    first['currentStep'] = 'VERIFY_UNIT'
    controller.store.save_state(first)

    second = controller.run_once()

    assert second['status'] == 'blocked'
    assert second['currentStep'] == 'VERIFY_UNIT'
    assert second['lastFailure']['count'] == 2
    assert 'Repeated VERIFY_UNIT failure' in second['blockedReason']
    assert 'runtime database missing' in second['blockedReason']


def test_run_verifier_rejects_malformed_evidence_schema_before_unit_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'VERIFY_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {
                    'id': 'unit-01',
                    'name': 'Delivery',
                    'passes': False,
                    'verification_commands': ['pytest tests/test_delivery.py -q'],
                },
            ],
        },
        force=True,
    )

    def fake_run_verifier(state: dict[str, Any], unit_dir: Path, **_: Any) -> None:
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / 'verification.json').write_text(
            json.dumps({
                'unit_id': 'unit-01',
                'passed': True,
                'commands': ['pytest tests/test_delivery.py -q'],
                'evidence_files': ['green-test.txt'],
                'verified_at': '2026-05-04T00:00:00+00:00',
            }),
            encoding='utf-8',
        )

    monkeypatch.setattr(rrc_controller_module, 'run_verifier', fake_run_verifier)

    state = controller.run_once()

    assert state['currentStep'] == 'EXECUTE_UNIT'
    assert state['lastFailure']['stage'] == 'VERIFY_UNIT'
    assert state['lastFailure']['details']['issues'][0]['type'] == 'invalid_evidence_schema'
    assert 'evidence_schema_version' in state['lastFailure']['details']['issues'][0]['message']


def _write_simplifier_result(unit_dir: Path, status: str, findings: list[dict[str, str]] | None = None) -> None:
    unit_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        'unit_id': 'unit-01',
        'status': status,
        'mode': 'role-runner',
        'changed_files': ['src/login.py'],
        'findings': findings or [],
        'runner_metadata': {},
        'exit_code': 0,
        'stdout': '',
        'stderr': '',
        'generated_at': '2026-05-03T00:00:00+00:00',
    }
    (unit_dir / 'simplifier-result.json').write_text(json.dumps(payload), encoding='utf-8')
    (unit_dir / 'refinement-summary.json').write_text(json.dumps(payload), encoding='utf-8')


def _refiner_controller_state(workspace: Path) -> dict[str, Any]:
    return {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'currentStep': 'REFINE_UNIT',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'usable-system',
        'feasibleOutcome': 'usable-system',
        'workspacePath': str(workspace),
        'objectiveCoverage': [
            {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {
                'id': 'unit-01',
                'name': 'Delivery',
                'passes': False,
            },
        ],
    }


def test_controller_routes_ok_simplifier_result_to_reviewer(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_refiner_controller_state(workspace), force=True)

    def fake_run_refiner(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> None:
        _write_simplifier_result(unit_dir, 'ok')

    monkeypatch.setattr('workflow_controller.rrc_controller.run_refiner', fake_run_refiner)

    state = controller.run_once()

    assert state['currentStep'] == 'REVIEW_UNIT'
    assert state['status'] == 'active'


def test_controller_routes_changes_requested_simplifier_result_back_to_builder(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_refiner_controller_state(workspace), force=True)

    def fake_run_refiner(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> None:
        _write_simplifier_result(
            unit_dir,
            'changes_requested',
            [{'type': 'over_nested_branch', 'message': 'Flatten the new login branch before review.'}],
        )

    monkeypatch.setattr('workflow_controller.rrc_controller.run_refiner', fake_run_refiner)

    state = controller.run_once()

    assert state['currentStep'] == 'EXECUTE_UNIT'
    assert state['status'] == 'active'
    assert state['lastFailure']['stage'] == 'REFINE_UNIT'
    assert state['lastFailure']['details']['issues'][0]['type'] == 'over_nested_branch'


def test_controller_failed_simplifier_result_does_not_reach_reviewer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    initial_state = _refiner_controller_state(workspace)
    initial_state['sameFailureMaxRetries'] = 0
    controller.init_state(initial_state, force=True)

    def fake_run_refiner(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> None:
        _write_simplifier_result(
            unit_dir,
            'failed',
            [{'type': 'missing_simplifier_result', 'message': 'CodeSimplifier output was malformed.'}],
        )

    monkeypatch.setattr('workflow_controller.rrc_controller.run_refiner', fake_run_refiner)

    state = controller.run_once()

    assert state['currentStep'] == 'REFINE_UNIT'
    assert state['status'] == 'blocked'
    assert 'Repeated REFINE_UNIT failure' in state['blockedReason']


def test_verifier_blocks_when_required_database_url_cannot_be_inferred(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'VERIFY_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'workspacePath': str(workspace),
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {
                    'id': 'unit-01',
                    'name': 'Delivery',
                    'passes': False,
                    'verification_commands': [
                        'pnpm exec playwright test e2e/tests/delivery.spec.ts --workers=1',
                    ],
                },
            ],
        },
        force=True,
    )

    state = controller.run_once()

    assert state['status'] == 'blocked'
    assert state['currentStep'] == 'VERIFY_UNIT'
    assert 'verification environment is incomplete' in state['blockedReason']
    assert 'DATABASE_URL' in state['blockedReason']
    assert state['nextAllowedActions'] == []


def test_drive_verbose_output_keeps_raw_progress_lines(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir), '--auto-approve')
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--dry-run',
        '--auto-approve',
        '--verbose',
    )

    assert result.returncode == 0, result.stderr
    assert '[进度] 目标：usable-system | 单元：unit-01 | 阶段：PLAN_CREATED | 下一步：范围确认' in result.stdout
    assert '[执行] 范围确认...' in result.stdout
    assert '[完成] 工作流已完成。' in result.stdout


def test_drive_color_auto_keeps_captured_output_plain(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir), '--auto-approve')
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--dry-run',
        '--auto-approve',
    )

    assert result.returncode == 0, result.stderr
    assert '\x1b[' not in result.stdout


def test_drive_color_always_adds_ansi_to_compact_output(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir), '--auto-approve')
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--dry-run',
        '--auto-approve',
        '--color',
        'always',
    )

    assert result.returncode == 0, result.stderr
    assert '\x1b[' in result.stdout
    plain = re.sub(r'\x1b\[[0-9;]*m', '', result.stdout)
    assert '▶ usable-system' in plain
    assert '验证 通过' in plain


def test_target_acceptance_completion_does_not_continue_unrelated_plan_units(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'target-acceptance',
            'currentUnitId': 'target-1-1',
            'currentStep': 'UNIT_COMPLETE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': '1.1',
            'targetMatchedPlanStep': False,
            'scopeApproved': True,
            'autoApprove': True,
            'objectiveCoverage': [
                {'objective': 'Future unrelated plan unit', 'units': ['future-unit'], 'status': 'partial'},
                {'objective': 'Target 1.1 acceptance', 'units': ['target-1-1'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'future-unit', 'passes': False},
                {'id': 'target-1-1', 'passes': False},
            ],
        },
        force=True,
    )

    state = controller.run_once()

    assert state['currentUnitId'] == 'target-1-1'
    assert state['currentStep'] == 'RELEASE_GATE'
    assert state['nextAllowedActions'] == ['require_release_approval']


def test_ui_design_step_writes_artifact_when_required(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'ui-work',
            'currentUnitId': 'unit-ui',
            'currentStep': 'PLAN_APPROVED',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'autoApprove': True,
            'currentUnitNeedsUiDesign': True,
            'objectiveCoverage': [
                {'objective': 'UI path is usable', 'units': ['unit-ui'], 'status': 'partial'},
            ],
            'units': [
                {
                    'id': 'unit-ui',
                    'name': 'UI delivery',
                    'scope': ['Build the browser-facing workflow'],
                    'ui_design_required': True,
                    'verification_commands': ['pytest tests/test_ui.py -q'],
                },
            ],
        },
        force=True,
    )

    state = controller.run_once()

    assert state['currentStep'] == 'UI_DESIGN_DONE'
    summary = json.loads((state_dir / 'artifacts' / 'unit-ui' / 'ui-design-summary.json').read_text(encoding='utf-8'))
    assert summary['status'] == 'ok'
    assert summary['unit_id'] == 'unit-ui'
    assert summary['mode'] == 'local-ui-design-brief'
    assert 'Build the browser-facing workflow' in summary['scope']


def test_migrate_command_adds_controller_state_patch_to_legacy_unit_plan_gate(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'legacy',
            'currentUnitId': 'unit-legacy',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Legacy objective', 'units': ['unit-legacy'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-legacy', 'name': 'Legacy unit', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Unit Plan Confirmation\n\n## Units\n- Legacy readable plan.\n\n'
        '## Human Confirmation\n\nStatus: pending\nConfirmed by: \nConfirmed at: \nContent hash: sha256:legacy\n',
        encoding='utf-8',
    )

    result = run_rrc('migrate', '--state-dir', str(state_dir))

    assert result.returncode == 0, result.stderr
    assert 'status=migrated' in result.stdout
    content = gate_path.read_text(encoding='utf-8')
    assert '## Controller State Patch' in content
    assert '"currentUnitId": "unit-legacy"' in content
    assert 'Status: pending' in content
    assert (state_dir / 'approvals' / 'unit-plan.md.before-controller-state-patch').exists()


def test_drive_outputs_compact_progress_and_runs_until_done_without_human_gate(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir), '--auto-approve')
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--dry-run',
        '--auto-approve',
    )

    assert result.returncode == 0, result.stderr
    assert '▶ usable-system' in result.stdout
    assert '单元   1/1  unit-01' in result.stdout
    assert '阶段 [构建] [精修] [评审] [验证] [单元完成]' in result.stdout
    assert '第 1 轮' in result.stdout
    assert '[进度]' not in result.stdout
    assert '[执行]' not in result.stdout
    assert '[完成] 工作流已完成。' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'DONE'
    assert state['status'] == 'done'


def test_drive_prefixes_each_output_line_with_seconds_timestamp(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir), '--auto-approve')
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--dry-run',
        '--auto-approve',
    )

    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines
    assert all(re.match(r'^\[\d{2}:\d{2}:\d{2}\] ', line) for line in lines)


def test_drive_stops_for_pending_unit_plan_gate_with_chinese_prompt(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Unit Plan Confirmation\n\n## Human Confirmation\n\nStatus: pending\nConfirmed by: \nConfirmed at: \nContent hash: sha256:legacy\n',
        encoding='utf-8',
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        input_text='q\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[人工确认] Unit Plan' in result.stdout
    assert str(gate_path) in result.stdout
    assert '状态：unit plan gate invalid' in result.stdout
    assert 'Controller State Patch' in result.stdout
    assert '    v  使用 Plannotator 辅助审阅' in result.stdout
    assert '    a  确认通过并继续' in result.stdout
    assert '[退出] 已停止在人工确认点。' in result.stdout


def test_drive_can_open_plannotator_review_without_approving_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Unit Plan Confirmation\n\n## Human Confirmation\n\nStatus: pending\nConfirmed by: \nConfirmed at: \nContent hash: sha256:legacy\n',
        encoding='utf-8',
    )
    plannotator_log = tmp_path / 'plannotator-args.json'
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

Path(os.environ['PLANNOTATOR_LOG']).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')
print('Open this link on your local machine to annotate:')
print('https://share.plannotator.ai/#fake')
print('{"decision":"dismissed"}')
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)
    monkeypatch.setenv('PLANNOTATOR_LOG', str(plannotator_log))

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--plannotator-command',
        str(fake_plannotator),
        input_text='v\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[Plannotator] 已打开辅助审阅。' in result.stdout
    assert 'http://localhost:20000' in result.stdout
    assert 'Open this link on your local machine to annotate:' not in result.stdout
    assert 'https://share.plannotator.ai/#fake' not in result.stdout
    assert '请在 Plannotator 浏览器里选择 Approve 或 Close。Approve 会自动继续。' in result.stdout
    assert '[Plannotator] 已关闭，未批准；仍停在人工确认点。' in result.stdout
    assert json.loads(plannotator_log.read_text(encoding='utf-8')) == [
        'annotate',
        str(gate_path),
        '--gate',
        '--json',
    ]
    summary_path = state_dir / 'plannotator' / 'unit-plan-last-review.json'
    assert summary_path.exists()
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['unitPlanAccepted'] is False
    events = [
        json.loads(line)
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    assert any(event['type'] == 'plannotator_review_requested' for event in events)


def test_drive_plannotator_reviews_requirements_body_artifact_when_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
            'lastVerifiedStep': 'REQUIREMENTS_DRAFT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    approval_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    approval_path.write_text(
        '# Requirements & Acceptance Confirmation\n\nClaude body\n\n## Human Confirmation\n\nStatus: pending\n',
        encoding='utf-8',
    )
    body_path = state_dir / 'artifacts' / 'requirements-draft' / 'requirements-body.md'
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_text('# Requirements & Acceptance Confirmation\n\nClaude body\n', encoding='utf-8')
    plannotator_log = tmp_path / 'plannotator-args.json'
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

Path(os.environ['PLANNOTATOR_LOG']).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')
print('Open this link on your local machine to annotate:')
print('https://share.plannotator.ai/#requirements-body')
print('{"decision":"dismissed"}')
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)
    monkeypatch.setenv('PLANNOTATOR_LOG', str(plannotator_log))

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--plannotator-command',
        str(fake_plannotator),
        input_text='v\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert f'审阅文件：{body_path}' in result.stdout
    assert f'确认文件：{approval_path}' in result.stdout
    assert json.loads(plannotator_log.read_text(encoding='utf-8')) == [
        'annotate',
        str(body_path),
        '--gate',
        '--json',
    ]
    summary = json.loads((state_dir / 'plannotator' / 'requirements-last-review.json').read_text(encoding='utf-8'))
    assert summary['gate_path'] == str(body_path)
    assert summary['review_path'] == str(body_path)
    assert summary['approval_gate_path'] == str(approval_path)


def test_drive_auto_approves_gate_when_plannotator_approves(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        '# Requirements & Acceptance Confirmation\n\n## 4. Test Strategy\n- Unit tests cover delivery.\n',
    )
    approve_gate_file(requirements_path, actor='tester')

    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Units
### unit-01 - Delivery
- Verification commands:
  - `pytest tests/test_delivery.py -q`

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery",
      "passes": false,
      "verification_commands": ["pytest tests/test_delivery.py -q"]
    }
  ]
}
```
""",
    )
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
print('Open this link on your local machine to annotate:')
print('https://share.plannotator.ai/#approved')
print('{"decision":"approved"}')
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '1',
        '--actor',
        'tester',
        '--plannotator-command',
        str(fake_plannotator),
        input_text='v\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[Plannotator] 已收到 Approve，等同于人工确认通过。' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['unitPlanAccepted'] is True
    assert state['currentStep'] == 'PLAN_CREATED'


def test_drive_announces_plannotator_feedback_before_revising_gate(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        '# Requirements & Acceptance Confirmation\n\n## 4. Test Strategy\n- Unit tests cover delivery.\n',
    )
    approve_gate_file(requirements_path, actor='tester')

    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Units
### unit-01 - Delivery
- Verification commands:
  - `pytest tests/test_delivery.py -q`
""",
    )
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
import json

print('Open this link on your local machine to annotate:')
print('https://share.plannotator.ai/#feedback')
print(json.dumps({
    "decision": "annotated",
    "feedback": "# File Feedback\\n\\nI've reviewed this file and have 2 pieces of feedback:\\n\\n## 1. Feedback on: \\"Objective Coverage Matrix\\"\\n> please split this unit before approval.\\n\\n## 2. Feedback on: \\"Verification commands\\"\\n> please add explicit database env.\\n\\n---\\n"
}))
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '1',
        '--plannotator-command',
        str(fake_plannotator),
        input_text='v\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[Plannotator] 已收到修改意见，开始重新生成 Unit Plan。' in result.stdout
    assert '修改意见：共 2 条，完整反馈已写入 Claude 返工 prompt。' in result.stdout
    assert '预览：# File Feedback' in result.stdout
    assert '[修订] 已根据 Plannotator 反馈重新生成 Unit Plan。' in result.stdout


def test_drive_blocks_revise_after_plannotator_when_feedback_is_not_submitted(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Unit Plan Confirmation\n\n## Human Confirmation\n\nStatus: pending\nConfirmed by: \nConfirmed at: \nContent hash: sha256:legacy\n',
        encoding='utf-8',
    )
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
print('Open this link on your local machine to annotate:')
print('https://share.plannotator.ai/#fake-no-local-feedback')
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--plannotator-command',
        str(fake_plannotator),
        input_text='v\nr\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert 'Plannotator 尚未提交可供 controller 读取的返工反馈' in result.stdout
    assert 'Plannotator 没有返回返工反馈' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert 'unitPlanRevisionCount' not in state


def test_drive_blocks_revise_after_plannotator_review_without_submitted_feedback(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Unit Plan Confirmation\n\n## Human Confirmation\n\nStatus: pending\nConfirmed by: \nConfirmed at: \nContent hash: sha256:legacy\n',
        encoding='utf-8',
    )
    summary_path = state_dir / 'plannotator' / 'unit-plan-last-review.json'
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                'gate': 'unit-plan',
                'gate_path': str(gate_path),
                'stdout': '',
                'stderr': '(document only, annotations added in browser)',
            }
        ),
        encoding='utf-8',
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        input_text='r\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert 'Plannotator 尚未提交可供 controller 读取的返工反馈' in result.stdout
    assert 'Plannotator 没有返回返工反馈' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert 'unitPlanRevisionCount' not in state


def test_drive_passes_configured_plannotator_port_to_review_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Unit Plan Confirmation\n\n## Human Confirmation\n\nStatus: pending\nConfirmed by: \nConfirmed at: \nContent hash: sha256:legacy\n',
        encoding='utf-8',
    )
    env_log = tmp_path / 'plannotator-env.json'
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

Path(os.environ['PLANNOTATOR_ENV_LOG']).write_text(
    json.dumps({'port': os.environ.get('PLANNOTATOR_PORT')}),
    encoding='utf-8',
)
print('Open this link on your local machine to annotate:')
print('https://share.plannotator.ai/#fake-port')
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)
    monkeypatch.setenv('PLANNOTATOR_ENV_LOG', str(env_log))

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--plannotator-command',
        str(fake_plannotator),
        '--plannotator-port',
        '20000',
        input_text='v\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert 'http://localhost:20000' in result.stdout
    assert json.loads(env_log.read_text(encoding='utf-8')) == {'port': '20000'}


def test_drive_waits_for_plannotator_approval_after_printing_link(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        '# Requirements & Acceptance Confirmation\n\n## 4. Test Strategy\n- Unit tests cover delivery.\n',
    )
    approve_gate_file(requirements_path, actor='tester')
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Units
### unit-01 - Delivery
- Verification commands:
  - `pytest tests/test_delivery.py -q`

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery",
      "passes": false,
      "verification_commands": ["pytest tests/test_delivery.py -q"]
    }
  ]
}
```
""",
    )
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
import time

print('Open this link on your local machine to annotate:', flush=True)
print('https://share.plannotator.ai/#long-running', flush=True)
time.sleep(0.2)
print('{"decision":"approved"}', flush=True)
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '1',
        '--plannotator-command',
        str(fake_plannotator),
        input_text='v\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[Plannotator] 已打开辅助审阅。' in result.stdout
    assert 'http://localhost:20000' in result.stdout
    assert 'Open this link on your local machine to annotate:' not in result.stdout
    assert 'https://share.plannotator.ai/#long-running' not in result.stdout
    assert '等待 Plannotator 操作结果' in result.stdout
    assert '[Plannotator] 已收到 Approve，等同于人工确认通过。' in result.stdout
    summary = json.loads((state_dir / 'plannotator' / 'unit-plan-last-review.json').read_text(encoding='utf-8'))
    assert summary['process_id'] > 0
    assert summary['returncode'] is None
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['unitPlanAccepted'] is True


def test_drive_can_approve_unit_plan_gate_and_continue(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(
        '# Requirements & Acceptance Confirmation\n\n## 4. Test Strategy\n- Unit tests cover delivery.\n\n'
        '## Human Confirmation\n\nStatus: approved\nConfirmed by: tester\nConfirmed at: now\nContent hash: sha256:legacy\n',
        encoding='utf-8',
    )
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    write_gate_file(
        requirements_path,
        '# Requirements & Acceptance Confirmation\n\n## 4. Test Strategy\n- Unit tests cover delivery.\n',
    )
    approve_gate_file(requirements_path, actor='tester')
    unit_plan_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        unit_plan_path,
        """# Unit Plan Confirmation

## Units
### unit-01 - Delivery
- Verification commands:
  - `pytest tests/test_delivery.py -q`

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery",
      "passes": false,
      "verification_commands": ["pytest tests/test_delivery.py -q"]
    }
  ]
}
```
""",
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '1',
        '--actor',
        'tester',
        input_text='a\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[确认] Unit Plan 已确认，继续推进。' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['unitPlanAccepted'] is True
    assert state['currentStep'] == 'PLAN_CREATED'


def test_drive_blocks_unit_plan_approval_when_acceptance_obligation_is_missing(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'acceptanceObligations': [
                {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
                {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
            ],
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import write_gate_file

    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Test Case Matrix
| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |
| --- | --- | --- | --- | --- |
| AC-1 covers AO-001 | TC-1 | integration | pytest tests/test_delivery.py -q | AO-001 works |

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery",
      "passes": false,
      "test_cases": [
        {
          "id": "TC-1",
          "acceptance_criterion": "AC-1",
          "covers_obligations": ["AO-001"],
          "layer": "integration",
          "command": "pytest tests/test_delivery.py -q",
          "expected": "AO-001 works"
        }
      ],
      "verification_commands": ["pytest tests/test_delivery.py -q"]
    }
  ]
}
```
""",
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '3',
        input_text='a\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert 'missing Acceptance Obligation coverage' in result.stdout
    assert 'AO-002' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['unitPlanAccepted'] is False
    assert state['blockedReason'].startswith('unit plan gate invalid:')


def test_requirements_approval_blocks_unmapped_acceptance_obligation(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
            'lastVerifiedStep': 'REQUIREMENTS_DRAFT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': True,
            'acceptanceObligations': [
                {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
                {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
            ],
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import write_gate_file

    gate_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        gate_path,
        """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: integration]: 六步 UX 清楚展示。

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| AO-001 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |
""",
    )

    with pytest.raises(ValueError, match='requirements gate invalid:.*AO-002'):
        controller.approve_human_gate('requirements', actor='tester')

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['requirementsAccepted'] is False
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert state['blockedReason'].startswith('requirements gate invalid:')


def test_run_rejects_preapproved_requirements_missing_ac_verification_layer(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
            'lastVerifiedStep': 'REQUIREMENTS_DRAFT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': True,
            'acceptanceObligations': [
                {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
            ],
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    gate_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        gate_path,
        """# 需求与验收确认

## 3. 验收标准
- AC-1: 六步 UX 清楚展示。

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| AO-001 | AC-1 | covered |  | pytest tests/test_delivery.py -q |
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['requirementsAccepted'] is False
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert state['blockedReason'].startswith('requirements gate invalid:')
    assert 'AC-1' in state['blockedReason']
    assert 'verification layer' in state['blockedReason']


def test_requirements_revision_feedback_includes_controller_validation_error(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
            'lastVerifiedStep': 'REQUIREMENTS_DRAFT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': True,
            'acceptanceObligations': [
                {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
            ],
            'blockedReason': 'requirements gate invalid: AC-1 missing verification layer',
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import write_gate_file

    gate_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(gate_path, '# 需求与验收确认\n\n## 3. 验收标准\n- AC-1: 六步 UX 清楚展示。\n')

    feedback = controller._revision_feedback_for_gate('requirements', gate_path)

    assert '## Controller Validation Error' in feedback
    assert 'requirements gate invalid: AC-1 missing verification layer' in feedback



def test_run_rejects_preapproved_unit_plan_missing_acceptance_obligation(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'acceptanceObligations': [
                {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
                {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
            ],
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Test Case Matrix
| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |
| --- | --- | --- | --- | --- |
| AC-1 covers AO-001 | TC-1 | integration | pytest tests/test_delivery.py -q | AO-001 works |

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery",
      "passes": false,
      "test_cases": [
        {
          "id": "TC-1",
          "acceptance_criterion": "AC-1",
          "covers_obligations": ["AO-001"],
          "layer": "integration",
          "command": "pytest tests/test_delivery.py -q",
          "expected": "AO-001 works"
        }
      ],
      "verification_commands": ["pytest tests/test_delivery.py -q"]
    }
  ]
}
```
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['unitPlanAccepted'] is False
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert 'missing Acceptance Obligation coverage' in state['blockedReason']
    assert 'AO-002' in state['blockedReason']
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['unitPlanAccepted'] is False
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['blockedReason'].startswith('unit plan gate invalid:')


def test_run_rejects_preapproved_unit_plan_missing_design_architecture_traceability(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: integration]: Delivery behavior works.

## Design/Architecture Traceability Matrix
| AC | Product Design Ref | Technical Architecture Ref | Notes |
| --- | --- | --- | --- |
| AC-1 | PD-AC1-delivery-flow | TA-AC1-delivery-service | delivery flow |
""",
    )
    approve_gate_file(requirements_path, actor='tester')

    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery",
      "passes": false,
      "test_cases": [
        {
          "id": "TC-1",
          "acceptance_criterion": "AC-1",
          "layer": "integration",
          "command": "pytest tests/test_delivery.py -q",
          "expected": "Delivery behavior works"
        }
      ],
      "verification_commands": ["pytest tests/test_delivery.py -q"]
    }
  ]
}
```
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['unitPlanAccepted'] is False
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert 'design/architecture traceability' in state['blockedReason']
    assert state['blockedReason'].startswith('unit plan gate invalid:')


def test_drive_blocks_unit_plan_approval_when_plan_is_invalid(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Old objective', 'units': ['old-unit'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'old-unit', 'name': 'Old unit', 'passes': True},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import write_gate_file

    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Old objective", "units": ["missing-old-unit"], "status": "covered"},
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {"id": "unit-01", "name": "Delivery", "passes": false}
  ]
}
```
""",
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '3',
        input_text='a\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert 'unit plan gate invalid' in result.stdout
    assert '[确认] Unit Plan 已确认，继续推进。' not in result.stdout
    assert '[确认] Unit Plan 无法确认：unit plan gate invalid' in result.stdout
    assert result.stdout.count('[人工确认] Unit Plan') == 1
    assert '[停止] 已达到最大自动步数' not in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['unitPlanAccepted'] is False
    assert 'unitPlanAcceptedHash' not in state
    assert state['blockedReason'].startswith('unit plan gate invalid:')
    assert 'Status: pending' in gate_path.read_text(encoding='utf-8')


def test_drive_refreshes_stale_unit_plan_invalid_reason_from_current_gate(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-db',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'blockedReason': "unit plan gate invalid: old target-v2-2 error",
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-db'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-db', 'name': 'Database unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import write_gate_file

    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Objective Coverage Matrix
- Delivery objective -> unit-db

## Units
### unit-db - Database unit

## Controller State Patch

```json
{
  "currentUnitId": "unit-db",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-db"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-db",
      "name": "Database unit",
      "passes": false,
      "verification_commands": ["cd app && pnpm exec prisma migrate dev --name init"]
    }
  ]
}
```
""",
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        input_text='q\n',
    )

    assert result.returncode == 0, result.stderr
    assert 'verification_env is incomplete' in result.stdout
    assert 'old target-v2-2 error' not in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert 'verification_env is incomplete' in state['blockedReason']
    assert 'old target-v2-2 error' not in state['blockedReason']


def test_drive_can_revise_unit_plan_gate_from_human_notes(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text('# Unit Plan Confirmation\n\nReviewer note: split E2E closure.\n', encoding='utf-8')

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '0',
        input_text='r\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[修订] 已重新生成 Unit Plan，请重新阅读确认。' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['unitPlanRevisionCount'] == 1


def test_drive_can_reject_final_acceptance_and_return_to_builder(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': True},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'final-acceptance.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [ ] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [x] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        'Reviewer note: import preview is missing retry state.\n',
        encoding='utf-8',
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '0',
        input_text='r\n',
    )

    assert result.returncode == 0, result.stderr
    assert '    r  验收不通过，带批注返工' in result.stdout
    assert '[返工] 最终验收未通过，已回到 Builder。' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'EXECUTE_UNIT'
    assert state['finalAcceptanceRejectionRoute'] == 'implementation'
    assert state['finalAcceptanceAccepted'] is False
    assert state['finalAcceptanceRejectionCount'] == 1
    assert 'import preview is missing retry state' in state['finalAcceptanceRejectionFeedback']
    assert state['units'][0]['passes'] is False
    assert state['objectiveCoverage'][0]['status'] == 'partial'


def test_reject_final_acceptance_routes_to_requirements_when_selected_with_other_reasons(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'unitPlanDraftGenerated': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': True},
            ],
        },
        force=True,
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n', encoding='utf-8')
    (approvals_dir / 'unit-plan.md').write_text('# Unit Plan\n', encoding='utf-8')
    gate_path = approvals_dir / 'final-acceptance.md'
    gate_path.write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [x] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [ ] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [x] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        'Reviewer note: add missing acceptance around offline import recovery.\n',
        encoding='utf-8',
    )

    controller.reject_final_acceptance_gate()

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert state['finalAcceptanceRejectionRoute'] == 'requirements'
    assert state['requirementsAccepted'] is False
    assert state['unitPlanAccepted'] is False
    assert state['requirementsDraftGenerated'] is True
    assert state['unitPlanDraftGenerated'] is False
    assert not (approvals_dir / 'unit-plan.md').exists()
    assert state['units'][0]['passes'] is False
    assert state['objectiveCoverage'][0]['status'] == 'partial'


def test_reject_final_acceptance_requires_human_routing_checkbox(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': True},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'final-acceptance.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [ ] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [ ] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n',
        encoding='utf-8',
    )

    try:
        controller.reject_final_acceptance_gate()
    except ValueError as exc:
        assert 'Final acceptance rejection routing must select one option' in str(exc)
    else:
        raise AssertionError('expected rejection without routing to fail')

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_FINAL_ACCEPTANCE'
    assert state['units'][0]['passes'] is True


def test_drive_prompts_for_final_acceptance_rejection_route_when_unselected(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': True},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'final-acceptance.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [ ] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [ ] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        'Reviewer note: button copy is wrong.\n',
        encoding='utf-8',
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '0',
        input_text='r\n4\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[验收路由] 请选择最终验收不通过后的流向：' in result.stdout
    assert '1  验收缺陷修复 -> Defect Fix' in result.stdout
    assert '4  实现返工 -> Builder' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'EXECUTE_UNIT'
    assert state['finalAcceptanceRejectionRoute'] == 'implementation'
    content = gate_path.read_text(encoding='utf-8')
    assert '- [x] 实现返工:' in content
    assert 'Reviewer note: button copy is wrong.' in content


def test_drive_defect_fix_route_migrates_old_final_acceptance_gate_and_keeps_plannotator_feedback(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'v2-2-u5-baidu-search',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'V2.2',
            'feasibleOutcome': 'V2.2',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'unitPlanDraftGenerated': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Logo objective', 'units': ['v2-2-u2-logo-real'], 'status': 'covered'},
                {'objective': 'Baidu objective', 'units': ['v2-2-u5-baidu-search'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'v2-2-u2-logo-real', 'name': 'logo', 'passes': True},
                {'id': 'v2-2-u5-baidu-search', 'name': 'baidu', 'passes': True},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import write_gate_file

    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n', encoding='utf-8')
    gate_path = approvals_dir / 'final-acceptance.md'
    write_gate_file(
        gate_path,
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        'If final acceptance is rejected, select the human routing decision below. Multiple selections are allowed; requirements revision has highest priority.\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [ ] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        '## Rejection Notes\n'
        'Old gate format without Defect fix row.\n',
    )
    plannotator_dir = state_dir / 'plannotator'
    plannotator_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = plannotator_dir / 'final-acceptance-last-review.stdout.log'
    stdout_path.write_text(
        json.dumps(
            {
                'decision': 'annotated',
                'feedback': '# File Feedback\n\nplayback logo needs dark-mode asset and better placement.',
            }
        ),
        encoding='utf-8',
    )
    (plannotator_dir / 'final-acceptance-last-review.json').write_text(
        json.dumps(
            {
                'gate_path': str(gate_path),
                'approval_gate_path': str(gate_path),
                'stdout_path': str(stdout_path),
            }
        ),
        encoding='utf-8',
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '0',
        input_text='r\n1\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[验收路由] 已选择：Defect fix' in result.stdout
    assert '[返工] 最终验收未通过，已进入验收缺陷修复流程。' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['finalAcceptanceRejectionRoute'] == 'defect_fix'
    assert 'playback logo needs dark-mode asset' in state['finalAcceptanceDefectFeedback']
    assert 'playback logo needs dark-mode asset' in state['finalAcceptanceRejectionFeedback']
    content = gate_path.read_text(encoding='utf-8')
    assert '- [x] 验收缺陷修复:' in content
    assert '- [ ] 需求变更:' in content


def test_reject_final_acceptance_routes_to_defect_fix_unit_plan_revision(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'v2-2-u5-baidu-search',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'V2.2',
            'feasibleOutcome': 'V2.2',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'unitPlanDraftGenerated': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'i18n coverage', 'units': ['v2-2-u1-i18n-fix'], 'status': 'covered'},
                {'objective': 'logo coverage', 'units': ['v2-2-u2-logo-real'], 'status': 'covered'},
                {'objective': 'baidu provider', 'units': ['v2-2-u5-baidu-search'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'v2-2-u1-i18n-fix', 'name': 'i18n', 'passes': True},
                {'id': 'v2-2-u2-logo-real', 'name': 'logo', 'passes': True},
                {'id': 'v2-2-u5-baidu-search', 'name': 'baidu', 'passes': True},
            ],
        },
        force=True,
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n', encoding='utf-8')
    gate_path = approvals_dir / 'final-acceptance.md'
    gate_path.write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [x] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [ ] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [ ] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        'Reviewer note: homepage logo is still text-only; workbench has untranslated strings.\n',
        encoding='utf-8',
    )

    controller.reject_final_acceptance_gate()

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['finalAcceptanceRejectionRoute'] == 'defect_fix'
    assert state['requirementsAccepted'] is True
    assert state['unitPlanAccepted'] is False
    assert state['unitPlanDraftGenerated'] is True
    assert state['finalAcceptanceAccepted'] is False
    assert state['finalAcceptanceDefectFeedback'].startswith('# Final Acceptance Confirmation')
    assert 'homepage logo is still text-only' in state['finalAcceptanceDefectFeedback']
    assert state['unitPlanRevisionMode'] == 'defect_fix'
    assert all(unit['passes'] is True for unit in state['units'])
    obligations = state['acceptanceObligations']
    assert [item['id'] for item in obligations] == ['AO-001']
    assert obligations[0]['source'] == 'final_acceptance_rejection'
    assert 'homepage logo is still text-only' in obligations[0]['description']
    assert (state_dir / 'artifacts' / 'acceptance-obligations' / 'acceptance-obligations.json').exists()
    assert 'AO-001' in (state_dir / 'artifacts' / 'acceptance-obligations' / 'acceptance-obligations.md').read_text(encoding='utf-8')


def test_reject_final_acceptance_routes_to_unit_plan_revision(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'unitPlanDraftGenerated': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': True},
            ],
        },
        force=True,
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n', encoding='utf-8')
    gate_path = approvals_dir / 'final-acceptance.md'
    gate_path.write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [x] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [ ] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        'Reviewer note: final acceptance shows verification commands need broader coverage.\n',
        encoding='utf-8',
    )

    controller.reject_final_acceptance_gate()

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['finalAcceptanceRejectionRoute'] == 'unit_plan'
    assert state['requirementsAccepted'] is True
    assert state['unitPlanAccepted'] is False
    assert state['unitPlanDraftGenerated'] is True
    assert state['units'][0]['passes'] is False


def test_reject_final_acceptance_can_block_for_environment_or_evidence_issue(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': True},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'final-acceptance.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [ ] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [ ] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [x] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        'Reviewer note: missing customer account credentials for UAT.\n',
        encoding='utf-8',
    )

    controller.reject_final_acceptance_gate()

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['status'] == 'blocked'
    assert state['currentStep'] == 'WAITING_FINAL_ACCEPTANCE'
    assert state['finalAcceptanceRejectionRoute'] == 'blocked'
    assert 'Final acceptance rejected as blocked' in state['blockedReason']
    assert state['units'][0]['passes'] is True


def test_start_initializes_and_drives_workflow_in_one_command(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'

    result = run_rrc(
        'start',
        '--state-dir',
        str(state_dir),
        '--dry-run',
        '--auto-approve',
    )

    assert result.returncode == 0, result.stderr
    assert '[初始化] 创建新的 controller 状态' in result.stdout
    assert '[完成] 工作流已完成。' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'DONE'
    assert state['status'] == 'done'


def test_start_resumes_existing_state_when_target_matches(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'target-acceptance',
            'currentUnitId': 'target-1-1',
            'currentStep': 'PLAN_CREATED',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': '1.1',
            'feasibleOutcome': '1.1',
            'scopeApproved': False,
            'autoApprove': True,
            'objectiveCoverage': [
                {'objective': 'Target 1.1 acceptance', 'units': ['target-1-1'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'target-1-1', 'passes': False},
            ],
        },
        force=True,
    )

    result = run_rrc(
        'start',
        '--state-dir',
        str(state_dir),
        '--target',
        '1.1',
        '--dry-run',
        '--auto-approve',
    )

    assert result.returncode == 0, result.stderr
    assert '[继续] 使用已有状态' in result.stdout
    assert '[完成] 工作流已完成。' in result.stdout


def test_start_rejects_existing_state_when_target_differs_without_force(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'target-acceptance',
            'currentUnitId': 'target-1-1',
            'currentStep': 'PLAN_CREATED',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': '1.1',
            'feasibleOutcome': '1.1',
            'scopeApproved': False,
            'autoApprove': True,
            'objectiveCoverage': [
                {'objective': 'Target 1.1 acceptance', 'units': ['target-1-1'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'target-1-1', 'passes': False},
            ],
        },
        force=True,
    )

    result = run_rrc(
        'start',
        '--state-dir',
        str(state_dir),
        '--target',
        '1.2',
        '--dry-run',
        '--auto-approve',
    )

    assert result.returncode == 1
    assert 'Existing session does not match start arguments' in result.stderr
    assert '--target=1.2 but session requestedOutcome=1.1' in result.stderr
    assert 'Use --force to reinitialize' in result.stderr


def test_unit_plan_drafter_emits_test_strategist_start_progress(tmp_path: Path, monkeypatch) -> None:
    approvals_dir = tmp_path / 'approvals'
    artifacts_dir = tmp_path / 'artifacts'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Behavior works.\n', encoding='utf-8')
    state = _controller_state_for_unit_plan(workspace)

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': []}),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': []}),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    emitted: list[str] = []
    run_unit_plan_drafter(state, approvals_dir, artifacts_dir, progress_callback=emitted.append)

    assert any('Test Strategist' in msg or 'Codex' in msg or 'test strategist' in msg.lower() for msg in emitted), \
        f'Expected a startup message about Test Strategist but got: {emitted}'


def test_drive_threads_output_func_to_unit_plan_drafter(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Behavior works.\n', encoding='utf-8')

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': []}),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': []}),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    output: list[str] = []

    def quit_at_gate(_prompt: str) -> str:
        return 'q'

    controller.drive(max_steps=2, output_func=output.append, input_func=quit_at_gate, timestamp_output=False)

    assert any('Test Strategist' in msg or 'Codex' in msg or 'test strategist' in msg.lower() for msg in output), \
        f'Expected startup message in drive output but got: {output}'


# ---------------------------------------------------------------------------
# Codex self-patch tests (Option C)
# ---------------------------------------------------------------------------

def test_codex_patcher_fills_gaps_and_marks_patched_test_cases(tmp_path: Path, monkeypatch) -> None:
    """When the initial strategist leaves a gap, a second Codex run patches it
    and marks each added test_case with codex_patch=True."""
    from workflow_controller.steps.unit_plan import _run_test_strategist_if_enabled

    draft_dir = tmp_path / 'unit-plan-draft'
    draft_dir.mkdir()
    approvals_dir = tmp_path / 'approvals'
    approvals_dir.mkdir()
    (approvals_dir / 'requirements-and-acceptance.md').write_text('## 1. 需求\n- req\n', encoding='utf-8')
    (draft_dir / 'unit-plan-body.md').write_text('## AC\n- AC-1-1: do thing\n', encoding='utf-8')

    call_count = [0]

    def fake_run(request):
        call_count[0] += 1
        if call_count[0] == 1:
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': [{'id': 'AC-1-1', 'test_cases': []}]}),
                encoding='utf-8',
            )
        else:
            patched = {
                'acceptance_criteria': [
                    {'id': 'AC-1-1', 'test_cases': [
                        {'id': 'TC-1-1-a', 'layer': 'functional',
                         'command': 'pytest tests/', 'expected': 'pass',
                         'codex_patch': True},
                    ]}
                ]
            }
            (request.artifact_dir / 'test-strategy.json').write_text(json.dumps(patched), encoding='utf-8')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run)

    state: dict = {'testStrategistEnabled': True, 'currentUnitId': 'u1'}
    _run_test_strategist_if_enabled(
        state=state,
        approvals_dir=approvals_dir,
        draft_dir=draft_dir,
        workspace_path=tmp_path,
    )

    assert call_count[0] == 2, f'patcher should run a second Codex pass when gaps exist, got {call_count[0]}'
    strategy = json.loads((draft_dir / 'test-strategy.json').read_text(encoding='utf-8'))
    tc = strategy['acceptance_criteria'][0]['test_cases'][0]
    assert tc.get('codex_patch') is True


def test_codex_patch_markers_appear_in_unit_plan_gate(tmp_path: Path) -> None:
    """Patched test cases are rendered in a dedicated section in the gate."""
    from workflow_controller.steps.unit_plan import _merge_review_package_into_unit_plan_gate

    draft_dir = tmp_path / 'unit-plan-draft'
    draft_dir.mkdir()

    patched_strategy = {
        'acceptance_criteria': [
            {'id': 'AC-1-1', 'test_cases': [
                {'id': 'TC-1-1-a', 'layer': 'functional',
                 'command': 'pytest tests/', 'expected': 'pass',
                 'codex_patch': True},
            ]}
        ]
    }
    (draft_dir / 'test-strategy.json').write_text(json.dumps(patched_strategy), encoding='utf-8')
    (draft_dir / 'unit-plan-gap-report.json').write_text(
        json.dumps({'gap_counts': {'critical': 0, 'major': 0, 'minor': 0}, 'gaps': []}),
        encoding='utf-8',
    )

    gate = _merge_review_package_into_unit_plan_gate(
        'Original body\n', draft_dir, retry_count=0
    )

    assert 'Codex' in gate
    assert 'TC-1-1-a' in gate
    assert 'AC-1-1' in gate


def test_patcher_failure_does_not_block_gate_creation(tmp_path: Path, monkeypatch) -> None:
    """If the patcher Codex run fails, the original test-strategy.json is kept
    and the strategist summary is returned without raising."""
    from workflow_controller.steps.unit_plan import _run_test_strategist_if_enabled

    draft_dir = tmp_path / 'unit-plan-draft'
    draft_dir.mkdir()
    approvals_dir = tmp_path / 'approvals'
    approvals_dir.mkdir()
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# req\n', encoding='utf-8')
    (draft_dir / 'unit-plan-body.md').write_text('body\n', encoding='utf-8')

    call_count = [0]

    def fake_run(request):
        call_count[0] += 1
        if call_count[0] == 1:
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': [{'id': 'AC-1-1', 'test_cases': []}]}),
                encoding='utf-8',
            )
            return _fake_agent_result(request)
        return _fake_agent_result(request, status='failed', returncode=1, stderr='error')

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run)

    state: dict = {'testStrategistEnabled': True, 'currentUnitId': 'u1'}
    summary = _run_test_strategist_if_enabled(
        state=state,
        approvals_dir=approvals_dir,
        draft_dir=draft_dir,
        workspace_path=tmp_path,
    )

    assert (draft_dir / 'test-strategy.json').exists()
    assert 'gap_counts' in summary


def test_patch_list_in_final_acceptance_gate_is_extracted_for_builder(tmp_path: Path) -> None:
    """When ## 修改清单 has items, finalAcceptanceRejectionFeedback contains only those items."""
    from workflow_controller.gates.parsers import write_gate_file
    from workflow_controller.gates.generators import normalize_final_acceptance_rejection_routing

    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(tmp_path / 'workspace')
    initial_state.update({
        'currentStep': 'WAITING_FINAL_ACCEPTANCE',
        'unitPlanDraftGenerated': True,
        'unitPlanAccepted': True,
        'scopeApproved': True,
        'units': [{'id': 'u1', 'passes': True}],
        'objectiveCoverage': [{'objective': 'obj1', 'status': 'covered', 'units': ['u1']}],
    })
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)

    gate_body = (
        '# 最终验收确认\n\n'
        '## 结果\n- 状态: active\n\n'
        '## 修改清单\n\n'
        '- [ ] 登录按钮文字改为"立即登录"\n'
        '- [ ] 错误提示消失时间从 5s 改为 3s\n\n'
        '## 人工审阅清单\n- [ ] 实际结果满足已批准的验收标准。\n\n'
    )
    gate_body = normalize_final_acceptance_rejection_routing(
        gate_body, selected_route='implementation'
    )
    write_gate_file(approvals_dir / 'final-acceptance.md', gate_body)

    controller.reject_final_acceptance_gate()

    saved = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    feedback = saved['finalAcceptanceRejectionFeedback']
    assert '立即登录' in feedback
    assert '5s 改为 3s' in feedback
    assert '## 结果' not in feedback, 'Full gate content should not be in feedback when patch list is present'
    assert '## 覆盖情况' not in feedback


def test_empty_patch_list_falls_back_to_full_gate_for_builder(tmp_path: Path) -> None:
    """When ## 修改清单 is present but empty, builder receives the full gate content."""
    from workflow_controller.gates.parsers import write_gate_file
    from workflow_controller.gates.generators import normalize_final_acceptance_rejection_routing

    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(tmp_path / 'workspace')
    initial_state.update({
        'currentStep': 'WAITING_FINAL_ACCEPTANCE',
        'unitPlanDraftGenerated': True,
        'unitPlanAccepted': True,
        'scopeApproved': True,
        'units': [{'id': 'u1', 'passes': True}],
        'objectiveCoverage': [{'objective': 'obj1', 'status': 'covered', 'units': ['u1']}],
    })
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)

    gate_body = (
        '# 最终验收确认\n\n'
        '## 结果\n- 状态: active\n\n'
        '## 修改清单\n\n'
        '<!-- 如需 Agent 做定点修改，请在此列出具体事项（每项一行）。\n'
        '     留空则 Agent 收到完整验收文档作为参考。-->\n\n'
        '## 人工审阅清单\n- [ ] 实际结果满足已批准的验收标准。\n\n'
    )
    gate_body = normalize_final_acceptance_rejection_routing(
        gate_body, selected_route='implementation'
    )
    write_gate_file(approvals_dir / 'final-acceptance.md', gate_body)

    controller.reject_final_acceptance_gate()

    saved = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    feedback = saved['finalAcceptanceRejectionFeedback']
    assert '# 最终验收确认' in feedback, 'Full gate should be used when patch list is empty'
    assert '留空则 Agent 收到完整验收文档作为参考' not in feedback


def test_plannotator_final_acceptance_feedback_is_not_replaced_by_template_patch_comment(tmp_path: Path) -> None:
    from workflow_controller.gates.parsers import write_gate_file
    from workflow_controller.gates.generators import normalize_final_acceptance_rejection_routing

    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(tmp_path / 'workspace')
    initial_state.update({
        'currentStep': 'WAITING_FINAL_ACCEPTANCE',
        'unitPlanDraftGenerated': True,
        'unitPlanAccepted': True,
        'scopeApproved': True,
        'units': [{'id': 'u1', 'passes': True}],
        'objectiveCoverage': [{'objective': 'obj1', 'status': 'covered', 'units': ['u1']}],
    })
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    gate_path = approvals_dir / 'final-acceptance.md'

    gate_body = (
        '# 最终验收确认\n\n'
        '## 结果\n- 状态: active\n\n'
        '## 修改清单\n\n'
        '<!-- 如需 Agent 做定点修改，请在此列出具体事项（每项一行）。\n'
        '     留空则 Agent 收到完整验收文档作为参考。-->\n\n'
        '## 人工审阅清单\n- [ ] 实际结果满足已批准的验收标准。\n\n'
    )
    gate_body = normalize_final_acceptance_rejection_routing(
        gate_body, selected_route='implementation'
    )
    write_gate_file(gate_path, gate_body)

    plannotator_dir = state_dir / 'plannotator'
    plannotator_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = plannotator_dir / 'final-acceptance-last-review.stdout.log'
    stdout_path.write_text(
        json.dumps(
            {
                'decision': 'annotated',
                'feedback': '# File Feedback\n\n没有给上传材料的入口\n\n实现返工需要补齐上传入口。',
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    (plannotator_dir / 'final-acceptance-last-review.json').write_text(
        json.dumps(
            {
                'gate_path': str(gate_path),
                'approval_gate_path': str(gate_path),
                'stdout_path': str(stdout_path),
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )

    controller.reject_final_acceptance_gate()

    saved = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    feedback = saved['finalAcceptanceRejectionFeedback']
    assert '没有给上传材料的入口' in feedback
    assert '实现返工需要补齐上传入口' in feedback
    assert '留空则 Agent 收到完整验收文档作为参考' not in feedback
