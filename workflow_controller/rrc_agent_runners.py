from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TMUX_SUBMIT_DELAY_SECONDS = 0.5
DEFAULT_TMUX_CLEAR_DELAY_SECONDS = 0.5
DEFAULT_TMUX_IDLE_GRACE_SECONDS = 60.0
DEFAULT_TMUX_IDLE_POLL_SECONDS = 0.0


@dataclass(frozen=True)
class RunnerConfig:
    backend: str
    agent_command: str = ''
    tmux_target: str | None = None


@dataclass(frozen=True)
class RunnerRequest:
    backend: str
    workspace_dir: Path
    prompt_path: Path
    artifact_dir: Path
    unit_id: str
    agent_command: str = ''
    tmux_target: str | None = None
    timeout_seconds: int = 3600


@dataclass(frozen=True)
class RunnerResult:
    backend: str
    status: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    run_dir: Path
    prompt_path: Path
    done_path: Path | None = None
    done_payload: dict[str, Any] = field(default_factory=dict)


def make_runner(state: dict[str, Any]) -> RunnerConfig:
    backend = str(state.get('agentRunner') or state.get('runnerBackend') or 'subprocess')
    return RunnerConfig(
        backend=backend,
        agent_command=str(state.get('agentCommand') or ''),
        tmux_target=state.get('tmuxTarget') or state.get('tmuxPane'),
    )


def run_agent_backend(request: RunnerRequest) -> RunnerResult:
    if request.backend == 'subprocess':
        return _run_subprocess_agent(request)
    if request.backend == 'tmux-claude':
        return _run_tmux_claude(request)
    raise ValueError(f'Unsupported agent runner backend: {request.backend}')


def _run_subprocess_agent(request: RunnerRequest) -> RunnerResult:
    prompt = request.prompt_path.read_text(encoding='utf-8')
    command = _subprocess_agent_command(request.agent_command or 'claude', prompt)
    completed = subprocess.run(
        command,
        cwd=request.workspace_dir,
        text=True,
        input=prompt if _uses_stdin_prompt(command) else None,
        capture_output=True,
        timeout=request.timeout_seconds,
        check=False,
    )
    return RunnerResult(
        backend='subprocess',
        status='done' if completed.returncode == 0 else 'failed',
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        run_dir=request.artifact_dir,
        prompt_path=request.prompt_path,
    )


