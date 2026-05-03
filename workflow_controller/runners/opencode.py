from __future__ import annotations

from workflow_controller.runners.base import BaseRunner, RunnerRequest, RunnerResult


class OpenCodeRunner(BaseRunner):
    """Placeholder stub for the OpenCode runner (to be implemented in V0.5)."""

    def run(self, request: RunnerRequest) -> RunnerResult:
        raise NotImplementedError('OpenCodeRunner is not yet implemented (planned for V0.5)')
