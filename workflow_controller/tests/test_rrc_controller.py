from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import workflow_controller.rrc_controller as rrc_controller_module
import workflow_controller.cli as cli_module
from workflow_controller.rrc_controller import RalphRefinerController, parse_args, run_unit_plan_drafter
from workflow_controller.steps._common import TestStrategistBlocked as StrategistBlocked
from workflow_controller.state_machine.transitions import reconcile_state, validate_objective_coverage


ROOT = Path(__file__).resolve().parents[2]


def run_rrc(*args: str, cwd: Path | None = None, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'workflow_controller.rrc_controller', *args],
        cwd=str(cwd or ROOT),
        text=True,
        input=input_text,
        capture_output=True,
        check=False,
    )


def run_rrc_with_pythonpath(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env['PYTHONPATH'] = f"{ROOT}{os.pathsep}{env['PYTHONPATH']}" if env.get('PYTHONPATH') else str(ROOT)
    return subprocess.run(
        [sys.executable, '-m', 'workflow_controller.rrc_controller', *args],
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_default_unit_plan_auto_revision_budget_is_five() -> None:
    assert rrc_controller_module.DEFAULT_MAX_UNIT_PLAN_AUTO_REVISIONS == 5


def _make_fake_tmux(
    tmp_path: Path,
    *,
    pane_command: str = '',
    pane_title: str = '',
    pane_current_path: str = '',
    pane_pid: str = '',
    pane_output: str = '',
    split_pane_id: str = '%42',
    list_panes_output: str = '',
) -> Path:
    tmux_log = tmp_path / 'tmux.log'
    fake_tmux = tmp_path / 'tmux'
    fake_tmux.write_text(
        f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
args = sys.argv[1:]
with Path({str(tmux_log)!r}).open("a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\\n")
if args[:2] == ["display-message", "-p"]:
    fmt = args[-1] if args else ""
    if "pane_current_command" in fmt:
        print({pane_command!r})
    elif "pane_current_path" in fmt:
        print({pane_current_path!r})
    elif "pane_pid" in fmt:
        print({pane_pid!r})
    elif "pane_title" in fmt:
        print({pane_title!r})
elif args[:1] == ["capture-pane"]:
    print({pane_output!r})
elif args[:1] == ["split-window"]:
    print({split_pane_id!r})
elif args[:1] == ["list-panes"]:
    print({list_panes_output!r})
""",
        encoding='utf-8',
    )
    fake_tmux.chmod(0o755)
    return fake_tmux


def _make_fake_ps(tmp_path: Path, output: str) -> Path:
    fake_ps = tmp_path / 'ps'
    fake_ps.write_text(
        f"""#!/usr/bin/env python3
print({output!r})
""",
        encoding='utf-8',
    )
    fake_ps.chmod(0o755)
    return fake_ps


def _prepend_path(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    current_path = os.environ.get('PATH')
    monkeypatch.setenv('PATH', f"{directory}{os.pathsep}{current_path}" if current_path else str(directory))


def test_init_creates_session_and_events_files(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'

    result = run_rrc('init', '--state-dir', str(state_dir))

    assert result.returncode == 0, result.stderr
    assert (state_dir / 'session.json').exists()
    assert (state_dir / 'events.jsonl').exists()

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'PLAN_CREATED'
    assert state['status'] == 'active'
    assert state['testStrategistEnabled'] is False
    assert state['codeSimplifierEnabled'] is True


def test_init_creates_agent_operating_guide_and_docs_layout(tmp_path: Path) -> None:
    state_dir = tmp_path / '.plan-ralph'

    result = run_rrc('init', '--state-dir', str(state_dir))

    assert result.returncode == 0, result.stderr
    agents_path = tmp_path / 'AGENTS.md'
    assert agents_path.exists()
    agents = agents_path.read_text(encoding='utf-8')
    assert 'Agent 操作规范' in agents
    assert 'ROADMAP.md' in agents
    assert '<state-dir>/session.json' in agents
    assert '一次只处理一个 unit' in agents
    assert '不要把自然语言总结当作完成依据' in agents
    assert '工程行为准则' in agents
    assert '每一处改动都应能追溯到当前 unit' in agents
    assert (tmp_path / 'docs' / 'product').is_dir()
    assert (tmp_path / 'docs' / 'architecture').is_dir()
    assert (tmp_path / 'docs' / 'workflow').is_dir()
    assert (tmp_path / 'docs' / 'operations').is_dir()
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['agentGuideArtifacts']['agents']['status'] == 'created'
    assert state['agentGuideArtifacts']['claude']['status'] == 'skipped'


def test_init_can_generate_claude_md_and_does_not_overwrite_existing_guides(tmp_path: Path) -> None:
    state_dir = tmp_path / '.plan-ralph'
    (tmp_path / 'AGENTS.md').write_text('# Existing agent rules\n', encoding='utf-8')
    (tmp_path / 'CLAUDE.md').write_text('# Existing Claude rules\n', encoding='utf-8')

    result = run_rrc('init', '--state-dir', str(state_dir), '--claude-md')

    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'AGENTS.md').read_text(encoding='utf-8') == '# Existing agent rules\n'
    assert (tmp_path / 'CLAUDE.md').read_text(encoding='utf-8') == '# Existing Claude rules\n'
    assert (tmp_path / 'AGENTS.md.generated').exists()
    assert (tmp_path / 'CLAUDE.md.generated').exists()
    assert 'Agent 操作规范' in (tmp_path / 'AGENTS.md.generated').read_text(encoding='utf-8')
    assert '唯一权威 Agent 操作规范' in (tmp_path / 'CLAUDE.md.generated').read_text(encoding='utf-8')
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['agentGuideArtifacts']['agents']['status'] == 'drafted'
    assert state['agentGuideArtifacts']['claude']['status'] == 'drafted'


def test_init_can_skip_agent_operating_guides(tmp_path: Path) -> None:
    state_dir = tmp_path / '.plan-ralph'

    result = run_rrc('init', '--state-dir', str(state_dir), '--no-agent-guides')

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / 'AGENTS.md').exists()
    assert not (tmp_path / 'docs').exists()
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['agentGuideArtifacts']['enabled'] is False
    assert state['agentGuideArtifacts']['agents']['status'] == 'skipped'


def test_start_initializes_agent_operating_guide_when_creating_state(tmp_path: Path) -> None:
    state_dir = tmp_path / '.plan-ralph'

    result = run_rrc(
        'start',
        '--state-dir',
        str(state_dir),
        '--max-steps',
        '0',
        '--color',
        'never',
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'AGENTS.md').exists()
    assert (tmp_path / 'docs' / 'workflow').is_dir()
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['agentGuideArtifacts']['agents']['status'] == 'created'


def test_init_with_target_and_workspace_without_ralph_creates_target_acceptance_state(tmp_path: Path) -> None:
    workspace = tmp_path / 'union'
    workspace.mkdir()
    (workspace / 'task_plan.md').write_text('# Plan\n\nV3.0 target acceptance.\n', encoding='utf-8')
    state_dir = workspace / '.rrc-controller-v3.0'
    fake_tmux = _make_fake_tmux(
        tmp_path,
        pane_command='claude',
        pane_title='claude',
        pane_current_path=str(workspace),
        pane_pid='12345',
        pane_output='Claude Code',
    )

    result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--target',
        'V3.0',
        '--runner',
        'tmux-claude',
        '--tmux-target',
        '3.0',
        '--agent',
        str(fake_tmux),
        '--force',
    )

    assert result.returncode == 0, result.stderr
    assert 'currentStep=REQUIREMENTS_DRAFT' in result.stdout
    assert 'nextAction=run_requirements_drafter' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['requestedOutcome'] == 'V3.0'
    assert state['feasibleOutcome'] == 'V3.0'
    assert state['workspacePath'] == str(workspace)
    assert state['currentUnitId'] == 'target-v3-0'
    assert state['units'][0]['id'] == 'target-v3-0'
    assert state['objectiveCoverage'][0]['units'] == ['target-v3-0']
    assert state['humanGatesRequired'] is True
    assert state['requirementsAccepted'] is False
    assert state['unitPlanAccepted'] is False
    assert state['agentRunner'] == 'tmux-claude'
    assert state['tmuxTarget'] == '3.0'
    assert str(workspace / 'task_plan.md') in state['targetContextFiles']
    assert Path(state['promptPath']).exists()
    assert 'Target acceptance: V3.0' in Path(state['promptPath']).read_text(encoding='utf-8')


def test_init_with_tmux_target_detects_codex_agent_and_selects_tmux_codex(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(tmp_path, pane_command='codex')
    _prepend_path(monkeypatch, tmp_path)

    controller = RalphRefinerController(
        state_dir=tmp_path / 'state',
        workspace_dir=workspace,
        target='V1.0',
        agent_runner=None,
        tmux_target='1.2',
        agent_guides_enabled=False,
    )

    state = controller.init_state(force=True)

    assert state['agentRunner'] == 'tmux-codex'
    assert state['tmuxTarget'] == '1.2'


def test_init_with_tmux_target_detects_claude_agent_and_selects_tmux_claude(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(tmp_path, pane_title='Claude Code')
    _prepend_path(monkeypatch, tmp_path)

    controller = RalphRefinerController(
        state_dir=tmp_path / 'state',
        workspace_dir=workspace,
        target='V1.0',
        agent_runner=None,
        tmux_target='1.2',
        agent_guides_enabled=False,
    )

    state = controller.init_state(force=True)

    assert state['agentRunner'] == 'tmux-claude'
    assert state['tmuxTarget'] == '1.2'


def test_init_with_tmux_target_blocks_explicit_runner_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(tmp_path, pane_output='codex is ready')
    _prepend_path(monkeypatch, tmp_path)
    controller = RalphRefinerController(
        state_dir=tmp_path / 'state',
        workspace_dir=workspace,
        target='V1.0',
        agent_runner='tmux-claude',
        tmux_target='1.2',
        agent_guides_enabled=False,
    )

    with pytest.raises(ValueError, match='--runner=tmux-claude.*tmux-codex'):
        controller.init_state(force=True)


def test_init_with_tmux_target_blocks_reverse_explicit_runner_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(tmp_path, pane_output='Claude Code is ready')
    _prepend_path(monkeypatch, tmp_path)
    controller = RalphRefinerController(
        state_dir=tmp_path / 'state',
        workspace_dir=workspace,
        target='V1.0',
        agent_runner='tmux-codex',
        tmux_target='1.2',
        agent_guides_enabled=False,
    )

    with pytest.raises(ValueError, match='--runner=tmux-codex.*tmux-claude'):
        controller.init_state(force=True)


def test_init_with_unknown_tmux_target_and_no_explicit_runner_defaults_to_tmux_codex(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(tmp_path)
    _prepend_path(monkeypatch, tmp_path)
    controller = RalphRefinerController(
        state_dir=tmp_path / 'state',
        workspace_dir=workspace,
        target='V1.0',
        agent_runner=None,
        tmux_target='1.2',
        agent_guides_enabled=False,
    )

    state = controller.init_state(force=True)

    assert state['agentRunner'] == 'tmux-codex'
    assert state['tmuxTarget'] == '1.2'


def test_init_with_explicit_tmux_codex_runner_auto_discovers_codex_pane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(
        tmp_path,
        pane_command='codex',
        pane_title='Codex CLI',
        pane_current_path=str(workspace),
        list_panes_output='%12',
    )
    _prepend_path(monkeypatch, tmp_path)
    monkeypatch.setenv('TMUX', '/tmp/tmux-session')
    monkeypatch.setenv('TMUX_PANE', '%24')
    controller = RalphRefinerController(
        state_dir=tmp_path / 'state',
        workspace_dir=workspace,
        target='V1.0',
        agent_runner='tmux-codex',
        tmux_target=None,
        agent_guides_enabled=False,
    )

    state = controller.init_state(force=True)

    assert state['agentRunner'] == 'tmux-codex'
    assert state['tmuxTarget'] == '%12'
    assert state['tmuxTargetResolution']['source'] == 'auto-detected'
    assert state['tmuxTargetResolution']['detectedBackend'] == 'tmux-codex'


def test_init_with_explicit_tmux_codex_runner_skips_current_controller_pane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(
        tmp_path,
        pane_command='codex',
        pane_title='Codex CLI',
        pane_current_path=str(workspace),
        list_panes_output='%24\n%43',
    )
    _prepend_path(monkeypatch, tmp_path)
    monkeypatch.setenv('TMUX', '/tmp/tmux-session')
    monkeypatch.setenv('TMUX_PANE', '%24')
    controller = RalphRefinerController(
        state_dir=tmp_path / 'state',
        workspace_dir=workspace,
        target='V1.0',
        agent_runner='tmux-codex',
        tmux_target=None,
        agent_guides_enabled=False,
    )

    state = controller.init_state(force=True)

    assert state['agentRunner'] == 'tmux-codex'
    assert state['tmuxTarget'] == '%43'
    assert state['tmuxTargetResolution']['source'] == 'auto-detected'


def test_init_without_tmux_target_inside_tmux_creates_claude_pane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(tmp_path, split_pane_id='%99')
    _prepend_path(monkeypatch, tmp_path)
    monkeypatch.setenv('TMUX', '/tmp/tmux-session')
    controller = RalphRefinerController(
        state_dir=tmp_path / 'state',
        workspace_dir=workspace,
        target='V1.0',
        agent_runner=None,
        tmux_target=None,
        agent_guides_enabled=False,
    )

    state = controller.init_state(force=True)

    assert state['agentRunner'] == 'tmux-claude'
    assert state['tmuxTarget'] == '%99'
    tmux_calls = [
        json.loads(line)
        for line in (tmp_path / 'tmux.log').read_text(encoding='utf-8').splitlines()
    ]
    split_call = next(args for args in tmux_calls if args[:1] == ['split-window'])
    assert split_call == [
        'split-window',
        '-h',
        '-P',
        '-F',
        '#{pane_id}',
        '-c',
        str(workspace),
        'claude',
        '--permission-mode',
        'bypassPermissions',
    ]


def test_auto_created_claude_pane_permission_mode_can_be_overridden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(tmp_path, split_pane_id='%98')
    _prepend_path(monkeypatch, tmp_path)
    monkeypatch.setenv('TMUX', '/tmp/tmux-session')
    monkeypatch.setenv('WAYGATE_AUTO_CLAUDE_PERMISSION_MODE', 'acceptEdits')
    controller = RalphRefinerController(
        state_dir=tmp_path / 'state',
        workspace_dir=workspace,
        target='V1.0',
        agent_runner=None,
        tmux_target=None,
        agent_guides_enabled=False,
    )

    state = controller.init_state(force=True)

    assert state['agentRunner'] == 'tmux-claude'
    assert state['tmuxTarget'] == '%98'
    tmux_calls = [
        json.loads(line)
        for line in (tmp_path / 'tmux.log').read_text(encoding='utf-8').splitlines()
    ]
    split_call = next(args for args in tmux_calls if args[:1] == ['split-window'])
    assert split_call == [
        'split-window',
        '-h',
        '-P',
        '-F',
        '#{pane_id}',
        '-c',
        str(workspace),
        'claude',
        '--permission-mode',
        'acceptEdits',
    ]


def test_auto_created_claude_pane_command_can_be_overridden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(tmp_path, split_pane_id='%97')
    _prepend_path(monkeypatch, tmp_path)
    monkeypatch.setenv('TMUX', '/tmp/tmux-session')
    monkeypatch.setenv('WAYGATE_AUTO_CLAUDE_COMMAND', 'claude --permission-mode dontAsk --model sonnet')
    controller = RalphRefinerController(
        state_dir=tmp_path / 'state',
        workspace_dir=workspace,
        target='V1.0',
        agent_runner=None,
        tmux_target=None,
        agent_guides_enabled=False,
    )

    state = controller.init_state(force=True)

    assert state['agentRunner'] == 'tmux-claude'
    assert state['tmuxTarget'] == '%97'
    tmux_calls = [
        json.loads(line)
        for line in (tmp_path / 'tmux.log').read_text(encoding='utf-8').splitlines()
    ]
    split_call = next(args for args in tmux_calls if args[:1] == ['split-window'])
    assert split_call == [
        'split-window',
        '-h',
        '-P',
        '-F',
        '#{pane_id}',
        '-c',
        str(workspace),
        'claude',
        '--permission-mode',
        'dontAsk',
        '--model',
        'sonnet',
    ]


def test_init_without_workspace_uses_current_directory_for_auto_claude_pane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(tmp_path, split_pane_id='%77')
    _prepend_path(monkeypatch, tmp_path)
    monkeypatch.setenv('TMUX', '/tmp/tmux-session')
    monkeypatch.chdir(workspace)
    controller = RalphRefinerController(
        state_dir=tmp_path / 'state',
        workspace_dir=None,
        target='V1.0',
        agent_runner=None,
        tmux_target=None,
        agent_guides_enabled=False,
    )

    state = controller.init_state(force=True)

    assert state['agentRunner'] == 'tmux-claude'
    assert state['tmuxTarget'] == '%77'
    tmux_calls = [
        json.loads(line)
        for line in (tmp_path / 'tmux.log').read_text(encoding='utf-8').splitlines()
    ]
    split_call = next(args for args in tmux_calls if args[:1] == ['split-window'])
    assert split_call[-4:] == [str(workspace), 'claude', '--permission-mode', 'bypassPermissions']


def test_init_without_tmux_target_outside_tmux_blocks_with_actionable_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    monkeypatch.delenv('TMUX', raising=False)
    controller = RalphRefinerController(
        state_dir=tmp_path / 'state',
        workspace_dir=workspace,
        target='V1.0',
        agent_runner=None,
        tmux_target=None,
        agent_guides_enabled=False,
    )

    with pytest.raises(ValueError, match='--tmux-target.*tmux session'):
        controller.init_state(force=True)


def test_init_with_explicit_subprocess_runner_does_not_auto_create_tmux_pane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    monkeypatch.delenv('TMUX', raising=False)
    controller = RalphRefinerController(
        state_dir=tmp_path / 'state',
        workspace_dir=workspace,
        target='V1.0',
        agent_runner='subprocess',
        tmux_target=None,
        agent_guides_enabled=False,
    )

    state = controller.init_state(force=True)

    assert state['agentRunner'] == 'subprocess'
    assert state['tmuxTarget'] is None


def test_start_existing_session_with_tmux_target_re_detects_agent_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    RalphRefinerController(
        state_dir=state_dir,
        workspace_dir=workspace,
        target='V1.0',
        agent_runner='subprocess',
        agent_guides_enabled=False,
    ).init_state(force=True)
    _make_fake_tmux(tmp_path, pane_command='codex')
    _prepend_path(monkeypatch, tmp_path)
    controller = RalphRefinerController(
        state_dir=state_dir,
        workspace_dir=workspace,
        target='V1.0',
        agent_runner=None,
        tmux_target='1.2',
        agent_guides_enabled=False,
    )

    controller.start(max_steps=0, output_func=lambda _message: None)

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['agentRunner'] == 'tmux-codex'
    assert state['tmuxTarget'] == '1.2'


def test_init_with_test_strategist_flag_enables_it_in_session(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'

    result = run_rrc(
        'init',
        '--state-dir', str(state_dir),
        '--test-strategist',
        '--test-strategist-command', 'my-codex exec -',
        '--test-strategist-env', 'HTTP_PROXY=http://127.0.0.1:7890',
        '--test-strategist-env', 'NO_PROXY=localhost',
    )

    assert result.returncode == 0, result.stderr
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['testStrategistEnabled'] is True
    ts = state['roleRunners']['test_strategist']
    assert ts['command'] == 'my-codex exec -'
    assert ts['env']['HTTP_PROXY'] == 'http://127.0.0.1:7890'
    assert ts['env']['NO_PROXY'] == 'localhost'


def test_init_test_strategist_flag_without_extras_uses_defaults(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'

    result = run_rrc('init', '--state-dir', str(state_dir), '--test-strategist')

    assert result.returncode == 0, result.stderr
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['testStrategistEnabled'] is True
    assert 'roleRunners' not in state or 'test_strategist' not in state.get('roleRunners', {})


def test_init_with_code_simplifier_flag_configures_refiner_runner_only(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'

    result = run_rrc(
        'init',
        '--state-dir', str(state_dir),
        '--runner', 'tmux-claude',
        '--tmux-target', '1.2',
        '--code-simplifier',
        '--code-simplifier-command', 'codex exec -',
        '--code-simplifier-env', 'SECRET_TOKEN',
        '--test-strategist',
        '--test-strategist-env', 'HTTP_PROXY=http://127.0.0.1:7890',
    )

    assert result.returncode == 0, result.stderr
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['codeSimplifierEnabled'] is True
    assert state['testStrategistEnabled'] is True
    assert state['roleRunners']['refiner'] == {
        'runner': 'subprocess',
        'command': 'codex exec -',
        'env': {'SECRET_TOKEN': ''},
    }
    assert state['roleRunners']['test_strategist'] == {
        'runner': 'subprocess',
        'env': {'HTTP_PROXY': 'http://127.0.0.1:7890'},
    }
    assert 'refiner' in state['roleRunners']
    assert 'test_strategist' in state['roleRunners']


def test_init_can_disable_default_code_simplifier(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'

    result = run_rrc('init', '--state-dir', str(state_dir), '--no-code-simplifier')

    assert result.returncode == 0, result.stderr
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['codeSimplifierEnabled'] is False


def test_status_reports_current_step_and_next_action(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir))
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc('status', '--state-dir', str(state_dir))

    assert result.returncode == 0, result.stderr
    assert 'currentStep=PLAN_CREATED' in result.stdout
    assert 'nextAction=require_scope_approval' in result.stdout


def _fake_agent_result(request, *, status: str = 'done', returncode: int = 0, stderr: str = ''):
    return SimpleNamespace(
        backend=request.backend,
        status=status,
        command=[request.agent_command or 'fake'],
        returncode=returncode,
        stdout='',
        stderr=stderr,
        run_dir=request.artifact_dir,
        prompt_path=request.prompt_path,
        done_payload={},
        runner_metadata={
            'role': request.role,
            'backend': request.backend,
            'agent_command': request.agent_command,
            'tmux_target': request.tmux_target,
            'env_keys': sorted(request.env),
        },
    )


def _write_valid_unit_plan(path: Path, *, command: str = 'pytest tests/test_delivery.py -q') -> None:
    path.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Test Case Matrix\n'
        '| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |\n'
        '| --- | --- | --- | --- | --- |\n'
        f'| AC-1 | TC-AC1 | integration | {command} | Delivery behavior works |\n\n'
        '## Controller State Patch\n\n'
        '```json\n'
        + json.dumps(
            {
                'currentUnitId': 'unit-01',
                'objectiveCoverage': [
                    {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'}
                ],
                'units': [
                    {
                        'id': 'unit-01',
                        'name': 'Delivery unit',
                        'passes': False,
                        'test_cases': [
                            {
                                'id': 'TC-AC1',
                                'acceptance_criterion': 'AC-1',
                                'layer': 'integration',
                                'command': command,
                                'expected': 'Delivery behavior works',
                            }
                        ],
                        'verification_commands': [command],
                    }
                ],
            }
        )
        + '\n```\n',
        encoding='utf-8',
    )


def _controller_state_for_unit_plan(workspace: Path) -> dict[str, Any]:
    return {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'currentStep': 'UNIT_PLAN_DRAFT',
        'lastVerifiedStep': 'REQUIREMENTS_DRAFT',
        'status': 'active',
        'requestedOutcome': 'usable-system',
        'feasibleOutcome': 'usable-system',
        'agentRunner': 'tmux-claude',
        'workspacePath': str(workspace),
        'testStrategistEnabled': True,
        'humanGatesRequired': True,
        'requirementsAccepted': True,
        'unitPlanAccepted': False,
        'objectiveCoverage': [
            {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {'id': 'unit-01', 'name': 'Delivery unit', 'scope': ['Implement delivery behavior'], 'passes': False},
        ],
    }


def test_unit_plan_drafter_persists_test_strategist_artifacts(tmp_path: Path, monkeypatch) -> None:
    approvals_dir = tmp_path / 'approvals'
    artifacts_dir = tmp_path / 'artifacts'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(
        '# Requirements & Acceptance Confirmation\n\n'
        '## 3. Acceptance Criteria\n'
        '- AC-1: Import retry state is visible.\n\n'
        '## 4. Test Strategy\n'
        '- E2E covers AC-1.\n',
        encoding='utf-8',
    )
    state = {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'requestedOutcome': 'usable-system',
        'feasibleOutcome': 'usable-system',
        'agentRunner': 'tmux-claude',
        'workspacePath': str(workspace),
        'testStrategistEnabled': True,
        'unitPlanRetryCount': 2,
        'roleRunners': {
            'test_strategist': {
                'runner': 'subprocess',
                'command': 'fake-strategist -',
                'env': {'SECRET_TOKEN': 'redacted-value'},
            },
        },
        'objectiveCoverage': [
            {'objective': 'Import retry state is visible', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {
                'id': 'unit-01',
                'name': 'Import retry visibility',
                'scope': ['Expose retry state in import UI'],
                'done_when': ['AC-1 is visible in browser'],
            },
        ],
    }

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            prompt = request.prompt_path.read_text(encoding='utf-8')
            assert 'AC-1: Import retry state is visible' in prompt
            assert 'Expose retry state in import UI' in prompt
            assert 'verification requirements' in prompt
            assert 'fake runner' in prompt
            assert 'mock-only flow' in prompt
            assert 'stubbed API-only flow' in prompt
            assert 'controller workflow orchestration tests may use fake runners' in prompt
            assert 'target project feature acceptance' in prompt
            assert 'Critical' in prompt and 'fake/mock/stubbed/page-load/screenshot evidence' in prompt
            assert 'Major' in prompt and 'fixture, real entrypoint, or expected assertion' in prompt
            assert 'suggested_fix' in prompt and 'Playwright or pytest command' in prompt
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC1-E2E',
                                        'layer': 'e2e',
                                        'command': 'pnpm exec playwright test import-retry.spec.ts --workers=1',
                                        'evidence': '',
                                        'expected': 'Retry state is visible in the browser',
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
            (request.artifact_dir / 'test-strategy.md').write_text(
                '# Test Strategy\n\nAC-1 -> TC-AC1-E2E via browser-visible E2E.\n',
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': []}),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-review-package.json').write_text(
                json.dumps({'ready_for_review': True, 'acceptance_criteria': ['AC-1']}),
                encoding='utf-8',
            )
        else:
            (request.artifact_dir / 'unit-plan-body.md').write_text(
                '# Unit Plan Confirmation\n\n'
                '## Test Case Matrix\n'
                '| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |\n'
                '| --- | --- | --- | --- | --- |\n'
                '| AC-1 | TC-AC1-E2E | e2e | pnpm exec playwright test import-retry.spec.ts --workers=1 | Retry state visible |\n\n'
                '## Controller State Patch\n\n'
                '```json\n'
                '{"currentUnitId":"unit-01","objectiveCoverage":[{"objective":"Import retry state is visible","units":["unit-01"],"status":"partial"}],"units":[{"id":"unit-01","name":"Import retry visibility","passes":false,"test_cases":[{"id":"TC-AC1-E2E","acceptance_criterion":"AC-1","layer":"e2e","command":"pnpm exec playwright test import-retry.spec.ts --workers=1","expected":"Retry state visible"}],"verification_commands":["pnpm exec playwright test import-retry.spec.ts --workers=1"],"verification_env":{"DATABASE_URL":"file:test.db"}}]}\n'
                '```\n',
                encoding='utf-8',
            )
        return SimpleNamespace(
            backend=request.backend,
            status='done',
            command=[request.agent_command or 'fake'],
            returncode=0,
            stdout='',
            stderr='',
            run_dir=request.artifact_dir,
            prompt_path=request.prompt_path,
            done_payload={},
            runner_metadata={
                'role': request.role,
                'backend': request.backend,
                'agent_command': request.agent_command,
                'tmux_target': request.tmux_target,
                'env_keys': sorted(request.env),
            },
        )

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    run_unit_plan_drafter(state, approvals_dir, artifacts_dir)

    draft_dir = artifacts_dir / 'unit-plan-draft'
    assert (draft_dir / 'test-strategy.json').exists()
    assert (draft_dir / 'unit-plan-gap-report.json').exists()
    assert (draft_dir / 'unit-plan-review-package.json').exists()
    assert (draft_dir / 'test-strategy.md').read_text(encoding='utf-8').startswith('# Test Strategy')
    summary = json.loads((draft_dir / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['test_strategist']['enabled'] is True
    assert summary['test_strategist']['actual_independence'] == 'role-runner'
    assert summary['test_strategist']['gap_counts'] == {'critical': 0, 'major': 0, 'minor': 0}
    assert summary['test_strategist']['planner_retry_count'] == 2
    assert summary['test_strategist']['fallback']['used'] is False
    assert summary['test_strategist']['runner']['env_keys'] == ['SECRET_TOKEN']
    assert 'redacted-value' not in json.dumps(summary)


def test_unit_plan_drafter_records_critical_gap_for_static_only_strategy(tmp_path: Path, monkeypatch) -> None:
    approvals_dir = tmp_path / 'approvals'
    artifacts_dir = tmp_path / 'artifacts'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(
        '# Requirements & Acceptance Confirmation\n\n'
        '## 3. Acceptance Criteria\n'
        '- AC-1: Browser retry state is visible.\n',
        encoding='utf-8',
    )
    state = {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'requestedOutcome': 'usable-system',
        'feasibleOutcome': 'usable-system',
        'agentRunner': 'tmux-claude',
        'workspacePath': str(workspace),
        'testStrategistEnabled': True,
        'objectiveCoverage': [
            {'objective': 'Browser retry state is visible', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {'id': 'unit-01', 'name': 'Import retry visibility', 'scope': ['Expose retry state']},
        ],
    }

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC1-STATIC',
                                        'layer': 'static',
                                        'command': 'pnpm exec tsc --noEmit',
                                        'expected': 'Types compile',
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
        else:
            (request.artifact_dir / 'unit-plan-body.md').write_text('# Unit Plan Confirmation\n', encoding='utf-8')
        return SimpleNamespace(
            backend=request.backend,
            status='done',
            command=[request.agent_command or 'fake'],
            returncode=0,
            stdout='',
            stderr='',
            run_dir=request.artifact_dir,
            prompt_path=request.prompt_path,
            done_payload={},
            runner_metadata={'role': request.role, 'backend': request.backend, 'env_keys': []},
        )

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    run_unit_plan_drafter(state, approvals_dir, artifacts_dir)

    draft_dir = artifacts_dir / 'unit-plan-draft'
    gap_report = json.loads((draft_dir / 'unit-plan-gap-report.json').read_text(encoding='utf-8'))
    assert gap_report['gap_counts']['critical'] == 1
    assert gap_report['gaps'][0]['severity'] == 'Critical'
    assert gap_report['gaps'][0]['type'] == 'static_only_coverage'
    summary = json.loads((draft_dir / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['test_strategist']['gap_counts']['critical'] == 1
    gate_path = approvals_dir / 'unit-plan.md'
    assert gate_path.exists(), 'Gate must be generated for human review even when critical gaps remain'
    gate_body = gate_path.read_text(encoding='utf-8')
    assert 'Unresolved Critical' in gate_body
    assert 'static_only_coverage' in gate_body


def test_unit_plan_drafter_materializes_strategy_artifacts_when_strategist_fails(tmp_path: Path, monkeypatch) -> None:
    approvals_dir = tmp_path / 'approvals'
    artifacts_dir = tmp_path / 'artifacts'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(
        '# Requirements & Acceptance Confirmation\n\n'
        '## 3. Acceptance Criteria\n'
        '- AC-1: Browser retry state is visible.\n',
        encoding='utf-8',
    )
    state = {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'requestedOutcome': 'usable-system',
        'feasibleOutcome': 'usable-system',
        'agentRunner': 'tmux-claude',
        'workspacePath': str(workspace),
        'testStrategistEnabled': True,
        'objectiveCoverage': [
            {'objective': 'Browser retry state is visible', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {'id': 'unit-01', 'name': 'Import retry visibility', 'scope': ['Expose retry state']},
        ],
    }

    def fake_run_agent_backend(request):
        if request.role is None:
            (request.artifact_dir / 'unit-plan-body.md').write_text('# Unit Plan Confirmation\n', encoding='utf-8')
        return SimpleNamespace(
            backend=request.backend,
            status='failed' if request.role == 'test_strategist' else 'done',
            command=[request.agent_command or 'fake'],
            returncode=1 if request.role == 'test_strategist' else 0,
            stdout='',
            stderr='strategist crashed',
            run_dir=request.artifact_dir,
            prompt_path=request.prompt_path,
            done_payload={},
            runner_metadata={'role': request.role, 'backend': request.backend, 'env_keys': []},
        )

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    run_unit_plan_drafter(state, approvals_dir, artifacts_dir)

    draft_dir = artifacts_dir / 'unit-plan-draft'
    assert json.loads((draft_dir / 'test-strategy.json').read_text(encoding='utf-8')) == {
        'acceptance_criteria': []
    }
    gap_report = json.loads((draft_dir / 'unit-plan-gap-report.json').read_text(encoding='utf-8'))
    assert gap_report['gap_counts']['critical'] == 0
    summary = json.loads((draft_dir / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['test_strategist']['actual_independence'] == 'same_family_fallback'
    assert summary['test_strategist']['independence'] == 'degraded'
    assert summary['test_strategist']['fallback'] == {
        'used': True,
        'reason': 'Test strategist failed with exit code 1',
    }


def test_unit_plan_drafter_rewrites_stale_strategist_artifacts_on_rerun(tmp_path: Path, monkeypatch) -> None:
    approvals_dir = tmp_path / 'approvals'
    artifacts_dir = tmp_path / 'artifacts'
    draft_dir = artifacts_dir / 'unit-plan-draft'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    draft_dir.mkdir(parents=True)
    (draft_dir / 'unit-plan-gap-report.json').write_text(
        json.dumps(
            {
                'gap_counts': {'critical': 1, 'major': 0, 'minor': 0},
                'gaps': [{'severity': 'Critical', 'type': 'stale_gap', 'message': 'old gap'}],
            }
        ),
        encoding='utf-8',
    )
    (draft_dir / 'unit-plan-review-package.json').write_text(
        json.dumps({'ready_for_review': True, 'stale': True}),
        encoding='utf-8',
    )
    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(
        '# Requirements & Acceptance Confirmation\n\n'
        '## 3. Acceptance Criteria\n'
        '- AC-1: Browser retry state is visible.\n',
        encoding='utf-8',
    )
    state = {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'requestedOutcome': 'usable-system',
        'feasibleOutcome': 'usable-system',
        'agentRunner': 'tmux-claude',
        'workspacePath': str(workspace),
        'testStrategistEnabled': True,
        'objectiveCoverage': [
            {'objective': 'Browser retry state is visible', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {'id': 'unit-01', 'name': 'Import retry visibility', 'scope': ['Expose retry state']},
        ],
    }

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            static_gap = {
                'severity': 'Critical',
                'type': 'static_only_coverage',
                'message': 'AC-1 is covered only by static checks',
            }
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {'id': 'TC-AC1-STATIC', 'layer': 'static', 'command': 'pnpm exec tsc --noEmit'}
                                ],
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gap_counts': {'critical': 1, 'major': 0, 'minor': 0}, 'gaps': [static_gap]}),
                encoding='utf-8',
            )
        else:
            (request.artifact_dir / 'unit-plan-body.md').write_text('# Unit Plan Confirmation\n', encoding='utf-8')
        return SimpleNamespace(
            backend=request.backend,
            status='done',
            command=[request.agent_command or 'fake'],
            returncode=0,
            stdout='',
            stderr='',
            run_dir=request.artifact_dir,
            prompt_path=request.prompt_path,
            done_payload={},
            runner_metadata={'role': request.role, 'backend': request.backend, 'env_keys': []},
        )

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    run_unit_plan_drafter(state, approvals_dir, artifacts_dir)

    gap_report = json.loads((draft_dir / 'unit-plan-gap-report.json').read_text(encoding='utf-8'))
    assert gap_report['gap_counts']['critical'] == 1
    assert gap_report['gaps'] == [
        {
            'severity': 'Critical',
            'type': 'static_only_coverage',
            'message': 'AC-1 is covered only by static checks',
        }
    ]
    review_package = json.loads((draft_dir / 'unit-plan-review-package.json').read_text(encoding='utf-8'))
    assert review_package['ready_for_review'] is False
    assert 'stale' not in review_package


def test_unit_plan_drafter_runs_planner_before_strategist_and_passes_body_in_prompt(tmp_path: Path, monkeypatch) -> None:
    approvals_dir = tmp_path / 'approvals'
    artifacts_dir = tmp_path / 'artifacts'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(
        '# Requirements & Acceptance Confirmation\n\n- AC-1: Delivery behavior works.\n',
        encoding='utf-8',
    )
    state = _controller_state_for_unit_plan(workspace)
    calls: list[str | None] = []

    def fake_run_agent_backend(request):
        calls.append(request.role)
        if request.role == 'test_strategist':
            prompt = request.prompt_path.read_text(encoding='utf-8')
            assert '# Unit Plan Confirmation' in prompt
            assert 'TC-AC1' in prompt
            assert 'Test Strategist internal state' not in prompt
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC1',
                                        'layer': 'integration',
                                        'command': 'pytest tests/test_delivery.py -q',
                                        'expected': 'Delivery behavior works',
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': []}),
                encoding='utf-8',
            )
        else:
            planner_prompt = request.prompt_path.read_text(encoding='utf-8')
            assert 'unit-plan-gap-report' not in planner_prompt
            assert 'Test Strategist internal state' not in planner_prompt
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    run_unit_plan_drafter(state, approvals_dir, artifacts_dir)

    assert calls == [None, 'test_strategist']


def test_codex_patcher_fills_critical_gap_and_enters_unit_plan_gate(tmp_path: Path, monkeypatch) -> None:
    """When initial strategist finds a Critical gap, the Codex patcher (2nd run) fills it.
    No Planner revision loop occurs."""
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')
    strategist_calls = 0
    planner_prompts: list[str] = []

    def fake_run_agent_backend(request):
        nonlocal strategist_calls
        if request.role == 'test_strategist':
            strategist_calls += 1
            # Initial run: returns a Critical gap; patcher (2nd run): returns no gaps
            gaps = [] if strategist_calls == 2 else [
                {
                    'id': 'GAP-AC1',
                    'severity': 'Critical',
                    'type': 'missing_acceptance_criterion_mapping',
                    'message': 'AC-1 has no mapped behavioral test',
                }
            ]
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC1',
                                        'layer': 'integration',
                                        'command': 'pytest tests/test_delivery.py -q',
                                        'expected': 'Delivery behavior works',
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': gaps}),
                encoding='utf-8',
            )
        else:
            planner_prompts.append(request.prompt_path.read_text(encoding='utf-8'))
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['status'] == 'active'
    assert state['testStrategistPlannerRetryCount'] == 0, 'Planner is no longer retried; patcher handles gaps'
    assert strategist_calls == 2, 'initial strategist run + patcher run'
    assert not any('Critical Test Strategy Gap Feedback' in p for p in planner_prompts), \
        'No Planner revision prompt should be sent; Codex patcher handles gap remediation'
    assert not (state_dir / 'approvals' / 'unit-plan.md').read_text(encoding='utf-8').count('GAP-AC1')
    summary = json.loads((state_dir / 'artifacts' / 'unit-plan-draft' / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['test_strategist']['planner_retry_count'] == 0
    assert summary['test_strategist']['gap_counts']['critical'] == 0


def test_controller_renders_major_minor_gap_report_in_existing_unit_plan_gate(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC1',
                                        'layer': 'integration',
                                        'command': 'pytest tests/test_delivery.py -q',
                                        'expected': 'Delivery behavior works',
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps(
                    {
                        'gaps': [
                            {
                                'id': 'MAJOR-AC1',
                                'severity': 'Major',
                                'type': 'weak_manual_evidence',
                                'message': 'Manual evidence should name the approval artifact',
                            },
                            {
                                'id': 'MINOR-AC1',
                                'severity': 'Minor',
                                'type': 'wording_gap',
                                'message': 'Expected result could be more specific',
                            },
                        ]
                    }
                ),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['nextAllowedActions'] == ['check_unit_plan_approval']
    gate_body = (state_dir / 'approvals' / 'unit-plan.md').read_text(encoding='utf-8')
    review_package = json.loads(
        (state_dir / 'artifacts' / 'unit-plan-draft' / 'unit-plan-review-package.json').read_text(encoding='utf-8')
    )
    assert review_package['gap_report']['gaps'] == [
        {
            'id': 'MAJOR-AC1',
            'severity': 'Major',
            'type': 'weak_manual_evidence',
            'message': 'Manual evidence should name the approval artifact',
        },
        {
            'id': 'MINOR-AC1',
            'severity': 'Minor',
            'type': 'wording_gap',
            'message': 'Expected result could be more specific',
        },
    ]
    assert '## Test Strategy Gap Report' in gate_body
    assert 'MAJOR-AC1' in gate_body
    assert 'Manual evidence should name the approval artifact' in gate_body
    assert 'MINOR-AC1' in gate_body
    assert 'Expected result could be more specific' in gate_body
    assert 'WAITING_TEST_STRATEGY_APPROVAL' not in json.dumps(state)


def test_suggested_fix_appears_in_major_minor_gap_report_in_gate(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': [{'id': 'AC-1', 'test_cases': [{'id': 'TC-1', 'layer': 'unit', 'command': 'pytest', 'expected': 'pass'}]}]}),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': [{
                    'id': 'MAJOR-AC1',
                    'severity': 'Major',
                    'type': 'weak_manual_evidence',
                    'message': 'Manual evidence should name the approval artifact',
                    'suggested_fix': 'Add a screenshot path or artifact name as evidence for AC-1',
                }]}),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)
    controller.run_once()

    gate_body = (state_dir / 'approvals' / 'unit-plan.md').read_text(encoding='utf-8')
    assert 'Add a screenshot path or artifact name as evidence for AC-1' in gate_body


def test_suggested_fix_appears_in_codex_patcher_prompt(tmp_path: Path, monkeypatch) -> None:
    """suggested_fix from the gap report is forwarded to the Codex patcher prompt
    so Codex knows exactly how to fill the gap."""
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Behavior works.\n', encoding='utf-8')

    patcher_prompts: list[str] = []

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': [{'id': 'AC-1', 'test_cases': []}]}),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': [{
                    'id': 'CRIT-AC1',
                    'severity': 'Critical',
                    'type': 'missing_acceptance_criterion_mapping',
                    'message': 'AC-1 has no mapped test cases',
                    'suggested_fix': 'Add a Playwright E2E test that verifies AC-1 behavior end-to-end',
                }]}),
                encoding='utf-8',
            )
            prompt = request.prompt_path.read_text(encoding='utf-8')
            if 'codex_patch' in prompt:
                patcher_prompts.append(prompt)
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)
    controller.run_once()

    assert patcher_prompts, 'Expected Codex patcher to be invoked'
    assert 'Add a Playwright E2E test that verifies AC-1 behavior end-to-end' in patcher_prompts[0]


def test_critical_gap_escalates_to_human_review_after_max_retries(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(workspace)
    initial_state['testStrategistCriticalMaxReworks'] = 0
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': []}),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': [{
                    'id': 'CRITICAL-AC1',
                    'severity': 'Critical',
                    'type': 'missing_acceptance_criterion_mapping',
                    'message': 'AC-1 has no mapped behavioral test',
                    'suggested_fix': 'Add a pytest integration test for AC-1',
                }]}),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL', f"Expected human review, got: {state['currentStep']}"
    assert state.get('status') != 'blocked'
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    assert gate_path.exists(), 'Gate file must exist for human review'
    gate_body = gate_path.read_text(encoding='utf-8')
    assert 'CRITICAL-AC1' in gate_body
    assert 'AC-1 has no mapped behavioral test' in gate_body
    assert 'Add a pytest integration test for AC-1' in gate_body



def test_e2e_test_strategist_unit_plan_flow(tmp_path: Path, monkeypatch) -> None:
    disabled_workspace = tmp_path / 'disabled-workspace'
    disabled_workspace.mkdir()
    disabled_state_dir = tmp_path / 'disabled-state'
    disabled_controller = RalphRefinerController(state_dir=disabled_state_dir, auto_approve=True)
    disabled_state = _controller_state_for_unit_plan(disabled_workspace)
    disabled_state['testStrategistEnabled'] = False
    disabled_controller.init_state(disabled_state, force=True)
    disabled_requirements = disabled_state_dir / 'approvals' / 'requirements-and-acceptance.md'
    disabled_requirements.parent.mkdir(parents=True, exist_ok=True)
    disabled_requirements.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')

    enabled_workspace = tmp_path / 'enabled-workspace'
    enabled_workspace.mkdir()
    enabled_state_dir = tmp_path / 'enabled-state'
    enabled_controller = RalphRefinerController(state_dir=enabled_state_dir, auto_approve=True)
    enabled_state = _controller_state_for_unit_plan(enabled_workspace)
    enabled_state['roleRunners'] = {
        'test_strategist': {
            'runner': 'subprocess',
            'command': 'codex exec --dangerously-bypass-approvals-and-sandbox -',
            'env': {
                'HTTP_PROXY': 'http://127.0.0.1:7890',
                'HTTPS_PROXY': 'http://127.0.0.1:7890',
                'NO_PROXY': 'localhost,127.0.0.1',
                'SECRET_TOKEN': 'super-secret-token',
            },
        }
    }
    enabled_controller.init_state(enabled_state, force=True)
    enabled_requirements = enabled_state_dir / 'approvals' / 'requirements-and-acceptance.md'
    enabled_requirements.parent.mkdir(parents=True, exist_ok=True)
    enabled_requirements.write_text(
        '# Requirements\n\n'
        '- AC-1: Delivery behavior works.\n'
        '- AC-2: Test strategy gaps are visible to humans.\n',
        encoding='utf-8',
    )

    calls: list[tuple[str | None, dict[str, str]]] = []
    planner_prompts: list[str] = []
    strategist_prompts: list[str] = []
    strategist_calls_by_state: dict[Path, int] = {}

    def fake_run_agent_backend(request):
        calls.append((request.role, dict(request.env)))
        if request.role == 'test_strategist':
            strategist_prompts.append(request.prompt_path.read_text(encoding='utf-8'))
            call_number = strategist_calls_by_state.get(request.artifact_dir, 0) + 1
            strategist_calls_by_state[request.artifact_dir] = call_number
            gaps = [
                {
                    'id': 'GAP-AC1',
                    'severity': 'Critical',
                    'type': 'missing_acceptance_criterion_mapping',
                    'message': 'AC-1 has no mapped behavioral test',
                }
            ] if call_number == 1 else [
                {
                    'id': 'MAJOR-AC2',
                    'severity': 'Major',
                    'type': 'weak_manual_evidence',
                    'message': 'Human evidence should name approvals/unit-plan.md',
                },
                {
                    'id': 'MINOR-AC2',
                    'severity': 'Minor',
                    'type': 'wording_gap',
                    'message': 'Expected result can be more specific',
                },
            ]
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC1',
                                        'layer': 'integration',
                                        'command': 'pytest tests/test_delivery.py -q',
                                        'fixture': 'fake unit planner and strategist',
                                        'environment': 'temporary state dir',
                                        'evidence': 'approvals/unit-plan.md',
                                        'expected': 'Delivery behavior works',
                                    }
                                ],
                            },
                            {
                                'id': 'AC-2',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC2',
                                        'layer': 'manual',
                                        'command': 'manual approval artifact inspection',
                                        'fixture': 'Major and Minor gap report',
                                        'environment': 'temporary state dir',
                                        'evidence': 'approvals/unit-plan.md contains Test Strategy Gap Report',
                                        'expected': 'Gaps are visible in the existing Unit Plan gate',
                                    }
                                ],
                            },
                        ]
                    }
                ),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(json.dumps({'gaps': gaps}), encoding='utf-8')
        else:
            planner_prompts.append(request.prompt_path.read_text(encoding='utf-8'))
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    disabled_result = disabled_controller.run_once()

    assert disabled_result['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    disabled_draft_dir = disabled_state_dir / 'artifacts' / 'unit-plan-draft'
    assert (disabled_state_dir / 'approvals' / 'unit-plan.md').exists()
    assert not (disabled_draft_dir / 'test-strategy.json').exists()
    assert not (disabled_draft_dir / 'unit-plan-gap-report.json').exists()
    assert not (disabled_draft_dir / 'unit-plan-review-package.json').exists()

    enabled_result = enabled_controller.run_once()

    assert enabled_result['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert enabled_result['status'] == 'active'
    assert enabled_result['testStrategistPlannerRetryCount'] == 0, 'Planner runs once; patcher handles gaps'
    assert 'WAITING_TEST_STRATEGY_APPROVAL' not in json.dumps(enabled_result)
    role_calls = [role for role, _env in calls]
    # disabled planner, enabled planner, initial strategist, patcher (no Planner revision loop)
    assert role_calls == [None, None, 'test_strategist', 'test_strategist']
    strategist_envs = [env for role, env in calls if role == 'test_strategist']
    non_strategist_envs = [env for role, env in calls if role is None]
    assert all(env['HTTP_PROXY'] == 'http://127.0.0.1:7890' for env in strategist_envs)
    assert all('HTTP_PROXY' not in env for env in non_strategist_envs)
    assert not any('Critical Test Strategy Gap Feedback' in prompt for prompt in planner_prompts), \
        'Planner should not receive gap feedback; Codex patcher handles remediation'
    assert any('AC-1: Delivery behavior works' in prompt and '# Unit Plan Confirmation' in prompt for prompt in strategist_prompts)

    enabled_draft_dir = enabled_state_dir / 'artifacts' / 'unit-plan-draft'
    gate_body = (enabled_state_dir / 'approvals' / 'unit-plan.md').read_text(encoding='utf-8')
    summary = json.loads((enabled_draft_dir / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    review_package = json.loads((enabled_draft_dir / 'unit-plan-review-package.json').read_text(encoding='utf-8'))
    gap_report = json.loads((enabled_draft_dir / 'unit-plan-gap-report.json').read_text(encoding='utf-8'))
    assert (enabled_draft_dir / 'test-strategy.json').exists()
    assert (enabled_draft_dir / 'test-strategy.md').exists()
    assert summary['test_strategist']['enabled'] is True
    assert summary['test_strategist']['runner']['env_keys'] == [
        'HTTPS_PROXY',
        'HTTP_PROXY',
        'NO_PROXY',
        'SECRET_TOKEN',
    ]
    assert summary['test_strategist']['gap_counts'] == {'critical': 0, 'major': 1, 'minor': 1}
    assert summary['test_strategist']['planner_retry_count'] == 0
    assert review_package['ready_for_review'] is True
    assert gap_report['gap_counts'] == {'critical': 0, 'major': 1, 'minor': 1}
    assert 'GAP-AC1' not in gate_body
    assert '## Test Strategy Gap Report' in gate_body
    assert 'MAJOR-AC2' in gate_body
    assert 'MINOR-AC2' in gate_body
    serialized_artifacts = json.dumps(summary) + json.dumps(review_package) + gate_body
    assert 'super-secret-token' not in serialized_artifacts
    assert 'http://127.0.0.1:7890' not in serialized_artifacts



def test_controller_escalates_to_human_review_after_third_unresolved_critical_gap(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')
    strategist_calls = 0

    def fake_run_agent_backend(request):
        nonlocal strategist_calls
        if request.role == 'test_strategist':
            strategist_calls += 1
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': []}),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': [{
                    'id': 'GAP-AC1',
                    'severity': 'Critical',
                    'type': 'missing_acceptance_criterion_mapping',
                    'message': 'AC-1 has no mapped behavioral test',
                }]}),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state.get('status') != 'blocked'
    assert state['testStrategistPlannerRetryCount'] == 0, 'Planner is no longer retried for test strategy gaps'
    assert strategist_calls == 2, 'initial strategist run + patcher run (both return gappy strategy)'
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    assert gate_path.exists()
    gate_body = gate_path.read_text(encoding='utf-8')
    assert 'GAP-AC1' in gate_body
    assert 'Unresolved Critical' in gate_body


def test_controller_blocks_when_test_strategist_fallback_is_not_allowed(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(workspace)
    initial_state['allowTestStrategistFallback'] = False
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            return _fake_agent_result(request, status='failed', returncode=127, stderr='codex: not found')
        _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['status'] == 'blocked'
    assert state['currentStep'] == 'UNIT_PLAN_DRAFT'
    assert 'Test strategist failed with exit code 127' in state['blockedReason']
    assert 'fallback is not allowed' in state['blockedReason']


def test_controller_continues_with_degraded_independence_when_strategist_fallback_allowed(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')
    strategist_calls = 0

    def fake_run_agent_backend(request):
        nonlocal strategist_calls
        if request.role == 'test_strategist':
            strategist_calls += 1
            return _fake_agent_result(request, status='failed', returncode=127, stderr='codex: not found')
        _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['status'] == 'active'
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['testStrategistPlannerRetryCount'] == 0
    assert strategist_calls == 1
    draft_dir = state_dir / 'artifacts' / 'unit-plan-draft'
    gap_report = json.loads((draft_dir / 'unit-plan-gap-report.json').read_text(encoding='utf-8'))
    assert gap_report['gap_counts']['critical'] == 0
    summary = json.loads((draft_dir / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['test_strategist']['actual_independence'] == 'same_family_fallback'
    assert summary['test_strategist']['independence'] == 'degraded'
    assert summary['test_strategist']['fallback'] == {
        'used': True,
        'reason': 'Test strategist failed with exit code 127',
    }



def test_controller_ignores_partial_critical_artifacts_when_strategist_fallback_allowed(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')
    strategist_calls = 0

    def fake_run_agent_backend(request):
        nonlocal strategist_calls
        if request.role == 'test_strategist':
            strategist_calls += 1
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps(
                    {
                        'gap_counts': {'critical': 1, 'major': 0, 'minor': 0},
                        'gaps': [
                            {
                                'id': 'PARTIAL-GAP',
                                'severity': 'Critical',
                                'type': 'partial_failed_strategist_output',
                                'message': 'partial output before crash',
                            }
                        ],
                    }
                ),
                encoding='utf-8',
            )
            return _fake_agent_result(request, status='failed', returncode=1, stderr='strategist crashed')
        _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['status'] == 'active'
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert strategist_calls == 1
    draft_dir = state_dir / 'artifacts' / 'unit-plan-draft'
    gap_report = json.loads((draft_dir / 'unit-plan-gap-report.json').read_text(encoding='utf-8'))
    assert gap_report['gap_counts']['critical'] == 0
    assert gap_report['gaps'] == []
    assert 'PARTIAL-GAP' not in json.dumps(gap_report)
    summary = json.loads((draft_dir / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['test_strategist']['actual_independence'] == 'same_family_fallback'
    assert summary['test_strategist']['fallback']['reason'] == 'Test strategist failed with exit code 1'



def test_controller_resets_stale_strategist_retry_count_for_fresh_unit_plan_cycle(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(workspace)
    initial_state['testStrategistPlannerRetryCount'] = 2
    initial_state['unitPlanRetryCount'] = 2
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps(
                    {
                        'acceptance_criteria': [
                            {
                                'id': 'AC-1',
                                'test_cases': [
                                    {
                                        'id': 'TC-AC1',
                                        'layer': 'integration',
                                        'command': 'pytest tests/test_delivery.py -q',
                                        'expected': 'Delivery behavior works',
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': []}),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['testStrategistPlannerRetryCount'] == 0
    assert state['unitPlanRetryCount'] == 0
    summary = json.loads((state_dir / 'artifacts' / 'unit-plan-draft' / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['test_strategist']['planner_retry_count'] == 0


def test_controller_escalates_unit_plan_gate_revision_to_human_after_unresolved_critical_gap(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(workspace)
    initial_state['currentStep'] = 'WAITING_UNIT_PLAN_APPROVAL'
    initial_state['unitPlanDraftGenerated'] = True
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')
    (approvals_dir / 'unit-plan.md').write_text('# Unit Plan Confirmation\n\nReviewer note: add behavioral coverage.\n', encoding='utf-8')
    strategist_calls = 0

    def fake_run_agent_backend(request):
        nonlocal strategist_calls
        if request.role == 'test_strategist':
            strategist_calls += 1
            (request.artifact_dir / 'test-strategy.json').write_text(json.dumps({'acceptance_criteria': []}), encoding='utf-8')
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps(
                    {
                        'gaps': [
                            {
                                'id': 'GAP-REVISION',
                                'severity': 'Critical',
                                'type': 'missing_acceptance_criterion_mapping',
                                'message': 'AC-1 has no mapped behavioral test',
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    controller.revise_human_gate('unit-plan')

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state.get('status') != 'blocked'
    assert state['testStrategistPlannerRetryCount'] == 0, 'Planner is no longer retried for test strategy gaps'
    assert strategist_calls == 2, 'initial strategist run + patcher run (both return gappy strategy)'
    gate_body = (state_dir / 'approvals' / 'unit-plan.md').read_text(encoding='utf-8')
    assert 'GAP-REVISION' in gate_body
    assert 'Unresolved Critical' in gate_body


def test_controller_escalates_final_acceptance_unit_plan_reroute_to_human_after_unresolved_critical_gap(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(workspace)
    initial_state.update(
        {
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'scopeApproved': True,
            'unitPlanAccepted': True,
            'unitPlanDraftGenerated': True,
            'finalAcceptanceAccepted': False,
        }
    )
    initial_state['objectiveCoverage'][0]['status'] = 'covered'
    initial_state['units'][0]['passes'] = True
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n\n- AC-1: Delivery behavior works.\n', encoding='utf-8')
    (approvals_dir / 'unit-plan.md').write_text('# Unit Plan Confirmation\n', encoding='utf-8')
    (approvals_dir / 'final-acceptance.md').write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [x] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [ ] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        'Reviewer note: final acceptance shows verification commands need broader coverage.\n',
        encoding='utf-8',
    )
    strategist_calls = 0

    def fake_run_agent_backend(request):
        nonlocal strategist_calls
        if request.role == 'test_strategist':
            strategist_calls += 1
            (request.artifact_dir / 'test-strategy.json').write_text(json.dumps({'acceptance_criteria': []}), encoding='utf-8')
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps(
                    {
                        'gaps': [
                            {
                                'id': 'GAP-FINAL',
                                'severity': 'Critical',
                                'type': 'missing_acceptance_criterion_mapping',
                                'message': 'AC-1 has no mapped behavioral test',
                            }
                        ]
                    }
                ),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    controller.reject_final_acceptance_gate()

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state.get('status') != 'blocked'
    assert state['testStrategistPlannerRetryCount'] == 0, 'Planner is no longer retried for test strategy gaps'
    assert strategist_calls == 2, 'initial strategist run + patcher run (both return gappy strategy)'
    gate_body = (state_dir / 'approvals' / 'unit-plan.md').read_text(encoding='utf-8')
    assert 'GAP-FINAL' in gate_body
    assert 'Unresolved Critical' in gate_body


def test_dry_run_until_done_advances_workflow_and_writes_artifacts(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir))
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc('run', '--state-dir', str(state_dir), '--dry-run', '--until-done')

    assert result.returncode == 0, result.stderr
    assert 'currentStep=DONE status=done' in result.stdout

    session = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert session['currentStep'] == 'DONE'
    assert session['status'] == 'done'

    unit_dir = state_dir / 'artifacts' / 'unit-01'
    assert (unit_dir / 'builder-summary.json').exists()
    assert (unit_dir / 'review.json').exists()
    assert (unit_dir / 'verification.json').exists()
    assert (state_dir / 'approvals' / 'scope-approval.json').exists()
    assert (state_dir / 'approvals' / 'release-approval.json').exists()


def test_non_dry_run_until_done_with_auto_approve_advances_to_done(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir), '--auto-approve')
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc('run', '--state-dir', str(state_dir), '--until-done', '--auto-approve')

    assert result.returncode == 0, result.stderr
    assert 'currentStep=DONE status=done' in result.stdout

    session = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert session['currentStep'] == 'DONE'
    assert session['status'] == 'done'
    assert (state_dir / 'approvals' / 'release-approval.json').exists()


def test_cli_rejects_abbreviated_long_options(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir))
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approv')

    assert result.returncode != 0
    assert 'unrecognized arguments: --auto-approv' in result.stderr


def test_drive_and_start_default_to_2000_max_steps(monkeypatch) -> None:
    monkeypatch.setattr(sys, 'argv', ['rrc_controller.py', 'drive'])
    drive_args = parse_args()

    monkeypatch.setattr(sys, 'argv', ['rrc_controller.py', 'start'])
    start_args = parse_args()

    monkeypatch.setattr(sys, 'argv', ['rrc_controller.py', 'run', '--until-done'])
    run_args = parse_args()
    monkeypatch.setattr(sys, 'argv', ['rrc_controller.py', 'approve', '--gate', 'bug-fix'])
    approve_args = parse_args()

    assert drive_args.max_steps == 2000
    assert start_args.max_steps == 2000
    assert run_args.max_steps == 2000
    assert approve_args.gate == 'bug-fix'


def test_go_infers_target_state_dir_workspace_and_tmux_runner(monkeypatch) -> None:
    for module, script_name in (
        (rrc_controller_module, 'rrc_controller.py'),
        (cli_module, 'cli.py'),
    ):
        monkeypatch.setattr(sys, 'argv', [script_name, 'go', 'V1.0', '--tmux-target', '1.2'])

        args = module.parse_args()

        assert args.command == 'go'
        assert args.target == 'V1.0'
        assert args.state_dir == '.rrc-controller-v1.0'
        assert args.workspace_dir is None
        assert args.runner is None
        assert args.tmux_target == '1.2'


def test_go_allows_explicit_subprocess_runner_without_tmux_target(monkeypatch) -> None:
    monkeypatch.setattr(sys, 'argv', ['rrc_controller.py', 'go', 'V1.0', '--runner', 'subprocess'])

    args = parse_args()

    assert args.target == 'V1.0'
    assert args.runner == 'subprocess'
    assert args.tmux_target is None


def test_go_infers_state_dir_inside_explicit_workspace(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / 'target-project'
    for module, script_name in (
        (rrc_controller_module, 'rrc_controller.py'),
        (cli_module, 'cli.py'),
    ):
        monkeypatch.setattr(
            sys,
            'argv',
            [
                script_name,
                'go',
                'V1.0',
                '--workspace-dir',
                str(workspace),
                '--tmux-target',
                '1.2',
            ],
        )

        args = module.parse_args()

        assert args.workspace_dir == str(workspace)
        assert args.state_dir == str(workspace / '.rrc-controller-v1.0')
        assert args.runner is None


def test_go_state_dir_slug_replaces_unsupported_target_characters(monkeypatch) -> None:
    monkeypatch.setattr(sys, 'argv', ['rrc_controller.py', 'go', 'Release Candidate/2!', '--runner', 'subprocess'])

    args = parse_args()

    assert args.state_dir == '.rrc-controller-release-candidate-2'


def test_go_rejects_conflicting_positional_and_flag_targets(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, 'argv', ['rrc_controller.py', 'go', 'V1.0', '--target', 'V2.0'])

    with pytest.raises(SystemExit) as exc_info:
        parse_args()

    assert exc_info.value.code == 2
    assert 'TARGET conflicts with --target' in capsys.readouterr().err


def test_go_without_target_or_state_dir_errors(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, 'argv', ['rrc_controller.py', 'go', '--tmux-target', '1.2'])

    with pytest.raises(SystemExit) as exc_info:
        parse_args()

    assert exc_info.value.code == 2
    assert 'go requires TARGET or --target when --state-dir is omitted' in capsys.readouterr().err


def test_rrc_go_dry_run_creates_and_resumes_inferred_state_dir(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()

    result = run_rrc_with_pythonpath('go', 'V1.0', '--runner', 'subprocess', '--dry-run', '--max-steps', '0', cwd=workspace)

    assert result.returncode == 0, result.stderr
    state_dir = workspace / '.rrc-controller-v1.0'
    assert (state_dir / 'session.json').exists()
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['requestedOutcome'] == 'V1.0'
    assert state['workspacePath'] == str(workspace)

    resume = run_rrc_with_pythonpath('go', 'V1.0', '--runner', 'subprocess', '--dry-run', '--max-steps', '0', cwd=workspace)

    assert resume.returncode == 0, resume.stderr
    assert '[继续] 使用已有状态' in resume.stdout


def test_rrc_go_inside_tmux_auto_creates_claude_pane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(tmp_path, split_pane_id='%88')
    _prepend_path(monkeypatch, tmp_path)
    monkeypatch.setenv('TMUX', '/tmp/tmux-session')

    result = run_rrc_with_pythonpath('go', 'V1.0', '--dry-run', '--max-steps', '0', cwd=workspace)

    assert result.returncode == 0, result.stderr
    state = json.loads((workspace / '.rrc-controller-v1.0' / 'session.json').read_text(encoding='utf-8'))
    assert state['agentRunner'] == 'tmux-claude'
    assert state['tmuxTarget'] == '%88'
    assert '[tmux] target=%88' in result.stdout
    assert 'runner=tmux-claude' in result.stdout
    assert 'submitKey=C-m' in result.stdout
    assert 'source=auto-created' in result.stdout
    assert 'command=claude --permission-mode bypassPermissions' in result.stdout
    tmux_calls = [
        json.loads(line)
        for line in (tmp_path / 'tmux.log').read_text(encoding='utf-8').splitlines()
    ]
    assert [
        'split-window',
        '-h',
        '-P',
        '-F',
        '#{pane_id}',
        '-c',
        str(workspace),
        'claude',
        '--permission-mode',
        'bypassPermissions',
    ] in tmux_calls


def test_rrc_go_with_tmux_target_detects_codex_pane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(
        tmp_path,
        pane_command='codex',
        pane_title='Codex CLI',
        pane_current_path=str(workspace),
    )
    _prepend_path(monkeypatch, tmp_path)
    monkeypatch.delenv('TMUX', raising=False)

    result = run_rrc_with_pythonpath(
        'go',
        'V1.0',
        '--tmux-target',
        '1.2',
        '--dry-run',
        '--max-steps',
        '0',
        cwd=workspace,
    )

    assert result.returncode == 0, result.stderr
    state = json.loads((workspace / '.rrc-controller-v1.0' / 'session.json').read_text(encoding='utf-8'))
    assert state['agentRunner'] == 'tmux-codex'
    assert state['tmuxTarget'] == '1.2'
    assert '[tmux] target=1.2' in result.stdout
    assert 'command=codex' in result.stdout
    assert 'title=Codex CLI' in result.stdout
    assert f'path={workspace}' in result.stdout
    assert 'detected=tmux-codex' in result.stdout
    assert 'runner=tmux-codex' in result.stdout
    assert 'submitKey=Enter' in result.stdout
    assert 'submitDelay=2.0s' in result.stdout


def test_rrc_go_with_tmux_codex_runner_auto_discovers_codex_pane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(
        tmp_path,
        pane_command='codex',
        pane_title='Codex CLI',
        pane_current_path=str(workspace),
        list_panes_output='%12',
    )
    _prepend_path(monkeypatch, tmp_path)
    monkeypatch.setenv('TMUX', '/tmp/tmux-session')

    result = run_rrc_with_pythonpath(
        'go',
        'V1.0',
        '--runner',
        'tmux-codex',
        '--dry-run',
        '--max-steps',
        '0',
        cwd=workspace,
    )

    assert result.returncode == 0, result.stderr
    state = json.loads((workspace / '.rrc-controller-v1.0' / 'session.json').read_text(encoding='utf-8'))
    assert state['agentRunner'] == 'tmux-codex'
    assert state['tmuxTarget'] == '%12'
    assert '[tmux] target=%12' in result.stdout
    assert 'runner=tmux-codex' in result.stdout
    assert 'detected=tmux-codex' in result.stdout
    assert 'source=auto-detected' in result.stdout


def test_rrc_go_with_tmux_target_detects_codex_from_process_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(
        tmp_path,
        pane_command='node',
        pane_title='CLIProxyAPI',
        pane_current_path=str(workspace),
        pane_pid='12345',
    )
    _make_fake_ps(
        tmp_path,
        '12345 1 12345 zsh -zsh\n'
        '12346 12345 12346 node node /home/user/.nvm/bin/codex\n'
        '12347 12346 12346 codex /home/user/.nvm/lib/node_modules/@openai/codex/vendor/codex',
    )
    _prepend_path(monkeypatch, tmp_path)
    monkeypatch.delenv('TMUX', raising=False)

    result = run_rrc_with_pythonpath(
        'go',
        'V1.0',
        '--tmux-target',
        '1.2',
        '--dry-run',
        '--max-steps',
        '0',
        cwd=workspace,
    )

    assert result.returncode == 0, result.stderr
    state = json.loads((workspace / '.rrc-controller-v1.0' / 'session.json').read_text(encoding='utf-8'))
    assert state['agentRunner'] == 'tmux-codex'
    assert state['tmuxTargetResolution']['detectedSource'] == 'process-tree'
    assert 'command=node' in result.stdout
    assert 'detected=tmux-codex' in result.stdout
    assert 'detectedSource=process-tree' in result.stdout


def test_rrc_go_with_tmux_target_ignores_waygate_runner_argument_in_process_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _make_fake_tmux(
        tmp_path,
        pane_command='python3',
        pane_title='Controller',
        pane_current_path=str(workspace),
        pane_pid='12345',
    )
    _make_fake_ps(
        tmp_path,
        '12345 1 12345 zsh -zsh\n'
        '12346 12345 12345 python3 python3 -m workflow_controller.cli go V1.0 --runner tmux-codex',
    )
    _prepend_path(monkeypatch, tmp_path)
    monkeypatch.delenv('TMUX', raising=False)

    result = run_rrc_with_pythonpath(
        'go',
        'V1.0',
        '--tmux-target',
        '1.2',
        '--runner',
        'tmux-claude',
        '--dry-run',
        '--max-steps',
        '0',
        cwd=workspace,
    )

    assert result.returncode == 0, result.stderr
    state = json.loads((workspace / '.rrc-controller-v1.0' / 'session.json').read_text(encoding='utf-8'))
    assert state['agentRunner'] == 'tmux-claude'
    assert state['tmuxTargetResolution']['detectedBackend'] is None


def test_rrc_go_with_tmux_target_uses_target_pane_directory_as_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller_cwd = tmp_path / 'controller-cwd'
    controller_cwd.mkdir()
    (controller_cwd / 'task_plan.md').write_text('workflow-controller V0.4.5a progress\n', encoding='utf-8')
    (controller_cwd / 'progress.md').write_text('wrong controller progress\n', encoding='utf-8')
    workspace = tmp_path / 'target-workspace'
    workspace.mkdir()
    (workspace / 'task_plan.md').write_text('CLIProxyAPI usage web target V1.1\n', encoding='utf-8')
    (workspace / 'progress.md').write_text('usage web implementation progress\n', encoding='utf-8')
    _make_fake_tmux(tmp_path, pane_command='codex', pane_current_path=str(workspace))
    _prepend_path(monkeypatch, tmp_path)
    monkeypatch.delenv('TMUX', raising=False)

    result = run_rrc_with_pythonpath(
        'go',
        'V1.1',
        '--tmux-target',
        '1.2',
        '--dry-run',
        '--max-steps',
        '0',
        cwd=controller_cwd,
    )

    assert result.returncode == 0, result.stderr
    state_dir = workspace / '.rrc-controller-v1.1'
    assert (state_dir / 'session.json').exists()
    assert not (controller_cwd / '.rrc-controller-v1.1' / 'session.json').exists()
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['workspacePath'] == str(workspace)
    assert state['executionWorkspacePath'] == str(workspace)
    assert state['agentRunner'] == 'tmux-codex'
    assert state['tmuxTarget'] == '1.2'


def test_rrc_go_with_tmux_target_rebases_before_continuing_stale_implicit_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller_cwd = tmp_path / 'controller-cwd'
    controller_cwd.mkdir()
    (controller_cwd / 'task_plan.md').write_text('workflow-controller V0.4.5a progress\n', encoding='utf-8')
    (controller_cwd / 'progress.md').write_text('wrong controller progress\n', encoding='utf-8')
    workspace = tmp_path / 'target-workspace'
    workspace.mkdir()
    (workspace / 'task_plan.md').write_text('CLIProxyAPI usage web target V1.1\n', encoding='utf-8')
    (workspace / 'progress.md').write_text('usage web implementation progress\n', encoding='utf-8')
    stale = run_rrc_with_pythonpath(
        'go',
        'V1.1',
        '--runner',
        'subprocess',
        '--dry-run',
        '--max-steps',
        '0',
        cwd=controller_cwd,
    )
    assert stale.returncode == 0, stale.stderr
    stale_state_dir = controller_cwd / '.rrc-controller-v1.1'
    assert (stale_state_dir / 'session.json').exists()

    _make_fake_tmux(tmp_path, pane_command='codex', pane_current_path=str(workspace))
    _prepend_path(monkeypatch, tmp_path)
    monkeypatch.delenv('TMUX', raising=False)

    result = run_rrc_with_pythonpath(
        'go',
        'V1.1',
        '--tmux-target',
        '1.2',
        '--dry-run',
        '--max-steps',
        '0',
        cwd=controller_cwd,
    )

    assert result.returncode == 0, result.stderr
    target_state_dir = workspace / '.rrc-controller-v1.1'
    assert (target_state_dir / 'session.json').exists()
    stale_state = json.loads((stale_state_dir / 'session.json').read_text(encoding='utf-8'))
    target_state = json.loads((target_state_dir / 'session.json').read_text(encoding='utf-8'))
    assert stale_state['workspacePath'] == str(controller_cwd)
    assert target_state['workspacePath'] == str(workspace)
    assert target_state['agentRunner'] == 'tmux-codex'
    assert str(workspace / 'task_plan.md') in target_state['targetContextFiles']
    assert str(controller_cwd / 'task_plan.md') not in target_state['targetContextFiles']
    assert f'使用已有状态：{stale_state_dir}' not in result.stdout
    prompt = Path(target_state['promptPath']).read_text(encoding='utf-8')
    assert 'CLIProxyAPI usage web target V1.1' in prompt
    assert 'workflow-controller V0.4.5a progress' not in prompt


def test_rrc_go_without_runner_or_tmux_target_outside_tmux_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    monkeypatch.delenv('TMUX', raising=False)

    result = run_rrc_with_pythonpath('go', 'V1.0', '--dry-run', '--max-steps', '0', cwd=workspace)

    assert result.returncode != 0
    assert '--tmux-target' in result.stderr
    assert 'tmux session' in result.stderr


def test_rrc_go_with_explicit_workspace_creates_state_dir_in_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / 'target-project'
    workspace.mkdir()
    cwd = tmp_path / 'controller-cwd'
    cwd.mkdir()

    result = run_rrc_with_pythonpath(
        'go',
        'V1.0',
        '--workspace-dir',
        str(workspace),
        '--runner',
        'subprocess',
        '--dry-run',
        '--max-steps',
        '0',
        cwd=cwd,
    )

    assert result.returncode == 0, result.stderr
    state_dir = workspace / '.rrc-controller-v1.0'
    assert (state_dir / 'session.json').exists()
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['workspacePath'] == str(workspace)


def test_rrc_go_uses_start_target_conflict_for_existing_state_dir(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = workspace / '.rrc-controller-v1.0'
    init_result = run_rrc_with_pythonpath('go', 'V1.0', '--runner', 'subprocess', '--dry-run', '--max-steps', '0', cwd=workspace)
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc_with_pythonpath(
        'go',
        'V2.0',
        '--state-dir',
        str(state_dir),
        '--runner',
        'subprocess',
        '--dry-run',
        '--max-steps',
        '0',
        cwd=workspace,
    )

    assert result.returncode != 0
    assert 'Existing session does not match start arguments' in result.stderr
    assert '--target=V2.0 but session requestedOutcome=V1.0' in result.stderr


def test_drive_stops_when_same_action_repeats_without_progress(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    initial_state = controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'PLAN_CREATED',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    calls = 0

    def unchanged_run_once() -> dict:
        nonlocal calls
        calls += 1
        return dict(initial_state)

    monkeypatch.setattr(controller, 'run_once', unchanged_run_once)
    output: list[str] = []

    controller.drive(
        max_steps=2000,
        max_no_progress_steps=3,
        output_func=output.append,
        timestamp_output=False,
    )

    assert calls == 3
    assert any('连续 3 次执行未推进' in line for line in output)
    assert not any('已达到最大自动步数：2000' in line for line in output)


def test_drive_compact_output_shows_unit_roadmap_and_attempt_summary(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'EXECUTE_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    output: list[str] = []

    controller.drive(output_func=output.append, timestamp_output=False)
    rendered = '\n'.join(output)

    assert '▶ usable-system' in rendered
    assert '单元   1/1  unit-01' in rendered
    assert '阶段 [构建*] [精修] [评审] [验证] [单元完成]' in rendered
    assert '第 1 轮' in rendered
    assert '构建' in rendered
    assert '精修 通过' in rendered
    assert '评审 通过' in rendered
    assert '验证 通过' in rendered
    assert '[进度]' not in rendered
    assert '[执行]' not in rendered


def test_compact_reporter_dedupes_identical_rendered_status_cards() -> None:
    output: list[str] = []
    reporter = rrc_controller_module._CompactDriveReporter(output.append, color_enabled=False)
    state = {
        'requestedOutcome': 'V1.3',
        'currentUnitId': 'v13-key-model-drilldown',
        'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
        'nextAction': 'check_unit_plan_approval',
        'status': 'active',
        'objectiveCoverage': [
            {
                'objective': 'V1.3 controlled delivery',
                'units': ['v13-key-model-drilldown'],
                'status': 'partial',
            },
        ],
        'units': [
            {'id': 'v13-key-model-drilldown', 'passes': False},
        ],
    }

    reporter.print_status(state, current_label='检查 Unit Plan 确认')
    changed_internal_state = dict(state)
    changed_internal_state['blockedReason'] = 'not rendered in the status card'
    reporter.print_status(changed_internal_state, current_label='检查 Unit Plan 确认')

    assert len(output) == 1
    assert output[0].count('当前   检查 Unit Plan 确认') == 1


def test_human_review_sends_tmux_reminder_without_submit(tmp_path: Path, monkeypatch) -> None:
    tmux_log = tmp_path / 'tmux-reminder.log'
    fake_tmux = tmp_path / 'tmux'
    fake_tmux.write_text(
        f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
with Path({str(tmux_log)!r}).open("a", encoding="utf-8") as log:
    log.write(json.dumps(args, ensure_ascii=False) + "\\n")
""",
        encoding='utf-8',
    )
    fake_tmux.chmod(0o755)
    _prepend_path(monkeypatch, tmp_path)

    cases = [
        (
            'requirements',
            {
                'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
                'requirementsAccepted': False,
                'unitPlanAccepted': False,
                'finalAcceptanceAccepted': False,
            },
        ),
        (
            'unit-plan',
            {
                'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
                'requirementsAccepted': True,
                'unitPlanAccepted': False,
                'finalAcceptanceAccepted': False,
            },
        ),
        (
            'final-acceptance',
            {
                'currentStep': 'WAITING_FINAL_ACCEPTANCE',
                'lastVerifiedStep': 'VERIFY_UNIT',
                'requirementsAccepted': True,
                'unitPlanAccepted': True,
                'finalAcceptanceAccepted': False,
                'objectiveCoverage': [
                    {'objective': 'Target V0.5.4 acceptance', 'units': ['unit-01'], 'status': 'covered'},
                ],
                'units': [
                    {'id': 'unit-01', 'name': 'Unit 1', 'passes': True},
                ],
            },
        ),
        (
            'bug-fix',
            {
                'currentStep': 'WAITING_BUG_FIX_GATE',
                'requirementsAccepted': True,
                'unitPlanAccepted': True,
                'finalAcceptanceAccepted': False,
                'activeBugFixId': 'bug-fix-1',
                'bugFixFeedback': 'Fix final acceptance defect.',
            },
        ),
    ]
    for gate, overrides in cases:
        state_dir = tmp_path / f'state-{gate}'
        controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
        base_state = {
            'task_id': f'target-{gate}',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'V0.5.4',
            'feasibleOutcome': 'V0.5.4',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'agentRunner': 'tmux-codex',
            'agentCommand': 'tmux',
            'tmuxTarget': '2.1',
            'objectiveCoverage': [
                {'objective': 'Target V0.5.4 acceptance', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Unit 1', 'passes': False},
            ],
        }
        base_state.update(overrides)
        controller.init_state(base_state, force=True)
        before = controller.store.load_state()

        state = controller.drive(
            max_steps=0,
            input_func=lambda _prompt: (_ for _ in ()).throw(EOFError),
            output_func=lambda _line: None,
            timestamp_output=False,
            print_agent_target=False,
        )

        assert state['currentStep'] == before['currentStep']
        assert state['nextAllowedActions'] == before['nextAllowedActions']
        assert not list(state_dir.rglob('done.json'))

    commands = [json.loads(line) for line in tmux_log.read_text(encoding='utf-8').splitlines()]
    set_buffer_commands = [command for command in commands if command[:1] == ['set-buffer']]
    paste_commands = [command for command in commands if command[:1] == ['paste-buffer']]
    send_key_commands = [command for command in commands if command[:1] == ['send-keys']]

    assert len(set_buffer_commands) == 4
    assert len(paste_commands) == 4
    assert send_key_commands == []
    for command in set_buffer_commands:
        reminder = command[-1]
        assert '\n' not in reminder
        assert 'Agent结论已形成，已进入人工评审阶段，请不要和Agent再继续沟通！' in reminder
        assert 'The agent has reached its conclusion and the workflow is now in human review. Please do not continue chatting with the agent.' in reminder
    assert all(command == ['paste-buffer', '-t', '2.1'] for command in paste_commands)


def test_compact_status_shows_target_version_separate_from_package_version(tmp_path: Path) -> None:
    state = {
        'requestedOutcome': 'V0.5.4',
        'feasibleOutcome': 'V0.5.4',
        'currentUnitId': 'v0-5-4-u1',
        'currentStep': 'EXECUTE_UNIT',
        'status': 'active',
        'scopeApproved': True,
        'objectiveCoverage': [
            {'objective': 'Complete V0.5.4 development acceptance', 'units': ['v0-5-4-u1'], 'status': 'partial'},
        ],
        'units': [
            {'id': 'v0-5-4-u1', 'name': 'V0.5.4 unit', 'passes': False},
        ],
    }
    output: list[str] = []
    reporter = rrc_controller_module._CompactDriveReporter(output.append, color_enabled=False)

    reporter.print_status(state)
    status_line = rrc_controller_module.render_status_line(state)
    cli_status_line = cli_module.render_status_line(state)
    version_result = subprocess.run(
        [sys.executable, '-m', 'workflow_controller.cli', '--version'],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )

    rendered = '\n'.join(output)
    assert 'V0.5.4' in rendered
    assert '项目目标版本/分支' in rendered
    assert 'projectTargetVersion=V0.5.4' in status_line
    assert 'projectTargetVersion=V0.5.4' in cli_status_line
    assert version_result.returncode == 0
    assert version_result.stdout.startswith('waygate ')
    assert 'projectTargetVersion' not in version_result.stdout


def test_agent_guides_include_version_planning_rules(tmp_path: Path) -> None:
    from workflow_controller.agent_guides import ensure_agent_operating_guides

    generated_workspace = tmp_path / 'generated-workspace'
    ensure_agent_operating_guides(generated_workspace)
    generated_agents = (generated_workspace / 'AGENTS.md').read_text(encoding='utf-8')
    root_agents = (ROOT / 'AGENTS.md').read_text(encoding='utf-8')

    for content in (root_agents, generated_agents):
        assert '讨论版本范围前，必须读取 `ROADMAP.md`、`task_plan.md` 和 Controller state-dir 中的 `session.json`' in content
        assert '不要根据最近进度推断版本范围' in content
        assert '讨论某个版本时，必须把当前版本需求和后续版本候选分开记录' in content


def test_complete_unit_keeps_multi_unit_objective_partial_until_all_units_pass(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'multi-unit-delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'UNIT_COMPLETE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {
                    'objective': 'Complete usable system',
                    'units': ['unit-01', 'unit-02', 'unit-03'],
                    'status': 'partial',
                },
            ],
            'units': [
                {'id': 'unit-01', 'name': 'First unit', 'passes': False},
                {'id': 'unit-02', 'name': 'Second unit', 'passes': False},
                {'id': 'unit-03', 'name': 'Third unit', 'passes': False},
            ],
        },
        force=True,
    )

    state = controller.run_once()

    assert state['objectiveCoverage'][0]['status'] == 'partial'
    assert state['units'][0]['passes'] is True
    assert state['currentUnitId'] == 'unit-02'
    assert state['currentStep'] == 'EXECUTE_UNIT'
    assert not (state_dir / 'approvals' / 'final-acceptance.md').exists()


def test_reconcile_reopens_early_final_acceptance_when_units_are_incomplete(tmp_path: Path) -> None:
    state = {
        'task_id': 'multi-unit-delivery',
        'currentUnitId': 'unit-01',
        'currentStep': 'WAITING_FINAL_ACCEPTANCE',
        'lastVerifiedStep': 'VERIFY_UNIT',
        'status': 'active',
        'requestedOutcome': 'usable-system',
        'feasibleOutcome': 'usable-system',
        'scopeApproved': True,
        'humanGatesRequired': True,
        'requirementsAccepted': True,
        'unitPlanAccepted': True,
        'finalAcceptanceAccepted': False,
        'objectiveCoverage': [
            {
                'objective': 'Complete usable system',
                'units': ['unit-01', 'unit-02', 'unit-03'],
                'status': 'covered',
            },
        ],
        'units': [
            {'id': 'unit-01', 'name': 'First unit', 'passes': True},
            {'id': 'unit-02', 'name': 'Second unit', 'passes': False},
            {'id': 'unit-03', 'name': 'Third unit', 'passes': False},
        ],
    }

    reconciled = reconcile_state(state, tmp_path / 'artifacts')

    assert validate_objective_coverage(reconciled) is False
    assert reconciled['objectiveCoverage'][0]['status'] == 'partial'
    assert reconciled['currentUnitId'] == 'unit-02'
    assert reconciled['currentStep'] == 'EXECUTE_UNIT'
    assert reconciled['finalAcceptanceAccepted'] is False


def test_drive_compact_output_shows_planning_roadmap_before_unit_execution(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'target-v2-2',
            'currentStep': 'REQUIREMENTS_DRAFT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'V2.2',
            'feasibleOutcome': 'V2.2',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'unitPlanAccepted': False,
            'objectiveCoverage': [
                {'objective': 'V2.2 target acceptance', 'units': ['target-v2-2'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'target-v2-2', 'name': 'V2.2 target', 'passes': False},
            ],
        },
        force=True,
    )
    output: list[str] = []

    controller.drive(max_steps=0, output_func=output.append, timestamp_output=False)
    rendered = '\n'.join(output)

    assert '当前   生成需求与验收草案' in rendered
    assert '阶段 [需求草案*] [需求确认] [Unit Plan] [Unit Plan确认] [构建]' in rendered
    assert '阶段 [构建] [精修] [评审] [验证] [单元完成]' not in rendered


def test_drive_compact_output_updates_for_unit_plan_generation_and_waiting(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'target-v5-2',
            'currentStep': 'UNIT_PLAN_DRAFT',
            'lastVerifiedStep': 'REQUIREMENTS_ACCEPTANCE',
            'status': 'active',
            'requestedOutcome': 'V5.2',
            'feasibleOutcome': 'V5.2',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': False,
            'objectiveCoverage': [
                {'objective': 'V5.2 target acceptance', 'units': ['target-v5-2'], 'status': 'partial'},
            ],
            'units': [
                {
                    'id': 'target-v5-2',
                    'name': 'V5.2 target',
                    'passes': False,
                    'test_cases': [
                        {
                            'id': 'TC-1',
                            'acceptance_criterion': 'AC-1',
                            'layer': 'unit',
                            'fixture': 'fixtures/unit.json',
                            'command': 'python -m pytest tests/unit -q',
                            'expected': 'unit plan is valid',
                        },
                    ],
                    'verification_commands': ['python -m pytest tests/unit -q'],
                },
            ],
        },
        force=True,
    )
    output: list[str] = []

    controller.drive(input_func=lambda _prompt: (_ for _ in ()).throw(EOFError), output_func=output.append, timestamp_output=False)
    rendered = '\n'.join(output)

    assert '当前   生成 Unit Plan 草案' in rendered
    assert '当前   等待 Unit Plan 确认' in rendered
    assert rendered.index('当前   生成 Unit Plan 草案') < rendered.index('当前   等待 Unit Plan 确认')
    assert '阶段 [需求草案] [需求确认] [Unit Plan*] [Unit Plan确认] [构建]' in rendered
    assert '阶段 [需求草案] [需求确认] [Unit Plan] [Unit Plan确认*] [构建]' in rendered


