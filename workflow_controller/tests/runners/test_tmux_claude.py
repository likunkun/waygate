from __future__ import annotations

import json
import stat
from pathlib import Path

from workflow_controller.runners.base import BaseRunner, RunnerRequest, RunnerResult
from workflow_controller.runners.tmux_claude import TmuxClaudeRunner
from workflow_controller.runners.codex import CodexRunner
from workflow_controller.runners.opencode import OpenCodeRunner
from workflow_controller.runners import make_runner, run_agent_backend


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def _make_executable(path: Path, content: str) -> Path:
    _write(path, content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class TestBaseRunner:
    def test_base_runner_is_abstract(self) -> None:
        import inspect
        assert inspect.isabstract(BaseRunner)

    def test_base_runner_has_run_method(self) -> None:
        assert hasattr(BaseRunner, 'run')

    def test_tmux_claude_runner_is_subclass(self) -> None:
        assert issubclass(TmuxClaudeRunner, BaseRunner)

    def test_codex_runner_is_subclass(self) -> None:
        assert issubclass(CodexRunner, BaseRunner)

    def test_opencode_runner_is_subclass(self) -> None:
        assert issubclass(OpenCodeRunner, BaseRunner)


class TestOpenCodeRunner:
    def test_opencode_runner_raises_not_implemented(self, tmp_path: Path) -> None:
        import pytest
        runner = OpenCodeRunner()
        request = RunnerRequest(
            backend='opencode',
            workspace_dir=tmp_path,
            prompt_path=tmp_path / 'prompt.md',
            artifact_dir=tmp_path / 'artifacts',
            unit_id='unit-1',
        )
        with pytest.raises(NotImplementedError):
            runner.run(request)


class TestTmuxClaudeRunner:
    def test_tmux_claude_runner_dispatches_and_waits(self, tmp_path: Path) -> None:
        workspace = tmp_path / 'workspace'
        workspace.mkdir()
        prompt_path = workspace / 'prompt.md'
        _write(prompt_path, 'Test task.')
        fake_tmux = _make_executable(
            tmp_path / 'tmux',
            f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
if sys.argv[1:2] == ["send-keys"] and sys.argv[-1:] == ["C-m"]:
    Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
        json.dumps({{"status": "done", "summary": "ok", "run_id": os.environ["RRC_RUN_ID"]}}),
        encoding="utf-8",
    )
""",
        )

        runner = TmuxClaudeRunner()
        request = RunnerRequest(
            backend='tmux-claude',
            workspace_dir=workspace,
            prompt_path=prompt_path,
            artifact_dir=tmp_path / 'artifacts',
            unit_id='unit-1',
            agent_command=str(fake_tmux),
            tmux_target='1.2',
            timeout_seconds=5,
        )

        result = runner.run(request)
        assert result.status == 'done'
        assert result.backend == 'tmux-claude'
        assert result.returncode == 0


class TestCodexRunner:
    def test_codex_runner_executes_subprocess(self, tmp_path: Path) -> None:
        workspace = tmp_path / 'workspace'
        workspace.mkdir()
        prompt_path = workspace / 'prompt.md'
        _write(prompt_path, 'Test task.')
        fake_agent = _make_executable(
            tmp_path / 'fake-agent',
            '#!/usr/bin/env python3\nprint("done")\n',
        )

        runner = CodexRunner()
        request = RunnerRequest(
            backend='subprocess',
            workspace_dir=workspace,
            prompt_path=prompt_path,
            artifact_dir=tmp_path / 'artifacts',
            unit_id='unit-1',
            agent_command=str(fake_agent),
            timeout_seconds=10,
        )

        result = runner.run(request)
        assert result.status == 'done'
        assert result.returncode == 0


class TestRunAgentBackend:
    def test_run_agent_backend_dispatches_subprocess(self, tmp_path: Path) -> None:
        workspace = tmp_path / 'workspace'
        workspace.mkdir()
        prompt_path = workspace / 'prompt.md'
        _write(prompt_path, 'Task.')
        fake_agent = _make_executable(
            tmp_path / 'fake-agent',
            '#!/usr/bin/env python3\nprint("ok")\n',
        )

        request = RunnerRequest(
            backend='subprocess',
            workspace_dir=workspace,
            prompt_path=prompt_path,
            artifact_dir=tmp_path / 'artifacts',
            unit_id='unit-1',
            agent_command=str(fake_agent),
            timeout_seconds=10,
        )

        result = run_agent_backend(request)
        assert result.status == 'done'

    def test_run_agent_backend_raises_for_unknown_backend(self, tmp_path: Path) -> None:
        import pytest
        request = RunnerRequest(
            backend='unknown-backend',
            workspace_dir=tmp_path,
            prompt_path=tmp_path / 'prompt.md',
            artifact_dir=tmp_path / 'artifacts',
            unit_id='unit-1',
        )
        with pytest.raises(ValueError, match='Unsupported'):
            run_agent_backend(request)



class TestMakeRunner:
    def test_make_runner_returns_runner_config(self) -> None:
        from workflow_controller.runners.base import RunnerConfig
        state = {'agentRunner': 'subprocess', 'agentCommand': 'claude'}
        config = make_runner(state)
        assert isinstance(config, RunnerConfig)
        assert config.backend == 'subprocess'

    def test_make_runner_test_strategist_uses_codex(self) -> None:
        state = {}
        config = make_runner(state, role='test_strategist')
        assert config.backend == 'subprocess'
        assert 'codex' in config.agent_command
