from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflow_controller.acceptance_obligations import active_must_obligations
from workflow_controller.gates.parsers import gate_body
from workflow_controller.journeys import final_journey_matrix_rows
from workflow_controller.rrc_real_runtime import collect_git_changed_files


FINAL_SCOPE_AUDIT_VERSION = 'v0.4.5'
FINAL_SCOPE_AUDIT_ARTIFACT_DIR = 'final-scope-audit'
FINAL_SCOPE_AUDIT_JSON = 'scope-audit.json'
FINAL_SCOPE_AUDIT_MARKDOWN = 'scope-audit.md'
BLOCKER_SEVERITY = 'blocker'
REVIEW_SEVERITY = 'review'


def final_scope_audit_paths(artifacts_dir: Path) -> tuple[Path, Path]:
    audit_dir = artifacts_dir / FINAL_SCOPE_AUDIT_ARTIFACT_DIR
    return audit_dir / FINAL_SCOPE_AUDIT_JSON, audit_dir / FINAL_SCOPE_AUDIT_MARKDOWN


def write_final_scope_audit(
    state: dict[str, Any],
    artifacts_dir: Path,
    *,
    requirements_path: Path | None = None,
    workspace_dir: Path | None = None,
) -> dict[str, Any]:
    artifacts_dir = Path(artifacts_dir)
    requirements_path = requirements_path or artifacts_dir.parent / 'approvals' / 'requirements-and-acceptance.md'
    workspace_dir = _workspace_dir_from_state(state, workspace_dir)

    evidence_rows, evidence_sources = _verification_evidence_rows(artifacts_dir)
    ao_coverage = _acceptance_obligation_coverage(state, evidence_rows)
    ac_coverage = _acceptance_criterion_coverage(requirements_path, evidence_rows)
    journey_coverage = _journey_coverage(state, artifacts_dir)
    changed_files = _changed_files_audit(state, artifacts_dir, workspace_dir)
    issues = [
        *_ao_issues(ao_coverage),
        *_ac_issues(ac_coverage),
        *_journey_issues(journey_coverage),
        *_changed_file_issues(changed_files),
    ]

    json_path, markdown_path = final_scope_audit_paths(artifacts_dir)
    payload: dict[str, Any] = {
        'version': FINAL_SCOPE_AUDIT_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'audit_hash': None,
        'task_id': state.get('task_id'),
        'current_step': state.get('currentStep'),
        'current_unit_id': state.get('currentUnitId'),
        'requirements_gate_path': str(requirements_path),
        'evidence_sources': evidence_sources,
        'ao_coverage': ao_coverage,
        'ac_coverage': ac_coverage,
        'journey_coverage': journey_coverage,
        'changed_files': changed_files,
        'issues': issues,
        'artifact_paths': {
            'json': _artifact_ref(json_path, artifacts_dir),
            'markdown': _artifact_ref(markdown_path, artifacts_dir),
        },
    }
    payload['audit_hash'] = _audit_hash(payload)

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    markdown_path.write_text(_scope_audit_markdown(payload), encoding='utf-8')
    return payload


def load_final_scope_audit(artifacts_dir: Path) -> dict[str, Any] | None:
    json_path, _ = final_scope_audit_paths(artifacts_dir)
    if not json_path.exists():
        return None
    return json.loads(json_path.read_text(encoding='utf-8'))


def validate_final_scope_audit(audit: dict[str, Any] | None) -> None:
    if not audit:
        raise ValueError('final scope audit artifact is missing')
    blockers = [
        issue for issue in audit.get('issues') or []
        if isinstance(issue, dict) and issue.get('severity') == BLOCKER_SEVERITY
    ]
    if not blockers:
        return
    messages = [
        str(issue.get('message') or issue.get('type') or 'scope audit blocker')
        for issue in blockers
    ]
    raise ValueError('final scope audit has blocker(s): ' + '; '.join(messages))


