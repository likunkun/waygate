from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from workflow_controller import __version__
from workflow_controller.diagnostics import render_doctor_report


ANSI_PATTERN = re.compile(r'\x1b\[[0-9;]*m')


def _executable(path: Path) -> None:
    path.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    path.chmod(0o755)


def _strip_ansi(text: str) -> str:
    return ANSI_PATTERN.sub('', text)


def _install_recommended_skill_set(root: Path) -> None:
    installed = {
        '.agents/skills/planning-with-files/SKILL.md': 'planning-with-files',
        '.codex/superpowers/skills/using-superpowers/SKILL.md': 'using-superpowers',
        '.codex/superpowers/skills/brainstorming/SKILL.md': 'superpowers:brainstorming',
        '.codex/superpowers/skills/writing-plans/SKILL.md': 'superpowers:writing-plans',
        '.codex/superpowers/skills/test-driven-development/SKILL.md': 'superpowers:test-driven-development',
        '.codex/superpowers/skills/systematic-debugging/SKILL.md': 'superpowers:systematic-debugging',
        '.agents/skills/testing-strategy/SKILL.md': 'testing-strategy',
        '.agents/skills/code-simplifier/SKILL.md': 'code-simplifier',
        '.codex/superpowers/skills/verification-before-completion/SKILL.md': 'superpowers:verification-before-completion',
        '.codex/superpowers/skills/requesting-code-review/SKILL.md': 'superpowers:requesting-code-review',
        '.codex/superpowers/skills/executing-plans/SKILL.md': 'superpowers:executing-plans',
        '.agents/skills/webapp-testing/SKILL.md': 'webapp-testing',
        '.agents/skills/ui-ux-pro-max/SKILL.md': 'ui-ux-pro-max',
    }
    for relative_path, skill_name in installed.items():
        skill_path = root / relative_path
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(f'---\nname: {skill_name}\n---\n# {skill_name}\n', encoding='utf-8')


