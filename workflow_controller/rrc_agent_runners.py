from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TMUX_SUBMIT_DELAY_SECONDS = 0.5


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
    done_path = run_dir / 'done.json'
    events_path = run_dir / 'events.log'
    runner_prompt_path = run_dir / 'prompt.md'
    runner_prompt_path.write_text(
        _render_tmux_prompt(
            original_prompt=request.prompt_path.read_text(encoding='utf-8'),
            done_path=done_path,
            workspace_dir=request.workspace_dir,
            unit_id=request.unit_id,
        ),
        encoding='utf-8',
    )

    tmux_command = _tmux_command(request.agent_command)
    env = {
        **os.environ,
        'RRC_RUN_DONE_FILE': str(done_path),
        'RRC_RUN_DIR': str(run_dir),
    }
    commands = [
        [*tmux_command, 'load-buffer', str(runner_prompt_path)],
        [*tmux_command, 'paste-buffer', '-t', request.tmux_target],
        [*tmux_command, 'send-keys', '-t', request.tmux_target, 'C-m'],
    ]

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
                command=commands[-1],
                returncode=completed.returncode,
                stdout=''.join(stdout_parts),
                stderr=''.join(stderr_parts),
                run_dir=run_dir,
                prompt_path=runner_prompt_path,
                done_path=done_path,
            )
        if command == commands[1]:
            delay_seconds = _tmux_submit_delay_seconds()
            _append_event(events_path, {
                'event': 'tmux_submit_delay',
                'seconds': delay_seconds,
            })
            time.sleep(delay_seconds)

    deadline = time.monotonic() + request.timeout_seconds
    while time.monotonic() < deadline:
        if done_path.exists():
            payload = _read_done_payload(done_path)
            status = str(payload.get('status') or 'done')
            _append_event(events_path, {'event': 'done_signal_seen', 'status': status})
            return RunnerResult(
                backend='tmux-claude',
                status=status,
                command=commands[-1],
                returncode=0 if status == 'done' else 1,
                stdout=''.join(stdout_parts),
                stderr=''.join(stderr_parts),
                run_dir=run_dir,
                prompt_path=runner_prompt_path,
                done_path=done_path,
                done_payload=payload,
            )
        time.sleep(0.2)

    _append_event(events_path, {'event': 'timeout'})
    timeout_message = (
        f'tmux-claude timed out waiting for DONE_FILE: {done_path}. '
        'If the agent finished in the pane, ask it to write done.json there, '
        'or write done.json manually with {"status":"done","summary":"<short summary>"} and rerun the controller.'
    )
    return RunnerResult(
        backend='tmux-claude',
        status='timeout',
        command=commands[-1],
        returncode=124 if last_returncode == 0 else last_returncode,
        stdout=''.join(stdout_parts),
        stderr=''.join(stderr_parts) + timeout_message,
        run_dir=run_dir,
        prompt_path=runner_prompt_path,
        done_path=done_path,
    )


def _render_tmux_prompt(original_prompt: str, done_path: Path, workspace_dir: Path, unit_id: str) -> str:
    return f"""You are being controlled by workflow-controller through a tmux pane.

Workspace: {workspace_dir}
Unit id: {unit_id}
DONE_FILE: {done_path}

Execute the task below in the workspace. When finished, write DONE_FILE as JSON:
{{"status": "done", "summary": "<short summary>"}}

If blocked, write DONE_FILE as JSON:
{{"status": "blocked", "summary": "<exact blocker>"}}

Original task:

{original_prompt}
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
    raw_value = os.environ.get('RRC_TMUX_SUBMIT_DELAY_SECONDS')
    if raw_value is None:
        return DEFAULT_TMUX_SUBMIT_DELAY_SECONDS
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return DEFAULT_TMUX_SUBMIT_DELAY_SECONDS


def _uses_stdin_prompt(command: list[str]) -> bool:
    executable = Path(command[0]).name if command else ''
    return 'codex' in executable and command[-1:] == ['-']


def _new_run_dir(artifact_dir: Path, unit_id: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    return artifact_dir / 'runs' / f'{unit_id}-{timestamp}'


def _append_event(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {'ts': datetime.now(timezone.utc).isoformat(), **payload}
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + '\n')


def _read_done_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {'status': 'failed', 'summary': 'done.json is not valid JSON'}
    return payload if isinstance(payload, dict) else {'status': 'failed', 'summary': 'done.json is not an object'}