def final_scope_audit_gate_lines(artifacts_dir: Path) -> list[str]:
    audit = load_final_scope_audit(artifacts_dir)
    lines = [
        '',
        '## Final Scope Audit',
        '',
    ]
    if not audit:
        lines.extend([
            '- Scope audit artifact: `missing`',
            f'- Expected JSON: `artifacts/{FINAL_SCOPE_AUDIT_ARTIFACT_DIR}/{FINAL_SCOPE_AUDIT_JSON}`',
            f'- Expected Markdown: `artifacts/{FINAL_SCOPE_AUDIT_ARTIFACT_DIR}/{FINAL_SCOPE_AUDIT_MARKDOWN}`',
        ])
        return lines

    ao = audit.get('ao_coverage') or {}
    ac = audit.get('ac_coverage') or {}
    journeys = audit.get('journey_coverage') or {}
    changed = audit.get('changed_files') or {}
    blockers = [
        issue for issue in audit.get('issues') or []
        if isinstance(issue, dict) and issue.get('severity') == BLOCKER_SEVERITY
    ]
    review_issues = [
        issue for issue in audit.get('issues') or []
        if isinstance(issue, dict) and issue.get('severity') == REVIEW_SEVERITY
    ]
    paths = audit.get('artifact_paths') or {}
    json_ref = paths.get('json') or f'artifacts/{FINAL_SCOPE_AUDIT_ARTIFACT_DIR}/{FINAL_SCOPE_AUDIT_JSON}'
    markdown_ref = paths.get('markdown') or f'artifacts/{FINAL_SCOPE_AUDIT_ARTIFACT_DIR}/{FINAL_SCOPE_AUDIT_MARKDOWN}'

    lines.extend([
        f"- Audit hash: `sha256:{audit.get('audit_hash') or 'unknown'}`",
        f"- AO coverage: `{ao.get('covered_count', 0)}/{ao.get('required_count', 0)}`",
        f"- AC coverage: `{ac.get('covered_count', 0)}/{ac.get('required_count', 0)}`",
        f"- Journey coverage: `{journeys.get('covered_count', 0)}/{journeys.get('required_count', 0)}`",
        f"- Declared changed files: `{len(changed.get('declared_files') or [])}`",
        f"- Unexplained changed files: `{len(changed.get('unexplained_changed_files') or [])}`",
        f"- Audit JSON: `{json_ref}`",
        f"- Audit Markdown: `{markdown_ref}`",
    ])
    if ao.get('uncovered_ids'):
        lines.append('- Uncovered AO: ' + ', '.join(f"`{item}`" for item in ao['uncovered_ids']))
    if ac.get('uncovered_ids'):
        lines.append('- Uncovered AC: ' + ', '.join(f"`{item}`" for item in ac['uncovered_ids']))
    if journeys.get('uncovered_ids'):
        lines.append('- Uncovered Journey: ' + ', '.join(f"`{item}`" for item in journeys['uncovered_ids']))
    unexplained = changed.get('unexplained_changed_files') or []
    if unexplained:
        lines.append('- Unexplained changed file list:')
        lines.extend(f'  - `{path}`' for path in unexplained[:20])
    if blockers:
        lines.append('- Blocking scope issue(s):')
        lines.extend(f"  - {issue.get('message') or issue.get('type')}" for issue in blockers[:20])
    if review_issues:
        lines.append('- Human review scope issue(s):')
        lines.extend(f"  - {issue.get('message') or issue.get('type')}" for issue in review_issues[:20])
    return lines


