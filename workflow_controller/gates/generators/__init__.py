from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from workflow_controller.acceptance_obligations import active_must_obligations
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
from workflow_controller.journeys import final_journey_matrix_rows
from workflow_controller.scope_audit import final_scope_audit_gate_lines


def ensure_requirements_gate(state: dict[str, Any], approvals_dir: Path) -> Path:
    path = approvals_dir / 'requirements-and-acceptance.md'
    if not path.exists():
        write_gate_file(path, render_requirements_gate_body(state))
    return path


def render_requirements_gate_body(state: dict[str, Any]) -> str:
    return format_requirements_gate_body(state, _requirements_body(state))


def ensure_unit_plan_gate(state: dict[str, Any], approvals_dir: Path) -> Path:
    path = approvals_dir / 'unit-plan.md'
    if not path.exists():
        write_gate_file(path, render_unit_plan_gate_body(state))
    return path


def ensure_bug_fix_gate(state: dict[str, Any], approvals_dir: Path) -> Path:
    path = approvals_dir / 'bug-fix.md'
    if not path.exists():
        write_gate_file(path, render_bug_fix_gate_body(state))
    return path


def render_bug_fix_gate_body(state: dict[str, Any]) -> str:
    feedback = str(state.get('finalAcceptanceDefectFeedback') or state.get('finalAcceptanceRejectionFeedback') or '').strip()
    bug_fix_id = state.get('activeBugFixId') or f"bug-fix-{int(state.get('bugFixAttemptCount') or 1)}"
    return (
        '# Bug Fix Gate\n\n'
        f"- Bug Fix ID: `{bug_fix_id}`\n"
        '- Scope: fix defects under already approved requirements only; do not add, remove, or weaken AC.\n\n'
        '## Final Acceptance Defect Feedback\n\n'
        f'{feedback or "- Fill in the observed final acceptance defect."}\n\n'
        '## Expected Behavior\n\n'
        '- Describe the approved behavior that should already work.\n\n'
        '## Actual Behavior\n\n'
        '- Describe the observed defect and reproduction path.\n\n'
        '## Root Cause\n\n'
        '- Bug Fix Agent must classify root cause as implementation_bug, test_gap, unit_plan_gap, or architecture_issue.\n'
        '- If root cause is unit_plan_gap or architecture_issue, controller must escalate to Unit Plan revision.\n\n'
        '## Regression Verification\n\n'
        '- List existing test cases, regression commands, or manual evidence required before returning to Final Acceptance.\n'
    )


def render_unit_plan_gate_body(state: dict[str, Any]) -> str:
    return _unit_plan_body(state)


def format_requirements_gate_body(state: dict[str, Any], raw_body: str) -> str:
    return _with_approval_summary(
        raw_body,
        default_title='# 需求与验收确认',
        summary_lines=_requirements_summary_lines(state),
        appendix_title='## 附录 A：完整需求与验收正文',
    )


def format_unit_plan_gate_body(state: dict[str, Any], raw_body: str) -> str:
    return _with_approval_summary(
        raw_body,
        default_title='# 单元计划确认（Unit Plan Confirmation）',
        summary_lines=_unit_plan_summary_lines(state),
        appendix_title='## 附录 A：Unit Plan 原始正文',
    )


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


def _with_approval_summary(
    raw_body: str,
    *,
    default_title: str,
    summary_lines: list[str],
    appendix_title: str,
) -> str:
    body = gate_body(raw_body).rstrip()
    if _approval_body_has_summary(body):
        return body + '\n'

    title, detail = _split_markdown_title(body, default_title)
    lines = [
        title,
        '',
        *summary_lines,
        '',
        appendix_title,
        '',
    ]
    if detail.strip():
        lines.append(detail.strip())
    else:
        lines.append('- 原始正文为空；请重新生成审批内容。')
    return '\n'.join(lines).rstrip() + '\n'


def _approval_body_has_summary(body: str) -> bool:
    return bool(re.search(r'(?m)^##\s+审批摘要\s*$', body))


def _split_markdown_title(body: str, default_title: str) -> tuple[str, str]:
    lines = body.splitlines()
    if lines and re.match(r'^#\s+\S', lines[0].strip()):
        return lines[0].strip(), '\n'.join(lines[1:]).strip()
    return default_title, body.strip()


