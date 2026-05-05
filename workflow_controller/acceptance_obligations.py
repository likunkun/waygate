from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

OPEN_OBLIGATION_STATUSES = {'open', 'clarified', 'planned'}
CLOSED_OBLIGATION_STATUSES = {'accepted', 'verified', 'deferred', 'rejected', 'duplicate', 'out_of_scope'}


def append_acceptance_obligations(
    state: dict[str, Any],
    *,
    source: str,
    source_ref: str,
    feedback_text: str,
    annotations: list[Any] | None = None,
) -> list[dict[str, Any]]:
    items = _feedback_items(feedback_text, annotations=annotations)
    existing = _state_obligations(state)
    next_number = _next_obligation_number(existing)
    created: list[dict[str, Any]] = []
    for item in items:
        obligation = {
            'id': f'AO-{next_number:03d}',
            'source': source,
            'sourceRef': source_ref,
            'title': item['title'],
            'description': item['description'],
            'category': item.get('category', 'human_feedback'),
            'priority': 'must',
            'status': 'open',
            'ownerStage': 'requirements',
            'mappedAcceptanceCriteria': [],
            'mappedUnits': [],
            'mappedTestCases': [],
            'evidence': [],
        }
        existing.append(obligation)
        created.append(obligation)
        next_number += 1
    state['acceptanceObligations'] = existing
    return created


