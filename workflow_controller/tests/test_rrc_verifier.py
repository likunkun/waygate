from __future__ import annotations

import json
from pathlib import Path

import pytest

from workflow_controller.steps.builder import run_verifier
from workflow_controller.gates.validators import validate_verification_evidence_schema


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def test_run_verifier_generates_passing_verification_when_green_test_exists(tmp_path: Path) -> None:
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    _write(unit_dir / 'green-test.txt', 'PASSED test_example\n')

    state = {
        'currentUnitId': 'unit-01',
        'units': [
            {
                'id': 'unit-01',
                'test_cases': [
                    {
                        'id': 'TC-MANUAL-1',
                        'acceptance_criterion': 'AC-1',
                        'covers_obligations': ['AO-001'],
                        'layer': 'manual',
                        'evidence': 'green-test.txt contains manual acceptance transcript',
                        'expected': 'manual acceptance transcript confirms AC-1',
                    }
                ],
            }
        ],
    }
    result = run_verifier(state, unit_dir, dry_run=False)

    assert result.summary == 'verification passed'
    verification = json.loads((unit_dir / 'verification.json').read_text(encoding='utf-8'))
    assert verification['passed'] is True
    assert verification['evidence_files'] == ['green-test.txt']
    assert verification['evidence_schema_version'] == 'v0.3.5'
    assert verification['evidence_rows'] == [
        {
            'unit_id': 'unit-01',
            'test_case_id': 'TC-MANUAL-1',
            'acceptance_criterion': 'AC-1',
            'acceptance_obligations': ['AO-001'],
            'layer': 'manual',
            'command': None,
            'manual_evidence': 'green-test.txt contains manual acceptance transcript',
            'expected': 'manual acceptance transcript confirms AC-1',
            'status': 'manual',
            'result_index': None,
            'returncode': None,
            'artifact_refs': ['green-test.txt'],
            'golden_path': False,
        }
    ]


def test_run_verifier_generates_failing_verification_when_green_test_missing_or_invalid(tmp_path: Path) -> None:
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    _write(unit_dir / 'green-test.txt', 'still running maybe?\n')

    state = {'currentUnitId': 'unit-01'}
    result = run_verifier(state, unit_dir, dry_run=False)

    assert result.summary == 'verification failed'
    verification = json.loads((unit_dir / 'verification.json').read_text(encoding='utf-8'))
    assert verification['passed'] is False
    issue_types = {issue['type'] for issue in verification['issues']}
    assert 'green_test_not_passing' in issue_types

    missing_dir = tmp_path / 'artifacts' / 'unit-02'
    missing_dir.mkdir(parents=True, exist_ok=True)
    state = {'currentUnitId': 'unit-02'}
    result = run_verifier(state, missing_dir, dry_run=False)

    assert result.summary == 'verification failed'
    verification = json.loads((missing_dir / 'verification.json').read_text(encoding='utf-8'))
    assert verification['passed'] is False
    issue_types = {issue['type'] for issue in verification['issues']}
    assert 'missing_green_test' in issue_types


def test_validate_verification_evidence_schema_rejects_missing_schema_fields(tmp_path: Path) -> None:
    verification_path = tmp_path / 'verification.json'
    verification_path.write_text(
        json.dumps({
            'unit_id': 'unit-01',
            'passed': True,
            'commands': ['pytest -q'],
            'evidence_files': ['green-test.txt'],
            'verified_at': '2026-05-04T00:00:00+00:00',
        }),
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='evidence_schema_version'):
        validate_verification_evidence_schema(verification_path)

    verification_path.write_text(
        json.dumps({
            'unit_id': 'unit-01',
            'passed': True,
            'commands': ['pytest -q'],
            'evidence_files': ['green-test.txt'],
            'evidence_schema_version': 'v0.3.5',
            'evidence_rows': [{'unit_id': 'unit-01'}],
            'verified_at': '2026-05-04T00:00:00+00:00',
        }),
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='test_case_id'):
        validate_verification_evidence_schema(verification_path)