def _requirements_summary_lines(state: dict[str, Any]) -> list[str]:
    unit = _current_unit(state)
    commands = unit.get('verification_commands') or state.get('verificationCommands') or []
    command_lines = [f'- `{command}`' for command in commands[:5]]
    if len(commands) > 5:
        command_lines.append(f'- 另有 {len(commands) - 5} 条命令见附录。')
    if not command_lines:
        command_lines.append('- 待在正文测试策略中补充验证命令或人工证据。')

    obligations = active_must_obligations(state)
    ao_summary = (
        f'{len(obligations)} 条 active must AO 需要在 AC 中覆盖。'
        if obligations
        else '当前没有 active must AO。'
    )
    return [
        '## 审批摘要',
        '',
        '### 结论',
        '- 待人工确认 Requirements 与 Acceptance Criteria 后进入 Unit Plan。',
        '',
        '### 变更点',
        f"- 请求目标：`{state.get('requestedOutcome') or '-'}`",
        f"- 可行目标：`{state.get('feasibleOutcome') or '-'}`",
        f"- 当前单元：`{state.get('currentUnitId') or '-'}`",
        f'- AO 覆盖要求：{ao_summary}',
        '',
        '### 需要人确认的点',
        '- 需求描述、用户旅程和验收标准是否准确。',
        '- 每条 AC 是否声明 verification layer，并能被测试或人工证据验证。',
        '- Product Design / Technical Architecture 引用是否足以支持后续执行。',
        '- Journey Acceptance Matrix 是否覆盖跨单元闭环；不涉及跨流程时确认其为空是合理的。',
        '',
        '### 验收命令',
        *command_lines,
        '',
        '### Controller/Critic 检查摘要',
        '- Controller 会在人工确认前预检 AO/AC 映射、verification layer、设计/架构引用和 Journey 合约。',
        '- Critic：未配置独立审批模型；最终确认仍由人或 controller 规则完成。',
    ]


