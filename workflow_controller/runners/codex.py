from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from workflow_controller.runners.base import BaseRunner, RunnerRequest, RunnerResult


class CodexRunner(BaseRunner):
    """Runner that executes agents as subprocesses (supports both claude CLI and codex exec)."""

    def run(self, request: RunnerRequest) -> RunnerResult:
        return _run_subprocess_agent(request)


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
        env={**os.environ, **request.env} if request.env else None,
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
        runner_metadata=_request_metadata(request),
    )


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
            command = list(parts)
        else:
            command = [*parts, 'exec']
        if '--dangerously-bypass-approvals-and-sandbox' not in command:
            command.append('--dangerously-bypass-approvals-and-sandbox')
        if '-' not in command[2:]:
            command.append('-')
        return command
    return [*parts, prompt]


def _uses_stdin_prompt(command: list[str]) -> bool:
    executable = Path(command[0]).name if command else ''
    return 'codex' in executable and command[-1:] == ['-']


def _request_metadata(request: RunnerRequest) -> dict[str, Any]:
    return {
        'role': request.role,
        'backend': request.backend,
        'agent_command': request.agent_command,
        'tmux_target': request.tmux_target,
        'env_keys': sorted(request.env),
    }
