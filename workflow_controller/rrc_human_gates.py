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
CONTROLLER_STATE_PATCH_HEADING_ALIASES = (
    'Controller State Patch',
    '控制器状态补丁',
)
ALLOWED_COVERAGE_STATUSES = {'partial', 'covered'}

FINAL_ACCEPTANCE_REJECTION_ROUTES = (
    ('requirements', '需求变更', '已批准需求不完整或存在错误。'),
    ('defect_fix', '验收缺陷修复', '已批准需求正确，最终验收发现已完成工作存在缺陷。'),
    ('unit_plan', 'Unit Plan 修订', '单元范围或验证命令不正确。'),
    ('implementation', '实现返工', '已批准需求正确，但实现需要修改。'),
    ('blocked', '阻塞', '由于环境、数据、权限或证据缺失，暂时无法判断。'),
)
FINAL_ACCEPTANCE_REJECTION_ROUTE_ALIASES = {
    'requirements': ('需求变更', 'Requirements revision'),
    'defect_fix': ('验收缺陷修复', 'Defect fix'),
    'unit_plan': ('Unit Plan 修订', 'Unit plan revision'),
    'implementation': ('实现返工', 'Implementation rework'),
    'blocked': ('阻塞', 'Blocked'),
}


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
    heading = _find_controller_state_patch_heading(body)
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


def _find_controller_state_patch_heading(body: str) -> re.Match[str] | None:
    names = '|'.join(re.escape(name) for name in CONTROLLER_STATE_PATCH_HEADING_ALIASES)
    return re.search(rf'(?im)^##+\s+(?:{names})\s*$', body)


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
    else:
        body = gate_body(path.read_text(encoding='utf-8'))
        normalized = normalize_final_acceptance_rejection_routing(body)
        if normalized != body:
            write_gate_file(path, normalized)
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
        '# 需求与验收确认',
        '',
        '## 1. 需求',
        f"- 请求目标：`{state.get('requestedOutcome')}`",
        f"- 可行目标：`{state.get('feasibleOutcome')}`",
        f"- 当前单元：`{state.get('currentUnitId')}`",
        '',
        '## 2. 用户旅程',
        '- 根据当前进度、发现记录和 Ralph 计划上下文整理。',
        '- 确认前请人工补齐正常、异常、角色、权限、重试和数据持久化路径。',
        '',
        '## 3. 验收标准',
    ]
    done_when = unit.get('done_when') or []
    if done_when:
        lines.extend(f'- {item}' for item in done_when)
    else:
        lines.append('- 当前上下文中的目标验收标准均已满足。')
    lines.extend([
        '',
        '## 4. 测试策略（Test Strategy）',
    ])
    if commands:
        lines.extend(f'- `{command}`' for command in commands)
    else:
        lines.append('- 确认前至少补充一个验证命令或明确的人工证据。')
    lines.extend([
        '',
        '## 5. 范围外',
    ])
    non_goals = unit.get('non_goals') or []
    if non_goals:
        lines.extend(f'- {item}' for item in non_goals)
    else:
        lines.append('- 未更新本确认门禁前，不扩展到请求目标之外。')
    lines.extend([
        '',
        '## 6. 产品设计概要',
        '- **主要用户流程**：补充用户完成核心功能的关键步骤，包括正常路径和主要异常路径。',
        '- **关键页面/状态**：补充关键界面、关键系统状态，或无 UI 场景下的 API/CLI 输出示意。',
        '- **验收示意**：补充“什么样算完成”的直观表现，方便快速评审。',
        '',
        '## 7. 架构概要',
        '- **模块边界**：补充涉及的模块、组件及职责划分。',
        '- **数据流**：补充核心输入、处理、输出路径。',
        '- **外部依赖**：补充依赖的系统、服务、第三方 API 或运行环境。',
        '- **主要风险**：补充兼容性、约束或技术风险。',
        '',
        '## 8. 人工审阅清单',
        '- [ ] 需求描述准确。',
        '- [ ] 用户旅程覆盖适用的正常、异常、角色、权限、重试和持久化路径。',
        '- [ ] 验收标准足以判断是否完成。',
        '- [ ] 测试策略足以验证请求目标。',
        '- [ ] 产品设计概要足以帮助评审者形成具体产品形态认知。',
        '- [ ] 架构概要足以帮助评审者理解模块边界、数据流和主要风险。',
    ])
    return '\n'.join(lines) + '\n'


