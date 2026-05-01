from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

from workflow_controller.rrc_agent_runners import RunnerRequest, make_runner, run_agent_backend
from workflow_controller.rrc_human_gates import (
    check_gate_file,
    render_requirements_gate_body,
    render_unit_plan_gate_body,
    write_gate_file,
)
from workflow_controller.rrc_real_runtime import (
    collect_git_changed_files,
    run_agent_for_current_step,
    run_verification_commands,
    verification_commands_for_state,
)
from workflow_controller.rrc_validators import objective_coverage_units_passed


@dataclass
class StepResult:
    approved: bool | None = None
    summary: str | None = None
    outputs: list[str] | None = None


def _approval_requested_by_state(state: dict[str, Any]) -> bool:
    return bool(state.get('autoApprove'))


class NotImplementedWorkflowStep(RuntimeError):
    pass


class TestStrategistBlocked(RuntimeError):
    def __init__(self, message: str, *, retry_count: int, gap_id: str | None = None) -> None:
        super().__init__(message)
        self.retry_count = retry_count
        self.gap_id = gap_id


class TestStrategistFallbackBlocked(RuntimeError):
    pass


def run_requirements_drafter(
    state: dict[str, Any],
    approvals_dir: Path,
    artifacts_dir: Path,
    dry_run: bool = False,
) -> StepResult:
    draft_dir = artifacts_dir / 'requirements-draft'
    draft_dir.mkdir(parents=True, exist_ok=True)
    gate_path = approvals_dir / 'requirements-and-acceptance.md'
    body_path = draft_dir / 'requirements-body.md'
    summary_path = draft_dir / 'requirements-draft-summary.json'

    if dry_run or state.get('agentRunner') != 'tmux-claude':
        body = render_requirements_gate_body(state)
        write_gate_file(gate_path, body)
        body_path.write_text(body, encoding='utf-8')
        _write_json(summary_path, {
            'status': 'ok',
            'mode': 'local-template',
            'gate_path': str(gate_path),
            'body_path': str(body_path),
            'generated_at': _now_iso(),
        })
        return StepResult(summary='requirements draft generated', outputs=[str(gate_path), str(summary_path)])

    prompt_path = draft_dir / 'requirements-draft-prompt.md'
    if body_path.exists():
        body_path.unlink()
    prompt_path.write_text(
        _render_requirements_draft_prompt(state, body_path),
        encoding='utf-8',
    )
    workspace_path = state.get('executionWorkspacePath') or state.get('workspacePath')
    if not workspace_path:
        raise RuntimeError('requirements drafter requires workspacePath or executionWorkspacePath')

    runner = make_runner(state)
    result = run_agent_backend(RunnerRequest(
        backend=runner.backend,
        workspace_dir=Path(workspace_path),
        prompt_path=prompt_path,
        artifact_dir=draft_dir,
        unit_id='requirements-draft',
        agent_command=runner.agent_command,
        tmux_target=runner.tmux_target,
        role=runner.role,
        env=runner.env,
        timeout_seconds=int(state.get('requirementsDraftTimeoutSeconds') or 1800),
    ))
    _write_json(summary_path, {
        'status': result.status,
        'mode': result.backend,
        'runner_run_dir': str(result.run_dir),
        'done_payload': result.done_payload,
        'agent_command': result.command,
        'runner_metadata': result.runner_metadata,
        'exit_code': result.returncode,
        'stdout': result.stdout,
        'stderr': result.stderr,
        'gate_path': str(gate_path),
        'body_path': str(body_path),
        'generated_at': _now_iso(),
    })
    if result.returncode != 0:
        raise RuntimeError(
            f"Requirements drafter failed with exit code {result.returncode}. See {summary_path}"
        )
    if not body_path.exists():
        raise FileNotFoundError(
            f"Requirements drafter did not write {body_path}. See {summary_path}"
        )

    write_gate_file(gate_path, body_path.read_text(encoding='utf-8'))
    return StepResult(summary='requirements draft generated', outputs=[str(gate_path), str(summary_path)])


def run_unit_plan_drafter(
    state: dict[str, Any],
    approvals_dir: Path,
    artifacts_dir: Path,
    dry_run: bool = False,
    progress_callback: Callable[[str], None] | None = None,
) -> StepResult:
    draft_dir = artifacts_dir / 'unit-plan-draft'
    draft_dir.mkdir(parents=True, exist_ok=True)
    gate_path = approvals_dir / 'unit-plan.md'
    body_path = draft_dir / 'unit-plan-body.md'
    summary_path = draft_dir / 'unit-plan-draft-summary.json'

    if dry_run or state.get('agentRunner') != 'tmux-claude':
        body = render_unit_plan_gate_body(state)
        write_gate_file(gate_path, body)
        body_path.write_text(body, encoding='utf-8')
        _write_json(summary_path, {
            'status': 'ok',
            'mode': 'local-template',
            'gate_path': str(gate_path),
            'body_path': str(body_path),
            'generated_at': _now_iso(),
        })
        return StepResult(summary='unit plan draft generated', outputs=[str(gate_path), str(summary_path)])

    prompt_path = draft_dir / 'unit-plan-draft-prompt.md'
    workspace_path = state.get('executionWorkspacePath') or state.get('workspacePath')
    if not workspace_path:
        raise RuntimeError('unit plan drafter requires workspacePath or executionWorkspacePath')

    planner_result = None
    strategist_summary: dict[str, Any] | None = None
    max_reworks = int(state.get('testStrategistCriticalMaxReworks') or 2)
    orchestrate_critical_rework = bool(
        state.get('testStrategistCriticalReworkRequired')
        or state.get('currentStep') == 'UNIT_PLAN_DRAFT'
    )
    retry_count = 0 if orchestrate_critical_rework else int(
        state.get('testStrategistPlannerRetryCount') or state.get('unitPlanRetryCount') or 0
    )
    if orchestrate_critical_rework:
        state['testStrategistPlannerRetryCount'] = retry_count
        state['unitPlanRetryCount'] = retry_count
    while True:
        if body_path.exists():
            body_path.unlink()
        prompt_path.write_text(
            _render_unit_plan_draft_prompt(state, approvals_dir / 'requirements-and-acceptance.md', body_path),
            encoding='utf-8',
        )
        runner = make_runner(state)
        planner_result = run_agent_backend(RunnerRequest(
            backend=runner.backend,
            workspace_dir=Path(workspace_path),
            prompt_path=prompt_path,
            artifact_dir=draft_dir,
            unit_id='unit-plan-draft',
            agent_command=runner.agent_command,
            tmux_target=runner.tmux_target,
            role=runner.role,
            env=runner.env,
            timeout_seconds=int(state.get('unitPlanDraftTimeoutSeconds') or 1800),
        ))
        if planner_result.returncode != 0:
            break
        if not body_path.exists():
            break

        state['testStrategistPlannerRetryCount'] = retry_count
        strategist_summary = _run_test_strategist_if_enabled(
            state=state,
            approvals_dir=approvals_dir,
            draft_dir=draft_dir,
            workspace_path=Path(workspace_path),
            progress_callback=progress_callback,
        )
        # Codex Test Strategist patches its own gaps; no Planner retry needed.
        break

    if planner_result is None:
        raise RuntimeError('Unit plan drafter did not run')
    _write_unit_plan_summary(
        summary_path=summary_path,
        result=planner_result,
        gate_path=gate_path,
        body_path=body_path,
        strategist_summary=strategist_summary or _disabled_test_strategist_summary(state),
    )
    if planner_result.returncode != 0:
        raise RuntimeError(
            f"Unit plan drafter failed with exit code {planner_result.returncode}. See {summary_path}"
        )
    if not body_path.exists():
        raise FileNotFoundError(
            f"Unit plan drafter did not write {body_path}. See {summary_path}"
        )

    # critical gaps remaining after retries are escalated to human review via the gate file

    gate_body = body_path.read_text(encoding='utf-8')
    if state.get('testStrategistEnabled'):
        gate_body = _merge_review_package_into_unit_plan_gate(
            gate_body,
            draft_dir,
            retry_count=retry_count,
        )
    write_gate_file(gate_path, gate_body)
    state.pop('unitPlanRevisionFeedback', None)
    return StepResult(summary='unit plan draft generated', outputs=[str(gate_path), str(summary_path)])


