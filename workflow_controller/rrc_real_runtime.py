from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from workflow_controller.runners.base import RunnerRequest
from workflow_controller.runners import make_runner, run_agent_backend
from workflow_controller.runners.base import DEFAULT_AGENT_TIMEOUT_SECONDS


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
    runner_metadata: dict[str, Any] | None = None


class VerificationEnvironmentError(RuntimeError):
    pass


def build_state_from_target_acceptance(
    workspace_dir: Path,
    target: str,
    agent_command: str = 'claude',
    agent_runner: str = 'subprocess',
    tmux_target: str | None = None,
) -> dict[str, Any]:
    execution_workspace = infer_execution_workspace(workspace_dir)
    target_unit = build_target_acceptance_unit(target, workspace_dir)
    target_context_files = find_target_context_files(workspace_dir, target=target)
    return {
        'task_id': target_unit['id'],
        'currentUnitId': target_unit['id'],
        'currentStep': 'PLAN_CREATED',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': target,
        'feasibleOutcome': target,
        'scopeApproved': False,
        'autoApprove': False,
        'testStrategistEnabled': False,
        'currentUnitNeedsUiDesign': False,
        'workspacePath': str(workspace_dir),
        'executionWorkspacePath': str(execution_workspace),
        'baselineChangedFiles': collect_git_changed_files(execution_workspace),
        'agentCommand': agent_command,
        'agentRunner': agent_runner,
        'tmuxTarget': tmux_target,
        'targetMatchedPlanStep': False,
        'targetContextFiles': [str(path) for path in target_context_files],
        'objectiveCoverage': [
            {
                'objective': target_unit.get('goal') or target_unit['id'],
                'units': [target_unit['id']],
                'status': 'partial',
            },
        ],
        'units': [target_unit],
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
    ]
    return [path for path in candidates if path.exists()]


def _target_markers(target: str | None) -> list[str]:
    markers = [
        target or '',
        f'V{target}' if target else '',
        f'v{target}' if target else '',
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
    return workspace_dir


def run_agent_for_current_step(
    state: dict[str, Any],
    workspace_dir: Path,
    prompt_path: Path,
    artifact_dir: Path | None = None,
    role: str | None = None,
) -> AgentRunResult:
    timeout = int(state.get('agentTimeoutSeconds') or DEFAULT_AGENT_TIMEOUT_SECONDS)
    runner = make_runner(state, role=role)
    result = run_agent_backend(
        RunnerRequest(
            backend=runner.backend,
            workspace_dir=workspace_dir,
            prompt_path=prompt_path,
            artifact_dir=artifact_dir or prompt_path.parent,
            unit_id=str(state.get('currentUnitId') or 'unit'),
            agent_command=runner.agent_command or str(state.get('agentCommand') or 'claude'),
            tmux_target=runner.tmux_target,
            role=runner.role,
            env=runner.env,
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
        runner_metadata=result.runner_metadata,
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


def ensure_verification_env_for_state(state: dict[str, Any], workspace_dir: Path) -> dict[str, str]:
    env = verification_env_for_state(state)
    inferred: dict[str, str] = {}
    missing: list[str] = []
    for command in verification_commands_for_state(state):
        for key in sorted(_required_env_keys_for_verification_command(command)):
            if key in env or _command_sets_env(command, key):
                continue
            inferred_value = _infer_verification_env_value(key, workspace_dir)
            if inferred_value:
                state_env = state.setdefault('verification_env', {})
                if isinstance(state_env, dict):
                    state_env[key] = inferred_value
                inferred_state = state.setdefault('verification_env_inferred', {})
                if isinstance(inferred_state, dict):
                    inferred_state[key] = inferred_value
                env[key] = inferred_value
                inferred[key] = inferred_value
            else:
                missing.append(f'{key} for `{command}`')
    if missing:
        raise VerificationEnvironmentError(
            'verification environment is incomplete: '
            + '; '.join(missing)
            + '. Add verification_env or inline the variable in the verification command.'
        )
    return env


def run_verification_commands(
    state: dict[str, Any],
    workspace_dir: Path,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    verification_env = ensure_verification_env_for_state(state, workspace_dir)
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
                executable='/bin/bash',
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


def _infer_verification_env_value(key: str, workspace_dir: Path) -> str | None:
    if key != 'DATABASE_URL':
        return None
    candidate = workspace_dir / 'prisma' / 'dev.db'
    if candidate.exists():
        return f'file:{candidate}'
    return None


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
