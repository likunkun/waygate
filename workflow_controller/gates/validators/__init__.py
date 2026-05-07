from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from workflow_controller.acceptance_obligations import (
    active_must_obligations,
    covered_obligation_ids_from_state_and_text,
)
from workflow_controller.gates.parsers import (
    ALLOWED_COVERAGE_STATUSES,
    CONTROLLER_STATE_PATCH_HEADING,
    _controller_state_patch,
    _find_controller_state_patch_heading,
    _markdown_section,
    _unit_test_cases,
    extract_unit_plan_state_patch,
    gate_body,
    write_gate_file,
)


VERIFICATION_EVIDENCE_SCHEMA_VERSION = 'v0.3.5'
VERIFICATION_EVIDENCE_ROW_FIELDS = {
    'unit_id',
    'test_case_id',
    'acceptance_criterion',
    'acceptance_obligations',
    'layer',
    'command',
    'manual_evidence',
    'expected',
    'status',
    'result_index',
    'returncode',
    'artifact_refs',
    'golden_path',
}
VERIFICATION_EVIDENCE_ROW_STATUSES = {'passed', 'failed', 'missing', 'manual'}


# ---------------------------------------------------------------------------
# Validators from rrc_validators.py (artifact validation)
# ---------------------------------------------------------------------------

def validate_required_artifacts(unit_dir: Path, filenames: list[str]) -> None:
    missing = [name for name in filenames if not (unit_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f'Missing required artifacts in {unit_dir}: {missing}')


def validate_review_verdict(review_path: Path) -> dict[str, Any]:
    review = _load_json(review_path)
    if 'passed' not in review:
        raise ValueError(f"Review verdict missing 'passed': {review_path}")
    return review


def validate_verification_verdict(verification_path: Path) -> dict[str, Any]:
    verification = _load_json(verification_path)
    if 'passed' not in verification:
        raise ValueError(f"Verification verdict missing 'passed': {verification_path}")
    return verification


def validate_verification_evidence_schema(verification_path: Path) -> dict[str, Any]:
    verification = _load_json(verification_path)
    if verification.get('evidence_schema_version') != VERIFICATION_EVIDENCE_SCHEMA_VERSION:
        raise ValueError(f'Verification evidence schema missing evidence_schema_version: {verification_path}')

    rows = verification.get('evidence_rows')
    if not isinstance(rows, list):
        raise ValueError(f'Verification evidence_rows must be a list: {verification_path}')

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f'Verification evidence row {index} must be an object: {verification_path}')
        missing_fields = sorted(VERIFICATION_EVIDENCE_ROW_FIELDS - set(row))
        if missing_fields:
            raise ValueError(
                f'Verification evidence row {index} missing field(s) {missing_fields}: {verification_path}'
            )
        if row.get('status') not in VERIFICATION_EVIDENCE_ROW_STATUSES:
            raise ValueError(f'Verification evidence row {index} has invalid status: {verification_path}')
        if not isinstance(row.get('acceptance_obligations'), list):
            raise ValueError(f'Verification evidence row {index} acceptance_obligations must be a list: {verification_path}')
        if not isinstance(row.get('artifact_refs'), list):
            raise ValueError(f'Verification evidence row {index} artifact_refs must be a list: {verification_path}')
        if not isinstance(row.get('golden_path'), bool):
            raise ValueError(f'Verification evidence row {index} golden_path must be a boolean: {verification_path}')
    return verification


def validate_simplifier_result(result_path: Path) -> dict[str, Any]:
    result = _load_json(result_path)
    if not isinstance(result, dict):
        raise ValueError(f'Simplifier result must be a JSON object: {result_path}')

    status = result.get('status')
    if status not in {'ok', 'changes_requested', 'failed', 'skipped'}:
        raise ValueError(f'Simplifier result has invalid status: {result_path}')

    mode = result.get('mode')
    if mode not in {'disabled', 'dry-run', 'role-runner', 'no-workspace'}:
        raise ValueError(f'Simplifier result has invalid mode: {result_path}')

    if not isinstance(result.get('changed_files'), list):
        raise ValueError(f'Simplifier result changed_files must be a list: {result_path}')
    if not isinstance(result.get('findings'), list):
        raise ValueError(f'Simplifier result findings must be a list: {result_path}')
    if not isinstance(result.get('runner_metadata'), dict):
        raise ValueError(f'Simplifier result runner_metadata must be an object: {result_path}')
    if 'generated_at' not in result:
        raise ValueError(f'Simplifier result missing generated_at: {result_path}')
    return result


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


