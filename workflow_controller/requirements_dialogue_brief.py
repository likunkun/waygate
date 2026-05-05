from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflow_controller.acceptance_obligations import render_acceptance_obligations_markdown


BRIEF_VERSION = 'v0.4.5a'
BRIEF_DIR_NAME = 'requirements-dialogue-brief'
BRIEF_JSON_NAME = 'requirements-dialogue-brief.json'
BRIEF_MARKDOWN_NAME = 'requirements-dialogue-brief.md'
MAX_SOURCE_EXCERPT_CHARS = 4000


def write_requirements_dialogue_brief(state: dict[str, Any], artifacts_dir: Path) -> dict[str, Any]:
    brief_dir = artifacts_dir / BRIEF_DIR_NAME
    brief_dir.mkdir(parents=True, exist_ok=True)
    json_path = brief_dir / BRIEF_JSON_NAME
    markdown_path = brief_dir / BRIEF_MARKDOWN_NAME

    semantic_payload = _semantic_payload(state)
    brief_hash = _stable_hash(semantic_payload)
    payload = {
        'version': BRIEF_VERSION,
        'generated_at': _now_iso(),
        'task_id': state.get('task_id'),
        'current_unit_id': state.get('currentUnitId'),
        'source_refs': semantic_payload['source_refs'],
        'summary_sections': semantic_payload['summary_sections'],
        'artifact_paths': {
            'json': str(json_path),
            'markdown': str(markdown_path),
        },
        'brief_hash': brief_hash,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    markdown_path.write_text(_render_markdown(payload), encoding='utf-8')
    return payload


def render_requirements_dialogue_brief_prompt_section(state: dict[str, Any]) -> str:
    brief_path = str(state.get('requirementsDialogueBriefPath') or '').strip()
    brief_hash = str(state.get('requirementsDialogueBriefHash') or '').strip()
    if brief_path:
        path = Path(brief_path)
        if path.exists():
            brief_markdown = path.read_text(encoding='utf-8')
        else:
            brief_markdown = f'Requirements Dialogue Brief artifact is missing at {brief_path}.'
    else:
        brief_markdown = 'Requirements Dialogue Brief artifact has not been generated for this render.'

    return f"""Requirements Dialogue Brief:

Brief artifact path: `{brief_path or 'not generated'}`
Brief hash: `{brief_hash or 'not generated'}`

This brief compresses original user context and current controller state. It is not a new requirements source.
Use it to preserve the user's requested outcome, feasible outcome, non-goals, constraints, Acceptance Obligation Ledger, and recorded revision feedback.
Do not reinterpret the task background from recent progress records when the brief and controller state already define the scope.

````md
{brief_markdown}
````
"""


def _semantic_payload(state: dict[str, Any]) -> dict[str, Any]:
    current_unit_id = state.get('currentUnitId')
    unit = _find_unit(state, current_unit_id)
    source_refs: list[dict[str, Any]] = [
        _state_ref(state, 'requestedOutcome'),
        _state_ref(state, 'feasibleOutcome'),
        _state_ref(state, 'currentUnitId'),
        _state_ref(state, 'targetContextFiles'),
        _state_ref(state, 'acceptanceObligations'),
        _state_ref(state, 'requirementsRevisionFeedback'),
    ]
    prompt_ref, prompt_excerpt = _optional_file_ref(state.get('promptPath'), fallback_ref='promptPath')
    source_refs.append(prompt_ref)

    context_refs: list[dict[str, Any]] = []
    context_excerpts: list[dict[str, str]] = []
    for raw_path in state.get('targetContextFiles') or []:
        ref, excerpt = _optional_file_ref(raw_path)
        context_refs.append(ref)
        if excerpt:
            context_excerpts.append({'path': str(raw_path), 'excerpt': excerpt})
    source_refs.extend(context_refs)

    summary_sections = [
        _section('outcome', 'Outcome', _outcome_summary(state, unit)),
        _section('current_unit', 'Current Unit', _current_unit_summary(unit)),
        _section('source_prompt', 'Source Prompt Context', prompt_excerpt or 'Prompt path is missing or unavailable.'),
        _section('target_context_files', 'Target Context Files', _context_files_summary(context_refs, context_excerpts)),
        _section('acceptance_obligations', 'Acceptance Obligation Ledger', _acceptance_obligations_summary(state)),
        _section('requirements_revision_feedback', 'Requirements Revision Feedback', _revision_feedback_summary(state)),
    ]
    return {
        'source_refs': source_refs,
        'summary_sections': summary_sections,
    }


def _find_unit(state: dict[str, Any], unit_id: str | None) -> dict[str, Any]:
    for unit in state.get('units') or []:
        if isinstance(unit, dict) and unit.get('id') == unit_id:
            return unit
    return {'id': unit_id or 'unknown-unit'}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        '# Requirements Dialogue Brief',
        '',
        f"- Version: `{payload.get('version')}`",
        f"- Generated at: `{payload.get('generated_at')}`",
        f"- Task ID: `{payload.get('task_id')}`",
        f"- Current Unit ID: `{payload.get('current_unit_id')}`",
        f"- Brief Hash: `{payload.get('brief_hash')}`",
        f"- JSON Artifact: `{payload.get('artifact_paths', {}).get('json')}`",
        f"- Markdown Artifact: `{payload.get('artifact_paths', {}).get('markdown')}`",
        '',
        '## How to Use',
        '',
        '- This brief compresses original user context and current controller state; it is not a new requirements source.',
        '- Preserve the user goal, feasible target, non-goals, constraints, Acceptance Obligation Ledger, and recorded revision feedback.',
        '- Do not use recent progress records to reinterpret the task background when they conflict with this controller-owned context.',
        '',
        '## Source Refs',
        '',
        '| Type | Ref | Status | Notes |',
        '| --- | --- | --- | --- |',
    ]
    for ref in payload.get('source_refs') or []:
        notes = ref.get('sha256') or ref.get('reason') or ref.get('error') or ''
        lines.append(f"| {ref.get('type')} | `{ref.get('ref')}` | {ref.get('status')} | {notes} |")
    for section in payload.get('summary_sections') or []:
        lines.extend([
            '',
            f"## {section.get('title')}",
            '',
            str(section.get('content') or '').rstrip(),
        ])
    return '\n'.join(lines).rstrip() + '\n'


