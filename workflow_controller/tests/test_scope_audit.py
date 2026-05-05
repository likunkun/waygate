from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from workflow_controller.gates.generators import ensure_final_acceptance_gate
from workflow_controller.gates.parsers import approve_gate_file, write_gate_file
from workflow_controller.rrc_controller import RalphRefinerController
from workflow_controller.scope_audit import (
    validate_final_scope_audit,
    write_final_scope_audit,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')


def _final_acceptance_state(workspace: Path | None = None) -> dict:
    state = {
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
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': 'Delivery is visible', 'priority': 'must', 'status': 'open'},
            {'id': 'AO-002', 'title': 'Manual acceptance recorded', 'priority': 'must', 'status': 'open'},
        ],
        'objectiveCoverage': [
            {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
        ],
        'units': [
            {'id': 'unit-01', 'name': 'Delivery unit', 'passes': True},
        ],
        'baselineChangedFiles': [],
    }
    if workspace is not None:
        state['workspacePath'] = str(workspace)
    return state


def _write_requirements(path: Path, ac_ids: list[str] | None = None) -> None:
    ac_ids = ac_ids or ['AC-1', 'AC-2']
    path.parent.mkdir(parents=True, exist_ok=True)
    write_gate_file(
        path,
        '# Requirements & Acceptance Confirmation\n\n'
        '## Acceptance Criteria\n\n'
        + '\n'.join(f'- {ac_id} [verification: e2e] delivery requirement' for ac_id in ac_ids)
        + '\n',
    )
    approve_gate_file(path, actor='tester')


def _write_unit_artifacts(artifacts_dir: Path, evidence_rows: list[dict]) -> None:
    unit_dir = artifacts_dir / 'unit-01'
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / 'changed-files.txt').write_text('src/delivery.py\n', encoding='utf-8')
    _write_json(unit_dir / 'builder-summary.json', {'runner_status': 'done'})
    _write_json(unit_dir / 'review.json', {'passed': True, 'issues': []})
    _write_json(
        unit_dir / 'verification.json',
        {
            'passed': True,
            'commands': ['pytest tests/test_delivery.py -q'],
            'evidence_schema_version': 'v0.3.5',
            'evidence_rows': evidence_rows,
        },
    )


def _passed_row(ac_id: str, ao_ids: list[str]) -> dict:
    return {
        'unit_id': 'unit-01',
        'test_case_id': f'TC-{ac_id}',
        'acceptance_criterion': ac_id,
        'acceptance_obligations': ao_ids,
        'layer': 'e2e',
        'command': 'pytest tests/test_delivery.py -q',
        'manual_evidence': None,
        'expected': f'{ac_id} is satisfied',
        'status': 'passed',
        'result_index': 0,
        'returncode': 0,
        'artifact_refs': ['artifacts/unit-01/verification.json'],
        'golden_path': True,
    }


def _manual_row(ac_id: str, ao_ids: list[str], manual_evidence: str | None, artifact_refs: list[str]) -> dict:
    return {
        'unit_id': 'unit-01',
        'test_case_id': f'TC-{ac_id}',
        'acceptance_criterion': ac_id,
        'acceptance_obligations': ao_ids,
        'layer': 'manual',
        'command': None,
        'manual_evidence': manual_evidence,
        'expected': f'{ac_id} is manually accepted',
        'status': 'manual',
        'result_index': None,
        'returncode': None,
        'artifact_refs': artifact_refs,
        'golden_path': False,
    }