# ---------------------------------------------------------------------------
# Unit plan validators (from rrc_human_gates.py)
# ---------------------------------------------------------------------------

def validate_unit_plan_test_strategy(
    requirements_path: Path,
    unit_plan_path: Path,
    state: dict[str, Any],
) -> None:
    if not requirements_path.exists():
        return
    required_layers = _required_test_layers(requirements_path.read_text(encoding='utf-8'))
    if not required_layers:
        return

    unit_plan_content = gate_body(unit_plan_path.read_text(encoding='utf-8')).lower()
    unit_state_content = json.dumps({
        'units': state.get('units') or [],
        'objectiveCoverage': state.get('objectiveCoverage') or [],
    }, ensure_ascii=False).lower()
    haystack = f'{unit_plan_content}\n{unit_state_content}'
    missing = [
        layer
        for layer in sorted(required_layers)
        if not _test_layer_is_covered(layer, haystack)
    ]
    if missing:
        raise ValueError(
            'unit plan does not cover approved test strategy layer(s): '
            + ', '.join(missing)
        )


def validate_unit_plan_test_case_coverage(
    unit_plan_path: Path,
    state: dict[str, Any],
) -> None:
    if not unit_plan_path.exists():
        return
    content = gate_body(unit_plan_path.read_text(encoding='utf-8'))
    gaps: list[str] = []
    for unit in state.get('units') or []:
        if not isinstance(unit, dict) or bool(unit.get('passes')):
            continue
        unit_id = str(unit.get('id') or 'unknown-unit')
        commands = [str(command) for command in unit.get('verification_commands') or []]
        test_cases = _unit_test_cases(unit)
        if test_cases:
            continue
        if _unit_plan_body_has_test_case_matrix_entry(content, unit_id):
            continue
        if commands and all(_is_static_verification_command(command) for command in commands):
            gaps.append(
                f'unit {unit_id} has only static verification commands; add test_cases or Test Case Matrix evidence'
            )
    if gaps:
        raise ValueError('unit plan test case coverage is incomplete: ' + '; '.join(gaps))


def validate_unit_plan_acceptance_obligation_coverage(
    unit_plan_path: Path,
    state: dict[str, Any],
) -> None:
    if not unit_plan_path.exists():
        return
    obligations = active_must_obligations(state)
    if not obligations:
        return
    content = gate_body(unit_plan_path.read_text(encoding='utf-8'))
    covered = covered_obligation_ids_from_state_and_text(state, content)
    missing = [
        obligation
        for obligation in obligations
        if str(obligation.get('id') or '').upper() not in covered
    ]
    if missing:
        summary = ', '.join(
            f"{obligation.get('id')} {obligation.get('title', '')}".strip()
            for obligation in missing
        )
        raise ValueError('missing Acceptance Obligation coverage: ' + summary)


def validate_unit_plan_design_architecture_traceability(
    requirements_path: Path,
    unit_plan_path: Path,
    state: dict[str, Any],
) -> None:
    if not requirements_path.exists() or not unit_plan_path.exists():
        return
    requirements_content = gate_body(requirements_path.read_text(encoding='utf-8'))
    required_trace = _requirements_design_architecture_traceability(requirements_content)
    if not required_trace:
        return

    missing: list[str] = []
    for unit in state.get('units') or []:
        if not isinstance(unit, dict) or bool(unit.get('passes')):
            continue
        unit_id = str(unit.get('id') or 'unknown-unit')
        for case in _unit_test_cases(unit):
            if not isinstance(case, dict):
                continue
            ac_ids = _requirements_ac_ids_in_text(
                str(case.get('acceptance_criterion') or case.get('acceptanceCriterion') or '')
            )
            for ac_id in sorted(ac_ids & set(required_trace)):
                required = required_trace[ac_id]
                product_refs = _trace_refs_from_case(
                    case,
                    'product_design_refs',
                    'productDesignRefs',
                    'product_design_ref',
                    'productDesignRef',
                    'design_refs',
                    'designRefs',
                )
                architecture_refs = _trace_refs_from_case(
                    case,
                    'technical_architecture_refs',
                    'technicalArchitectureRefs',
                    'technical_architecture_ref',
                    'technicalArchitectureRef',
                    'architecture_refs',
                    'architectureRefs',
                )
                product_refs_ok = required['product_design_refs'].issubset(product_refs)
                architecture_refs_ok = required['technical_architecture_refs'].issubset(architecture_refs)
                if not product_refs_ok or not architecture_refs_ok:
                    missing.append(
                        f'unit {unit_id} test case {case.get("id", "unknown-test")} for {ac_id} '
                        'missing design/architecture traceability'
                    )
    if missing:
        raise ValueError('unit plan design/architecture traceability is incomplete: ' + '; '.join(missing))


