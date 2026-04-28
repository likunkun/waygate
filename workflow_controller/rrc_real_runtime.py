from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from workflow_controller.rrc_agent_runners import RunnerRequest, make_runner, run_agent_backend


@dataclass(frozen=True)
class AgentRunResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    backend: str = 'subprocess'
    status: str = 'done'
    run_dir: str | None = None
    done_payload: dict[str, Any] | None = None


def build_state_from_ralph(
    workspace_dir: Path,
    agent_command: str = 'claude',
    agent_runner: str = 'subprocess',
    tmux_target: str | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    ralph_dir = workspace_dir / '.plan-ralph'
    session_path = ralph_dir / 'session.json'
    if not session_path.exists():
        raise FileNotFoundError(f'Ralph session not found: {session_path}')

    ralph_session = json.loads(session_path.read_text(encoding='utf-8'))
    plan_path = Path(ralph_session['planPath'])
    prompt_path = Path(ralph_session.get('promptPath') or ralph_dir / 'current-prompt.md')
    units = parse_ralph_plan(plan_path)
    completed = set(ralph_session.get('completedStepIds') or [])
    target_matched = target_matches_unit(units, target)

    if target and not target_matched:
        target_unit = build_target_acceptance_unit(target, workspace_dir)
        units.append(target_unit)
        selected_unit_id = target_unit['id']
        execution_workspace = infer_execution_workspace(workspace_dir)
    else:
        selected_unit_id = select_ralph_unit(
            units,
            completed_step_ids=completed,
            active_step_id=ralph_session.get('activeStepId'),
            target=target,
        )
        execution_workspace = workspace_dir

    target_context_files = find_target_context_files(workspace_dir, target=target)

    objective_coverage = []
    for unit in units:
        status = 'covered' if unit['id'] in completed else 'partial'
        objective_coverage.append({
            'objective': unit.get('goal') or unit['id'],
            'units': [unit['id']],
            'status': status,
        })

    for unit in units:
        unit['passes'] = unit['id'] in completed

    return {
        'task_id': plan_path.stem,
        'currentUnitId': selected_unit_id,
        'currentStep': 'PLAN_CREATED',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': target or 'complete current Ralph step',
        'feasibleOutcome': target or 'complete current Ralph step',
        'scopeApproved': False,
        'autoApprove': False,
        'currentUnitNeedsUiDesign': False,
        'workspacePath': str(workspace_dir),
        'executionWorkspacePath': str(execution_workspace),
        'baselineChangedFiles': collect_git_changed_files(execution_workspace),
        'ralphSessionPath': str(session_path),
        'planPath': str(plan_path),
        'planHash': ralph_session.get('planHash'),
        'promptPath': str(prompt_path),
        'agentCommand': agent_command,
        'agentRunner': agent_runner,
        'tmuxTarget': tmux_target,
        'targetMatchedPlanStep': bool(target_matched) if target else None,
        'targetContextFiles': [str(path) for path in target_context_files],
        'objectiveCoverage': objective_coverage,
        'units': units,
        'nextAllowedActions': ['require_scope_approval'],
        'blockedReason': None,
        'updatedAt': _now_iso(),
    }


def render_target_acceptance_prompt(state: dict[str, Any]) -> str:
    context_sections = []
    markers = _target_markers(str(state.get('requestedOutcome') or ''))
    for raw_path in state.get('targetContextFiles') or []:
        path = Path(raw_path)
        if not path.exists():
            continue
        content = path.read_text(encoding='utf-8')
        excerpt = extract_relevant_context(content, markers)
        if excerpt:
            context_sections.append(f'## Context File: {path}\n\n{excerpt}')

    return f"""You are executing a real development acceptance target from the current workspace.

Target acceptance: {state.get('requestedOutcome')}
Workspace: {state.get('workspacePath')}
Execution workspace: {state.get('executionWorkspacePath') or state.get('workspacePath')}
Plan path: {state.get('planPath')}
Current unit id: {state.get('currentUnitId')}

Goal:
- Complete only the remaining work needed for the target acceptance.
- If the target spans multiple units, complete the first missing verifiable unit only.
- Use the existing progress and findings below as source of truth.
- Preserve already accepted work.
- If the target is impossible or underspecified after reading the context, report BLOCKED with the exact missing decision.

Rules:
- Do not modify frozen plan files unless the task explicitly requires progress bookkeeping.
- Do not expand scope beyond the target acceptance.
- Prefer the shortest path that reaches a verifiable customer-facing acceptance result.
- You are not done until the relevant verification commands pass or you can show the exact blocker.

{chr(10).join(context_sections)}
"""


def extract_relevant_context(content: str, markers: list[str], context_lines: int = 5, max_chars: int = 3000) -> str:
    lines = content.splitlines()
    selected: set[int] = set()
    lowered_markers = [marker.lower() for marker in markers if marker]
    for index, line in enumerate(lines):
        lowered = line.lower()
        if any(marker in lowered for marker in lowered_markers):
            start = max(0, index - context_lines)
            end = min(len(lines), index + context_lines + 1)
            selected.update(range(start, end))

    if not selected:
        return content[: min(len(content), 2000)]

    chunks: list[str] = []
    previous = -2
    for index in sorted(selected):
        if index != previous + 1 and chunks:
            chunks.append('...')
        chunks.append(lines[index])
        previous = index
    excerpt = '\n'.join(chunks)
    return excerpt[:max_chars]


def target_matches_unit(units: list[dict[str, Any]], target: str | None) -> bool:
    if not target:
        return False
    return any(unit['id'] == target or unit['id'].startswith(target) or target in unit['name'] for unit in units)


def build_target_acceptance_unit(target: str, workspace_dir: Path) -> dict[str, Any]:
    return {
        'id': f'target-{_slug(target)}',
        'name': f'{target} development acceptance',
        'goal': f'Complete {target} development acceptance using current planning progress',
        'status_label': 'target',
        'scope': [
            'Read current task_plan.md, progress.md, and findings.md before acting',
            'Identify remaining acceptance work from the target context',
            'Implement the shortest verifiable path only',
            'Update artifacts with real execution and verification evidence',
        ],
        'non_goals': [
            'Do not redo already accepted work',
            'Do not expand into future roadmap items without an explicit blocker',
        ],
        'done_when': [
            'Target acceptance criteria from the progress context are satisfied',
            'Relevant automated verification commands pass',
            'Any browser-visible acceptance is explicitly verified when UI is touched',
        ],
        'verification_commands': infer_workspace_verification_commands(workspace_dir),
    }


def find_target_context_files(workspace_dir: Path, target: str | None = None) -> list[Path]:
    candidates = [
        workspace_dir / 'task_plan.md',
        workspace_dir / 'progress.md',
        workspace_dir / 'findings.md',
        workspace_dir / 'OpenMAIC' / '.worktrees' / 'course-mgmt-v1' / 'task_plan.md',
        workspace_dir / 'OpenMAIC' / '.worktrees' / 'course-mgmt-v1' / 'progress.md',
        workspace_dir / 'OpenMAIC' / '.worktrees' / 'course-mgmt-v1' / 'findings.md',
        workspace_dir / 'OpenMAIC' / 'task_plan.md',
        workspace_dir / 'OpenMAIC' / 'progress.md',
        workspace_dir / 'OpenMAIC' / 'findings.md',
    ]
    found = [path for path in candidates if path.exists()]
    found.extend(find_relevant_claude_plans(target))
    return list(dict.fromkeys(found))


def find_relevant_claude_plans(target: str | None) -> list[Path]:
    if not target:
        return []

    plans_dir = Path.home() / '.claude' / 'plans'
    if not plans_dir.exists():
        return []

    target_markers = set(_target_markers(target))
    acceptance_markers = {
        'customer delivery/import acceptance',
        '客户平台导入',
        '客户交付',
        '批量 AI 课程包工厂',
        '批量AI课程包工厂',
    }
    domain_markers = {'OpenMAIC', 'course-mgmt-v1', '课程'}
    scored: list[tuple[int, Path]] = []
    for path in plans_dir.glob('*.md'):
        try:
            content = path.read_text(encoding='utf-8')
        except OSError:
            continue
        target_score = sum(content.count(marker) for marker in target_markers if marker)
        acceptance_score = sum(content.count(marker) for marker in acceptance_markers)
        domain_score = sum(content.count(marker) for marker in domain_markers)
        if not ((target_score > 0 and domain_score > 0) or acceptance_score > 0):
            continue
        score = target_score + (acceptance_score * 5) + (domain_score * 2)
        if score > 0:
            scored.append((score, path))

    scored.sort(key=lambda item: (-item[0], str(item[1])))
    return [path for _, path in scored[:3]]


def _target_markers(target: str | None) -> list[str]:
    markers = [
        target or '',
        f'V{target}' if target else '',
        f'v{target}' if target else '',
        'Phase 7',
        '工作流 G',
        'customer delivery/import acceptance',
        '客户平台导入',
        '客户交付',
        '批量 AI 课程包工厂',
        '批量AI课程包工厂',
        'V1.1',
        'v1.1',
    ]
    return [marker for marker in markers if marker]


def infer_workspace_verification_commands(workspace_dir: Path) -> list[str]:
    worktree = infer_execution_workspace(workspace_dir)
    if (worktree / 'package.json').exists():
        return [
            f'pnpm --dir {shlex.quote(str(worktree))} exec tsc --noEmit',
        ]
    if (workspace_dir / 'package.json').exists():
        return ['pnpm exec tsc --noEmit']
    return []


def infer_execution_workspace(workspace_dir: Path) -> Path:
    worktree = workspace_dir / 'OpenMAIC' / '.worktrees' / 'course-mgmt-v1'
    if (worktree / 'package.json').exists():
        return worktree
    if (workspace_dir / 'package.json').exists():
        return workspace_dir
    return workspace_dir


def parse_ralph_plan(plan_path: Path) -> list[dict[str, Any]]:
    content = plan_path.read_text(encoding='utf-8')
    step_matches = list(re.finditer(r'^## Step\s+(.+?)\s*$', content, flags=re.MULTILINE))
    units: list[dict[str, Any]] = []

    for index, match in enumerate(step_matches):
        raw_id = match.group(1).strip()
        start = match.end()
        end = step_matches[index + 1].start() if index + 1 < len(step_matches) else len(content)
        block = content[start:end]
        unit_id = raw_id.split()[0].strip()
        units.append({
            'id': unit_id,
            'name': raw_id,
            'goal': _extract_bullet_value(block, 'Goal'),
            'status_label': _extract_bullet_value(block, 'Status'),
            'scope': _extract_section_bullets(block, 'Scope'),
            'non_goals': _extract_section_bullets(block, 'Non-goals'),
            'done_when': _extract_section_bullets(block, 'Done when'),
            'verification_commands': _extract_section_bullets(block, 'Verification'),
        })

    if not units:
        raise ValueError(f'No Ralph plan steps found in {plan_path}')
    return units


def select_ralph_unit(
    units: list[dict[str, Any]],
    completed_step_ids: set[str],
    active_step_id: str | None = None,
    target: str | None = None,
) -> str:
    if target:
        for unit in units:
            if unit['id'] == target or unit['id'].startswith(target) or target in unit['name']:
                return unit['id']

    if active_step_id:
        return active_step_id

    for unit in units:
        if unit['id'] not in completed_step_ids:
            return unit['id']
    return units[-1]['id']


def run_agent_for_current_step(
    state: dict[str, Any],
    workspace_dir: Path,
    prompt_path: Path,
    artifact_dir: Path | None = None,
) -> AgentRunResult:
    timeout = int(state.get('agentTimeoutSeconds') or 3600)
    runner = make_runner(state)
    result = run_agent_backend(
        RunnerRequest(
            backend=runner.backend,
            workspace_dir=workspace_dir,
            prompt_path=prompt_path,
            artifact_dir=artifact_dir or prompt_path.parent,
            unit_id=str(state.get('currentUnitId') or 'unit'),
            agent_command=runner.agent_command or str(state.get('agentCommand') or 'claude'),
            tmux_target=runner.tmux_target,
            timeout_seconds=timeout,
        )
    )
    return AgentRunResult(
        command=result.command,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        backend=result.backend,
        status=result.status,
        run_dir=str(result.run_dir),
        done_payload=result.done_payload,
    )


def collect_git_changed_files(workspace_dir: Path) -> list[str]:
    completed = subprocess.run(
        ['git', 'status', '--porcelain'],
        cwd=workspace_dir,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return []

    changed: list[str] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if ' -> ' in path:
            path = path.split(' -> ', 1)[1].strip()
        if path and not path.startswith('.plan-ralph/'):
            changed.append(path)
    return sorted(dict.fromkeys(changed))


def verification_commands_for_state(state: dict[str, Any]) -> list[str]:
    unit = _find_unit(state, state.get('currentUnitId'))
    commands = unit.get('verification_commands') or state.get('verificationCommands') or []
    return [str(command) for command in commands if str(command).strip()]


def verification_env_for_state(state: dict[str, Any]) -> dict[str, str]:
    unit = _find_unit(state, state.get('currentUnitId'))
    env: dict[str, str] = {}
    for source in (
        state.get('verification_env'),
        state.get('verificationEnv'),
        unit.get('verification_env'),
        unit.get('verificationEnv'),
    ):
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            key_text = str(key).strip()
            if key_text and value is not None:
                env[key_text] = str(value)
    return env


def run_verification_commands(
    state: dict[str, Any],
    workspace_dir: Path,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    verification_env = verification_env_for_state(state)
    env = {**os.environ, **verification_env} if verification_env else None
    commands = verification_commands_for_state(state)
    total = len(commands)
    timeout_seconds = int(state.get('verificationTimeoutSeconds') or 1800)
    _emit_progress(progress_callback, {
        'event': 'verification_started',
        'total': total,
        'env_keys': sorted(verification_env),
    })
    for index, command in enumerate(commands, start=1):
        _emit_progress(progress_callback, {
            'event': 'verification_command_started',
            'index': index,
            'total': total,
            'command': command,
        })
        started_at = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=workspace_dir,
                shell=True,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
                env=env,
            )
            result = {
                'command': command,
                'returncode': completed.returncode,
                'ok': completed.returncode == 0,
                'stdout': completed.stdout,
                'stderr': completed.stderr,
                'env_keys': sorted(verification_env),
                'elapsed_seconds': round(time.monotonic() - started_at, 3),
            }
        except subprocess.TimeoutExpired as exc:
            result = {
                'command': command,
                'returncode': 124,
                'ok': False,
                'stdout': exc.stdout or '',
                'stderr': exc.stderr or f'Command timed out after {timeout_seconds} seconds',
                'env_keys': sorted(verification_env),
                'elapsed_seconds': round(time.monotonic() - started_at, 3),
                'timed_out': True,
            }
        results.append(result)
        _emit_progress(progress_callback, {
            'event': 'verification_command_finished',
            'index': index,
            'total': total,
            'command': command,
            'returncode': result['returncode'],
            'ok': result['ok'],
            'elapsed_seconds': result['elapsed_seconds'],
        })
    _emit_progress(progress_callback, {
        'event': 'verification_finished',
        'total': total,
        'passed': all(result.get('ok') for result in results),
    })
    return results


def _emit_progress(
    progress_callback: Callable[[dict[str, Any]], None] | None,
    event: dict[str, Any],
) -> None:
    if progress_callback is not None:
        progress_callback(event)


def _extract_bullet_value(block: str, key: str) -> str | None:
    pattern = re.compile(rf'^\s*-\s*{re.escape(key)}:\s*(.*?)\s*$', flags=re.MULTILINE)
    match = pattern.search(block)
    return match.group(1).strip() if match else None


def _extract_section_bullets(block: str, section_name: str) -> list[str]:
    pattern = re.compile(
        rf'^###\s+{re.escape(section_name)}\s*$(.*?)(?=^###\s+|\Z)',
        flags=re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(block)
    if not match:
        return []

    bullets: list[str] = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith('- '):
            bullets.append(stripped[2:].strip())
    return bullets


def _find_unit(state: dict[str, Any], unit_id: str | None) -> dict[str, Any]:
    for unit in state.get('units', []):
        if unit.get('id') == unit_id:
            return unit
    return {}


def _slug(value: str) -> str:
    slug = re.sub(r'[^A-Za-z0-9]+', '-', value).strip('-').lower()
    return slug or 'acceptance'


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
