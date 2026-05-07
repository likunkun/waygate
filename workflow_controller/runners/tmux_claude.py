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
DEFAULT_TMUX_CODEX_SUBMIT_DELAY_SECONDS = 2.0
DEFAULT_TMUX_CLEAR_DELAY_SECONDS = 0.5
DEFAULT_TMUX_IDLE_GRACE_SECONDS = 60.0
DEFAULT_TMUX_IDLE_POLL_SECONDS = 60.0
DEFAULT_TMUX_IDLE_NUDGE_SECONDS = 120.0
DEFAULT_TMUX_IDLE_MAX_NUDGES = 3
DEFAULT_TMUX_CLAUDE_SUBMIT_KEY = 'C-m'
DEFAULT_TMUX_CODEX_SUBMIT_KEY = 'Enter'
DEFAULT_TMUX_CODEX_SUBMIT_RETRY_DELAY_SECONDS = 1.0
DEFAULT_TMUX_SUBMIT_RETRY_DELAY_SECONDS = 0.2
DEFAULT_TMUX_POST_DONE_IDLE_POLL_SECONDS = 0.5


class TmuxClaudeRunner(BaseRunner):
    """Runner that dispatches prompts to a tmux pane and waits for a done signal."""

    def run(self, request: RunnerRequest) -> RunnerResult:
        return _run_tmux_claude(request)


class TmuxCodexRunner(BaseRunner):
    """Runner that dispatches prompts to a tmux pane and waits for a done signal."""

    def run(self, request: RunnerRequest) -> RunnerResult:
        return _run_tmux_codex(request)


def _run_tmux_claude(request: RunnerRequest) -> RunnerResult:
    return _run_tmux_agent(request, backend='tmux-claude')


def _run_tmux_codex(request: RunnerRequest) -> RunnerResult:
    return _run_tmux_agent(request, backend='tmux-codex')