def _verification_evidence_rows(artifacts_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    sources: list[str] = []
    for path in sorted(artifacts_dir.rglob('verification.json')):
        if FINAL_SCOPE_AUDIT_ARTIFACT_DIR in path.parts:
            continue
        payload = _load_json_object(path)
        if not payload:
            continue
        source_ref = _artifact_ref(path, artifacts_dir)
        sources.append(source_ref)
        raw_rows = payload.get('evidence_rows')
        if not isinstance(raw_rows, list):
            continue
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            copied = dict(row)
            copied['_source_ref'] = source_ref
            rows.append(copied)
    return rows, sources


def _acceptance_obligation_coverage(
    state: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    required_items: list[dict[str, Any]] = []
    for obligation in active_must_obligations(state):
        obligation_id = _normalize_id(obligation.get('id'))
        if not obligation_id:
            continue
        required_items.append({
            'id': obligation_id,
            'title': obligation.get('title') or '',
            'priority': obligation.get('priority') or '',
            'status': obligation.get('status') or '',
        })

    evidence_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in evidence_rows:
        if not _row_is_valid_coverage(row):
            continue
        for obligation_id in _ids_from_value(row.get('acceptance_obligations'), 'AO'):
            evidence_by_id.setdefault(obligation_id, []).append(_evidence_ref(row))

    required_ids = [item['id'] for item in required_items]
    covered_ids = [item for item in required_ids if item in evidence_by_id]
    uncovered_ids = [item for item in required_ids if item not in evidence_by_id]
    return {
        'required_count': len(required_ids),
        'covered_count': len(covered_ids),
        'required_items': required_items,
        'covered_ids': covered_ids,
        'uncovered_ids': uncovered_ids,
        'evidence_by_id': {key: evidence_by_id[key] for key in covered_ids},
    }


def _acceptance_criterion_coverage(
    requirements_path: Path,
    evidence_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    required_ids = _requirements_ac_ids(requirements_path)
    evidence_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in evidence_rows:
        if not _row_is_valid_coverage(row):
            continue
        for ac_id in _ids_from_value(row.get('acceptance_criterion'), 'AC'):
            evidence_by_id.setdefault(ac_id, []).append(_evidence_ref(row))

    covered_ids = [item for item in required_ids if item in evidence_by_id]
    uncovered_ids = [item for item in required_ids if item not in evidence_by_id]
    return {
        'required_count': len(required_ids),
        'covered_count': len(covered_ids),
        'required_ids': required_ids,
        'covered_ids': covered_ids,
        'uncovered_ids': uncovered_ids,
        'evidence_by_id': {key: evidence_by_id[key] for key in covered_ids},
    }


def _journey_coverage(state: dict[str, Any], artifacts_dir: Path) -> dict[str, Any]:
    rows = final_journey_matrix_rows(state, artifacts_dir)
    required_ids: list[str] = []
    evidence_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        journey_id = _normalize_id(row.get('journey_id'))
        if not journey_id:
            continue
        if journey_id not in required_ids:
            required_ids.append(journey_id)
        evidence_by_id.setdefault(journey_id, []).append(_journey_evidence_ref(row))

    covered_ids = [
        journey_id for journey_id in required_ids
        if any(row.get('status') == 'passed' for row in evidence_by_id.get(journey_id, []))
    ]
    uncovered_ids = [journey_id for journey_id in required_ids if journey_id not in covered_ids]
    return {
        'required_count': len(required_ids),
        'covered_count': len(covered_ids),
        'required_ids': required_ids,
        'covered_ids': covered_ids,
        'uncovered_ids': uncovered_ids,
        'evidence_by_id': evidence_by_id,
    }


def _changed_files_audit(
    state: dict[str, Any],
    artifacts_dir: Path,
    workspace_dir: Path | None,
) -> dict[str, Any]:
    completed_unit_ids = _completed_unit_ids(state)
    sources: list[dict[str, Any]] = []
    declared_files: list[str] = []
    completed_declared_files: list[str] = []

    for path in sorted(artifacts_dir.rglob('changed-files.txt')):
        if FINAL_SCOPE_AUDIT_ARTIFACT_DIR in path.parts or 'journeys' in path.parts:
            continue
        files = _read_lines(path)
        source = _changed_file_source(path, artifacts_dir, state, completed_unit_ids)
        source['files'] = files
        sources.append(source)
        declared_files.extend(files)
        if source['completed']:
            completed_declared_files.extend(files)

    baseline_files = _unique_list(state.get('baselineChangedFiles') or [])
    workspace_changed_files = _workspace_changed_files(workspace_dir)
    auditable_workspace_files = [
        path for path in workspace_changed_files
        if path not in set(baseline_files)
    ]
    completed_declared = set(_unique_list(completed_declared_files))
    unexplained = [
        path for path in auditable_workspace_files
        if path not in completed_declared
    ]
    return {
        'artifact_sources': sources,
        'declared_files': _unique_list(declared_files),
        'completed_declared_files': _unique_list(completed_declared_files),
        'baseline_changed_files': baseline_files,
        'workspace_changed_files': workspace_changed_files,
        'auditable_workspace_changed_files': auditable_workspace_files,
        'unexplained_changed_files': unexplained,
    }


def _ao_issues(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            'severity': BLOCKER_SEVERITY,
            'type': 'missing_acceptance_obligation_evidence',
            'id': ao_id,
            'message': f'active must AO {ao_id} has no passed or valid manual evidence row',
        }
        for ao_id in coverage.get('uncovered_ids') or []
    ]


def _ac_issues(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            'severity': BLOCKER_SEVERITY,
            'type': 'missing_acceptance_criterion_evidence',
            'id': ac_id,
            'message': f'approved acceptance criterion {ac_id} has no passed or valid manual evidence row',
        }
        for ac_id in coverage.get('uncovered_ids') or []
    ]


def _journey_issues(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            'severity': BLOCKER_SEVERITY,
            'type': 'missing_journey_evidence',
            'id': journey_id,
            'message': f'active journey {journey_id} has no passed journey evidence row',
        }
        for journey_id in coverage.get('uncovered_ids') or []
    ]


