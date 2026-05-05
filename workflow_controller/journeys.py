from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflow_controller.gates.parsers import _unit_test_cases, gate_body, hash_gate_body


JOURNEY_CONTRACT_VERSION = 1
ALLOWED_JOURNEY_STATUSES = {'active', 'deferred', 'rejected', 'out_of_scope'}
ALLOWED_JOURNEY_LAYERS = {'functional', 'integration', 'e2e', 'manual'}
JOURNEY_ID_HEADERS = ('journey', 'journey id', 'journey_id', '旅程', '旅程 id')
JOURNEY_VALUE_ID_HEADERS = ('journey', 'journey id', 'journey_id', 'id', '旅程', '旅程 id')
JOURNEY_TITLE_HEADERS = ('title', 'name', '标题', '名称')
JOURNEY_STATUS_HEADERS = ('status', '状态')
JOURNEY_STEPS_HEADERS = ('steps', 'step', '路径', '步骤')
JOURNEY_AC_HEADERS = (
    'ac',
    'acs',
    'acceptance criteria',
    'acceptance criterion',
    'linked ac',
    '验收标准',
)
JOURNEY_LAYER_HEADERS = ('verification layer', 'layer', '验证层级')
JOURNEY_COMMAND_HEADERS = ('verification command', 'command', '命令')
JOURNEY_TEST_CASE_HEADERS = ('test case', 'test cases', 'tc', '测试用例')
JOURNEY_UNIT_HEADERS = ('unit', 'units', 'linked units', '单元')


def validate_and_write_journey_contract(
    *,
    requirements_path: Path,
    artifacts_dir: Path,
    state: dict[str, Any],
    unit_plan_path: Path | None = None,
) -> Path | None:
    if not requirements_path.exists():
        return None

    requirements_body = gate_body(requirements_path.read_text(encoding='utf-8'))
    journeys = extract_requirement_journeys(requirements_body)
    required = requirements_requires_journey_contract(requirements_body)
    active = [journey for journey in journeys if journey['status'] == 'active']

    if required and not active:
        raise ValueError(
            'journey contract required for e2e or closure acceptance; '
            'add a Journey Acceptance Matrix with active journey rows'
        )

    _validate_journeys(journeys)
    if not journeys:
        state.pop('journeyContractPath', None)
        return None

    journey_dir = artifacts_dir / 'journeys'
    journey_dir.mkdir(parents=True, exist_ok=True)
    path = journey_dir / 'journeys.json'
    unit_plan_hash = None
    if unit_plan_path and unit_plan_path.exists():
        unit_plan_hash = hash_gate_body(gate_body(unit_plan_path.read_text(encoding='utf-8')))
    payload = {
        'version': JOURNEY_CONTRACT_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_gate': 'requirements',
        'requirements_gate_path': str(requirements_path),
        'requirements_gate_hash': hash_gate_body(requirements_body),
        'unit_plan_gate_path': str(unit_plan_path) if unit_plan_path else None,
        'unit_plan_gate_hash': unit_plan_hash,
        'journeys': journeys,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    state['journeyContractPath'] = str(path)
    return path


def validate_and_enrich_journey_unit_plan(
    *,
    unit_plan_path: Path,
    artifacts_dir: Path,
    state: dict[str, Any],
) -> Path | None:
    contract_path = _journey_contract_path(artifacts_dir, state)
    if not contract_path.exists():
        return None

    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    journeys = contract.get('journeys')
    if not isinstance(journeys, list):
        raise ValueError(f'journey contract invalid: journeys must be a list: {contract_path}')

    mappings = _journey_test_case_mappings(state)
    issues: list[str] = []
    enriched_journeys: list[dict[str, Any]] = []
    for journey in journeys:
        if not isinstance(journey, dict):
            issues.append('journey contract contains a non-object journey row')
            continue
        enriched = dict(journey)
        if journey.get('status') != 'active':
            enriched_journeys.append(enriched)
            continue

        journey_id = str(journey.get('journey_id') or '').strip()
        mapped = mappings.get(journey_id, [])
        if not mapped:
            issues.append(f'active journey {journey_id or "unknown"} has no mapped test case')
            enriched_journeys.append(enriched)
            continue

        valid_mapped = []
        for mapping in mapped:
            case_issues = _journey_mapping_issues(journey, mapping)
            if case_issues:
                issues.extend(f'{journey_id} {issue}' for issue in case_issues)
            else:
                valid_mapped.append(mapping)

        if valid_mapped:
            enriched['linked_units'] = _dedupe(
                _unit_identifier(mapping['unit'])
                for mapping in valid_mapped
            )
            enriched['test_cases'] = _dedupe(
                _test_case_identifier(mapping['case'])
                for mapping in valid_mapped
            )
            enriched['verification_command'] = _test_case_command(valid_mapped[0]['case']) or None
        enriched_journeys.append(enriched)

    if issues:
        raise ValueError('journey mapping is incomplete: ' + '; '.join(issues))

    contract['journeys'] = enriched_journeys
    contract['unit_plan_gate_path'] = str(unit_plan_path)
    contract['unit_plan_gate_hash'] = hash_gate_body(gate_body(unit_plan_path.read_text(encoding='utf-8')))
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding='utf-8')
    state['journeyContractPath'] = str(contract_path)
    return contract_path