def _state_ref(state: dict[str, Any], key: str) -> dict[str, Any]:
    value = state.get(key)
    if value in (None, '', [], {}):
        return {'type': 'state', 'ref': key, 'status': 'missing'}
    return {'type': 'state', 'ref': key, 'status': 'present'}


def _optional_file_ref(raw_path: Any, *, fallback_ref: str | None = None) -> tuple[dict[str, Any], str]:
    if not raw_path:
        return {'type': 'file', 'ref': fallback_ref or 'unspecified', 'status': 'not_specified'}, ''
    path = Path(str(raw_path))
    ref = str(raw_path)
    if not path.exists():
        return {'type': 'file', 'ref': ref, 'status': 'missing'}, ''
    if not path.is_file():
        return {'type': 'file', 'ref': ref, 'status': 'not_file'}, ''
    try:
        content = path.read_text(encoding='utf-8')
    except OSError as exc:
        return {'type': 'file', 'ref': ref, 'status': 'unreadable', 'error': str(exc)}, ''
    excerpt = _excerpt(content)
    return {
        'type': 'file',
        'ref': ref,
        'status': 'read',
        'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest(),
        'excerpt': excerpt,
    }, excerpt


def _section(section_id: str, title: str, content: str) -> dict[str, str]:
    return {
        'id': section_id,
        'title': title,
        'content': content.rstrip() or 'Not specified.',
    }


def _outcome_summary(state: dict[str, Any], unit: dict[str, Any]) -> str:
    return '\n'.join([
        f"- Requested outcome: {_text(state.get('requestedOutcome'))}",
        f"- Feasible outcome: {_text(state.get('feasibleOutcome'))}",
        f"- Current unit id: {_text(state.get('currentUnitId'))}",
        f"- Current unit name: {_text(unit.get('name') or unit.get('id'))}",
    ])


def _current_unit_summary(unit: dict[str, Any]) -> str:
    return '\n'.join([
        'Scope:',
        _bullet_list(unit.get('scope')),
        '',
        'Non-goals:',
        _bullet_list(unit.get('non_goals')),
        '',
        'Done when:',
        _bullet_list(unit.get('done_when')),
        '',
        'Verification commands:',
        _command_list(unit.get('verification_commands')),
    ])


def _context_files_summary(
    context_refs: list[dict[str, Any]],
    context_excerpts: list[dict[str, str]],
) -> str:
    if not context_refs:
        return 'No target context files were recorded.'
    excerpts_by_path = {item['path']: item['excerpt'] for item in context_excerpts}
    lines: list[str] = []
    for ref in context_refs:
        lines.append(f"- `{ref.get('ref')}`: {ref.get('status')}")
        excerpt = excerpts_by_path.get(str(ref.get('ref')))
        if excerpt:
            lines.extend(['', '```text', excerpt, '```', ''])
    return '\n'.join(lines).rstrip()


def _acceptance_obligations_summary(state: dict[str, Any]) -> str:
    obligations = [item for item in state.get('acceptanceObligations') or [] if isinstance(item, dict)]
    if not obligations:
        return 'No acceptance obligations recorded.'
    lines: list[str] = []
    for obligation in obligations:
        lines.append(
            f"- {obligation.get('id')}: {obligation.get('title')} "
            f"(priority: {obligation.get('priority', 'must')}, status: {obligation.get('status', 'open')})"
        )
        description = str(obligation.get('description') or '').strip()
        if description:
            lines.append(f"  {description}")
    lines.extend(['', 'Full ledger:', '', '```md', render_acceptance_obligations_markdown(state).rstrip(), '```'])
    return '\n'.join(lines)


def _revision_feedback_summary(state: dict[str, Any]) -> str:
    feedback = str(state.get('requirementsRevisionFeedback') or '').strip()
    return feedback or 'No requirements revision feedback recorded.'


def _bullet_list(value: Any) -> str:
    items = [str(item).strip() for item in value or [] if str(item).strip()]
    if not items:
        return '- Not specified.'
    return '\n'.join(f'- {item}' for item in items)


def _command_list(value: Any) -> str:
    items = [str(item).strip() for item in value or [] if str(item).strip()]
    if not items:
        return '- Not specified.'
    return '\n'.join(f'- `{item}`' for item in items)


def _text(value: Any) -> str:
    text = str(value).strip() if value is not None else ''
    return text or 'Not specified.'


def _excerpt(text: str) -> str:
    normalized = text.strip()
    if len(normalized) <= MAX_SOURCE_EXCERPT_CHARS:
        return normalized
    return normalized[:MAX_SOURCE_EXCERPT_CHARS].rstrip() + '\n... truncated ...'


def _stable_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
