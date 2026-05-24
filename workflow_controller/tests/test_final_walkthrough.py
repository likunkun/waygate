from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path

import pytest

from workflow_controller.gates.generators import ensure_final_acceptance_gate
from workflow_controller.gates.validators import validate_unit_plan_final_acceptance_walkthrough
from workflow_controller.rrc_controller import RalphRefinerController
from workflow_controller.steps.final_walkthrough import run_final_walkthrough_prepare


def _golden_case() -> dict[str, object]:
    return {
        'id': 'TC-GP-01',
        'acceptance_criterion': 'AC-01',
        'covers_obligations': ['AO-001'],
        'covers_journeys': ['J-001'],
        'layer': 'e2e',
        'environment_kind': 'local_real',
        'entrypoint': 'http://127.0.0.1:4173/orders',
        'real_entrypoint': 'http://127.0.0.1:4173/orders',
        'golden_path': True,
        'fixture': 'Seed order ORD-100 for user reviewer@example.test',
        'user_steps': [
            'Open the orders page',
            'Create order ORD-100',
            'Confirm the order appears in the submitted list',
        ],
        'command': 'python3 -m pytest tests/e2e/test_orders.py -q',
        'expected': 'Order ORD-100 is visible with status submitted and persisted row count 1',
    }


def _inspection() -> dict[str, object]:
    return {
        'surface_kind': 'browser',
        'entrypoint': 'http://127.0.0.1:4173/orders',
        'manual_steps': [
            'Open the orders page in a browser',
            'Create order ORD-100 as reviewer@example.test',
            'Confirm the order appears in the submitted list',
        ],
        'expected_observations': [
            'Order ORD-100 is visible with status submitted',
            'The submitted list count increases to 1',
        ],
    }


def _state(
    tmp_path: Path,
    launch: dict[str, object],
    *,
    inspection: dict[str, object] | None = None,
    omit_inspection: bool = False,
) -> dict[str, object]:
    walkthrough: dict[str, object] = {'launch': launch}
    if not omit_inspection:
        walkthrough['inspection'] = inspection or _inspection()
    return {
        'task_id': 'walkthrough',
        'currentUnitId': 'unit-01',
        'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
        'status': 'active',
        'workspacePath': str(tmp_path),
        'executionWorkspacePath': str(tmp_path),
        'objectiveCoverage': [
            {'objective': 'Orders golden path', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'workflow_validation_level': 'closure',
                'final_acceptance_walkthrough': walkthrough,
                'test_cases': [_golden_case()],
                'verification_commands': ['python3 -m pytest tests/e2e/test_orders.py -q'],
            }
        ],
    }


def test_unit_plan_final_walkthrough_accepts_agent_start_with_readiness_hint(tmp_path: Path) -> None:
    validate_unit_plan_final_acceptance_walkthrough(
        _state(
            tmp_path,
            {
                'mode': 'agent_start',
                'command': 'pnpm exec vite --host 127.0.0.1',
                'cwd': '.',
                'env_keys': ['DATABASE_URL', 'PORT'],
                'ready_url': 'http://127.0.0.1:4173',
                'ready_timeout_seconds': 30,
                'stop_command': 'pkill -f vite',
            },
        )
    )


def test_unit_plan_final_walkthrough_rejects_closure_unit_missing_inspection(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match='inspection.entrypoint'):
        validate_unit_plan_final_acceptance_walkthrough(
            _state(
                tmp_path,
                {
                    'mode': 'manual_only',
                    'manual_launch_instructions': 'Run `pnpm dev` and open http://127.0.0.1:4173/orders.',
                },
                omit_inspection=True,
            )
        )


@pytest.mark.parametrize('surface_kind', ['browser', 'api', 'cli', 'artifact'])
def test_unit_plan_final_walkthrough_accepts_manual_inspection_surface_kinds(
    tmp_path: Path,
    surface_kind: str,
) -> None:
    validate_unit_plan_final_acceptance_walkthrough(
        _state(
            tmp_path,
            {
                'mode': 'manual_only',
                'manual_launch_instructions': 'Open the declared inspection entrypoint.',
            },
            inspection={
                'surface_kind': surface_kind,
                'entrypoint': 'python3 -m workflow_controller.cli status --state-dir .rrc',
                'manual_steps': ['Run the CLI status command against the target controller state'],
                'expected_observations': ['The command prints currentStep and nextAction for the target workflow'],
            },
        )
    )


