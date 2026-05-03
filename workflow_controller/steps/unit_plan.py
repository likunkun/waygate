from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from workflow_controller.runners import RunnerRequest, make_runner, run_agent_backend
from workflow_controller.gates import render_unit_plan_gate_body, write_gate_file
from workflow_controller.prompts.unit_plan import (
    _render_unit_plan_draft_prompt,
    _render_test_strategist_prompt,
    _render_test_strategist_patch_prompt,
    _render_codex_patch_summary,
    _render_critical_gap_escalation,
    _render_test_strategy_gap_report,
    _gap_identifier,
    _gap_counts_from_list,
)
from workflow_controller.steps._common import (
    StepResult,
    TestStrategistFallbackBlocked,
    _write_json,
    _read_json_object,
    _now_iso,
)


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
    strategy = _read_json_object(strategy_path) or {}
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
    patch_summary = _render_codex_patch_summary(draft_dir, strategy)
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


def _gaps(gap_report: dict[str, Any]) -> list[dict[str, Any]]:
    gaps = gap_report.get('gaps') if isinstance(gap_report.get('gaps'), list) else []
    return [gap for gap in gaps if isinstance(gap, dict)]


def _critical_gaps(gap_report: dict[str, Any]) -> list[dict[str, Any]]:
    return [gap for gap in _gaps(gap_report) if str(gap.get('severity') or '').lower() == 'critical']


def _gap_counts(gaps: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {'critical': 0, 'major': 0, 'minor': 0}
    for gap in gaps:
        severity = str(gap.get('severity') or '').lower()
        if severity in counts:
            counts[severity] += 1
    return counts


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
