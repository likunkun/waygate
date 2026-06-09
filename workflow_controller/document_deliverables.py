from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from workflow_controller.gates.parsers import gate_body


DOCUMENT_DELIVERABLES_HEADING_PATTERN = re.compile(
    r'(?im)^##+\s+.*(?:Document Deliverables Matrix|文档交付矩阵).*$'
)

LONG_LIVED_FACT_KEYWORDS = [
    'workflow',
    'evidence policy',
    'approval',
    'acceptance gate',
    'verifier evidence',
    'document lifecycle',
    'documentation lifecycle',
    'architecture',
    'module boundary',
    'operations',
    'runbook',
    'deployment',
    'troubleshooting',
    'product',
    'user journey',
    'documentation',
    '工作流',
    '流程',
    '证据规则',
    '审批',
    '验收流程',
    '文档生命周期',
    '架构',
    '模块边界',
    '运维',
    '运行手册',
    '部署',
    '排障',
    '产品',
    '用户旅程',
    '需求说明',
    '文档',
]


def parse_document_deliverables_from_unit_plan(unit_plan_path: Path) -> list[dict[str, Any]]:
    if not unit_plan_path.exists():
        return []
    content = gate_body(unit_plan_path.read_text(encoding='utf-8'))
    return parse_document_deliverables(content)


def parse_document_deliverables(content: str) -> list[dict[str, Any]]:
    section = _document_deliverables_section(content)
    if not section:
        return []

    table = _markdown_table_rows(section)
    if not table:
        return []

    headers = [_normalize_header(cell) for cell in table[0]]
    rows: list[dict[str, Any]] = []
    for cells in table[1:]:
        if len(cells) < 3:
            continue
        row = {
            'area': _cell_by_header(headers, cells, 'area') or cells[0],
            'target_path': _cell_by_header(headers, cells, 'target_path') or cells[1],
            'action': _cell_by_header(headers, cells, 'action') or cells[2],
            'required_for_acceptance': document_deliverable_is_required(
                _cell_by_header(headers, cells, 'required_for_acceptance') or ''
            ),
            'reason': _cell_by_header(headers, cells, 'reason') or cells[-1],
        }
        if _row_is_header_or_empty(row):
            continue
        for target_path in _target_paths_from_cell(str(row.get('target_path') or '')):
            expanded_row = dict(row)
            expanded_row['target_path'] = target_path
            rows.append(expanded_row)
    return rows


def unit_plan_requires_document_deliverables(state: dict[str, Any]) -> bool:
    haystack_parts: list[str] = []
    for unit in state.get('units') or []:
        if not isinstance(unit, dict) or bool(unit.get('passes')):
            continue
        for key in ('name', 'title', 'description'):
            if unit.get(key):
                haystack_parts.append(str(unit.get(key)))
        for key in ('scope', 'non_goals', 'done_when'):
            value = unit.get(key)
            if isinstance(value, list):
                haystack_parts.extend(str(item) for item in value)
            elif value:
                haystack_parts.append(str(value))
    for item in state.get('objectiveCoverage') or []:
        if isinstance(item, dict) and str(item.get('status') or '') != 'covered':
            haystack_parts.append(str(item.get('objective') or ''))

    haystack = _normalize_text('\n'.join(haystack_parts))
    return any(_normalize_text(keyword) in haystack for keyword in LONG_LIVED_FACT_KEYWORDS)


def unit_plan_declares_no_formal_doc_change(content: str) -> bool:
    normalized = _normalize_text(content)
    no_doc_markers = [
        '不需要正式文档变更',
        '无需正式文档变更',
        'no formal document change',
        'no formal docs change',
    ]
    if not any(marker in normalized for marker in no_doc_markers):
        return False
    reason_markers = ['原因', '因为', '纯', 'does not change', 'not change', 'reason']
    return any(marker in normalized for marker in reason_markers)


def document_deliverable_is_required(value: str) -> bool:
    normalized = _normalize_text(value)
    if not normalized:
        return False
    false_values = {
        'false',
        'no',
        'n',
        'not required',
        'not acceptance blocking',
        '非必需',
        '否',
        '不是',
        '不需要',
        '无需',
        'nope',
    }
    if normalized in false_values:
        return False
    return normalized in {
        'true',
        'yes',
        'y',
        'required',
        'acceptance blocking',
        '是',
        '必需',
        '必须',
        '验收必需',
    } or 'true' in normalized or 'required' in normalized or '必需' in normalized or '必须' in normalized