def test_unit_plan_final_walkthrough_rejects_test_only_manual_steps(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match='manual_steps'):
        validate_unit_plan_final_acceptance_walkthrough(
            _state(
                tmp_path,
                {
                    'mode': 'manual_only',
                    'manual_launch_instructions': 'Run `pnpm dev` and open http://127.0.0.1:4173/orders.',
                },
                inspection={
                    'surface_kind': 'browser',
                    'entrypoint': 'http://127.0.0.1:4173/orders',
                    'manual_steps': ['Run python3 -m pytest tests/e2e/test_orders.py -q'],
                    'expected_observations': ['pytest exits 0'],
                },
            )
        )


@pytest.mark.parametrize(
    ('launch', 'expected'),
    [
        ({'mode': 'agent_start', 'ready_url': 'http://127.0.0.1:4173'}, 'command'),
        ({'mode': 'agent_start', 'command': 'pnpm dev'}, 'readiness'),
        ({'mode': 'agent_start', 'command': 'pnpm dev', 'ready_url': 'http://127.0.0.1:4173', 'cwd': '../outside'}, 'cwd'),
        ({'mode': 'agent_start', 'command': 'pnpm dev', 'ready_url': 'http://127.0.0.1:4173', 'env_keys': ['DATABASE_URL=postgres://secret']}, 'secret'),
        ({'mode': 'agent_start', 'command': 'pnpm dev', 'ready_url': 'http://127.0.0.1:4173', 'env': {'DATABASE_URL': 'postgres://secret'}}, 'secret'),
        ({'mode': 'manual_only'}, 'manual_launch_instructions'),
        ({'mode': 'sometimes'}, 'mode'),
    ],
)
def test_unit_plan_final_walkthrough_rejects_invalid_launch_contract(
    tmp_path: Path,
    launch: dict[str, object],
    expected: str,
) -> None:
    with pytest.raises(ValueError, match=expected):
        validate_unit_plan_final_acceptance_walkthrough(_state(tmp_path, launch))


def test_final_walkthrough_prepare_records_agent_start_success(tmp_path: Path) -> None:
    command = (
        f'{sys.executable} -c '
        '"import time; print(\'READY\', flush=True); time.sleep(30)"'
    )
    state = _state(
        tmp_path,
        {
            'mode': 'agent_start',
            'command': command,
            'ready_output_contains': 'READY',
            'ready_timeout_seconds': 5,
            'stop_command': 'pkill -f READY',
        },
    )
    artifacts_dir = tmp_path / 'artifacts'

    result = run_final_walkthrough_prepare(state, artifacts_dir=artifacts_dir, workspace_dir=tmp_path)
    payload = json.loads((artifacts_dir / 'unit-01' / 'final-walkthrough-launch.json').read_text(encoding='utf-8'))

    assert result.summary == 'final walkthrough launch ready'
    assert payload['status'] == 'ready'
    assert payload['launch']['mode'] == 'agent_start'
    assert payload['ready_check']['type'] == 'output'
    assert payload['log_path'].endswith('final-walkthrough-launch.log')
    assert payload['pid']
    os.kill(int(payload['pid']), signal.SIGTERM)


def test_final_walkthrough_prepare_records_agent_start_failure(tmp_path: Path) -> None:
    state = _state(
        tmp_path,
        {
            'mode': 'agent_start',
            'command': f'{sys.executable} -c "import sys; sys.exit(42)"',
            'ready_output_contains': 'READY',
            'ready_timeout_seconds': 1,
            'manual_launch_instructions': 'Run `pnpm dev` manually if startup fails.',
        },
    )
    artifacts_dir = tmp_path / 'artifacts'

    result = run_final_walkthrough_prepare(state, artifacts_dir=artifacts_dir, workspace_dir=tmp_path)
    payload = json.loads((artifacts_dir / 'unit-01' / 'final-walkthrough-launch.json').read_text(encoding='utf-8'))

    assert result.summary == 'final walkthrough launch failed'
    assert payload['status'] == 'failed'
    assert payload['returncode'] == 42
    assert 'Run `pnpm dev` manually' in payload['manual_launch_instructions']


def test_final_walkthrough_prepare_records_manual_only_fallback(tmp_path: Path) -> None:
    state = _state(
        tmp_path,
        {
            'mode': 'manual_only',
            'manual_launch_instructions': 'Run `pnpm dev` in the target workspace and open http://127.0.0.1:4173.',
        },
    )
    artifacts_dir = tmp_path / 'artifacts'

    result = run_final_walkthrough_prepare(state, artifacts_dir=artifacts_dir, workspace_dir=tmp_path)
    payload = json.loads((artifacts_dir / 'unit-01' / 'final-walkthrough-launch.json').read_text(encoding='utf-8'))

    assert result.summary == 'final walkthrough launch manual'
    assert payload['status'] == 'manual_only'
    assert 'Run `pnpm dev`' in payload['manual_launch_instructions']


