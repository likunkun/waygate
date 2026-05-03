from __future__ import annotations

import json
from pathlib import Path

from workflow_controller.steps.builder import run_reviewer


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def test_run_reviewer_generates_passing_review_when_required_artifacts_are_present(tmp_path: Path) -> None:
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    _write(unit_dir / 'builder-summary.json', json.dumps({'status': 'ok'}))
    _write(unit_dir / 'changed-files.txt', 'src/example.py\n')
    _write(unit_dir / 'red-test.txt', 'FAILED test_example\n')
    _write(unit_dir / 'green-test.txt', 'PASSED test_example\n')
    _write(unit_dir / 'refinement-summary.json', json.dumps({'status': 'ok'}))

    state = {'currentUnitId': 'unit-01'}
    result = run_reviewer(state, unit_dir, dry_run=False)

    assert result.summary == 'review passed'
    review = json.loads((unit_dir / 'review.json').read_text(encoding='utf-8'))
    assert review['passed'] is True
    assert review['issues'] == []


def test_run_reviewer_generates_failing_review_when_green_test_or_changed_files_are_missing(tmp_path: Path) -> None:
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    _write(unit_dir / 'builder-summary.json', json.dumps({'status': 'ok'}))
    _write(unit_dir / 'red-test.txt', 'FAILED test_example\n')

    state = {'currentUnitId': 'unit-01'}
    result = run_reviewer(state, unit_dir, dry_run=False)

    assert result.summary == 'review failed'
    review = json.loads((unit_dir / 'review.json').read_text(encoding='utf-8'))
    assert review['passed'] is False
    issue_types = {issue['type'] for issue in review['issues']}
    assert 'missing_changed_files' in issue_types
    assert 'missing_green_test' in issue_types


def test_real_runtime_reviewer_allows_verification_only_acceptance_without_changed_files(tmp_path: Path) -> None:
    unit_dir = tmp_path / 'artifacts' / 'target-1-1'
    _write(
        unit_dir / 'builder-summary.json',
        json.dumps(
            {
                'mode': 'tmux-claude',
                'runner_status': 'done',
                'exit_code': 0,
                'done_payload': {
                    'status': 'done',
                    'summary': 'No implementation change needed; verification is the evidence.',
                },
            }
        ),
    )
    _write(unit_dir / 'changed-files.txt', '')
    _write(unit_dir / 'refinement-summary.json', json.dumps({'status': 'ok'}))

    state = {
        'currentUnitId': 'target-1-1',
        'workspacePath': str(tmp_path / 'workspace'),
        'requestedOutcome': '1.1',
        'units': [
            {
                'id': 'target-1-1',
                'verification_commands': ['python -c "print(1)"'],
            }
        ],
    }
    result = run_reviewer(state, unit_dir, dry_run=False)

    assert result.summary == 'review passed'
    review = json.loads((unit_dir / 'review.json').read_text(encoding='utf-8'))
    assert review['passed'] is True
    assert review['issues'] == []