def write_acceptance_obligation_artifacts(state: dict[str, Any], artifacts_dir: Path) -> None:
    ledger_dir = artifacts_dir / 'acceptance-obligations'
    ledger_dir.mkdir(parents=True, exist_ok=True)
    obligations = _state_obligations(state)
    (ledger_dir / 'acceptance-obligations.json').write_text(
        json.dumps(obligations, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    (ledger_dir / 'acceptance-obligations.md').write_text(
        render_acceptance_obligations_markdown(state),
        encoding='utf-8',
    )


def render_acceptance_obligations_markdown(state: dict[str, Any]) -> str:
    obligations = _state_obligations(state)
    lines = ['# Acceptance Obligation Ledger', '']
    if not obligations:
        lines.extend(['No acceptance obligations recorded.', ''])
        return '\n'.join(lines)
    for obligation in obligations:
        lines.extend([
            f"## {obligation.get('id')}: {obligation.get('title')}",
            '',
            f"Source: {obligation.get('source', 'unknown')}",
            f"Source Ref: {obligation.get('sourceRef', 'unknown')}",
            f"Priority: {obligation.get('priority', 'must')}",
            f"Status: {obligation.get('status', 'open')}",
            f"Owner Stage: {obligation.get('ownerStage', 'requirements')}",
            '',
            'Original Feedback:',
            '',
            str(obligation.get('description') or obligation.get('title') or '').strip(),
            '',
            f"Mapped AC: {_pending_or_join(obligation.get('mappedAcceptanceCriteria'))}",
            f"Mapped Units: {_pending_or_join(obligation.get('mappedUnits'))}",
            f"Mapped Test Cases: {_pending_or_join(obligation.get('mappedTestCases'))}",
            f"Evidence: {_pending_or_join(obligation.get('evidence'))}",
            '',
        ])
    return '\n'.join(lines)


def active_must_obligations(state: dict[str, Any]) -> list[dict[str, Any]]:
    obligations: list[dict[str, Any]] = []
    for obligation in _state_obligations(state):
        priority = str(obligation.get('priority') or 'must').strip().lower()
        status = str(obligation.get('status') or 'open').strip().lower()
        if priority == 'must' and status not in CLOSED_OBLIGATION_STATUSES:
            obligations.append(obligation)
    return obligations


def covered_obligation_ids_from_state_and_text(state: dict[str, Any], text: str) -> set[str]:
    covered = _covered_obligation_ids_from_test_cases(state)
    covered.update(_covered_obligation_ids_from_test_case_matrix(text))
    for obligation in _state_obligations(state):
        status = str(obligation.get('status') or '').strip().lower()
        if status in {'deferred', 'rejected', 'duplicate', 'out_of_scope'}:
            covered.add(str(obligation.get('id')))
    return covered


def _covered_obligation_ids_from_test_cases(state: dict[str, Any]) -> set[str]:
    covered: set[str] = set()
    for unit in state.get('units') or []:
        if not isinstance(unit, dict):
            continue
        for key in ('test_cases', 'testCases'):
            for case in unit.get(key) or []:
                if not isinstance(case, dict) or not _test_case_has_verifiable_evidence(case):
                    continue
                covered.update(_ids_from_value(case.get('covers_obligations')))
                covered.update(_ids_from_value(case.get('coversObligations')))
    return covered


def _covered_obligation_ids_from_test_case_matrix(text: str) -> set[str]:
    section = _markdown_section(text, r'(?:Test Case Matrix|测试用例矩阵)')
    if not section:
        return set()
    covered: set[str] = set()
    header_indices: dict[str, int] | None = None
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith('|') or re.fullmatch(r'\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?', stripped):
            continue
        columns = [column.strip() for column in stripped.strip('|').split('|')]
        if _looks_like_test_case_matrix_header(columns):
            header_indices = _test_case_matrix_column_indices(columns)
            continue
        if len(columns) < 5:
            continue
        column_indices = header_indices or _legacy_test_case_matrix_column_indices()
        criterion = _matrix_cell_at(columns, column_indices.get('criterion'))
        test_case = _matrix_cell_at(columns, column_indices.get('test_case'))
        layer = _matrix_cell_at(columns, column_indices.get('layer'))
        command_or_evidence = _matrix_cell_at(columns, column_indices.get('command_or_evidence'))
        expected = _matrix_cell_at(columns, column_indices.get('expected'))
        if not _matrix_row_has_verifiable_evidence(test_case, layer, command_or_evidence, expected):
            continue
        covered.update(_obligation_ids_in_text(criterion))
        covered.update(_obligation_ids_in_text(test_case))
        covered.update(_obligation_ids_in_text(_matrix_cell_at(columns, column_indices.get('ao'))))
    return covered


def _looks_like_test_case_matrix_header(columns: list[str]) -> bool:
    normalized = [_normalize_header_cell(column) for column in columns]
    return (
        any(cell in {'acceptancecriterion', '验收标准', 'acid'} for cell in normalized)
        and any(cell in {'testcase', '测试用例', 'testcaseid'} for cell in normalized)
    )


def _test_case_matrix_column_indices(columns: list[str]) -> dict[str, int]:
    indices: dict[str, int] = {}
    for index, column in enumerate(columns):
        normalized = _normalize_header_cell(column)
        if normalized in {'acceptancecriterion', '验收标准', 'acid'}:
            indices.setdefault('criterion', index)
        elif normalized in {'testcase', '测试用例', 'testcaseid'}:
            indices.setdefault('test_case', index)
        elif normalized in {'ao', 'aoid'}:
            indices.setdefault('ao', index)
        elif normalized in {'layer', '层级'}:
            indices.setdefault('layer', index)
        elif normalized in {'commandevidence', 'commandmanualevidence', '命令证据', '命令或人工证据'}:
            indices.setdefault('command_or_evidence', index)
        elif normalized in {'expectedresult', 'expected', '预期结果'}:
            indices.setdefault('expected', index)
    return {**_legacy_test_case_matrix_column_indices(), **indices}


def _legacy_test_case_matrix_column_indices() -> dict[str, int]:
    return {
        'criterion': 0,
        'test_case': 1,
        'layer': 2,
        'command_or_evidence': 3,
        'expected': 4,
    }


def _matrix_cell_at(columns: list[str], index: int | None) -> str:
    if index is None or index < 0 or index >= len(columns):
        return ''
    return columns[index]


def _normalize_header_cell(value: str) -> str:
    return re.sub(r'[\s`*_/\-|（）()]+', '', value.strip().lower())


def _markdown_section(text: str, heading_pattern: str) -> str:
    match = re.search(
        rf'(?im)^##+\s+[^\n]*{heading_pattern}[^\n]*\n([\s\S]*?)(?=^##+\s+|\Z)',
        text,
    )
    return match.group(1) if match else ''


def _test_case_has_verifiable_evidence(case: dict[str, Any]) -> bool:
    expected = str(case.get('expected') or case.get('expected_result') or case.get('expectedResult') or '').strip()
    command = str(case.get('command') or '').strip()
    evidence = str(case.get('evidence') or '').strip()
    return bool(expected and (command or evidence))


def _matrix_row_has_verifiable_evidence(test_case: str, layer: str, command_or_evidence: str, expected: str) -> bool:
    if not test_case or test_case.lower() in {'test case', 'pending', 'todo', 'tbd'}:
        return False
    if layer.strip().lower() not in {'unit', 'functional', 'integration', 'e2e', 'manual'}:
        return False
    return bool(command_or_evidence.strip() and expected.strip())


def _state_obligations(state: dict[str, Any]) -> list[dict[str, Any]]:
    raw = state.get('acceptanceObligations')
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _feedback_items(feedback_text: str, *, annotations: list[Any] | None) -> list[dict[str, str]]:
    annotation_items = _items_from_annotations(annotations)
    if annotation_items:
        return annotation_items
    list_items = _items_from_list_text(feedback_text)
    if list_items:
        return [{'title': item, 'description': item} for item in list_items]
    stripped = feedback_text.strip()
    if not stripped:
        return []
    return [{'title': _first_line(stripped), 'description': stripped}]


def _items_from_annotations(annotations: list[Any] | None) -> list[dict[str, str]]:
    if not isinstance(annotations, list):
        return []
    items: list[dict[str, str]] = []
    for annotation in annotations:
        if not isinstance(annotation, dict):
            continue
        comment = str(annotation.get('comment') or annotation.get('feedback') or annotation.get('text') or '').strip()
        quote = str(annotation.get('quote') or annotation.get('selection') or '').strip()
        title = _first_line(comment or quote)
        if not title:
            continue
        description = '\n'.join(part for part in [f'Quote: {quote}' if quote else '', comment] if part).strip()
        items.append({'title': title, 'description': description or title})
    return items


def _items_from_list_text(text: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    marker_re = re.compile(r'^\s*(?:[-*+]\s+|\d+[.)、]\s*)(.+?)\s*$')
    for line in text.splitlines():
        match = marker_re.match(line)
        if match:
            item = match.group(1).strip()
            if _looks_like_checklist_control(item):
                continue
            if current:
                items.append(' '.join(current).strip())
            current = [item]
        elif current and line.strip():
            current.append(line.strip())
    if current:
        items.append(' '.join(current).strip())
    return [item for item in items if item]


def _looks_like_checklist_control(item: str) -> bool:
    return bool(re.match(r'^\[[ xX]\]\s+', item))


def _next_obligation_number(obligations: list[dict[str, Any]]) -> int:
    highest = 0
    for obligation in obligations:
        match = re.fullmatch(r'AO-(\d+)', str(obligation.get('id') or '').strip())
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:160]
    return ''


def _pending_or_join(value: Any) -> str:
    items = sorted(_string_items(value))
    return ', '.join(items) if items else 'pending'


def _ids_from_value(value: Any) -> set[str]:
    ids: set[str] = set()
    for item in _string_items(value):
        ids.update(_obligation_ids_in_text(item))
    return ids


def _string_items(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _obligation_ids_in_text(text: str) -> set[str]:
    return {match.group(0).upper() for match in re.finditer(r'\bAO-\d{3,}\b', text, flags=re.IGNORECASE)}