def _write_unit_plan_summary(
    *,
    summary_path: Path,
    result: Any,
    gate_path: Path,
    body_path: Path,
    strategist_summary: dict[str, Any],
) -> None:
    _write_json(summary_path, {
        'status': result.status,
        'mode': result.backend,
        'runner_run_dir': str(result.run_dir),
        'done_payload': result.done_payload,
        'agent_command': result.command,
        'runner_metadata': result.runner_metadata,
        'exit_code': result.returncode,
        'stdout': result.stdout,
        'stderr': result.stderr,
        'gate_path': str(gate_path),
        'body_path': str(body_path),
        'test_strategist': strategist_summary,
        'generated_at': _now_iso(),
    })


def _disabled_test_strategist_summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        'enabled': False,
        'runner': None,
        'actual_independence': 'disabled',
        'gap_counts': {'critical': 0, 'major': 0, 'minor': 0},
        'planner_retry_count': int(state.get('testStrategistPlannerRetryCount') or state.get('unitPlanRetryCount') or 0),
        'fallback': {'used': False, 'reason': None},
    }


def _run_test_strategist_if_enabled(
    *,
    state: dict[str, Any],
    approvals_dir: Path,
    draft_dir: Path,
    workspace_path: Path,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if not state.get('testStrategistEnabled'):
        return _disabled_test_strategist_summary(state)

    _clear_test_strategist_artifacts(draft_dir)
    prompt_path = draft_dir / 'test-strategist-prompt.md'
    prompt_path.write_text(
        _render_test_strategist_prompt(
            state=state,
            requirements_path=approvals_dir / 'requirements-and-acceptance.md',
            unit_plan_body_path=draft_dir / 'unit-plan-body.md',
            draft_dir=draft_dir,
        ),
        encoding='utf-8',
    )
    runner = make_runner(state, role='test_strategist')
    if progress_callback is not None:
        command_label = runner.agent_command.split()[0] if runner.agent_command else runner.backend
        progress_callback(f'[Test Strategist] 启动 {command_label}，正在分析测试策略...')
    result = run_agent_backend(RunnerRequest(
        backend=runner.backend,
        workspace_dir=workspace_path,
        prompt_path=prompt_path,
        artifact_dir=draft_dir,
        unit_id='test-strategist',
        agent_command=runner.agent_command,
        tmux_target=runner.tmux_target,
        role=runner.role,
        env=runner.env,
        timeout_seconds=int(state.get('testStrategistTimeoutSeconds') or state.get('unitPlanDraftTimeoutSeconds') or 1800),
    ))
    fallback_reason = None
    actual_independence = 'role-runner'
    if result.returncode != 0:
        fallback_reason = f'Test strategist failed with exit code {result.returncode}'
        if state.get('allowTestStrategistFallback') is False:
            raise TestStrategistFallbackBlocked(f'{fallback_reason}; fallback is not allowed')
        actual_independence = 'same_family_fallback'
        _clear_test_strategist_artifacts(draft_dir)
    gap_report = _ensure_test_strategy_artifacts(draft_dir)
    if _gaps(gap_report) and not fallback_reason:
        _run_test_strategist_patcher(
            state=state,
            draft_dir=draft_dir,
            workspace_path=workspace_path,
            gap_report=gap_report,
            progress_callback=progress_callback,
        )
        gap_report = _ensure_test_strategy_artifacts(draft_dir)
    return {
        'enabled': True,
        'runner': result.runner_metadata,
        'actual_independence': actual_independence,
        'independence': 'degraded' if fallback_reason else 'independent',
        'gap_counts': gap_report['gap_counts'],
        'planner_retry_count': int(state.get('testStrategistPlannerRetryCount') or state.get('unitPlanRetryCount') or 0),
        'fallback': {'used': fallback_reason is not None, 'reason': fallback_reason},
        'status': result.status,
        'exit_code': result.returncode,
        'prompt_path': str(prompt_path),
    }


def _clear_test_strategist_artifacts(draft_dir: Path) -> None:
    for filename in [
        'test-strategy.json',
        'test-strategy.md',
        'unit-plan-gap-report.json',
        'unit-plan-review-package.json',
    ]:
        path = draft_dir / filename
        if path.exists():
            path.unlink()


def _render_test_strategist_prompt(
    *,
    state: dict[str, Any],
    requirements_path: Path,
    unit_plan_body_path: Path,
    draft_dir: Path,
) -> str:
    requirements_content = requirements_path.read_text(encoding='utf-8') if requirements_path.exists() else ''
    unit = _find_unit(state, state.get('currentUnitId'))
    unit_plan_body = unit_plan_body_path.read_text(encoding='utf-8') if unit_plan_body_path.exists() else ''
    return f"""Create Test Strategist artifacts for the workflow-controller Unit Plan draft.

Write these exact artifacts in this directory:
{draft_dir}

Required files:
- test-strategy.json
- test-strategy.md
- unit-plan-gap-report.json
- unit-plan-review-package.json

Use the requirements context, Unit Plan body target path, target context, constraints, and verification requirements below.
Validate every acceptance criterion has at least one concrete behavioral test case or manual evidence.
Reject static-only strategy coverage by reporting a Critical gap.
Do not modify source code.

CRITICAL: test-strategy.json MUST use this exact top-level schema or the controller will reject it:
{{
  "acceptance_criteria": [
    {{
      "id": "AC-X-Y",
      "test_cases": [
        {{
          "id": "TC-X-Y-a",
          "layer": "unit|functional|integration|e2e|manual",
          "command": "the exact shell command to run",
          "evidence": "manual evidence description (use instead of command for manual cases)",
          "expected": "expected result"
        }}
      ]
    }}
  ]
}}
The top-level key must be "acceptance_criteria" (a list). Each entry must have "id" and "test_cases" (a non-empty list). Each test case must have either "command" or "evidence". Do not rename these keys or wrap them in another structure.

Requirements context:

```md
{requirements_content}
```

Unit Plan body path:
{unit_plan_body_path}

Unit Plan body:

```md
{unit_plan_body}
```

Target context:
- requestedOutcome: {state.get('requestedOutcome')}
- feasibleOutcome: {state.get('feasibleOutcome')}
- currentUnitId: {state.get('currentUnitId')}
- currentUnit: {json.dumps(unit, ensure_ascii=False, indent=2)}
- objectiveCoverage: {json.dumps(state.get('objectiveCoverage') or [], ensure_ascii=False, indent=2)}
- targetContextFiles: {json.dumps(state.get('targetContextFiles') or [], ensure_ascii=False, indent=2)}

Constraints:
- Keep planner and strategist outputs independent.
- Static checks such as lint, typecheck, eslint, prettier, biome, or tsc cannot be the only coverage for an acceptance criterion.
- Prefer user-visible or behavior-visible verification when the requirement has observable runtime behavior.

verification requirements:
- Include test case id, acceptance criterion, layer, command or evidence, and expected result.
- Include gap severity as Critical, Major, or Minor.
- For every gap, include a "suggested_fix" field with a concrete, actionable instruction for the Planner: specify which AC needs what kind of test, what layer (unit/integration/e2e/manual), and an example command or evidence format.
- Summarize review readiness in unit-plan-review-package.json.
"""


def _render_test_strategist_patch_prompt(
    *,
    state: dict[str, Any],
    draft_dir: Path,
    gap_report: dict[str, Any],
) -> str:
    strategy_path = draft_dir / 'test-strategy.json'
    strategy_content = strategy_path.read_text(encoding='utf-8') if strategy_path.exists() else '{}'
    return f"""你是 Test Strategist。初始测试策略存在以下空缺，请直接填补，不要发送反馈。

当前 test-strategy.json 路径：
{strategy_path}

当前 test-strategy.json 内容：
```json
{strategy_content}
```

需要修复的空缺（gap report）：
```json
{json.dumps(gap_report, ensure_ascii=False, indent=2)}
```

操作要求：
1. 对每个 gap，在对应 acceptance_criteria 条目中添加或补全 test_cases。
2. 对每个你【新增或修改】以填补空缺的 test_case，在该对象上加 `"codex_patch": true`。
3. 将完整更新后的 test-strategy.json 写回：{strategy_path}
4. 对原本已有效的 test_case，不要加 `"codex_patch"` 标记。
5. 如果某条 AC 描述过于模糊，你无法生成有意义的测试用例，则保持该 gap 条目不变。
6. 不要修改 unit-plan-gap-report.json 或其他任何文件。
7. 不要修改源代码。

已修补的 test_case 示例结构：
{{
  "id": "TC-X-Y-a",
  "layer": "unit|functional|integration|e2e|manual",
  "command": "具体的 shell 命令",
  "expected": "预期结果",
  "codex_patch": true
}}
"""


def _run_test_strategist_patcher(
    *,
    state: dict[str, Any],
    draft_dir: Path,
    workspace_path: Path,
    gap_report: dict[str, Any],
    progress_callback: Callable[[str], None] | None = None,
) -> None:
    patch_prompt_path = draft_dir / 'test-strategist-patch-prompt.md'
    patch_prompt_path.write_text(
        _render_test_strategist_patch_prompt(state=state, draft_dir=draft_dir, gap_report=gap_report),
        encoding='utf-8',
    )
    runner = make_runner(state, role='test_strategist')
    if progress_callback is not None:
        progress_callback('[Test Strategist] 正在补充缺失的测试用例...')
    result = run_agent_backend(RunnerRequest(
        backend=runner.backend,
        workspace_dir=workspace_path,
        prompt_path=patch_prompt_path,
        artifact_dir=draft_dir,
        unit_id='test-strategist-patch',
        agent_command=runner.agent_command,
        tmux_target=runner.tmux_target,
        role=runner.role,
        env=runner.env,
        timeout_seconds=int(
            state.get('testStrategistTimeoutSeconds')
            or state.get('unitPlanDraftTimeoutSeconds')
            or 1800
        ),
    ))
    if result.returncode != 0 and progress_callback is not None:
        progress_callback('[Test Strategist] 补充运行失败，保留原始结果')


def _ensure_test_strategy_artifacts(draft_dir: Path) -> dict[str, Any]:
    strategy_path = draft_dir / 'test-strategy.json'
    gap_path = draft_dir / 'unit-plan-gap-report.json'
    review_path = draft_dir / 'unit-plan-review-package.json'
    markdown_path = draft_dir / 'test-strategy.md'

    strategy = _read_json_object(strategy_path)
    if strategy is None:
        strategy = {'acceptance_criteria': []}
        _write_json(strategy_path, strategy)
    computed_gaps = _test_strategy_gaps(strategy)
    existing_report = _read_json_object(gap_path) or {}
    existing_gaps = existing_report.get('gaps') if isinstance(existing_report.get('gaps'), list) else []
    gaps = _dedupe_gaps([gap for gap in existing_gaps if isinstance(gap, dict)] + computed_gaps)
    gap_report = {
        'gap_counts': _gap_counts(gaps),
        'gaps': gaps,
    }
    _write_json(gap_path, gap_report)

    _write_json(review_path, _unit_plan_review_package(
        ready_for_review=gap_report['gap_counts']['critical'] == 0,
        strategy_path=strategy_path,
        gap_path=gap_path,
        gap_report=gap_report,
    ))
    if not markdown_path.exists():
        markdown_path.write_text('# Test Strategy\n\nNo human-readable strategy was produced.\n', encoding='utf-8')
    return gap_report


def _unit_plan_review_package(
    *,
    ready_for_review: bool,
    strategy_path: Path,
    gap_path: Path,
    gap_report: dict[str, Any],
) -> dict[str, Any]:
    return {
        'ready_for_review': ready_for_review,
        'strategy_path': str(strategy_path),
        'gap_report_path': str(gap_path),
        'gap_report': gap_report,
    }



def _merge_review_package_into_unit_plan_gate(unit_plan_body: str, draft_dir: Path, *, retry_count: int) -> str:
    gap_report = _read_json_object(draft_dir / 'unit-plan-gap-report.json') or {'gap_counts': _gap_counts([]), 'gaps': []}
    review_path = draft_dir / 'unit-plan-review-package.json'
    strategy_path = draft_dir / 'test-strategy.json'
    if review_path.exists():
        review_package = _read_json_object(review_path) or {}
        if review_package.get('gap_report') != gap_report:
            review_package = _unit_plan_review_package(
                ready_for_review=_gap_counts(_gaps(gap_report))['critical'] == 0,
                strategy_path=strategy_path,
                gap_path=draft_dir / 'unit-plan-gap-report.json',
                gap_report=gap_report,
            )
            _write_json(review_path, review_package)
    else:
        _write_json(review_path, _unit_plan_review_package(
            ready_for_review=_gap_counts(_gaps(gap_report))['critical'] == 0,
            strategy_path=strategy_path,
            gap_path=draft_dir / 'unit-plan-gap-report.json',
            gap_report=gap_report,
        ))

    critical_gaps = [gap for gap in _gaps(gap_report) if str(gap.get('severity') or '').lower() == 'critical']
    noncritical_gaps = [gap for gap in _gaps(gap_report) if str(gap.get('severity') or '').lower() in {'major', 'minor'}]
    patch_summary = _render_codex_patch_summary(draft_dir)
    if not critical_gaps and not noncritical_gaps and not patch_summary:
        return unit_plan_body

    body = unit_plan_body.rstrip()
    insert_at = body.find('\n## Controller State Patch')
    sections: list[str] = []
    if critical_gaps:
        sections.append(_render_critical_gap_escalation(critical_gaps, gap_report, retry_count=retry_count).rstrip())
    if noncritical_gaps:
        sections.append(_render_test_strategy_gap_report(noncritical_gaps, gap_report, retry_count=retry_count).rstrip())
    if patch_summary:
        sections.append(patch_summary.rstrip())
    gap_block = '\n\n'.join(sections)
    if insert_at == -1:
        return f'{body}\n\n{gap_block}\n'
    return f'{body[:insert_at].rstrip()}\n\n{gap_block}\n{body[insert_at:]}\n'


def _render_codex_patch_summary(draft_dir: Path) -> str:
    strategy_path = draft_dir / 'test-strategy.json'
    if not strategy_path.exists():
        return ''
    strategy = _read_json_object(strategy_path) or {}
    patched: list[tuple[str, dict[str, Any]]] = []
    for ac in strategy.get('acceptance_criteria') or []:
        ac_id = ac.get('id') or '?'
        for tc in ac.get('test_cases') or []:
            if tc.get('codex_patch'):
                patched.append((ac_id, tc))
    if not patched:
        return ''
    lines = [
        '',
        '## 📝 Codex Test Strategist 自动补充',
        '',
        '以下测试用例由 Codex 自动填补策略空缺，请确认合理性（不影响后续执行）：',
        '',
    ]
    for ac_id, tc in patched:
        tc_id = tc.get('id') or '?'
        layer = tc.get('layer') or '?'
        cmd = tc.get('command') or tc.get('evidence') or '(no command)'
        expected = tc.get('expected') or ''
        lines.append(f'- **{tc_id}** (AC: {ac_id} · {layer})')
        lines.append(f'  - 命令/证据: `{cmd}`')
        if expected:
            lines.append(f'  - 预期: {expected}')
    return '\n'.join(lines)



def _render_critical_gap_escalation(gaps: list[dict[str, Any]], gap_report: dict[str, Any], *, retry_count: int) -> str:
    lines = [
        '## ⚠️ Unresolved Critical Test Strategy Gaps — Human Review Required',
        '',
        f'Automatic retry exhausted after {retry_count} attempt(s). The following Critical gaps remain unresolved.',
        'Please review, annotate this gate with concrete fixes, and trigger a revision (r).',
        '',
    ]
    for gap in gaps:
        gap_id = _gap_identifier(gap)
        message = str(gap.get('message') or gap.get('type') or 'No detail provided')
        criterion = gap.get('acceptance_criterion') or gap.get('acceptanceCriterion') or gap.get('criterion')
        suffix = f" (AC: {criterion})" if criterion else ''
        lines.append(f'- `Critical` `{gap_id}`{suffix}: {message}')
        fix = gap.get('suggested_fix')
        if fix:
            lines.append(f'  - Suggested fix: {fix}')
    lines.append('')
    return '\n'.join(lines)


def _render_test_strategy_gap_report(gaps: list[dict[str, Any]], gap_report: dict[str, Any], *, retry_count: int) -> str:
    counts = gap_report.get('gap_counts') if isinstance(gap_report.get('gap_counts'), dict) else _gap_counts(_gaps(gap_report))
    lines = [
        '## Test Strategy Gap Report',
        '',
        f"- Critical: {int(counts.get('critical') or 0)}",
        f"- Major: {int(counts.get('major') or 0)}",
        f"- Minor: {int(counts.get('minor') or 0)}",
        f'- Planner retry count: {retry_count}',
        '',
    ]
    for gap in gaps:
        gap_id = _gap_identifier(gap)
        severity = str(gap.get('severity') or 'Unknown')
        message = str(gap.get('message') or gap.get('type') or 'No detail provided')
        criterion = gap.get('acceptance_criterion') or gap.get('acceptanceCriterion') or gap.get('criterion')
        suffix = f" (AC: {criterion})" if criterion else ''
        lines.append(f'- `{severity}` `{gap_id}`{suffix}: {message}')
        fix = gap.get('suggested_fix')
        if fix:
            lines.append(f'  - Suggested fix: {fix}')
    lines.append('')
    return '\n'.join(lines)



def _gaps(gap_report: dict[str, Any]) -> list[dict[str, Any]]:
    gaps = gap_report.get('gaps') if isinstance(gap_report.get('gaps'), list) else []
    return [gap for gap in gaps if isinstance(gap, dict)]



def _critical_gaps(gap_report: dict[str, Any]) -> list[dict[str, Any]]:
    return [gap for gap in _gaps(gap_report) if str(gap.get('severity') or '').lower() == 'critical']


def _gap_identifier(gap: dict[str, Any]) -> str:
    return str(gap.get('id') or gap.get('type') or gap.get('message') or 'unknown-critical-gap')


def _render_critical_gap_feedback(gaps: list[dict[str, Any]], next_retry_count: int) -> str:
    lines = [
        '## Critical Test Strategy Gap Feedback',
        '',
        f'Planner retry count after this revision: {next_retry_count}',
        '',
        'Resolve these Critical gaps before the Unit Plan can enter human approval:',
    ]
    for gap in gaps:
        criterion = gap.get('acceptance_criterion') or gap.get('acceptanceCriterion') or gap.get('criterion')
        suffix = f" (AC: {criterion})" if criterion else ''
        lines.append(f"- {_gap_identifier(gap)}{suffix}: {gap.get('message') or gap.get('type') or 'Critical gap'}")
        fix = gap.get('suggested_fix')
        if fix:
            lines.append(f"  Suggested fix: {fix}")
    lines.append('')
    return '\n'.join(lines)


def _dedupe_gaps(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for gap in gaps:
        key = (
            str(gap.get('severity') or ''),
            str(gap.get('type') or ''),
            str(gap.get('message') or ''),
        )
        if key not in seen:
            seen.add(key)
            unique.append(gap)
    return unique


def _test_strategy_gaps(strategy: dict[str, Any]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    criteria = strategy.get('acceptance_criteria')
    if not isinstance(criteria, list):
        return [
            {
                'severity': 'Critical',
                'type': 'missing_acceptance_criteria_mapping',
                'message': 'test-strategy.json must include acceptance_criteria mappings',
            }
        ]
    for criterion in criteria:
        if not isinstance(criterion, dict):
            continue
        criterion_id = str(criterion.get('id') or criterion.get('acceptance_criterion') or 'unknown')
        cases = criterion.get('test_cases')
        if not isinstance(cases, list) or not cases:
            gaps.append({
                'severity': 'Critical',
                'type': 'missing_acceptance_criterion_mapping',
                'message': f'{criterion_id} has no mapped test cases',
            })
            continue
        if all(_test_case_is_static_only(case) for case in cases if isinstance(case, dict)):
            gaps.append({
                'severity': 'Critical',
                'type': 'static_only_coverage',
                'message': f'{criterion_id} is covered only by static checks',
            })
        for case in cases:
            if isinstance(case, dict) and not (case.get('command') or case.get('evidence')):
                gaps.append({
                    'severity': 'Major',
                    'type': 'missing_command_or_evidence',
                    'message': f"{case.get('id') or criterion_id} lacks command or evidence",
                })
    return gaps


def _test_case_is_static_only(case: dict[str, Any]) -> bool:
    layer = str(case.get('layer') or '').lower()
    command = str(case.get('command') or '').lower()
    if layer in {'unit', 'functional', 'integration', 'e2e', 'manual'}:
        return False
    static_tokens = ['tsc', 'eslint', 'biome check', 'prettier', 'typecheck', 'type-check', 'lint']
    return layer in {'static', 'lint', 'typecheck'} or any(token in command for token in static_tokens)


def _gap_counts(gaps: list[dict[str, Any]]) -> dict[str, int]:
    counts = {'critical': 0, 'major': 0, 'minor': 0}
    for gap in gaps:
        severity = str(gap.get('severity') or '').lower()
        if severity in counts:
            counts[severity] += 1
    return counts


def run_ui_design_if_needed(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> StepResult:
    if dry_run:
        return _write_json_result(
            unit_dir / 'ui-design-summary.json',
            {
                'unit_id': state.get('currentUnitId'),
                'status': 'ok',
                'mode': 'dry-run',
                'generated_at': _now_iso(),
            },
            summary='dry-run ui design complete',
        )
    unit = _find_unit(state, state.get('currentUnitId'))
    scope = unit.get('scope') or []
    non_goals = unit.get('non_goals') or []
    done_when = unit.get('done_when') or []
    payload = {
        'unit_id': state.get('currentUnitId'),
        'unit_name': unit.get('name', state.get('currentUnitId')),
        'status': 'ok',
        'mode': 'local-ui-design-brief',
        'requested_outcome': state.get('requestedOutcome'),
        'objective': _find_objective_for_unit(state, state.get('currentUnitId')),
        'scope': scope,
        'non_goals': non_goals,
        'done_when': done_when,
        'design_checks': [
            'Confirm primary user path is visible without relying on implementation notes.',
            'Confirm UI states cover loading, empty, error, success, and retry paths where applicable.',
            'Confirm verification includes browser-visible evidence when the unit changes UI behavior.',
        ],
        'generated_at': _now_iso(),
    }
    unit_dir.mkdir(parents=True, exist_ok=True)
    _write_json(unit_dir / 'ui-design-summary.json', payload)
    (unit_dir / 'ui-design-brief.md').write_text(
        _render_ui_design_brief(payload),
        encoding='utf-8',
    )
    return StepResult(
        summary='ui design brief complete',
        outputs=['ui-design-summary.json', 'ui-design-brief.md'],
    )


def run_builder(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> StepResult:
    if dry_run:
        unit_dir.mkdir(parents=True, exist_ok=True)
        _write_json(unit_dir / 'builder-summary.json', {
            'unit_id': state.get('currentUnitId'),
            'status': 'ok',
            'mode': 'dry-run',
            'generated_at': _now_iso(),
        })
        (unit_dir / 'changed-files.txt').write_text('src/example.py\n', encoding='utf-8')
        (unit_dir / 'red-test.txt').write_text('FAILED test_example\n', encoding='utf-8')
        (unit_dir / 'green-test.txt').write_text('PASSED test_example\n', encoding='utf-8')
        return StepResult(summary='dry-run builder complete', outputs=[
            'builder-summary.json', 'changed-files.txt', 'red-test.txt', 'green-test.txt'
        ])

    workspace_path = state.get('executionWorkspacePath') or state.get('workspacePath')
    prompt_path = state.get('builderPromptPath') or state.get('promptPath')
    if workspace_path and prompt_path:
        unit_dir.mkdir(parents=True, exist_ok=True)
        workspace_dir = Path(workspace_path)
        agent_result = run_agent_for_current_step(state, workspace_dir, Path(prompt_path), artifact_dir=unit_dir)
        baseline_changed_files = set(state.get('baselineChangedFiles') or [])
        changed_files = [
            path for path in collect_git_changed_files(workspace_dir)
            if path not in baseline_changed_files
        ]
        if not changed_files:
            unit = _find_unit(state, state.get('currentUnitId'))
            changed_files = unit.get('changed_files') or []

        _write_json(unit_dir / 'builder-summary.json', {
            'task_id': state.get('task_id'),
            'unit_id': state.get('currentUnitId'),
            'mode': agent_result.backend if agent_result.backend != 'subprocess' else 'claude-code',
            'runner_status': agent_result.status,
            'runner_run_dir': agent_result.run_dir,
            'done_payload': agent_result.done_payload or {},
            'agent_command': agent_result.command,
            'runner_metadata': agent_result.runner_metadata or {},
            'exit_code': agent_result.returncode,
            'stdout': agent_result.stdout,
            'stderr': agent_result.stderr,
            'changed_files': changed_files,
            'prompt_path': str(prompt_path),
            'generated_at': _now_iso(),
        })
        (unit_dir / 'changed-files.txt').write_text(
            '\n'.join(changed_files) + ('\n' if changed_files else ''),
            encoding='utf-8',
        )
        if agent_result.returncode != 0:
            tmux_hint = ''
            if agent_result.backend == 'tmux-claude':
                tmux_hint = f" tmux target {state.get('tmuxTarget')!s} failed."
            stderr_hint = f" stderr: {agent_result.stderr.strip()}" if agent_result.stderr.strip() else ''
            raise RuntimeError(
                f"Builder agent failed with exit code {agent_result.returncode}.{tmux_hint}{stderr_hint} "
                f"See {unit_dir / 'builder-summary.json'}"
            )
        return StepResult(
            summary='builder complete',
            outputs=['builder-summary.json', 'changed-files.txt'],
        )

    unit_dir.mkdir(parents=True, exist_ok=True)
    current_unit_id = state.get('currentUnitId')
    unit = _find_unit(state, current_unit_id)
    changed_files = unit.get('changed_files') or [f'src/{current_unit_id}.py']
    verification_commands = unit.get('verification_commands') or ['pytest -q']
    scope = unit.get('scope') or []
    non_goals = unit.get('non_goals') or []
    objective = _find_objective_for_unit(state, current_unit_id)

    builder_payload = {
        'task_id': state.get('task_id'),
        'unit_id': current_unit_id,
        'unit_name': unit.get('name', current_unit_id),
        'requested_outcome': state.get('requestedOutcome'),
        'objective': objective,
        'scope': scope,
        'non_goals': non_goals,
        'changed_files': changed_files,
        'verification_commands': verification_commands,
        'generated_at': _now_iso(),
    }
    _write_json(unit_dir / 'builder-summary.json', builder_payload)
    (unit_dir / 'changed-files.txt').write_text('\n'.join(changed_files) + '\n', encoding='utf-8')
    (unit_dir / 'red-test.txt').write_text(f'FAILED {current_unit_id} initial check\n', encoding='utf-8')
    (unit_dir / 'green-test.txt').write_text(f'PASSED {current_unit_id} verification\n', encoding='utf-8')
    return StepResult(
        summary='builder complete',
        outputs=['builder-summary.json', 'changed-files.txt', 'red-test.txt', 'green-test.txt'],
    )


def prepare_builder_prompt(state: dict[str, Any], approvals_dir: Path, unit_dir: Path) -> Path | None:
    if not state.get('humanGatesRequired'):
        return None
    if not (state.get('workspacePath') or state.get('executionWorkspacePath')) or not state.get('promptPath'):
        return None

    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    unit_plan_path = approvals_dir / 'unit-plan.md'
    requirements_content = _approved_gate_content(requirements_path, 'requirements')
    unit_plan_content = _approved_gate_content(unit_plan_path, 'unit plan')

    original_prompt_path = Path(state.get('originalPromptPath') or state.get('promptPath'))
    original_prompt = ''
    if original_prompt_path.exists():
        original_prompt = original_prompt_path.read_text(encoding='utf-8')

    unit_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = unit_dir / 'builder-prompt.md'
    prompt_path.write_text(
        _render_builder_execution_prompt(
            state=state,
            requirements_path=requirements_path,
            requirements_content=requirements_content,
            unit_plan_path=unit_plan_path,
            unit_plan_content=unit_plan_content,
            original_prompt_path=original_prompt_path,
            original_prompt=original_prompt,
            previous_failure_feedback=_render_previous_controller_failure_feedback(unit_dir),
        ),
        encoding='utf-8',
    )
    state.setdefault('originalPromptPath', str(original_prompt_path))
    state['builderPromptPath'] = str(prompt_path)
    return prompt_path


def _approved_gate_content(path: Path, gate_name: str) -> str:
    gate = check_gate_file(path)
    if not gate.approved:
        raise RuntimeError(f'{gate_name} gate is not approved: {gate.reason}')
    return path.read_text(encoding='utf-8')


def _render_builder_execution_prompt(
    *,
    state: dict[str, Any],
    requirements_path: Path,
    requirements_content: str,
    unit_plan_path: Path,
    unit_plan_content: str,
    original_prompt_path: Path,
    original_prompt: str,
    previous_failure_feedback: str,
) -> str:
    unit = _find_unit(state, state.get('currentUnitId'))
    coverage = [
        item
        for item in state.get('objectiveCoverage') or []
        if state.get('currentUnitId') in (item.get('units') or [])
    ]
    final_rejection_feedback = state.get('finalAcceptanceRejectionFeedback')
    final_rejection_route = state.get('finalAcceptanceRejectionRoute')
    final_rejection_section = ''
    if final_rejection_feedback and final_rejection_route in {None, 'implementation', 'defect_fix'}:
        if final_rejection_route == 'defect_fix':
            heading = 'Final acceptance defect-fix feedback from the previous attempt'
            route_instruction = (
                '\nThis is an approved defect-fix unit generated from final acceptance. '
                'Fix only the defects in this unit scope and the feedback below; do not treat this as a requirements change.\n'
            )
        else:
            heading = 'Final acceptance rejection feedback from the previous attempt'
            route_instruction = ''
        final_rejection_section = f"""
{heading}:

```md
{final_rejection_feedback}
```
{route_instruction}
"""
    previous_failure_section = ''
    if previous_failure_feedback:
        previous_failure_section = f"""
Previous controller failure feedback:

The controller rejected the previous attempt after running its own checks. Treat this as primary debugging context.
The controller will rerun the approved verification commands exactly; do not mark DONE only because a manually modified command passed.

{previous_failure_feedback}
"""
    return f"""You are executing one approved workflow-controller unit.

Use the approved human gate documents as the source of truth. Do not expand scope beyond them.
If the approved requirements, Unit Plan, or current workspace make the task impossible, stop and report BLOCKED with the exact missing decision.

Execution workspace: {state.get('executionWorkspacePath') or state.get('workspacePath')}
Task id: {state.get('task_id')}
Current unit id: {state.get('currentUnitId')}
Requested outcome: {state.get('requestedOutcome')}

Current unit from approved Controller State Patch:

```json
{json.dumps(unit, ensure_ascii=False, indent=2)}
```

Objectives covered by this unit:

```json
{json.dumps(coverage, ensure_ascii=False, indent=2)}
```

Approved requirements gate: {requirements_path}

```md
{requirements_content}
```

Approved unit plan gate: {unit_plan_path}

```md
{unit_plan_content}
```

Original Ralph prompt/context: {original_prompt_path}

```md
{original_prompt}
```
{final_rejection_section}
{previous_failure_section}

Builder rules:
- Implement the shortest verifiable path for the current unit only.
- Follow the Unit Plan scope, non-goals, done_when, and verification_commands.
- Add or update the mapped Unit Plan test cases before implementation where code behavior changes.
- For defect-fix units, add a regression test for each defect when feasible; if not feasible, leave explicit manual evidence.
- Preserve already accepted work.
- Leave clear evidence for the verifier.
"""


def _render_previous_controller_failure_feedback(unit_dir: Path) -> str:
    sections: list[str] = []

    review = _read_json_object(unit_dir / 'review.json')
    if review and review.get('passed') is False:
        sections.append(_format_failed_review_feedback(review))

    verification = _read_json_object(unit_dir / 'verification.json')
    if verification and verification.get('passed') is False:
        sections.append(_format_failed_verification_feedback(verification))

    return '\n\n'.join(section for section in sections if section)


def _format_failed_review_feedback(review: dict[str, Any]) -> str:
    issues = review.get('issues') or []
    issue_lines = '\n'.join(
        f"- {issue.get('severity', 'unknown')} {issue.get('type', 'issue')}: {issue.get('message', '')}"
        for issue in issues
        if isinstance(issue, dict)
    )
    if not issue_lines:
        issue_lines = '- Review failed without structured issues.'
    return f"""## Previous review failure

Issues:
{issue_lines}"""


def _format_failed_verification_feedback(verification: dict[str, Any]) -> str:
    issues = verification.get('issues') or []
    issue_lines = '\n'.join(
        f"- {issue.get('severity', 'unknown')} {issue.get('type', 'issue')}: {issue.get('message', '')}"
        for issue in issues
        if isinstance(issue, dict)
    )
    if not issue_lines:
        issue_lines = '- Verification failed without structured issues.'

    results = [
        result for result in verification.get('results') or []
        if isinstance(result, dict) and not result.get('ok')
    ]
    result_blocks = '\n\n'.join(_format_failed_command_result(result) for result in results[:3])
    if len(results) > 3:
        result_blocks += f'\n\n... {len(results) - 3} additional failed command result(s) omitted.'
    if not result_blocks:
        result_blocks = 'No failed command result payload was recorded.'

    return f"""## Previous verification failure

Issues:
{issue_lines}

Failed command results:
{result_blocks}"""


def _format_failed_command_result(result: dict[str, Any]) -> str:
    lines = [
        f"- command: {result.get('command', '')}",
        f"- returncode: {result.get('returncode')}",
    ]
    stdout = _tail_text(str(result.get('stdout') or '').strip())
    stderr = _tail_text(str(result.get('stderr') or '').strip())
    if stdout:
        lines.append(f"- stdout tail:\n```text\n{stdout}\n```")
    if stderr:
        lines.append(f"- stderr tail:\n```text\n{stderr}\n```")
    return '\n'.join(lines)


def _tail_text(text: str, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return f'... truncated ...\n{text[-max_chars:]}'


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _render_ui_design_brief(payload: dict[str, Any]) -> str:
    scope = '\n'.join(f"- {item}" for item in payload.get('scope') or []) or '- Not specified'
    non_goals = '\n'.join(f"- {item}" for item in payload.get('non_goals') or []) or '- Not specified'
    checks = '\n'.join(f"- {item}" for item in payload.get('design_checks') or [])
    return f"""# UI Design Brief

Unit: `{payload.get('unit_id')}` - {payload.get('unit_name')}
Requested outcome: `{payload.get('requested_outcome')}`
Objective: {payload.get('objective') or 'Not specified'}

## Scope
{scope}

## Non-goals
{non_goals}

## Design Checks
{checks}
"""


def _render_requirements_draft_prompt(state: dict[str, Any], body_path: Path) -> str:
    unit = _find_unit(state, state.get('currentUnitId'))
    context_files = '\n'.join(f'- {path}' for path in state.get('targetContextFiles') or [])
    verification_commands = '\n'.join(
        f"- `{command}`" for command in (unit.get('verification_commands') or state.get('verificationCommands') or [])
    ) or '- Not specified'
    done_when = '\n'.join(f"- {item}" for item in unit.get('done_when') or []) or '- Infer from the target and context files'
    scope = '\n'.join(f"- {item}" for item in unit.get('scope') or []) or '- Infer from the target and context files'
    non_goals = '\n'.join(f"- {item}" for item in unit.get('non_goals') or []) or '- Do not expand beyond the requested target'
    revision_feedback = state.get('requirementsRevisionFeedback')
    revision_section = ''
    if revision_feedback:
        revision_section = f"""
已有草案及人工批注：

```md
{revision_feedback}
```

请在重新生成的 Markdown 正文中解决这些人工批注。除非审阅意见本身属于最终需求内容，否则不要把审阅者评论原样带入正文。
"""

    return f"""为 workflow-controller 生成“需求与验收确认”Markdown 正文。

将 Markdown 正文写入这个精确文件：
{body_path}
Write the Markdown body to this exact file:
{body_path}

使用简体中文展示所有面向人工审阅的标题、说明、表格、清单、证据和验收内容。
保留命令、路径、代码标识符、JSON key、HTTP route、枚举值、文件名和产品名的原文。
不要包含 `## Human Confirmation` 段落；controller 会自动追加确认段落和内容 hash。
不要修改应用源代码；这是规划/门禁文档生成任务。
使用 `test-strategy` skill 将每条验收标准映射到适当验证层级、具体测试用例、命令、fixture、环境和人工证据。

目标：
- 请求目标：`{state.get('requestedOutcome')}`
- 可行目标：`{state.get('feasibleOutcome')}`
- 当前单元 id：`{state.get('currentUnitId')}`
- 当前单元名称：`{unit.get('name', state.get('currentUnitId'))}`

已知范围：
{scope}

已知非目标：
{non_goals}

已知完成条件 / 验收提示：
{done_when}

已知验证命令：
{verification_commands}

如存在，请读取这些上下文文件：
{context_files or '- None'}

{revision_section}

必须使用以下 Markdown 结构：

# 需求与验收确认

## 1. 需求

## 2. 用户旅程

覆盖正常路径、异常路径、角色/权限路径、重试/恢复路径、持久化/数据路径，以及适用的导入/导出或集成路径。

## 3. 验收标准

使用可观察、可测试的标准。每条标准都要说明可证明它的证据。

## 4. 测试策略（Test Strategy）

按适用情况区分单元测试、功能/API 测试、集成检查和 E2E/人工验收。

## 5. 范围外

## 6. 产品设计概要

描述核心用户流程（正常路径 + 主要异常路径）、关键页面或系统状态的文字/ASCII 示意；如果没有 UI，就描述 API 响应结构、CLI 输出或关键状态变化；再补充“完成后应该长什么样”的验收示意。

## 7. 架构概要

描述参与本次变更的模块边界与职责划分、核心数据流（输入 → 处理 → 输出）、外部依赖（系统/服务/API/环境），以及主要技术风险和约束。

## 8. 人工审阅清单

使用未勾选的 Markdown checkbox。
"""


def _render_unit_plan_draft_prompt(state: dict[str, Any], requirements_path: Path, body_path: Path) -> str:
    requirements_content = ''
    if requirements_path.exists():
        requirements_content = requirements_path.read_text(encoding='utf-8')
    unit = _find_unit(state, state.get('currentUnitId'))
    context_files = '\n'.join(f'- {path}' for path in state.get('targetContextFiles') or [])
    units = json.dumps(state.get('units') or [], ensure_ascii=False, indent=2)
    coverage = json.dumps(state.get('objectiveCoverage') or [], ensure_ascii=False, indent=2)
    revision_feedback = state.get('unitPlanRevisionFeedback')
    revision_section = ''
    if revision_feedback:
        revision_section = f"""
已有 Unit Plan 草案及人工批注：

```md
{revision_feedback}
```

请在重新生成的 Markdown 正文中解决这些人工批注。保持 `Controller State Patch` 与人工可读的 Unit Plan 章节一致。
"""
    defect_fix_section = ''
    if state.get('unitPlanRevisionMode') == 'defect_fix' or state.get('finalAcceptanceRejectionRoute') == 'defect_fix':
        defect_fix_section = """
最终验收缺陷修复模式：
- 将最终验收反馈视为已批准需求下的缺陷。
- 不要修改已批准需求，也不要重新解释请求目标。
- 生成一个或多个只聚焦最终验收缺陷的 bug-fix 单元。
- 将受影响的已覆盖目标重新打开为 `partial`，并在 objectiveCoverage 中加入新的 bug-fix unit id。
- 除非必须重新执行，否则已完成单元不要放回 `units`；`units` 应只包含下一步要执行的缺陷修复单元。
- 将 `currentUnitId` 设置为第一个缺陷修复单元。
"""

    return f"""为 workflow-controller 生成“单元计划确认”Markdown 正文。

将 Unit Plan Markdown 正文写入这个精确文件：
{body_path}
Write the Unit Plan Markdown body to this exact file:
{body_path}

使用简体中文展示所有面向人工审阅的标题、说明、表格、清单、证据和验收内容。
保留命令、路径、代码标识符、JSON key、HTTP route、枚举值、文件名和产品名的原文。
控制器状态补丁标题可使用 `## 控制器状态补丁` 或 `## Controller State Patch`，正文必须包含 fenced JSON patch。
不要包含 `## Human Confirmation` 段落；controller 会自动追加确认段落和内容 hash。
不要修改应用源代码；这是规划/门禁文档生成任务。
使用 `test-strategy` skill 将每条验收标准映射到适当验证层级、具体测试用例、命令、fixture、环境和人工证据。

以下已批准需求与验收门禁是事实来源：

```md
{requirements_content}
```

目标：
- 请求目标：`{state.get('requestedOutcome')}`
- 可行目标：`{state.get('feasibleOutcome')}`
- 当前单元 id：`{state.get('currentUnitId')}`
- 当前单元名称：`{unit.get('name', state.get('currentUnitId'))}`

controller state 中的已知目标覆盖：

```json
{coverage}
```

controller state 中的已知单元：

```json
{units}
```

如存在，请读取这些上下文文件：
{context_files or '- None'}

{revision_section}
{defect_fix_section}

必须使用以下 Markdown 结构：

# 单元计划确认（Unit Plan Confirmation）

## 目标覆盖矩阵

将每条需求和验收标准映射到一个或多个单元。

## 测试用例矩阵（Test Case Matrix）

创建一张表，表达以下精确映射：

Acceptance Criterion -> Test Case -> Layer -> Command/Evidence -> Expected Result

缺陷修复模式下，每条验收标准和每个最终验收缺陷都必须至少有一个具体测试用例或明确人工证据。typecheck/lint/tsc 等静态检查可以出现，但不能单独算作行为覆盖。

## 执行单元

每个单元必须包含：
- 范围
- 非目标
- 覆盖目标
- 覆盖验收标准
- 影响的工作流片段
- 工作流验证层级：`fragment` 或 `closure`
- 完成条件
- 映射到测试用例矩阵的测试用例
- 验证命令
- 命令依赖的验证环境，例如 Playwright/E2E 数据库测试需要的 `DATABASE_URL`
- 所需证据
- 风险

## 控制器状态补丁

包含一个 fenced `json` 对象，controller 会在人工批准后安全应用：

```json
{{
  "currentUnitId": "<first unit to execute>",
  "objectiveCoverage": [
    {{"objective": "<objective>", "units": ["<unit-id>"], "status": "partial"}}
  ],
  "units": [
    {{
      "id": "<unit-id>",
      "name": "<unit name>",
      "passes": false,
      "scope": ["<scope item>"],
      "non_goals": ["<non-goal item>"],
      "done_when": ["<observable completion condition>"],
      "workflow_validation_level": "fragment",
      "test_cases": [
        {{
          "id": "<stable test case id>",
          "acceptance_criterion": "<criterion or defect covered>",
          "layer": "unit|functional|integration|e2e|manual",
          "command": "<verification command if automated>",
          "evidence": "<manual evidence if not automated>",
          "expected": "<observable expected result>"
        }}
      ],
      "verification_commands": ["<command>"],
      "verification_env": {{"DATABASE_URL": "<test database url if required>"}}
    }}
  ],
  "currentUnitNeedsUiDesign": false
}}
```

JSON 必须合法，且 `units` 必须列出下一步要执行的每个可执行单元。
每个未完成的 `partial` objectiveCoverage unit id 都必须存在于 `units`。
已完成的既有 unit id 如果在 objectiveCoverage 中标记为 `covered`，可以不出现在 `units` 中；这用于同时引用已完成和剩余工作的 rollup objective。
除非必须重新执行，否则不要把已经 covered 的历史单元重新加入 `units`。
如果用更小的可执行单元替换合成 target unit，请从 partial objectiveCoverage 中移除合成 target unit id，或将该 objective 映射到新的可执行 unit id。

## 人工审阅清单

使用未勾选的 Markdown checkbox。
"""


def run_refiner(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> StepResult:
    if dry_run:
        return _write_json_result(
            unit_dir / 'refinement-summary.json',
            {
                'unit_id': state.get('currentUnitId'),
                'status': 'ok',
                'mode': 'dry-run',
                'changes': ['simplified example logic'],
                'generated_at': _now_iso(),
            },
            summary='dry-run refinement complete',
        )

    current_unit_id = state.get('currentUnitId')
    changed_files_path = unit_dir / 'changed-files.txt'
    changed_files = []
    if changed_files_path.exists():
        changed_files = [line.strip() for line in changed_files_path.read_text(encoding='utf-8').splitlines() if line.strip()]

    refinement_payload = {
        'unit_id': current_unit_id,
        'status': 'ok',
        'mode': 'local-heuristic-refiner',
        'changes': [f'reviewed {len(changed_files)} changed file(s) for simplification opportunities'],
        'changed_files': changed_files,
        'generated_at': _now_iso(),
    }
    _write_json(unit_dir / 'refinement-summary.json', refinement_payload)
    return StepResult(summary='refinement complete', outputs=['refinement-summary.json'])


def run_reviewer(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> StepResult:
    if dry_run:
        return _write_json_result(
            unit_dir / 'review.json',
            {
                'unit_id': state.get('currentUnitId'),
                'passed': True,
                'issues': [],
                'reviewer': 'dry-run-reviewer',
                'reviewed_at': _now_iso(),
            },
            summary='dry-run review passed',
        )

    if state.get('workspacePath'):
        issues: list[dict[str, str]] = []
        builder_path = unit_dir / 'builder-summary.json'
        changed_files_path = unit_dir / 'changed-files.txt'
        refinement_path = unit_dir / 'refinement-summary.json'

        if not builder_path.exists():
            issues.append(_issue('missing_builder_summary', 'Missing builder summary artifact'))
        else:
            builder = json.loads(builder_path.read_text(encoding='utf-8'))
            if builder.get('exit_code') != 0:
                issues.append(_issue('builder_failed', 'Builder agent did not exit cleanly'))

        if not changed_files_path.exists():
            issues.append(_issue('missing_changed_files', 'Missing changed files artifact'))
        else:
            changed_files = [
                line.strip()
                for line in changed_files_path.read_text(encoding='utf-8').splitlines()
                if line.strip()
            ]
            if not changed_files and not _allows_verification_only_acceptance(state, builder if builder_path.exists() else {}):
                issues.append(_issue('empty_changed_files', 'Builder did not leave detectable git changes'))

        if not refinement_path.exists():
            issues.append(_issue('missing_refinement_summary', 'Missing refinement summary artifact'))

        review_payload = {
            'unit_id': state.get('currentUnitId'),
            'passed': not issues,
            'issues': issues,
            'reviewer': 'real-runtime-reviewer',
            'reviewed_at': _now_iso(),
        }
        _write_json(unit_dir / 'review.json', review_payload)
        return StepResult(summary='review passed' if not issues else 'review failed', outputs=['review.json'])

    issues: list[dict[str, str]] = []
    current_unit_id = state.get('currentUnitId')

    required_files = {
        'builder-summary.json': ('missing_builder_summary', 'Missing builder summary artifact'),
        'changed-files.txt': ('missing_changed_files', 'Missing changed files artifact'),
        'red-test.txt': ('missing_red_test', 'Missing failing test evidence'),
        'green-test.txt': ('missing_green_test', 'Missing passing test evidence'),
        'refinement-summary.json': ('missing_refinement_summary', 'Missing refinement summary artifact'),
    }

    for filename, (issue_type, message) in required_files.items():
        if not (unit_dir / filename).exists():
            issues.append(_issue(issue_type, message))

    green_test_path = unit_dir / 'green-test.txt'
    if green_test_path.exists():
        green_content = green_test_path.read_text(encoding='utf-8')
        if 'PASS' not in green_content.upper():
            issues.append(_issue('green_test_not_passing', 'green-test.txt does not show a passing result'))

    red_test_path = unit_dir / 'red-test.txt'
    if red_test_path.exists():
        red_content = red_test_path.read_text(encoding='utf-8')
        if 'FAIL' not in red_content.upper():
            issues.append(_issue('red_test_not_failing', 'red-test.txt does not show a failing result'))

    changed_files_path = unit_dir / 'changed-files.txt'
    if changed_files_path.exists():
        changed_files = [line.strip() for line in changed_files_path.read_text(encoding='utf-8').splitlines() if line.strip()]
        if not changed_files:
            issues.append(_issue('empty_changed_files', 'changed-files.txt is empty'))

    review_payload = {
        'unit_id': current_unit_id,
        'passed': not issues,
        'issues': issues,
        'reviewer': 'local-heuristic-reviewer',
        'reviewed_at': _now_iso(),
    }
    _write_json(unit_dir / 'review.json', review_payload)
    return StepResult(summary='review passed' if not issues else 'review failed', outputs=['review.json'])


def run_verifier(
    state: dict[str, Any],
    unit_dir: Path,
    dry_run: bool = False,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> StepResult:
    if dry_run:
        return _write_json_result(
            unit_dir / 'verification.json',
            {
                'unit_id': state.get('currentUnitId'),
                'passed': True,
                'commands': ['pytest tests/test_example.py -q'],
                'evidence_files': ['green-test.txt'],
                'verified_at': _now_iso(),
            },
            summary='dry-run verification passed',
        )

    workspace_path = state.get('executionWorkspacePath') or state.get('workspacePath')
    commands = verification_commands_for_state(state)
    if workspace_path and commands:
        unit_dir.mkdir(parents=True, exist_ok=True)
        results = run_verification_commands(
            state,
            Path(workspace_path),
            progress_callback=progress_callback,
        )
        issues = [
            _issue('verification_command_failed', f"Command failed: {result['command']}")
            for result in results
            if not result['ok']
        ]
        combined_stdout = '\n'.join(result['stdout'] for result in results if result.get('stdout'))
        combined_stderr = '\n'.join(result['stderr'] for result in results if result.get('stderr'))
        evidence = 'PASSED\n' if not issues else 'FAILED\n'
        (unit_dir / 'green-test.txt').write_text(
            evidence + combined_stdout + combined_stderr,
            encoding='utf-8',
        )
        verification_payload = {
            'unit_id': state.get('currentUnitId'),
            'passed': not issues,
            'issues': issues,
            'commands': commands,
            'results': results,
            'evidence_files': ['green-test.txt'],
            'verified_at': _now_iso(),
        }
        _write_json(unit_dir / 'verification.json', verification_payload)
        return StepResult(
            summary='verification passed' if not issues else 'verification failed',
            outputs=['verification.json', 'green-test.txt'],
        )

    issues: list[dict[str, str]] = []
    current_unit_id = state.get('currentUnitId')
    evidence_files: list[str] = []

    green_test_path = unit_dir / 'green-test.txt'
    if not green_test_path.exists():
        issues.append(_issue('missing_green_test', 'Missing passing test evidence'))
    else:
        evidence_files.append('green-test.txt')
        green_content = green_test_path.read_text(encoding='utf-8')
        if 'PASS' not in green_content.upper():
            issues.append(_issue('green_test_not_passing', 'green-test.txt does not show a passing result'))

    verification_payload = {
        'unit_id': current_unit_id,
        'passed': not issues,
        'issues': issues,
        'commands': ['inspect green-test.txt for pass evidence'],
        'evidence_files': evidence_files,
        'verified_at': _now_iso(),
    }
    _write_json(unit_dir / 'verification.json', verification_payload)
    return StepResult(summary='verification passed' if not issues else 'verification failed', outputs=['verification.json'])


def ask_human_scope_approval(state: dict[str, Any], approvals_dir: Path, dry_run: bool = False) -> StepResult:
    if dry_run or _approval_requested_by_state(state):
        approvals_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            approvals_dir / 'scope-approval.json',
            {
                'type': 'scope_approval',
                'approved': True,
                'actor': 'dry-run-human' if dry_run else 'auto-approve',
                'approved_at': _now_iso(),
            },
        )
        return StepResult(approved=True, summary='scope approval granted', outputs=['scope-approval.json'])

    approval_path = approvals_dir / 'scope-approval.json'
    if approval_path.exists():
        payload = json.loads(approval_path.read_text(encoding='utf-8'))
        return StepResult(approved=bool(payload.get('approved')), summary='scope approval loaded', outputs=['scope-approval.json'])

    raise NotImplementedWorkflowStep(
        'Scope approval required. Provide approvals/scope-approval.json or run with --auto-approve.'
    )


def ask_human_release_approval(state: dict[str, Any], approvals_dir: Path, dry_run: bool = False) -> StepResult:
    if dry_run or _approval_requested_by_state(state):
        approvals_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            approvals_dir / 'release-approval.json',
            {
                'type': 'release_approval',
                'approved': True,
                'actor': 'dry-run-human' if dry_run else 'auto-approve',
                'approved_at': _now_iso(),
            },
        )
        return StepResult(approved=True, summary='release approval granted', outputs=['release-approval.json'])

    approval_path = approvals_dir / 'release-approval.json'
    if approval_path.exists():
        payload = json.loads(approval_path.read_text(encoding='utf-8'))
        return StepResult(approved=bool(payload.get('approved')), summary='release approval loaded', outputs=['release-approval.json'])

    raise NotImplementedWorkflowStep(
        'Release approval required. Provide approvals/release-approval.json or run with --auto-approve.'
    )


def select_next_unit(state: dict[str, Any]) -> str:
    units: list[dict[str, Any]] = state.get('units', [])
    for unit in units:
        if not unit.get('passes'):
            return unit['id']
    return 'RELEASE_GATE'


def mark_current_unit_covered(state: dict[str, Any]) -> None:
    current_unit_id = state.get('currentUnitId')
    for unit in state.get('units', []):
        if unit.get('id') == current_unit_id:
            unit['passes'] = True
    for item in state.get('objectiveCoverage', []):
        if current_unit_id in item.get('units', []):
            item['status'] = 'covered' if objective_coverage_units_passed(state, item) else 'partial'


def target_acceptance_covered(state: dict[str, Any]) -> bool:
    current_unit_id = state.get('currentUnitId')
    if state.get('targetMatchedPlanStep') is not False:
        return False
    if not str(current_unit_id or '').startswith('target-'):
        return False
    for item in state.get('objectiveCoverage', []):
        if current_unit_id in item.get('units', []):
            return item.get('status') == 'covered'
    return False


def _find_unit(state: dict[str, Any], unit_id: str | None) -> dict[str, Any]:
    for unit in state.get('units', []):
        if unit.get('id') == unit_id:
            return unit
    return {'id': unit_id or 'unknown-unit'}


def _find_objective_for_unit(state: dict[str, Any], unit_id: str | None) -> str | None:
    for item in state.get('objectiveCoverage', []):
        if unit_id in item.get('units', []):
            return item.get('objective')
    return None


def _allows_verification_only_acceptance(state: dict[str, Any], builder: dict[str, Any]) -> bool:
    if builder.get('exit_code') not in {0, None}:
        return False
    if builder.get('runner_status') not in {'done', None}:
        return False
    done_payload = builder.get('done_payload') or {}
    if done_payload and done_payload.get('status') not in {'done', None}:
        return False
    unit = _find_unit(state, state.get('currentUnitId'))
    commands = unit.get('verification_commands') or state.get('verificationCommands') or []
    return bool(commands)


def _issue(issue_type: str, message: str, severity: str = 'high') -> dict[str, str]:
    return {
        'severity': severity,
        'type': issue_type,
        'message': message,
    }


def _write_json_result(path: Path, payload: dict[str, Any], summary: str) -> StepResult:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, payload)
    return StepResult(summary=summary, outputs=[path.name])


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