def final_journey_matrix_rows(state: dict[str, Any], artifacts_dir: Path) -> list[dict[str, Any]]:
    contract = _load_journey_contract(state, artifacts_dir)
    if not contract:
        return []
    evidence_rows = _load_journey_evidence_rows(state, artifacts_dir)
    evidence_by_journey: dict[str, list[dict[str, Any]]] = {}
    for row in evidence_rows:
        evidence_by_journey.setdefault(str(row.get('journey_id') or ''), []).append(row)

    rows: list[dict[str, Any]] = []
    for journey in _active_journeys(contract):
        journey_id = str(journey.get('journey_id') or '')
        matched = evidence_by_journey.get(journey_id) or []
        if not matched:
            rows.append({
                'journey_id': journey_id,
                'title': journey.get('title') or journey_id,
                'acceptance_criteria': journey.get('linked_acceptance_criteria') or [],
                'unit_id': _join_cell(journey.get('linked_units')) or '未指定',
                'test_case_id': _join_cell(journey.get('test_cases')) or '未指定',
                'layer': journey.get('verification_layer') or '未指定',
                'status': 'missing',
                'command': journey.get('verification_command'),
                'expected': '未指定',
                'artifact_refs': ['artifacts/journeys/journey-evidence.json'],
            })
            continue
        rows.extend(matched)
    return rows


def validate_final_journey_acceptance(state: dict[str, Any], artifacts_dir: Path) -> None:
    contract_path = _journey_contract_path(artifacts_dir, state)
    if not contract_path.exists():
        if str(state.get('journeyContractPath') or '').strip():
            raise ValueError(f'journey contract missing: {contract_path}')
        return

    contract = _load_json_object(contract_path)
    active = _active_journeys(contract)
    if not active:
        return

    issues = _journey_contract_hash_issues(contract)
    evidence_rows = _load_journey_evidence_rows(state, artifacts_dir)
    for journey in active:
        journey_id = str(journey.get('journey_id') or '').strip()
        rows = [row for row in evidence_rows if str(row.get('journey_id') or '').strip() == journey_id]
        if not rows:
            issues.append(f'active journey {journey_id} has no journey evidence')
            continue
        if not any(row.get('status') == 'passed' for row in rows):
            statuses = ', '.join(str(row.get('status') or 'missing') for row in rows)
            issues.append(f'active journey {journey_id} has no passed journey evidence: {statuses}')

    if issues:
        raise ValueError('journey acceptance is incomplete: ' + '; '.join(issues))


def requirements_requires_journey_contract(requirements_body: str) -> bool:
    return (
        bool(extract_requirement_journeys(requirements_body))
        or _requirements_declares_e2e_acceptance(requirements_body)
        or bool(re.search(r'(?i)\bworkflow_validation_level\s*[:=]\s*closure\b', requirements_body))
    )


def _requirements_declares_e2e_acceptance(requirements_body: str) -> bool:
    return (
        _requirements_has_e2e_acceptance_line(requirements_body)
        or _requirements_has_e2e_traceability_row(requirements_body)
    )


