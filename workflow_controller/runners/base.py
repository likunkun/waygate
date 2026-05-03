from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_TEST_STRATEGIST_COMMAND = 'codex exec --dangerously-bypass-approvals-and-sandbox -'
DEFAULT_AGENT_TIMEOUT_SECONDS = 7200


@dataclass(frozen=True)
class RunnerConfig:
    backend: str
    agent_command: str = ''
    tmux_target: str | None = None
    role: str | None = None
    env: dict[str, str] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        return {
            'role': self.role,
            'backend': self.backend,
            'agent_command': self.agent_command,
            'tmux_target': self.tmux_target,
            'env_keys': sorted(self.env),
        }


@dataclass(frozen=True)
class RunnerRequest:
    backend: str
    workspace_dir: Path
    prompt_path: Path
    artifact_dir: Path
    unit_id: str
    agent_command: str = ''
    tmux_target: str | None = None
    role: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = DEFAULT_AGENT_TIMEOUT_SECONDS


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
    runner_metadata: dict[str, Any] = field(default_factory=dict)


class BaseRunner(ABC):
    """Abstract base class for all agent runners."""

    @abstractmethod
    def run(self, request: RunnerRequest) -> RunnerResult:
        """Execute an agent for the given request and return the result."""
        ...
