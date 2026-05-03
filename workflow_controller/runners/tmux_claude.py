from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflow_controller.runners.base import BaseRunner, RunnerRequest, RunnerResult


DEFAULT_TMUX_SUBMIT_DELAY_SECONDS = 0.5
DEFAULT_TMUX_CLEAR_DELAY_SECONDS = 0.5
DEFAULT_TMUX_IDLE_GRACE_SECONDS = 60.0
DEFAULT_TMUX_IDLE_POLL_SECONDS = 60.0
DEFAULT_TMUX_IDLE_NUDGE_SECONDS = 120.0
DEFAULT_TMUX_IDLE_MAX_NUDGES = 3


class TmuxClaudeRunner(BaseRunner):
    """Runner that dispatches prompts to a tmux pane and waits for a done signal."""

    def run(self, request: RunnerRequest) -> RunnerResult:
        return _run_tmux_claude(request)


def _run_tmux_claude(request: RunnerRequest) -> RunnerResult:
    if not request.tmux_target:
        raise ValueError('tmux-claude runner requires tmuxTarget or tmuxPane in state')

    runner_metadata = _request_metadata(request)
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
        **request.env,
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
                runner_metadata=runner_metadata,
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
    nudge_seconds = _tmux_idle_nudge_seconds()
    max_nudges = _tmux_idle_max_nudges()
    nudge_count = 0
    last_pane_content: str | None = None
    last_pane_change_time = time.monotonic()
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
                    runner_metadata=runner_metadata,
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
                    runner_metadata=runner_metadata,
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
                runner_metadata=runner_metadata,
            )
        now = time.monotonic()
        if idle_poll_seconds > 0 and now >= next_idle_check:
            pane_tail = _capture_tmux_pane(
                tmux_command=tmux_command,
                tmux_target=request.tmux_target,
                workspace_dir=request.workspace_dir,
                env=env,
            )
            if pane_tail != last_pane_content:
                last_pane_content = pane_tail
                last_pane_change_time = now
            elif (now - last_pane_change_time) >= nudge_seconds:
                if max_nudges > 0 and nudge_count < max_nudges:
                    if pane_tail:
                        (run_dir / 'tmux-pane-tail.txt').write_text(pane_tail, encoding='utf-8')
                    _append_event(events_path, {
                        'event': 'agent_nudge_sent',
                        'nudge_count': nudge_count + 1,
                        'seconds_since_change': now - last_pane_change_time,
                    })
                    subprocess.run(
                        [*tmux_command, 'send-keys', '-t', request.tmux_target, '继续', 'C-m'],
                        cwd=request.workspace_dir,
                        capture_output=True,
                        timeout=5,
                        check=False,
                        env=env,
                    )
                    nudge_count += 1
                    last_pane_change_time = now
                else:
                    if pane_tail:
                        (run_dir / 'tmux-pane-tail.txt').write_text(pane_tail, encoding='utf-8')
                    _append_event(events_path, {
                        'event': 'agent_idle_without_done',
                        'nudge_count': nudge_count,
                        'pane_tail_path': str(run_dir / 'tmux-pane-tail.txt') if pane_tail else None,
                    })
                    timeout_message = _tmux_timeout_message(
                        done_path=done_path,
                        run_id=run_id,
                        pane_tail=pane_tail,
                    )
                    return RunnerResult(
                        backend='tmux-claude',
                        status='agent_idle_without_done',
                        command=dispatch_commands[-1],
                        returncode=124 if last_returncode == 0 else last_returncode,
                        stdout=''.join(stdout_parts),
                        stderr=''.join(stderr_parts) + timeout_message,
                        run_dir=run_dir,
                        prompt_path=runner_prompt_path,
                        done_path=done_path,
                        runner_metadata=runner_metadata,
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
    status = 'timeout'
    _append_event(events_path, {
        'event': status,
        'pane_tail_path': str(run_dir / 'tmux-pane-tail.txt') if pane_tail else None,
    })
    timeout_message = _tmux_timeout_message(
        done_path=done_path,
        run_id=run_id,
        pane_tail=pane_tail,
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
        runner_metadata=runner_metadata,
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

IMPORTANT: The summary value must not contain ASCII double quotes ("). Use single quotes, Chinese quotes「」, or rephrase instead. The file must be valid JSON.

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
IMPORTANT: summary must not contain ASCII double quotes ("). Use single quotes or 「」 to avoid breaking JSON.
"""


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
        return False
    return raw_value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _tmux_clear_delay_seconds() -> float:
    return _env_float('RRC_TMUX_CLEAR_DELAY_SECONDS', DEFAULT_TMUX_CLEAR_DELAY_SECONDS)


def _tmux_idle_grace_seconds() -> float:
    return _env_float('RRC_TMUX_IDLE_GRACE_SECONDS', DEFAULT_TMUX_IDLE_GRACE_SECONDS)


def _tmux_idle_poll_seconds() -> float:
    return _env_float('RRC_TMUX_IDLE_POLL_SECONDS', DEFAULT_TMUX_IDLE_POLL_SECONDS)


def _tmux_idle_nudge_seconds() -> float:
    return _env_float('RRC_TMUX_IDLE_NUDGE_SECONDS', DEFAULT_TMUX_IDLE_NUDGE_SECONDS)


def _tmux_idle_max_nudges() -> int:
    raw = os.environ.get('RRC_TMUX_IDLE_MAX_NUDGES')
    if raw is None:
        return DEFAULT_TMUX_IDLE_MAX_NUDGES
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_TMUX_IDLE_MAX_NUDGES


def _env_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return default


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


def _tmux_timeout_message(*, done_path: Path, run_id: str, pane_tail: str) -> str:
    pane_hint = ''
    if pane_tail:
        pane_hint = f'\n\nLast captured tmux pane output:\n{_tail_text(pane_tail, max_chars=4000)}'
    return (
        f'tmux-claude timed out waiting for DONE_FILE: {done_path} (run_id={run_id}).'
        ' The tmux pane output stopped changing, so the agent likely finished or stalled without writing DONE_FILE.'
        ' If the agent finished in the pane, ask it to write done.json there,'
        ' or write done.json manually with '
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
    text = path.read_text(encoding='utf-8')
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {'status': 'invalid_done_file', 'summary': 'done.json is not an object'}
    except json.JSONDecodeError:
        pass
    # Fallback: extract status and run_id via regex when summary contains unescaped quotes
    status_m = re.search(r'"status"\s*:\s*"([^"]+)"', text)
    run_id_m = re.search(r'"run_id"\s*:\s*"([^"]+)"', text)
    if status_m and run_id_m:
        return {
            'status': status_m.group(1),
            'run_id': run_id_m.group(1),
            'summary': '(summary unparseable — done.json contained unescaped quotes)',
        }
    return {'status': 'invalid_done_file', 'summary': 'done.json is not valid JSON'}


def _request_metadata(request: RunnerRequest) -> dict[str, Any]:
    return {
        'role': request.role,
        'backend': request.backend,
        'agent_command': request.agent_command,
        'tmux_target': request.tmux_target,
        'env_keys': sorted(request.env),
    }
