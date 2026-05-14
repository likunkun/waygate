from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from workflow_controller import __version__

ROOT = Path(__file__).resolve().parents[2]


def test_version_flag_outputs_package_version() -> None:
    result = subprocess.run(
        ['python', '-m', 'workflow_controller.cli', '--version'],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert f'waygate {__version__}' in result.stdout


def test_build_deb_creates_waygate_package(tmp_path: Path) -> None:
    if shutil.which('dpkg-deb') is None:
        pytest.skip('dpkg-deb is required to build Debian packages')

    script = ROOT / 'packaging' / 'debian' / 'build-deb.sh'
    env = os.environ.copy()
    env['WAYGATE_DIST_DIR'] = str(tmp_path / 'dist')
    env['WAYGATE_BUILD_ROOT'] = str(tmp_path / 'build')

    result = subprocess.run(
        ['bash', str(script)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    deb_path = tmp_path / 'dist' / f'waygate_{__version__}_all.deb'
    assert deb_path.exists()

    package_name = subprocess.run(
        ['dpkg-deb', '--field', str(deb_path), 'Package'],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    version = subprocess.run(
        ['dpkg-deb', '--field', str(deb_path), 'Version'],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    contents = subprocess.run(
        ['dpkg-deb', '--contents', str(deb_path)],
        text=True,
        capture_output=True,
        check=True,
    ).stdout

    assert package_name == 'waygate'
    assert version == __version__
    assert './usr/bin/waygate' in contents
    assert './usr/lib/waygate/workflow_controller/cli.py' in contents
    assert './usr/share/doc/waygate/README.md' in contents
    assert './usr/share/doc/waygate/README.zh-CN.md' in contents
    assert './usr/share/doc/waygate/USAGE.md' in contents
    assert './usr/share/doc/waygate/USAGE.zh-CN.md' in contents
    assert './usr/share/doc/waygate/ROADMAP.md' in contents
    assert './usr/share/doc/waygate/ROADMAP.zh-CN.md' in contents
    assert './usr/share/doc/waygate/docs/architecture.md' in contents
    assert './usr/share/doc/waygate/docs/workflow.zh-CN.md' in contents

    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    readme_zh = (ROOT / 'README.zh-CN.md').read_text(encoding='utf-8')
    required_english = [
        'Python 3',
        'pytest',
        'tmux',
        'Claude Code',
        'Codex',
        'Plannotator',
        'skills',
        'dpkg-deb',
        'Waygate Markdown spec',
    ]
    for expected in required_english:
        assert expected in readme
    for expected in ['Python 3', 'pytest', 'tmux', 'Claude Code', 'Codex', 'Plannotator', 'skills', 'dpkg-deb', 'Waygate Markdown spec']:
        assert expected in readme_zh