def _doctor_env_with_all_tools(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for command in ['pytest', 'tmux', 'claude', 'codex', 'plannotator', 'dpkg-deb']:
        _executable(bin_dir / command)
    _install_recommended_skill_set(tmp_path)
    return {
        'PATH': str(bin_dir),
        'HOME': str(tmp_path),
        'TMUX': '/tmp/tmux-1000/default,1,0',
    }


def test_doctor_reports_runtime_version_and_path_candidates(tmp_path: Path) -> None:
    local_bin = tmp_path / 'home/user/.local/bin'
    usr_bin = tmp_path / 'usr/bin'
    local_bin.mkdir(parents=True)
    usr_bin.mkdir(parents=True)
    _executable(local_bin / 'waygate')
    _executable(usr_bin / 'waygate')
    env = {
        'PATH': os.pathsep.join([str(local_bin), str(usr_bin)]),
        'HOME': str(tmp_path / 'home/user'),
    }

    report = render_doctor_report(
        env=env,
        argv0=str(local_bin / 'waygate'),
        module_file=str(tmp_path / 'usr/lib/waygate/workflow_controller/__init__.py'),
        dpkg_version_provider=lambda: __version__,
    )

    assert f'module_version: {__version__}' in report
    assert 'module_path: ' + str(tmp_path / 'usr/lib/waygate/workflow_controller/__init__.py') in report
    assert 'dpkg_version: ' + __version__ in report
    assert 'path_candidates:' in report
    assert '- ' + str(local_bin / 'waygate') in report
    assert '- ' + str(usr_bin / 'waygate') in report
    assert 'PATH shadow' in report
    assert '.local/bin/waygate' in report


def test_doctor_reports_environment_checks(tmp_path: Path) -> None:
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for command in ['pytest', 'tmux', 'claude', 'codex', 'plannotator', 'dpkg-deb']:
        _executable(bin_dir / command)

    report = render_doctor_report(
        env={
            'PATH': str(bin_dir),
            'HOME': str(tmp_path),
            'TMUX': '/tmp/tmux-1000/default,1,0',
        },
        argv0='waygate',
        module_file=str(tmp_path / 'usr/lib/waygate/workflow_controller/__init__.py'),
        dpkg_version_provider=lambda: '0.6.0e',
    )

    assert 'environment_checks:' in report
    assert '- python: status=ok' in report
    assert 'executable=' in report
    assert 'version=' in report
    assert '- pytest: status=ok' in report
    assert '- tmux: status=ok' in report
    assert '- tmux_session: status=ok' in report
    assert '- Claude Code: status=ok' in report
    assert '- Codex: status=ok' in report
    assert '- Plannotator: status=ok' in report
    assert '- dpkg-deb: status=ok' in report
    assert '- recommended_plannotator_port: 20000' in report


def test_doctor_reports_skill_checks_and_recommended_gaps(tmp_path: Path) -> None:
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for command in ['pytest', 'tmux', 'dpkg-deb']:
        _executable(bin_dir / command)

    for relative_path, skill_name in [
        ('.agents/skills/code-simplifier/SKILL.md', 'code-simplifier'),
        ('.agents/skills/ui-ux-pro-max/SKILL.md', 'ui-ux-pro-max'),
        ('.codex/skills/test-strategy/SKILL.md', 'test-strategy'),
        ('.codex/superpowers/skills/test-driven-development/SKILL.md', 'test-driven-development'),
        ('.config/opencode/skills/unit-loop-orchestrator/SKILL.md', 'unit-loop-orchestrator'),
    ]:
        skill_path = tmp_path / relative_path
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(f'---\nname: {skill_name}\n---\n# {skill_name}\n', encoding='utf-8')

    report = render_doctor_report(
        env={'PATH': str(bin_dir), 'HOME': str(tmp_path)},
        argv0='waygate',
        module_file=str(tmp_path / 'usr/lib/waygate/workflow_controller/__init__.py'),
        dpkg_version_provider=lambda: '0.6.0e',
    )

    assert 'skill_roots:' in report
    assert str(tmp_path / '.agents/skills') in report
    assert str(tmp_path / '.codex/skills') in report
    assert str(tmp_path / '.codex/superpowers/skills') in report
    assert str(tmp_path / '.config/opencode/skills') in report
    assert 'installed_skills:' in report
    assert '- code-simplifier: status=ok path=' in report
    assert '- test-strategy: status=ok path=' in report
    assert '- test-driven-development: status=ok path=' in report
    assert '- ui-ux-pro-max: status=ok path=' in report
    assert '- unit-loop-orchestrator: status=ok path=' in report
    assert 'skill_recommendations:' in report
    assert '- builder_tdd: status=ok matched=test-driven-development' in report
    assert '- test_strategy: status=ok matched=test-strategy' in report
    assert '- ui_ux_design: status=ok matched=ui-ux-pro-max' in report
    assert '- verification: status=warning missing=verification-before-completion' in report


def test_doctor_warns_when_only_frontend_design_is_installed_for_ui_ux(tmp_path: Path) -> None:
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for command in ['pytest', 'tmux', 'dpkg-deb']:
        _executable(bin_dir / command)
    skill_path = tmp_path / '.agents/skills/frontend-design/SKILL.md'
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text('---\nname: frontend-design\n---\n# frontend-design\n', encoding='utf-8')

    report = render_doctor_report(
        env={'PATH': str(bin_dir), 'HOME': str(tmp_path)},
        argv0='waygate',
        module_file=str(tmp_path / 'usr/lib/waygate/workflow_controller/__init__.py'),
        dpkg_version_provider=lambda: __version__,
    )

    assert '- frontend-design: status=ok path=' in report
    assert '- ui_ux_design: status=warning missing=ui-ux-pro-max' in report
    assert 'Install ui-ux-pro-max for UI/Web/prototype production consistency work.' in report
    assert 'matched=frontend-design' not in report
    assert 'skill_recommendations.ui_ux_design' in report


def test_doctor_prefers_ui_ux_pro_max_when_frontend_design_is_also_installed(tmp_path: Path) -> None:
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for command in ['pytest', 'tmux', 'dpkg-deb']:
        _executable(bin_dir / command)
    for skill_name in ['frontend-design', 'ui-ux-pro-max']:
        skill_path = tmp_path / f'.agents/skills/{skill_name}/SKILL.md'
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(f'---\nname: {skill_name}\n---\n# {skill_name}\n', encoding='utf-8')

    report = render_doctor_report(
        env={'PATH': str(bin_dir), 'HOME': str(tmp_path)},
        argv0='waygate',
        module_file=str(tmp_path / 'usr/lib/waygate/workflow_controller/__init__.py'),
        dpkg_version_provider=lambda: __version__,
    )

    assert '- frontend-design: status=ok path=' in report
    assert '- ui-ux-pro-max: status=ok path=' in report
    assert '- ui_ux_design: status=ok matched=ui-ux-pro-max' in report
    assert 'matched=frontend-design' not in report


def test_doctor_reports_ok_tmux_config_and_summary_first(tmp_path: Path) -> None:
    (tmp_path / '.tmux.conf').write_text(
        '\n'.join(
            [
                '# recommended Waygate tmux settings',
                'set -g mouse off',
                'set -g mouse on',
                'set-option -g history-limit 100000',
                'set -g @scroll-speed 5',
                "set -g @copy-mode-vi 'on'",
                'set -g @private-token super-secret-value',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    report = render_doctor_report(
        env=_doctor_env_with_all_tools(tmp_path),
        argv0='waygate',
        module_file=str(tmp_path / 'usr/lib/waygate/workflow_controller/__init__.py'),
        dpkg_version_provider=lambda: __version__,
    )

    assert report.startswith('Waygate doctor\nsummary:\n')
    assert '- overall: status=ok warnings=0 manual_actions=0' in report
    assert f'- version: module={__version__} dpkg={__version__}' in report
    assert 'action_required:\n- none\nexecutable_path:' in report
    assert report.index('summary:') < report.index('executable_path:')
    assert report.index('action_required:') < report.index('environment_checks:')
    assert 'tmux_config:' in report
    assert f'- {tmp_path / ".tmux.conf"}: status=found' in report
    assert '- mouse: status=ok expected=on actual=on' in report
    assert '- history-limit: status=ok expected=100000 actual=100000' in report
    assert '- @scroll-speed: status=ok expected=5 actual=5' in report
    assert '- @copy-mode-vi: status=ok expected=on actual=on' in report
    assert 'super-secret-value' not in report
    assert '@private-token' not in report


def test_doctor_warns_when_tmux_config_is_missing_and_promotes_actions(tmp_path: Path) -> None:
    report = render_doctor_report(
        env=_doctor_env_with_all_tools(tmp_path),
        argv0='waygate',
        module_file=str(tmp_path / 'usr/lib/waygate/workflow_controller/__init__.py'),
        dpkg_version_provider=lambda: __version__,
    )

    assert '- overall: status=warning warnings=4 manual_actions=4' in report
    assert 'action_required:' in report
    assert '- tmux_config.mouse: Add `set -g mouse on` to ~/.tmux.conf and reload tmux config.' in report
    assert '- tmux_config.history-limit: Add `set -g history-limit 100000` to ~/.tmux.conf and reload tmux config.' in report
    assert '- tmux_config.@scroll-speed: Add `set -g @scroll-speed 5` to ~/.tmux.conf and reload tmux config.' in report
    assert "- tmux_config.@copy-mode-vi: Add `set -g @copy-mode-vi 'on'` to ~/.tmux.conf and reload tmux config." in report
    assert report.index('action_required:') < report.index('executable_path:')
    assert report.index('environment_checks:') < report.rindex('tmux_config:')
    assert 'tmux_config:' in report
    assert f'- {tmp_path / ".tmux.conf"}: status=missing' in report
    assert '- mouse: status=warning expected=on actual=missing manual_action=Add `set -g mouse on` to ~/.tmux.conf and reload tmux config.' in report
    assert '- history-limit: status=warning expected=100000 actual=missing manual_action=Add `set -g history-limit 100000` to ~/.tmux.conf and reload tmux config.' in report
    assert '- @scroll-speed: status=warning expected=5 actual=missing manual_action=Add `set -g @scroll-speed 5` to ~/.tmux.conf and reload tmux config.' in report
    assert "- @copy-mode-vi: status=warning expected=on actual=missing manual_action=Add `set -g @copy-mode-vi 'on'` to ~/.tmux.conf and reload tmux config." in report


def test_doctor_color_output_highlights_focus_and_actions(tmp_path: Path) -> None:
    report = render_doctor_report(
        env=_doctor_env_with_all_tools(tmp_path),
        argv0='waygate',
        module_file=str(tmp_path / 'usr/lib/waygate/workflow_controller/__init__.py'),
        dpkg_version_provider=lambda: __version__,
        color_mode='always',
    )
    plain = _strip_ansi(report)

    assert '\x1b[' in report
    assert '\x1b[1;36mfocus:\x1b[0m' in report
    assert '\x1b[33mstatus=warning\x1b[0m' in report
    assert '\x1b[1;33m[P1]\x1b[0m' in report
    assert plain.startswith('Waygate doctor\nsummary:\n')
    assert 'focus:\n- [P1] tmux_config: 4 warning(s); update ~/.tmux.conf and reload tmux config.' in plain
    assert plain.index('summary:') < plain.index('focus:') < plain.index('action_required:') < plain.index('executable_path:')
    assert '- tmux_config.mouse: Add `set -g mouse on` to ~/.tmux.conf and reload tmux config.' in plain


def test_doctor_reports_tmux_config_mismatches_without_leaking_unrelated_lines(tmp_path: Path) -> None:
    (tmp_path / '.tmux.conf').write_text(
        '\n'.join(
            [
                'set -g mouse off',
                'set-option -g history-limit 2000',
                "set -g @copy-mode-vi 'off'",
                'set -g @private-token super-secret-value',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    report = render_doctor_report(
        env=_doctor_env_with_all_tools(tmp_path),
        argv0='waygate',
        module_file=str(tmp_path / 'usr/lib/waygate/workflow_controller/__init__.py'),
        dpkg_version_provider=lambda: __version__,
    )

    assert '- overall: status=warning warnings=4 manual_actions=4' in report
    assert '- mouse: status=warning expected=on actual=off manual_action=Add `set -g mouse on` to ~/.tmux.conf and reload tmux config.' in report
    assert '- history-limit: status=warning expected=100000 actual=2000 manual_action=Add `set -g history-limit 100000` to ~/.tmux.conf and reload tmux config.' in report
    assert '- @scroll-speed: status=warning expected=5 actual=missing manual_action=Add `set -g @scroll-speed 5` to ~/.tmux.conf and reload tmux config.' in report
    assert "- @copy-mode-vi: status=warning expected=on actual=off manual_action=Add `set -g @copy-mode-vi 'on'` to ~/.tmux.conf and reload tmux config." in report
    assert 'super-secret-value' not in report
    assert '@private-token' not in report


def test_doctor_recommendations_cover_readme_baseline_skill_groups(tmp_path: Path) -> None:
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for command in ['pytest', 'tmux', 'dpkg-deb']:
        _executable(bin_dir / command)

    installed = {
        '.agents/skills/planning-with-files/SKILL.md': 'planning-with-files',
        '.codex/superpowers/skills/using-superpowers/SKILL.md': 'using-superpowers',
        '.codex/superpowers/skills/brainstorming/SKILL.md': 'superpowers:brainstorming',
        '.codex/superpowers/skills/writing-plans/SKILL.md': 'superpowers:writing-plans',
        '.codex/superpowers/skills/test-driven-development/SKILL.md': 'superpowers:test-driven-development',
        '.codex/superpowers/skills/systematic-debugging/SKILL.md': 'superpowers:systematic-debugging',
        '.agents/skills/testing-strategy/SKILL.md': 'testing-strategy',
        '.agents/skills/code-simplifier/SKILL.md': 'code-simplifier',
        '.codex/superpowers/skills/verification-before-completion/SKILL.md': 'superpowers:verification-before-completion',
        '.codex/superpowers/skills/requesting-code-review/SKILL.md': 'superpowers:requesting-code-review',
        '.codex/superpowers/skills/executing-plans/SKILL.md': 'superpowers:executing-plans',
        '.agents/skills/webapp-testing/SKILL.md': 'webapp-testing',
        '.agents/skills/ui-ux-pro-max/SKILL.md': 'ui-ux-pro-max',
    }
    for relative_path, skill_name in installed.items():
        skill_path = tmp_path / relative_path
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(f'---\nname: {skill_name}\n---\n# {skill_name}\n', encoding='utf-8')

    report = render_doctor_report(
        env={'PATH': str(bin_dir), 'HOME': str(tmp_path)},
        argv0='waygate',
        module_file=str(tmp_path / 'usr/lib/waygate/workflow_controller/__init__.py'),
        dpkg_version_provider=lambda: __version__,
    )

    expected_groups = [
        'startup',
        'planning',
        'requirements',
        'builder_tdd',
        'debugging',
        'test_strategy',
        'refiner',
        'verification',
        'code_review',
        'plan_execution',
        'webapp_testing',
        'ui_ux_design',
    ]
    for group in expected_groups:
        assert f'- {group}: status=ok matched=' in report
    assert 'status=warning missing=' not in report


def test_doctor_reports_claude_assets_without_reading_secrets_or_history(tmp_path: Path) -> None:
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for command in ['pytest', 'tmux', 'dpkg-deb']:
        _executable(bin_dir / command)
    claude_dir = tmp_path / '.claude'
    for name, count in [('commands', 2), ('agents', 1), ('plugins', 3)]:
        directory = claude_dir / name
        directory.mkdir(parents=True)
        for index in range(count):
            (directory / f'asset-{index}.md').write_text(f'# {name} {index}\nTOKEN=secret-{index}\n', encoding='utf-8')
    (claude_dir / 'cache').mkdir()
    (claude_dir / 'cache' / 'token-cache.json').write_text('super-secret-cache-token\n', encoding='utf-8')
    (claude_dir / 'file-history').write_text('/private/project/secret-file.ts\n', encoding='utf-8')

    report = render_doctor_report(
        env={
            'PATH': str(bin_dir),
            'HOME': str(tmp_path),
            'TOKEN': 'super-secret-env-token',
        },
        argv0='waygate',
        module_file=str(tmp_path / 'usr/lib/waygate/workflow_controller/__init__.py'),
        dpkg_version_provider=lambda: __version__,
    )

    assert 'claude_assets:' in report
    assert f'- {claude_dir / "commands"}: status=found count=2' in report
    assert f'- {claude_dir / "agents"}: status=found count=1' in report
    assert f'- {claude_dir / "rules"}: status=missing count=0' in report
    assert f'- {claude_dir / "plugins"}: status=found count=3' in report
    assert 'super-secret-cache-token' not in report
    assert 'super-secret-env-token' not in report
    assert 'secret-file.ts' not in report
    assert 'file-history' not in report
    assert 'cache' not in report


def test_doctor_ignores_local_gui_app_entries(tmp_path: Path) -> None:
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for command in ['pytest', 'tmux', 'dpkg-deb']:
        _executable(bin_dir / command)
    applications_dir = tmp_path / '.local/share/applications'
    applications_dir.mkdir(parents=True)
    entry_extension = ''.join(['desk', 'top'])
    app_entry = applications_dir / f'claude-code.{entry_extension}'
    app_entry.write_text(
        '[Application Entry]\nName=Claude Visual\nExec=/opt/Claude/visual\n',
        encoding='utf-8',
    )

    report = render_doctor_report(
        env={'PATH': str(bin_dir), 'HOME': str(tmp_path), 'XDG_DATA_HOME': str(tmp_path / '.local/share')},
        argv0='waygate',
        module_file=str(tmp_path / 'usr/lib/waygate/workflow_controller/__init__.py'),
        dpkg_version_provider=lambda: '0.6.0e',
    )

    assert '- Claude Code: status=warning path=missing manual_action=' in report
    assert '- Codex: status=warning path=missing manual_action=' in report
    assert str(app_entry) not in report


def test_doctor_warns_for_missing_optional_agent_tools_without_secret_values(tmp_path: Path) -> None:
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for command in ['pytest', 'tmux', 'dpkg-deb']:
        _executable(bin_dir / command)
    env = {
        'PATH': str(bin_dir),
        'HOME': str(tmp_path),
        'DATABASE_URL': 'postgres://secret-user:secret-pass@localhost/db',
        'TOKEN': 'super-secret-token',
        'SECRET_KEY': 'super-secret-key',
    }

    report = render_doctor_report(
        env=env,
        argv0='waygate',
        module_file=str(tmp_path / 'usr/lib/waygate/workflow_controller/__init__.py'),
        dpkg_version_provider=lambda: '0.6.0e',
    )

    assert '- Claude Code: status=warning path=missing manual_action=' in report
    assert '- Codex: status=warning path=missing manual_action=' in report
    assert '- Plannotator: status=warning path=missing manual_action=' in report
    assert 'postgres://secret-user:secret-pass@localhost/db' not in report
    assert 'super-secret-token' not in report
    assert 'super-secret-key' not in report
    assert '.rrc-controller-v0.6.0e/artifacts' not in report


def test_doctor_warns_when_dpkg_version_differs_from_module_version(tmp_path: Path) -> None:
    bin_dir = tmp_path / 'usr/bin'
    bin_dir.mkdir(parents=True)
    _executable(bin_dir / 'waygate')

    report = render_doctor_report(
        env={'PATH': str(bin_dir), 'HOME': str(tmp_path)},
        argv0=str(bin_dir / 'waygate'),
        module_file=str(tmp_path / 'usr/lib/waygate/workflow_controller/__init__.py'),
        dpkg_version_provider=lambda: '0.0.0-old',
    )

    assert f'module_version: {__version__}' in report
    assert 'dpkg_version: 0.0.0-old' in report
    assert 'version mismatch' in report


def test_cli_doctor_command_prints_report(tmp_path: Path) -> None:
    local_bin = tmp_path / 'home/user/.local/bin'
    usr_bin = tmp_path / 'usr/bin'
    local_bin.mkdir(parents=True)
    usr_bin.mkdir(parents=True)
    _executable(local_bin / 'waygate')
    _executable(usr_bin / 'waygate')
    env = os.environ.copy()
    env['PATH'] = os.pathsep.join([str(local_bin), str(usr_bin), env.get('PATH', '')])
    env['HOME'] = str(tmp_path / 'home/user')

    result = subprocess.run(
        [sys.executable, '-m', 'workflow_controller.cli', 'doctor'],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0
    assert 'Waygate doctor' in result.stdout
    assert 'module_version: ' + __version__ in result.stdout
    assert 'environment_checks:' in result.stdout
    assert 'PATH shadow' in result.stdout


def test_cli_doctor_color_always_prints_ansi_report(tmp_path: Path) -> None:
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for command in ['pytest', 'tmux', 'dpkg-deb']:
        _executable(bin_dir / command)
    env = os.environ.copy()
    env['PATH'] = os.pathsep.join([str(bin_dir), env.get('PATH', '')])
    env['HOME'] = str(tmp_path)

    result = subprocess.run(
        [sys.executable, '-m', 'workflow_controller.cli', 'doctor', '--color', 'always'],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0
    assert '\x1b[' in result.stdout
    assert 'focus:' in _strip_ansi(result.stdout)
    assert '[P1]' in _strip_ansi(result.stdout)
