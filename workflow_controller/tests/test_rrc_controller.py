from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

from workflow_controller.rrc_controller import RalphRefinerController, parse_args


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


def test_status_reports_current_step_and_next_action(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir))
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc('status', '--state-dir', str(state_dir))

    assert result.returncode == 0, result.stderr
    assert 'currentStep=PLAN_CREATED' in result.stdout
    assert 'nextAction=require_scope_approval' in result.stdout


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
    assert '状态：待确认' in result.stdout
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
    assert 'https://share.plannotator.ai/#fake' in result.stdout
    assert '完成审阅后，请回到这里输入 a 通过、r 返工或 q 退出。' in result.stdout
    assert json.loads(plannotator_log.read_text(encoding='utf-8')) == [
        'annotate',
        str(gate_path),
        '--gate',
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
    assert json.loads(env_log.read_text(encoding='utf-8')) == {'port': '20000'}


def test_drive_returns_after_plannotator_prints_link_even_if_review_keeps_running(
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
    pid_file = tmp_path / 'plannotator.pid'
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
import os
import time
from pathlib import Path

Path(os.environ['PLANNOTATOR_PID']).write_text(str(os.getpid()), encoding='utf-8')
print('Open this link on your local machine to annotate:', flush=True)
print('https://share.plannotator.ai/#long-running', flush=True)
time.sleep(60)
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)
    monkeypatch.setenv('PLANNOTATOR_PID', str(pid_file))

    try:
        result = run_rrc(
            'drive',
            '--state-dir',
            str(state_dir),
            '--auto-approve',
            '--plannotator-command',
            str(fake_plannotator),
            input_text='v\nq\n',
        )
    finally:
        if pid_file.exists():
            pid = int(pid_file.read_text(encoding='utf-8'))
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    assert result.returncode == 0, result.stderr
    assert '[Plannotator] 已打开辅助审阅。' in result.stdout
    assert 'https://share.plannotator.ai/#long-running' in result.stdout
    assert 'timed out' not in result.stdout
    summary = json.loads((state_dir / 'plannotator' / 'unit-plan-last-review.json').read_text(encoding='utf-8'))
    assert summary['process_id'] > 0
    assert summary['returncode'] is None


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
    from workflow_controller.rrc_human_gates import approve_gate_file, write_gate_file

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


def test_drive_shows_unit_plan_gate_again_when_approved_plan_is_invalid(tmp_path: Path) -> None:
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
    from workflow_controller.rrc_human_gates import write_gate_file

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
    assert result.stdout.count('[人工确认] Unit Plan') == 2
    assert '[停止] 已达到最大自动步数' not in result.stdout


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
        input_text='r\n3\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[验收路由] 请选择最终验收不通过后的流向：' in result.stdout
    assert '3  实现返工 -> Builder' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'EXECUTE_UNIT'
    assert state['finalAcceptanceRejectionRoute'] == 'implementation'
    content = gate_path.read_text(encoding='utf-8')
    assert '- [x] Implementation rework:' in content
    assert 'Reviewer note: button copy is wrong.' in content


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