def test_scope_audit_writes_json_and_markdown_with_manual_evidence_rules(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    requirements_path = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    _write_requirements(requirements_path, ['AC-1', 'AC-2', 'AC-3'])
    _write_unit_artifacts(
        artifacts_dir,
        [
            _passed_row('AC-1', ['AO-001']),
            _manual_row('AC-2', ['AO-002'], None, ['approvals/unit-plan.md']),
            _manual_row('AC-3', [], None, []),
        ],
    )

    audit = write_final_scope_audit(
        _final_acceptance_state(),
        artifacts_dir,
        requirements_path=requirements_path,
    )

    assert (artifacts_dir / 'final-scope-audit' / 'scope-audit.json').exists()
    assert (artifacts_dir / 'final-scope-audit' / 'scope-audit.md').exists()
    assert audit['ao_coverage']['covered_ids'] == ['AO-001', 'AO-002']
    assert audit['ac_coverage']['covered_ids'] == ['AC-1', 'AC-2']
    assert audit['ac_coverage']['uncovered_ids'] == ['AC-3']
    assert any(issue['type'] == 'missing_acceptance_criterion_evidence' for issue in audit['issues'])
    with pytest.raises(ValueError, match='AC-3'):
        validate_final_scope_audit(audit)


def test_final_acceptance_gate_renders_final_scope_audit_summary(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    approvals_dir = tmp_path / 'approvals'
    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    _write_requirements(requirements_path)
    _write_unit_artifacts(
        artifacts_dir,
        [
            _passed_row('AC-1', ['AO-001']),
            _manual_row('AC-2', ['AO-002'], 'Manual approval recorded in unit plan.', []),
        ],
    )
    write_final_scope_audit(
        _final_acceptance_state(),
        artifacts_dir,
        requirements_path=requirements_path,
    )

    gate_path = ensure_final_acceptance_gate(
        _final_acceptance_state(),
        approvals_dir,
        artifacts_dir,
        force=True,
    )

    content = gate_path.read_text(encoding='utf-8')
    assert '## Final Scope Audit' in content
    assert '- AO coverage: `2/2`' in content
    assert '- AC coverage: `2/2`' in content
    assert '- Journey coverage: `0/0`' in content
    assert '- Unexplained changed files: `0`' in content
    assert '`artifacts/final-scope-audit/scope-audit.json`' in content
    assert '`artifacts/final-scope-audit/scope-audit.md`' in content


def test_final_acceptance_approval_blocks_missing_ao_and_ac_evidence(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_final_acceptance_state(), force=True)
    approvals_dir = state_dir / 'approvals'
    artifacts_dir = state_dir / 'artifacts'
    _write_requirements(approvals_dir / 'requirements-and-acceptance.md')
    _write_unit_artifacts(artifacts_dir, [_passed_row('AC-1', ['AO-001'])])

    gate_path = ensure_final_acceptance_gate(
        controller.store.load_state(),
        approvals_dir,
        artifacts_dir,
        force=True,
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['finalAcceptanceAccepted'] is False
    assert state['currentStep'] == 'WAITING_FINAL_ACCEPTANCE'
    assert state['blockedReason'].startswith('final acceptance gate invalid:')
    assert 'AO-002' in state['blockedReason']
    assert 'AC-2' in state['blockedReason']


def test_scope_audit_records_missing_active_journey_as_blocker(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    approvals_dir = tmp_path / 'approvals'
    journey_dir = artifacts_dir / 'journeys'
    journey_dir.mkdir(parents=True, exist_ok=True)
    journey_path = journey_dir / 'journeys.json'
    _write_json(
        journey_path,
        {
            'version': 1,
            'journeys': [
                {
                    'journey_id': 'J-001',
                    'title': 'Delivery happy path',
                    'status': 'active',
                    'linked_acceptance_criteria': ['AC-1'],
                }
            ],
        },
    )
    state = _final_acceptance_state()
    state['journeyContractPath'] = str(journey_path)
    _write_requirements(approvals_dir / 'requirements-and-acceptance.md')
    _write_unit_artifacts(
        artifacts_dir,
        [
            _passed_row('AC-1', ['AO-001']),
            _manual_row('AC-2', ['AO-002'], 'Manual approval recorded.', []),
        ],
    )

    audit = write_final_scope_audit(
        state,
        artifacts_dir,
        requirements_path=approvals_dir / 'requirements-and-acceptance.md',
    )

    assert audit['journey_coverage']['uncovered_ids'] == ['J-001']
    with pytest.raises(ValueError, match='J-001'):
        validate_final_scope_audit(audit)


def test_unexplained_changed_file_is_a_review_warning_not_final_approval_blocker(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    subprocess.run(['git', 'init'], cwd=workspace, text=True, capture_output=True, check=True)
    unplanned = workspace / 'src' / 'unplanned.py'
    unplanned.parent.mkdir()
    unplanned.write_text('print("unplanned")\n', encoding='utf-8')
    subprocess.run(['git', 'add', '-N', 'src/unplanned.py'], cwd=workspace, text=True, capture_output=True, check=True)

    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True, agent_guides_enabled=False)
    state = _final_acceptance_state(workspace)
    controller.init_state(state, force=True)
    approvals_dir = state_dir / 'approvals'
    artifacts_dir = state_dir / 'artifacts'
    _write_requirements(approvals_dir / 'requirements-and-acceptance.md')
    _write_unit_artifacts(
        artifacts_dir,
        [
            _passed_row('AC-1', ['AO-001']),
            _manual_row('AC-2', ['AO-002'], 'Manual approval recorded.', []),
        ],
    )
    write_final_scope_audit(
        controller.store.load_state(),
        artifacts_dir,
        requirements_path=approvals_dir / 'requirements-and-acceptance.md',
        workspace_dir=workspace,
    )

    gate_path = ensure_final_acceptance_gate(
        controller.store.load_state(),
        approvals_dir,
        artifacts_dir,
        force=True,
    )
    approve_gate_file(gate_path, actor='tester')

    final_state = controller.run_once()
    audit = json.loads((artifacts_dir / 'final-scope-audit' / 'scope-audit.json').read_text(encoding='utf-8'))
    content = gate_path.read_text(encoding='utf-8')

    assert final_state['finalAcceptanceAccepted'] is True
    assert final_state['currentStep'] == 'RELEASE_GATE'
    assert audit['changed_files']['unexplained_changed_files'] == ['src/unplanned.py']
    assert any(issue['type'] == 'unexplained_changed_file' for issue in audit['issues'])
    assert '- Unexplained changed files: `1`' in content
    assert '`src/unplanned.py`' in content
