from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from workflow_controller.gates.parsers import _unit_test_cases


HANDOFF_EVIDENCE_FILENAME = 'handoff-evidence.json'


def unit_depends_on(unit: dict[str, Any]) -> list[str]:
    return _string_list(unit.get('depends_on') or unit.get('dependsOn'))


def unit_handoff(unit: dict[str, Any]) -> dict[str, Any]:
    raw = unit.get('handoff') or unit.get('unit_handoff') or unit.get('unitHandoff')
    return raw if isinstance(raw, dict) else {}


def handoff_human_summary(unit: dict[str, Any]) -> str:
    return str(
        unit_handoff(unit).get('human_summary')
        or unit_handoff(unit).get('humanSummary')
        or ''
    ).strip()


def handoff_produces(unit: dict[str, Any]) -> list[str]:
    handoff = unit_handoff(unit)
    return _string_list(handoff.get('produces') or handoff.get('produced_outputs') or handoff.get('producedOutputs'))


def handoff_requires(unit: dict[str, Any]) -> list[str]:
    handoff = unit_handoff(unit)
    return _string_list(handoff.get('requires') or handoff.get('consumes') or handoff.get('consumed_inputs') or handoff.get('consumedInputs'))


def handoff_ready_checks(unit: dict[str, Any]) -> list[str]:
    handoff = unit_handoff(unit)
    return _string_list(handoff.get('ready_checks') or handoff.get('readyChecks'))


def handoff_evidence_artifacts(unit: dict[str, Any]) -> list[str]:
    handoff = unit_handoff(unit)
    return _string_list(handoff.get('evidence_artifacts') or handoff.get('evidenceArtifacts'))


def handoff_evidence_path(artifacts_dir: Path, unit_id: str) -> Path:
    return artifacts_dir / unit_id / HANDOFF_EVIDENCE_FILENAME


def normalized_handoff_token(value: str) -> str:
    text = str(value or '').strip().lower()
    text = re.sub(r'[`*_#\[\]()]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def handoff_text_matches(left: str, right: str) -> bool:
    left_token = normalized_handoff_token(left)
    right_token = normalized_handoff_token(right)
    if not left_token or not right_token:
        return False
    return left_token == right_token or left_token in right_token or right_token in left_token


def handoff_summary_is_vague(summary: str) -> bool:
    normalized = normalized_handoff_token(summary)
    if not normalized or len(normalized) < 18:
        return True
    vague_phrases = {
        'environment ready',
        'env ready',
        'ready',
        'done',
        'complete',
        'completed',
        'tbd',
        'todo',
        'same as above',
        'n/a',
        'na',
        '准备完成',
        '环境就绪',
        '前置环境就绪',
        '已完成',
        '完成',
        '就绪',
    }
    if normalized in vague_phrases:
        return True
    vague_only = re.sub(
        r'\b(unit|step|task|upstream|downstream|previous|next|environment|env|ready|done|complete|completed|handoff|consume|consumes)\b',
        ' ',
        normalized,
    )
    vague_only = re.sub(r'\s+', '', vague_only)
    return len(vague_only) < 8


def ready_check_is_mapped(unit: dict[str, Any], ready_check: str) -> bool:
    check = normalized_handoff_token(ready_check)
    if not check:
        return False
    candidates: list[str] = []
    for command in unit.get('verification_commands') or []:
        candidates.append(str(command))
    for case in _unit_test_cases(unit):
        if not isinstance(case, dict):
            continue
        for key in ('id', 'name', 'command', 'expected', 'acceptance_criterion', 'acceptanceCriterion'):
            value = case.get(key)
            if value is not None:
                candidates.append(str(value))
    return any(handoff_text_matches(check, candidate) for candidate in candidates)


def ready_check_passed(
    unit: dict[str, Any],
    ready_check: str,
    results: list[dict[str, Any]],
) -> bool:
    if not ready_check_is_mapped(unit, ready_check):
        return False
    check = normalized_handoff_token(ready_check)
    for case in _unit_test_cases(unit):
        if not isinstance(case, dict):
            continue
        case_id = str(case.get('id') or case.get('name') or '')
        command = str(case.get('command') or '').strip()
        if not handoff_text_matches(check, case_id) and not handoff_text_matches(check, command):
            continue
        if not command:
            return True
        for result in results:
            if not isinstance(result, dict):
                continue
            result_command = str(result.get('command') or '').strip()
            if result.get('ok') and (command == result_command or command in result_command or result_command in command):
                return True
        return False
    for command in unit.get('verification_commands') or []:
        command_text = str(command).strip()
        if not handoff_text_matches(check, command_text):
            continue
        return any(
            bool(result.get('ok'))
            and (
                command_text == str(result.get('command') or '').strip()
                or command_text in str(result.get('command') or '').strip()
                or str(result.get('command') or '').strip() in command_text
            )
            for result in results
            if isinstance(result, dict)
        )
    return False


def build_handoff_evidence_payload(
    *,
    unit: dict[str, Any],
    unit_dir: Path,
    results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    handoff = unit_handoff(unit)
    if not handoff:
        return None

    unit_id = str(unit.get('id') or unit_dir.name or 'unknown-unit').strip()
    artifact_records: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    for artifact in handoff_evidence_artifacts(unit):
        resolved = resolve_handoff_artifact_path(artifact, unit_dir)
        exists = resolved.exists()
        artifact_records.append({
            'path': artifact,
            'resolved_path': str(resolved),
            'exists': exists,
        })
        if not exists:
            issues.append({
                'type': 'unit_handoff_evidence_missing',
                'message': f'unit {unit_id} handoff evidence artifact is missing: {artifact}',
            })

    for ready_check in handoff_ready_checks(unit):
        if ready_check_passed(unit, ready_check, results):
            continue
        issues.append({
            'type': 'unit_handoff_ready_check_failed',
            'message': f'unit {unit_id} ready_check did not pass or was not mapped to a passed command: {ready_check}',
        })

    payload = {
        'schema_version': 'v0.6.2d-unit-handoff',
        'unit_id': unit_id,
        'passed': not issues,
        'human_summary': handoff_human_summary(unit),
        'produces': handoff_produces(unit),
        'requires': handoff_requires(unit),
        'ready_checks': handoff_ready_checks(unit),
        'evidence_artifacts': artifact_records,
        'issues': issues,
    }
    return payload


def resolve_handoff_artifact_path(path_text: str, unit_dir: Path) -> Path:
    candidate = Path(path_text)
    if candidate.is_absolute():
        return candidate
    candidates = [
        unit_dir / candidate,
        unit_dir.parent / candidate,
        unit_dir.parent.parent / candidate,
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def load_handoff_evidence(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in re.split(r'[,;\n]+', value) if part.strip()]
    return []
