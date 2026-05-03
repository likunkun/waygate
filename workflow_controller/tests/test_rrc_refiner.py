from __future__ import annotations

import json
from pathlib import Path

from workflow_controller.runners import RunnerResult
from workflow_controller.gates.validators import validate_simplifier_result
from workflow_controller.steps.builder import run_refiner
from workflow_controller.prompts.builder import _render_previous_controller_failure_feedback


def test_run_refiner_disabled_writes_skipped_simplifier_artifacts(tmp_path: Path) -> None:
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / 'changed-files.txt').write_text('src/login.py\ntests/test_login.py\n', encoding='utf-8')

    state = {'currentUnitId': 'unit-01', 'codeSimplifierEnabled': False}
    result = run_refiner(state, unit_dir, dry_run=False)

    assert result.summary == 'refinement skipped'
    payload = json.loads((unit_dir / 'simplifier-result.json').read_text(encoding='utf-8'))
    assert payload['unit_id'] == 'unit-01'
    assert payload['status'] == 'skipped'
    assert payload['mode'] == 'disabled'
    assert payload['changed_files'] == ['src/login.py', 'tests/test_login.py']
    assert payload['findings'] == []

    summary = json.loads((unit_dir / 'refinement-summary.json').read_text(encoding='utf-8'))
    assert summary['status'] == 'skipped'
    assert summary['mode'] == 'disabled'


def test_run_refiner_enabled_invokes_refiner_runner_and_uses_agent_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / 'changed-files.txt').write_text('src/login.py\ntests/test_login.py\n', encoding='utf-8')
    (unit_dir / 'builder-summary.json').write_text(
        json.dumps({'status': 'ok', 'changed_files': ['src/login.py']}),
        encoding='utf-8',
    )
    seen_requests = []

    def fake_run_agent_backend(request):
        seen_requests.append(request)
        (request.artifact_dir / 'simplifier-result.json').write_text(
            json.dumps({
                'unit_id': 'unit-01',
                'status': 'ok',
                'changed_files': ['src/login.py'],
                'findings': [{'type': 'simplified_branch', 'message': 'Reduced nesting'}],
            }),
            encoding='utf-8',
        )
        return RunnerResult(
            backend='subprocess',
            status='done',
            command=['codex', 'exec', '-'],
            returncode=0,
            stdout='refined',
            stderr='',
            run_dir=request.artifact_dir,
            prompt_path=request.prompt_path,
            runner_metadata={'role': 'refiner', 'backend': 'subprocess', 'env_keys': ['SECRET_TOKEN']},
        )

    monkeypatch.setattr('workflow_controller.steps.builder.run_agent_backend', fake_run_agent_backend)

    result = run_refiner(
        {
            'currentUnitId': 'unit-01',
            'workspacePath': str(workspace),
            'roleRunners': {
                'refiner': {
                    'command': 'codex exec -',
                    'env': {'SECRET_TOKEN': 'top-secret'},
                },
            },
        },
        unit_dir,
        dry_run=False,
    )

    assert result.summary == 'refinement complete'
    assert len(seen_requests) == 1
    assert seen_requests[0].role == 'refiner'
    assert seen_requests[0].agent_command == 'codex exec -'
    assert seen_requests[0].env == {'SECRET_TOKEN': 'top-secret'}

    prompt = (unit_dir / 'code-simplifier-prompt.md').read_text(encoding='utf-8')
    assert 'src/login.py' in prompt
    assert 'tests/test_login.py' in prompt
    assert 'Preserve behavior' in prompt
    assert 'Do not expand scope' in prompt

    payload_text = (unit_dir / 'simplifier-result.json').read_text(encoding='utf-8')
    assert 'top-secret' not in payload_text
    payload = json.loads(payload_text)
    assert payload['status'] == 'ok'
    assert payload['mode'] == 'role-runner'
    assert payload['runner_metadata']['env_keys'] == ['SECRET_TOKEN']
    assert payload['stdout'] == 'refined'
    assert payload['exit_code'] == 0


def test_run_refiner_default_enabled_without_workspace_writes_skipped_artifacts(tmp_path: Path) -> None:
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / 'changed-files.txt').write_text('src/login.py\n', encoding='utf-8')

    result = run_refiner({'currentUnitId': 'unit-01'}, unit_dir, dry_run=False)

    assert result.summary == 'refinement skipped'
    payload = json.loads((unit_dir / 'simplifier-result.json').read_text(encoding='utf-8'))
    assert payload['status'] == 'skipped'
    assert payload['mode'] == 'no-workspace'
    assert payload['findings'][0]['type'] == 'refiner_workspace_missing'