def validate_requirements_acceptance_quality(
    requirements_path: Path,
    state: dict[str, Any],
) -> None:
    if not requirements_path.exists():
        return

    content = gate_body(requirements_path.read_text(encoding='utf-8'))
    ac_ids = _requirements_acceptance_criterion_ids(content)
    ac_layers = _requirements_acceptance_criterion_layers(content)
    missing_layers = [
        ac_id
        for ac_id in sorted(ac_ids)
        if ac_id not in ac_layers
    ]

    issues: list[str] = []
    if missing_layers:
        issues.append(
            ', '.join(f'{ac_id} missing verification layer' for ac_id in missing_layers)
            + '; add one of unit, functional, integration, e2e, or manual in the AC line '
            + 'or Requirements Traceability Matrix'
        )

    obligations = active_must_obligations(state)
    if obligations:
        trace = _requirements_obligation_traceability(content)
        missing_obligations = [
            obligation
            for obligation in obligations
            if str(obligation.get('id') or '').upper() not in trace
        ]
        if missing_obligations:
            summary = ', '.join(
                f"{obligation.get('id')} {obligation.get('title', '')}".strip()
                for obligation in missing_obligations
            )
            issues.append(
                'missing Acceptance Obligation requirements mapping: '
                + summary
                + '; map every active must AO to an AC, or mark it deferred, '
                + 'rejected, or out_of_scope with a reason'
            )

    if _requirements_has_design_architecture_matrix(content):
        design_architecture_trace = _requirements_design_architecture_traceability(content)
        missing_design_architecture = [
            ac_id
            for ac_id in sorted(ac_ids)
            if ac_id not in design_architecture_trace
            or not design_architecture_trace[ac_id]['product_design_refs']
            or not design_architecture_trace[ac_id]['technical_architecture_refs']
        ]
        if missing_design_architecture:
            issues.append(
                ', '.join(
                    f'{ac_id} missing design/architecture traceability'
                    for ac_id in missing_design_architecture
                )
                + '; add Product Design Ref and Technical Architecture Ref for every AC'
            )

    if issues:
        raise ValueError('; '.join(issues))



def validate_unit_plan_golden_path(state: dict[str, Any]) -> None:
    missing: list[str] = []
    for unit in state.get('units') or []:
        if not isinstance(unit, dict) or bool(unit.get('passes')):
            continue
        if not _unit_requires_golden_path(unit):
            continue
        unit_id = str(unit.get('id') or 'unknown-unit')
        commands = [str(command).strip() for command in unit.get('verification_commands') or [] if str(command).strip()]
        golden_cases = [case for case in _unit_test_cases(unit) if _is_golden_path_case(case)]
        if not golden_cases:
            missing.append(f'unit {unit_id} requires a golden_path test case before final acceptance')
            continue
        valid_case = next((case for case in golden_cases if _golden_path_case_is_executable(case, commands)), None)
        if valid_case is None:
            missing.append(
                f'unit {unit_id} golden_path test case must include command, fixture, concrete expected result, '
                'and that command must appear in verification_commands'
            )
    if missing:
        raise ValueError('unit plan golden_path coverage is incomplete: ' + '; '.join(missing))



def validate_unit_plan_verification_environment(state: dict[str, Any]) -> None:
    missing: list[str] = []
    state_env_keys = _verification_env_keys(state)
    for unit in state.get('units') or []:
        if not isinstance(unit, dict):
            continue
        unit_id = str(unit.get('id') or 'unknown-unit')
        env_keys = state_env_keys | _verification_env_keys(unit)
        commands = unit.get('verification_commands') or []
        for command in commands:
            command_text = str(command)
            for required_key in sorted(_required_env_keys_for_verification_command(command_text)):
                if required_key in env_keys or _command_sets_env(command_text, required_key):
                    continue
                missing.append(
                    f'unit {unit_id} command requires {required_key}; '
                    f'add {required_key} to verification_env or inline it in the command: {command_text}'
                )
    if missing:
        raise ValueError('unit plan verification_env is incomplete: ' + '; '.join(missing))