def _run_tmux_claude(request: RunnerRequest) -> RunnerResult:
    if not request.tmux_target:
        raise ValueError('tmux-claude runner requires tmuxTarget or tmuxPane in state')

    run_dir = _new_run_dir(request.artifact_dir, request.unit_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_dir.name
    done_path = run_dir / 'done.json'
    events_path = run_dir / 'events.log'
    runner_prompt_path = run_dir / 'prompt.md'
    dispatch_prompt_path = run_dir / 'dispatch.md'
    runner_prompt_path.write_text(
        _render_tmux_prompt(
            original_prompt=request.prompt_path.read_text(encoding='utf-8'),
            done_path=done_path,
            workspace_dir=request.workspace_dir,
            unit_id=request.unit_id,
            run_id=run_id,
        ),
        encoding='utf-8',
    )
    dispatch_prompt_path.write_text(
        _render_tmux_dispatch_prompt(
            prompt_path=runner_prompt_path,
            done_path=done_path,
            run_id=run_id,
        ),
        encoding='utf-8',
    )

    tmux_command = _tmux_command(request.agent_command)
    env = {
        **os.environ,
        'RRC_RUN_DONE_FILE': str(done_path),
        'RRC_RUN_DIR': str(run_dir),
        'RRC_RUN_ID': run_id,
    }
    clear_commands = []
    if _tmux_clear_before_dispatch_enabled():
        clear_commands = [
            [*tmux_command, 'send-keys', '-t', request.tmux_target, 'C-u'],
            [*tmux_command, 'send-keys', '-t', request.tmux_target, '/clear', 'C-m'],
        ]
    dispatch_commands = [
        [*tmux_command, 'load-buffer', str(dispatch_prompt_path)],
        [*tmux_command, 'paste-buffer', '-t', request.tmux_target],
        [*tmux_command, 'send-keys', '-t', request.tmux_target, 'C-m'],
    ]
    commands = [*clear_commands, *dispatch_commands]

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    last_returncode = 0
    _append_event(events_path, {'event': 'dispatch_started', 'backend': 'tmux-claude'})
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=request.workspace_dir,
            text=True,
            capture_output=True,
            timeout=min(request.timeout_seconds, 30),
            check=False,
            env=env,
        )
        last_returncode = completed.returncode
        stdout_parts.append(completed.stdout)
        stderr_parts.append(completed.stderr)
        _append_event(events_path, {
            'event': 'tmux_command',
            'command': command,
            'returncode': completed.returncode,
        })
        if completed.returncode != 0:
            return RunnerResult(
                backend='tmux-claude',
                status='failed',
                command=dispatch_commands[-1],
                returncode=completed.returncode,
                stdout=''.join(stdout_parts),
                stderr=''.join(stderr_parts),
                run_dir=run_dir,
                prompt_path=runner_prompt_path,
                done_path=done_path,
            )
        if clear_commands and command == clear_commands[-1]:
            delay_seconds = _tmux_clear_delay_seconds()
            _append_event(events_path, {
                'event': 'tmux_clear_delay',
                'seconds': delay_seconds,
            })
            time.sleep(delay_seconds)
        if command == dispatch_commands[1]:
            delay_seconds = _tmux_submit_delay_seconds()
            _append_event(events_path, {
                'event': 'tmux_submit_delay',
                'seconds': delay_seconds,
            })
            time.sleep(delay_seconds)

    deadline = time.monotonic() + request.timeout_seconds
    next_idle_check = time.monotonic() + _tmux_idle_grace_seconds()
    idle_poll_seconds = _tmux_idle_poll_seconds()
    while time.monotonic() < deadline:
        if done_path.exists():
            payload = _read_done_payload(done_path)
            if payload.get('status') == 'invalid_done_file':
                message = (
                    f'DONE_FILE {done_path} is invalid: {payload.get("summary")}. '
                    'Rewrite it as a JSON object like '
                    f'{{"status":"done","summary":"<short summary>","run_id":"{run_id}"}}.'
                )
                _append_event(events_path, {
                    'event': 'invalid_done_file',
                    'summary': payload.get('summary'),
                })
                return RunnerResult(
                    backend='tmux-claude',
                    status='invalid_done_file',
                    command=dispatch_commands[-1],
                    returncode=1,
                    stdout=''.join(stdout_parts),
                    stderr=''.join(stderr_parts) + message,
                    run_dir=run_dir,
                    prompt_path=runner_prompt_path,
                    done_path=done_path,
                    done_payload=payload,
                )
            actual_run_id = payload.get('run_id')
            if actual_run_id != run_id:
                message = (
                    f'DONE_FILE {done_path} has wrong run_id. '
                    f'expected run_id={run_id!r}, actual run_id={actual_run_id!r}. '
                    'This usually means an older tmux agent wrote a stale completion signal; '
                    'rerun the current controller step after clearing the pane or ensuring Claude uses the latest prompt.'
                )
                _append_event(events_path, {
                    'event': 'done_file_wrong_run',
                    'expected_run_id': run_id,
                    'actual_run_id': actual_run_id,
                })
                return RunnerResult(
                    backend='tmux-claude',
                    status='done_file_wrong_run',
                    command=dispatch_commands[-1],
                    returncode=1,
                    stdout=''.join(stdout_parts),
                    stderr=''.join(stderr_parts) + message,
                    run_dir=run_dir,
                    prompt_path=runner_prompt_path,
                    done_path=done_path,
                    done_payload=payload,
                )
            status = str(payload.get('status') or 'done')
            _append_event(events_path, {'event': 'done_signal_seen', 'status': status})
            return RunnerResult(
                backend='tmux-claude',
                status=status,
                command=dispatch_commands[-1],
                returncode=0 if status == 'done' else 1,
                stdout=''.join(stdout_parts),
                stderr=''.join(stderr_parts),
                run_dir=run_dir,
                prompt_path=runner_prompt_path,
                done_path=done_path,
                done_payload=payload,
            )
        now = time.monotonic()
        if idle_poll_seconds > 0 and now >= next_idle_check:
            pane_tail = _capture_tmux_pane(
                tmux_command=tmux_command,
                tmux_target=request.tmux_target,
                workspace_dir=request.workspace_dir,
                env=env,
            )
            if _tmux_pane_looks_idle(pane_tail):
                if pane_tail:
                    (run_dir / 'tmux-pane-tail.txt').write_text(pane_tail, encoding='utf-8')
                _append_event(events_path, {
                    'event': 'agent_idle_without_done',
                    'pane_tail_path': str(run_dir / 'tmux-pane-tail.txt') if pane_tail else None,
                })
                return RunnerResult(
                    backend='tmux-claude',
                    status='agent_idle_without_done',
                    command=dispatch_commands[-1],
                    returncode=124,
                    stdout=''.join(stdout_parts),
                    stderr=''.join(stderr_parts) + _tmux_timeout_message(
                        done_path=done_path,
                        run_id=run_id,
                        pane_tail=pane_tail,
                        pane_is_idle=True,
                    ),
                    run_dir=run_dir,
                    prompt_path=runner_prompt_path,
                    done_path=done_path,
                )
            next_idle_check = now + idle_poll_seconds
        time.sleep(0.2)

    pane_tail = _capture_tmux_pane(
        tmux_command=tmux_command,
        tmux_target=request.tmux_target,
        workspace_dir=request.workspace_dir,
        env=env,
    )
    if pane_tail:
        (run_dir / 'tmux-pane-tail.txt').write_text(pane_tail, encoding='utf-8')
    pane_is_idle = _tmux_pane_looks_idle(pane_tail)
    status = 'agent_idle_without_done' if pane_is_idle else 'timeout'
    _append_event(events_path, {
        'event': status,
        'pane_tail_path': str(run_dir / 'tmux-pane-tail.txt') if pane_tail else None,
    })
    timeout_message = _tmux_timeout_message(
        done_path=done_path,
        run_id=run_id,
        pane_tail=pane_tail,
        pane_is_idle=pane_is_idle,
    )
    return RunnerResult(
        backend='tmux-claude',
        status=status,
        command=dispatch_commands[-1],
        returncode=124 if last_returncode == 0 else last_returncode,
        stdout=''.join(stdout_parts),
        stderr=''.join(stderr_parts) + timeout_message,
        run_dir=run_dir,
        prompt_path=runner_prompt_path,
        done_path=done_path,
    )