def _write_final_artifacts(artifacts_dir: Path) -> None:
    unit_dir = artifacts_dir / 'unit-01'
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / 'changed-files.txt').write_text('src/orders.py\n', encoding='utf-8')
    (unit_dir / 'builder-summary.json').write_text(
        json.dumps({'runner_status': 'done', 'done_payload': {'summary': 'Orders implemented'}}),
        encoding='utf-8',
    )
    (unit_dir / 'review.json').write_text(json.dumps({'passed': True, 'issues': []}), encoding='utf-8')
    (unit_dir / 'verification.json').write_text(
        json.dumps(
            {
                'passed': True,
                'commands': ['python3 -m pytest tests/e2e/test_orders.py -q'],
                'results': [
                    {
                        'command': 'python3 -m pytest tests/e2e/test_orders.py -q',
                        'ok': True,
                        'returncode': 0,
                    }
                ],
                'evidence_schema_version': 'v0.3.5',
                'evidence_rows': [
                    {
                        'unit_id': 'unit-01',
                        'test_case_id': 'TC-GP-01',
                        'acceptance_criterion': 'AC-01',
                        'acceptance_obligations': ['AO-001'],
                        'layer': 'e2e',
                        'command': 'python3 -m pytest tests/e2e/test_orders.py -q',
                        'manual_evidence': '',
                        'expected': 'Order ORD-100 is visible with status submitted and persisted row count 1',
                        'status': 'passed',
                        'result_index': 0,
                        'returncode': 0,
                        'artifact_refs': ['green-test.txt', 'verification.json'],
                        'golden_path': True,
                        'environment_kind': 'local_real',
                        'real_entrypoint': 'http://127.0.0.1:4173/orders',
                        'uses_core_api_mock': False,
                        'mocked_routes': [],
                        'browser_console_errors': [],
                        'page_errors': [],
                        'request_failures': [],
                        'screenshot_refs': [],
                        'visual_evidence_refs': {},
                    }
                ],
            }
        ),
        encoding='utf-8',
    )


def test_controller_runs_final_walkthrough_prepare_before_final_acceptance_gate(tmp_path: Path) -> None:
    controller = RalphRefinerController(
        state_dir=tmp_path / '.rrc',
        workspace_dir=tmp_path,
        agent_guides_enabled=False,
    )
    state = _state(
        tmp_path,
        {
            'mode': 'manual_only',
            'manual_launch_instructions': 'Run `pnpm dev` and open http://127.0.0.1:4173/orders.',
        },
    )
    state.update(
        {
            'currentStep': 'UNIT_COMPLETE',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'scopeApproved': True,
        }
    )
    controller.init_state(state, force=True)

    first = controller.run_once()

    assert first['currentStep'] == 'FINAL_WALKTHROUGH_PREPARE'
    assert first['nextAllowedActions'] == ['prepare_final_walkthrough']

    _write_final_artifacts(controller.artifacts_dir)

    second = controller.run_once()

    assert second['currentStep'] == 'WAITING_FINAL_ACCEPTANCE'
    assert (controller.artifacts_dir / 'unit-01' / 'final-walkthrough-launch.json').exists()
    assert (controller.approvals_dir / 'final-acceptance.md').exists()


def test_final_acceptance_gate_renders_guided_golden_path_walkthrough(tmp_path: Path) -> None:
    state = _state(
        tmp_path,
        {
            'mode': 'manual_only',
            'manual_launch_instructions': 'Run `pnpm dev` and open http://127.0.0.1:4173/orders.',
        },
    )
    state['currentStep'] = 'WAITING_FINAL_ACCEPTANCE'
    state['units'][0]['passes'] = True
    state['objectiveCoverage'][0]['status'] = 'covered'
    artifacts_dir = tmp_path / 'artifacts'
    _write_final_artifacts(artifacts_dir)
    (artifacts_dir / 'unit-01' / 'final-walkthrough-launch.json').write_text(
        json.dumps(
            {
                'unit_id': 'unit-01',
                'status': 'manual_only',
                'launch': {'mode': 'manual_only'},
                'manual_launch_instructions': 'Run `pnpm dev` and open http://127.0.0.1:4173/orders.',
                'generated_at': '2026-05-23T00:00:00+00:00',
            }
        ),
        encoding='utf-8',
    )

    gate_path = ensure_final_acceptance_gate(state, tmp_path / 'approvals', artifacts_dir, force=True)
    content = gate_path.read_text(encoding='utf-8')

    assert '## Golden Path 人工走查' in content
    assert 'Run `pnpm dev` and open http://127.0.0.1:4173/orders.' in content
    assert 'TC-GP-01' in content
    assert 'AO-001' in content
    assert 'J-001' in content
    assert 'Seed order ORD-100' in content
    assert 'Open the orders page' in content
    assert 'Order ORD-100 is visible' in content
    assert '### 人工走查确认' in content
    assert '### 观察记录' in content
    assert '## 修改清单' in content


