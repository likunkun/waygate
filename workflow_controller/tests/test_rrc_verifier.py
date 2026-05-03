from __future__ import annotations

import json
from pathlib import Path

from workflow_controller.steps.builder import run_verifier


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def test_run_verifier_generates_passing_verification_when_green_test_exists(tmp_path: Path) -> None:
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    _write(unit_dir / 'green-test.txt', 'PASSED test_example\n')

    state = {'currentUnitId': 'unit-01'}
    result = run_verifier(state, unit_dir, dry_run=False)

    assert result.summary == 'verification passed'
    verification = json.loads((unit_dir / 'verification.json').read_text(encoding='utf-8'))
    assert verification['passed'] is True
    assert verification['evidence_files'] == ['green-test.txt']


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