def _changed_file_issues(changed_files: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            'severity': REVIEW_SEVERITY,
            'type': 'unexplained_changed_file',
            'file': path,
            'message': f'changed file {path} is not explained by any completed unit changed-files.txt artifact',
        }
        for path in changed_files.get('unexplained_changed_files') or []
    ]


def _requirements_ac_ids(requirements_path: Path) -> list[str]:
    if not requirements_path.exists():
        return []
    content = gate_body(requirements_path.read_text(encoding='utf-8'))
    return _unique_list(_ids_from_value(content, 'AC'))


def _row_is_valid_coverage(row: dict[str, Any]) -> bool:
    status = row.get('status')
    if status == 'passed':
        return True
    if status != 'manual':
        return False
    manual_evidence = str(row.get('manual_evidence') or '').strip()
    artifact_refs = [
        str(item).strip()
        for item in row.get('artifact_refs') or []
        if str(item).strip()
    ]
    return bool(manual_evidence or artifact_refs)


def _evidence_ref(row: dict[str, Any]) -> dict[str, Any]:
    artifact_refs = [
        str(item).strip()
        for item in row.get('artifact_refs') or []
        if str(item).strip()
    ]
    return {
        'unit_id': row.get('unit_id'),
        'test_case_id': row.get('test_case_id'),
        'status': row.get('status'),
        'command': row.get('command'),
        'manual_evidence': row.get('manual_evidence'),
        'artifact_refs': artifact_refs or [row.get('_source_ref') or 'verification.json'],
        'source': row.get('_source_ref'),
    }


def _journey_evidence_ref(row: dict[str, Any]) -> dict[str, Any]:
    return {
        'journey_id': row.get('journey_id'),
        'title': row.get('title'),
        'status': row.get('status') or 'missing',
        'unit_id': row.get('unit_id'),
        'test_case_id': row.get('test_case_id'),
        'command': row.get('command'),
        'artifact_refs': row.get('artifact_refs') or ['artifacts/journeys/journey-evidence.json'],
    }


def _changed_file_source(
    path: Path,
    artifacts_dir: Path,
    state: dict[str, Any],
    completed_unit_ids: set[str],
) -> dict[str, Any]:
    relative = path.relative_to(artifacts_dir)
    parts = relative.parts
    unit_id = parts[0] if parts else 'unknown'
    source_type = 'unit'
    completed = unit_id in completed_unit_ids
    if len(parts) >= 3 and parts[0] == 'bug-fixes':
        source_type = 'bug_fix'
        unit_id = f'{parts[0]}/{parts[1]}'
        completed = _bug_fix_source_is_completed(state, parts[1], path.parent)
    elif not completed and state.get('currentStep') in {'WAITING_FINAL_ACCEPTANCE', 'RELEASE_GATE', 'DONE'}:
        completed = _verification_passed(path.parent / 'verification.json')
    return {
        'source': _artifact_ref(path, artifacts_dir),
        'source_type': source_type,
        'unit_id': unit_id,
        'completed': completed,
    }


