from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from workflow_controller.gates.parsers import (
    CONFIRMATION_HEADING,
    CONTROLLER_STATE_PATCH_HEADING,
    FINAL_ACCEPTANCE_REJECTION_ROUTE_ALIASES,
    FINAL_ACCEPTANCE_REJECTION_ROUTES,
    _controller_state_patch,
    _current_unit,
    _load_json_file,
    _read_lines,
    _unit_test_cases,
    gate_body,
    write_gate_file,
)


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
        '',
        '- 每条验收标准应使用稳定 AC ID，并写明固定测试数据或 fixture、操作路径、可断言的期望值。',
        '- 用户可见闭环或数据流验收应能生成可执行 E2E 测试；截图或人工观察不能替代断言。',
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
        '- **验收示意**：补充"什么样算完成"的直观表现，方便快速评审。',
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
        '| 验收标准 | 测试用例 | 层级 | 测试数据/Fixture | 命令/证据 | 预期结果 |',
        '|---|---|---|---|---|---|',
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
            fixture = str(case.get('fixture') or case.get('test_data') or case.get('testData') or '未指定')
            command_or_evidence = str(case.get('command') or case.get('evidence') or '未指定')
            expected = str(case.get('expected') or case.get('expected_result') or case.get('expectedResult') or '未指定')
            golden_path = ' · Golden Path' if case.get('golden_path') is True else ''
            lines.append(f'| {criterion} | {case_id}{golden_path} | {layer} | {fixture} | {command_or_evidence} | {expected} |')
    if lines[-1] == '|---|---|---|---|---|---|':
        lines.append('| 补充验收标准 | 补充测试用例 ID | unit/functional/integration/e2e/manual | 补充 fixture 或测试数据 | 补充命令或人工证据 | 补充预期结果 |')
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
        '- [ ] E2E/closure 测试用例包含 AC、fixture、可执行命令和具体断言，并至少标记一个 Golden Path 正常流程。',
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
    lines.extend(_golden_path_result_lines(state, verification))
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
        '- [ ] 已核对 AC 对应的测试命令、测试文件和具体断言，不只依赖截图或 UI 外观。',
        '- [ ] 已知问题已接受或记录。',
        '- [ ] 证据文件足以支持最终验收。',
        '',
        '## 修改清单',
        '',
        '<!-- 如需 Agent 做定点修改，请在此列出具体事项（每项一行）。',
        '     留空则 Agent 收到完整验收文档作为参考。-->',
    ])
    return _with_final_acceptance_rejection_routing('\n'.join(lines) + '\n')


def _golden_path_result_lines(state: dict[str, Any], verification: dict[str, Any]) -> list[str]:
    unit = _current_unit(state)
    golden_cases = [
        case for case in _unit_test_cases(unit)
        if isinstance(case, dict) and case.get('golden_path') is True
    ]
    if not golden_cases:
        return []
    results = [
        result for result in verification.get('results') or []
        if isinstance(result, dict)
    ]
    lines = [
        '',
        '## Golden Path 正常流程',
    ]
    for case in golden_cases:
        command = str(case.get('command') or '').strip()
        result = _find_matching_command_result(command, results)
        if result is None:
            status = 'missing'
            suffix = ''
        else:
            status = 'passed' if result.get('ok') else 'failed'
            returncode = result.get('returncode')
            suffix = f' (exit {returncode})' if returncode not in {None, 0} else ''
        lines.extend([
            f"- AC：{case.get('acceptance_criterion') or '未指定'}",
            f"- 测试用例：`{case.get('id') or '未指定'}`",
            f"- 命令：`{command or '未指定'}` -> {status}{suffix}",
            f"- 期望：{case.get('expected') or '未指定'}",
        ])
    return lines



def _find_matching_command_result(command: str, results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not command:
        return None
    for result in results:
        result_command = str(result.get('command') or '').strip()
        if command == result_command or command in result_command or result_command in command:
            return result
    return None



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
