from __future__ import annotations

import json
import stat
import time
from pathlib import Path

import workflow_controller.runners.tmux_claude as tmux_runner
from workflow_controller.runners.base import RunnerRequest, DEFAULT_AGENT_TIMEOUT_SECONDS
from workflow_controller.runners.codex import _subprocess_agent_command
from workflow_controller.runners.tmux_claude import _tmux_idle_poll_seconds
from workflow_controller.runners import make_runner, run_agent_backend


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
    assert 'If the task requires asking the user a blocking clarification question' in prompt
    assert 'ask it in the active tmux agent pane' in prompt
    assert 'Do not write DONE_FILE while waiting for the user answer' in prompt
    assert 'Implement this unit.' in prompt


def test_tmux_codex_runner_reuses_tmux_dispatch_and_records_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Implement this unit.')
    tmux_log = tmp_path / 'tmux.log'
    sleep_calls: list[float] = []
    monkeypatch.setattr(tmux_runner.time, 'sleep', sleep_calls.append)
    fake_tmux = _make_executable(
        tmp_path / 'tmux',
        f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
with Path({str(tmux_log)!r}).open("a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:2] == ["send-keys"] and sys.argv[-1:] == ["Enter"]:
    Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
        json.dumps({{
            "status": "done",
            "summary": "codex tmux finished",
            "run_id": os.environ["RRC_RUN_ID"],
        }}),
        encoding="utf-8",
    )
""",
    )

    request = RunnerRequest(
        backend='tmux-codex',
        workspace_dir=workspace,
        prompt_path=prompt_path,
        artifact_dir=tmp_path / 'artifacts',
        unit_id='unit-1',
        agent_command=str(fake_tmux),
        tmux_target='1.2',
        timeout_seconds=5,
    )

    result = run_agent_backend(request)

    assert result.backend == 'tmux-codex'
    assert result.status == 'done'
    assert result.runner_metadata['backend'] == 'tmux-codex'
    log = tmux_log.read_text(encoding='utf-8')
    assert 'paste-buffer -t 1.2' in log
    assert 'send-keys -t 1.2 Enter' in log
    assert 'send-keys -t 1.2 C-m' not in log
    assert 'send-keys -t 1.2 C-j' not in log
    events = [
        json.loads(line)
        for line in (result.run_dir / 'events.log').read_text(encoding='utf-8').splitlines()
    ]
    assert events[0]['event'] == 'dispatch_started'
    assert events[0]['backend'] == 'tmux-codex'
    submit_delay = next(event for event in events if event.get('event') == 'tmux_submit_delay')
    assert submit_delay['seconds'] == 2.0
    assert sleep_calls == [2.0]


def test_tmux_codex_submit_key_can_be_overridden(tmp_path: Path, monkeypatch) -> None:
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
if sys.argv[1:2] == ["send-keys"] and sys.argv[-1:] == ["C-m"]:
    Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
        json.dumps({{"status": "done", "summary": "codex override finished", "run_id": os.environ["RRC_RUN_ID"]}}),
        encoding="utf-8",
    )
""",
    )
    monkeypatch.setenv('RRC_TMUX_CODEX_SUBMIT_KEY', 'C-m')
    monkeypatch.setenv('RRC_TMUX_CODEX_SUBMIT_DELAY_SECONDS', '0')

    request = RunnerRequest(
        backend='tmux-codex',
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
    assert 'send-keys -t 1.2 C-m' in tmux_log.read_text(encoding='utf-8')


def test_tmux_codex_retries_submit_when_prompt_remains_in_input(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Implement this unit.')
    tmux_log = tmp_path / 'tmux.log'
    submit_count_path = tmp_path / 'submit-count.txt'
    sleep_calls: list[float] = []
    monkeypatch.setattr(tmux_runner.time, 'sleep', sleep_calls.append)
    fake_tmux = _make_executable(
        tmp_path / 'tmux',
        f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
with Path({str(tmux_log)!r}).open("a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:2] == ["send-keys"] and sys.argv[-1:] == ["Enter"]:
    path = Path({str(submit_count_path)!r})
    count = int(path.read_text(encoding="utf-8")) if path.exists() else 0
    path.write_text(str(count + 1), encoding="utf-8")
    if count >= 1:
        Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
            json.dumps({{"status": "done", "summary": "codex retry finished", "run_id": os.environ["RRC_RUN_ID"]}}),
            encoding="utf-8",
        )
if sys.argv[1:2] == ["capture-pane"]:
    print("› workflow-controller dispatch.")
    print("RUN_ID: " + os.environ["RRC_RUN_ID"])
""",
    )

    request = RunnerRequest(
        backend='tmux-codex',
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
    log = tmux_log.read_text(encoding='utf-8')
    assert log.count('send-keys -t 1.2 Enter') == 2
    events = [
        json.loads(line)
        for line in (result.run_dir / 'events.log').read_text(encoding='utf-8').splitlines()
    ]
    retry_event = next(event for event in events if event.get('event') == 'tmux_codex_submit_retry')
    assert retry_event['reason'] == 'prompt_still_in_input'
    assert sleep_calls == [2.0, 1.0]


def test_tmux_codex_retries_submit_when_codex_collapses_pasted_input(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Implement this unit.')
    tmux_log = tmp_path / 'tmux.log'
    submit_count_path = tmp_path / 'submit-count.txt'
    sleep_calls: list[float] = []
    monkeypatch.setattr(tmux_runner.time, 'sleep', sleep_calls.append)
    fake_tmux = _make_executable(
        tmp_path / 'tmux',
        f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
with Path({str(tmux_log)!r}).open("a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:2] == ["send-keys"] and sys.argv[-1:] == ["Enter"]:
    path = Path({str(submit_count_path)!r})
    count = int(path.read_text(encoding="utf-8")) if path.exists() else 0
    path.write_text(str(count + 1), encoding="utf-8")
    if count >= 1:
        Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
            json.dumps({{"status": "done", "summary": "codex retry finished", "run_id": os.environ["RRC_RUN_ID"]}}),
            encoding="utf-8",
        )
if sys.argv[1:2] == ["capture-pane"]:
    print("› [Pasted Content 1024 chars]")
""",
    )

    request = RunnerRequest(
        backend='tmux-codex',
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
    log = tmux_log.read_text(encoding='utf-8')
    assert log.count('send-keys -t 1.2 Enter') == 2
    assert sleep_calls == [2.0, 1.0]


def test_tmux_codex_retries_submit_when_agent_is_not_working_after_submit(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Implement this unit.')
    tmux_log = tmp_path / 'tmux.log'
    submit_count_path = tmp_path / 'submit-count.txt'
    sleep_calls: list[float] = []
    monkeypatch.setattr(tmux_runner.time, 'sleep', sleep_calls.append)
    fake_tmux = _make_executable(
        tmp_path / 'tmux',
        f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
with Path({str(tmux_log)!r}).open("a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:2] == ["send-keys"] and sys.argv[-1:] == ["Enter"]:
    path = Path({str(submit_count_path)!r})
    count = int(path.read_text(encoding="utf-8")) if path.exists() else 0
    path.write_text(str(count + 1), encoding="utf-8")
    if count >= 1:
        Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
            json.dumps({{"status": "done", "summary": "codex retry finished", "run_id": os.environ["RRC_RUN_ID"]}}),
            encoding="utf-8",
        )
if sys.argv[1:2] == ["capture-pane"]:
    print("›")
""",
    )

    request = RunnerRequest(
        backend='tmux-codex',
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
    log = tmux_log.read_text(encoding='utf-8')
    assert log.count('send-keys -t 1.2 Enter') == 2
    events = [
        json.loads(line)
        for line in (result.run_dir / 'events.log').read_text(encoding='utf-8').splitlines()
    ]
    retry_event = next(event for event in events if event.get('event') == 'tmux_codex_submit_retry')
    assert retry_event['reason'] == 'agent_not_working_after_submit'
    assert sleep_calls == [2.0, 1.0]


def test_tmux_codex_waits_for_pane_to_leave_working_state_after_done(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Implement this unit.')
    tmux_log = tmp_path / 'tmux.log'
    capture_count_path = tmp_path / 'capture-count.txt'
    sleep_calls: list[float] = []
    monkeypatch.setattr(tmux_runner.time, 'sleep', sleep_calls.append)
    monkeypatch.setenv('RRC_TMUX_POST_DONE_IDLE_POLL_SECONDS', '0.1')
    fake_tmux = _make_executable(
        tmp_path / 'tmux',
        f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
with Path({str(tmux_log)!r}).open("a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:2] == ["send-keys"] and sys.argv[-1:] == ["Enter"]:
    Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
        json.dumps({{"status": "done", "summary": "codex wrote done early", "run_id": os.environ["RRC_RUN_ID"]}}),
        encoding="utf-8",
    )
if sys.argv[1:2] == ["capture-pane"]:
    path = Path({str(capture_count_path)!r})
    count = int(path.read_text(encoding="utf-8")) if path.exists() else 0
    path.write_text(str(count + 1), encoding="utf-8")
    if count == 0:
        print("◦ Working (4m 18s • esc to interrupt)")
    else:
        print("─ Worked for 4m 21s")
""",
    )

    request = RunnerRequest(
        backend='tmux-codex',
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
    assert 'capture-pane -t 1.2' in tmux_log.read_text(encoding='utf-8')
    events = [
        json.loads(line)
        for line in (result.run_dir / 'events.log').read_text(encoding='utf-8').splitlines()
    ]
    assert any(event.get('event') == 'tmux_agent_busy_after_done' for event in events)
    assert any(event.get('event') == 'tmux_agent_idle_after_done' for event in events)
    assert sleep_calls == [2.0, 0.1]


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
    assert f'PROMPT_FILE: {result.prompt_path.resolve()}' in dispatch_text
    assert f'DONE_FILE: {result.done_path.resolve()}' in dispatch_text
    assert f'RUN_ID: {result.run_dir.name}' in dispatch_text
    assert 'Read PROMPT_FILE first' in dispatch_text
    assert 'If PROMPT_FILE instructs you to ask the user a clarification question' in dispatch_text
    assert 'ask it in this tmux pane and continue after the user answers' in dispatch_text
    assert 'Do not write DONE_FILE until the task is complete or truly blocked' in dispatch_text
    full_prompt = result.prompt_path.read_text(encoding='utf-8')
    assert 'Implement this unit with a long body.' in full_prompt
    log = tmux_log.read_text(encoding='utf-8')
    assert f'load-buffer {dispatch_path}' in log
    assert f'load-buffer {result.prompt_path}' not in log


def test_tmux_runner_dispatch_prompt_uses_absolute_paths_for_relative_artifact_dir(tmp_path: Path, monkeypatch) -> None:
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
        json.dumps({"status": "done", "summary": "ok", "run_id": os.environ["RRC_RUN_ID"]}),
        encoding="utf-8",
    )
""",
    )
    monkeypatch.chdir(tmp_path)

    request = RunnerRequest(
        backend='tmux-claude',
        workspace_dir=workspace,
        prompt_path=prompt_path,
        artifact_dir=Path('relative-artifacts'),
        unit_id='unit-1',
        agent_command=str(fake_tmux),
        tmux_target='1.2',
        timeout_seconds=5,
    )

    result = run_agent_backend(request)

    assert result.status == 'done'
    dispatch_text = (result.run_dir / 'dispatch.md').read_text(encoding='utf-8')
    assert f'PROMPT_FILE: {result.prompt_path.resolve()}' in dispatch_text
    assert f'DONE_FILE: {result.done_path.resolve()}' in dispatch_text


def test_tmux_claude_runner_does_not_clear_claude_session_by_default(tmp_path: Path) -> None:
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
    assert 'send-keys -t 1.2 C-u' not in log_lines
    assert 'send-keys -t 1.2 /clear C-m' not in log_lines
    assert log_lines[:3] == [
        f'load-buffer {result.run_dir / "dispatch.md"}',
        'paste-buffer -t 1.2',
        'send-keys -t 1.2 C-m',
    ]


def test_tmux_claude_runner_clears_only_when_enabled(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setenv('RRC_TMUX_CLEAR_BEFORE_DISPATCH', '1')

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


def test_tmux_claude_timeout_reports_idle_pane_without_done_file(tmp_path: Path, monkeypatch) -> None:
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
raise SystemExit(0)
""",
    )
    monkeypatch.setenv('RRC_TMUX_IDLE_GRACE_SECONDS', '0')
    monkeypatch.setenv('RRC_TMUX_IDLE_POLL_SECONDS', '0.1')
    monkeypatch.setenv('RRC_TMUX_IDLE_NUDGE_SECONDS', '0')
    monkeypatch.setenv('RRC_TMUX_IDLE_MAX_NUDGES', '0')
    monkeypatch.setenv('RRC_TMUX_CLEAR_DELAY_SECONDS', '0')

    request = RunnerRequest(
        backend='tmux-claude',
        workspace_dir=workspace,
        prompt_path=prompt_path,
        artifact_dir=tmp_path / 'artifacts',
        unit_id='unit-idle',
        agent_command=str(fake_tmux),
        tmux_target='1.2',
        timeout_seconds=2,
    )

    result = run_agent_backend(request)

    assert result.status == 'agent_idle_without_done'
    assert result.returncode == 124
    assert result.done_path is not None
    assert 'tmux pane output stopped changing' in result.stderr
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
raise SystemExit(0)
""",
    )
    monkeypatch.setenv('RRC_TMUX_IDLE_GRACE_SECONDS', '0')
    monkeypatch.setenv('RRC_TMUX_IDLE_POLL_SECONDS', '0.1')
    monkeypatch.setenv('RRC_TMUX_IDLE_NUDGE_SECONDS', '0')
    monkeypatch.setenv('RRC_TMUX_IDLE_MAX_NUDGES', '0')
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


def test_tmux_claude_runner_idle_poll_default_is_60s(
    monkeypatch,
) -> None:
    monkeypatch.delenv('RRC_TMUX_IDLE_POLL_SECONDS', raising=False)

    assert _tmux_idle_poll_seconds() == 60.0





def test_runner_request_default_timeout_is_two_hours() -> None:
    assert DEFAULT_AGENT_TIMEOUT_SECONDS == 7200
    assert RunnerRequest(
        backend='subprocess',
        workspace_dir=Path('/workspace'),
        prompt_path=Path('/workspace/prompt.md'),
        artifact_dir=Path('/workspace/artifacts'),
        unit_id='unit-1',
    ).timeout_seconds == 7200



def test_make_runner_maps_state_to_backend() -> None:
    assert make_runner({'agentRunner': 'tmux-claude'}).backend == 'tmux-claude'
    assert make_runner({'agentRunner': 'tmux-codex'}).backend == 'tmux-codex'
    assert make_runner({'agentRunner': 'subprocess'}).backend == 'subprocess'
    assert make_runner({'agentCommand': 'claude'}).backend == 'subprocess'


def test_make_runner_defaults_test_strategist_to_codex_subprocess() -> None:
    runner = make_runner({}, role='test_strategist')

    assert runner.backend == 'subprocess'
    assert runner.agent_command == 'codex exec --dangerously-bypass-approvals-and-sandbox -'
    assert runner.role == 'test_strategist'
    assert runner.env == {}


def test_make_runner_role_specific_test_strategist_overrides_global_only_for_that_role() -> None:
    state = {
        'agentRunner': 'tmux-claude',
        'agentCommand': 'claude',
        'tmuxTarget': '1.2',
        'roleRunners': {
            'test_strategist': {
                'runner': 'subprocess',
                'command': 'codex exec -',
                'env': {
                    'HTTP_PROXY': 'http://127.0.0.1:7890',
                    'HTTPS_PROXY': 'http://127.0.0.1:7890',
                    'NO_PROXY': 'localhost,127.0.0.1',
                },
            },
        },
    }

    strategist_runner = make_runner(state, role='test_strategist')
    builder_runner = make_runner(state, role='builder')

    assert strategist_runner.backend == 'subprocess'
    assert strategist_runner.agent_command == 'codex exec -'
    assert strategist_runner.tmux_target is None
    assert strategist_runner.env == {
        'HTTP_PROXY': 'http://127.0.0.1:7890',
        'HTTPS_PROXY': 'http://127.0.0.1:7890',
        'NO_PROXY': 'localhost,127.0.0.1',
    }
    assert builder_runner.backend == 'tmux-claude'
    assert builder_runner.agent_command == 'claude'
    assert builder_runner.tmux_target == '1.2'
    assert builder_runner.env == {}


def test_default_test_strategist_command_expands_to_single_codex_exec_stdin_command() -> None:
    runner = make_runner({}, role='test_strategist')

    assert _subprocess_agent_command(runner.agent_command, 'Prompt body') == [
        'codex',
        'exec',
        '--dangerously-bypass-approvals-and-sandbox',
        '-',
    ]


def test_make_runner_env_only_test_strategist_config_keeps_codex_default() -> None:
    runner = make_runner({
        'agentRunner': 'tmux-claude',
        'agentCommand': 'claude',
        'roleRunners': {
            'test_strategist': {
                'env': {'HTTP_PROXY': 'http://127.0.0.1:7890'},
            },
        },
    }, role='test_strategist')

    assert runner.backend == 'subprocess'
    assert runner.agent_command == 'codex exec --dangerously-bypass-approvals-and-sandbox -'
    assert runner.env == {'HTTP_PROXY': 'http://127.0.0.1:7890'}


def test_make_runner_role_specific_refiner_overrides_global_only_for_that_role() -> None:
    state = {
        'agentRunner': 'tmux-claude',
        'agentCommand': 'claude',
        'tmuxTarget': '1.2',
        'roleRunners': {
            'refiner': {
                'runner': 'subprocess',
                'command': 'codex exec -',
                'env': {'SECRET_TOKEN': ''},
            },
        },
    }

    refiner_runner = make_runner(state, role='refiner')
    builder_runner = make_runner(state, role='builder')

    assert refiner_runner.backend == 'subprocess'
    assert refiner_runner.agent_command == 'codex exec -'
    assert refiner_runner.tmux_target is None
    assert refiner_runner.env == {'SECRET_TOKEN': ''}
    assert refiner_runner.to_metadata() == {
        'role': 'refiner',
        'backend': 'subprocess',
        'agent_command': 'codex exec -',
        'tmux_target': None,
        'env_keys': ['SECRET_TOKEN'],
    }
    assert builder_runner.backend == 'tmux-claude'
    assert builder_runner.agent_command == 'claude'
    assert builder_runner.tmux_target == '1.2'
    assert builder_runner.env == {}


def test_subprocess_runner_injects_env_only_from_runner_request(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv('HTTP_PROXY', raising=False)
    monkeypatch.delenv('HTTPS_PROXY', raising=False)
    monkeypatch.delenv('NO_PROXY', raising=False)
    monkeypatch.delenv('http_proxy', raising=False)
    monkeypatch.delenv('https_proxy', raising=False)
    monkeypatch.delenv('no_proxy', raising=False)
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Inspect env.')
    agent = _make_executable(
        tmp_path / 'fake-agent',
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
keys = ["HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"]
Path("env-capture.json").write_text(json.dumps({key: os.environ.get(key) for key in keys}), encoding="utf-8")
""",
    )

    clean_request = RunnerRequest(
        backend='subprocess',
        workspace_dir=workspace,
        prompt_path=prompt_path,
        artifact_dir=tmp_path / 'artifacts-clean',
        unit_id='builder',
        agent_command=str(agent),
        env={},
        timeout_seconds=30,
    )
    clean_result = run_agent_backend(clean_request)
    clean_capture = json.loads((workspace / 'env-capture.json').read_text(encoding='utf-8'))

    strategist_request = RunnerRequest(
        backend='subprocess',
        workspace_dir=workspace,
        prompt_path=prompt_path,
        artifact_dir=tmp_path / 'artifacts-strategist',
        unit_id='test-strategist',
        agent_command=str(agent),
        env={
            'HTTP_PROXY': 'http://127.0.0.1:7890',
            'HTTPS_PROXY': 'http://127.0.0.1:7890',
            'NO_PROXY': 'localhost,127.0.0.1',
        },
        timeout_seconds=30,
    )
    strategist_result = run_agent_backend(strategist_request)
    strategist_capture = json.loads((workspace / 'env-capture.json').read_text(encoding='utf-8'))

    assert clean_result.status == 'done'
    assert strategist_result.status == 'done'
    assert clean_capture == {'HTTP_PROXY': None, 'HTTPS_PROXY': None, 'NO_PROXY': None}
    assert strategist_capture == {
        'HTTP_PROXY': 'http://127.0.0.1:7890',
        'HTTPS_PROXY': 'http://127.0.0.1:7890',
        'NO_PROXY': 'localhost,127.0.0.1',
    }
    assert strategist_result.runner_metadata == {
        'role': None,
        'backend': 'subprocess',
        'agent_command': str(agent),
        'tmux_target': None,
        'env_keys': ['HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY'],
    }
    assert 'http://127.0.0.1:7890' not in json.dumps(strategist_result.runner_metadata)


def test_runner_config_metadata_redacts_env_values() -> None:
    runner = make_runner({
        'roleRunners': {
            'test_strategist': {
                'command': 'codex exec -',
                'env': {
                    'HTTP_PROXY': 'http://127.0.0.1:7890',
                    'SECRET_TOKEN': 'super-secret-token',
                },
            },
        },
    }, role='test_strategist')

    metadata = runner.to_metadata()

    assert metadata == {
        'role': 'test_strategist',
        'backend': 'subprocess',
        'agent_command': 'codex exec -',
        'tmux_target': None,
        'env_keys': ['HTTP_PROXY', 'SECRET_TOKEN'],
    }
    assert 'http://127.0.0.1:7890' not in json.dumps(metadata)
    assert 'super-secret-token' not in json.dumps(metadata)


def test_tmux_claude_runner_sends_continue_nudge_when_pane_unchanged(
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
import json, os, sys
from pathlib import Path
if sys.argv[1:2] == ["capture-pane"]:
    # always return same content - no change (no prompt character so _tmux_pane_looks_idle returns False)
    print("Claude is thinking about the task, please stand by")
elif sys.argv[1:2] == ["send-keys"] and sys.argv[2:3] == ["-t"]:
    text_args = sys.argv[4:]
    text = " ".join(text_args)
    # Check for the actual Chinese characters (继续 = U+7EE7 U+7EED)
    if "\\u7ee7\\u7eed" in text:
        done_file = os.environ.get("RRC_RUN_DONE_FILE", "")
        run_id = os.environ.get("RRC_RUN_ID", "")
        if done_file:
            Path(done_file).write_text(
                json.dumps({"status": "done", "summary": "nudged to complete", "run_id": run_id}),
                encoding="utf-8",
            )
raise SystemExit(0)
""",
    )
    monkeypatch.setenv('RRC_TMUX_IDLE_NUDGE_SECONDS', '0')
    monkeypatch.setenv('RRC_TMUX_IDLE_POLL_SECONDS', '0.1')
    monkeypatch.setenv('RRC_TMUX_IDLE_GRACE_SECONDS', '0')
    monkeypatch.setenv('RRC_TMUX_CLEAR_DELAY_SECONDS', '0')
    monkeypatch.setenv('RRC_TMUX_SUBMIT_DELAY_SECONDS', '0')

    request = RunnerRequest(
        backend='tmux-claude',
        workspace_dir=workspace,
        prompt_path=prompt_path,
        artifact_dir=tmp_path / 'artifacts',
        unit_id='unit-nudge',
        agent_command=str(fake_tmux),
        tmux_target='1.2',
        timeout_seconds=5,
    )

    result = run_agent_backend(request)

    assert result.status == 'done'
    assert result.done_payload.get('summary') == 'nudged to complete'
    events = [
        json.loads(line)
        for line in (result.run_dir / 'events.log').read_text(encoding='utf-8').splitlines()
    ]
    assert any(event.get('event') == 'agent_nudge_sent' for event in events)


def test_tmux_claude_runner_idle_nudge_disabled_when_nudge_seconds_is_zero_and_no_env(
    monkeypatch,
) -> None:
    from workflow_controller.runners.tmux_claude import _tmux_idle_nudge_seconds
    monkeypatch.delenv('RRC_TMUX_IDLE_NUDGE_SECONDS', raising=False)

    assert _tmux_idle_nudge_seconds() == 120.0
