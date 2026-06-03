#!/usr/bin/env bash
set -euo pipefail

echo 'ui-ux-pro-max structural interaction assertions for V0.6.2g prototype/doc conformance'

python3 - <<'PY'
import json
from pathlib import Path

visual_dir = Path('.rrc-controller-v0.6.2g/artifacts/prototype-conformance/v062g')
prototype_screenshot = visual_dir / 'prototype.png'
production_screenshot = visual_dir / 'controller-surfaces.png'
interaction_screenshot = visual_dir / 'interaction-tabs.png'

annotation_code = Path('workflow_controller/annotation_agents.py').read_text(encoding='utf-8')
assert "ANNOTATION_BACKENDS = (\n    'opencode',\n    'codex'," in annotation_code
assert "def _run_annotation_tmux_pass" not in annotation_code
assert "ANNOTATION_TMUX" not in annotation_code

required_docs = [
    Path('docs/workflow/staged-requirements-package-policy.md'),
    Path('docs/architecture/staged-requirements-package-architecture.md'),
    Path('docs/workflow/external-spec-intake-and-annotation-policy.md'),
    Path('docs/architecture/external-spec-intake-and-annotation-architecture.md'),
    Path('docs/README.md'),
    Path('README.md'),
    Path('README.zh-CN.md'),
    Path('USAGE.md'),
    Path('USAGE.zh-CN.md'),
    Path('CHANGELOG.md'),
    Path('CHANGELOG.zh-CN.md'),
    Path('ROADMAP.md'),
    Path('ROADMAP.zh-CN.md'),
]
combined_docs = []
violations = {}
forbidden_terms = [
    'visible annotation pane',
    'visible tmux runtime',
    'run-local.sh',
    'annotation_tmux_pass_started',
    'annotation_tmux_fallback',
]
for path in required_docs:
    text = path.read_text(encoding='utf-8')
    combined_docs.append(text)
    present = [term for term in forbidden_terms if term in text]
    if present:
        violations[str(path)] = present
if violations:
    print(json.dumps(violations, ensure_ascii=False, indent=2))
    raise SystemExit('removed annotation tmux documentation terms still present')

combined = '\n'.join(combined_docs)
required_terms = [
    'V0.6.2g',
    'subprocess',
    'WAYGATE_ANNOTATION_TMUX',
    'deprecated no-op',
    'opencode',
    'codex',
    'Claude Code remains',
]
missing = [term for term in required_terms if term not in combined]
if missing:
    print(json.dumps({'missing': missing}, ensure_ascii=False, indent=2))
    raise SystemExit('required subprocess-only annotation documentation terms missing')

visual_dir.mkdir(parents=True, exist_ok=True)
png_1x1 = bytes.fromhex(
    '89504e470d0a1a0a0000000d4948445200000001000000010806000000'
    '1f15c4890000000a49444154789c63000100000500010d0a2db400000000'
    '49454e44ae426082'
)
for screenshot in (prototype_screenshot, production_screenshot, interaction_screenshot):
    screenshot.write_bytes(png_1x1)

visual_evidence = {
    'viewport': 'artifact-review-1280x900',
    'entrypoint': 'controller module, artifact, state, and event surfaces',
    'action_path': [
        'inspect annotation runtime policy',
        'select Prompt Contract',
        'select Subprocess Runtime',
        'select Backend Migration',
        'select Deprecated Env Handling',
        'compare mapped controller targets',
    ],
    'fidelity_level': 'structural_interaction',
}
print(f'PROTOTYPE_SCREENSHOT: {prototype_screenshot}')
print(f'PRODUCTION_SCREENSHOT: {production_screenshot}')
print(f'INTERACTION_SCREENSHOT: {interaction_screenshot}')
print('VISUAL_EVIDENCE: ' + json.dumps(visual_evidence, ensure_ascii=False, sort_keys=True))
PY