def _unit_plan_body(state: dict[str, Any]) -> str:
    lines = [
        '# 单元计划确认（Unit Plan Confirmation）',
        '',
        '## 目标覆盖矩阵',
    ]
    for item in state.get('objectiveCoverage', []):
        units = ', '.join(item.get('units', []))
        lines.append(f"- `{item.get('status')}` {item.get('objective')} -> {units}")
    lines.extend([
        '',
        '## 测试用例矩阵（Test Case Matrix）',
        '',
        '| 验收标准 | 测试用例 | 层级 | 命令/证据 | 预期结果 |',
        '|---|---|---|---|---|',
    ])
    for unit in state.get('units', []):
        test_cases = _unit_test_cases(unit)
        if not test_cases:
            continue
        for case in test_cases:
            if not isinstance(case, dict):
                continue
            criterion = str(case.get('acceptance_criterion') or case.get('acceptanceCriterion') or '未指定')
            case_id = str(case.get('id') or case.get('name') or '未指定')
            layer = str(case.get('layer') or '未指定')
            command_or_evidence = str(case.get('command') or case.get('evidence') or '未指定')
            expected = str(case.get('expected') or case.get('expected_result') or case.get('expectedResult') or '未指定')
            lines.append(f'| {criterion} | {case_id} | {layer} | {command_or_evidence} | {expected} |')
    if lines[-1] == '|---|---|---|---|---|':
        lines.append('| 补充验收标准 | 补充测试用例 ID | unit/functional/integration/e2e/manual | 补充命令或人工证据 | 补充预期结果 |')
    lines.extend([
        '',
        '## 执行单元',
    ])
    for unit in state.get('units', []):
        lines.extend([
            f"### {unit.get('id')} - {unit.get('name', unit.get('id'))}",
            f"- 工作流验证层级：`{unit.get('workflow_validation_level', 'fragment')}`",
            '- 范围：',
        ])
        scope = unit.get('scope') or []
        lines.extend(f'  - {item}' for item in scope) if scope else lines.append('  - 未指定')
        commands = unit.get('verification_commands') or []
        lines.append('- 验证命令：')
        lines.extend(f'  - `{command}`' for command in commands) if commands else lines.append('  - 未指定')
        test_cases = _unit_test_cases(unit)
        lines.append('- 测试用例：')
        if test_cases:
            for case in test_cases:
                if isinstance(case, dict):
                    case_id = case.get('id') or case.get('name') or 'unnamed'
                    layer = case.get('layer') or 'unspecified'
                    lines.append(f'  - `{case_id}` ({layer})')
                else:
                    lines.append(f'  - {case}')
        else:
            lines.append('  - 未指定')
        lines.append('')
    lines.extend([
        '',
        CONTROLLER_STATE_PATCH_HEADING,
        '',
        '```json',
        json.dumps(_controller_state_patch(state), ensure_ascii=False, indent=2),
        '```',
        '',
        '## 人工审阅清单',
        '- [ ] 每个目标都映射到一个或多个单元。',
        '- [ ] 每个单元都声明了足够的验证证据。',
        '- [ ] fragment 单元没有声称完整场景闭环。',
        '- [ ] closure 单元包含功能或 E2E 闭环证据。',
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
        '# 最终验收确认',
        '',
        '## 结果',
        f"- 当前阶段：`{state.get('currentStep')}`",
        f"- 状态：`{state.get('status')}`",
        f"- 当前单元：`{unit_id}`",
        '',
        '## 覆盖情况',
    ]
    for item in state.get('objectiveCoverage', []):
        units = ', '.join(item.get('units', []))
        lines.append(f"- `{item.get('status')}` {item.get('objective')} -> {units}")
    lines.extend([
        '',
        '## 证据摘要',
    ])
    builder_summary = (builder.get('done_payload') or {}).get('summary') or builder.get('runner_status')
    if builder_summary:
        lines.append(f'- 构建器：{builder_summary}')
    if changed_files:
        lines.append('- 变更文件：')
        lines.extend(f'  - `{path}`' for path in changed_files[:20])
    if review:
        review_status = 'passed' if review.get('passed') else 'failed'
        lines.append(f'- 评审：{review_status}')
        issues = review.get('issues') or []
        if issues:
            lines.append('- 评审问题：')
            lines.extend(f"  - {issue.get('type', 'issue')}: {issue.get('message', issue)}" for issue in issues[:10])
    if verification:
        verification_status = 'passed' if verification.get('passed') else 'failed'
        lines.append(f'- 验证：{verification_status}')
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
        '## 证据文件',
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
        '## 人工审阅清单',
        '- [ ] 实际结果满足已批准的验收标准。',
        '- [ ] 已知问题已接受或记录。',
        '- [ ] 证据文件足以支持最终验收。',
        '',
        '## 修改清单',
        '',
        '<!-- 如需 Agent 做定点修改，请在此列出具体事项（每项一行）。',
        '     留空则 Agent 收到完整验收文档作为参考。-->',
    ])
    return _with_final_acceptance_rejection_routing('\n'.join(lines) + '\n')