def _render_tmux_prompt(
    original_prompt: str,
    done_path: Path,
    workspace_dir: Path,
    unit_id: str,
    run_id: str,
) -> str:
    return f"""You are being controlled by workflow-controller through a tmux pane.

Workspace: {workspace_dir}
Unit id: {unit_id}
RUN_ID: {run_id}
DONE_FILE: {done_path}

Execute the task below in the workspace. When finished, write DONE_FILE as JSON:
{{"status": "done", "summary": "<short summary>", "run_id": "{run_id}"}}

If blocked, write DONE_FILE as JSON:
{{"status": "blocked", "summary": "<exact blocker>", "run_id": "{run_id}"}}

Original task:

{original_prompt}
"""


def _render_tmux_dispatch_prompt(prompt_path: Path, done_path: Path, run_id: str) -> str:
    return f"""workflow-controller dispatch.

PROMPT_FILE: {prompt_path}
RUN_ID: {run_id}
DONE_FILE: {done_path}

Read PROMPT_FILE first, then execute the complete task described there.
Do not infer the task from previous conversation or terminal output.
When finished, write DONE_FILE as JSON with the exact RUN_ID:
{{"status":"done","summary":"<short summary>","run_id":"{run_id}"}}
If blocked, write:
{{"status":"blocked","summary":"<exact blocker>","run_id":"{run_id}"}}
"""


def _subprocess_agent_command(agent_command: str, prompt: str) -> list[str]:
    parts = shlex.split(agent_command)
    executable = Path(parts[0]).name if parts else agent_command
    if 'claude' in executable:
        return [
            *parts,
            '-p',
            prompt,
            '--permission-mode',
            'bypassPermissions',
        ]
    if 'codex' in executable:
        if len(parts) > 1 and parts[1] == 'exec':
            return [
                *parts,
                '--dangerously-bypass-approvals-and-sandbox',
                '-',
            ]
        return [
            *parts,
            'exec',
            '--dangerously-bypass-approvals-and-sandbox',
            '-',
        ]
    return [*parts, prompt]


def _tmux_command(agent_command: str) -> list[str]:
    parts = shlex.split(agent_command) if agent_command else []
    if parts and Path(parts[0]).name == 'tmux':
        return parts
    return ['tmux']