def test_compact_output_counts_units_for_requested_target_not_historical_units(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'v2-1-first',
            'currentStep': 'EXECUTE_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'V2.1',
            'feasibleOutcome': 'V2.1',
            'scopeApproved': True,
            'objectiveCoverage': [
                {'objective': 'V2.0 historical objective', 'units': ['old-1'], 'status': 'covered'},
                {'objective': 'V2.0 another historical objective', 'units': ['old-2'], 'status': 'covered'},
                {'objective': 'V2.1 first objective', 'units': ['v2-1-first'], 'status': 'partial'},
                {'objective': 'V2.1 second objective', 'units': ['v2-1-second'], 'status': 'partial'},
                {'objective': 'V2.1 third objective', 'units': ['v2-1-third'], 'status': 'partial'},
                {'objective': 'V2.1 fourth objective', 'units': ['v2-1-fourth'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'v2-1-first', 'passes': False},
                {'id': 'v2-1-second', 'passes': False},
                {'id': 'v2-1-third', 'passes': False},
                {'id': 'v2-1-fourth', 'passes': False},
                {'id': 'old-1', 'passes': True},
                {'id': 'old-2', 'passes': True},
            ],
        },
        force=True,
    )
    output: list[str] = []

    controller.drive(max_steps=0, output_func=output.append, timestamp_output=False)

    rendered = '\n'.join(output)
    assert '单元   1/4  v2-1-first' in rendered
    assert '单元   1/6  v2-1-first' not in rendered


