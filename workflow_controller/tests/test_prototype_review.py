from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from workflow_controller.prototype_review import (
    prepare_prototype_review_bundle,
    start_prototype_review_preview_server,
    validate_prototype_review_manifest,
)


def _write_requirements(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-01 [verification: manual]: 用户可以打开原型并完成核心路径。\n'
        '- AC-02 [verification: manual]: 用户可以检查错误状态。\n',
        encoding='utf-8',
    )


def test_prototype_review_bundle_normalizes_manifest_copies_assets_and_renders_markdown(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    draft_dir = artifacts_dir / 'requirements-draft'
    source_dir = tmp_path / 'source-prototypes'
    source_dir.mkdir()
    html_source = source_dir / 'flow.html'
    image_source = source_dir / 'error.png'
    html_source.write_text('<html><body><button>Next</button></body></html>\n', encoding='utf-8')
    image_source.write_bytes(b'\x89PNG\r\n\x1a\n')
    requirements_path = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    _write_requirements(requirements_path)
    (draft_dir / 'prototype-manifest.json').parent.mkdir(parents=True, exist_ok=True)
    (draft_dir / 'prototype-manifest.json').write_text(
        json.dumps(
            {
                'prototypes': [
                    {
                        'id': 'checkout-flow',
                        'type': 'html',
                        'path': str(html_source),
                        'title': 'Checkout flow',
                        'linked_acceptance_criteria': ['AC-01'],
                        'linked_journeys': ['J-01'],
                        'page_states': ['Cart', 'Checkout', 'Done'],
                        'click_path': ['Open cart', 'Click checkout', 'Submit'],
                        'review_guidance': 'Click the happy path.',
                    },
                    {
                        'id': 'error-state',
                        'type': 'image',
                        'path': str(image_source),
                        'title': 'Error state',
                        'acceptance_criteria': ['AC-02'],
                        'journeys': ['J-02'],
                        'page_states': ['Error'],
                        'click_path': ['Open invalid link'],
                        'preview_hint': 'Static screenshot for AC-02.',
                    },
                ]
            }
        ),
        encoding='utf-8',
    )

    bundle = prepare_prototype_review_bundle(
        artifacts_dir=artifacts_dir,
        requirements_path=requirements_path,
        state={},
    )

    assert bundle is not None
    assert bundle.review_path == draft_dir / 'plannotator-review.md'
    assert bundle.manifest_path == draft_dir / 'prototype-review-manifest.json'
    assert (draft_dir / 'prototypes' / 'checkout-flow' / 'flow.html').read_text(encoding='utf-8') == html_source.read_text(encoding='utf-8')
    assert (draft_dir / 'prototypes' / 'error-state' / 'error.png').read_bytes() == image_source.read_bytes()

    normalized = json.loads(bundle.manifest_path.read_text(encoding='utf-8'))
    assert normalized['version'] == 'v0.6.0a'
    assert normalized['source_manifest'] == str(draft_dir / 'prototype-manifest.json')
    assert normalized['review_bundle_path'] == str(bundle.review_path)
    assert normalized['prototypes'][0]['review_href'] == 'prototypes/checkout-flow/flow.html'
    assert normalized['prototypes'][1]['review_href'] == 'prototypes/error-state/error.png'
    assert normalized['prototypes'][0]['linked_acceptance_criteria'] == ['AC-01']

    review = bundle.review_path.read_text(encoding='utf-8')
    assert '# Prototype Review Bundle for Plannotator' in review
    assert str(requirements_path) in review
    assert '[Checkout flow](prototypes/checkout-flow/flow.html)' in review
    assert '| checkout-flow | Checkout flow | html | AC-01 | J-01 | Cart; Checkout; Done | Open cart -> Click checkout -> Submit |' in review


def test_prototype_manifest_validation_blocks_unknown_ac_missing_interaction_and_sensitive_url(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    draft_dir = artifacts_dir / 'requirements-draft'
    draft_dir.mkdir(parents=True)
    requirements_path = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    _write_requirements(requirements_path)
    manifest_path = draft_dir / 'prototype-manifest.json'
    manifest_path.write_text(
        json.dumps(
            {
                'prototypes': [
                    {
                        'id': 'unsafe-link',
                        'type': 'url',
                        'url': 'https://example.test/prototype?token=secret',
                        'title': 'Unsafe link',
                        'linked_acceptance_criteria': ['AC-99'],
                        'page_states': [],
                        'click_path': [],
                    }
                ]
            }
        ),
        encoding='utf-8',
    )

    with pytest.raises(ValueError) as excinfo:
        validate_prototype_review_manifest(
            manifest_path,
            requirements_path=requirements_path,
            artifacts_dir=artifacts_dir,
            require_clickable=True,
        )

    message = str(excinfo.value)
    assert 'unknown acceptance criteria: AC-99' in message
    assert 'missing page_states' in message
    assert 'missing click_path' in message
    assert 'sensitive URL query parameter: token' in message


def test_prototype_preview_server_only_serves_review_bundle_manifest_prototypes_and_approval_gate(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    draft_dir = artifacts_dir / 'requirements-draft'
    prototype_dir = draft_dir / 'prototypes' / 'checkout-flow'
    prototype_dir.mkdir(parents=True)
    review_path = draft_dir / 'plannotator-review.md'
    manifest_path = draft_dir / 'prototype-review-manifest.json'
    approval_path = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    secret_path = tmp_path / 'secret.txt'
    review_path.write_text('# Review\n', encoding='utf-8')
    manifest_path.write_text('{"version": "v0.6.0a"}\n', encoding='utf-8')
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    approval_path.write_text('# Approval\n', encoding='utf-8')
    (prototype_dir / 'index.html').write_text('<button>OK</button>\n', encoding='utf-8')
    secret_path.write_text('do not serve\n', encoding='utf-8')

    server = start_prototype_review_preview_server(
        review_path=review_path,
        manifest_path=manifest_path,
        prototypes_dir=draft_dir / 'prototypes',
        approval_gate_path=approval_path,
    )
    try:
        assert urllib.request.urlopen(f'{server.base_url}/plannotator-review.md', timeout=2).read().decode() == '# Review\n'
        assert urllib.request.urlopen(f'{server.base_url}/prototype-review-manifest.json', timeout=2).read().decode() == '{"version": "v0.6.0a"}\n'
        assert urllib.request.urlopen(f'{server.base_url}/prototypes/checkout-flow/index.html', timeout=2).read().decode() == '<button>OK</button>\n'
        assert urllib.request.urlopen(f'{server.base_url}/requirements-and-acceptance.md', timeout=2).read().decode() == '# Approval\n'
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(f'{server.base_url}/../secret.txt', timeout=2)
        assert excinfo.value.code == 404
    finally:
        server.close()