def test_run_refiner_missing_or_invalid_agent_output_is_failed(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / 'changed-files.txt').write_text('src/login.py\n', encoding='utf-8')

    def fake_run_agent_backend(request):
        return RunnerResult(
            backend='subprocess',
            status='done',
            command=['codex', 'exec', '-'],
            returncode=0,
            stdout='no artifact',
            stderr='',
            run_dir=request.artifact_dir,
            prompt_path=request.prompt_path,
            runner_metadata={'role': 'refiner', 'backend': 'subprocess', 'env_keys': []},
        )

    monkeypatch.setattr('workflow_controller.steps.builder.run_agent_backend', fake_run_agent_backend)

    result = run_refiner(
        {
            'currentUnitId': 'unit-01',
            'codeSimplifierEnabled': True,
            'workspacePath': str(workspace),
            'roleRunners': {'refiner': {'command': 'codex exec -'}},
        },
        unit_dir,
        dry_run=False,
    )

    assert result.summary == 'refinement failed'
    payload = json.loads((unit_dir / 'simplifier-result.json').read_text(encoding='utf-8'))
    assert payload['status'] == 'failed'
    assert payload['mode'] == 'role-runner'
    assert payload['findings'][0]['type'] == 'missing_simplifier_result'


def test_run_refiner_redacts_env_values_from_runner_output(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / 'changed-files.txt').write_text('src/login.py\n', encoding='utf-8')

    def fake_run_agent_backend(request):
        (request.artifact_dir / 'simplifier-result.json').write_text(
            json.dumps({'unit_id': 'unit-01', 'status': 'ok', 'findings': []}),
            encoding='utf-8',
        )
        return RunnerResult(
            backend='subprocess',
            status='done',
            command=['codex', 'exec', '-'],
            returncode=0,
            stdout='token=top-secret',
            stderr='',
            run_dir=request.artifact_dir,
            prompt_path=request.prompt_path,
            runner_metadata={'role': 'refiner', 'backend': 'subprocess', 'env_keys': ['SECRET_TOKEN']},
        )

    monkeypatch.setattr('workflow_controller.steps.builder.run_agent_backend', fake_run_agent_backend)

    run_refiner(
        {
            'currentUnitId': 'unit-01',
            'codeSimplifierEnabled': True,
            'workspacePath': str(workspace),
            'roleRunners': {
                'refiner': {
                    'command': 'codex exec -',
                    'env': {'SECRET_TOKEN': 'top-secret'},
                },
            },
        },
        unit_dir,
        dry_run=False,
    )

    payload_text = (unit_dir / 'simplifier-result.json').read_text(encoding='utf-8')
    assert 'top-secret' not in payload_text
    assert '[redacted]' in payload_text


def test_validate_simplifier_result_rejects_invalid_status(tmp_path: Path) -> None:
    path = tmp_path / 'simplifier-result.json'
    path.write_text(
        json.dumps({
            'unit_id': 'unit-01',
            'status': 'needs_work',
            'mode': 'role-runner',
            'changed_files': [],
            'findings': [],
            'runner_metadata': {},
            'exit_code': 0,
            'stdout': '',
            'stderr': '',
            'generated_at': '2026-05-03T00:00:00+00:00',
        }),
        encoding='utf-8',
    )

    try:
        validate_simplifier_result(path)
    except ValueError as exc:
        assert 'invalid status' in str(exc)
    else:
        raise AssertionError('invalid simplifier status should fail validation')


def test_previous_failure_feedback_includes_simplifier_findings(tmp_path: Path) -> None:
    unit_dir = tmp_path / 'artifacts' / 'unit-01'
    unit_dir.mkdir(parents=True)
    (unit_dir / 'simplifier-result.json').write_text(
        json.dumps({
            'unit_id': 'unit-01',
            'status': 'changes_requested',
            'mode': 'role-runner',
            'changed_files': ['src/login.py'],
            'findings': [
                {
                    'severity': 'medium',
                    'type': 'over_nested_branch',
                    'message': 'Flatten the new login branch before review.',
                },
            ],
            'runner_metadata': {},
            'exit_code': 0,
            'stdout': '',
            'stderr': '',
            'generated_at': '2026-05-03T00:00:00+00:00',
        }),
        encoding='utf-8',
    )

    feedback = _render_previous_controller_failure_feedback(unit_dir)

    assert 'Previous CodeSimplifier feedback' in feedback
    assert 'changes_requested' in feedback
    assert 'over_nested_branch' in feedback
    assert 'Flatten the new login branch before review.' in feedback