def test_drive_prints_verification_state_change_markers(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'VERIFY_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'workspacePath': str(workspace),
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {
                    'id': 'unit-01',
                    'name': 'Delivery',
                    'passes': False,
                    'verification_commands': ["python -c \"print('verified')\""],
                },
            ],
        },
        force=True,
    )
    output: list[str] = []

    controller.drive(max_steps=1, output_func=output.append, timestamp_output=False)

    rendered = '\n'.join(output)
    assert '[验证] 开始 1 个命令' in rendered
    assert '[验证] ... 1/1 python -c' in rendered
    assert '[验证] 通过 1/1 exit=0' in rendered
    assert '[验证] 完成 通过' in rendered


def test_drive_prints_compact_verification_failure_reason(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'VERIFY_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'workspacePath': str(workspace),
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {
                    'id': 'unit-01',
                    'name': 'Delivery',
                    'passes': False,
                    'verification_commands': [
                        "DATABASE_URL=file:test.db python -c \"import sys; print('error: Environment variable not found: DATABASE_URL'); sys.exit(1)\"",
                    ],
                },
            ],
        },
        force=True,
    )
    output: list[str] = []

    controller.drive(max_steps=1, output_func=output.append, timestamp_output=False)

    rendered = '\n'.join(output)
    assert '原因 验证未通过' in rendered
    assert 'DATABASE_URL' in rendered
    assert 'exit 1' in rendered


