from __future__ import annotations

import json
from pathlib import Path

from workflow_controller.requirements_dialogue_brief import write_requirements_dialogue_brief
from workflow_controller.runners import RunnerConfig, RunnerResult
from workflow_controller.steps import requirements as requirements_step
from workflow_controller.steps.requirements import run_requirements_drafter


def _sample_state(tmp_path: Path) -> dict:
    workspace = tmp_path / 'workspace'
    prompt_path = workspace / '.plan-ralph' / 'current-prompt.md'
    context_path = workspace / 'docs' / 'import-retry.md'
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(
        'Original user request: add import retry recovery without changing the gate schema.\n',
        encoding='utf-8',
    )
    context_path.write_text(
        'Context: retry recovery must keep exports out of scope and preserve existing CLI output.\n',
        encoding='utf-8',
    )
    return {
        'task_id': 'import-retry',
        'requestedOutcome': 'Ship import retry recovery',
        'feasibleOutcome': 'Ship import retry recovery without schema changes',
        'currentUnitId': 'unit-import-retry',
        'workspacePath': str(workspace),
        'promptPath': str(prompt_path),
        'targetContextFiles': [
            str(context_path),
            str(workspace / 'docs' / 'missing-context.md'),
        ],
        'requirementsRevisionFeedback': 'Reviewer feedback: please add the retry failure path.',
        'acceptanceObligations': [
            {
                'id': 'AO-001',
                'title': 'Retry failure path is visible',
                'description': 'The revised requirements must cover retry failure state.',
                'source': 'requirements_feedback',
                'sourceRef': 'requirements:revision-1',
                'priority': 'must',
                'status': 'open',
                'ownerStage': 'requirements',
                'mappedAcceptanceCriteria': [],
                'mappedUnits': [],
                'mappedTestCases': [],
                'evidence': [],
            }
        ],
        'units': [
            {
                'id': 'unit-import-retry',
                'name': 'Import retry recovery',
                'scope': ['Generate retry requirements and acceptance coverage.'],
                'non_goals': ['Do not add export changes.'],
                'done_when': ['Requirements mention retry failure and recovery evidence.'],
                'verification_commands': ['python -m pytest workflow_controller/tests -q'],
            }
        ],
    }


def test_requirements_dialogue_brief_writes_json_and_markdown_from_state(tmp_path: Path) -> None:
    state = _sample_state(tmp_path)
    artifacts_dir = tmp_path / '.plan-ralph' / 'artifacts'

    brief = write_requirements_dialogue_brief(state, artifacts_dir)

    json_path = artifacts_dir / 'requirements-dialogue-brief' / 'requirements-dialogue-brief.json'
    markdown_path = artifacts_dir / 'requirements-dialogue-brief' / 'requirements-dialogue-brief.md'
    assert brief['artifact_paths']['json'] == str(json_path)
    assert brief['artifact_paths']['markdown'] == str(markdown_path)
    assert json_path.exists()
    assert markdown_path.exists()

    payload = json.loads(json_path.read_text(encoding='utf-8'))
    assert payload['version'] == 'v0.4.5a'
    assert payload['task_id'] == 'import-retry'
    assert payload['current_unit_id'] == 'unit-import-retry'
    assert len(payload['brief_hash']) == 64
    assert payload['brief_hash'] == brief['brief_hash']

    source_statuses = {(ref['type'], ref['ref']): ref['status'] for ref in payload['source_refs']}
    assert source_statuses[('state', 'requestedOutcome')] == 'present'
    assert source_statuses[('state', 'feasibleOutcome')] == 'present'
    assert source_statuses[('file', state['promptPath'])] == 'read'
    assert source_statuses[('file', state['targetContextFiles'][0])] == 'read'
    assert source_statuses[('file', state['targetContextFiles'][1])] == 'missing'

    markdown = markdown_path.read_text(encoding='utf-8')
    assert '# Requirements Dialogue Brief' in markdown
    assert 'not a new requirements source' in markdown
    assert 'Ship import retry recovery without schema changes' in markdown
    assert 'Original user request: add import retry recovery' in markdown
    assert 'retry recovery must keep exports out of scope' in markdown
    assert 'Do not add export changes.' in markdown
    assert 'AO-001: Retry failure path is visible' in markdown
    assert 'Reviewer feedback: please add the retry failure path.' in markdown