def test_final_acceptance_gate_uses_builder_confirmed_inspection_entrypoint(tmp_path: Path) -> None:
    state = _state(
        tmp_path,
        {
            'mode': 'manual_only',
            'manual_launch_instructions': 'Run `pnpm dev` and open http://127.0.0.1:4173/orders.',
        },
    )
    state['currentStep'] = 'WAITING_FINAL_ACCEPTANCE'
    state['units'][0]['passes'] = True
    state['objectiveCoverage'][0]['status'] = 'covered'
    artifacts_dir = tmp_path / 'artifacts'
    _write_final_artifacts(artifacts_dir)
    builder_summary = json.loads((artifacts_dir / 'unit-01' / 'builder-summary.json').read_text(encoding='utf-8'))
    builder_summary['done_payload']['final_acceptance_walkthrough'] = {
        'inspection': {
            'surface_kind': 'browser',
            'entrypoint': 'http://127.0.0.1:5173/orders',
            'manual_steps': ['Open the Vite-selected port 5173 orders page'],
            'expected_observations': ['Order ORD-100 is visible with status submitted'],
            'reason': 'The implementation started on Vite fallback port 5173 after 4173 was occupied.',
        }
    }
    (artifacts_dir / 'unit-01' / 'builder-summary.json').write_text(
        json.dumps(builder_summary),
        encoding='utf-8',
    )

    gate_path = ensure_final_acceptance_gate(state, tmp_path / 'approvals', artifacts_dir, force=True)
    content = gate_path.read_text(encoding='utf-8')

    assert '## Agent 提供的人工走查入口' in content
    assert 'http://127.0.0.1:5173/orders' in content
    assert 'Vite fallback port 5173' in content
    assert 'http://127.0.0.1:4173/orders' not in content.split('## Agent 提供的人工走查入口', 1)[1].split('##', 1)[0]


def test_final_acceptance_approval_requires_manual_observation_record(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc'
    controller = RalphRefinerController(
        state_dir=state_dir,
        workspace_dir=tmp_path,
        auto_approve=True,
        agent_guides_enabled=False,
    )
    state = _state(
        tmp_path,
        {
            'mode': 'manual_only',
            'manual_launch_instructions': 'Run `pnpm dev` and open http://127.0.0.1:4173/orders.',
        },
    )
    state.update(
        {
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'scopeApproved': True,
        }
    )
    state['units'][0]['passes'] = True
    state['objectiveCoverage'][0]['status'] = 'covered'
    controller.init_state(state, force=True)
    _write_final_artifacts(controller.artifacts_dir)
    gate_path = ensure_final_acceptance_gate(controller.store.load_state(), controller.approvals_dir, controller.artifacts_dir, force=True)

    from workflow_controller.gates.parsers import approve_gate_file

    with pytest.raises(ValueError, match='人工系统观察记录'):
        controller.approve_human_gate('final-acceptance', actor='tester')

    approve_gate_file(gate_path, actor='tester')
    blocked = controller.run_once()

    assert blocked['currentStep'] == 'WAITING_FINAL_ACCEPTANCE'
    assert blocked['finalAcceptanceAccepted'] is False
    assert '人工系统观察记录' in blocked['blockedReason']

    content = gate_path.read_text(encoding='utf-8')
    content = content.replace(
        '- Observed entrypoint: \n',
        '- Observed entrypoint: http://127.0.0.1:4173/orders\n',
    )
    content = content.replace(
        '- Actual observation: \n',
        '- Actual observation: Order ORD-100 appeared with status submitted.\n',
    )
    content = content.replace(
        '- Data/account/fixture: \n',
        '- Data/account/fixture: reviewer@example.test / ORD-100 seed data\n',
    )
    content = content.replace(
        '- Issues or evidence path: \n',
        '- Issues or evidence path: artifacts/unit-01/final-acceptance-screenshot.png\n',
    )
    gate_path.write_text(content, encoding='utf-8')
    approve_gate_file(gate_path, actor='tester')
    accepted = controller.run_once()

    assert accepted['finalAcceptanceAccepted'] is True
    assert accepted['currentStep'] == 'RELEASE_GATE'