def _completed_unit_ids(state: dict[str, Any]) -> set[str]:
    completed: set[str] = set()
    for unit in state.get('units') or []:
        if isinstance(unit, dict) and unit.get('passes') is True and unit.get('id'):
            completed.add(str(unit['id']))
    for coverage in state.get('objectiveCoverage') or []:
        if not isinstance(coverage, dict) or coverage.get('status') != 'covered':
            continue
        for unit_id in coverage.get('units') or []:
            if str(unit_id).strip():
                completed.add(str(unit_id).strip())
    current_unit_id = str(state.get('currentUnitId') or '').strip()
    if current_unit_id and state.get('currentStep') in {'WAITING_FINAL_ACCEPTANCE', 'RELEASE_GATE', 'DONE'}:
        completed.add(current_unit_id)
    return completed


def _bug_fix_source_is_completed(state: dict[str, Any], bug_fix_id: str, source_dir: Path) -> bool:
    if state.get('activeBugFixId') == bug_fix_id and state.get('bugFixVerified') is True:
        return True
    return _verification_passed(source_dir / 'verification.json')


def _verification_passed(path: Path) -> bool:
    payload = _load_json_object(path)
    return bool(payload and payload.get('passed') is True)


def _workspace_changed_files(workspace_dir: Path | None) -> list[str]:
    if workspace_dir is None or not workspace_dir.exists():
        return []
    return collect_git_changed_files(workspace_dir)


def _workspace_dir_from_state(state: dict[str, Any], workspace_dir: Path | None) -> Path | None:
    if workspace_dir is not None:
        return Path(workspace_dir)
    raw = state.get('executionWorkspacePath') or state.get('workspacePath')
    if not raw:
        return None
    return Path(str(raw))


def _scope_audit_markdown(audit: dict[str, Any]) -> str:
    ao = audit.get('ao_coverage') or {}
    ac = audit.get('ac_coverage') or {}
    journeys = audit.get('journey_coverage') or {}
    changed = audit.get('changed_files') or {}
    lines = [
        '# Final Scope Audit',
        '',
        f"- Version: `{audit.get('version')}`",
        f"- Generated at: `{audit.get('generated_at')}`",
        f"- Audit hash: `sha256:{audit.get('audit_hash')}`",
        '',
        '## Coverage Summary',
        f"- AO coverage: `{ao.get('covered_count', 0)}/{ao.get('required_count', 0)}`",
        f"- AC coverage: `{ac.get('covered_count', 0)}/{ac.get('required_count', 0)}`",
        f"- Journey coverage: `{journeys.get('covered_count', 0)}/{journeys.get('required_count', 0)}`",
        f"- Declared changed files: `{len(changed.get('declared_files') or [])}`",
        f"- Unexplained changed files: `{len(changed.get('unexplained_changed_files') or [])}`",
        '',
        '## Acceptance Obligation Coverage',
        '',
        '| AO | Status | Evidence |',
        '| --- | --- | --- |',
    ]
    _append_coverage_rows(lines, ao.get('required_items') or [], ao.get('evidence_by_id') or {})
    lines.extend([
        '',
        '## Acceptance Criterion Coverage',
        '',
        '| AC | Status | Evidence |',
        '| --- | --- | --- |',
    ])
    _append_id_coverage_rows(
        lines,
        ac.get('required_ids') or [],
        ac.get('evidence_by_id') or {},
        set(ac.get('covered_ids') or []),
    )
    lines.extend([
        '',
        '## Journey Coverage',
        '',
        '| Journey | Status | Evidence |',
        '| --- | --- | --- |',
    ])
    _append_id_coverage_rows(
        lines,
        journeys.get('required_ids') or [],
        journeys.get('evidence_by_id') or {},
        set(journeys.get('covered_ids') or []),
    )
    lines.extend([
        '',
        '## Changed Files',
        '',
        '- Declared files from completed artifacts:',
    ])
    completed_declared = changed.get('completed_declared_files') or []
    lines.extend(f'  - `{path}`' for path in completed_declared) if completed_declared else lines.append('  - none')
    lines.append('- Unexplained changed files:')
    unexplained = changed.get('unexplained_changed_files') or []
    lines.extend(f'  - `{path}`' for path in unexplained) if unexplained else lines.append('  - none')
    lines.extend([
        '',
        '## Validation Issues',
    ])
    issues = audit.get('issues') or []
    if issues:
        lines.extend(
            f"- `{issue.get('severity')}` `{issue.get('type')}`: {issue.get('message')}"
            for issue in issues
            if isinstance(issue, dict)
        )
    else:
        lines.append('- none')
    return '\n'.join(lines).rstrip() + '\n'