def _with_final_acceptance_rejection_routing(body: str) -> str:
    return normalize_final_acceptance_rejection_routing(body)


def normalize_final_acceptance_rejection_routing(
    body: str,
    selected_route: str | None = None,
) -> str:
    route_ids = {route for route, _, _ in FINAL_ACCEPTANCE_REJECTION_ROUTES}
    if selected_route is not None and selected_route not in route_ids:
        raise ValueError(f'Unknown final acceptance rejection route: {selected_route}')

    selected_routes = {selected_route} if selected_route else _selected_final_acceptance_rejection_routes(body)
    routing_block = _final_acceptance_rejection_routing_block(selected_routes)
    if _has_final_acceptance_rejection_routing_heading(body):
        return _replace_final_acceptance_rejection_routing_block(body, routing_block)

    lines = [
        body.rstrip(),
        '',
        routing_block.rstrip(),
        '',
    ]
    if '## Rejection Notes' not in body and '## 返工说明' not in body:
        lines.extend([
            '## 返工说明（Rejection Notes）',
            '选择拒绝或返工前，请描述验收差距、缺失证据或需要变更的范围。',
        ])
    return '\n'.join(lines) + '\n'


def _selected_final_acceptance_rejection_routes(body: str) -> set[str]:
    selected: set[str] = set()
    for route, label, _ in FINAL_ACCEPTANCE_REJECTION_ROUTES:
        for alias in (*FINAL_ACCEPTANCE_REJECTION_ROUTE_ALIASES.get(route, ()), label):
            pattern = rf'^\s*[-*]\s*\[[xX]\]\s*{re.escape(alias)}\s*:'
            if re.search(pattern, body, flags=re.MULTILINE):
                selected.add(route)
                break
    return selected


def _replace_final_acceptance_rejection_routing_block(body: str, routing_block: str) -> str:
    lines = body.rstrip().splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if _is_final_acceptance_rejection_routing_heading(line)
        ),
        None,
    )
    if start is None:
        return body.rstrip() + '\n'

    end = start + 1
    saw_route_item = False
    while end < len(lines):
        line = lines[end]
        if line.startswith('## ') and end > start + 1:
            break
        if _is_final_acceptance_rejection_route_line(line):
            saw_route_item = True
            end += 1
            continue
        if not saw_route_item:
            end += 1
            continue
        if not line.strip():
            end += 1
        break

    next_lines = [
        *lines[:start],
        *routing_block.rstrip().splitlines(),
        '',
        *lines[end:],
    ]
    return '\n'.join(next_lines).rstrip() + '\n'


def _is_final_acceptance_rejection_route_line(line: str) -> bool:
    for route, label, _ in FINAL_ACCEPTANCE_REJECTION_ROUTES:
        for alias in (*FINAL_ACCEPTANCE_REJECTION_ROUTE_ALIASES.get(route, ()), label):
            pattern = rf'^\s*[-*]\s*\[[ xX]\]\s*{re.escape(alias)}\s*:'
            if re.search(pattern, line):
                return True
    return False


def _final_acceptance_rejection_routing_block(selected_routes: set[str]) -> str:
    lines = [
        '## 返工路由（Rejection Routing）',
        '如果最终验收不通过，请勾选下面的人工流向。可多选；需求变更优先级最高。',
    ]
    for route, label, description in FINAL_ACCEPTANCE_REJECTION_ROUTES:
        checked = 'x' if route in selected_routes else ' '
        lines.append(f'- [{checked}] {label}: {description}')
    return '\n'.join(lines) + '\n'


def _has_final_acceptance_rejection_routing_heading(body: str) -> bool:
    return any(_is_final_acceptance_rejection_routing_heading(line) for line in body.splitlines())


def _is_final_acceptance_rejection_routing_heading(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith('##') and (
        'Rejection Routing' in stripped
        or '返工路由' in stripped
    )


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


def _unit_test_cases(unit: dict[str, Any]) -> list[Any]:
    for key in ('test_cases', 'testCases'):
        raw_cases = unit.get(key)
        if isinstance(raw_cases, list) and raw_cases:
            return raw_cases
    return []


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


def extract_patch_list(gate_content: str) -> str | None:
    """Return non-empty lines from the ## 修改清单 section, or None if absent/empty."""
    raw = _markdown_section(gate_content, '修改清单')
    lines = [
        line for line in raw.splitlines()
        if line.strip() and not line.strip().startswith('<!--') and not line.strip().startswith('-->')
    ]
    return '\n'.join(lines) if lines else None


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
        if 'test_cases' in unit and not isinstance(unit['test_cases'], list):
            raise ValueError(f'unit {unit_id} test_cases must be a list')
        if 'testCases' in unit and not isinstance(unit['testCases'], list):
            raise ValueError(f'unit {unit_id} testCases must be a list')
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