def _unit_plan_summary_lines(state: dict[str, Any]) -> list[str]:
    units = [unit for unit in state.get('units') or [] if isinstance(unit, dict)]
    pending_units = [unit for unit in units if not unit.get('passes')]
    commands = []
    for unit in pending_units:
        for command in unit.get('verification_commands') or []:
            command_text = str(command)
            if command_text not in commands:
                commands.append(command_text)
    command_lines = [f'- `{command}`' for command in commands[:6]]
    if len(commands) > 6:
        command_lines.append(f'- 另有 {len(commands) - 6} 条命令见附录。')
    if not command_lines:
        command_lines.append('- 待在 Unit Plan 正文中补充验证命令或人工证据。')

    coverage_lines = []
    for item in state.get('objectiveCoverage') or []:
        if not isinstance(item, dict):
            continue
        units_text = ', '.join(str(unit_id) for unit_id in item.get('units') or []) or '-'
        coverage_lines.append(f"- `{item.get('status') or '-'}` {item.get('objective') or '-'} -> {units_text}")
    if not coverage_lines:
        coverage_lines.append('- 待补目标覆盖矩阵。')

    return [
        '## 审批摘要',
        '',
        '### 结论',
        '- 待人工确认 Unit Plan 后进入执行阶段。',
        '',
        '### 变更点',
        f"- 当前单元：`{state.get('currentUnitId') or '-'}`",
        f'- 待执行单元数：{len(pending_units)} / {len(units) or 1}',
        *coverage_lines[:4],
        '',
        '### 需要人确认的点',
        '- 每个目标是否映射到一个或多个可执行 unit。',
        '- 每条非 manual AC 是否有 Test Case、fixture/setup、命令或人工证据、具体 expected assertion。',
        '- Journey 是否映射到 closure 或 E2E 测试用例。',
        '- Controller State Patch 是否只改变当前计划允许的 state 字段。',
        '',
        '### 验收命令',
        *command_lines,
        '',
        '### Controller/Critic 检查摘要',
        '- Controller 会在进入人工确认前预检 Controller State Patch、AO 覆盖、测试用例覆盖、验证环境、Golden Path 和 Journey 映射。',
        '- Critic：未配置独立审批模型；最终确认仍由人或 controller 规则完成。',
    ]


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
        '- 根据当前进度、发现记录和目标上下文整理。',
        '- 确认前请人工补齐正常、异常、角色、权限、重试和数据持久化路径。',
        '',
        '## 3. 验收标准',
        '',
        '- 每条验收标准应使用稳定 AC ID，并写明固定测试数据或 fixture、操作路径、可断言的期望值。',
        '- 每条 AC 必须声明 verification layer：unit / functional / integration / e2e / manual，推荐格式：`AC-ID [verification: e2e]`。',
        '- 用户可见闭环或数据流验收应能生成可执行 E2E 测试；截图或人工观察不能替代断言。',
    ]
    done_when = unit.get('done_when') or []
    if done_when:
        lines.extend(f'- {item}' for item in done_when)
    else:
        lines.append('- 当前上下文中的目标验收标准均已满足。')
    lines.extend([
        '',
        '## 4. 需求可追溯矩阵（Requirements Traceability Matrix）',
        '',
        '- 每个 active must AO 必须映射到一个 AC，或显式标记为 `deferred` / `rejected` / `out_of_scope` 并写明原因。',
        '- Status 只能填写 covered/deferred/rejected/out_of_scope；covered 行必须填写 AC ID 和 Verification Layer。',
        '- Verification Layer 只能填写 unit / functional / integration / e2e / manual。',
        '',
        '| AO | AC | Status | Verification Layer | Evidence/Reason |',
        '| --- | --- | --- | --- | --- |',
    ])
    obligations = active_must_obligations(state)
    if obligations:
        for obligation in obligations:
            lines.append(
                f"| {obligation.get('id')} | 待补 AC ID | pending | 待补 | {obligation.get('title', '待补证据或原因')} |"
            )
    else:
        lines.append('| 无 active must AO | 待补 AC ID | pending | 待补 | 待补证据或原因 |')
    lines.extend([
        '',
        '## 4.5 设计与架构可追溯矩阵（Design/Architecture Traceability Matrix）',
        '',
        '- 每条 covered AC 必须映射到产品设计引用和技术架构引用。',
        '- Product Design Ref 指向用户流程、界面/状态、API/CLI 输出或无 UI 场景的产品行为说明。',
        '- Technical Architecture Ref 指向模块边界、数据流、外部依赖或主要技术风险说明。',
        '- 这里先记录设计/架构引用；Verifier evidence schema 会在验证阶段消费 Unit Plan test cases，并进入最终验收矩阵。',
        '',
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |',
        '| --- | --- | --- | --- |',
        '| 待补 AC ID | 待补产品设计引用 | 待补技术架构引用 | 待补说明 |',
        '',
        '## 4.7 Journey Acceptance Matrix',
        '',
        '- e2e 或 closure 验收必须至少有一行 active Journey；不涉及时可以只保留表头。',
        '- Steps 使用 `->` 分隔关键路径步骤；AC 填关联 AC ID；Verification Layer 只能使用 functional / integration / e2e / manual。',
        '',
        '| Journey | Title | Status | Steps | AC | Verification Layer | Verification Command | Test Case | Unit |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- |',
        '',
        '## 4.8 已澄清事项、关键假设与待确认风险',
        '',
        '- **已澄清事项**：如 agent 在 tmux pane 中向用户提问，在这里记录用户回答形成的具体决策。',
        '- **关键假设**：列出为避免打断而采用的保守假设，并说明对需求和验收的影响。',
        '- **待确认风险**：列出仍需人工在 gate 审阅时重点确认的风险；不能把阻断性缺口藏在这里。',
        '',
        '## 5. 测试策略（Test Strategy）',
    ])
    if commands:
        lines.extend(f'- `{command}`' for command in commands)
    else:
        lines.append('- 确认前至少补充一个验证命令或明确的人工证据。')
    lines.extend([
        '',
        '## 6. 范围外',
    ])
    non_goals = unit.get('non_goals') or []
    if non_goals:
        lines.extend(f'- {item}' for item in non_goals)
    else:
        lines.append('- 未更新本确认门禁前，不扩展到请求目标之外。')
    lines.extend([
        '',
        '## 7. 产品设计概要',
        '- **主要用户流程**：补充用户完成核心功能的关键步骤，包括正常路径和主要异常路径。',
        '- **关键页面/状态**：补充关键界面、关键系统状态，或无 UI 场景下的 API/CLI 输出示意。',
        '- **验收示意**：补充"什么样算完成"的直观表现，方便快速评审。',
        '',
        '## 8. 架构概要',
        '- **模块边界**：补充涉及的模块、组件及职责划分。',
        '- **数据流**：补充核心输入、处理、输出路径。',
        '- **外部依赖**：补充依赖的系统、服务、第三方 API 或运行环境。',
        '- **主要风险**：补充兼容性、约束或技术风险。',
        '',
        '## 9. 人工审阅清单',
        '- [ ] 需求描述准确。',
        '- [ ] 用户旅程覆盖适用的正常、异常、角色、权限、重试和持久化路径。',
        '- [ ] 验收标准足以判断是否完成。',
        '- [ ] 每条 AC 都声明了 verification layer。',
        '- [ ] 每个 active must AO 都映射到 AC，或已明确 deferred/rejected/out_of_scope 及原因。',
        '- [ ] 测试策略足以验证请求目标。',
        '- [ ] 产品设计概要足以帮助评审者形成具体产品形态认知。',
        '- [ ] 架构概要足以帮助评审者理解模块边界、数据流和主要风险。',
    ])
    return '\n'.join(lines) + '\n'