def test_drive_compact_output_groups_failed_attempt_and_retry(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    states = [
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'EXECUTE_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        {
            'currentStep': 'REFINE_UNIT',
        },
        {
            'currentStep': 'REVIEW_UNIT',
        },
        {
            'currentStep': 'VERIFY_UNIT',
        },
        {
            'currentStep': 'EXECUTE_UNIT',
        },
    ]
    base = states[0]
    controller.init_state(base, force=True)
    transitions = iter(states[1:])

    def advance_once() -> dict:
        next_state = dict(base)
        next_state.update(next(transitions))
        return next_state

    monkeypatch.setattr(controller, 'run_once', advance_once)
    output: list[str] = []

    controller.drive(max_steps=4, output_func=output.append, timestamp_output=False)
    rendered = '\n'.join(output)

    assert '第 1 轮' in rendered
    assert '验证 未通过' in rendered
    assert '重试第 2 轮' in rendered
    assert '原因 验证未通过' in rendered


def test_repeated_verification_failure_blocks_before_another_retry(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'VERIFY_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'workspacePath': str(workspace),
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {
                    'id': 'unit-01',
                    'name': 'Delivery',
                    'passes': False,
                    'verification_commands': [
                        'python -c "import sys; print(\'runtime database missing\'); sys.exit(1)"',
                    ],
                },
            ],
        },
        force=True,
    )

    first = controller.run_once()

    assert first['status'] == 'active'
    assert first['currentStep'] == 'EXECUTE_UNIT'
    assert first['lastFailure']['stage'] == 'VERIFY_UNIT'
    assert first['lastFailure']['count'] == 1

    first['currentStep'] = 'VERIFY_UNIT'
    controller.store.save_state(first)

    second = controller.run_once()

    assert second['status'] == 'blocked'
    assert second['currentStep'] == 'VERIFY_UNIT'
    assert second['lastFailure']['count'] == 2
    assert 'Repeated VERIFY_UNIT failure' in second['blockedReason']
    assert 'runtime database missing' in second['blockedReason']


def test_run_verifier_rejects_malformed_evidence_schema_before_unit_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'VERIFY_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {
                    'id': 'unit-01',
                    'name': 'Delivery',
                    'passes': False,
                    'verification_commands': ['pytest tests/test_delivery.py -q'],
                },
            ],
        },
        force=True,
    )

    def fake_run_verifier(state: dict[str, Any], unit_dir: Path, **_: Any) -> None:
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / 'verification.json').write_text(
            json.dumps({
                'unit_id': 'unit-01',
                'passed': True,
                'commands': ['pytest tests/test_delivery.py -q'],
                'evidence_files': ['green-test.txt'],
                'verified_at': '2026-05-04T00:00:00+00:00',
            }),
            encoding='utf-8',
        )

    monkeypatch.setattr(rrc_controller_module, 'run_verifier', fake_run_verifier)

    state = controller.run_once()

    assert state['currentStep'] == 'EXECUTE_UNIT'
    assert state['lastFailure']['stage'] == 'VERIFY_UNIT'
    assert state['lastFailure']['details']['issues'][0]['type'] == 'invalid_evidence_schema'
    assert 'evidence_schema_version' in state['lastFailure']['details']['issues'][0]['message']


def _write_simplifier_result(unit_dir: Path, status: str, findings: list[dict[str, str]] | None = None) -> None:
    unit_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        'unit_id': 'unit-01',
        'status': status,
        'mode': 'role-runner',
        'changed_files': ['src/login.py'],
        'findings': findings or [],
        'runner_metadata': {},
        'exit_code': 0,
        'stdout': '',
        'stderr': '',
        'generated_at': '2026-05-03T00:00:00+00:00',
    }
    (unit_dir / 'simplifier-result.json').write_text(json.dumps(payload), encoding='utf-8')
    (unit_dir / 'refinement-summary.json').write_text(json.dumps(payload), encoding='utf-8')


def _refiner_controller_state(workspace: Path) -> dict[str, Any]:
    return {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'currentStep': 'REFINE_UNIT',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'usable-system',
        'feasibleOutcome': 'usable-system',
        'workspacePath': str(workspace),
        'objectiveCoverage': [
            {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {
                'id': 'unit-01',
                'name': 'Delivery',
                'passes': False,
            },
        ],
    }


def test_controller_routes_ok_simplifier_result_to_reviewer(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_refiner_controller_state(workspace), force=True)

    def fake_run_refiner(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> None:
        _write_simplifier_result(unit_dir, 'ok')

    monkeypatch.setattr('workflow_controller.rrc_controller.run_refiner', fake_run_refiner)

    state = controller.run_once()

    assert state['currentStep'] == 'REVIEW_UNIT'
    assert state['status'] == 'active'


def test_controller_routes_changes_requested_simplifier_result_back_to_builder(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_refiner_controller_state(workspace), force=True)

    def fake_run_refiner(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> None:
        _write_simplifier_result(
            unit_dir,
            'changes_requested',
            [{'type': 'over_nested_branch', 'message': 'Flatten the new login branch before review.'}],
        )

    monkeypatch.setattr('workflow_controller.rrc_controller.run_refiner', fake_run_refiner)

    state = controller.run_once()

    assert state['currentStep'] == 'EXECUTE_UNIT'
    assert state['status'] == 'active'
    assert state['lastFailure']['stage'] == 'REFINE_UNIT'
    assert state['lastFailure']['details']['issues'][0]['type'] == 'over_nested_branch'


def test_controller_failed_simplifier_result_does_not_reach_reviewer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    initial_state = _refiner_controller_state(workspace)
    initial_state['sameFailureMaxRetries'] = 0
    controller.init_state(initial_state, force=True)

    def fake_run_refiner(state: dict[str, Any], unit_dir: Path, dry_run: bool = False) -> None:
        _write_simplifier_result(
            unit_dir,
            'failed',
            [{'type': 'missing_simplifier_result', 'message': 'CodeSimplifier output was malformed.'}],
        )

    monkeypatch.setattr('workflow_controller.rrc_controller.run_refiner', fake_run_refiner)

    state = controller.run_once()

    assert state['currentStep'] == 'REFINE_UNIT'
    assert state['status'] == 'blocked'
    assert 'Repeated REFINE_UNIT failure' in state['blockedReason']


def test_verifier_blocks_when_required_database_url_cannot_be_inferred(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'VERIFY_UNIT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'workspacePath': str(workspace),
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {
                    'id': 'unit-01',
                    'name': 'Delivery',
                    'passes': False,
                    'verification_commands': [
                        'pnpm exec playwright test e2e/tests/delivery.spec.ts --workers=1',
                    ],
                },
            ],
        },
        force=True,
    )

    state = controller.run_once()

    assert state['status'] == 'blocked'
    assert state['currentStep'] == 'VERIFY_UNIT'
    assert 'verification environment is incomplete' in state['blockedReason']
    assert 'DATABASE_URL' in state['blockedReason']
    assert state['nextAllowedActions'] == []


def test_drive_verbose_output_keeps_raw_progress_lines(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir), '--auto-approve')
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--dry-run',
        '--auto-approve',
        '--verbose',
    )

    assert result.returncode == 0, result.stderr
    assert '[进度] 目标：usable-system | 单元：unit-01 | 阶段：PLAN_CREATED | 下一步：范围确认' in result.stdout
    assert '[执行] 范围确认...' in result.stdout
    assert '[完成] 工作流已完成。' in result.stdout


def test_drive_color_auto_keeps_captured_output_plain(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir), '--auto-approve')
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--dry-run',
        '--auto-approve',
    )

    assert result.returncode == 0, result.stderr
    assert '\x1b[' not in result.stdout


