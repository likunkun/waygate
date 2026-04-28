from __future__ import annotations

import json
import stat
import time
from pathlib import Path

from workflow_controller.rrc_agent_runners import (
    RunnerRequest,
    _tmux_pane_looks_idle,
    make_runner,
    run_agent_backend,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def _make_executable(path: Path, content: str) -> Path:
    _write(path, content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_subprocess_runner_preserves_existing_agent_command_contract(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Implement this unit.')
    agent = _make_executable(
        tmp_path / 'fake-claude',
        """#!/usr/bin/env python3
import sys
from pathlib import Path
Path("subprocess-output.txt").write_text("changed\\n", encoding="utf-8")
print("argv=" + " ".join(sys.argv[1:]))
""",
    )

    request = RunnerRequest(
        backend='subprocess',
        workspace_dir=workspace,
        prompt_path=prompt_path,
        artifact_dir=tmp_path / 'artifacts',
        unit_id='unit-1',
        agent_command=str(agent),
        timeout_seconds=30,
    )

    result = run_agent_backend(request)

    assert result.backend == 'subprocess'
    assert result.status == 'done'
    assert result.returncode == 0
    assert result.command[0] == str(agent)
    assert 'argv=' in result.stdout
    assert (workspace / 'subprocess-output.txt').read_text(encoding='utf-8') == 'changed\n'


def test_tmux_claude_runner_dispatches_prompt_and_waits_for_done_signal(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Implement this unit.')
    tmux_log = tmp_path / 'tmux.log'
    fake_tmux = _make_executable(
        tmp_path / 'tmux',
        f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
with Path({str(tmux_log)!r}).open("a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:2] == ["paste-buffer"]:
    Path("tmux-output.txt").write_text("changed by tmux\\n", encoding="utf-8")
if sys.argv[1:2] == ["send-keys"] and sys.argv[-1:] == ["C-m"]:
    Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
        json.dumps({{
            "status": "done",
            "summary": "tmux finished",
            "run_id": os.environ["RRC_RUN_ID"],
        }}),
        encoding="utf-8",
    )
""",
    )

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

    result = run_agent_backend(request)

    assert result.backend == 'tmux-claude'
    assert result.status == 'done'
    assert result.returncode == 0
    assert result.done_payload['summary'] == 'tmux finished'
    assert result.done_payload['run_id'] == result.run_dir.name
    assert (workspace / 'tmux-output.txt').read_text(encoding='utf-8') == 'changed by tmux\n'
    log = tmux_log.read_text(encoding='utf-8')
    assert 'load-buffer' in log
    assert 'paste-buffer -t 1.2' in log
    assert 'send-keys -t 1.2 C-m' in log
    events = [
        json.loads(line)
        for line in (result.run_dir / 'events.log').read_text(encoding='utf-8').splitlines()
    ]
    assert any(event.get('event') == 'tmux_submit_delay' for event in events)
    prompt = result.prompt_path.read_text(encoding='utf-8')
    assert 'DONE_FILE:' in prompt
    assert 'RUN_ID:' in prompt
    assert 'Implement this unit.' in prompt


def test_tmux_claude_runner_pastes_short_dispatch_that_points_to_full_prompt(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Implement this unit with a long body.' * 500)
    tmux_log = tmp_path / 'tmux.log'
    fake_tmux = _make_executable(
        tmp_path / 'tmux',
        f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
with Path({str(tmux_log)!r}).open("a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:2] == ["send-keys"] and sys.argv[-1:] == ["C-m"]:
    Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
        json.dumps({{"status": "done", "summary": "tmux finished", "run_id": os.environ["RRC_RUN_ID"]}}),
        encoding="utf-8",
    )
""",
    )

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

    result = run_agent_backend(request)

    dispatch_path = result.run_dir / 'dispatch.md'
    assert result.status == 'done'
    assert result.prompt_path.name == 'prompt.md'
    assert dispatch_path.exists()
    dispatch_text = dispatch_path.read_text(encoding='utf-8')
    assert len(dispatch_text) < 2000
    assert f'PROMPT_FILE: {result.prompt_path}' in dispatch_text
    assert f'DONE_FILE: {result.done_path}' in dispatch_text
    assert f'RUN_ID: {result.run_dir.name}' in dispatch_text
    assert 'Read PROMPT_FILE first' in dispatch_text
    full_prompt = result.prompt_path.read_text(encoding='utf-8')
    assert 'Implement this unit with a long body.' in full_prompt
    log = tmux_log.read_text(encoding='utf-8')
    assert f'load-buffer {dispatch_path}' in log
    assert f'load-buffer {result.prompt_path}' not in log


def test_tmux_claude_runner_clears_claude_session_before_dispatch(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Implement this unit.')
    tmux_log = tmp_path / 'tmux.log'
    fake_tmux = _make_executable(
        tmp_path / 'tmux',
        f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
with Path({str(tmux_log)!r}).open("a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:2] == ["send-keys"] and sys.argv[-1:] == ["C-m"] and "/clear" not in sys.argv:
    Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
        json.dumps({{"status": "done", "summary": "tmux finished", "run_id": os.environ["RRC_RUN_ID"]}}),
        encoding="utf-8",
    )
""",
    )

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

    result = run_agent_backend(request)

    assert result.status == 'done'
    log_lines = tmux_log.read_text(encoding='utf-8').splitlines()
    assert log_lines[:3] == [
        'send-keys -t 1.2 C-u',
        'send-keys -t 1.2 /clear C-m',
        f'load-buffer {result.run_dir / "dispatch.md"}',
    ]


def test_tmux_claude_runner_rejects_done_signal_from_wrong_run_id(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Implement this unit.')
    fake_tmux = _make_executable(
        tmp_path / 'tmux',
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
if sys.argv[1:2] == ["send-keys"] and sys.argv[-1:] == ["C-m"]:
    Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
        json.dumps({"status": "done", "summary": "old run", "run_id": "old-run-id"}),
        encoding="utf-8",
    )
""",
    )

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

    result = run_agent_backend(request)

    assert result.status == 'done_file_wrong_run'
    assert result.returncode == 1
    assert result.done_payload['run_id'] == 'old-run-id'
    assert 'expected run_id' in result.stderr
    assert result.run_dir.name in result.stderr


def test_tmux_claude_runner_reports_invalid_done_json_separately(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Implement this unit.')
    fake_tmux = _make_executable(
        tmp_path / 'tmux',
        """#!/usr/bin/env python3
import os
import sys
from pathlib import Path
if sys.argv[1:2] == ["send-keys"] and sys.argv[-1:] == ["C-m"]:
    Path(os.environ["RRC_RUN_DONE_FILE"]).write_text("{not-json", encoding="utf-8")
""",
    )

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

    result = run_agent_backend(request)

    assert result.status == 'invalid_done_file'
    assert result.returncode == 1
    assert 'not valid JSON' in result.stderr
    assert result.done_payload['status'] == 'invalid_done_file'


def test_tmux_claude_timeout_reports_done_file_recovery_path(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Implement this unit.')
    fake_tmux = _make_executable(
        tmp_path / 'tmux',
        """#!/usr/bin/env python3
import sys
raise SystemExit(0)
""",
    )

    request = RunnerRequest(
        backend='tmux-claude',
        workspace_dir=workspace,
        prompt_path=prompt_path,
        artifact_dir=tmp_path / 'artifacts',
        unit_id='unit-timeout',
        agent_command=str(fake_tmux),
        tmux_target='1.2',
        timeout_seconds=1,
    )

    result = run_agent_backend(request)

    assert result.status == 'timeout'
    assert result.returncode == 124
    assert result.done_path is not None
    assert str(result.done_path) in result.stderr
    assert 'DONE_FILE' in result.stderr
    assert 'write done.json' in result.stderr


def test_tmux_claude_timeout_reports_idle_pane_without_done_file(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Implement this unit.')
    fake_tmux = _make_executable(
        tmp_path / 'tmux',
        """#!/usr/bin/env python3
import sys
if sys.argv[1:2] == ["capture-pane"]:
    print("Claude finished the work but did not write done.json")
    print("❯")
raise SystemExit(0)
""",
    )

    request = RunnerRequest(
        backend='tmux-claude',
        workspace_dir=workspace,
        prompt_path=prompt_path,
        artifact_dir=tmp_path / 'artifacts',
        unit_id='unit-idle',
        agent_command=str(fake_tmux),
        tmux_target='1.2',
        timeout_seconds=1,
    )

    result = run_agent_backend(request)

    assert result.status == 'agent_idle_without_done'
    assert result.returncode == 124
    assert result.done_path is not None
    assert 'tmux pane appears idle' in result.stderr
    assert 'Claude finished the work' in result.stderr
    assert result.run_dir.name in result.stderr


def test_tmux_claude_runner_fails_fast_when_pane_returns_idle_after_dispatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Implement this unit.')
    fake_tmux = _make_executable(
        tmp_path / 'tmux',
        """#!/usr/bin/env python3
import sys
if sys.argv[1:2] == ["capture-pane"]:
    print("Claude ignored the new prompt and returned to idle")
    print("❯")
raise SystemExit(0)
""",
    )
    monkeypatch.setenv('RRC_TMUX_IDLE_GRACE_SECONDS', '0')
    monkeypatch.setenv('RRC_TMUX_IDLE_POLL_SECONDS', '0.1')
    monkeypatch.setenv('RRC_TMUX_CLEAR_DELAY_SECONDS', '0')

    request = RunnerRequest(
        backend='tmux-claude',
        workspace_dir=workspace,
        prompt_path=prompt_path,
        artifact_dir=tmp_path / 'artifacts',
        unit_id='unit-idle-fast',
        agent_command=str(fake_tmux),
        tmux_target='1.2',
        timeout_seconds=2,
    )

    started = time.monotonic()
    result = run_agent_backend(request)
    elapsed = time.monotonic() - started

    assert result.status == 'agent_idle_without_done'
    assert elapsed < 1.0
    assert result.done_path is not None
    assert str(result.done_path) in result.stderr


def test_tmux_idle_detection_accepts_claude_prompt_with_insert_status() -> None:
    pane_tail = """
────────────────────────────────────────────────────────────────────────────────
❯ 
────────────────────────────────────────────────────────────────────────────────
  -- INSERT -- ⏵⏵ bypass permissions on (shift+tab to cycle)
"""

    assert _tmux_pane_looks_idle(pane_tail) is True


def test_tmux_idle_detection_rejects_claude_active_status_with_prompt_area() -> None:
    pane_tail = """
● Read(/tmp/prompt.md)
  ⎿  Read 931 lines

✢ Actualizing… (2m 9s · ↓ 3.6k tokens · almost done thinking)

────────────────────────────────────────────────────────────────────────────────
❯ 
────────────────────────────────────────────────────────────────────────────────
  -- INSERT -- ⏵⏵ bypass permissions on (shift+tab to cycle)
"""

    assert _tmux_pane_looks_idle(pane_tail) is False


def test_make_runner_maps_state_to_backend() -> None:
    assert make_runner({'agentRunner': 'tmux-claude'}).backend == 'tmux-claude'
    assert make_runner({'agentRunner': 'subprocess'}).backend == 'subprocess'
    assert make_runner({'agentCommand': 'claude'}).backend == 'subprocess'