def _run_tmux_agent(request: RunnerRequest, *, backend: str) -> RunnerResult:
    if not request.tmux_target:
        raise ValueError(f'{backend} runner requires tmuxTarget or tmuxPane in state')

    runner_metadata = _request_metadata(request)
    run_dir = _new_run_dir(request.artifact_dir.resolve(), request.unit_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_dir.name
    done_path = run_dir / 'done.json'
    events_path = run_dir / 'events.log'
    runner_prompt_path = run_dir / 'prompt.md'
    dispatch_prompt_path = run_dir / 'dispatch.md'
    _append_event(events_path, {'event': 'dispatch_started', 'backend': backend})
    _write_pending_done_file(done_path, run_id)
    _append_event(events_path, {'event': 'done_file_precreated', 'status': 'pending'})
    runner_prompt_path.write_text(
        _render_tmux_prompt(
            original_prompt=request.prompt_path.read_text(encoding='utf-8'),
            done_path=done_path.resolve(),
            workspace_dir=request.workspace_dir.resolve(),
            unit_id=request.unit_id,
            run_id=run_id,
        ),
        encoding='utf-8',
    )
    dispatch_prompt_path.write_text(
        _render_tmux_dispatch_prompt(
            prompt_path=runner_prompt_path.resolve(),
            done_path=done_path.resolve(),
            run_id=run_id,
        ),
        encoding='utf-8',
    )

    tmux_command = _tmux_command(request.agent_command)
    env = {
        **os.environ,
        **request.env,
        'RRC_RUN_DONE_FILE': str(done_path.resolve()),
        'RRC_RUN_DIR': str(run_dir),
        'RRC_RUN_ID': run_id,
    }
    submit_key = _tmux_submit_key(backend)
    clear_commands = []
    if _tmux_clear_before_dispatch_enabled():
        clear_commands = [
            [*tmux_command, 'send-keys', '-t', request.tmux_target, 'C-u'],
            [*tmux_command, 'send-keys', '-t', request.tmux_target, '/clear', submit_key],
        ]
    dispatch_commands = [
        [*tmux_command, 'load-buffer', str(dispatch_prompt_path)],
        [*tmux_command, 'paste-buffer', '-t', request.tmux_target],
        [*tmux_command, 'send-keys', '-t', request.tmux_target, submit_key],
    ]
    commands = [*clear_commands, *dispatch_commands]

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    last_returncode = 0
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
                backend=backend,
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
            delay_seconds = _tmux_submit_delay_seconds(backend)
            _append_event(events_path, {
                'event': 'tmux_submit_delay',
                'seconds': delay_seconds,
            })
            time.sleep(delay_seconds)

    _retry_submit_if_prompt_still_pending(
        backend=backend,
        tmux_command=tmux_command,
        tmux_target=request.tmux_target,
        workspace_dir=request.workspace_dir,
        env=env,
        run_id=run_id,
        submit_key=submit_key,
        done_path=done_path,
        events_path=events_path,
    )

    deadline = time.monotonic() + request.timeout_seconds
    next_idle_check = time.monotonic() + _tmux_idle_grace_seconds()
    idle_poll_seconds = _tmux_idle_poll_seconds()
    nudge_seconds = _tmux_idle_nudge_seconds()
    max_nudges = _tmux_idle_max_nudges()
    nudge_count = 0
    last_pane_content: str | None = None
    last_pane_change_time = time.monotonic()
    pending_seen = False
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
                    backend=backend,
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
                    'rerun the current controller step after clearing the pane or ensuring the pane agent uses the latest prompt.'
                )
                _append_event(events_path, {
                    'event': 'done_file_wrong_run',
                    'expected_run_id': run_id,
                    'actual_run_id': actual_run_id,
                })
                return RunnerResult(
                    backend=backend,
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
            if status == 'pending':
                if not pending_seen:
                    _append_event(events_path, {'event': 'done_signal_pending'})
                    pending_seen = True
            else:
                _append_event(events_path, {'event': 'done_signal_seen', 'status': status})
                if backend == 'tmux-codex' and status == 'done':
                    idle_result = _wait_for_tmux_agent_idle_after_done(
                        tmux_command=tmux_command,
                        tmux_target=request.tmux_target,
                        workspace_dir=request.workspace_dir,
                        env=env,
                        events_path=events_path,
                        deadline=deadline,
                    )
                    if idle_result is not None:
                        return RunnerResult(
                            backend=backend,
                            status=idle_result['status'],
                            command=dispatch_commands[-1],
                            returncode=idle_result['returncode'],
                            stdout=''.join(stdout_parts),
                            stderr=''.join(stderr_parts) + idle_result['stderr'],
                            run_dir=run_dir,
                            prompt_path=runner_prompt_path,
                            done_path=done_path,
                            done_payload=payload,
                            runner_metadata=runner_metadata,
                        )
                return RunnerResult(
                    backend=backend,
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
                        [*tmux_command, 'send-keys', '-t', request.tmux_target, '继续', submit_key],
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
                        backend=backend,
                        done_path=done_path,
                        run_id=run_id,
                        pane_tail=pane_tail,
                    )
                    return RunnerResult(
                        backend=backend,
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
        backend=backend,
        done_path=done_path,
        run_id=run_id,
        pane_tail=pane_tail,
    )
    return RunnerResult(
        backend=backend,
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

If the task requires asking the user a blocking clarification question, ask it in the active tmux agent pane and continue after the user answers. Do not write DONE_FILE while waiting for the user answer. Only write DONE_FILE when the task is complete or truly blocked.

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
If PROMPT_FILE instructs you to ask the user a clarification question, ask it in this tmux pane and continue after the user answers. Do not write DONE_FILE until the task is complete or truly blocked.
IMPORTANT: summary must not contain ASCII double quotes ("). Use single quotes or 「」 to avoid breaking JSON.
"""


def _tmux_command(agent_command: str) -> list[str]:
    parts = shlex.split(agent_command) if agent_command else []
    if parts and Path(parts[0]).name == 'tmux':
        return parts
    return ['tmux']


def _tmux_submit_delay_seconds(backend: str) -> float:
    backend_env = 'RRC_TMUX_CODEX_SUBMIT_DELAY_SECONDS' if backend == 'tmux-codex' else 'RRC_TMUX_CLAUDE_SUBMIT_DELAY_SECONDS'
    backend_default = DEFAULT_TMUX_CODEX_SUBMIT_DELAY_SECONDS if backend == 'tmux-codex' else DEFAULT_TMUX_SUBMIT_DELAY_SECONDS
    if os.environ.get(backend_env) is not None:
        return _env_float(backend_env, backend_default)
    return _env_float('RRC_TMUX_SUBMIT_DELAY_SECONDS', backend_default)


def _tmux_codex_submit_retry_delay_seconds() -> float:
    return _env_float('RRC_TMUX_CODEX_SUBMIT_RETRY_DELAY_SECONDS', DEFAULT_TMUX_CODEX_SUBMIT_RETRY_DELAY_SECONDS)


def _tmux_submit_retry_delay_seconds(backend: str) -> float:
    if backend == 'tmux-codex':
        return _tmux_codex_submit_retry_delay_seconds()
    backend_env = 'RRC_TMUX_CLAUDE_SUBMIT_RETRY_DELAY_SECONDS' if backend == 'tmux-claude' else ''
    if backend_env and os.environ.get(backend_env) is not None:
        return _env_float(backend_env, DEFAULT_TMUX_SUBMIT_RETRY_DELAY_SECONDS)
    return _env_float('RRC_TMUX_SUBMIT_RETRY_DELAY_SECONDS', DEFAULT_TMUX_SUBMIT_RETRY_DELAY_SECONDS)


def _tmux_post_done_idle_poll_seconds() -> float:
    return _env_float('RRC_TMUX_POST_DONE_IDLE_POLL_SECONDS', DEFAULT_TMUX_POST_DONE_IDLE_POLL_SECONDS)


def _tmux_submit_key(backend: str) -> str:
    if backend == 'tmux-codex':
        return os.environ.get('RRC_TMUX_CODEX_SUBMIT_KEY', DEFAULT_TMUX_CODEX_SUBMIT_KEY).strip() or DEFAULT_TMUX_CODEX_SUBMIT_KEY
    return os.environ.get('RRC_TMUX_CLAUDE_SUBMIT_KEY', DEFAULT_TMUX_CLAUDE_SUBMIT_KEY).strip() or DEFAULT_TMUX_CLAUDE_SUBMIT_KEY


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


def _write_pending_done_file(path: Path, run_id: str) -> None:
    path.write_text(
        json.dumps(
            {
                'status': 'pending',
                'summary': 'waiting for tmux agent completion',
                'run_id': run_id,
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )


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


def _retry_submit_if_prompt_still_pending(
    *,
    backend: str,
    tmux_command: list[str],
    tmux_target: str,
    workspace_dir: Path,
    env: dict[str, str],
    run_id: str,
    submit_key: str,
    done_path: Path,
    events_path: Path,
) -> None:
    skipped_event = _tmux_submit_retry_event_name(backend, 'skipped')
    delay_event = _tmux_submit_retry_event_name(backend, 'delay')
    retry_event = _tmux_submit_retry_event_name(backend, '')
    if _done_file_has_non_pending_signal(done_path):
        _append_event(events_path, {'event': skipped_event, 'reason': 'done_file_exists'})
        return
    delay_seconds = _tmux_submit_retry_delay_seconds(backend)
    if delay_seconds > 0:
        _append_event(events_path, {
            'event': delay_event,
            'seconds': delay_seconds,
        })
        time.sleep(delay_seconds)
    pane_tail = _capture_tmux_pane(
        tmux_command=tmux_command,
        tmux_target=tmux_target,
        workspace_dir=workspace_dir,
        env=env,
    )
    retry_reason = _submit_retry_reason(pane_tail, run_id, backend=backend)
    if retry_reason is None:
        _append_event(events_path, {
            'event': skipped_event,
            'reason': 'agent_already_working',
        })
        return
    completed = subprocess.run(
        [*tmux_command, 'send-keys', '-t', tmux_target, submit_key],
        cwd=workspace_dir,
        capture_output=True,
        timeout=5,
        check=False,
        env=env,
    )
    _append_event(events_path, {
        'event': retry_event,
        'reason': retry_reason,
        'returncode': completed.returncode,
    })


def _codex_submit_retry_reason(pane_tail: str, run_id: str) -> str | None:
    return _submit_retry_reason(pane_tail, run_id, backend='tmux-codex')


def _done_file_has_non_pending_signal(path: Path) -> bool:
    if not path.exists():
        return False
    payload = _read_done_payload(path)
    return str(payload.get('status') or 'done') != 'pending'


def _submit_retry_reason(pane_tail: str, run_id: str, *, backend: str) -> str | None:
    if _tmux_pane_looks_busy(pane_tail):
        return None
    if run_id in pane_tail and 'workflow-controller dispatch.' in pane_tail:
        return 'prompt_still_in_input'
    # Codex collapses long pasted input in the TUI. tmux capture then loses the
    # RUN_ID even though the dispatch is still sitting in the input box.
    if 'Pasted Content' in pane_tail:
        return 'pasted_content_still_in_input'
    if backend != 'tmux-codex':
        return None
    return 'agent_not_working_after_submit'


def _tmux_submit_retry_event_name(backend: str, suffix: str) -> str:
    if backend == 'tmux-codex':
        base = 'tmux_codex_submit_retry'
    else:
        base = 'tmux_submit_retry'
    return f'{base}_{suffix}' if suffix else base


def _wait_for_tmux_agent_idle_after_done(
    *,
    tmux_command: list[str],
    tmux_target: str,
    workspace_dir: Path,
    env: dict[str, str],
    events_path: Path,
    deadline: float,
) -> dict[str, Any] | None:
    saw_busy = False
    poll_seconds = _tmux_post_done_idle_poll_seconds()
    while time.monotonic() < deadline:
        pane_tail = _capture_tmux_pane(
            tmux_command=tmux_command,
            tmux_target=tmux_target,
            workspace_dir=workspace_dir,
            env=env,
        )
        if not _tmux_pane_looks_busy(pane_tail):
            if saw_busy:
                _append_event(events_path, {'event': 'tmux_agent_idle_after_done'})
            return None
        saw_busy = True
        _append_event(events_path, {
            'event': 'tmux_agent_busy_after_done',
            'pane_state': _tail_text(pane_tail, max_chars=500),
        })
        time.sleep(poll_seconds)
    return {
        'status': 'agent_busy_after_done',
        'returncode': 124,
        'stderr': (
            'tmux-codex wrote DONE_FILE but the pane still shows a Working state. '
            'The controller did not dispatch the next step to avoid queuing a prompt into a busy Codex session.'
        ),
    }


def _tmux_pane_looks_busy(pane_tail: str) -> bool:
    lines = [line.strip() for line in str(pane_tail or '').splitlines() if line.strip()]
    last_busy = -1
    last_done = -1
    for index, line in enumerate(lines):
        if re.search(r'(?:^|\s|[•◦])\s*Working\s*\(', line) or re.search(r'[•◦]\s*Working\b', line):
            last_busy = index
        if re.search(r'\bWorked for\b', line):
            last_done = index
    return last_busy > last_done


def _tmux_timeout_message(*, backend: str, done_path: Path, run_id: str, pane_tail: str) -> str:
    pane_hint = ''
    if pane_tail:
        pane_hint = f'\n\nLast captured tmux pane output:\n{_tail_text(pane_tail, max_chars=4000)}'
    return (
        f'{backend} timed out waiting for DONE_FILE: {done_path} (run_id={run_id}).'
        ' The tmux pane output stopped changing, so the agent likely finished or stalled without writing DONE_FILE.'
        ' If the pane agent finished, ask it to write done.json there,'
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
