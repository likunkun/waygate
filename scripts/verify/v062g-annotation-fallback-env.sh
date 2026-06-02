#!/usr/bin/env bash
set -euo pipefail

python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q \
  -k 'annotation_tmux_deprecated_env_zero_is_ignored_by_subprocess_runtime or annotation_tmux_env_is_ignored_and_uses_subprocess_without_tmux_commands or proxy_env_values_are_redacted or inherits_default_proxy_env or does_not_create_proxy_env or config_safety_rejects_invalid_backend_unavailable_timeout_and_redacts_env_values'

python3 - <<'PY'
import json
from pathlib import Path

state_dir = Path('.rrc-controller-v0.6.2g')
canaries = [
    'secret-value-that-must-not-leak',
    'do-not-leak-this-value',
    'proxy-pass@',
    'postgres://user:password@',
    'api_key=',
    'signature=',
]
paths = []
for relative in ['session.json', 'events.jsonl']:
    path = state_dir / relative
    if path.exists():
        paths.append(path)
artifact_root = state_dir / 'artifacts'
if artifact_root.exists():
    paths.extend(path for path in artifact_root.rglob('*') if path.is_file())

violations = []
for path in paths:
    text = path.read_text(encoding='utf-8', errors='replace')
    for canary in canaries:
        if canary in text:
            violations.append({'path': str(path), 'canary': canary})

if violations:
    print(json.dumps(violations, ensure_ascii=False, indent=2))
    raise SystemExit('env secrecy scan failed')
PY