def _unit_plan_body(state: dict[str, Any]) -> str:
    lines = [
        '# 单元计划确认（Unit Plan Confirmation）',
        '',
        *_unit_plan_summary_lines(state),
        '',
        '## 附录 A：目标覆盖矩阵',
    ]
    for item in state.get('objectiveCoverage', []):
        units = ', '.join(item.get('units', []))
        lines.append(f"- `{item.get('status')}` {item.get('objective')} -> {units}")
    lines.extend([
        '',
        '## 附录 B：测试用例矩阵（Test Case Matrix）',
        '',
        '| 验收标准 | 测试用例 | 层级 | 产品设计引用 | 技术架构引用 | 测试数据/Fixture | 命令/证据 | 预期结果 |',
        '|---|---|---|---|---|---|---|---|',
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
            product_design_refs = _case_trace_refs(
                case,
                'product_design_refs',
                'productDesignRefs',
                'product_design_ref',
                'productDesignRef',
            )
            technical_architecture_refs = _case_trace_refs(
                case,
                'technical_architecture_refs',
                'technicalArchitectureRefs',
                'technical_architecture_ref',
                'technicalArchitectureRef',
            )
            fixture = str(case.get('fixture') or case.get('test_data') or case.get('testData') or '未指定')
            command_or_evidence = str(case.get('command') or case.get('evidence') or '未指定')
            expected = str(case.get('expected') or case.get('expected_result') or case.get('expectedResult') or '未指定')
            golden_path = ' · Golden Path' if case.get('golden_path') is True else ''
            lines.append(f'| {criterion} | {case_id}{golden_path} | {layer} | {product_design_refs} | {technical_architecture_refs} | {fixture} | {command_or_evidence} | {expected} |')
    if lines[-1] == '|---|---|---|---|---|---|---|---|':
        lines.append('| 补充验收标准 | 补充测试用例 ID | unit/functional/integration/e2e/manual | 补充产品设计引用 | 补充技术架构引用 | 补充 fixture 或测试数据 | 补充命令或人工证据 | 补充预期结果 |')
    lines.extend([
        '',
        '## 附录 C：执行单元',
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
        '## 附录 D：人工审阅清单',
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
    lines.extend(_final_acceptance_evidence_matrix_lines(verification))
    lines.extend(final_scope_audit_gate_lines(artifacts_dir))
    lines.extend(_journey_matrix_lines(state, artifacts_dir))
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
    lines.extend(_bug_fix_evidence_lines(state, artifacts_dir))
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


def _bug_fix_evidence_lines(state: dict[str, Any], artifacts_dir: Path) -> list[str]:
    bug_fix_id = str(state.get('activeBugFixId') or '').strip()
    if not bug_fix_id:
        return []
    bug_fix_dir = artifacts_dir / 'bug-fixes' / bug_fix_id
    if not bug_fix_dir.exists():
        return []
    summary = _load_json_file(bug_fix_dir / 'bug-fix-summary.json')
    root_cause = _load_json_file(bug_fix_dir / 'root-cause.json')
    verification = _load_json_file(bug_fix_dir / 'verification.json')
    lines = [
        '',
        '## Bug Fix Evidence',
        f'- Bug Fix ID: `{bug_fix_id}`',
        f"- Status: `{summary.get('status', 'unknown')}`",
    ]
    if root_cause:
        lines.extend([
            f"- Root cause classification: `{root_cause.get('classification', 'unknown')}`",
            f"- Root cause route: `{root_cause.get('route', 'unknown')}`",
            f"- Root cause summary: {root_cause.get('summary', 'not provided')}",
        ])
    if verification:
        lines.append(f"- Regression verification: `{'passed' if verification.get('passed') else 'failed'}`")
        for command in verification.get('commands') or []:
            lines.append(f"  - `{command}`")
    for name in ['bug-fix-summary.json', 'root-cause.json', 'verification.json', 'green-test.txt']:
        path = bug_fix_dir / name
        if path.exists():
            lines.append(f'- `{path}`')
    return lines


def _final_acceptance_evidence_matrix_lines(verification: dict[str, Any]) -> list[str]:
    rows = [
        row for row in verification.get('evidence_rows') or []
        if isinstance(row, dict)
    ]
    lines = [
        '',
        '## 验收证据矩阵（Final Acceptance Evidence Matrix）',
        '',
        '拒绝时请引用矩阵中的 AO、AC、Test Case 或 Evidence，便于路由到 requirements、unit_plan、defect_fix 或 implementation。',
        '',
        '| AO | AC | Test Case | Layer | Status | Evidence | Expected | Artifacts | Golden Path |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- |',
    ]
    if not rows:
        lines.append('| 未指定 | 未指定 | 未指定 | 未指定 | missing | verification.json 未包含 evidence_rows | 请检查 Verifier evidence schema | verification.json | no |')
        return lines

    for row in rows:
        lines.append(
            '| '
            + ' | '.join([
                _markdown_cell(_join_strings(row.get('acceptance_obligations')) or '未指定'),
                _markdown_cell(row.get('acceptance_criterion') or '未指定'),
                _markdown_cell(row.get('test_case_id') or '未指定'),
                _markdown_cell(row.get('layer') or '未指定'),
                _markdown_cell(row.get('status') or 'missing'),
                _markdown_cell(_evidence_cell(row)),
                _markdown_cell(row.get('expected') or '未指定'),
                _markdown_cell(_join_strings(row.get('artifact_refs')) or 'verification.json'),
                'yes' if row.get('golden_path') is True else 'no',
            ])
            + ' |'
        )
    return lines


def _journey_matrix_lines(state: dict[str, Any], artifacts_dir: Path) -> list[str]:
    rows = final_journey_matrix_rows(state, artifacts_dir)
    if not rows:
        return []
    lines = [
        '',
        '## Journey Matrix',
        '',
        '| Journey | AC | Unit | Test Case | Layer | Status | Command / Evidence | Expected | Artifacts |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- |',
    ]
    for row in rows:
        command = str(row.get('command') or '').strip()
        evidence = f'`{command}`' if command else '未指定'
        lines.append(
            '| '
            + ' | '.join([
                _markdown_cell(
                    f"{row.get('journey_id') or '未指定'} {row.get('title') or ''}".strip()
                ),
                _markdown_cell(_join_strings(row.get('acceptance_criteria')) or '未指定'),
                _markdown_cell(row.get('unit_id') or '未指定'),
                _markdown_cell(row.get('test_case_id') or '未指定'),
                _markdown_cell(row.get('layer') or '未指定'),
                _markdown_cell(row.get('status') or 'missing'),
                _markdown_cell(evidence),
                _markdown_cell(row.get('expected') or '未指定'),
                _markdown_cell(_join_strings(row.get('artifact_refs')) or 'artifacts/journeys/journey-evidence.json'),
            ])
            + ' |'
        )
    return lines


def _evidence_cell(row: dict[str, Any]) -> str:
    command = str(row.get('command') or '').strip()
    if command:
        return f'`{command}`'
    manual_evidence = str(row.get('manual_evidence') or '').strip()
    return manual_evidence or '未指定'


def _join_strings(value: Any) -> str:
    if isinstance(value, list):
        return ', '.join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip() if value is not None else ''


def _markdown_cell(value: Any) -> str:
    return str(value).replace('|', '\\|').replace('\n', '<br>').strip()


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


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    return [str(value).strip()] if str(value).strip() else []


def _case_trace_refs(case: dict[str, Any], *keys: str) -> str:
    for key in keys:
        refs = _string_list(case.get(key))
        if refs:
            return ', '.join(refs)
    return '未指定'
