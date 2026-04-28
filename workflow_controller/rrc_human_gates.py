from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONFIRMATION_HEADING = '## Human Confirmation'
CONTROLLER_STATE_PATCH_HEADING = '## Controller State Patch'
ALLOWED_COVERAGE_STATUSES = {'partial', 'covered'}


@dataclass(frozen=True)
class GateCheck:
    approved: bool
    reason: str | None = None
    content_hash: str | None = None
    confirmed_by: str | None = None


def ensure_requirements_gate(state: dict[str, Any], approvals_dir: Path) -> Path:
    path = approvals_dir / 'requirements-and-acceptance.md'
    if not path.exists():
        write_gate_file(path, render_requirements_gate_body(state))
    return path


def render_requirements_gate_body(state: dict[str, Any]) -> str:
    return _requirements_body(state)


def ensure_unit_plan_gate(state: dict[str, Any], approvals_dir: Path) -> Path:
    path = approvals_dir / 'unit-plan.md'
    if not path.exists():
        write_gate_file(path, render_unit_plan_gate_body(state))
    return path


def render_unit_plan_gate_body(state: dict[str, Any]) -> str:
    return _unit_plan_body(state)


def apply_unit_plan_state_patch_from_gate(state: dict[str, Any], gate_path: Path) -> dict[str, Any]:
    patch = extract_unit_plan_state_patch(gate_path.read_text(encoding='utf-8'))
    return apply_unit_plan_state_patch(state, patch)


def migrate_unit_plan_gate_to_state_patch(state: dict[str, Any], gate_path: Path) -> bool:
    content = gate_path.read_text(encoding='utf-8')
    if CONTROLLER_STATE_PATCH_HEADING in gate_body(content):
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


