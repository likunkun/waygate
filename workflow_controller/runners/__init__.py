from __future__ import annotations

from typing import Any

from workflow_controller.runners.base import (
    DEFAULT_TEST_STRATEGIST_COMMAND,
    BaseRunner,
    RunnerConfig,
    RunnerRequest,
    RunnerResult,
)
from workflow_controller.runners.codex import _run_subprocess_agent
from workflow_controller.runners.tmux_claude import _run_tmux_claude


def make_runner(state: dict[str, Any], role: str | None = None) -> RunnerConfig:
    role_config = _role_runner_config(state, role)
    if role == 'test_strategist' and not role_config:
        return RunnerConfig(
            backend='subprocess',
            agent_command=DEFAULT_TEST_STRATEGIST_COMMAND,
            role=role,
        )

    if role_config:
        default_command = DEFAULT_TEST_STRATEGIST_COMMAND if role == 'test_strategist' else ''
        return RunnerConfig(
            backend=str(role_config.get('runner') or role_config.get('backend') or 'subprocess'),
            agent_command=str(role_config.get('command') or role_config.get('agentCommand') or default_command),
            tmux_target=role_config.get('tmuxTarget') or role_config.get('tmuxPane'),
            role=role,
            env=_string_env(role_config.get('env')),
        )

    backend = str(state.get('agentRunner') or state.get('runnerBackend') or 'subprocess')
    return RunnerConfig(
        backend=backend,
        agent_command=str(state.get('agentCommand') or ''),
        tmux_target=state.get('tmuxTarget') or state.get('tmuxPane'),
        role=role,
    )


def run_agent_backend(request: RunnerRequest) -> RunnerResult:
    if request.backend == 'subprocess':
        return _run_subprocess_agent(request)
    if request.backend == 'tmux-claude':
        return _run_tmux_claude(request)
    raise ValueError(f'Unsupported agent runner backend: {request.backend}')


def _role_runner_config(state: dict[str, Any], role: str | None) -> dict[str, Any]:
    if not role:
        return {}
    role_runners = state.get('roleRunners')
    if not isinstance(role_runners, dict):
        return {}
    config = role_runners.get(role)
    return dict(config) if isinstance(config, dict) else {}


def _string_env(raw_env: Any) -> dict[str, str]:
    if not isinstance(raw_env, dict):
        return {}
    env: dict[str, str] = {}
    for key, value in raw_env.items():
        key_text = str(key).strip()
        if key_text and value is not None:
            env[key_text] = str(value)
    return env


__all__ = [
    'BaseRunner',
    'RunnerConfig',
    'RunnerRequest',
    'RunnerResult',
    'DEFAULT_TEST_STRATEGIST_COMMAND',
    'make_runner',
    'run_agent_backend',
]
