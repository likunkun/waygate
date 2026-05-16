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


def test_prototype_review_bundle_normalizes_manifest_copies_assets_and_renders_markdown_and_html(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    draft_dir = artifacts_dir / 'requirements-draft'
    source_dir = tmp_path / 'source-prototypes'
    source_dir.mkdir()
    html_source = source_dir / 'flow.html'
    markdown_source = source_dir / 'source-notes.md'
    image_source = source_dir / 'error.png'
    html_source.write_text('<html><body><button>Next</button></body></html>\n', encoding='utf-8')
    markdown_source.write_text('# Source Notes\n\nReview the copy and state labels.\n', encoding='utf-8')
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
                        'implementation_targets': [
                            {'kind': 'route', 'path': '/checkout'},
                        ],
                        'review_guidance': 'Click the happy path.',
                    },
                    {
                        'id': 'source-notes',
                        'type': 'markdown',
                        'path': str(markdown_source),
                        'title': 'Source notes',
                        'linked_acceptance_criteria': ['AC-01'],
                        'linked_journeys': ['J-01'],
                        'page_states': ['Documentation'],
                        'click_path': ['Open source notes'],
                        'implementation_targets': [
                            {'kind': 'route', 'path': '/checkout'},
                        ],
                        'review_guidance': 'Review source documentation for AC-01.',
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
                        'implementation_targets': [
                            {'kind': 'route', 'path': '/checkout/error'},
                        ],
                        'preview_hint': 'Static screenshot for AC-02.',
                    },
                    {
                        'id': 'hosted-flow',
                        'type': 'url',
                        'url': 'https://example.test/prototypes/checkout',
                        'title': 'Hosted flow',
                        'linked_acceptance_criteria': ['AC-02'],
                        'linked_journeys': ['J-02'],
                        'page_states': ['Hosted checkout'],
                        'click_path': ['Open hosted flow'],
                        'implementation_targets': [
                            {'kind': 'route', 'path': '/checkout/hosted'},
                        ],
                        'preview_hint': 'External hosted prototype.',
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
    assert bundle.html_review_path == draft_dir / 'plannotator-review.html'
    assert bundle.manifest_path == draft_dir / 'prototype-review-manifest.json'
    assert (draft_dir / 'prototypes' / 'checkout-flow' / 'flow.html').read_text(encoding='utf-8') == html_source.read_text(encoding='utf-8')
    assert (draft_dir / 'prototypes' / 'source-notes' / 'source-notes.md').read_text(encoding='utf-8') == markdown_source.read_text(encoding='utf-8')
    assert (draft_dir / 'prototypes' / 'error-state' / 'error.png').read_bytes() == image_source.read_bytes()

    normalized = json.loads(bundle.manifest_path.read_text(encoding='utf-8'))
    assert normalized['version'] == 'v0.6.0b'
    assert normalized['source_manifest'] == str(draft_dir / 'prototype-manifest.json')
    assert normalized['review_bundle_path'] == str(bundle.review_path)
    assert normalized['prototypes'][0]['review_href'] == 'prototypes/checkout-flow/flow.html'
    assert normalized['prototypes'][1]['review_href'] == 'prototypes/source-notes/source-notes.md'
    assert normalized['prototypes'][2]['review_href'] == 'prototypes/error-state/error.png'
    assert normalized['prototypes'][3]['review_href'] == 'https://example.test/prototypes/checkout'
    assert normalized['prototypes'][0]['linked_acceptance_criteria'] == ['AC-01']
    assert normalized['prototypes'][0]['implementation_targets'] == [
        {'kind': 'route', 'path': '/checkout'},
    ]

    review = bundle.review_path.read_text(encoding='utf-8')
    assert '# Prototype Review Bundle for Plannotator' in review
    assert str(requirements_path) in review
    assert '[Checkout flow](prototypes/checkout-flow/flow.html)' in review
    assert '| checkout-flow | Checkout flow | html | AC-01 | J-01 | route:/checkout | Cart; Checkout; Done | Open cart -> Click checkout -> Submit |' in review

    html_review = bundle.html_review_path.read_text(encoding='utf-8')
    assert '<iframe' in html_review
    assert 'srcdoc=' in html_review
    assert '&lt;button&gt;Next&lt;/button&gt;' in html_review
    assert '<h2>Prototype Links</h2>' in html_review
    assert 'Open rendered source' in html_review
    assert 'href="prototypes/checkout-flow/flow.html"' in html_review
    assert 'Open markdown/source doc' in html_review
    assert 'href="prototypes/source-notes/source-notes.md"' in html_review
    assert 'Open image' in html_review
    assert 'href="prototypes/error-state/error.png"' in html_review
    assert 'href="https://example.test/prototypes/checkout"' in html_review
    assert 'src="https://example.test/prototypes/checkout"' in html_review
    assert 'localhost:20000/prototypes/' not in html_review
    assert 'Checkout flow' in html_review
    assert 'route:/checkout' in html_review


def test_prototype_manifest_requires_implementation_targets_and_accepts_aliases(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    draft_dir = artifacts_dir / 'requirements-draft'
    draft_dir.mkdir(parents=True)
    html_source = draft_dir / 'teacher.html'
    html_source.write_text('<button>Open class</button>\n', encoding='utf-8')
    requirements_path = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    _write_requirements(requirements_path)
    manifest_path = draft_dir / 'prototype-manifest.json'
    base_prototype = {
        'id': 'teacher-dashboard',
        'type': 'html',
        'path': str(html_source),
        'title': 'Teacher dashboard',
        'linked_acceptance_criteria': ['AC-01'],
        'linked_journeys': ['J-01'],
        'page_states': ['Dashboard', 'Class detail'],
        'click_path': ['Open dashboard', 'Open class'],
    }
    manifest_path.write_text(json.dumps({'prototypes': [base_prototype]}), encoding='utf-8')

    with pytest.raises(ValueError, match='implementation_targets'):
        validate_prototype_review_manifest(
            manifest_path,
            requirements_path=requirements_path,
            artifacts_dir=artifacts_dir,
            require_implementation_targets=True,
        )

    with_alias = dict(base_prototype)
    with_alias['production_targets'] = [{'kind': 'route', 'path': '/dashboard/teacher'}]
    manifest_path.write_text(json.dumps({'prototypes': [with_alias]}), encoding='utf-8')

    normalized = validate_prototype_review_manifest(
        manifest_path,
        requirements_path=requirements_path,
        artifacts_dir=artifacts_dir,
        require_implementation_targets=True,
    )

    assert normalized['prototypes'][0]['implementation_targets'] == [
        {'kind': 'route', 'path': '/dashboard/teacher'},
    ]

    with_real_alias = dict(base_prototype)
    with_real_alias['real_targets'] = [{'kind': 'page', 'path': 'src/app/dashboard/teacher/page.tsx'}]
    manifest_path.write_text(json.dumps({'prototypes': [with_real_alias]}), encoding='utf-8')

    normalized = validate_prototype_review_manifest(
        manifest_path,
        requirements_path=requirements_path,
        artifacts_dir=artifacts_dir,
        require_implementation_targets=True,
    )

    assert normalized['prototypes'][0]['implementation_targets'] == [
        {'kind': 'page', 'path': 'src/app/dashboard/teacher/page.tsx'},
    ]


def test_prototype_manifest_normalizes_surface_contracts_and_aliases(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    draft_dir = artifacts_dir / 'requirements-draft'
    draft_dir.mkdir(parents=True)
    html_source = draft_dir / 'course-ops.html'
    html_source.write_text('<button>分配管理</button>\n', encoding='utf-8')
    requirements_path = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    _write_requirements(requirements_path)
    manifest_path = draft_dir / 'prototype-manifest.json'
    manifest_path.write_text(
        json.dumps(
            {
                'prototypes': [
                    {
                        'id': 'v291-course-ops-prototype-contract',
                        'type': 'html',
                        'path': str(html_source),
                        'title': 'Course ops prototype',
                        'linked_acceptance_criteria': ['AC-01'],
                        'linked_journeys': ['J-01'],
                        'page_states': ['Teacher dashboard'],
                        'click_path': ['Open dashboard'],
                        'implementation_targets': [{'kind': 'route', 'path': '/dashboard/teacher'}],
                        'ui_surfaces': [
                            {
                                'id': 'assignment-management-dialog',
                                'title': 'Assignment management dialog',
                                'kind': 'dialog',
                                'page_states': ['Teacher dashboard', 'Assign management dialog'],
                                'click_path': ['Open dashboard', 'Click 分配管理'],
                                'entrypoints': ['CourseCard -> 分配管理'],
                                'implementation_targets': [
                                    {'kind': 'component', 'path': 'OpenMAIC/components/course/AssignManageDialog.tsx'}
                                ],
                                'linked_acceptance_criteria': ['AC-01'],
                                'required': True,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding='utf-8',
    )

    normalized = validate_prototype_review_manifest(
        manifest_path,
        requirements_path=requirements_path,
        artifacts_dir=artifacts_dir,
        require_implementation_targets=True,
    )

    assert normalized['prototypes'][0]['surface_contracts'] == [
        {
            'id': 'assignment-management-dialog',
            'title': 'Assignment management dialog',
            'kind': 'dialog',
            'page_states': ['Teacher dashboard', 'Assign management dialog'],
            'click_path': ['Open dashboard', 'Click 分配管理'],
            'entrypoints': ['CourseCard -> 分配管理'],
            'implementation_targets': [
                {'kind': 'component', 'path': 'OpenMAIC/components/course/AssignManageDialog.tsx'}
            ],
            'linked_acceptance_criteria': ['AC-01'],
            'required': True,
        }
    ]


def test_prototype_manifest_blocks_incomplete_surface_contract(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    draft_dir = artifacts_dir / 'requirements-draft'
    draft_dir.mkdir(parents=True)
    html_source = draft_dir / 'course-ops.html'
    html_source.write_text('<button>分配管理</button>\n', encoding='utf-8')
    requirements_path = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    _write_requirements(requirements_path)
    manifest_path = draft_dir / 'prototype-manifest.json'
    manifest_path.write_text(
        json.dumps(
            {
                'prototypes': [
                    {
                        'id': 'v291-course-ops-prototype-contract',
                        'type': 'html',
                        'path': str(html_source),
                        'title': 'Course ops prototype',
                        'linked_acceptance_criteria': ['AC-01'],
                        'linked_journeys': ['J-01'],
                        'page_states': ['Teacher dashboard'],
                        'click_path': ['Open dashboard'],
                        'implementation_targets': [{'kind': 'route', 'path': '/dashboard/teacher'}],
                        'surface_contracts': [
                            {
                                'id': 'assignment-management-dialog',
                                'title': 'Assignment management dialog',
                                'kind': 'dialog',
                                'page_states': ['Teacher dashboard', 'Assign management dialog'],
                                'click_path': ['Open dashboard', 'Click 分配管理'],
                                'linked_acceptance_criteria': ['AC-99'],
                                'required': True,
                            }
                        ],
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
            require_implementation_targets=True,
        )
    message = str(excinfo.value)
    assert 'assignment-management-dialog' in message
    assert 'missing entrypoints' in message
    assert 'missing implementation_targets' in message
    assert 'unknown acceptance criteria: AC-99' in message


def test_html_prototype_with_multi_surface_signals_requires_surface_contracts(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    draft_dir = artifacts_dir / 'requirements-draft'
    draft_dir.mkdir(parents=True)
    html_source = draft_dir / 'course-ops.html'
    html_source.write_text(
        '<button>分配管理</button><dialog>AssignManageDialog</dialog><aside>课程管理面板</aside>\n',
        encoding='utf-8',
    )
    requirements_path = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    _write_requirements(requirements_path)
    manifest_path = draft_dir / 'prototype-manifest.json'
    manifest_path.write_text(
        json.dumps(
            {
                'prototypes': [
                    {
                        'id': 'v291-course-ops-prototype-contract',
                        'type': 'html',
                        'path': str(html_source),
                        'title': 'Course ops prototype with 分配管理 dialog',
                        'linked_acceptance_criteria': ['AC-01'],
                        'linked_journeys': ['J-01'],
                        'page_states': ['Teacher dashboard', '分配管理弹窗'],
                        'click_path': ['Open dashboard', 'Click 分配管理'],
                        'implementation_targets': [{'kind': 'route', 'path': '/dashboard/teacher'}],
                    }
                ]
            }
        ),
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='surface_contracts'):
        validate_prototype_review_manifest(
            manifest_path,
            requirements_path=requirements_path,
            artifacts_dir=artifacts_dir,
            require_implementation_targets=True,
        )


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
    html_review_path = draft_dir / 'plannotator-review.html'
    manifest_path = draft_dir / 'prototype-review-manifest.json'
    approval_path = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    secret_path = tmp_path / 'secret.txt'
    review_path.write_text('# Review\n', encoding='utf-8')
    html_review_path.write_text('<!doctype html><p>Review</p>\n', encoding='utf-8')
    manifest_path.write_text('{"version": "v0.6.0b"}\n', encoding='utf-8')
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
        markdown_response = urllib.request.urlopen(f'{server.base_url}/plannotator-review.md', timeout=2)
        assert markdown_response.read().decode() == '# Review\n'
        assert markdown_response.headers.get_content_type() == 'text/markdown'
        assert markdown_response.headers.get_content_charset() == 'utf-8'
        html_response = urllib.request.urlopen(f'{server.base_url}/plannotator-review.html', timeout=2)
        assert html_response.read().decode() == '<!doctype html><p>Review</p>\n'
        assert html_response.headers.get_content_type() == 'text/html'
        assert html_response.headers.get_content_charset() == 'utf-8'
        assert urllib.request.urlopen(f'{server.base_url}/prototype-review-manifest.json', timeout=2).read().decode() == '{"version": "v0.6.0b"}\n'
        assert urllib.request.urlopen(f'{server.base_url}/prototypes/checkout-flow/index.html', timeout=2).read().decode() == '<button>OK</button>\n'
        assert urllib.request.urlopen(f'{server.base_url}/requirements-and-acceptance.md', timeout=2).read().decode() == '# Approval\n'
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(f'{server.base_url}/../secret.txt', timeout=2)
        assert excinfo.value.code == 404
    finally:
        server.close()