def apply_unit_plan_state_patch_from_gate(state: dict[str, Any], gate_path: Path) -> dict[str, Any]:
    patch = extract_unit_plan_state_patch(gate_path.read_text(encoding='utf-8'))
    return apply_unit_plan_state_patch(state, patch)


def migrate_unit_plan_gate_to_state_patch(state: dict[str, Any], gate_path: Path) -> bool:
    content = gate_path.read_text(encoding='utf-8')
    if _find_controller_state_patch_heading(gate_body(content)):
        return False

    backup_path = gate_path.with_suffix('.md.before-controller-state-patch')
    if not backup_path.exists():
        backup_path.write_text(content, encoding='utf-8')

    body = gate_body(content).rstrip()
    migrated_body = (
        body
        + '\n\n'
        + CONTROLLER_STATE_PATCH_HEADING
        + '\n\n```json\n'
        + json.dumps(_controller_state_patch(state), ensure_ascii=False, indent=2)
        + '\n```\n'
    )
    write_gate_file(gate_path, migrated_body)
    return True


def apply_unit_plan_state_patch(state: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    if 'units' not in patch or 'objectiveCoverage' not in patch:
        raise ValueError('Controller State Patch must include units and objectiveCoverage')

    normalized_units = _normalize_patch_units(patch.get('units'), state)
    unit_ids = {unit['id'] for unit in normalized_units}
    previous_units = {
        str(unit.get('id')): unit
        for unit in state.get('units', [])
        if isinstance(unit, dict) and unit.get('id')
    }
    normalized_coverage = _normalize_patch_coverage(
        patch.get('objectiveCoverage'),
        unit_ids | set(previous_units),
    )
    preserved_units = _preserved_existing_units_from_coverage(
        normalized_coverage,
        declared_unit_ids=unit_ids,
        previous_units=previous_units,
    )

    explicit_current_unit = patch.get('currentUnitId')
    if explicit_current_unit:
        current_unit_id = str(explicit_current_unit).strip()
        if current_unit_id not in unit_ids:
            raise ValueError(f'currentUnitId is not declared in units: {current_unit_id}')
    else:
        existing_current = str(state.get('currentUnitId') or '').strip()
        current_unit_id = existing_current if existing_current in unit_ids else normalized_units[0]['id']

    next_state = dict(state)
    next_state['units'] = [*normalized_units, *preserved_units]
    next_state['objectiveCoverage'] = normalized_coverage
    next_state['currentUnitId'] = current_unit_id
    if 'currentUnitNeedsUiDesign' in patch:
        next_state['currentUnitNeedsUiDesign'] = bool(patch['currentUnitNeedsUiDesign'])
    else:
        current_unit = next((unit for unit in normalized_units if unit.get('id') == current_unit_id), {})
        if current_unit.get('ui_design_required') is True:
            next_state['currentUnitNeedsUiDesign'] = True
    return next_state


def _preserved_existing_units_from_coverage(
    coverage: list[dict[str, Any]],
    *,
    declared_unit_ids: set[str],
    previous_units: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    completed_existing_ids = {
        unit_id
        for unit_id, unit in previous_units.items()
        if bool(unit.get('passes'))
    }
    completed_existing_ids.update(
        unit_id
        for item in coverage
        if item['status'] == 'covered'
        for unit_id in item['units']
        if unit_id in previous_units
    )

    preserved_ids: list[str] = []
    for item in coverage:
        extra_unit_ids = [unit_id for unit_id in item['units'] if unit_id not in declared_unit_ids]
        if not extra_unit_ids:
            continue
        if item['status'] != 'covered':
            unfinished_extra_unit_ids = [
                unit_id
                for unit_id in extra_unit_ids
                if unit_id not in completed_existing_ids
            ]
            if unfinished_extra_unit_ids:
                raise ValueError(
                    'partial objectiveCoverage may omit only completed existing unit ids from units; '
                    f'declare unfinished unit ids in units: {unfinished_extra_unit_ids}'
                )
        for unit_id in extra_unit_ids:
            if unit_id not in preserved_ids:
                preserved_ids.append(unit_id)

    preserved_units: list[dict[str, Any]] = []
    for unit_id in preserved_ids:
        unit = dict(previous_units[unit_id])
        unit['id'] = unit_id
        unit['passes'] = True
        preserved_units.append(unit)
    return preserved_units


def _normalize_patch_units(raw_units: Any, state: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(raw_units, list) or not raw_units:
        raise ValueError('Controller State Patch units must be a non-empty list')

    previous_passes = {
        str(unit.get('id')): bool(unit.get('passes'))
        for unit in state.get('units', [])
        if isinstance(unit, dict) and unit.get('id')
    }
    normalized_units: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_unit in raw_units:
        if not isinstance(raw_unit, dict):
            raise ValueError('Each Controller State Patch unit must be an object')
        unit_id = str(raw_unit.get('id') or '').strip()
        if not unit_id:
            raise ValueError('Each Controller State Patch unit must include id')
        if unit_id in seen:
            raise ValueError(f'Duplicate unit id in Controller State Patch: {unit_id}')
        seen.add(unit_id)

        unit = dict(raw_unit)
        unit['id'] = unit_id
        if 'passes' not in unit:
            unit['passes'] = previous_passes.get(unit_id, False)
        if 'verification_commands' in unit and not isinstance(unit['verification_commands'], list):
            raise ValueError(f'unit {unit_id} verification_commands must be a list')
        if 'test_cases' in unit and not isinstance(unit['test_cases'], list):
            raise ValueError(f'unit {unit_id} test_cases must be a list')
        if 'testCases' in unit and not isinstance(unit['testCases'], list):
            raise ValueError(f'unit {unit_id} testCases must be a list')
        normalized_units.append(unit)
    return normalized_units


def _normalize_patch_coverage(
    raw_coverage: Any,
    unit_ids: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw_coverage, list) or not raw_coverage:
        raise ValueError('Controller State Patch objectiveCoverage must be a non-empty list')

    normalized_coverage: list[dict[str, Any]] = []
    for raw_item in raw_coverage:
        if not isinstance(raw_item, dict):
            raise ValueError('Each Controller State Patch objectiveCoverage item must be an object')
        objective = str(raw_item.get('objective') or '').strip()
        if not objective:
            raise ValueError('Each Controller State Patch objectiveCoverage item must include objective')
        units = raw_item.get('units')
        if not isinstance(units, list) or not units:
            raise ValueError(f'objectiveCoverage for {objective} must include one or more units')
        normalized_units = [str(unit_id).strip() for unit_id in units if str(unit_id).strip()]
        unknown_units = [unit_id for unit_id in normalized_units if unit_id not in unit_ids]
        if unknown_units:
            raise ValueError(f'objectiveCoverage references unknown unit ids: {unknown_units}')
        status = str(raw_item.get('status') or 'partial').strip()
        if status not in ALLOWED_COVERAGE_STATUSES:
            raise ValueError(f'objectiveCoverage status must be one of {sorted(ALLOWED_COVERAGE_STATUSES)}')
        item = dict(raw_item)
        item['objective'] = objective
        item['units'] = normalized_units
        item['status'] = status
        normalized_coverage.append(item)
    return normalized_coverage


_REQUIREMENTS_RESOLUTION_STATUSES = {'deferred', 'rejected', 'out_of_scope'}


def _requirements_has_design_architecture_matrix(content: str) -> bool:
    return bool(_markdown_section(content, 'Design/Architecture Traceability Matrix'))


def _requirements_design_architecture_traceability(content: str) -> dict[str, dict[str, set[str]]]:
    section = _markdown_section(content, 'Design/Architecture Traceability Matrix')
    trace: dict[str, dict[str, set[str]]] = {}
    if not section:
        return trace

    for line in section.splitlines():
        cells = _markdown_table_cells(line)
        if len(cells) < 3:
            continue
        ac_ids = _requirements_ac_ids_in_text(cells[0])
        if not ac_ids:
            continue
        product_design_refs = _requirements_trace_refs_from_cell(cells[1])
        technical_architecture_refs = _requirements_trace_refs_from_cell(cells[2])
        for ac_id in ac_ids:
            item = trace.setdefault(
                ac_id,
                {'product_design_refs': set(), 'technical_architecture_refs': set()},
            )
            item['product_design_refs'].update(product_design_refs)
            item['technical_architecture_refs'].update(technical_architecture_refs)
    return trace


def _requirements_acceptance_criterion_ids(content: str) -> set[str]:
    return {match.group(0).upper() for match in re.finditer(r'\bAC-\d+(?:[-.]\d+)*\b', content, re.IGNORECASE)}


def _requirements_acceptance_criterion_layers(content: str) -> dict[str, str]:
    layers: dict[str, str] = {}
    for line in content.splitlines():
        ac_ids = _requirements_ac_ids_in_text(line)
        if not ac_ids:
            continue
        layer = _requirements_verification_layer_from_line(line)
        if not layer:
            continue
        for ac_id in ac_ids:
            layers.setdefault(ac_id, layer)
    return layers


def _requirements_obligation_traceability(content: str) -> set[str]:
    traceable: set[str] = set()
    for line in content.splitlines():
        ao_ids = _requirements_ao_ids_in_text(line)
        if not ao_ids:
            continue
        if _requirements_ac_ids_in_text(line):
            traceable.update(ao_ids)
            continue
        if _requirements_line_resolves_obligation(line):
            traceable.update(ao_ids)
    return traceable


def _requirements_ac_ids_in_text(text: str) -> set[str]:
    return {match.group(0).upper() for match in re.finditer(r'\bAC-\d+(?:[-.]\d+)*\b', text, re.IGNORECASE)}


def _requirements_ao_ids_in_text(text: str) -> set[str]:
    return {_normalize_requirements_ao_id(match.group(0)) for match in re.finditer(r'\bAO-\d+\b', text, re.IGNORECASE)}


def _normalize_requirements_ao_id(value: str) -> str:
    match = re.fullmatch(r'AO-(\d+)', str(value or '').strip(), flags=re.IGNORECASE)
    if not match:
        return str(value or '').strip().upper()
    digits = match.group(1)
    return f'AO-{int(digits):0{max(3, len(digits))}d}'


def _requirements_verification_layer_from_line(line: str) -> str | None:
    if _is_markdown_table_separator(line):
        return None
    cells = _markdown_table_cells(line)
    if cells:
        for cell in cells:
            layer = _normalize_requirements_verification_layer(cell)
            if layer:
                return layer

    structured_patterns = [
        r'\bverification(?:\s+layer)?\s*[:：=]\s*([A-Za-z0-9_-]+)\b',
        r'\b验证(?:层级|层|方式)?\s*[:：]\s*([A-Za-z0-9_-]+|单元|集成|端到端|人工)\b',
        r'\[\s*verification\s*:\s*([A-Za-z0-9_-]+)\s*\]',
        r'\(\s*(unit|functional|integration|e2e|manual)\s*\)',
    ]
    for pattern in structured_patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if not match:
            continue
        layer = _normalize_requirements_verification_layer(match.group(1))
        if layer:
            return layer

    leading_layer = re.search(
        r'^\s*(?:[-*+]\s*)?(unit|functional|integration|e2e|manual)\b',
        line,
        re.IGNORECASE,
    )
    if leading_layer:
        return _normalize_requirements_verification_layer(leading_layer.group(1))
    return None


def _normalize_requirements_verification_layer(value: str) -> str | None:
    normalized = re.sub(r'[\s`*_，。:：;；]+', ' ', str(value).strip().lower()).strip()
    if not normalized:
        return None
    aliases = {
        'unit': ('unit', 'unit test', 'unit tests', '单元', '单元测试'),
        'functional': ('functional', 'api', 'api test', 'api tests', '功能', '功能测试', '接口', '接口测试'),
        'integration': ('integration', 'integration test', 'integration tests', '集成', '集成测试'),
        'e2e': ('e2e', 'end-to-end', 'end to end', 'playwright', 'browser', '端到端', '浏览器'),
        'manual': ('manual', 'manual acceptance', 'uat', '人工', '人工验收', '手工'),
    }
    for layer, candidates in aliases.items():
        if normalized in candidates:
            return layer
    for layer, candidates in aliases.items():
        if any(re.search(rf'\b{re.escape(candidate)}\b', normalized) for candidate in candidates if re.match(r'^[a-z0-9 -]+$', candidate)):
            return layer
    return None


def _requirements_line_resolves_obligation(line: str) -> bool:
    normalized = line.lower()
    if not any(status in normalized for status in _REQUIREMENTS_RESOLUTION_STATUSES):
        return False
    cells = _markdown_table_cells(line)
    if cells:
        return any(_requirements_resolution_reason_is_meaningful(cell) for cell in cells)
    parts = re.split(r'\b(?:deferred|rejected|out_of_scope)\b', line, maxsplit=1, flags=re.IGNORECASE)
    return len(parts) == 2 and _requirements_resolution_reason_is_meaningful(parts[1])


def _requirements_resolution_reason_is_meaningful(text: str) -> bool:
    stripped = str(text).strip()
    if not stripped:
        return False
    lowered = stripped.lower().strip('`*_ -')
    if lowered in {
        'ao',
        'ac',
        'status',
        'verification layer',
        'evidence/reason',
        'reason',
        'deferred',
        'rejected',
        'out_of_scope',
        'manual',
        'unit',
        'functional',
        'integration',
        'e2e',
        'pending',
        'todo',
        'tbd',
        'n/a',
    }:
        return False
    if _requirements_ao_ids_in_text(stripped) or _requirements_ac_ids_in_text(stripped):
        return False
    if _requirements_resolution_reason_is_layer_only(stripped):
        return False
    return True


def _requirements_resolution_reason_is_layer_only(text: str) -> bool:
    normalized = re.sub(r'[\s`*_，。:：;；]+', ' ', str(text).strip().lower()).strip()
    if not normalized:
        return False
    layer_aliases = {
        'unit',
        'unit test',
        'unit tests',
        '单元',
        '单元测试',
        'functional',
        'api',
        'api test',
        'api tests',
        '功能',
        '功能测试',
        '接口',
        '接口测试',
        'integration',
        'integration test',
        'integration tests',
        '集成',
        '集成测试',
        'e2e',
        'end-to-end',
        'end to end',
        'playwright',
        'browser',
        '端到端',
        '浏览器',
        'manual',
        'manual acceptance',
        'uat',
        '人工',
        '人工验收',
        '手工',
    }
    return normalized in layer_aliases


def _requirements_trace_refs_from_cell(value: str) -> set[str]:
    refs: set[str] = set()
    for part in re.split(r'(?:<br\s*/?>|[,，;；、])', str(value), flags=re.IGNORECASE):
        ref = _normalize_requirements_trace_ref(part)
        if not _requirements_trace_ref_is_meaningful(ref):
            continue
        stable_ids = _requirements_trace_ref_ids(ref)
        refs.update(stable_ids or {ref})
    return refs


def _normalize_requirements_trace_ref(value: str) -> str:
    ref = str(value or '').strip().strip('`*_')
    ref = ref.replace('`', '')
    ref = re.sub(r'\s*/\s*', ' / ', ref)
    ref = re.sub(r'\s+', ' ', ref).strip()
    return ref


def _requirements_trace_ref_ids(value: str) -> set[str]:
    return {
        match.group(0).upper()
        for match in re.finditer(r'\b(?:PD|PDR|TA|TAR)(?:-[A-Za-z0-9_.]+)+\b', value, re.IGNORECASE)
    }


def _trace_refs_from_case(case: dict[str, Any], *keys: str) -> set[str]:
    refs: set[str] = set()
    for key in keys:
        value = case.get(key)
        if isinstance(value, list):
            for item in value:
                refs.update(_requirements_trace_refs_from_cell(str(item)))
        elif value is not None:
            refs.update(_requirements_trace_refs_from_cell(str(value)))
    return refs


def _requirements_trace_ref_is_meaningful(value: str) -> bool:
    normalized = re.sub(r'\s+', ' ', value.strip().lower())
    if not normalized:
        return False
    if normalized in {
        '-',
        'n/a',
        'na',
        'none',
        'pending',
        'todo',
        'tbd',
        '待补',
        '未指定',
        '无',
        '无 active must ao',
        'product design ref',
        'technical architecture ref',
        '设计引用',
        '架构引用',
    }:
        return False
    return True


def _markdown_table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith('|') or '|' not in stripped[1:]:
        return []
    if _is_markdown_table_separator(stripped):
        return []
    return [cell.strip() for cell in stripped.strip('|').split('|')]


def _is_markdown_table_separator(line: str) -> bool:
    stripped = line.strip()
    return bool(re.fullmatch(r'\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?', stripped))


def _required_test_layers(content: str) -> set[str]:
    section = _markdown_section(content, 'Test Strategy').lower()
    if not section:
        return set()
    layers: set[str] = set()
    patterns = {
        'unit': ('unit test', 'unit tests'),
        'functional': ('functional', 'api test', 'api tests'),
        'integration': ('integration', 'integrated'),
        'e2e': ('e2e', 'end-to-end', 'end to end', 'playwright', 'browser', 'manual acceptance', 'uat'),
    }
    for layer, needles in patterns.items():
        if any(needle in section for needle in needles):
            layers.add(layer)
    return layers


def _test_layer_is_covered(layer: str, haystack: str) -> bool:
    coverage_terms = {
        'unit': ('unit', 'pytest', 'unittest'),
        'functional': ('functional', 'api', 'route', 'request'),
        'integration': ('integration', 'database', 'db', 'import', 'export'),
        'e2e': ('e2e', 'end-to-end', 'end to end', 'playwright', 'browser', 'manual acceptance', 'uat'),
    }
    return any(term in haystack for term in coverage_terms[layer])


def _unit_plan_body_has_test_case_matrix_entry(content: str, unit_id: str) -> bool:
    if not unit_id:
        return False
    matrix_match = re.search(
        r'(?ims)^##+\s+.*(?:Test Case Matrix|测试用例矩阵).*$([\s\S]*?)(?=^##+\s+|\Z)',
        content,
    )
    if not matrix_match:
        return False
    return unit_id.lower() in matrix_match.group(1).lower()


def _is_static_verification_command(command: str) -> bool:
    lowered = command.lower().replace('--noemit', '--noemit')
    normalized = re.sub(r'\s+', ' ', lowered).strip()
    static_patterns = [
        'tsc --noemit',
        'tsc --no-emit',
        'eslint',
        'biome check',
        'prettier',
        'typecheck',
        'type-check',
        'lint',
    ]
    if any(pattern in normalized for pattern in static_patterns):
        return True
    return re.search(r'\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:lint|typecheck|type-check)\b', normalized) is not None


def _unit_requires_golden_path(unit: dict[str, Any]) -> bool:
    validation_level = str(unit.get('workflow_validation_level') or '').strip().lower()
    if validation_level == 'closure':
        return True
    test_cases = _unit_test_cases(unit)
    if any(str(case.get('layer') or '').strip().lower() == 'e2e' for case in test_cases if isinstance(case, dict)):
        return True
    commands = ' '.join(str(command).lower() for command in unit.get('verification_commands') or [])
    return 'playwright' in commands or 'e2e' in commands



def _is_golden_path_case(case: Any) -> bool:
    return isinstance(case, dict) and case.get('golden_path') is True



def _golden_path_case_is_executable(case: dict[str, Any], verification_commands: list[str]) -> bool:
    command = str(case.get('command') or '').strip()
    fixture = str(case.get('fixture') or case.get('test_data') or case.get('testData') or '').strip()
    expected = str(case.get('expected') or case.get('expected_result') or case.get('expectedResult') or '').strip()
    if not command or not fixture or _expected_is_weak(expected):
        return False
    return any(command == candidate or command in candidate or candidate in command for candidate in verification_commands)



def _expected_is_weak(expected: str) -> bool:
    if not expected:
        return True
    normalized = re.sub(r'\s+', '', expected.lower())
    weak_terms = {
        '页面正常',
        '页面正常渲染',
        '渲染成功',
        '无报错',
        '没有报错',
        '截图留存',
        '截图已上传',
        '人工确认',
        '流程正常',
    }
    return normalized in weak_terms



def _verification_env_keys(payload: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for field in ('verification_env', 'verificationEnv'):
        value = payload.get(field)
        if isinstance(value, dict):
            keys.update(str(key).strip() for key in value if str(key).strip())
    return keys


def _required_env_keys_for_verification_command(command: str) -> set[str]:
    lowered = command.lower()
    required: set[str] = set()
    if 'playwright' in lowered or 'prisma' in lowered:
        required.add('DATABASE_URL')
    if re.search(r'\bDATABASE_URL\b', command):
        required.add('DATABASE_URL')
    return required


def _command_sets_env(command: str, key: str) -> bool:
    return re.search(rf'(?:^|[;&\s])(?:export\s+)?{re.escape(key)}\s*=', command) is not None