def _tmux_submit_delay_seconds() -> float:
    return _env_float('RRC_TMUX_SUBMIT_DELAY_SECONDS', DEFAULT_TMUX_SUBMIT_DELAY_SECONDS)


def _tmux_clear_before_dispatch_enabled() -> bool:
    raw_value = os.environ.get('RRC_TMUX_CLEAR_BEFORE_DISPATCH')
    if raw_value is None:
        return True
    return raw_value.strip().lower() not in {'0', 'false', 'no', 'off'}


def _tmux_clear_delay_seconds() -> float:
    return _env_float('RRC_TMUX_CLEAR_DELAY_SECONDS', DEFAULT_TMUX_CLEAR_DELAY_SECONDS)


def _tmux_idle_grace_seconds() -> float:
    return _env_float('RRC_TMUX_IDLE_GRACE_SECONDS', DEFAULT_TMUX_IDLE_GRACE_SECONDS)


def _tmux_idle_poll_seconds() -> float:
    return _env_float('RRC_TMUX_IDLE_POLL_SECONDS', DEFAULT_TMUX_IDLE_POLL_SECONDS)


def _env_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return default


def _uses_stdin_prompt(command: list[str]) -> bool:
    executable = Path(command[0]).name if command else ''
    return 'codex' in executable and command[-1:] == ['-']


def _new_run_dir(artifact_dir: Path, unit_id: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    return artifact_dir / 'runs' / f'{unit_id}-{timestamp}'


def _capture_tmux_pane(
    *,
    tmux_command: list[str],
    tmux_target: str,
    workspace_dir: Path,
    env: dict[str, str],
) -> str:
    command = [*tmux_command, 'capture-pane', '-t', tmux_target, '-p', '-S', '-80']
    try:
        completed = subprocess.run(
            command,
            cwd=workspace_dir,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f'Unable to capture tmux pane: {exc}'
    if completed.returncode != 0:
        return '\n'.join(part for part in (completed.stdout, completed.stderr) if part).strip()
    return completed.stdout.strip()


def _tmux_pane_looks_idle(pane_tail: str) -> bool:
    lines = [line.strip() for line in pane_tail.splitlines() if line.strip()]
    if not lines:
        return False
    if _tmux_pane_has_active_claude_status(lines):
        return False
    last_line = lines[-1]
    if re.search(r'(^|\s)(❯|>|[$#])\s*$', last_line):
        return True
    tail_lines = lines[-8:]
    if any(re.search(r'(^|\s)(❯|>|[$#])\s*$', line) for line in tail_lines):
        return True
    lowered_tail = pane_tail.lower()
    return 'no active conversation' in lowered_tail or 'press enter to continue' in lowered_tail


def _tmux_pane_has_active_claude_status(lines: list[str]) -> bool:
    active_patterns = (
        'actualizing',
        'thinking',
        'drizzling',
        'running',
        'processing',
        'working',
        'esc to interrupt',
    )
    for line in lines[-20:]:
        lowered = line.lower()
        if any(pattern in lowered for pattern in active_patterns):
            if '…' in line or '...' in line or re.search(r'\(\d+[smh]', line):
                return True
    return False


def _tmux_timeout_message(*, done_path: Path, run_id: str, pane_tail: str, pane_is_idle: bool) -> str:
    idle_hint = ''
    if pane_is_idle:
        idle_hint = (
            ' The tmux pane appears idle without the completion file, so the agent likely stopped '
            'or returned to the prompt before writing DONE_FILE.'
        )
    pane_hint = ''
    if pane_tail:
        pane_hint = f'\n\nLast captured tmux pane output:\n{_tail_text(pane_tail, max_chars=4000)}'
    return (
        f'tmux-claude timed out waiting for DONE_FILE: {done_path} (run_id={run_id}).'
        f'{idle_hint} '
        'If the agent finished in the pane, ask it to write done.json there, '
        'or write done.json manually with '
        f'{{"status":"done","summary":"<short summary>","run_id":"{run_id}"}} and rerun the controller.'
        f'{pane_hint}'
    )


def _tail_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f'... truncated ...\n{text[-max_chars:]}'


def _append_event(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {'ts': datetime.now(timezone.utc).isoformat(), **payload}
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + '\n')


def _read_done_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {'status': 'invalid_done_file', 'summary': 'done.json is not valid JSON'}
    return payload if isinstance(payload, dict) else {'status': 'invalid_done_file', 'summary': 'done.json is not an object'}