def test_drive_color_always_adds_ansi_to_compact_output(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir), '--auto-approve')
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--dry-run',
        '--auto-approve',
        '--color',
        'always',
    )

    assert result.returncode == 0, result.stderr
    assert '\x1b[' in result.stdout
    plain = re.sub(r'\x1b\[[0-9;]*m', '', result.stdout)
    assert '▶ usable-system' in plain
    assert '验证 通过' in plain


def test_target_acceptance_completion_does_not_continue_unrelated_plan_units(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'target-acceptance',
            'currentUnitId': 'target-1-1',
            'currentStep': 'UNIT_COMPLETE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': '1.1',
            'targetMatchedPlanStep': False,
            'scopeApproved': True,
            'autoApprove': True,
            'objectiveCoverage': [
                {'objective': 'Future unrelated plan unit', 'units': ['future-unit'], 'status': 'partial'},
                {'objective': 'Target 1.1 acceptance', 'units': ['target-1-1'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'future-unit', 'passes': False},
                {'id': 'target-1-1', 'passes': False},
            ],
        },
        force=True,
    )

    state = controller.run_once()

    assert state['currentUnitId'] == 'target-1-1'
    assert state['currentStep'] == 'RELEASE_GATE'
    assert state['nextAllowedActions'] == ['require_release_approval']


def test_ui_design_step_writes_artifact_when_required(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'ui-work',
            'currentUnitId': 'unit-ui',
            'currentStep': 'PLAN_APPROVED',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'autoApprove': True,
            'currentUnitNeedsUiDesign': True,
            'objectiveCoverage': [
                {'objective': 'UI path is usable', 'units': ['unit-ui'], 'status': 'partial'},
            ],
            'units': [
                {
                    'id': 'unit-ui',
                    'name': 'UI delivery',
                    'scope': ['Build the browser-facing workflow'],
                    'ui_design_required': True,
                    'verification_commands': ['pytest tests/test_ui.py -q'],
                },
            ],
        },
        force=True,
    )

    state = controller.run_once()

    assert state['currentStep'] == 'UI_DESIGN_DONE'
    summary = json.loads((state_dir / 'artifacts' / 'unit-ui' / 'ui-design-summary.json').read_text(encoding='utf-8'))
    assert summary['status'] == 'ok'
    assert summary['unit_id'] == 'unit-ui'
    assert summary['mode'] == 'local-ui-design-brief'
    assert 'Build the browser-facing workflow' in summary['scope']


def test_migrate_command_adds_controller_state_patch_to_legacy_unit_plan_gate(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'legacy',
            'currentUnitId': 'unit-legacy',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Legacy objective', 'units': ['unit-legacy'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-legacy', 'name': 'Legacy unit', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Unit Plan Confirmation\n\n## Units\n- Legacy readable plan.\n\n'
        '## Human Confirmation\n\nStatus: pending\nConfirmed by: \nConfirmed at: \nContent hash: sha256:legacy\n',
        encoding='utf-8',
    )

    result = run_rrc('migrate', '--state-dir', str(state_dir))

    assert result.returncode == 0, result.stderr
    assert 'status=migrated' in result.stdout
    content = gate_path.read_text(encoding='utf-8')
    assert '## Controller State Patch' in content
    assert '"currentUnitId": "unit-legacy"' in content
    assert 'Status: pending' in content
    assert (state_dir / 'approvals' / 'unit-plan.md.before-controller-state-patch').exists()


def test_drive_outputs_compact_progress_and_runs_until_done_without_human_gate(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir), '--auto-approve')
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--dry-run',
        '--auto-approve',
    )

    assert result.returncode == 0, result.stderr
    assert '▶ usable-system' in result.stdout
    assert '单元   1/1  unit-01' in result.stdout
    assert '阶段 [构建] [精修] [评审] [验证] [单元完成]' in result.stdout
    assert '第 1 轮' in result.stdout
    assert '[进度]' not in result.stdout
    assert '[执行]' not in result.stdout
    assert '[完成] 工作流已完成。' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'DONE'
    assert state['status'] == 'done'


def test_drive_prefixes_each_output_line_with_seconds_timestamp(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    init_result = run_rrc('init', '--state-dir', str(state_dir), '--auto-approve')
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--dry-run',
        '--auto-approve',
    )

    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines
    assert all(re.match(r'^\[\d{2}:\d{2}:\d{2}\] ', line) for line in lines)


def test_drive_stops_for_pending_unit_plan_gate_with_chinese_prompt(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Unit Plan Confirmation\n\n## Human Confirmation\n\nStatus: pending\nConfirmed by: \nConfirmed at: \nContent hash: sha256:legacy\n',
        encoding='utf-8',
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        input_text='q\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[人工确认] Unit Plan' in result.stdout
    assert str(gate_path) in result.stdout
    assert '状态：unit plan gate invalid' in result.stdout
    assert 'Controller State Patch' in result.stdout
    assert '    v  使用 Plannotator 辅助审阅' in result.stdout
    assert '    a  确认通过并继续' in result.stdout
    assert '[退出] 已停止在人工确认点。' in result.stdout


def test_drive_can_open_plannotator_review_without_approving_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Unit Plan Confirmation\n\n## Human Confirmation\n\nStatus: pending\nConfirmed by: \nConfirmed at: \nContent hash: sha256:legacy\n',
        encoding='utf-8',
    )
    plannotator_log = tmp_path / 'plannotator-args.json'
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

Path(os.environ['PLANNOTATOR_LOG']).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')
print('Open this link on your local machine to annotate:')
print('https://share.plannotator.ai/#fake')
print('{"decision":"dismissed"}')
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)
    monkeypatch.setenv('PLANNOTATOR_LOG', str(plannotator_log))

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--plannotator-command',
        str(fake_plannotator),
        input_text='v\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[Plannotator] 已打开辅助审阅。' in result.stdout
    assert 'http://localhost:20000' in result.stdout
    assert 'Open this link on your local machine to annotate:' not in result.stdout
    assert 'https://share.plannotator.ai/#fake' not in result.stdout
    assert '请在 Plannotator 浏览器里选择 Approve 或 Close。Approve 会自动继续。' in result.stdout
    assert '[Plannotator] 已关闭，未批准；仍停在人工确认点。' in result.stdout
    assert json.loads(plannotator_log.read_text(encoding='utf-8')) == [
        'annotate',
        str(gate_path),
        '--gate',
        '--json',
    ]
    summary_path = state_dir / 'plannotator' / 'unit-plan-last-review.json'
    assert summary_path.exists()
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['unitPlanAccepted'] is False
    events = [
        json.loads(line)
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    assert any(event['type'] == 'plannotator_review_requested' for event in events)


def test_drive_plannotator_reviews_requirements_approval_markdown_when_body_artifact_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
            'lastVerifiedStep': 'REQUIREMENTS_DRAFT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    approval_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    approval_path.write_text(
        '# Requirements & Acceptance Confirmation\n\nClaude body\n\n## Human Confirmation\n\nStatus: pending\n',
        encoding='utf-8',
    )
    body_path = state_dir / 'artifacts' / 'requirements-draft' / 'requirements-body.md'
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_text('# Requirements & Acceptance Confirmation\n\nClaude body\n', encoding='utf-8')
    plannotator_log = tmp_path / 'plannotator-args.json'
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

Path(os.environ['PLANNOTATOR_LOG']).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')
print('Open this link on your local machine to annotate:')
print('https://share.plannotator.ai/#requirements-body')
print('{"decision":"dismissed"}')
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)
    monkeypatch.setenv('PLANNOTATOR_LOG', str(plannotator_log))

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--plannotator-command',
        str(fake_plannotator),
        input_text='v\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert f'审阅文件：{body_path}' not in result.stdout
    assert f'确认文件：{approval_path}' not in result.stdout
    assert json.loads(plannotator_log.read_text(encoding='utf-8')) == [
        'annotate',
        str(approval_path),
        '--gate',
        '--json',
    ]
    summary = json.loads((state_dir / 'plannotator' / 'requirements-last-review.json').read_text(encoding='utf-8'))
    assert summary['gate_path'] == str(approval_path)
    assert summary['review_path'] == str(approval_path)
    assert summary['approval_gate_path'] == str(approval_path)


def test_drive_auto_approves_gate_when_plannotator_approves(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        '# Requirements & Acceptance Confirmation\n\n## 4. Test Strategy\n- Unit tests cover delivery.\n',
    )
    approve_gate_file(requirements_path, actor='tester')

    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Units
