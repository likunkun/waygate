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
    assert 'PATH shadow' in result.stdout