def _append_coverage_rows(
    lines: list[str],
    items: list[dict[str, Any]],
    evidence_by_id: dict[str, list[dict[str, Any]]],
) -> None:
    if not items:
        lines.append('| none | covered | No active must AO required. |')
        return
    for item in items:
        item_id = str(item.get('id') or '').strip()
        evidence = evidence_by_id.get(item_id) or []
        status = 'covered' if evidence else 'missing'
        title = str(item.get('title') or '').strip()
        label = f'{item_id} {title}'.strip()
        lines.append(f'| {_markdown_cell(label)} | {status} | {_markdown_cell(_coverage_evidence_text(evidence))} |')


def _append_id_coverage_rows(
    lines: list[str],
    ids: list[str],
    evidence_by_id: dict[str, list[dict[str, Any]]],
    covered_ids: set[str],
) -> None:
    if not ids:
        lines.append('| none | covered | No active item required. |')
        return
    for item_id in ids:
        evidence = evidence_by_id.get(item_id) or []
        status = 'covered' if item_id in covered_ids else 'missing'
        lines.append(f'| {_markdown_cell(item_id)} | {status} | {_markdown_cell(_coverage_evidence_text(evidence))} |')


def _coverage_evidence_text(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return 'missing'
    refs: list[str] = []
    for item in evidence:
        command = str(item.get('command') or '').strip()
        if command:
            refs.append(f'`{command}`')
            continue
        manual = str(item.get('manual_evidence') or '').strip()
        if manual:
            refs.append(manual)
            continue
        artifact_refs = item.get('artifact_refs') or []
        if artifact_refs:
            refs.append(', '.join(str(ref) for ref in artifact_refs if str(ref).strip()))
    return '<br>'.join(refs) or 'missing'


def _audit_hash(payload: dict[str, Any]) -> str:
    semantic = {
        key: value
        for key, value in payload.items()
        if key not in {'generated_at', 'audit_hash'}
    }
    encoded = json.dumps(semantic, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _artifact_ref(path: Path, artifacts_dir: Path) -> str:
    try:
        return 'artifacts/' + path.relative_to(artifacts_dir).as_posix()
    except ValueError:
        return str(path)


def _load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]


def _ids_from_value(value: Any, prefix: str) -> list[str]:
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_ids_from_value(item, prefix))
        return _unique_list(values)
    pattern = rf'(?<![A-Za-z0-9_-]){re.escape(prefix)}-[A-Za-z0-9]+(?:[_.-][A-Za-z0-9]+)*'
    ids = [_normalize_id(match.group(0)) for match in re.finditer(pattern, str(value), re.IGNORECASE)]
    return _unique_list(item for item in ids if _id_is_not_placeholder(item, prefix))


def _normalize_id(value: Any) -> str:
    return str(value or '').strip().upper()


def _id_is_not_placeholder(value: str, prefix: str) -> bool:
    suffix = value.removeprefix(prefix + '-')
    return suffix not in {'ID', 'IDS', '待补'}


def _unique_list(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _markdown_cell(value: Any) -> str:
    return str(value).replace('|', '\\|').replace('\n', '<br>').strip()
