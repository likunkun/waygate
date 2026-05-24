from __future__ import annotations

import json
import sys
from pathlib import Path

from workflow_controller.gates.generators import ensure_final_acceptance_gate
from workflow_controller.gates.validators import (
    validate_unit_plan_golden_path,
    validate_unit_plan_verification_assist_contract,
    validate_verification_evidence_schema,
)
from workflow_controller.steps.builder import run_verifier


def test_flexible_evidence_schema_records_strict_and_descriptive_rows(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    strict_command = "python -c \"print('strict command passed')\""
    descriptive_command = "python -c \"print('descriptive command output')\""
    state = {
        'currentUnitId': 'unit-01',
        'workspacePath': str(workspace),
        'units': [
            {
                'id': 'unit-01',
                'test_cases': [
                    {
                        'id': 'TC-STRICT-CMD',
                        'acceptance_criterion': 'AC-15',
                        'layer': 'integration',
                        'command': strict_command,
                        'expected': 'strict command exits 0',
                    },
                    {
                        'id': 'TC-DESC-CMD',
                        'acceptance_criterion': 'AC-15',
                        'layer': 'integration',
                        'command': descriptive_command,
                        'description': 'Inspect the flexible evidence artifact for risk annotations.',
                        'evidence_type': 'descriptive_command',
                        'expected': 'descriptive command exits 0 and risk notes remain human-reviewed',
                        'agent_assisted_judgement': {
                            'status': 'needs_human_review',
                            'summary': 'Command output exists, but mapping strength needs human review.',
                        },
                        'risk_annotations': [
                            {
                                'category': 'weak_evidence',
                                'severity': 'medium',
                                'note': 'The command proves shape, while acceptance mapping remains descriptive.',
                            }
                        ],
                        'structured_evidence_refs': ['artifacts/unit-01/final-assist.json'],
                        'human_review_required': True,
                    },
                ],
                'verification_commands': [strict_command, descriptive_command],
            }
        ],
    }
    unit_dir = tmp_path / 'artifacts' / 'unit-01'

    result = run_verifier(state, unit_dir, dry_run=False)

    assert result.summary == 'verification passed'
    verification_path = unit_dir / 'verification.json'
    verification = validate_verification_evidence_schema(verification_path)
    strict_row, descriptive_row = verification['evidence_rows']
    assert strict_row['test_case_id'] == 'TC-STRICT-CMD'
    assert 'agent_assisted_judgement' not in strict_row
    assert strict_row['status'] == 'passed'
    assert descriptive_row['test_case_id'] == 'TC-DESC-CMD'
    assert descriptive_row['evidence_type'] == 'descriptive_command'
    assert descriptive_row['description'] == 'Inspect the flexible evidence artifact for risk annotations.'
    assert descriptive_row['status'] == 'passed'
    assert descriptive_row['returncode'] == 0
    assert descriptive_row['agent_assisted_judgement']['status'] == 'needs_human_review'
    assert descriptive_row['risk_annotations'][0]['category'] == 'weak_evidence'
    assert descriptive_row['structured_evidence_refs'] == ['artifacts/unit-01/final-assist.json']
    assert descriptive_row['human_review_required'] is True


def test_agent_assisted_case_without_command_runs_assist_and_writes_evidence_row(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    assist_script = tmp_path / 'write_assist_artifact.py'
    assist_script.write_text(
        'from __future__ import annotations\n'
        'import json, os\n'
        "artifact = os.environ['WAYGATE_ANNOTATION_ARTIFACT']\n"
        'payload = {\n'
        '    "agent_assisted_judgement": {\n'
        '        "status": "passed",\n'
        '        "summary": "Checkout flow was observed through the requested entrypoint."\n'
        '    },\n'
        '    "risk_annotations": [\n'
        '        {"severity": "low", "category": "runtime_dependency_gap", "note": "Browser runtime remains human-reviewed."}\n'
        '    ],\n'
        '    "structured_evidence_refs": ["screenshots/checkout-confirmation.png"],\n'
        '    "human_review_required": True\n'
        '}\n'
        "with open(artifact, 'w', encoding='utf-8') as f:\n"
        '    json.dump(payload, f)\n',
        encoding='utf-8',
    )
    state = {
        'currentUnitId': 'unit-01',
        'workspacePath': str(workspace),
        'annotationAgents': {
            'final_acceptance_verification_assist': {
                'enabled': True,
                'role': 'final_acceptance_verification_assist',
                'backend': 'codex',
                'command': sys.executable,
                'args': [str(assist_script)],
                'artifact_path': 'assist/{case_id}.json',
                'timeout_seconds': 5,
                'failure_policy': 'block',
                'prompt_template': 'verification-assist-case-v1',
            }
        },
        'units': [
            {
                'id': 'unit-01',
                'test_cases': [
                    {
                        'id': 'TC-ASSIST-CHECKOUT',
                        'acceptance_criterion': 'AC-15',
                        'layer': 'e2e',
                        'environment_kind': 'local_real',
                        'entrypoint': 'http://localhost:3000/checkout',
                        'fixture': 'Seed checkout fixture order C-100.',
                        'expected': 'Order confirmation C-100 is visible after submit.',
                        'verification_assist': {
                            'description': 'Open checkout, submit order C-100, and inspect the confirmation page.',
                            'expected': [
                                'Confirmation heading is visible.',
                                'Order id C-100 is visible.',
                            ],
                            'evidence_required': ['screenshot', 'DOM state'],
                        },
                    }
                ],
                'verification_commands': [],
            }
        ],
    }
    unit_dir = tmp_path / 'artifacts' / 'unit-01'

    result = run_verifier(state, unit_dir, dry_run=False)

    assert result.summary == 'verification passed'
    verification_path = unit_dir / 'verification.json'
    verification = validate_verification_evidence_schema(verification_path)
    row = verification['evidence_rows'][0]
    assert verification['commands'] == []
    assert row['test_case_id'] == 'TC-ASSIST-CHECKOUT'
    assert row['command'] is None
    assert row['evidence_type'] == 'agent_assisted_case'
    assert row['description'] == 'Open checkout, submit order C-100, and inspect the confirmation page.'
    assert row['status'] == 'passed'
    assert row['agent_assisted_judgement']['summary'] == 'Checkout flow was observed through the requested entrypoint.'
    assert row['risk_annotations'][0]['category'] == 'runtime_dependency_gap'
    assert row['structured_evidence_refs'] == ['screenshots/checkout-confirmation.png']
    assert row['human_review_required'] is True
    assert row['assist_artifact_path'].endswith('assist/TC-ASSIST-CHECKOUT.json')
    assert Path(row['assist_artifact_path']).exists()


def test_unit_plan_verification_assist_contract_rejects_missing_fields_and_missing_config(tmp_path: Path) -> None:
    base_case = {
        'id': 'TC-ASSIST',
        'acceptance_criterion': 'AC-15',
        'layer': 'e2e',
        'expected': 'Visible confirmation after checkout.',
        'verification_assist': {
            'description': 'Inspect checkout in a difficult browser environment.',
            'expected': 'Visible confirmation after checkout.',
        },
    }
    valid_state = {
        'currentUnitId': 'unit-01',
        'annotationAgents': {
            'final_acceptance_verification_assist': {
                'enabled': True,
                'role': 'final_acceptance_verification_assist',
                'backend': 'codex',
                'command': sys.executable,
                'args': ['-c', 'print("ok")'],
            }
        },
        'units': [{'id': 'unit-01', 'test_cases': [base_case], 'verification_commands': []}],
    }
    validate_unit_plan_verification_assist_contract(valid_state, artifacts_dir=tmp_path)

    missing_description = json.loads(json.dumps(valid_state))
    del missing_description['units'][0]['test_cases'][0]['verification_assist']['description']
    try:
        validate_unit_plan_verification_assist_contract(missing_description, artifacts_dir=tmp_path)
    except ValueError as exc:
        assert 'verification_assist.description is required' in str(exc)
    else:
        raise AssertionError('missing description must be rejected')

    missing_expected = json.loads(json.dumps(valid_state))
    del missing_expected['units'][0]['test_cases'][0]['verification_assist']['expected']
    try:
        validate_unit_plan_verification_assist_contract(missing_expected, artifacts_dir=tmp_path)
    except ValueError as exc:
        assert 'verification_assist.expected is required' in str(exc)
    else:
        raise AssertionError('missing expected must be rejected')

    both_command_and_assist = json.loads(json.dumps(valid_state))
    both_command_and_assist['units'][0]['test_cases'][0]['command'] = 'python3 -m pytest tests/e2e.py'
    try:
        validate_unit_plan_verification_assist_contract(both_command_and_assist, artifacts_dir=tmp_path)
    except ValueError as exc:
        assert 'must use either command or verification_assist' in str(exc)
    else:
        raise AssertionError('command plus verification_assist must be rejected')

    missing_agent_config = json.loads(json.dumps(valid_state))
    missing_agent_config['annotationAgents'] = {}
    try:
        validate_unit_plan_verification_assist_contract(missing_agent_config, artifacts_dir=tmp_path)
    except ValueError as exc:
        assert 'has no enabled verification-assist agent config' in str(exc)
    else:
        raise AssertionError('missing assist config must be rejected')


def test_golden_path_allows_verification_assist_without_command(tmp_path: Path) -> None:
    state = {
        'currentUnitId': 'unit-01',
        'workspacePath': str(tmp_path),
        'annotationAgents': {
            'final_acceptance_verification_assist': {
                'enabled': True,
                'role': 'final_acceptance_verification_assist',
                'backend': 'codex',
                'command': sys.executable,
                'args': ['-c', 'print("ok")'],
            }
        },
        'units': [
            {
                'id': 'unit-01',
                'workflow_validation_level': 'closure',
                'test_cases': [
                    {
                        'id': 'TC-ASSIST-GOLDEN',
                        'acceptance_criterion': 'AC-15',
                        'layer': 'e2e',
                        'environment_kind': 'local_real',
                        'entrypoint': 'http://localhost:3000/checkout',
                        'fixture': 'Seed checkout fixture order C-100.',
                        'expected': 'Confirmation heading and order id C-100 are visible.',
                        'golden_path': True,
                        'verification_assist': {
                            'description': 'Open checkout, submit order C-100, and inspect the confirmation page.',
                            'expected': 'Confirmation heading and order id C-100 are visible.',
                            'evidence_required': ['screenshot', 'DOM state'],
                        },
                    }
                ],
                'verification_commands': [],
            }
        ],
    }

    validate_unit_plan_verification_assist_contract(state, artifacts_dir=tmp_path)
    validate_unit_plan_golden_path(state)


def test_final_matrix_flex_separates_deterministic_and_agent_assisted_evidence(tmp_path: Path) -> None:
    state = {
        'currentStep': 'VERIFY_UNIT',
        'status': 'active',
        'currentUnitId': 'unit-01',
        'objectiveCoverage': [],
    }
    artifacts_dir = tmp_path / 'artifacts'
    unit_dir = artifacts_dir / 'unit-01'
    unit_dir.mkdir(parents=True)
    (unit_dir / 'changed-files.txt').write_text('workflow_controller/steps/builder.py\n', encoding='utf-8')
    (unit_dir / 'builder-summary.json').write_text(
        json.dumps({'runner_status': 'done', 'done_payload': {'summary': 'Flexible evidence implemented'}}),
        encoding='utf-8',
    )
    (unit_dir / 'review.json').write_text(json.dumps({'passed': True, 'issues': []}), encoding='utf-8')
    (unit_dir / 'verification.json').write_text(
        json.dumps(
            {
                'passed': True,
                'commands': ['python -m pytest workflow_controller/tests/test_v061_flexible_evidence.py -q'],
                'evidence_schema_version': 'v0.3.5',
                'evidence_rows': [
                    _strict_row(),
                    _descriptive_row(),
                    _agent_assisted_case_row(),
                ],
            }
        ),
        encoding='utf-8',
    )

    gate_path = ensure_final_acceptance_gate(state, tmp_path / 'approvals', artifacts_dir, force=True)

    content = gate_path.read_text(encoding='utf-8')
    assert '## 验收证据矩阵（Final Acceptance Evidence Matrix）' in content
    assert '| AO | AC | Test Case | Layer | Environment | Real Entry | Core API Mock | Runtime Errors | Status | Evidence | Expected | Artifacts | Golden Path |' in content
    assert '| 未指定 | AC-16 | TC-STRICT-PASS | integration | local_real | python -c print-strict | no | none | passed | `python -c print-strict` | strict command passes | green-test.txt, verification.json | no |' in content
    assert '## Agent-Assisted Descriptive Evidence' in content
    assert 'Agent-assisted judgement is risk context only and never approval.' in content
    assert '| AC | Test Case | Command | Description | Deterministic Status | Agent-Assisted Judgement | Human Review Required | Risks | Structured Evidence |' in content
    assert '| AC-16 | TC-DESC-ASSIST | `python -c print-descriptive` | Human checks mapped evidence strength. | passed | needs_human_review: Evidence shape is present, mapping remains a human call. | yes | medium/weak_evidence: Mapping is descriptive. | artifacts/unit-01/final-assist.json |' in content
    assert '| AC-16 | TC-DESC-ASSIST | integration |' not in content
    assert '## Agent-Assisted Verification Evidence' in content
    assert 'Agent-assisted verification evidence is controller evidence, not approval.' in content
    assert '| AC | Test Case | Description | Status | Agent-Assisted Judgement | Human Review Required | Risks | Structured Evidence | Assist Artifact |' in content
    assert '| AC-15 | TC-ASSIST-CHECKOUT | Open checkout and inspect confirmation page. | passed | passed: Checkout flow was observed. | yes | low/runtime_dependency_gap: Browser runtime remains human-reviewed. | screenshots/checkout-confirmation.png | artifacts/unit-01/assist/TC-ASSIST-CHECKOUT.json |' in content


def _strict_row() -> dict:
    return {
        'unit_id': 'unit-01',
        'test_case_id': 'TC-STRICT-PASS',
        'acceptance_criterion': 'AC-16',
        'acceptance_obligations': [],
        'layer': 'integration',
        'command': 'python -c print-strict',
        'manual_evidence': None,
        'expected': 'strict command passes',
        'status': 'passed',
        'result_index': 0,
        'returncode': 0,
        'artifact_refs': ['green-test.txt', 'verification.json'],
        'golden_path': False,
        'environment_kind': 'local_real',
        'real_entrypoint': 'python -c print-strict',
        'uses_core_api_mock': False,
        'mocked_routes': [],
        'browser_console_errors': [],
        'page_errors': [],
        'request_failures': [],
        'screenshot_refs': [],
        'visual_evidence_refs': {},
    }


def _descriptive_row() -> dict:
    return {
        'unit_id': 'unit-01',
        'test_case_id': 'TC-DESC-ASSIST',
        'acceptance_criterion': 'AC-16',
        'acceptance_obligations': [],
        'layer': 'integration',
        'command': 'python -c print-descriptive',
        'manual_evidence': None,
        'expected': 'descriptive evidence requires human review',
        'status': 'passed',
        'result_index': 1,
        'returncode': 0,
        'artifact_refs': ['green-test.txt', 'verification.json'],
        'golden_path': False,
        'environment_kind': 'local_real',
        'real_entrypoint': 'python -c print-descriptive',
        'uses_core_api_mock': False,
        'mocked_routes': [],
        'browser_console_errors': [],
        'page_errors': [],
        'request_failures': [],
        'screenshot_refs': [],
        'visual_evidence_refs': {},
        'evidence_type': 'descriptive_command',
        'description': 'Human checks mapped evidence strength.',
        'agent_assisted_judgement': {
            'status': 'needs_human_review',
            'summary': 'Evidence shape is present, mapping remains a human call.',
        },
        'risk_annotations': [
            {
                'severity': 'medium',
                'category': 'weak_evidence',
                'note': 'Mapping is descriptive.',
            }
        ],
        'structured_evidence_refs': ['artifacts/unit-01/final-assist.json'],
        'human_review_required': True,
    }


def _agent_assisted_case_row() -> dict:
    return {
        'unit_id': 'unit-01',
        'test_case_id': 'TC-ASSIST-CHECKOUT',
        'acceptance_criterion': 'AC-15',
        'acceptance_obligations': [],
        'layer': 'e2e',
        'command': None,
        'manual_evidence': None,
        'expected': 'Order confirmation C-100 is visible after submit.',
        'status': 'passed',
        'result_index': None,
        'returncode': None,
        'artifact_refs': ['verification.json', 'assist/TC-ASSIST-CHECKOUT.json'],
        'golden_path': False,
        'environment_kind': 'local_real',
        'real_entrypoint': 'http://localhost:3000/checkout',
        'uses_core_api_mock': False,
        'mocked_routes': [],
        'browser_console_errors': [],
        'page_errors': [],
        'request_failures': [],
        'screenshot_refs': [],
        'visual_evidence_refs': {},
        'evidence_type': 'agent_assisted_case',
        'description': 'Open checkout and inspect confirmation page.',
        'agent_assisted_judgement': {
            'status': 'passed',
            'summary': 'Checkout flow was observed.',
        },
        'risk_annotations': [
            {
                'severity': 'low',
                'category': 'runtime_dependency_gap',
                'note': 'Browser runtime remains human-reviewed.',
            }
        ],
        'structured_evidence_refs': ['screenshots/checkout-confirmation.png'],
        'human_review_required': True,
        'assist_artifact_path': 'artifacts/unit-01/assist/TC-ASSIST-CHECKOUT.json',
    }
