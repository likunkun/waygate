from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from workflow_controller import __version__
from workflow_controller.diagnostics import render_doctor_report


def _executable(path: Path) -> None:
    path.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    path.chmod(0o755)


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
    assert '- unit-loop-orchestrator: status=ok path=' in report
    assert 'skill_recommendations:' in report
    assert '- builder_tdd: status=ok matched=test-driven-development' in report
    assert '- test_strategy: status=ok matched=test-strategy' in report
    assert '- verification: status=warning missing=verification-before-completion' in report


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