### unit-01 - Delivery
- Verification commands:
  - `pytest tests/test_delivery.py -q`

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery",
      "passes": false,
      "verification_commands": ["pytest tests/test_delivery.py -q"]
    }
  ]
}
```
""",
    )
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
print('Open this link on your local machine to annotate:')
print('https://share.plannotator.ai/#approved')
print('{"decision":"approved"}')
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '1',
        '--actor',
        'tester',
        '--plannotator-command',
        str(fake_plannotator),
        input_text='v\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[Plannotator] 已收到 Approve，等同于人工确认通过。' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['unitPlanAccepted'] is True
    assert state['currentStep'] == 'PLAN_CREATED'


def test_drive_auto_revises_requirements_when_plannotator_approve_fails_controller_validation(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
            'lastVerifiedStep': 'REQUIREMENTS_DRAFT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import write_gate_file

    gate_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        gate_path,
        """# 需求与验收确认

## 3. 验收标准
- AC-1: User completes the delivery journey.
""",
    )
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
print('Open this link on your local machine to annotate:')
print('https://share.plannotator.ai/#approved-invalid')
print('{"decision":"approved"}')
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '1',
        '--actor',
        'tester',
        '--plannotator-command',
        str(fake_plannotator),
        input_text='v\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[确认] 需求与验收 无法确认：requirements gate invalid' in result.stdout
    assert '[修订] Controller 校验未通过，已自动打回需求草案生成。' in result.stdout
    assert '[修订] 已根据 Controller 校验错误重新生成 需求与验收。' in result.stdout

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['requirementsAccepted'] is False
    assert state['requirementsRevisionCount'] == 1
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    revision = json.loads(
        (state_dir / 'artifacts' / 'requirements-revisions' / 'revision-1.json').read_text(encoding='utf-8')
    )
    assert revision['controller_validation_error'].startswith('requirements gate invalid:')
    assert '## Controller Validation Error' in revision['feedback']


def test_requirements_draft_uses_two_hour_timeout_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import workflow_controller.steps.requirements as requirements_step
    from workflow_controller.runners import RunnerConfig
    from workflow_controller.runners.base import RunnerResult

    state_dir = tmp_path / 'state'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'REQUIREMENTS_DRAFT',
            'lastVerifiedStep': 'TARGET_ACCEPTANCE',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'workspacePath': str(workspace),
            'agentRunner': 'tmux-claude',
            'agentCommand': 'claude',
            'tmuxTarget': '1.2',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    captured_timeout_seconds: list[int] = []

    def fake_make_runner(state: dict) -> RunnerConfig:
        return RunnerConfig(backend='tmux-claude', agent_command='fake-claude', tmux_target='1.2')

    def fake_run_agent_backend(request):
        captured_timeout_seconds.append(request.timeout_seconds)
        body_path = state_dir / 'artifacts' / 'requirements-draft' / 'requirements-body.md'
        body_path.write_text(
            """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: unit]: User can continue after clarification.

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| 无 active must AO | AC-1 | covered | unit | pytest |
""",
            encoding='utf-8',
        )
        return RunnerResult(
            backend='tmux-claude',
            status='done',
            command=['fake-claude'],
            returncode=0,
            stdout='ok',
            stderr='',
            run_dir=state_dir / 'artifacts' / 'requirements-draft' / 'runs' / 'requirements-draft-run',
            prompt_path=request.prompt_path,
            done_payload={'status': 'done'},
            runner_metadata={'fake': True},
        )

    monkeypatch.setattr(requirements_step, 'make_runner', fake_make_runner)
    monkeypatch.setattr(requirements_step, 'run_agent_backend', fake_run_agent_backend)

    controller.run_once()

    assert captured_timeout_seconds == [7200]


def test_requirements_draft_timeout_resumes_existing_pending_run_without_redispatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import workflow_controller.steps.requirements as requirements_step
    from workflow_controller.runners import RunnerConfig
    from workflow_controller.runners.base import RunnerResult

    state_dir = tmp_path / 'state'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'REQUIREMENTS_DRAFT',
            'lastVerifiedStep': 'TARGET_ACCEPTANCE',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'workspacePath': str(workspace),
            'agentRunner': 'tmux-claude',
            'agentCommand': 'claude',
            'tmuxTarget': '1.2',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    run_dir = state_dir / 'artifacts' / 'requirements-draft' / 'runs' / 'requirements-draft-run'
    done_path = run_dir / 'done.json'
    dispatch_count = 0

    def fake_make_runner(state: dict) -> RunnerConfig:
        return RunnerConfig(backend='tmux-claude', agent_command='fake-claude', tmux_target='1.2')

    def fake_run_agent_backend(request):
        nonlocal dispatch_count
        dispatch_count += 1
        run_dir.mkdir(parents=True, exist_ok=True)
        done_path.write_text(
            json.dumps({
                'status': 'pending',
                'summary': 'waiting for requirements clarification',
                'run_id': run_dir.name,
            }),
            encoding='utf-8',
        )
        return RunnerResult(
            backend='tmux-claude',
            status='timeout',
            command=['fake-claude'],
            returncode=124,
            stdout='',
            stderr='',
            run_dir=run_dir,
            prompt_path=request.prompt_path,
            done_path=done_path,
            done_payload={'status': 'pending', 'run_id': run_dir.name},
            runner_metadata={'fake': True},
        )

    monkeypatch.setattr(requirements_step, 'make_runner', fake_make_runner)
    monkeypatch.setattr(requirements_step, 'run_agent_backend', fake_run_agent_backend)

    with pytest.raises(RuntimeError) as exc_info:
        controller.run_once()

    assert '等了太久，先休息一下，等agent好了，再接着干' in str(exc_info.value)
    assert dispatch_count == 1

    body_path = state_dir / 'artifacts' / 'requirements-draft' / 'requirements-body.md'
    body_path.write_text(
        """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: unit]: User can resume requirements drafting.

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| 无 active must AO | AC-1 | covered | unit | pytest |
""",
        encoding='utf-8',
    )
    done_path.write_text(
        json.dumps({
            'status': 'done',
            'summary': 'requirements generated after clarification',
            'run_id': run_dir.name,
        }),
        encoding='utf-8',
    )
    summary_path = state_dir / 'artifacts' / 'requirements-draft' / 'requirements-draft-summary.json'
    newer_than_timeout = summary_path.stat().st_mtime + 10
    os.utime(body_path, (newer_than_timeout, newer_than_timeout))
    os.utime(done_path, (newer_than_timeout, newer_than_timeout))

    state = controller.run_once()

    assert dispatch_count == 1
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert state['requirementsDraftGenerated'] is True
    gate_content = (state_dir / 'approvals' / 'requirements-and-acceptance.md').read_text(encoding='utf-8')
    assert 'User can resume requirements drafting.' in gate_content
    summary = json.loads(
        (state_dir / 'artifacts' / 'requirements-draft' / 'requirements-draft-summary.json').read_text(encoding='utf-8')
    )
    assert summary['status'] == 'done'
    assert summary['resumed_from_pending_run'] is True


def test_requirements_draft_recovers_legacy_timed_out_summary_when_done_run_and_body_exist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import workflow_controller.steps.requirements as requirements_step
    from workflow_controller.runners import RunnerConfig

    state_dir = tmp_path / 'state'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'REQUIREMENTS_DRAFT',
            'lastVerifiedStep': 'TARGET_ACCEPTANCE',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'workspacePath': str(workspace),
            'agentRunner': 'tmux-claude',
            'agentCommand': 'claude',
            'tmuxTarget': '1.2',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    draft_dir = state_dir / 'artifacts' / 'requirements-draft'
    draft_dir.mkdir(parents=True, exist_ok=True)
    body_path = draft_dir / 'requirements-body.md'
    legacy_run_dir = draft_dir / 'runs' / 'requirements-draft-legacy'
    legacy_run_dir.mkdir(parents=True)
    summary_path = draft_dir / 'requirements-draft-summary.json'
    summary_path.write_text(
        json.dumps({
            'status': 'timeout',
            'mode': 'tmux-claude',
            'runner_run_dir': str(legacy_run_dir),
            'exit_code': 124,
            'body_path': str(body_path),
        }),
        encoding='utf-8',
    )
    body_path.write_text(
        """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: unit]: Legacy completed run is reviewed without redispatch.

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| 无 active must AO | AC-1 | covered | unit | pytest |
""",
        encoding='utf-8',
    )
    done_path = legacy_run_dir / 'done.json'
    done_path.write_text(
        json.dumps({
            'status': 'done',
            'summary': 'requirements generated before controller resumed',
            'run_id': legacy_run_dir.name,
        }),
        encoding='utf-8',
    )
    newer_than_timeout = summary_path.stat().st_mtime + 10
    os.utime(body_path, (newer_than_timeout, newer_than_timeout))
    os.utime(done_path, (newer_than_timeout, newer_than_timeout))
    dispatch_count = 0

    def fake_make_runner(state: dict) -> RunnerConfig:
        return RunnerConfig(backend='tmux-claude', agent_command='fake-claude', tmux_target='1.2')

    def fake_run_agent_backend(request):
        nonlocal dispatch_count
        dispatch_count += 1
        raise AssertionError('requirements drafter should recover the completed legacy run')

    monkeypatch.setattr(requirements_step, 'make_runner', fake_make_runner)
    monkeypatch.setattr(requirements_step, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert dispatch_count == 0
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert state['requirementsDraftGenerated'] is True
    gate_content = (state_dir / 'approvals' / 'requirements-and-acceptance.md').read_text(encoding='utf-8')
    assert 'Legacy completed run is reviewed without redispatch.' in gate_content
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    assert summary['status'] == 'done'
    assert summary['resumed_from_pending_run'] is True
    assert summary['done_path'] == str(done_path.resolve())


def test_requirements_draft_does_not_recover_done_and_body_older_than_timeout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import workflow_controller.steps.requirements as requirements_step
    from workflow_controller.runners import RunnerConfig

    state_dir = tmp_path / 'state'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'REQUIREMENTS_DRAFT',
            'lastVerifiedStep': 'TARGET_ACCEPTANCE',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'workspacePath': str(workspace),
            'agentRunner': 'tmux-claude',
            'agentCommand': 'claude',
            'tmuxTarget': '1.2',
            'requirementsDraftTimeoutSeconds': 0,
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    draft_dir = state_dir / 'artifacts' / 'requirements-draft'
    draft_dir.mkdir(parents=True, exist_ok=True)
    body_path = draft_dir / 'requirements-body.md'
    body_path.write_text(
        """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: unit]: Stale requirements body must not be reviewed.

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| 无 active must AO | AC-1 | covered | unit | pytest |
""",
        encoding='utf-8',
    )
    stale_run_dir = draft_dir / 'runs' / 'requirements-draft-stale'
    stale_run_dir.mkdir(parents=True)
    done_path = stale_run_dir / 'done.json'
    done_path.write_text(
        json.dumps({
            'status': 'done',
            'summary': 'stale requirements body',
            'run_id': stale_run_dir.name,
        }),
        encoding='utf-8',
    )
    stale_time = body_path.stat().st_mtime
    summary_path = draft_dir / 'requirements-draft-summary.json'
    summary_path.write_text(
        json.dumps({
            'status': 'timeout',
            'mode': 'tmux-claude',
            'runner_run_dir': str(stale_run_dir),
            'exit_code': 124,
            'body_path': str(body_path),
        }),
        encoding='utf-8',
    )
    timeout_time = stale_time + 10
    os.utime(summary_path, (timeout_time, timeout_time))
    os.utime(body_path, (stale_time, stale_time))
    os.utime(done_path, (stale_time, stale_time))
    dispatch_count = 0

    def fake_make_runner(state: dict) -> RunnerConfig:
        return RunnerConfig(backend='tmux-claude', agent_command='fake-claude', tmux_target='1.2')

    def fake_run_agent_backend(request):
        nonlocal dispatch_count
        dispatch_count += 1
        raise AssertionError('requirements drafter should not redispatch while waiting for fresh done and body')

    monkeypatch.setattr(requirements_step, 'make_runner', fake_make_runner)
    monkeypatch.setattr(requirements_step, 'run_agent_backend', fake_run_agent_backend)

    with pytest.raises(RuntimeError) as exc_info:
        controller.run_once()

    assert '等了太久，先休息一下，等agent好了，再接着干' in str(exc_info.value)
    assert dispatch_count == 0


def test_requirements_draft_waits_on_existing_timeout_run_until_fresh_body_arrives(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import workflow_controller.steps.requirements as requirements_step
    from workflow_controller.runners import RunnerConfig

    state_dir = tmp_path / 'state'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'REQUIREMENTS_DRAFT',
            'lastVerifiedStep': 'TARGET_ACCEPTANCE',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'workspacePath': str(workspace),
            'agentRunner': 'tmux-claude',
            'agentCommand': 'claude',
            'tmuxTarget': '1.2',
            'requirementsDraftTimeoutSeconds': 5,
            'requirementsDraftResumePollSeconds': 0,
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    draft_dir = state_dir / 'artifacts' / 'requirements-draft'
    draft_dir.mkdir(parents=True, exist_ok=True)
    body_path = draft_dir / 'requirements-body.md'
    run_dir = draft_dir / 'runs' / 'requirements-draft-waiting'
    run_dir.mkdir(parents=True)
    done_path = run_dir / 'done.json'
    done_path.write_text(
        json.dumps({
            'status': 'pending',
            'summary': 'waiting for requirements body',
            'run_id': run_dir.name,
        }),
        encoding='utf-8',
    )
    summary_path = draft_dir / 'requirements-draft-summary.json'
    summary_path.write_text(
        json.dumps({
            'status': 'timeout',
            'mode': 'tmux-claude',
            'runner_run_dir': str(run_dir),
            'done_path': str(done_path),
            'exit_code': 124,
            'body_path': str(body_path),
        }),
        encoding='utf-8',
    )
    fresh_time = summary_path.stat().st_mtime + 10
    dispatch_count = 0
    sleep_count = 0

    def fake_make_runner(state: dict) -> RunnerConfig:
        return RunnerConfig(backend='tmux-claude', agent_command='fake-claude', tmux_target='1.2')

    def fake_run_agent_backend(request):
        nonlocal dispatch_count
        dispatch_count += 1
        raise AssertionError('requirements drafter should wait on existing run instead of redispatching')

    def fake_sleep(_seconds: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        body_path.write_text(
            """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: unit]: Existing run can finish while controller waits.

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| 无 active must AO | AC-1 | covered | unit | pytest |
""",
            encoding='utf-8',
        )
        done_path.write_text(
            json.dumps({
                'status': 'done',
                'summary': 'requirements body arrived',
                'run_id': run_dir.name,
            }),
            encoding='utf-8',
        )
        os.utime(body_path, (fresh_time, fresh_time))
        os.utime(done_path, (fresh_time, fresh_time))

    monkeypatch.setattr(requirements_step, 'make_runner', fake_make_runner)
    monkeypatch.setattr(requirements_step, 'run_agent_backend', fake_run_agent_backend)
    monkeypatch.setattr(requirements_step.time, 'sleep', fake_sleep)

    state = controller.run_once()

    assert sleep_count >= 1
    assert dispatch_count == 0
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert state['requirementsDraftGenerated'] is True
    gate_content = (state_dir / 'approvals' / 'requirements-and-acceptance.md').read_text(encoding='utf-8')
    assert 'Existing run can finish while controller waits.' in gate_content


def test_requirements_draft_auto_revises_controller_invalid_gate_before_human_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import workflow_controller.steps.requirements as requirements_step
    from workflow_controller.runners import RunnerConfig
    from workflow_controller.runners.base import RunnerResult

    state_dir = tmp_path / 'state'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'REQUIREMENTS_DRAFT',
            'lastVerifiedStep': 'TARGET_ACCEPTANCE',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'workspacePath': str(workspace),
            'agentRunner': 'tmux-claude',
            'agentCommand': 'claude',
            'tmuxTarget': '1.2',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    bodies = [
        """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: e2e]: User completes the delivery journey.

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| 无 active must AO | AC-1 | covered | e2e | pytest tests/e2e/test_delivery.py -q |
""",
        """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: e2e]: User completes the delivery journey.

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| 无 active must AO | AC-1 | covered | e2e | pytest tests/e2e/test_delivery.py -q |

## Journey Acceptance Matrix
| Journey | Title | Status | Steps | AC | Verification Layer |
| --- | --- | --- | --- | --- | --- |
| J-001 | Delivery happy path | active | Start request -> complete delivery -> see confirmation | AC-1 | e2e |
""",
    ]
    captured_prompts: list[str] = []

    def fake_make_runner(state: dict) -> RunnerConfig:
        return RunnerConfig(backend='tmux-claude', agent_command='fake-claude', tmux_target='1.2')

    def fake_run_agent_backend(request):
        captured_prompts.append(request.prompt_path.read_text(encoding='utf-8'))
        body_path = state_dir / 'artifacts' / 'requirements-draft' / 'requirements-body.md'
        body_path.write_text(bodies.pop(0), encoding='utf-8')
        return RunnerResult(
            backend='tmux-claude',
            status='done',
            command=['fake-claude'],
            returncode=0,
            stdout='ok',
            stderr='',
            run_dir=state_dir / 'artifacts' / 'requirements-draft' / f'run-{len(captured_prompts)}',
            prompt_path=request.prompt_path,
            done_payload={'status': 'done'},
            runner_metadata={'fake': True},
        )

    monkeypatch.setattr(requirements_step, 'make_runner', fake_make_runner)
    monkeypatch.setattr(requirements_step, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert len(captured_prompts) == 2
    assert '## Controller Validation Error' in captured_prompts[1]
    assert 'journey contract required' in captured_prompts[1]
    assert state['status'] == 'active'
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert state['requirementsAccepted'] is False
    assert state['requirementsRevisionCount'] == 1
    assert state.get('blockedReason') is None
    gate_content = (state_dir / 'approvals' / 'requirements-and-acceptance.md').read_text(encoding='utf-8')
    assert '## Journey Acceptance Matrix' in gate_content


def test_unit_plan_draft_auto_revises_controller_invalid_gate_before_human_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import workflow_controller.steps.unit_plan as unit_plan_step
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file
    from workflow_controller.runners import RunnerConfig
    from workflow_controller.runners.base import RunnerResult

    state_dir = tmp_path / 'state'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'UNIT_PLAN_DRAFT',
            'lastVerifiedStep': 'REQUIREMENTS_ACCEPTANCE',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'workspacePath': str(workspace),
            'agentRunner': 'tmux-codex',
            'agentCommand': 'codex',
            'tmuxTarget': '1.2',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': False,
            'acceptanceObligations': [
                {'id': 'AO-001', 'title': 'six-step UX unclear', 'priority': 'must', 'status': 'open'},
                {'id': 'AO-002', 'title': 'materials missing coverage', 'priority': 'must', 'status': 'open'},
            ],
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: integration]: Delivery behavior covers AO-001 and AO-002.

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| AO-001 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |
| AO-002 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |
""",
    )
    approve_gate_file(requirements_path, actor='tester')
    bodies = [
        _unit_plan_body_with_obligations(['AO-001']),
        _unit_plan_body_with_obligations(['AO-001', 'AO-002']),
    ]
    captured_prompts: list[str] = []

    def fake_make_runner(state: dict) -> RunnerConfig:
        return RunnerConfig(backend='tmux-codex', agent_command='fake-codex', tmux_target='1.2')

    def fake_run_agent_backend(request):
        captured_prompts.append(request.prompt_path.read_text(encoding='utf-8'))
        body_path = request.artifact_dir / 'unit-plan-body.md'
        body_path.write_text(bodies.pop(0), encoding='utf-8')
        return RunnerResult(
            backend='tmux-codex',
            status='done',
            command=['fake-codex'],
            returncode=0,
            stdout='ok',
            stderr='',
            run_dir=request.artifact_dir / f'run-{len(captured_prompts)}',
            prompt_path=request.prompt_path,
            done_payload={'status': 'done'},
            runner_metadata={'fake': True},
        )

    monkeypatch.setattr(unit_plan_step, 'make_runner', fake_make_runner)
    monkeypatch.setattr(unit_plan_step, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert len(captured_prompts) == 2
    assert '## Controller Validation Error' in captured_prompts[1]
    assert 'missing Acceptance Obligation coverage' in captured_prompts[1]
    assert 'AO-002' in captured_prompts[1]
    assert state['status'] == 'active'
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['unitPlanAccepted'] is False
    assert state['unitPlanRevisionCount'] == 1
    assert state.get('blockedReason') is None
    gate_content = (state_dir / 'approvals' / 'unit-plan.md').read_text(encoding='utf-8')
    assert '"covers_obligations": ["AO-001", "AO-002"]' in gate_content


def test_drive_auto_revises_invalid_unit_plan_with_short_precheck_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import workflow_controller.steps.unit_plan as unit_plan_step
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file
    from workflow_controller.runners import RunnerConfig
    from workflow_controller.runners.base import RunnerResult

    state_dir = tmp_path / 'state'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'REQUIREMENTS_ACCEPTANCE',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'workspacePath': str(workspace),
            'agentRunner': 'tmux-codex',
            'agentCommand': 'codex',
            'tmuxTarget': '1.2',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'acceptanceObligations': [
                {'id': 'AO-001', 'title': 'six-step UX unclear', 'priority': 'must', 'status': 'open'},
                {'id': 'AO-002', 'title': 'materials missing coverage', 'priority': 'must', 'status': 'open'},
            ],
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: integration]: Delivery behavior covers AO-001 and AO-002.

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| AO-001 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |
| AO-002 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |
""",
    )
    approve_gate_file(requirements_path, actor='tester')
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(gate_path, _unit_plan_body_with_obligations(['AO-001']))
    captured_prompts: list[str] = []

    def fake_make_runner(state: dict) -> RunnerConfig:
        return RunnerConfig(backend='tmux-codex', agent_command='fake-codex', tmux_target='1.2')

    def fake_run_agent_backend(request):
        captured_prompts.append(request.prompt_path.read_text(encoding='utf-8'))
        body_path = request.artifact_dir / 'unit-plan-body.md'
        body_path.write_text(_unit_plan_body_with_obligations(['AO-001', 'AO-002']), encoding='utf-8')
        return RunnerResult(
            backend='tmux-codex',
            status='done',
            command=['fake-codex'],
            returncode=0,
            stdout='ok',
            stderr='',
            run_dir=request.artifact_dir / f'run-{len(captured_prompts)}',
            prompt_path=request.prompt_path,
            done_payload={'status': 'done'},
            runner_metadata={'fake': True},
        )

    monkeypatch.setattr(unit_plan_step, 'make_runner', fake_make_runner)
    monkeypatch.setattr(unit_plan_step, 'run_agent_backend', fake_run_agent_backend)
    output: list[str] = []

    controller.drive(
        input_func=lambda _prompt: (_ for _ in ()).throw(EOFError),
        output_func=output.append,
        timestamp_output=False,
    )
    rendered = '\n'.join(output)

    assert captured_prompts
    assert '## Controller Validation Error' in captured_prompts[0]
    assert '[修订] Unit Plan 预检失败，已自动打回：' in rendered
    assert '当前   自动打回 Unit Plan 草案' in rendered
    assert 'unit plan gate invalid:' not in rendered
    assert rendered.index('[修订] Unit Plan 预检失败') < rendered.index('[人工确认] Unit Plan')


def test_gate_reason_label_compacts_large_acceptance_obligation_lists() -> None:
    reason = (
        'unit plan gate invalid: missing Acceptance Obligation coverage: '
        + ', '.join(f'AO-{index:03d} detailed obligation title {index}' for index in range(78, 120))
    )

    label = rrc_controller_module._gate_reason_label(reason)

    assert '42 AO missing (AO-078..AO-119)' in label
    assert 'full detail sent to revision prompt' in label
    assert 'detailed obligation title 100' not in label
    assert len(label) < 180


def test_colored_auto_revision_message_highlights_gate_and_ids() -> None:
    message = rrc_controller_module._format_auto_revision_message(
        gate_label='Unit Plan',
        action_label='预检失败，已自动打回',
        reason='missing Acceptance Obligation coverage: AO-001 and AC-1 via TC-V13-01',
        color_enabled=True,
    )

    assert '\x1b[' in message
    plain = re.sub(r'\x1b\[[0-9;]*m', '', message)
    assert plain == '[修订] Unit Plan 预检失败，已自动打回：missing Acceptance Obligation coverage: AO-001 and AC-1 via TC-V13-01'
    assert '\x1b[33mAO-001\x1b[0m' in message
    assert '\x1b[33mAC-1\x1b[0m' in message
    assert '\x1b[33mTC-V13-01\x1b[0m' in message


def _unit_plan_body_with_obligations(obligations: list[str]) -> str:
    return f"""# Unit Plan Confirmation

## Test Case Matrix
| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |
| --- | --- | --- | --- | --- |
| AC-1 covers {', '.join(obligations)} | TC-1 | integration | pytest tests/test_delivery.py -q | Delivery behavior works |

## Controller State Patch

```json
{{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {{"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}}
  ],
  "units": [
    {{
      "id": "unit-01",
      "name": "Delivery",
      "passes": false,
      "test_cases": [
        {{
          "id": "TC-1",
          "acceptance_criterion": "AC-1 covers {', '.join(obligations)}",
          "covers_obligations": {json.dumps(obligations)},
          "layer": "integration",
          "fixture": "tests/fixtures/delivery.json",
          "command": "pytest tests/test_delivery.py -q",
          "expected": "Delivery behavior works"
        }}
      ],
      "verification_commands": ["pytest tests/test_delivery.py -q"]
    }}
  ]
}}
```
"""


def test_drive_announces_plannotator_feedback_before_revising_gate(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        '# Requirements & Acceptance Confirmation\n\n## 4. Test Strategy\n- Unit tests cover delivery.\n',
    )
    approve_gate_file(requirements_path, actor='tester')

    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Units
### unit-01 - Delivery
- Verification commands:
  - `pytest tests/test_delivery.py -q`
""",
    )
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
import json

print('Open this link on your local machine to annotate:')
print('https://share.plannotator.ai/#feedback')
print(json.dumps({
    "decision": "annotated",
    "feedback": "# File Feedback\\n\\nI've reviewed this file and have 2 pieces of feedback:\\n\\n## 1. Feedback on: \\"Objective Coverage Matrix\\"\\n> please split this unit before approval.\\n\\n## 2. Feedback on: \\"Verification commands\\"\\n> please add explicit database env.\\n\\n---\\n"
}))
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '1',
        '--plannotator-command',
        str(fake_plannotator),
        input_text='v\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[Plannotator] 已收到修改意见，开始重新生成 Unit Plan。' in result.stdout
    assert '修改意见：共 2 条，完整反馈已写入 Claude 返工 prompt。' in result.stdout
    assert '预览：# File Feedback' in result.stdout
    assert '[修订] 已根据 Plannotator 反馈重新生成 Unit Plan。' in result.stdout


def test_drive_blocks_revise_after_plannotator_when_feedback_is_not_submitted(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Unit Plan Confirmation\n\n## Human Confirmation\n\nStatus: pending\nConfirmed by: \nConfirmed at: \nContent hash: sha256:legacy\n',
        encoding='utf-8',
    )
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
print('Open this link on your local machine to annotate:')
print('https://share.plannotator.ai/#fake-no-local-feedback')
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--plannotator-command',
        str(fake_plannotator),
        input_text='v\nr\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert 'Plannotator 尚未提交可供 controller 读取的返工反馈' in result.stdout
    assert 'Plannotator 没有返回返工反馈' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert 'unitPlanRevisionCount' not in state


def test_drive_blocks_revise_after_plannotator_review_without_submitted_feedback(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Unit Plan Confirmation\n\n## Human Confirmation\n\nStatus: pending\nConfirmed by: \nConfirmed at: \nContent hash: sha256:legacy\n',
        encoding='utf-8',
    )
    summary_path = state_dir / 'plannotator' / 'unit-plan-last-review.json'
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                'gate': 'unit-plan',
                'gate_path': str(gate_path),
                'stdout': '',
                'stderr': '(document only, annotations added in browser)',
            }
        ),
        encoding='utf-8',
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        input_text='r\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert 'Plannotator 尚未提交可供 controller 读取的返工反馈' in result.stdout
    assert 'Plannotator 没有返回返工反馈' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert 'unitPlanRevisionCount' not in state


def test_drive_passes_configured_plannotator_port_to_review_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Unit Plan Confirmation\n\n## Human Confirmation\n\nStatus: pending\nConfirmed by: \nConfirmed at: \nContent hash: sha256:legacy\n',
        encoding='utf-8',
    )
    env_log = tmp_path / 'plannotator-env.json'
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

Path(os.environ['PLANNOTATOR_ENV_LOG']).write_text(
    json.dumps({'port': os.environ.get('PLANNOTATOR_PORT')}),
    encoding='utf-8',
)
print('Open this link on your local machine to annotate:')
print('https://share.plannotator.ai/#fake-port')
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)
    monkeypatch.setenv('PLANNOTATOR_ENV_LOG', str(env_log))

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--plannotator-command',
        str(fake_plannotator),
        '--plannotator-port',
        '20000',
        input_text='v\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert 'http://localhost:20000' in result.stdout
    assert json.loads(env_log.read_text(encoding='utf-8')) == {'port': '20000'}


def test_drive_waits_for_plannotator_approval_after_printing_link(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        '# Requirements & Acceptance Confirmation\n\n## 4. Test Strategy\n- Unit tests cover delivery.\n',
    )
    approve_gate_file(requirements_path, actor='tester')
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Units
### unit-01 - Delivery
- Verification commands:
  - `pytest tests/test_delivery.py -q`

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery",
      "passes": false,
      "verification_commands": ["pytest tests/test_delivery.py -q"]
    }
  ]
}
```
""",
    )
    fake_plannotator = tmp_path / 'fake-plannotator'
    fake_plannotator.write_text(
        """#!/usr/bin/env python3
import time

print('Open this link on your local machine to annotate:', flush=True)
print('https://share.plannotator.ai/#long-running', flush=True)
time.sleep(0.2)
print('{"decision":"approved"}', flush=True)
""",
        encoding='utf-8',
    )
    fake_plannotator.chmod(0o755)

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '1',
        '--plannotator-command',
        str(fake_plannotator),
        input_text='v\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[Plannotator] 已打开辅助审阅。' in result.stdout
    assert 'http://localhost:20000' in result.stdout
    assert 'Open this link on your local machine to annotate:' not in result.stdout
    assert 'https://share.plannotator.ai/#long-running' not in result.stdout
    assert '等待 Plannotator 操作结果' in result.stdout
    assert '[Plannotator] 已收到 Approve，等同于人工确认通过。' in result.stdout
    summary = json.loads((state_dir / 'plannotator' / 'unit-plan-last-review.json').read_text(encoding='utf-8'))
    assert summary['process_id'] > 0
    assert summary['returncode'] is None
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['unitPlanAccepted'] is True


def test_drive_can_approve_unit_plan_gate_and_continue(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(
        '# Requirements & Acceptance Confirmation\n\n## 4. Test Strategy\n- Unit tests cover delivery.\n\n'
        '## Human Confirmation\n\nStatus: approved\nConfirmed by: tester\nConfirmed at: now\nContent hash: sha256:legacy\n',
        encoding='utf-8',
    )
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    write_gate_file(
        requirements_path,
        '# Requirements & Acceptance Confirmation\n\n## 4. Test Strategy\n- Unit tests cover delivery.\n',
    )
    approve_gate_file(requirements_path, actor='tester')
    unit_plan_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        unit_plan_path,
        """# Unit Plan Confirmation

## Units
### unit-01 - Delivery
- Verification commands:
  - `pytest tests/test_delivery.py -q`

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery",
      "passes": false,
      "verification_commands": ["pytest tests/test_delivery.py -q"]
    }
  ]
}
```
""",
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '1',
        '--actor',
        'tester',
        input_text='a\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[确认] Unit Plan 已确认，继续推进。' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['unitPlanAccepted'] is True
    assert state['currentStep'] == 'PLAN_CREATED'


def test_drive_blocks_unit_plan_approval_when_acceptance_obligation_is_missing(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'acceptanceObligations': [
                {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
                {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
            ],
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import write_gate_file

    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Test Case Matrix
| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |
| --- | --- | --- | --- | --- |
| AC-1 covers AO-001 | TC-1 | integration | pytest tests/test_delivery.py -q | AO-001 works |

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery",
      "passes": false,
      "test_cases": [
        {
          "id": "TC-1",
          "acceptance_criterion": "AC-1",
          "covers_obligations": ["AO-001"],
          "layer": "integration",
          "command": "pytest tests/test_delivery.py -q",
          "expected": "AO-001 works"
        }
      ],
      "verification_commands": ["pytest tests/test_delivery.py -q"]
    }
  ]
}
```
""",
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '3',
        input_text='a\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert 'missing Acceptance Obligation coverage' in result.stdout
    assert 'AO-002' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['unitPlanAccepted'] is False
    assert state['blockedReason'].startswith('unit plan gate invalid:')


def test_requirements_approval_blocks_unmapped_acceptance_obligation(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
            'lastVerifiedStep': 'REQUIREMENTS_DRAFT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': True,
            'acceptanceObligations': [
                {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
                {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
            ],
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import write_gate_file

    gate_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        gate_path,
        """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: integration]: 六步 UX 清楚展示。

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| AO-001 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |
""",
    )

    with pytest.raises(ValueError, match='requirements gate invalid:.*AO-002'):
        controller.approve_human_gate('requirements', actor='tester')

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['requirementsAccepted'] is False
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert state['blockedReason'].startswith('requirements gate invalid:')


def test_requirements_journey_contract_requirement_ignores_template_guidance() -> None:
    from workflow_controller.journeys import requirements_requires_journey_contract

    template_guidance = """# 需求与验收确认

## 3. 验收标准
- 每条 AC 必须声明 verification layer，推荐格式：`AC-ID [verification: e2e]`。
- 当前上下文中的目标验收标准均已满足。

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| 无 active must AO | 待补 AC ID | pending | 待补 | 待补证据或原因 |
"""

    assert requirements_requires_journey_contract(template_guidance) is False
    assert requirements_requires_journey_contract('- AC-1 [verification: e2e]: user completes delivery.') is True


def test_requirements_approval_blocks_e2e_ac_without_journey_contract(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
            'lastVerifiedStep': 'REQUIREMENTS_DRAFT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import write_gate_file

    gate_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        gate_path,
        """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: e2e]: User completes the delivery journey.

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| 无 active must AO | AC-1 | covered | e2e | pytest tests/e2e/test_delivery.py -q |
""",
    )

    with pytest.raises(ValueError, match='requirements gate invalid:.*journey'):
        controller.approve_human_gate('requirements', actor='tester')

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['requirementsAccepted'] is False
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert 'journey' in state['blockedReason'].lower()


def test_requirements_approval_writes_journey_contract_artifact(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
            'lastVerifiedStep': 'REQUIREMENTS_DRAFT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import write_gate_file

    gate_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        gate_path,
        """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: e2e]: User completes the delivery journey.

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| 无 active must AO | AC-1 | covered | e2e | pytest tests/e2e/test_delivery.py -q |

## Journey Acceptance Matrix
| Journey | Title | Status | Steps | AC | Verification Layer |
| --- | --- | --- | --- | --- | --- |
| J-001 | Delivery happy path | active | Start request -> complete delivery -> see confirmation | AC-1 | e2e |
""",
    )

    controller.approve_human_gate('requirements', actor='tester')

    artifact_path = state_dir / 'artifacts' / 'journeys' / 'journeys.json'
    assert artifact_path.exists()
    contract = json.loads(artifact_path.read_text(encoding='utf-8'))
    assert contract['version'] == 1
    assert contract['source_gate'] == 'requirements'
    assert contract['requirements_gate_path'] == str(gate_path)
    assert len(contract['requirements_gate_hash']) == 64
    assert contract['unit_plan_gate_hash'] is None
    assert len(contract['journeys']) == 1
    journey = contract['journeys'][0]
    assert journey['journey_id'] == 'J-001'
    assert journey['title'] == 'Delivery happy path'
    assert journey['status'] == 'active'
    assert journey['steps'] == ['Start request', 'complete delivery', 'see confirmation']
    assert journey['linked_acceptance_criteria'] == ['AC-1']
    assert journey['linked_units'] == []
    assert journey['verification_layer'] == 'e2e'
    assert journey['verification_command'] is None
    assert journey['test_cases'] == []
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['journeyContractPath'] == str(artifact_path)


def test_run_rejects_preapproved_requirements_missing_ac_verification_layer(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
            'lastVerifiedStep': 'REQUIREMENTS_DRAFT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': True,
            'acceptanceObligations': [
                {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
            ],
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    gate_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        gate_path,
        """# 需求与验收确认

## 3. 验收标准
- AC-1: 六步 UX 清楚展示。

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| AO-001 | AC-1 | covered |  | pytest tests/test_delivery.py -q |
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['requirementsAccepted'] is False
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert state['blockedReason'].startswith('requirements gate invalid:')
    assert 'AC-1' in state['blockedReason']
    assert 'verification layer' in state['blockedReason']