def extract_unit_plan_state_patch(content: str) -> dict[str, Any]:
    body = gate_body(content)
    heading = re.search(r'(?im)^##+\s+Controller State Patch\s*$', body)
    if not heading:
        raise ValueError('Unit plan is missing ## Controller State Patch')

    section = body[heading.end():]
    next_heading = re.search(r'(?m)^##\s+', section)
    if next_heading:
        section = section[:next_heading.start()]

    fence = re.search(r'```(?:json)?\s*\n(.*?)\n```', section, flags=re.DOTALL | re.IGNORECASE)
    if not fence:
        raise ValueError('Controller State Patch must contain a fenced JSON object')

    try:
        patch = json.loads(fence.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f'Controller State Patch JSON is invalid: {exc.msg}') from exc

    if not isinstance(patch, dict):
        raise ValueError('Controller State Patch must be a JSON object')
    return patch


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
    preserved_ids: list[str] = []
    for item in coverage:
        extra_unit_ids = [unit_id for unit_id in item['units'] if unit_id not in declared_unit_ids]
        if not extra_unit_ids:
            continue
        if item['status'] != 'covered':
            raise ValueError(
                'objectiveCoverage may omit existing unit ids from units only for covered objectives: '
                f'{extra_unit_ids}'
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


def ensure_final_acceptance_gate(
    state: dict[str, Any],
    approvals_dir: Path,
    artifacts_dir: Path,
    force: bool = False,
) -> Path:
    path = approvals_dir / 'final-acceptance.md'
    if force or not path.exists():
        body = _final_acceptance_body(state, artifacts_dir)
        write_gate_file(path, body)
    elif '## Rejection Routing' not in gate_body(path.read_text(encoding='utf-8')):
        write_gate_file(path, _with_final_acceptance_rejection_routing(gate_body(path.read_text(encoding='utf-8'))))
    return path


def write_gate_file(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_body = body.rstrip() + '\n'
    content_hash = hash_gate_body(normalized_body)
    path.write_text(
        f"{normalized_body}\n"
        f"{CONFIRMATION_HEADING}\n\n"
        "Status: pending\n"
        "Confirmed by: \n"
        "Confirmed at: \n"
        f"Content hash: sha256:{content_hash}\n",
        encoding='utf-8',
    )


def approve_gate_file(path: Path, actor: str = 'human') -> None:
    content = path.read_text(encoding='utf-8')
    body = gate_body(content)
    content_hash = hash_gate_body(body)
    approved = (
        body.rstrip()
        + '\n\n'
        + f'{CONFIRMATION_HEADING}\n\n'
        + 'Status: approved\n'
        + f'Confirmed by: {actor}\n'
        + f'Confirmed at: {datetime.now(timezone.utc).isoformat()}\n'
        + f'Content hash: sha256:{content_hash}\n'
    )
    path.write_text(approved, encoding='utf-8')


def check_gate_file(path: Path) -> GateCheck:
    if not path.exists():
        return GateCheck(False, reason='missing')
    content = path.read_text(encoding='utf-8')
    fields = _confirmation_fields(content)
    body = gate_body(content)
    actual_hash = hash_gate_body(body)
    expected_hash = fields.get('content hash', '').removeprefix('sha256:')

    if fields.get('status', '').strip().lower() != 'approved':
        return GateCheck(False, reason='not_approved', content_hash=actual_hash)
    if expected_hash != actual_hash:
        return GateCheck(False, reason='stale', content_hash=actual_hash, confirmed_by=fields.get('confirmed by'))
    return GateCheck(True, content_hash=actual_hash, confirmed_by=fields.get('confirmed by'))


def gate_body(content: str) -> str:
    if CONFIRMATION_HEADING not in content:
        return content.rstrip() + '\n'
    return content.split(CONFIRMATION_HEADING, 1)[0].rstrip() + '\n'


def hash_gate_body(body: str) -> str:
    return hashlib.sha256((body.rstrip() + '\n').encode('utf-8')).hexdigest()


def _confirmation_fields(content: str) -> dict[str, str]:
    if CONFIRMATION_HEADING not in content:
        return {}
    block = content.split(CONFIRMATION_HEADING, 1)[1]
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        fields[key.strip().lower()] = value.strip()
    return fields


def _requirements_body(state: dict[str, Any]) -> str:
    unit = _current_unit(state)
    commands = unit.get('verification_commands') or state.get('verificationCommands') or []
    lines = [
        '# Requirements & Acceptance Confirmation',
        '',
        '## 1. Requirements',
        f"- Requested outcome: `{state.get('requestedOutcome')}`",
        f"- Feasible outcome: `{state.get('feasibleOutcome')}`",
        f"- Current unit: `{state.get('currentUnitId')}`",
        '',
        '## 2. User Journeys',
        '- Derived from current progress, findings, and Ralph plan context.',
        '- Review this section manually and add missing normal, abnormal, role, permission, retry, and persistence paths before approval.',
        '',
        '## 3. Acceptance Criteria',
    ]
    done_when = unit.get('done_when') or []
    if done_when:
        lines.extend(f'- {item}' for item in done_when)
    else:
        lines.append('- Target acceptance criteria from current context are satisfied.')
    lines.extend([
        '',
        '## 4. Test Strategy',
    ])
    if commands:
        lines.extend(f'- `{command}`' for command in commands)
    else:
        lines.append('- Add at least one verification command or explicit manual evidence before approval.')
    lines.extend([
        '',
        '## 5. Out of Scope',
    ])
    non_goals = unit.get('non_goals') or []
    if non_goals:
        lines.extend(f'- {item}' for item in non_goals)
    else:
        lines.append('- Do not expand scope beyond the requested target without updating this gate.')
    lines.extend([
        '',
        '## 6. Human Review Checklist',
        '- [ ] Requirements are accurate.',
        '- [ ] User journeys cover normal, abnormal, role, permission, retry, and persistence paths as applicable.',
        '- [ ] Acceptance criteria are sufficient to judge completion.',
        '- [ ] Test strategy is sufficient for the requested outcome.',
    ])
    return '\n'.join(lines) + '\n'


def _unit_plan_body(state: dict[str, Any]) -> str:
    lines = [
        '# Unit Plan Confirmation',
        '',
        '## Objective Coverage Matrix',
    ]
    for item in state.get('objectiveCoverage', []):
        units = ', '.join(item.get('units', []))
        lines.append(f"- `{item.get('status')}` {item.get('objective')} -> {units}")
    lines.extend([
        '',
        '## Units',
    ])
    for unit in state.get('units', []):
        lines.extend([
            f"### {unit.get('id')} - {unit.get('name', unit.get('id'))}",
            f"- Workflow validation level: `{unit.get('workflow_validation_level', 'fragment')}`",
            '- Scope:',
        ])
        scope = unit.get('scope') or []
        lines.extend(f'  - {item}' for item in scope) if scope else lines.append('  - Not specified')
        commands = unit.get('verification_commands') or []
        lines.append('- Verification commands:')
        lines.extend(f'  - `{command}`' for command in commands) if commands else lines.append('  - Not specified')
        lines.append('')
    lines.extend([
        '',
        CONTROLLER_STATE_PATCH_HEADING,
        '',
        '```json',
        json.dumps(_controller_state_patch(state), ensure_ascii=False, indent=2),
        '```',
        '',
        '## Human Review Checklist',
        '- [ ] Every objective maps to one or more units.',
        '- [ ] Every unit declares enough verification evidence.',
        '- [ ] Fragment units do not claim full scenario completion.',
        '- [ ] Closure units include functional/E2E closure evidence.',
    ])
    return '\n'.join(lines).rstrip() + '\n'


def _final_acceptance_body(state: dict[str, Any], artifacts_dir: Path) -> str:
    unit_id = state.get('currentUnitId') or 'unknown'
    unit_dir = artifacts_dir / str(unit_id)
    builder = _load_json_file(unit_dir / 'builder-summary.json')
    review = _load_json_file(unit_dir / 'review.json')
    verification = _load_json_file(unit_dir / 'verification.json')
    changed_files = _read_lines(unit_dir / 'changed-files.txt')
    lines = [
        '# Final Acceptance Confirmation',
        '',
        '## Result',
        f"- Current step: `{state.get('currentStep')}`",
        f"- Status: `{state.get('status')}`",
        f"- Current unit: `{unit_id}`",
        '',
        '## Coverage',
    ]
    for item in state.get('objectiveCoverage', []):
        units = ', '.join(item.get('units', []))
        lines.append(f"- `{item.get('status')}` {item.get('objective')} -> {units}")
    lines.extend([
        '',
        '## Evidence Summary',
    ])
    builder_summary = (builder.get('done_payload') or {}).get('summary') or builder.get('runner_status')
    if builder_summary:
        lines.append(f'- Builder: {builder_summary}')
    if changed_files:
        lines.append('- Changed files:')
        lines.extend(f'  - `{path}`' for path in changed_files[:20])
    if review:
        review_status = 'passed' if review.get('passed') else 'failed'
        lines.append(f'- Review: {review_status}')
        issues = review.get('issues') or []
        if issues:
            lines.append('- Review issues:')
            lines.extend(f"  - {issue.get('type', 'issue')}: {issue.get('message', issue)}" for issue in issues[:10])
    if verification:
        verification_status = 'passed' if verification.get('passed') else 'failed'
        lines.append(f'- Verification: {verification_status}')
        for result in verification.get('results') or []:
            command = result.get('command')
            if not command:
                continue
            result_status = 'passed' if result.get('ok') else 'failed'
            returncode = result.get('returncode')
            suffix = f' (exit {returncode})' if returncode not in {None, 0} else ''
            lines.append(f'  - `{command}` -> {result_status}{suffix}')
    lines.extend([
        '',
        '## Evidence Files',
    ])
    for name in [
        'builder-summary.json',
        'changed-files.txt',
        'refinement-summary.json',
        'review.json',
        'verification.json',
        'green-test.txt',
    ]:
        path = unit_dir / name
        if path.exists():
            lines.append(f'- `{path}`')
    lines.extend([
        '',
        '## Human Review Checklist',
        '- [ ] Actual result satisfies the approved acceptance criteria.',
        '- [ ] Known issues are accepted or documented.',
        '- [ ] Evidence files are sufficient for final acceptance.',
    ])
    return _with_final_acceptance_rejection_routing('\n'.join(lines) + '\n')


def _with_final_acceptance_rejection_routing(body: str) -> str:
    if '## Rejection Routing' in body:
        return body.rstrip() + '\n'
    lines = [
        body.rstrip(),
        '',
        '## Rejection Routing',
        'If final acceptance is rejected, select the human routing decision below. Multiple selections are allowed; requirements revision has highest priority.',
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.',
        '- [ ] Unit plan revision: unit scope or verification commands are wrong.',
        '- [ ] Implementation rework: approved requirements are correct; implementation needs changes.',
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.',
        '',
        '## Rejection Notes',
        'Describe the acceptance gap, missing evidence, or required scope change before choosing reject/rework.',
    ]
    return '\n'.join(lines) + '\n'


def _current_unit(state: dict[str, Any]) -> dict[str, Any]:
    current = state.get('currentUnitId')
    for unit in state.get('units', []):
        if unit.get('id') == current:
            return unit
    return {}


def _controller_state_patch(state: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {
        'currentUnitId': state.get('currentUnitId'),
        'objectiveCoverage': state.get('objectiveCoverage') or [],
        'units': state.get('units') or [],
    }
    if 'currentUnitNeedsUiDesign' in state:
        patch['currentUnitNeedsUiDesign'] = bool(state.get('currentUnitNeedsUiDesign'))
    return patch


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


def _markdown_section(content: str, heading_contains: str) -> str:
    lines = gate_body(content).splitlines()
    heading_lower = heading_contains.lower()
    start: int | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('##') and heading_lower in stripped.lower():
            start = index + 1
            break
    if start is None:
        return ''

    section: list[str] = []
    for line in lines[start:]:
        if line.strip().startswith('##'):
            break
        section.append(line)
    return '\n'.join(section)


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


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
        normalized_units.append(unit)
    return normalized_units


def _normalize_patch_coverage(raw_coverage: Any, unit_ids: set[str]) -> list[dict[str, Any]]:
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