def _requirements_has_e2e_acceptance_line(requirements_body: str) -> bool:
    for line in requirements_body.splitlines():
        if _is_table_line(line) or _is_separator_row(line):
            continue
        if not _actual_ac_ids_from_text(line):
            continue
        if _line_declares_e2e_verification_layer(line):
            return True
    return False


def _line_declares_e2e_verification_layer(line: str) -> bool:
    patterns = [
        r'\bverification(?:\s+layer)?\s*[:：=]\s*e2e\b',
        r'\[\s*verification\s*:\s*e2e\s*\]',
        r'\b验证(?:层级|层|方式)?\s*[:：]\s*e2e\b',
        r'\(\s*e2e\s*\)',
    ]
    return any(re.search(pattern, line, re.IGNORECASE) for pattern in patterns)


def _requirements_has_e2e_traceability_row(requirements_body: str) -> bool:
    lines = requirements_body.splitlines()
    for index, line in enumerate(lines):
        if not _is_table_line(line):
            continue
        header = _split_table_line(line)
        normalized = [_normalize_header(cell) for cell in header]
        layer_indexes = [
            column_index
            for column_index, header_name in enumerate(normalized)
            if header_name in JOURNEY_LAYER_HEADERS
        ]
        if not layer_indexes:
            continue
        if index + 1 >= len(lines) or not _is_separator_row(lines[index + 1]):
            continue
        cursor = index + 2
        while cursor < len(lines) and _is_table_line(lines[cursor]):
            cells = _split_table_line(lines[cursor])
            if _actual_ac_ids_from_text(lines[cursor]) and any(
                column_index < len(cells) and _is_e2e_layer_value(cells[column_index])
                for column_index in layer_indexes
            ):
                return True
            cursor += 1
    return False


def _is_e2e_layer_value(value: str) -> bool:
    normalized = re.sub(r'[`*_，。:：;；\s]+', ' ', str(value).strip().lower()).strip()
    return normalized in {'e2e', 'end-to-end', 'end to end'}


def _actual_ac_ids_from_text(value: str) -> list[str]:
    return _ids_from_text(value, r'(?<![A-Za-z0-9_-])AC-\d+(?:[-.]\d+)*')


def extract_requirement_journeys(requirements_body: str) -> list[dict[str, Any]]:
    rows = _journey_table_rows(requirements_body)
    journeys: list[dict[str, Any]] = []
    for row in rows:
        journey_id = _first_value(row, *JOURNEY_VALUE_ID_HEADERS)
        title = _first_value(row, *JOURNEY_TITLE_HEADERS) or journey_id
        status = (_first_value(row, *JOURNEY_STATUS_HEADERS) or 'active').lower()
        steps = _split_steps(_first_value(row, *JOURNEY_STEPS_HEADERS) or '')
        ac_cell = _first_value(row, *JOURNEY_AC_HEADERS) or ''
        layer = (_first_value(row, *JOURNEY_LAYER_HEADERS) or '').lower()
        command = _first_value(row, *JOURNEY_COMMAND_HEADERS)
        test_cases = _ids_from_text(
            _first_value(row, *JOURNEY_TEST_CASE_HEADERS) or '',
            r'(?<![A-Za-z0-9_-])TC-[A-Za-z0-9_-]+',
        )
        linked_units = _ids_from_text(
            _first_value(row, *JOURNEY_UNIT_HEADERS) or '',
            r'(?<![A-Za-z0-9_-])(?:unit|u)-[A-Za-z0-9_-]+',
        )
        journeys.append({
            'journey_id': journey_id,
            'title': title,
            'status': status,
            'steps': steps,
            'linked_acceptance_criteria': _ids_from_text(ac_cell, r'(?<![A-Za-z0-9_-])AC-[A-Za-z0-9_-]+'),
            'linked_units': linked_units,
            'verification_layer': layer,
            'verification_command': command,
            'test_cases': test_cases,
        })
    return journeys


