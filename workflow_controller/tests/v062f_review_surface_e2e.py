from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / '.rrc-controller-v0.6.2f'
REQUIREMENTS_DRAFT = STATE_DIR / 'artifacts' / 'requirements-draft'
TARGET_ARTIFACTS = STATE_DIR / 'artifacts' / 'target-v0-6-2f'
VISUAL_DIR = TARGET_ARTIFACTS / 'visual'

REVIEW_BUNDLE = REQUIREMENTS_DRAFT / 'plannotator-review.html'
PROTOTYPE_HTML = REQUIREMENTS_DRAFT / 'prototypes' / 'waygate-review-control' / 'index.html'
MANIFEST = REQUIREMENTS_DRAFT / 'prototype-manifest.json'
REVIEW_MANIFEST = REQUIREMENTS_DRAFT / 'prototype-review-manifest.json'

REQUIRED_SURFACES = {
    'approval-notes-context-panel',
    'human-gate-menu-actions',
    'draft-merge-pending-state',
    'manual-adoption-guard',
    'human-interrupt-recovery-panel',
    'revise-route-output',
    'legacy-and-docs-review',
    'review-bundle-prototype-conformance',
}

REQUIRED_TARGET_MARKERS = {
    'review-bundle:artifacts/requirements-draft/plannotator-review.html',
    'prototype:prototypes/waygate-review-control/index.html',
    'manifest:artifacts/requirements-draft/prototype-manifest.json',
    'terminal-menu:Requirements and Unit Plan human gate menu',
    'cli:waygate approve|revise',
    'state:blockedContext.category=human_interrupt',
    'prompt:non-contract context injection',
}


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise AssertionError(f'missing required artifact: {path}')
    return json.loads(path.read_text(encoding='utf-8'))


def _target_markers(value: object) -> set[str]:
    markers: set[str] = set()
    if isinstance(value, dict):
        kind = str(value.get('kind') or '').strip()
        path = str(value.get('path') or value.get('name') or value.get('target') or '').strip()
        if kind and path:
            markers.add(f'{kind}:{path}')
        for child in value.values():
            markers.update(_target_markers(child))
    elif isinstance(value, list):
        for item in value:
            markers.update(_target_markers(item))
    elif isinstance(value, str) and ':' in value:
        markers.add(value)
    return markers


def _validate_manifest() -> None:
    manifest = _load_json(MANIFEST)
    review_manifest = _load_json(REVIEW_MANIFEST)
    prototypes = manifest.get('prototypes')
    if not isinstance(prototypes, list) or not prototypes:
        raise AssertionError('prototype-manifest.json must contain prototypes[]')
    prototype = prototypes[0]
    surfaces = prototype.get('surface_contracts')
    if not isinstance(surfaces, list):
        raise AssertionError('prototype must contain surface_contracts[]')
    actual_surfaces = {str(surface.get('id') or '') for surface in surfaces if isinstance(surface, dict)}
    missing = REQUIRED_SURFACES - actual_surfaces
    if missing:
        raise AssertionError(f'missing required surfaces: {sorted(missing)}')
    required_count = sum(1 for surface in surfaces if isinstance(surface, dict) and surface.get('required') is True)
    if required_count != 8:
        raise AssertionError(f'expected 8 required surface contracts, got {required_count}')
    target_markers = _target_markers(manifest) | _target_markers(review_manifest)
    missing_targets = REQUIRED_TARGET_MARKERS - target_markers
    if missing_targets:
        raise AssertionError(f'missing implementation target markers: {sorted(missing_targets)}')


def _assert_file_screenshot(path: Path) -> None:
    if not path.exists() or path.stat().st_size < 1000:
        raise AssertionError(f'screenshot missing or too small: {path}')


def main() -> None:
    for path in [REVIEW_BUNDLE, PROTOTYPE_HTML, MANIFEST, REVIEW_MANIFEST]:
        if not path.exists():
            raise AssertionError(f'missing required review artifact: {path}')
    _validate_manifest()
    VISUAL_DIR.mkdir(parents=True, exist_ok=True)
    prototype_screenshot = VISUAL_DIR / 'prototype-waygate-review-control-1280x900.png'
    production_screenshot = VISUAL_DIR / 'review-bundle-waygate-control-1280x900.png'
    interaction_screenshot = VISUAL_DIR / 'review-bundle-surface-conformance-click-1280x900.png'

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 900})

        page.goto(PROTOTYPE_HTML.as_uri())
        page.wait_for_load_state('networkidle')
        for text in ['Approval notes', 'AO-001', 'Ctrl+C', 'Revise routes', 'Surface conformance']:
            expect(page.get_by_text(text).first).to_be_visible()
        page.screenshot(path=prototype_screenshot, full_page=True)

        for nav, expected in [
            ('draft', 'Leave approval pending'),
            ('adopt', 'validator pass'),
            ('interrupt', 'blockedContext.category'),
            ('revise', 'rejected without'),
            ('conformance', 'AC-V062F-009'),
        ]:
            page.locator(f'[data-nav="{nav}"]').click()
            expect(page.get_by_text(expected).first).to_be_visible()
        page.screenshot(path=interaction_screenshot, full_page=True)

        page.goto(REVIEW_BUNDLE.as_uri())
        page.wait_for_load_state('networkidle')
        for text in ['Waygate V0.6.2f', 'review-bundle-prototype-conformance', 'AC-V062F-009', 'J-V062F-007']:
            expect(page.get_by_text(text).first).to_be_visible()
        page.screenshot(path=production_screenshot, full_page=True)
        browser.close()

    for path in [prototype_screenshot, production_screenshot, interaction_screenshot]:
        _assert_file_screenshot(path)

    evidence = {
        'viewport': '1280x900',
        'entrypoint': REVIEW_BUNDLE.as_uri(),
        'prototype_entrypoint': PROTOTYPE_HTML.as_uri(),
        'manifest': str(MANIFEST),
        'review_manifest': str(REVIEW_MANIFEST),
        'action_path': [
            'open review bundle file fallback',
            'open prototype artifact',
            'click draft/adopt/interrupt/revise/conformance navigation',
            'assert surface contract and target mapping text',
        ],
        'fidelity_level': 'structural_interaction',
        'required_surface_count': 8,
    }
    print(f'PROTOTYPE_SCREENSHOT: {prototype_screenshot}')
    print(f'PRODUCTION_SCREENSHOT: {production_screenshot}')
    print(f'INTERACTION_SCREENSHOT: {interaction_screenshot}')
    print('VISUAL_EVIDENCE: ' + json.dumps(evidence, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
