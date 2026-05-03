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
