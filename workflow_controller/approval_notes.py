from __future__ import annotations

import json
from typing import Any


def approval_notes_for_gate(state: dict[str, Any], gate: str) -> dict[str, Any] | None:
    notes = state.get('gateApprovalNotes') if isinstance(state.get('gateApprovalNotes'), dict) else {}
    record = notes.get(gate) if isinstance(notes, dict) else None
    return record if isinstance(record, dict) else None


def render_approval_notes_context(state: dict[str, Any], *gates: str) -> str:
    sections: list[str] = []
    for gate in gates:
        record = approval_notes_for_gate(state, gate)
        if not record:
            continue
        sections.append(_render_gate_notes(gate, record))
    if not sections:
        return ''
    return '\n\n'.join(sections).rstrip() + '\n'


def _render_gate_notes(gate: str, record: dict[str, Any]) -> str:
    lines = [
        '## Approval Notes Non-Contract Context',
        '',
        f'- Gate: `{gate}`',
        f"- Source: `{record.get('source') or 'approval_notes'}`",
        f"- Approved body hash: `{record.get('approved_body_hash') or '-'}`",
        '- Boundary: these notes are non-contract context; the approved gate body wins on conflict.',
        '- Do not create or change Acceptance Obligations, Acceptance Criteria, Journeys, test cases, scope, or contract truth from these notes unless the human has edited the gate body and the deterministic validator passes.',
    ]
    artifact_path = str(record.get('artifact_path') or '').strip()
    if artifact_path:
        lines.append(f'- Artifact: `{artifact_path}`')
    reason = str(record.get('reason') or '').strip()
    if reason:
        lines.extend(['', 'Reason:', '', reason])
    feedback = str(record.get('feedback') or '').strip()
    if feedback:
        lines.extend(['', 'Feedback:', '', feedback])
    annotations = record.get('annotations')
    if isinstance(annotations, list) and annotations:
        lines.extend([
            '',
            'Annotations:',
            '',
            '```json',
            json.dumps(annotations, ensure_ascii=False, indent=2),
            '```',
        ])
    return '\n'.join(lines)