def test_requirements_dialogue_brief_hash_is_stable_until_semantic_content_changes(tmp_path: Path) -> None:
    state = _sample_state(tmp_path)
    artifacts_dir = tmp_path / '.plan-ralph' / 'artifacts'

    first = write_requirements_dialogue_brief(state, artifacts_dir)
    second = write_requirements_dialogue_brief(state, artifacts_dir)
    assert second['brief_hash'] == first['brief_hash']

    state['requestedOutcome'] = 'Ship import retry recovery with explicit timeout messaging'
    third = write_requirements_dialogue_brief(state, artifacts_dir)
    assert third['brief_hash'] != first['brief_hash']


def test_requirements_dialogue_brief_records_missing_prompt_and_context_without_failing(tmp_path: Path) -> None:
    state = {
        'task_id': 'missing-context',
        'requestedOutcome': 'Handle missing context',
        'feasibleOutcome': 'Handle missing context',
        'currentUnitId': 'unit-missing',
        'targetContextFiles': [str(tmp_path / 'does-not-exist.md')],
        'units': [{'id': 'unit-missing'}],
    }

    brief = write_requirements_dialogue_brief(state, tmp_path / 'artifacts')

    source_statuses = {(ref['type'], ref['ref']): ref['status'] for ref in brief['source_refs']}
    assert source_statuses[('file', 'promptPath')] == 'not_specified'
    assert source_statuses[('file', str(tmp_path / 'does-not-exist.md'))] == 'missing'
    assert len(brief['brief_hash']) == 64


def test_requirements_drafter_generates_brief_for_local_template_summary_and_state(tmp_path: Path) -> None:
    state = _sample_state(tmp_path)
    approvals_dir = tmp_path / '.plan-ralph' / 'approvals'
    artifacts_dir = tmp_path / '.plan-ralph' / 'artifacts'

    run_requirements_drafter(state, approvals_dir, artifacts_dir)

    brief_path = artifacts_dir / 'requirements-dialogue-brief' / 'requirements-dialogue-brief.md'
    summary_path = artifacts_dir / 'requirements-draft' / 'requirements-draft-summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    assert state['requirementsDialogueBriefPath'] == str(brief_path)
    assert state['requirementsDialogueBriefHash'] == summary['requirements_dialogue_brief_hash']
    assert summary['requirements_dialogue_brief_path'] == str(brief_path)
    assert len(summary['requirements_dialogue_brief_hash']) == 64
    assert brief_path.exists()


def test_requirements_drafter_includes_brief_in_tmux_prompt_and_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state = _sample_state(tmp_path)
    state['agentRunner'] = 'tmux-claude'
    approvals_dir = tmp_path / '.plan-ralph' / 'approvals'
    artifacts_dir = tmp_path / '.plan-ralph' / 'artifacts'
    captured_requests = []

    def fake_make_runner(state: dict) -> RunnerConfig:
        return RunnerConfig(backend='tmux-claude', agent_command='fake-claude', tmux_target='1.2')

    def fake_run_agent_backend(request):
        captured_requests.append(request)
        body_path = artifacts_dir / 'requirements-draft' / 'requirements-body.md'
        body_path.write_text('# Requirements\n\n- generated\n', encoding='utf-8')
        return RunnerResult(
            backend='tmux-claude',
            status='done',
            command=['fake-claude'],
            returncode=0,
            stdout='ok',
            stderr='',
            run_dir=artifacts_dir / 'requirements-draft' / 'run-1',
            prompt_path=request.prompt_path,
            done_payload={'status': 'done'},
            runner_metadata={'fake': True},
        )

    monkeypatch.setattr(requirements_step, 'make_runner', fake_make_runner)
    monkeypatch.setattr(requirements_step, 'run_agent_backend', fake_run_agent_backend)

    run_requirements_drafter(state, approvals_dir, artifacts_dir)

    assert len(captured_requests) == 1
    prompt_path = artifacts_dir / 'requirements-draft' / 'requirements-draft-prompt.md'
    prompt = prompt_path.read_text(encoding='utf-8')
    assert 'Requirements Dialogue Brief' in prompt
    assert str(artifacts_dir / 'requirements-dialogue-brief' / 'requirements-dialogue-brief.md') in prompt
    assert state['requirementsDialogueBriefHash'] in prompt
    assert 'This brief compresses original user context and current controller state' in prompt
    assert 'not a new requirements source' in prompt
    assert 'Original user request: add import retry recovery' in prompt
    assert 'Reviewer feedback: please add the retry failure path.' in prompt
    assert 'AO-001: Retry failure path is visible' in prompt

    summary = json.loads(
        (artifacts_dir / 'requirements-draft' / 'requirements-draft-summary.json').read_text(encoding='utf-8')
    )
    assert summary['requirements_dialogue_brief_path'] == state['requirementsDialogueBriefPath']
    assert summary['requirements_dialogue_brief_hash'] == state['requirementsDialogueBriefHash']