def _validate_journeys(journeys: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    issues: list[str] = []
    for index, journey in enumerate(journeys, start=1):
        prefix = f'journey row {index}'
        journey_id = str(journey.get('journey_id') or '').strip()
        if not journey_id:
            issues.append(f'{prefix} missing journey_id')
            continue
        if journey_id in seen:
            issues.append(f'{journey_id} is duplicated')
        seen.add(journey_id)
        if not str(journey.get('title') or '').strip():
            issues.append(f'{journey_id} missing title')
        if journey.get('status') not in ALLOWED_JOURNEY_STATUSES:
            issues.append(f'{journey_id} has invalid status')
        if journey.get('status') == 'active':
            if not journey.get('steps'):
                issues.append(f'{journey_id} missing steps')
            if not journey.get('linked_acceptance_criteria'):
                issues.append(f'{journey_id} missing linked AC')
            if journey.get('verification_layer') not in ALLOWED_JOURNEY_LAYERS:
                issues.append(f'{journey_id} missing valid verification layer')
    if issues:
        raise ValueError('journey contract invalid: ' + '; '.join(issues))


def _journey_table_rows(markdown: str) -> list[dict[str, str]]:
    lines = markdown.splitlines()
    rows: list[dict[str, str]] = []
    for index, line in enumerate(lines):
        if not _is_table_line(line):
            continue
        header = _split_table_line(line)
        normalized = [_normalize_header(cell) for cell in header]
        if not _looks_like_journey_header(normalized):
            continue
        if index + 1 >= len(lines) or not _is_separator_row(lines[index + 1]):
            continue
        cursor = index + 2
        while cursor < len(lines) and _is_table_line(lines[cursor]):
            cells = _split_table_line(lines[cursor])
            if len(cells) >= len(header):
                rows.append({
                    normalized[column_index]: cells[column_index].strip()
                    for column_index in range(len(header))
                })
            cursor += 1
    return rows


def _looks_like_journey_header(headers: list[str]) -> bool:
    header_set = set(headers)
    return (
        _has_any_header(header_set, JOURNEY_ID_HEADERS)
        and _has_any_header(header_set, JOURNEY_TITLE_HEADERS)
        and _has_any_header(header_set, JOURNEY_AC_HEADERS)
        and _has_any_header(header_set, JOURNEY_LAYER_HEADERS)
    )


def _has_any_header(header_set: set[str], aliases: tuple[str, ...]) -> bool:
    return any(alias in header_set for alias in aliases)


def _normalize_header(value: str) -> str:
    return re.sub(r'\s+', ' ', value.strip().lower().replace('`', ''))


def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith('|') and stripped.endswith('|')


def _is_separator_row(line: str) -> bool:
    cells = _split_table_line(line)
    return bool(cells) and all(re.fullmatch(r':?-{3,}:?', cell.strip()) for cell in cells)


def _split_table_line(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip('|').split('|')]


def _first_value(row: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and value.strip():
            return value.strip()
    return None


def _split_steps(value: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r'\s*(?:->|→|;|；|<br\s*/?>)\s*', value)
        if part.strip()
    ]


def _ids_from_text(value: str, pattern: str) -> list[str]:
    ids: list[str] = []
    for match in re.finditer(pattern, value, flags=re.IGNORECASE):
        found = match.group(0)
        if found not in ids:
            ids.append(found)
    return ids


def _journey_contract_path(artifacts_dir: Path, state: dict[str, Any]) -> Path:
    raw_path = str(state.get('journeyContractPath') or '').strip()
    if raw_path:
        return Path(raw_path)
    return artifacts_dir / 'journeys' / 'journeys.json'


def _load_journey_contract(state: dict[str, Any], artifacts_dir: Path) -> dict[str, Any]:
    path = _journey_contract_path(artifacts_dir, state)
    if not path.exists():
        return {}
    return _load_json_object(path)


def _load_journey_evidence_rows(state: dict[str, Any], artifacts_dir: Path) -> list[dict[str, Any]]:
    contract_path = _journey_contract_path(artifacts_dir, state)
    evidence_path = contract_path.parent / 'journey-evidence.json'
    if not evidence_path.exists():
        return []
    payload = _load_json_object(evidence_path)
    rows = payload.get('journey_evidence_rows')
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _active_journeys(contract: dict[str, Any]) -> list[dict[str, Any]]:
    journeys = contract.get('journeys')
    if not isinstance(journeys, list):
        return []
    return [
        journey for journey in journeys
        if isinstance(journey, dict) and journey.get('status') == 'active'
    ]


def _journey_contract_hash_issues(contract: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for label, path_key, hash_key in (
        ('requirements', 'requirements_gate_path', 'requirements_gate_hash'),
        ('unit plan', 'unit_plan_gate_path', 'unit_plan_gate_hash'),
    ):
        raw_path = str(contract.get(path_key) or '').strip()
        expected_hash = str(contract.get(hash_key) or '').strip()
        if not raw_path or not expected_hash:
            continue
        path = Path(raw_path)
        if not path.exists():
            issues.append(f'{label} gate path in journey contract is missing: {path}')
            continue
        actual_hash = hash_gate_body(gate_body(path.read_text(encoding='utf-8')))
        if actual_hash != expected_hash:
            issues.append(f'{label} gate hash in journey contract is stale')
    return issues


def _join_cell(value: Any) -> str:
    if isinstance(value, list):
        return ', '.join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip() if value is not None else ''


def _journey_test_case_mappings(state: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    mappings: dict[str, list[dict[str, Any]]] = {}
    for unit in state.get('units') or []:
        if not isinstance(unit, dict):
            continue
        for case in _unit_test_cases(unit):
            if not isinstance(case, dict):
                continue
            for journey_id in _journey_ids_from_case(case):
                mappings.setdefault(journey_id, []).append({'unit': unit, 'case': case})
    return mappings


def _journey_ids_from_case(case: dict[str, Any]) -> list[str]:
    raw = (
        case.get('journey_id')
        or case.get('journeyId')
        or case.get('journey')
        or case.get('journeys')
        or case.get('journey_ids')
        or case.get('journeyIds')
        or case.get('covers_journeys')
        or case.get('coversJourneys')
        or case.get('journey_refs')
        or case.get('journeyRefs')
    )
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if raw is None:
        return []
    text = str(raw)
    matched = _ids_from_text(text, r'(?<![A-Za-z0-9_-])J-[A-Za-z0-9_-]+')
    return matched or ([text.strip()] if text.strip() else [])


def _journey_mapping_issues(journey: dict[str, Any], mapping: dict[str, Any]) -> list[str]:
    unit = mapping['unit']
    case = mapping['case']
    case_id = _test_case_identifier(case) or 'unknown-test'
    unit_id = _unit_identifier(unit) or 'unknown-unit'
    prefix = f'test case {case_id} in unit {unit_id}'
    issues: list[str] = []

    case_ac = str(case.get('acceptance_criterion') or case.get('acceptanceCriterion') or '')
    linked_ac = [str(item) for item in journey.get('linked_acceptance_criteria') or []]
    if linked_ac and not any(ac in case_ac for ac in linked_ac):
        issues.append(f'{prefix} must reference one of linked ACs: {", ".join(linked_ac)}')

    command = _test_case_command(case)
    commands = [str(item).strip() for item in unit.get('verification_commands') or [] if str(item).strip()]
    if not command:
        issues.append(f'{prefix} missing executable command')
    elif command not in commands:
        issues.append(f'{prefix} command must appear in verification_commands')

    if not _test_case_fixture_or_setup(case):
        issues.append(f'{prefix} missing fixture or setup')

    if not _test_case_expected_assertion(case):
        issues.append(f'{prefix} missing expected assertion')

    journey_layer = str(journey.get('verification_layer') or '').strip().lower()
    case_layer = str(case.get('layer') or '').strip().lower()
    unit_level = str(unit.get('workflow_validation_level') or '').strip().lower()
    if journey_layer == 'e2e' and case_layer != 'e2e' and unit_level != 'closure':
        issues.append(f'{prefix} must be layer=e2e or belong to a closure unit')

    return issues


def _unit_identifier(unit: dict[str, Any]) -> str:
    return str(unit.get('id') or '')


def _test_case_identifier(case: dict[str, Any]) -> str:
    return str(case.get('id') or case.get('name') or '')


def _test_case_command(case: dict[str, Any]) -> str:
    return str(case.get('command') or '').strip()


def _test_case_fixture_or_setup(case: dict[str, Any]) -> str:
    return str(
        case.get('fixture')
        or case.get('test_data')
        or case.get('testData')
        or case.get('setup')
        or ''
    ).strip()


def _test_case_expected_assertion(case: dict[str, Any]) -> str:
    return str(case.get('expected') or case.get('expected_result') or case.get('expectedResult') or '').strip()


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        stripped = str(value).strip()
        if stripped and stripped not in result:
            result.append(stripped)
    return result