def document_deliverable_status_rows(unit_plan_path: Path, state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = parse_document_deliverables_from_unit_plan(unit_plan_path)
    if not rows:
        return []

    workspace_dir = _workspace_dir_for_state(state, unit_plan_path)
    status_rows: list[dict[str, Any]] = []
    for row in rows:
        target_path = _clean_target_path(str(row.get('target_path') or ''))
        required = bool(row.get('required_for_acceptance'))
        if _target_declares_no_formal_doc_change(target_path):
            status = 'not required'
        elif _target_is_external_reference(target_path):
            status = 'external'
        elif not required:
            status = 'not required'
        elif _target_path_exists(target_path, workspace_dir):
            status = 'present'
        else:
            status = 'missing'
        status_rows.append({
            **row,
            'target_path': target_path,
            'required_for_acceptance': required,
            'status': status,
        })
    return status_rows


def final_document_deliverable_issues(unit_plan_path: Path, state: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for row in document_deliverable_status_rows(unit_plan_path, state):
        if not row.get('required_for_acceptance'):
            continue
        if row.get('status') == 'missing':
            issues.append(
                f"required document deliverable missing: {row.get('target_path')} "
                f"({row.get('action') or 'document action'})"
            )
    return issues


def _document_deliverables_section(content: str) -> str:
    match = DOCUMENT_DELIVERABLES_HEADING_PATTERN.search(content)
    if not match:
        return ''
    start = match.start()
    next_heading = re.search(r'(?m)^##+\s+', content[match.end():])
    end = match.end() + next_heading.start() if next_heading else len(content)
    return content[start:end]


def _markdown_table_rows(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith('|') or '|' not in stripped[1:]:
            continue
        if re.fullmatch(r'\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?', stripped):
            continue
        rows.append([cell.strip() for cell in stripped.strip('|').split('|')])
    return rows


def _normalize_header(value: str) -> str:
    normalized = _normalize_text(value)
    if any(term in normalized for term in ['area', 'category', 'domain', '文档领域', '类别', '类型']):
        return 'area'
    if any(term in normalized for term in ['target path', 'path', 'document path', '目标路径', '文档路径']):
        return 'target_path'
    if any(term in normalized for term in ['action', '动作', '变更']):
        return 'action'
    if any(term in normalized for term in ['required for acceptance', 'required', '验收必需', '是否必需']):
        return 'required_for_acceptance'
    if any(term in normalized for term in ['evidence', 'reason', '说明', '原因', '证据']):
        return 'reason'
    return normalized


def _cell_by_header(headers: list[str], cells: list[str], header: str) -> str:
    try:
        index = headers.index(header)
    except ValueError:
        return ''
    return cells[index].strip() if index < len(cells) else ''


def _row_is_header_or_empty(row: dict[str, Any]) -> bool:
    text = _normalize_text(' '.join(str(value) for value in row.values()))
    if not text:
        return True
    return text in {'area target path action required for acceptance evidence / reason'}


def _workspace_dir_for_state(state: dict[str, Any], unit_plan_path: Path) -> Path:
    raw = state.get('executionWorkspacePath') or state.get('workspacePath')
    if raw:
        return Path(str(raw)).expanduser()
    return unit_plan_path.parent.parent


def _target_path_exists(target_path: str, workspace_dir: Path) -> bool:
    if not target_path:
        return False
    path = Path(target_path).expanduser()
    if not path.is_absolute():
        path = workspace_dir / path
    return path.exists()


def _clean_target_path(value: str) -> str:
    text = value.strip().strip('`*_')
    if ' / ' in text:
        text = text.replace(' / ', '/')
    return text


def _target_paths_from_cell(value: str) -> list[str]:
    if not str(value or '').strip():
        return ['']
    if _target_declares_no_formal_doc_change(value):
        return [_clean_target_path(value)]

    code_spans = re.findall(r'`([^`]+)`', value)
    path_spans = [
        span
        for span in code_spans
        if _looks_like_deliverable_target(span)
    ]
    if len(path_spans) >= 2:
        return [_clean_target_path(span) for span in path_spans]
    return [_clean_target_path(value)]


def _looks_like_deliverable_target(value: str) -> bool:
    text = str(value or '').strip()
    if not text:
        return False
    if _target_is_external_reference(text):
        return True
    return '/' in text or text.endswith(('.md', '.markdown', '.rst', '.txt', '.json', '.html'))


def _target_declares_no_formal_doc_change(value: str) -> bool:
    normalized = _normalize_text(value)
    return any(
        marker in normalized
        for marker in [
            '不需要正式文档变更',
            '无需正式文档变更',
            'no formal document change',
            'no formal docs change',
        ]
    )


def _target_is_external_reference(value: str) -> bool:
    return bool(re.match(r'(?i)https?://', value.strip()))


def _normalize_text(value: str) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip().lower())
