from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import workflow_controller.rrc_controller  # noqa: F401
from workflow_controller.prompts.requirements import _render_requirements_draft_prompt
from workflow_controller.requirements_dialogue_brief import write_requirements_dialogue_brief
from workflow_controller.spec_sources import (
    classify_requirements_spec_path,
    requirements_spec_metadata,
)


ROOT = Path(__file__).resolve().parents[2]


def _run_rrc(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'workflow_controller.rrc_controller', *args],
        cwd=str(cwd or ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def _write_waygate_spec(path: Path) -> Path:
    path.write_text(
        '# Waygate requirements\n\n'
        '## Requirements\n\n'
        '- AC-01 [verification: functional]: Imported markdown stays compatible.\n',
        encoding='utf-8',
    )
    return path


def _write_openapi_json(path: Path, *, secret_value: str | None = None) -> Path:
    payload = {
        'openapi': '3.1.0',
        'info': {'title': 'Pet API', 'version': '1.0.0'},
        'servers': [{'url': 'https://api.example.test/v1'}],
        'paths': {
            '/pets': {
                'get': {
                    'summary': 'List pets',
                    'description': 'Return all visible pets.',
                    'responses': {'200': {'description': 'Pet list returned'}},
                }
            }
        },
    }
    if secret_value:
        payload['servers'][0]['url'] = f'https://api.example.test/v1?token={secret_value}&mode=test'
        payload['x-api-key'] = secret_value
        payload['paths']['/pets']['get']['description'] = f'Uses postgres://user:{secret_value}@db.example.test/pets'
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def _write_openapi_yaml(path: Path) -> Path:
    path.write_text(
        'openapi: 3.1.0\n'
        'info:\n'
        '  title: Store API\n'
        '  version: 1.0.0\n'
        'servers:\n'
        '  - url: https://store.example.test/v1\n'
        'paths:\n'
        '  /orders:\n'
        '    post:\n'
        '      summary: Create order\n'
        '      description: Create a test order.\n'
        '      responses:\n'
        '        "201":\n'
        '          description: Order created\n',
        encoding='utf-8',
    )
    return path


def _write_spec_kit(path: Path) -> Path:
    path.write_text(
        '# Feature: External Intake\n\n'
        '## Requirements\n\n'
        '- REQ-001: Import external specs into normalized requirements.\n\n'
        '## Acceptance Criteria\n\n'
        '- AC-001: Given a Spec Kit file, conversion creates acceptance candidates.\n\n'
        '## Non-Goals\n\n'
        '- Do not approve requirements automatically.\n\n'
        '## Assumptions\n\n'
        '- Local filesystem input only.\n',
        encoding='utf-8',
    )
    return path


def _artifact_payloads(metadata: dict) -> dict[str, dict]:
    artifacts = metadata['conversionArtifacts']
    return {
        name: json.loads(Path(path).read_text(encoding='utf-8'))
        for name, path in artifacts.items()
    }


def test_v061_spec_classify_records_waygate_and_external_source_types(tmp_path: Path) -> None:
    waygate = _write_waygate_spec(tmp_path / 'waygate.md')
    openapi_file = _write_openapi_json(tmp_path / 'openapi.json')
    openapi_dir = tmp_path / 'open-spec'
    openapi_dir.mkdir()
    _write_openapi_yaml(openapi_dir / 'openapi.yaml')
    spec_kit_file = _write_spec_kit(tmp_path / 'feature.specify.md')
    spec_kit_dir = tmp_path / 'spec-kit'
    spec_kit_dir.mkdir()
    _write_spec_kit(spec_kit_dir / 'spec.md')

    assert classify_requirements_spec_path(waygate)['sourceType'] == 'waygate-markdown'
    assert classify_requirements_spec_path(openapi_file)['sourceType'] == 'openspec'
    assert classify_requirements_spec_path(openapi_dir)['sourceType'] == 'openspec'
    assert classify_requirements_spec_path(spec_kit_file)['sourceType'] == 'spec-kit'
    assert classify_requirements_spec_path(spec_kit_dir)['sourceType'] == 'spec-kit'

    metadata = requirements_spec_metadata(waygate, target='V0.6.1')
    assert metadata['path'] == str(waygate.resolve())
    assert metadata['sourceType'] == 'waygate-markdown'
    assert metadata['hash'].startswith('sha256:')
    assert metadata['importedAt']
    assert 'conversionArtifacts' not in metadata

    external = requirements_spec_metadata(openapi_file, artifacts_dir=tmp_path / 'artifacts', target='V0.6.1')
    assert external['sourceType'] == 'openspec'
    assert external['conversionArtifacts']['normalizedRequirements'].endswith('normalized-requirements.json')

    with pytest.raises(ValueError, match='deferred to V0.6.1'):
        requirements_spec_metadata(openapi_file, artifacts_dir=tmp_path / 'legacy-artifacts', target='V0.5.6')


def test_v061_openspec_import_writes_normalized_conversion_artifacts(tmp_path: Path) -> None:
    json_spec = _write_openapi_json(tmp_path / 'openapi.json')
    yaml_spec = _write_openapi_yaml(tmp_path / 'openapi.yaml')

    json_metadata = requirements_spec_metadata(json_spec, artifacts_dir=tmp_path / 'json-artifacts', target='V0.6.1')
    yaml_metadata = requirements_spec_metadata(yaml_spec, artifacts_dir=tmp_path / 'yaml-artifacts', target='V0.6.1')

    for metadata, expected_title in ((json_metadata, 'Pet API'), (yaml_metadata, 'Store API')):
        payloads = _artifact_payloads(metadata)
        assert payloads['importSummary']['sourceType'] == 'openspec'
        assert payloads['importSummary']['sourceMetadata']['title'] == expected_title
        assert payloads['normalizedRequirements']['sourceType'] == 'openspec'
        assert payloads['normalizedRequirements']['title'] == expected_title
        assert payloads['normalizedRequirements']['requirements']
        assert payloads['sourceMap']['mappings']
        assert payloads['validationReport']['status'] == 'passed'


def test_v061_speckit_import_writes_normalized_acceptance_candidates(tmp_path: Path) -> None:
    spec_file = _write_spec_kit(tmp_path / 'feature.specify.md')
    spec_dir = tmp_path / 'spec-kit'
    spec_dir.mkdir()
    _write_spec_kit(spec_dir / 'spec.md')

    file_metadata = requirements_spec_metadata(spec_file, artifacts_dir=tmp_path / 'file-artifacts', target='V0.6.1')
    dir_metadata = requirements_spec_metadata(spec_dir, artifacts_dir=tmp_path / 'dir-artifacts', target='V0.6.1')

    for metadata in (file_metadata, dir_metadata):
        payloads = _artifact_payloads(metadata)
        normalized = payloads['normalizedRequirements']
        assert payloads['importSummary']['sourceType'] == 'spec-kit'
        assert normalized['sourceType'] == 'spec-kit'
        assert normalized['requirements'][0]['text'] == 'Import external specs into normalized requirements.'
        assert normalized['acceptanceCandidates'][0]['text'].startswith('Given a Spec Kit file')
        assert normalized['nonGoals'] == ['Do not approve requirements automatically.']
        assert normalized['assumptions'] == ['Local filesystem input only.']
        assert payloads['sourceMap']['mappings']
        assert payloads['validationReport']['status'] == 'passed'


def test_v061_cli_spec_flow_injects_conversion_artifact_refs(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    openapi = _write_openapi_json(tmp_path / 'openapi.json')
    state_dir = tmp_path / 'state'

    result = _run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--target',
        'V0.6.1',
        '--runner',
        'subprocess',
        '--spec',
        str(openapi),
    )
    assert result.returncode == 0, result.stderr
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    artifacts = state['requirementsSpec']['conversionArtifacts']
    assert Path(artifacts['importSummary']).exists()
    assert Path(artifacts['normalizedRequirements']).exists()

    brief = write_requirements_dialogue_brief(state, state_dir / 'artifacts')
    prompt = _render_requirements_draft_prompt(
        state,
        state_dir / 'artifacts' / 'requirements-draft' / 'requirements-body.md',
    )
    brief_md = Path(brief['artifact_paths']['markdown']).read_text(encoding='utf-8')
    for content in (brief_md, prompt):
        assert 'openspec' in content
        assert artifacts['normalizedRequirements'] in content
        assert artifacts['sourceMap'] in content
        assert 'conversion artifact' in content.lower()

    start_workspace = tmp_path / 'start-workspace'
    start_workspace.mkdir()
    start_spec_dir = tmp_path / 'start-spec-kit'
    start_spec_dir.mkdir()
    _write_spec_kit(start_spec_dir / 'spec.md')
    start_result = _run_rrc(
        'start',
        '--state-dir',
        str(tmp_path / 'start-state'),
        '--workspace-dir',
        str(start_workspace),
        '--target',
        'V0.6.1',
        '--runner',
        'subprocess',
        '--dry-run',
        '--max-steps',
        '0',
        '--spec',
        str(start_spec_dir),
    )
    assert start_result.returncode == 0, start_result.stderr

    go_workspace = tmp_path / 'go-workspace'
    go_workspace.mkdir()
    go_result = _run_rrc(
        'go',
        'V0.6.1',
        '--workspace-dir',
        str(go_workspace),
        '--runner',
        'subprocess',
        '--dry-run',
        '--max-steps',
        '0',
        '--spec',
        str(openapi),
    )
    assert go_result.returncode == 0, go_result.stderr
    go_state = json.loads((go_workspace / '.rrc-controller-v0.6.1' / 'session.json').read_text(encoding='utf-8'))
    assert go_state['requirementsSpec']['sourceType'] == 'openspec'
    assert Path(go_state['requirementsSpec']['conversionArtifacts']['validationReport']).exists()


def test_v061_spec_errors_are_clear_and_do_not_create_bad_sessions(tmp_path: Path) -> None:
    missing_state = tmp_path / 'missing-state'
    missing = _run_rrc(
        'init',
        '--state-dir',
        str(missing_state),
        '--target',
        'V0.6.1',
        '--runner',
        'subprocess',
        '--spec',
        str(tmp_path / 'missing-openapi.yaml'),
    )
    assert missing.returncode == 1
    assert 'missing' in missing.stderr
    assert 'sourceType' in missing.stderr
    assert not (missing_state / 'session.json').exists()

    unsupported_path = tmp_path / 'notes.txt'
    unsupported_path.write_text('plain text without a supported spec contract\n', encoding='utf-8')
    unsupported_state = tmp_path / 'unsupported-state'
    unsupported = _run_rrc(
        'init',
        '--state-dir',
        str(unsupported_state),
        '--target',
        'V0.6.1',
        '--runner',
        'subprocess',
        '--spec',
        str(unsupported_path),
    )
    assert unsupported.returncode == 1
    assert 'sourceType=unsupported' in unsupported.stderr
    assert 'next action' in unsupported.stderr
    assert not (unsupported_state / 'session.json').exists()

    deferred_path = tmp_path / 'asyncapi.yaml'
    deferred_path.write_text('asyncapi: 3.0.0\ninfo:\n  title: Events\n  version: 1.0.0\n', encoding='utf-8')
    deferred_state = tmp_path / 'deferred-state'
    deferred = _run_rrc(
        'init',
        '--state-dir',
        str(deferred_state),
        '--target',
        'V0.6.1',
        '--runner',
        'subprocess',
        '--spec',
        str(deferred_path),
    )
    assert deferred.returncode == 1
    assert 'sourceType=asyncapi' in deferred.stderr
    assert 'deferred' in deferred.stderr
    assert not (deferred_state / 'session.json').exists()

    invalid_path = tmp_path / 'openapi.yaml'
    invalid_path.write_text('openapi: 3.1.0\ninfo:\n  title: Missing paths\n  version: 1.0.0\n', encoding='utf-8')
    invalid_state = tmp_path / 'invalid-state'
    invalid = _run_rrc(
        'init',
        '--state-dir',
        str(invalid_state),
        '--target',
        'V0.6.1',
        '--runner',
        'subprocess',
        '--spec',
        str(invalid_path),
    )
    assert invalid.returncode == 1
    assert 'sourceType=openspec' in invalid.stderr
    assert 'invalid' in invalid.stderr
    assert 'paths' in invalid.stderr
    assert not (invalid_state / 'session.json').exists()

    unreadable_path = tmp_path / 'broken.specify.md'
    unreadable_path.write_bytes(b'\xff\xfe\x00\x00')
    unreadable_state = tmp_path / 'unreadable-state'
    unreadable = _run_rrc(
        'init',
        '--state-dir',
        str(unreadable_state),
        '--target',
        'V0.6.1',
        '--runner',
        'subprocess',
        '--spec',
        str(unreadable_path),
    )
    assert unreadable.returncode == 1
    assert 'unreadable' in unreadable.stderr
    assert 'sourceType=spec-kit' in unreadable.stderr
    assert not (unreadable_state / 'session.json').exists()


def test_v061_spec_artifact_safety_redacts_sensitive_values(tmp_path: Path) -> None:
    secret = 'supersecret-value'
    spec = _write_openapi_json(tmp_path / 'openapi.json', secret_value=secret)

    metadata = requirements_spec_metadata(spec, artifacts_dir=tmp_path / 'artifacts', target='V0.6.1')

    for path in metadata['conversionArtifacts'].values():
        content = Path(path).read_text(encoding='utf-8')
        assert secret not in content
        assert 'postgres://user:' not in content
    payloads = _artifact_payloads(metadata)
    report = payloads['validationReport']
    assert report['status'] == 'passed'
    assert report['redactions']
    assert payloads['importSummary']['redactionCount'] >= 1