def test_requirements_revision_feedback_includes_controller_validation_error(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
            'lastVerifiedStep': 'REQUIREMENTS_DRAFT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': True,
            'acceptanceObligations': [
                {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
            ],
            'blockedReason': 'requirements gate invalid: AC-1 missing verification layer',
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import write_gate_file

    gate_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(gate_path, '# 需求与验收确认\n\n## 3. 验收标准\n- AC-1: 六步 UX 清楚展示。\n')

    feedback = controller._revision_feedback_for_gate('requirements', gate_path)

    assert '## Controller Validation Error' in feedback
    assert 'requirements gate invalid: AC-1 missing verification layer' in feedback

    revised_path = controller.revise_human_gate('requirements')

    assert revised_path == gate_path
    revision_path = state_dir / 'artifacts' / 'requirements-revisions' / 'revision-1.json'
    revision = json.loads(revision_path.read_text(encoding='utf-8'))
    assert revision['controller_validation_error'] == 'requirements gate invalid: AC-1 missing verification layer'
    assert '## Controller Validation Error' in revision['feedback']
    assert 'requirements gate invalid: AC-1 missing verification layer' in revision['feedback']


def test_approve_requirements_gate_records_change_request_approver(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
            'lastVerifiedStep': 'REQUIREMENTS_DRAFT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'requirementsDraftGenerated': True,
            'pendingRequirementChangeRequestIds': ['CR-0001'],
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    change_requests_path = state_dir / 'change_requests.jsonl'
    change_requests_path.write_text(
        json.dumps(
            {
                'id': 'CR-0001',
                'record_type': 'change_request',
                'status': 'pending_requirements_approval',
                'approver': None,
            },
            ensure_ascii=False,
        ) + '\n',
        encoding='utf-8',
    )
    from workflow_controller.gates.parsers import write_gate_file

    gate_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        gate_path,
        """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: unit]: Delivery works.

## 4. 需求可追溯矩阵（Requirements Traceability Matrix）
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| 无 active must AO | AC-1 | covered | unit | pytest tests/test_delivery.py -q |

## 4.5 设计与架构可追溯矩阵（Design/Architecture Traceability Matrix）
| AC | Product Design Ref | Technical Architecture Ref | Notes |
| --- | --- | --- | --- |
| AC-1 | ## 7. 产品设计概要 | ## 8. 架构概要 | traced |
""",
    )

    controller.approve_human_gate('requirements', actor='alice')

    records = [
        json.loads(line)
        for line in change_requests_path.read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    assert records[-1]['id'] == 'CR-0001'
    assert records[-1]['record_type'] == 'change_request_status'
    assert records[-1]['status'] == 'approved'
    assert records[-1]['approver'] == 'alice'
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['pendingRequirementChangeRequestIds'] == []


def test_unit_plan_approval_rejects_active_journey_without_mapped_test_case(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'journeyContractPath': str(state_dir / 'artifacts' / 'journeys' / 'journeys.json'),
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    journey_path = state_dir / 'artifacts' / 'journeys' / 'journeys.json'
    journey_path.parent.mkdir(parents=True, exist_ok=True)
    journey_path.write_text(
        json.dumps(
            {
                'version': 1,
                'journeys': [
                    {
                        'journey_id': 'J-001',
                        'title': 'Delivery happy path',
                        'status': 'active',
                        'steps': ['Start request', 'complete delivery'],
                        'linked_acceptance_criteria': ['AC-1'],
                        'linked_units': [],
                        'verification_layer': 'e2e',
                        'verification_command': None,
                        'test_cases': [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n', encoding='utf-8')
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    gate_path = approvals_dir / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery unit",
      "passes": false,
      "workflow_validation_level": "closure",
      "test_cases": [
        {
          "id": "TC-AC1-E2E",
          "acceptance_criterion": "AC-1",
          "layer": "e2e",
          "fixture": "tests/fixtures/delivery.json",
          "command": "pytest tests/e2e/test_delivery.py -q",
          "expected": "delivery confirmation is visible",
          "golden_path": true
        }
      ],
      "verification_commands": ["pytest tests/e2e/test_delivery.py -q"]
    }
  ]
}
```
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['unitPlanAccepted'] is False
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert 'journey mapping is incomplete' in state['blockedReason']
    assert 'J-001' in state['blockedReason']


def test_unit_plan_approval_enriches_journey_contract_from_mapped_test_case(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'journeyContractPath': str(state_dir / 'artifacts' / 'journeys' / 'journeys.json'),
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    journey_path = state_dir / 'artifacts' / 'journeys' / 'journeys.json'
    journey_path.parent.mkdir(parents=True, exist_ok=True)
    journey_path.write_text(
        json.dumps(
            {
                'version': 1,
                'journeys': [
                    {
                        'journey_id': 'J-001',
                        'title': 'Delivery happy path',
                        'status': 'active',
                        'steps': ['Start request', 'complete delivery'],
                        'linked_acceptance_criteria': ['AC-1'],
                        'linked_units': [],
                        'verification_layer': 'e2e',
                        'verification_command': None,
                        'test_cases': [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n', encoding='utf-8')
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    gate_path = approvals_dir / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery unit",
      "passes": false,
      "workflow_validation_level": "closure",
      "test_cases": [
        {
          "id": "TC-AC1-E2E",
          "journey_id": "J-001",
          "acceptance_criterion": "AC-1",
          "layer": "e2e",
          "fixture": "tests/fixtures/delivery.json",
          "command": "pytest tests/e2e/test_delivery.py -q",
          "expected": "delivery confirmation is visible",
          "golden_path": true
        }
      ],
      "verification_commands": ["pytest tests/e2e/test_delivery.py -q"]
    }
  ]
}
```
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['unitPlanAccepted'] is True
    assert state['currentStep'] == 'PLAN_CREATED'
    contract = json.loads(journey_path.read_text(encoding='utf-8'))
    assert len(contract['unit_plan_gate_hash']) == 64
    journey = contract['journeys'][0]
    assert journey['linked_units'] == ['unit-01']
    assert journey['test_cases'] == ['TC-AC1-E2E']
    assert journey['verification_command'] == 'pytest tests/e2e/test_delivery.py -q'



def test_unit_plan_approval_accepts_covers_journeys_mapping(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'journeyContractPath': str(state_dir / 'artifacts' / 'journeys' / 'journeys.json'),
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    journey_path = state_dir / 'artifacts' / 'journeys' / 'journeys.json'
    journey_path.parent.mkdir(parents=True, exist_ok=True)
    journey_path.write_text(
        json.dumps(
            {
                'version': 1,
                'journeys': [
                    {
                        'journey_id': 'J-001',
                        'title': 'Delivery happy path',
                        'status': 'active',
                        'steps': ['Start request', 'complete delivery'],
                        'linked_acceptance_criteria': ['AC-1'],
                        'linked_units': [],
                        'verification_layer': 'e2e',
                        'verification_command': None,
                        'test_cases': [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n', encoding='utf-8')
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    gate_path = approvals_dir / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery unit",
      "passes": false,
      "workflow_validation_level": "closure",
      "test_cases": [
        {
          "id": "TC-AC1-E2E",
          "covers_journeys": ["J-001"],
          "acceptance_criterion": "AC-1",
          "layer": "e2e",
          "fixture": "tests/fixtures/delivery.json",
          "command": "pytest tests/e2e/test_delivery.py -q",
          "expected": "delivery confirmation is visible",
          "golden_path": true
        }
      ],
      "verification_commands": ["pytest tests/e2e/test_delivery.py -q"]
    }
  ]
}
```
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['unitPlanAccepted'] is True
    contract = json.loads(journey_path.read_text(encoding='utf-8'))
    journey = contract['journeys'][0]
    assert journey['test_cases'] == ['TC-AC1-E2E']


def test_unit_plan_approval_accepts_backticked_journey_contract_ids(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'journeyContractPath': str(state_dir / 'artifacts' / 'journeys' / 'journeys.json'),
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    journey_path = state_dir / 'artifacts' / 'journeys' / 'journeys.json'
    journey_path.parent.mkdir(parents=True, exist_ok=True)
    journey_path.write_text(
        json.dumps(
            {
                'version': 1,
                'journeys': [
                    {
                        'journey_id': '`J-001`',
                        'title': 'Delivery happy path',
                        'status': 'active',
                        'steps': ['Start request', 'complete delivery'],
                        'linked_acceptance_criteria': ['AC-1'],
                        'linked_units': [],
                        'verification_layer': 'e2e',
                        'verification_command': None,
                        'test_cases': [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n', encoding='utf-8')
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    gate_path = approvals_dir / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery unit",
      "passes": false,
      "workflow_validation_level": "closure",
      "test_cases": [
        {
          "id": "TC-AC1-E2E",
          "covers_journeys": ["J-001"],
          "acceptance_criterion": "AC-1",
          "layer": "e2e",
          "fixture": "tests/fixtures/delivery.json",
          "command": "pytest tests/e2e/test_delivery.py -q",
          "expected": "delivery confirmation is visible",
          "golden_path": true
        }
      ],
      "verification_commands": ["pytest tests/e2e/test_delivery.py -q"]
    }
  ]
}
```
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['unitPlanAccepted'] is True
    contract = json.loads(journey_path.read_text(encoding='utf-8'))
    journey = contract['journeys'][0]
    assert journey['journey_id'] == 'J-001'
    assert journey['test_cases'] == ['TC-AC1-E2E']


def test_unit_plan_approval_accepts_journey_refs_mapping(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'journeyContractPath': str(state_dir / 'artifacts' / 'journeys' / 'journeys.json'),
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    journey_path = state_dir / 'artifacts' / 'journeys' / 'journeys.json'
    journey_path.parent.mkdir(parents=True, exist_ok=True)
    journey_path.write_text(
        json.dumps(
            {
                'version': 1,
                'journeys': [
                    {
                        'journey_id': 'J-001',
                        'title': 'Delivery happy path',
                        'status': 'active',
                        'steps': ['Start request', 'complete delivery'],
                        'linked_acceptance_criteria': ['AC-1'],
                        'linked_units': [],
                        'verification_layer': 'e2e',
                        'verification_command': None,
                        'test_cases': [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n', encoding='utf-8')
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    gate_path = approvals_dir / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery unit",
      "passes": false,
      "workflow_validation_level": "closure",
      "test_cases": [
        {
          "id": "TC-AC1-E2E",
          "journey_refs": ["J-001"],
          "acceptance_criterion": "AC-1",
          "layer": "e2e",
          "fixture": "tests/fixtures/delivery.json",
          "command": "pytest tests/e2e/test_delivery.py -q",
          "expected": "delivery confirmation is visible",
          "golden_path": true
        }
      ],
      "verification_commands": ["pytest tests/e2e/test_delivery.py -q"]
    }
  ]
}
```
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['unitPlanAccepted'] is True
    contract = json.loads(journey_path.read_text(encoding='utf-8'))
    journey = contract['journeys'][0]
    assert journey['linked_units'] == ['unit-01']
    assert journey['test_cases'] == ['TC-AC1-E2E']
    assert journey['verification_command'] == 'pytest tests/e2e/test_delivery.py -q'


def test_run_rejects_preapproved_unit_plan_missing_acceptance_obligation(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'acceptanceObligations': [
                {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
                {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
            ],
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Test Case Matrix
| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |
| --- | --- | --- | --- | --- |
| AC-1 covers AO-001 | TC-1 | integration | pytest tests/test_delivery.py -q | AO-001 works |

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery",
      "passes": false,
      "test_cases": [
        {
          "id": "TC-1",
          "acceptance_criterion": "AC-1",
          "covers_obligations": ["AO-001"],
          "layer": "integration",
          "command": "pytest tests/test_delivery.py -q",
          "expected": "AO-001 works"
        }
      ],
      "verification_commands": ["pytest tests/test_delivery.py -q"]
    }
  ]
}
```
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['unitPlanAccepted'] is False
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert 'missing Acceptance Obligation coverage' in state['blockedReason']
    assert 'AO-002' in state['blockedReason']
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['unitPlanAccepted'] is False
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['blockedReason'].startswith('unit plan gate invalid:')


def test_run_rejects_preapproved_unit_plan_missing_design_architecture_traceability(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: integration]: Delivery behavior works.

## Design/Architecture Traceability Matrix
| AC | Product Design Ref | Technical Architecture Ref | Notes |
| --- | --- | --- | --- |
| AC-1 | PD-AC1-delivery-flow | TA-AC1-delivery-service | delivery flow |
""",
    )
    approve_gate_file(requirements_path, actor='tester')

    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery",
      "passes": false,
      "test_cases": [
        {
          "id": "TC-1",
          "acceptance_criterion": "AC-1",
          "layer": "integration",
          "command": "pytest tests/test_delivery.py -q",
          "expected": "Delivery behavior works"
        }
      ],
      "verification_commands": ["pytest tests/test_delivery.py -q"]
    }
  ]
}
```
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['unitPlanAccepted'] is False
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert 'design/architecture traceability' in state['blockedReason']
    assert state['blockedReason'].startswith('unit plan gate invalid:')


def test_drive_blocks_unit_plan_approval_when_plan_is_invalid(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Old objective', 'units': ['old-unit'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'old-unit', 'name': 'Old unit', 'passes': True},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import write_gate_file

    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Old objective", "units": ["missing-old-unit"], "status": "covered"},
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {"id": "unit-01", "name": "Delivery", "passes": false}
  ]
}
```
""",
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '3',
        input_text='a\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert 'unit plan gate invalid' in result.stdout
    assert '[确认] Unit Plan 已确认，继续推进。' not in result.stdout
    assert '[确认] Unit Plan 无法确认：unit plan gate invalid' in result.stdout
    assert result.stdout.count('[人工确认] Unit Plan') == 1
    assert '[停止] 已达到最大自动步数' not in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['unitPlanAccepted'] is False
    assert 'unitPlanAcceptedHash' not in state
    assert state['blockedReason'].startswith('unit plan gate invalid:')
    assert 'Status: pending' in gate_path.read_text(encoding='utf-8')


def test_drive_refreshes_stale_unit_plan_invalid_reason_from_current_gate(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-db',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'blockedReason': "unit plan gate invalid: old target-v2-2 error",
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-db'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-db', 'name': 'Database unit', 'passes': False},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import write_gate_file

    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Objective Coverage Matrix
- Delivery objective -> unit-db

## Units
### unit-db - Database unit

## Controller State Patch

```json
{
  "currentUnitId": "unit-db",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-db"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-db",
      "name": "Database unit",
      "passes": false,
      "verification_commands": ["cd app && pnpm exec prisma migrate dev --name init"]
    }
  ]
}
```
""",
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        input_text='q\n',
    )

    assert result.returncode == 0, result.stderr
    assert 'verification_env is incomplete' in result.stdout
    assert 'old target-v2-2 error' not in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert 'verification_env is incomplete' in state['blockedReason']
    assert 'old target-v2-2 error' not in state['blockedReason']


def test_drive_can_revise_unit_plan_gate_from_human_notes(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text('# Unit Plan Confirmation\n\nReviewer note: split E2E closure.\n', encoding='utf-8')

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '0',
        input_text='r\nq\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[修订] 已重新生成 Unit Plan，请重新阅读确认。' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['unitPlanRevisionCount'] == 1


def test_revise_unit_plan_after_builder_blocked_preserves_requirements_and_injects_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    requirements_hash = 'sha256:req-approved'
    unit_plan_hash = 'sha256:unit-approved'
    blocker = 'CLI Proxy API contract is missing; cannot safely implement disable/restore behavior.'
    controller.init_state(
        {
            'task_id': 'target-v1-8-1',
            'currentUnitId': 'unit-01',
            'currentStep': 'PLAN_APPROVED',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'V1.8.1',
            'feasibleOutcome': 'V1.8.1',
            'scopeApproved': True,
            'autoApprove': True,
            'agentRunner': 'tmux-claude',
            'workspacePath': str(workspace),
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'requirementsAcceptedHash': requirements_hash,
            'requirementsAcceptedBy': 'human',
            'unitPlanAccepted': True,
            'unitPlanAcceptedHash': unit_plan_hash,
            'unitPlanAcceptedBy': 'human',
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'scope': ['Implement delivery behavior'], 'passes': False},
            ],
        },
        force=True,
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text(
        '# Requirements & Acceptance Confirmation\n\n- AC-1: Delivery behavior works.\n',
        encoding='utf-8',
    )
    (approvals_dir / 'unit-plan.md').write_text(
        '# Unit Plan Confirmation\n\n'
        'Reviewer note: keep the manual CLI Proxy path as supplemental context.\n\n'
        '## Human Confirmation\n\n'
        'Status: approved\n'
        'Confirmed by: human\n'
        'Content hash: sha256:unit-approved\n',
        encoding='utf-8',
    )
    unit_dir = state_dir / 'artifacts' / 'unit-01'
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / 'builder-summary.json').write_text(
        json.dumps(
            {
                'runner_status': 'blocked',
                'done_payload': {
                    'status': 'blocked',
                    'summary': blocker,
                    'run_id': 'builder-run',
                },
            }
        ),
        encoding='utf-8',
    )
    planner_prompts: list[str] = []

    def fake_run_agent_backend(request):
        planner_prompts.append(request.prompt_path.read_text(encoding='utf-8'))
        _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    controller.revise_human_gate('unit-plan')

    assert planner_prompts, 'Expected Unit Plan drafter prompt to be captured'
    prompt = planner_prompts[0]
    assert blocker in prompt
    assert 'Treat this as Unit Plan revision context, not a Requirements change.' in prompt
    assert prompt.index(blocker) < prompt.index('keep the manual CLI Proxy path as supplemental context')
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['unitPlanAccepted'] is False
    assert 'unitPlanAcceptedHash' not in state
    assert 'unitPlanAcceptedBy' not in state
    assert state['requirementsAccepted'] is True
    assert state['requirementsAcceptedHash'] == requirements_hash
    assert state['requirementsAcceptedBy'] == 'human'
    assert state['unitPlanRevisionCount'] == 1
    assert not (state_dir / 'change_requests.jsonl').exists()


def test_drive_can_reject_final_acceptance_and_return_to_builder(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': True},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'final-acceptance.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [ ] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [x] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        'Reviewer note: import preview is missing retry state.\n',
        encoding='utf-8',
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '0',
        input_text='r\n',
    )

    assert result.returncode == 0, result.stderr
    assert '    r  验收不通过，带批注返工' in result.stdout
    assert '[返工] 最终验收未通过，已回到 Builder。' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'EXECUTE_UNIT'
    assert state['finalAcceptanceRejectionRoute'] == 'implementation'
    assert state['finalAcceptanceAccepted'] is False
    assert state['finalAcceptanceRejectionCount'] == 1
    assert 'import preview is missing retry state' in state['finalAcceptanceRejectionFeedback']
    assert state['units'][0]['passes'] is False
    assert state['objectiveCoverage'][0]['status'] == 'partial'


def test_reject_final_acceptance_routes_to_requirements_when_selected_with_other_reasons(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'unitPlanDraftGenerated': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': True},
            ],
        },
        force=True,
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n', encoding='utf-8')
    (approvals_dir / 'unit-plan.md').write_text('# Unit Plan\n', encoding='utf-8')
    gate_path = approvals_dir / 'final-acceptance.md'
    gate_path.write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [x] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [ ] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [x] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        'Reviewer note: add missing acceptance around offline import recovery. '
        'Impacts AO-123, AC-07, TC-AC-07, Journey: offline import recovery.\n',
        encoding='utf-8',
    )

    controller.reject_final_acceptance_gate()

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert state['finalAcceptanceRejectionRoute'] == 'requirements'
    assert state['requirementsAccepted'] is False
    assert state['unitPlanAccepted'] is False
    assert state['requirementsDraftGenerated'] is True
    assert state['unitPlanDraftGenerated'] is False
    assert not (approvals_dir / 'unit-plan.md').exists()
    assert state['units'][0]['passes'] is False
    assert state['objectiveCoverage'][0]['status'] == 'partial'

    change_requests = [
        json.loads(line)
        for line in (state_dir / 'change_requests.jsonl').read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    assert len(change_requests) == 1
    change_request = change_requests[0]
    assert change_request['id'] == 'CR-0001'
    assert change_request['source'] == 'final_acceptance_rejection'
    assert change_request['source_gate'] == 'final-acceptance'
    assert change_request['source_ref'] == 'final-acceptance:rejection-1'
    assert change_request['route'] == 'requirements'
    assert 'offline import recovery' in change_request['reason']
    assert change_request['status'] == 'pending_requirements_approval'
    assert change_request['approver'] is None
    assert change_request['impacted']['acceptance_obligations'] == ['AO-123']
    assert change_request['impacted']['acceptance_criteria'] == ['AC-07']
    assert change_request['impacted']['test_cases'] == ['TC-AC-07']
    assert change_request['impacted']['journeys'] == ['offline import recovery']
    assert len(change_request['before_hash']) == 64
    assert len(change_request['after_hash']) == 64
    assert change_request['changed'] is True

    events = [
        json.loads(line)
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    rejected_event = [event for event in events if event['type'] == 'final_acceptance_rejected'][-1]
    assert rejected_event['payload']['change_request_id'] == 'CR-0001'


def test_reject_final_acceptance_requires_human_routing_checkbox(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': True},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'final-acceptance.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [ ] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [ ] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n',
        encoding='utf-8',
    )

    try:
        controller.reject_final_acceptance_gate()
    except ValueError as exc:
        assert 'Final acceptance rejection routing must select one option' in str(exc)
    else:
        raise AssertionError('expected rejection without routing to fail')

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_FINAL_ACCEPTANCE'
    assert state['units'][0]['passes'] is True


def test_drive_prompts_for_final_acceptance_rejection_route_when_unselected(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': True},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'final-acceptance.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [ ] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [ ] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        'Reviewer note: button copy is wrong.\n',
        encoding='utf-8',
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '0',
        input_text='r\n4\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[验收路由] 请选择最终验收不通过后的流向：' in result.stdout
    assert '1  验收缺陷修复 -> Defect Fix' in result.stdout
    assert '4  实现返工 -> Builder' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'EXECUTE_UNIT'
    assert state['finalAcceptanceRejectionRoute'] == 'implementation'
    content = gate_path.read_text(encoding='utf-8')
    assert '- [x] 实现返工:' in content
    assert 'Reviewer note: button copy is wrong.' in content


def test_drive_defect_fix_route_migrates_old_final_acceptance_gate_and_keeps_plannotator_feedback(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'v2-2-u5-baidu-search',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'V2.2',
            'feasibleOutcome': 'V2.2',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'unitPlanDraftGenerated': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Logo objective', 'units': ['v2-2-u2-logo-real'], 'status': 'covered'},
                {'objective': 'Baidu objective', 'units': ['v2-2-u5-baidu-search'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'v2-2-u2-logo-real', 'name': 'logo', 'passes': True},
                {'id': 'v2-2-u5-baidu-search', 'name': 'baidu', 'passes': True},
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import write_gate_file

    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n', encoding='utf-8')
    gate_path = approvals_dir / 'final-acceptance.md'
    write_gate_file(
        gate_path,
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        'If final acceptance is rejected, select the human routing decision below. Multiple selections are allowed; requirements revision has highest priority.\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [ ] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        '## Rejection Notes\n'
        'Old gate format without Defect fix row.\n',
    )
    plannotator_dir = state_dir / 'plannotator'
    plannotator_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = plannotator_dir / 'final-acceptance-last-review.stdout.log'
    stdout_path.write_text(
        json.dumps(
            {
                'decision': 'annotated',
                'feedback': '# File Feedback\n\nplayback logo needs dark-mode asset and better placement.',
            }
        ),
        encoding='utf-8',
    )
    (plannotator_dir / 'final-acceptance-last-review.json').write_text(
        json.dumps(
            {
                'gate_path': str(gate_path),
                'approval_gate_path': str(gate_path),
                'stdout_path': str(stdout_path),
            }
        ),
        encoding='utf-8',
    )

    result = run_rrc(
        'drive',
        '--state-dir',
        str(state_dir),
        '--auto-approve',
        '--max-steps',
        '0',
        input_text='r\n1\n',
    )

    assert result.returncode == 0, result.stderr
    assert '[验收路由] 已选择：Defect fix' in result.stdout
    assert '[返工] 最终验收未通过，已进入验收缺陷修复流程。' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_BUG_FIX_GATE'
    assert state['finalAcceptanceRejectionRoute'] == 'defect_fix'
    assert 'playback logo needs dark-mode asset' in state['finalAcceptanceDefectFeedback']
    assert 'playback logo needs dark-mode asset' in state['finalAcceptanceRejectionFeedback']
    assert (state_dir / 'approvals' / 'bug-fix.md').exists()
    content = gate_path.read_text(encoding='utf-8')
    assert '- [x] 验收缺陷修复:' in content
    assert '- [ ] 需求变更:' in content


def test_reject_final_acceptance_routes_to_independent_bug_fix_gate(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'v2-2-u5-baidu-search',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'V2.2',
            'feasibleOutcome': 'V2.2',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'unitPlanDraftGenerated': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'i18n coverage', 'units': ['v2-2-u1-i18n-fix'], 'status': 'covered'},
                {'objective': 'logo coverage', 'units': ['v2-2-u2-logo-real'], 'status': 'covered'},
                {'objective': 'baidu provider', 'units': ['v2-2-u5-baidu-search'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'v2-2-u1-i18n-fix', 'name': 'i18n', 'passes': True},
                {'id': 'v2-2-u2-logo-real', 'name': 'logo', 'passes': True},
                {'id': 'v2-2-u5-baidu-search', 'name': 'baidu', 'passes': True},
            ],
        },
        force=True,
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n', encoding='utf-8')
    gate_path = approvals_dir / 'final-acceptance.md'
    gate_path.write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [x] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [ ] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [ ] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        'Reviewer note: homepage logo is still text-only; workbench has untranslated strings.\n',
        encoding='utf-8',
    )

    controller.reject_final_acceptance_gate()

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_BUG_FIX_GATE'
    assert state['finalAcceptanceRejectionRoute'] == 'defect_fix'
    assert state['requirementsAccepted'] is True
    assert state['unitPlanAccepted'] is True
    assert state['unitPlanDraftGenerated'] is True
    assert state['finalAcceptanceAccepted'] is False
    assert state['finalAcceptanceDefectFeedback'].startswith('# Final Acceptance Confirmation')
    assert 'homepage logo is still text-only' in state['finalAcceptanceDefectFeedback']
    assert state['bugFixGateGenerated'] is True
    assert state['bugFixAttemptCount'] == 1
    assert 'unitPlanRevisionMode' not in state
    assert all(unit['passes'] is True for unit in state['units'])
    bug_gate = approvals_dir / 'bug-fix.md'
    assert bug_gate.exists()
    bug_gate_content = bug_gate.read_text(encoding='utf-8')
    assert '# Bug Fix Gate' in bug_gate_content
    assert '## Expected Behavior' in bug_gate_content
    assert '## Actual Behavior' in bug_gate_content
    assert '## Root Cause' in bug_gate_content
    assert 'homepage logo is still text-only' in bug_gate_content
    obligations = state['acceptanceObligations']
    assert [item['id'] for item in obligations] == ['AO-001']
    assert obligations[0]['source'] == 'final_acceptance_rejection'
    assert 'homepage logo is still text-only' in obligations[0]['description']
    assert (state_dir / 'artifacts' / 'acceptance-obligations' / 'acceptance-obligations.json').exists()
    assert 'AO-001' in (state_dir / 'artifacts' / 'acceptance-obligations' / 'acceptance-obligations.md').read_text(encoding='utf-8')


def test_approved_bug_fix_gate_runs_bug_fix_and_regression_verification(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True, dry_run=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_BUG_FIX_GATE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'unitPlanDraftGenerated': True,
            'finalAcceptanceAccepted': False,
            'finalAcceptanceRejectionRoute': 'defect_fix',
            'finalAcceptanceDefectFeedback': 'Actual: retry button is missing. Expected: user can retry import.',
            'bugFixAttemptCount': 1,
            'activeBugFixId': 'bug-fix-1',
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {
                    'id': 'unit-01',
                    'name': 'Delivery',
                    'passes': True,
                    'verification_commands': ['python -c "print(\'PASS regression\')"'],
                    'test_cases': [
                        {
                            'id': 'TC-AC-01-regression',
                            'acceptance_criterion': 'AC-01',
                            'layer': 'unit',
                            'command': 'python -c "print(\'PASS regression\')"',
                            'expected': 'retry button is available',
                            'golden_path': True,
                        }
                    ],
                },
            ],
        },
        force=True,
    )
    from workflow_controller.gates.parsers import approve_gate_file, write_gate_file

    approvals_dir = state_dir / 'approvals'
    bug_gate = approvals_dir / 'bug-fix.md'
    write_gate_file(
        bug_gate,
        '# Bug Fix Gate\n\n'
        '## Expected Behavior\n- user can retry import.\n\n'
        '## Actual Behavior\n- retry button is missing.\n\n'
        '## Root Cause\n- implementation omitted retry control.\n\n'
        '## Regression Verification\n- python -c "print(\'PASS regression\')"\n',
    )
    approve_gate_file(bug_gate, actor='tester')

    state = controller.run_once()
    assert state['currentStep'] == 'BUG_FIX'
    assert state['bugFixGateAccepted'] is True

    state = controller.run_once()
    assert state['currentStep'] == 'BUG_FIX_VERIFY'
    bug_fix_dir = state_dir / 'artifacts' / 'bug-fixes' / 'bug-fix-1'
    assert (bug_fix_dir / 'root-cause.json').exists()
    assert (bug_fix_dir / 'bug-fix-summary.json').exists()
    root_cause = json.loads((bug_fix_dir / 'root-cause.json').read_text(encoding='utf-8'))
    assert root_cause['route'] == 'bug_fix'

    state = controller.run_once()
    assert state['currentStep'] == 'WAITING_FINAL_ACCEPTANCE'
    assert state['bugFixVerified'] is True
    final_gate = approvals_dir / 'final-acceptance.md'
    content = final_gate.read_text(encoding='utf-8')
    assert '## Bug Fix Evidence' in content
    assert 'bug-fix-summary.json' in content
    assert 'root-cause.json' in content


def test_bug_fix_root_cause_can_escalate_to_unit_plan_revision(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True, dry_run=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'BUG_FIX',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'unitPlanDraftGenerated': True,
            'finalAcceptanceAccepted': False,
            'finalAcceptanceRejectionRoute': 'defect_fix',
            'finalAcceptanceDefectFeedback': 'Actual: the workflow needs a missing architectural boundary.',
            'bugFixAttemptCount': 1,
            'activeBugFixId': 'bug-fix-1',
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': True},
            ],
        },
        force=True,
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n', encoding='utf-8')

    def fake_run_bug_fix(state: dict[str, Any], bug_fix_dir: Path, dry_run: bool = False):
        bug_fix_dir.mkdir(parents=True, exist_ok=True)
        root_cause = {
            'classification': 'architecture_issue',
            'route': 'unit_plan',
            'summary': 'The defect requires a new architecture boundary before implementation.',
        }
        (bug_fix_dir / 'root-cause.json').write_text(json.dumps(root_cause), encoding='utf-8')
        (bug_fix_dir / 'bug-fix-summary.json').write_text(
            json.dumps(
                {
                    'status': 'escalate_unit_plan',
                    'root_cause': root_cause,
                    'changed_files': [],
                    'regression': {'commands': [], 'evidence': []},
                }
            ),
            encoding='utf-8',
        )
        return SimpleNamespace(summary='escalated', outputs=['root-cause.json', 'bug-fix-summary.json'])

    monkeypatch.setattr(rrc_controller_module, 'run_bug_fix', fake_run_bug_fix)

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['finalAcceptanceRejectionRoute'] == 'unit_plan'
    assert state['bugFixEscalatedToUnitPlan'] is True
    assert state['unitPlanAccepted'] is False
    assert state['unitPlanDraftGenerated'] is True
    unit_plan_gate = approvals_dir / 'unit-plan.md'
    assert unit_plan_gate.exists()


def test_reject_final_acceptance_routes_to_unit_plan_revision(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'unitPlanDraftGenerated': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': True},
            ],
        },
        force=True,
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n', encoding='utf-8')
    gate_path = approvals_dir / 'final-acceptance.md'
    gate_path.write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [x] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [ ] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [ ] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        'Reviewer note: final acceptance shows verification commands need broader coverage.\n',
        encoding='utf-8',
    )

    controller.reject_final_acceptance_gate()

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['finalAcceptanceRejectionRoute'] == 'unit_plan'
    assert state['requirementsAccepted'] is True
    assert state['unitPlanAccepted'] is False
    assert state['unitPlanDraftGenerated'] is True
    assert state['units'][0]['passes'] is False


def test_reject_final_acceptance_can_block_for_environment_or_evidence_issue(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': True},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'final-acceptance.md'
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        '# Final Acceptance Confirmation\n\n'
        '## Rejection Routing\n'
        '- [ ] Requirements revision: approved requirements are incomplete or wrong.\n'
        '- [ ] Defect fix: approved requirements are correct; final acceptance found bugs in completed work.\n'
        '- [ ] Unit plan revision: unit scope or verification commands are wrong.\n'
        '- [ ] Implementation rework: approved requirements are correct; implementation needs changes.\n'
        '- [x] Blocked: cannot judge due to environment, data, access, or missing evidence.\n\n'
        'Reviewer note: missing customer account credentials for UAT.\n',
        encoding='utf-8',
    )

    controller.reject_final_acceptance_gate()

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['status'] == 'blocked'
    assert state['currentStep'] == 'WAITING_FINAL_ACCEPTANCE'
    assert state['finalAcceptanceRejectionRoute'] == 'blocked'
    assert 'Final acceptance rejected as blocked' in state['blockedReason']
    assert state['units'][0]['passes'] is True


def test_start_initializes_and_drives_workflow_in_one_command(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'

    result = run_rrc(
        'start',
        '--state-dir',
        str(state_dir),
        '--dry-run',
        '--auto-approve',
    )

    assert result.returncode == 0, result.stderr
    assert '[初始化] 创建新的 controller 状态' in result.stdout
    assert '[完成] 工作流已完成。' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'DONE'
    assert state['status'] == 'done'


def test_start_resumes_existing_state_when_target_matches(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'target-acceptance',
            'currentUnitId': 'target-1-1',
            'currentStep': 'PLAN_CREATED',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': '1.1',
            'feasibleOutcome': '1.1',
            'scopeApproved': False,
            'autoApprove': True,
            'objectiveCoverage': [
                {'objective': 'Target 1.1 acceptance', 'units': ['target-1-1'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'target-1-1', 'passes': False},
            ],
        },
        force=True,
    )

    result = run_rrc(
        'start',
        '--state-dir',
        str(state_dir),
        '--target',
        '1.1',
        '--dry-run',
        '--auto-approve',
    )

    assert result.returncode == 0, result.stderr
    assert '[继续] 使用已有状态' in result.stdout
    assert '[完成] 工作流已完成。' in result.stdout


def test_start_rejects_existing_state_when_target_differs_without_force(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'target-acceptance',
            'currentUnitId': 'target-1-1',
            'currentStep': 'PLAN_CREATED',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': '1.1',
            'feasibleOutcome': '1.1',
            'scopeApproved': False,
            'autoApprove': True,
            'objectiveCoverage': [
                {'objective': 'Target 1.1 acceptance', 'units': ['target-1-1'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'target-1-1', 'passes': False},
            ],
        },
        force=True,
    )

    result = run_rrc(
        'start',
        '--state-dir',
        str(state_dir),
        '--target',
        '1.2',
        '--dry-run',
        '--auto-approve',
    )

    assert result.returncode == 1
    assert 'Existing session does not match start arguments' in result.stderr
    assert '--target=1.2 but session requestedOutcome=1.1' in result.stderr
    assert 'Use --force to reinitialize' in result.stderr


def test_unit_plan_drafter_emits_test_strategist_start_progress(tmp_path: Path, monkeypatch) -> None:
    approvals_dir = tmp_path / 'approvals'
    artifacts_dir = tmp_path / 'artifacts'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Behavior works.\n', encoding='utf-8')
    state = _controller_state_for_unit_plan(workspace)

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': []}),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': []}),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    emitted: list[str] = []
    run_unit_plan_drafter(state, approvals_dir, artifacts_dir, progress_callback=emitted.append)

    assert any('Test Strategist' in msg or 'Codex' in msg or 'test strategist' in msg.lower() for msg in emitted), \
        f'Expected a startup message about Test Strategist but got: {emitted}'


def test_drive_threads_output_func_to_unit_plan_drafter(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_controller_state_for_unit_plan(workspace), force=True)
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text('# Requirements\n\n- AC-1: Behavior works.\n', encoding='utf-8')

    def fake_run_agent_backend(request):
        if request.role == 'test_strategist':
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': []}),
                encoding='utf-8',
            )
            (request.artifact_dir / 'unit-plan-gap-report.json').write_text(
                json.dumps({'gaps': []}),
                encoding='utf-8',
            )
        else:
            _write_valid_unit_plan(request.artifact_dir / 'unit-plan-body.md')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run_agent_backend)

    output: list[str] = []

    def quit_at_gate(_prompt: str) -> str:
        return 'q'

    controller.drive(max_steps=2, output_func=output.append, input_func=quit_at_gate, timestamp_output=False)

    assert any('Test Strategist' in msg or 'Codex' in msg or 'test strategist' in msg.lower() for msg in output), \
        f'Expected startup message in drive output but got: {output}'


# ---------------------------------------------------------------------------
# Codex self-patch tests (Option C)
# ---------------------------------------------------------------------------

def test_codex_patcher_fills_gaps_and_marks_patched_test_cases(tmp_path: Path, monkeypatch) -> None:
    """When the initial strategist leaves a gap, a second Codex run patches it
    and marks each added test_case with codex_patch=True."""
    from workflow_controller.steps.unit_plan import _run_test_strategist_if_enabled

    draft_dir = tmp_path / 'unit-plan-draft'
    draft_dir.mkdir()
    approvals_dir = tmp_path / 'approvals'
    approvals_dir.mkdir()
    (approvals_dir / 'requirements-and-acceptance.md').write_text('## 1. 需求\n- req\n', encoding='utf-8')
    (draft_dir / 'unit-plan-body.md').write_text('## AC\n- AC-1-1: do thing\n', encoding='utf-8')

    call_count = [0]

    def fake_run(request):
        call_count[0] += 1
        if call_count[0] == 1:
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': [{'id': 'AC-1-1', 'test_cases': []}]}),
                encoding='utf-8',
            )
        else:
            patched = {
                'acceptance_criteria': [
                    {'id': 'AC-1-1', 'test_cases': [
                        {'id': 'TC-1-1-a', 'layer': 'functional',
                         'command': 'pytest tests/', 'expected': 'pass',
                         'codex_patch': True},
                    ]}
                ]
            }
            (request.artifact_dir / 'test-strategy.json').write_text(json.dumps(patched), encoding='utf-8')
        return _fake_agent_result(request)

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run)

    state: dict = {'testStrategistEnabled': True, 'currentUnitId': 'u1'}
    _run_test_strategist_if_enabled(
        state=state,
        approvals_dir=approvals_dir,
        draft_dir=draft_dir,
        workspace_path=tmp_path,
    )

    assert call_count[0] == 2, f'patcher should run a second Codex pass when gaps exist, got {call_count[0]}'
    strategy = json.loads((draft_dir / 'test-strategy.json').read_text(encoding='utf-8'))
    tc = strategy['acceptance_criteria'][0]['test_cases'][0]
    assert tc.get('codex_patch') is True


def test_codex_patch_markers_appear_in_unit_plan_gate(tmp_path: Path) -> None:
    """Patched test cases are rendered in a dedicated section in the gate."""
    from workflow_controller.steps.unit_plan import _merge_review_package_into_unit_plan_gate

    draft_dir = tmp_path / 'unit-plan-draft'
    draft_dir.mkdir()

    patched_strategy = {
        'acceptance_criteria': [
            {'id': 'AC-1-1', 'test_cases': [
                {'id': 'TC-1-1-a', 'layer': 'functional',
                 'command': 'pytest tests/', 'expected': 'pass',
                 'codex_patch': True},
            ]}
        ]
    }
    (draft_dir / 'test-strategy.json').write_text(json.dumps(patched_strategy), encoding='utf-8')
    (draft_dir / 'unit-plan-gap-report.json').write_text(
        json.dumps({'gap_counts': {'critical': 0, 'major': 0, 'minor': 0}, 'gaps': []}),
        encoding='utf-8',
    )

    gate = _merge_review_package_into_unit_plan_gate(
        'Original body\n', draft_dir, retry_count=0
    )

    assert 'Codex' in gate
    assert 'TC-1-1-a' in gate
    assert 'AC-1-1' in gate


def test_patcher_failure_does_not_block_gate_creation(tmp_path: Path, monkeypatch) -> None:
    """If the patcher Codex run fails, the original test-strategy.json is kept
    and the strategist summary is returned without raising."""
    from workflow_controller.steps.unit_plan import _run_test_strategist_if_enabled

    draft_dir = tmp_path / 'unit-plan-draft'
    draft_dir.mkdir()
    approvals_dir = tmp_path / 'approvals'
    approvals_dir.mkdir()
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# req\n', encoding='utf-8')
    (draft_dir / 'unit-plan-body.md').write_text('body\n', encoding='utf-8')

    call_count = [0]

    def fake_run(request):
        call_count[0] += 1
        if call_count[0] == 1:
            (request.artifact_dir / 'test-strategy.json').write_text(
                json.dumps({'acceptance_criteria': [{'id': 'AC-1-1', 'test_cases': []}]}),
                encoding='utf-8',
            )
            return _fake_agent_result(request)
        return _fake_agent_result(request, status='failed', returncode=1, stderr='error')

    monkeypatch.setitem(run_unit_plan_drafter.__globals__, 'run_agent_backend', fake_run)

    state: dict = {'testStrategistEnabled': True, 'currentUnitId': 'u1'}
    summary = _run_test_strategist_if_enabled(
        state=state,
        approvals_dir=approvals_dir,
        draft_dir=draft_dir,
        workspace_path=tmp_path,
    )

    assert (draft_dir / 'test-strategy.json').exists()
    assert 'gap_counts' in summary


def test_patch_list_in_final_acceptance_gate_is_extracted_for_builder(tmp_path: Path) -> None:
    """When ## 修改清单 has items, finalAcceptanceRejectionFeedback contains only those items."""
    from workflow_controller.gates.parsers import write_gate_file
    from workflow_controller.gates.generators import normalize_final_acceptance_rejection_routing

    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(tmp_path / 'workspace')
    initial_state.update({
        'currentStep': 'WAITING_FINAL_ACCEPTANCE',
        'unitPlanDraftGenerated': True,
        'unitPlanAccepted': True,
        'scopeApproved': True,
        'units': [{'id': 'u1', 'passes': True}],
        'objectiveCoverage': [{'objective': 'obj1', 'status': 'covered', 'units': ['u1']}],
    })
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)

    gate_body = (
        '# 最终验收确认\n\n'
        '## 结果\n- 状态: active\n\n'
        '## 验收证据矩阵（Final Acceptance Evidence Matrix）\n\n'
        '| AO | AC | Test Case | Layer | Status | Evidence | Expected | Artifacts | Golden Path |\n'
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n'
        '| AO-001 | AC-1 | TC-AC1-GOLDEN | e2e | passed | `pytest tests/test_delivery.py -q` | delivery visible | verification.json | yes |\n\n'
        '## 修改清单\n\n'
        '- [ ] 登录按钮文字改为"立即登录"\n'
        '- [ ] 错误提示消失时间从 5s 改为 3s\n\n'
        '## 人工审阅清单\n- [ ] 实际结果满足已批准的验收标准。\n\n'
    )
    gate_body = normalize_final_acceptance_rejection_routing(
        gate_body, selected_route='implementation'
    )
    write_gate_file(approvals_dir / 'final-acceptance.md', gate_body)

    controller.reject_final_acceptance_gate()

    saved = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    feedback = saved['finalAcceptanceRejectionFeedback']
    assert '立即登录' in feedback
    assert '5s 改为 3s' in feedback
    assert '## 验收证据矩阵（Final Acceptance Evidence Matrix）' in feedback
    assert 'TC-AC1-GOLDEN' in feedback
    assert '## 结果' not in feedback, 'Full gate content should not be in feedback when patch list is present'
    assert '## 覆盖情况' not in feedback


def test_empty_patch_list_falls_back_to_full_gate_for_builder(tmp_path: Path) -> None:
    """When ## 修改清单 is present but empty, builder receives the full gate content."""
    from workflow_controller.gates.parsers import write_gate_file
    from workflow_controller.gates.generators import normalize_final_acceptance_rejection_routing

    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(tmp_path / 'workspace')
    initial_state.update({
        'currentStep': 'WAITING_FINAL_ACCEPTANCE',
        'unitPlanDraftGenerated': True,
        'unitPlanAccepted': True,
        'scopeApproved': True,
        'units': [{'id': 'u1', 'passes': True}],
        'objectiveCoverage': [{'objective': 'obj1', 'status': 'covered', 'units': ['u1']}],
    })
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)

    gate_body = (
        '# 最终验收确认\n\n'
        '## 结果\n- 状态: active\n\n'
        '## 修改清单\n\n'
        '<!-- 如需 Agent 做定点修改，请在此列出具体事项（每项一行）。\n'
        '     留空则 Agent 收到完整验收文档作为参考。-->\n\n'
        '## 人工审阅清单\n- [ ] 实际结果满足已批准的验收标准。\n\n'
    )
    gate_body = normalize_final_acceptance_rejection_routing(
        gate_body, selected_route='implementation'
    )
    write_gate_file(approvals_dir / 'final-acceptance.md', gate_body)

    controller.reject_final_acceptance_gate()

    saved = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    feedback = saved['finalAcceptanceRejectionFeedback']
    assert '# 最终验收确认' in feedback, 'Full gate should be used when patch list is empty'
    assert '留空则 Agent 收到完整验收文档作为参考' not in feedback


def test_final_acceptance_approval_blocks_missing_journey_evidence(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    journey_path = state_dir / 'artifacts' / 'journeys' / 'journeys.json'
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'journeyContractPath': str(journey_path),
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': True},
            ],
        },
        force=True,
    )
    journey_path.parent.mkdir(parents=True, exist_ok=True)
    journey_path.write_text(
        json.dumps(
            {
                'version': 1,
                'journeys': [
                    {
                        'journey_id': 'J-001',
                        'title': 'Delivery happy path',
                        'status': 'active',
                        'linked_acceptance_criteria': ['AC-1'],
                    }
                ],
            }
        ),
        encoding='utf-8',
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    from workflow_controller.gates.generators import ensure_final_acceptance_gate
    from workflow_controller.gates.parsers import approve_gate_file

    gate_path = ensure_final_acceptance_gate(
        controller.store.load_state(),
        approvals_dir,
        state_dir / 'artifacts',
        force=True,
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['finalAcceptanceAccepted'] is False
    assert state['currentStep'] == 'WAITING_FINAL_ACCEPTANCE'
    assert state['blockedReason'].startswith('final acceptance gate invalid:')
    assert 'J-001' in state['blockedReason']


def test_final_acceptance_approval_accepts_passed_journey_evidence(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    journey_path = state_dir / 'artifacts' / 'journeys' / 'journeys.json'
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'journeyContractPath': str(journey_path),
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery unit', 'passes': True},
            ],
        },
        force=True,
    )
    journey_path.parent.mkdir(parents=True, exist_ok=True)
    journey_path.write_text(
        json.dumps(
            {
                'version': 1,
                'journeys': [
                    {
                        'journey_id': 'J-001',
                        'title': 'Delivery happy path',
                        'status': 'active',
                        'linked_acceptance_criteria': ['AC-1'],
                    }
                ],
            }
        ),
        encoding='utf-8',
    )
    (journey_path.parent / 'journey-evidence.json').write_text(
        json.dumps(
            {
                'journey_evidence_rows': [
                    {
                        'journey_id': 'J-001',
                        'title': 'Delivery happy path',
                        'acceptance_criteria': ['AC-1'],
                        'unit_id': 'unit-01',
                        'test_case_id': 'TC-AC1-E2E',
                        'layer': 'e2e',
                        'command': 'pytest tests/e2e/test_delivery.py -q',
                        'status': 'passed',
                        'returncode': 0,
                        'expected': 'delivery confirmation is visible',
                        'artifact_refs': ['artifacts/unit-01/verification.json'],
                    }
                ],
            }
        ),
        encoding='utf-8',
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    from workflow_controller.gates.generators import ensure_final_acceptance_gate
    from workflow_controller.gates.parsers import approve_gate_file

    gate_path = ensure_final_acceptance_gate(
        controller.store.load_state(),
        approvals_dir,
        state_dir / 'artifacts',
        force=True,
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['finalAcceptanceAccepted'] is True
    assert state['currentStep'] == 'RELEASE_GATE'


def test_final_acceptance_approval_syncs_tmux_agent_before_release(tmp_path: Path, monkeypatch) -> None:
    import workflow_controller.steps.final_sync as final_sync_module

    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    for filename in ['AGENTS.md', 'ROADMAP.md', 'task_plan.md', 'progress.md', 'findings.md']:
        (workspace / filename).write_text(f'# {filename}\n', encoding='utf-8')
    state_dir = workspace / '.rrc-controller-v1.7'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'target-v1-7',
            'currentUnitId': 'v1-7-u1',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'V1.7',
            'feasibleOutcome': 'V1.7',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'workspacePath': str(workspace),
            'executionWorkspacePath': str(workspace),
            'agentRunner': 'tmux-codex',
            'agentCommand': 'codex',
            'tmuxTarget': '7.1',
            'targetContextFiles': [
                str(workspace / 'task_plan.md'),
                str(workspace / 'progress.md'),
                str(workspace / 'findings.md'),
            ],
            'objectiveCoverage': [
                {'objective': 'Target V1.7 acceptance', 'units': ['v1-7-u1'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'v1-7-u1', 'name': 'V1.7 delivery', 'passes': True},
            ],
        },
        force=True,
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    from workflow_controller.gates.generators import ensure_final_acceptance_gate
    from workflow_controller.gates.parsers import approve_gate_file

    gate_path = ensure_final_acceptance_gate(
        controller.store.load_state(),
        approvals_dir,
        state_dir / 'artifacts',
        force=True,
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['finalAcceptanceAccepted'] is True
    assert state['currentStep'] == 'FINAL_ACCEPTANCE_AGENT_SYNC'
    assert state['nextAllowedActions'] == ['sync_final_acceptance_agent']
    assert state['finalAcceptanceAgentSyncStatus'] == 'pending'

    captured: dict[str, Any] = {}

    def fake_run_agent_backend(request):
        captured['request'] = request
        captured['prompt'] = request.prompt_path.read_text(encoding='utf-8')
        (request.artifact_dir / 'final-sync-summary.json').write_text(
            json.dumps(
                {
                    'status': 'ok',
                    'updated_files': ['task_plan.md', 'progress.md', 'findings.md'],
                    'notes': ['marked V1.7 complete'],
                }
            ),
            encoding='utf-8',
        )
        return _fake_agent_result(request)

    monkeypatch.setattr(final_sync_module, 'run_agent_backend', fake_run_agent_backend)

    state = controller.run_once()

    assert state['currentStep'] == 'RELEASE_GATE'
    assert state['nextAllowedActions'] == ['require_release_approval']
    assert state['finalAcceptanceAgentSyncStatus'] == 'done'
    assert captured['request'].role == 'final_sync'
    assert captured['request'].backend == 'tmux-codex'
    assert 'Final acceptance has been approved' in captured['prompt']
    assert 'session.json' in captured['prompt']
    assert 'events.jsonl' in captured['prompt']
    assert 'task_plan.md' in captured['prompt']
    assert 'progress.md' in captured['prompt']
    assert 'findings.md' in captured['prompt']


def test_plannotator_final_acceptance_feedback_is_not_replaced_by_template_patch_comment(tmp_path: Path) -> None:
    from workflow_controller.gates.parsers import write_gate_file
    from workflow_controller.gates.generators import normalize_final_acceptance_rejection_routing

    state_dir = tmp_path / 'state'
    initial_state = _controller_state_for_unit_plan(tmp_path / 'workspace')
    initial_state.update({
        'currentStep': 'WAITING_FINAL_ACCEPTANCE',
        'unitPlanDraftGenerated': True,
        'unitPlanAccepted': True,
        'scopeApproved': True,
        'units': [{'id': 'u1', 'passes': True}],
        'objectiveCoverage': [{'objective': 'obj1', 'status': 'covered', 'units': ['u1']}],
    })
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(initial_state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    gate_path = approvals_dir / 'final-acceptance.md'

    gate_body = (
        '# 最终验收确认\n\n'
        '## 结果\n- 状态: active\n\n'
        '## 修改清单\n\n'
        '<!-- 如需 Agent 做定点修改，请在此列出具体事项（每项一行）。\n'
        '     留空则 Agent 收到完整验收文档作为参考。-->\n\n'
        '## 人工审阅清单\n- [ ] 实际结果满足已批准的验收标准。\n\n'
    )
    gate_body = normalize_final_acceptance_rejection_routing(
        gate_body, selected_route='implementation'
    )
    write_gate_file(gate_path, gate_body)

    plannotator_dir = state_dir / 'plannotator'
    plannotator_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = plannotator_dir / 'final-acceptance-last-review.stdout.log'
    stdout_path.write_text(
        json.dumps(
            {
                'decision': 'annotated',
                'feedback': '# File Feedback\n\n没有给上传材料的入口\n\n实现返工需要补齐上传入口。',
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    (plannotator_dir / 'final-acceptance-last-review.json').write_text(
        json.dumps(
            {
                'gate_path': str(gate_path),
                'approval_gate_path': str(gate_path),
                'stdout_path': str(stdout_path),
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )

    controller.reject_final_acceptance_gate()

    saved = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    feedback = saved['finalAcceptanceRejectionFeedback']
    assert '没有给上传材料的入口' in feedback
    assert '实现返工需要补齐上传入口' in feedback
    assert '留空则 Agent 收到完整验收文档作为参考' not in feedback
