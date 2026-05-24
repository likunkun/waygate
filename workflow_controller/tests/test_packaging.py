from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from workflow_controller import __version__

ROOT = Path(__file__).resolve().parents[2]


def _timestamped_version_line_re() -> str:
    return rf'^\[\d{{2}}:\d{{2}}:\d{{2}}\] {re.escape(f"waygate {__version__}")}$'


def test_version_flag_outputs_package_version() -> None:
    assert __version__ == '0.6.1'
    result = subprocess.run(
        [sys.executable, '-m', 'workflow_controller.cli', '--version'],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert f'waygate {__version__}' in result.stdout


def test_cli_start_prints_runtime_version(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            '-m',
            'workflow_controller.cli',
            'start',
            '--state-dir',
            str(tmp_path / 'state'),
            '--dry-run',
            '--max-steps',
            '0',
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert re.match(_timestamped_version_line_re(), result.stdout.splitlines()[0])


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
    extract_dir = tmp_path / 'extract'
    subprocess.run(
        ['dpkg-deb', '-x', str(deb_path), str(extract_dir)],
        text=True,
        capture_output=True,
        check=True,
    )
    unpacked_version = subprocess.run(
        [str(extract_dir / 'usr/bin/waygate'), '--version'],
        cwd=tmp_path,
        env={**env, 'WAYGATE_LIB_DIR': str(extract_dir / 'usr/lib/waygate')},
        text=True,
        capture_output=True,
        check=False,
    )
    unpacked_start = subprocess.run(
        [
            str(extract_dir / 'usr/bin/waygate'),
            'start',
            '--state-dir',
            str(tmp_path / 'pkg-state'),
            '--dry-run',
            '--max-steps',
            '0',
        ],
        cwd=tmp_path,
        env={**env, 'WAYGATE_LIB_DIR': str(extract_dir / 'usr/lib/waygate')},
        text=True,
        capture_output=True,
        check=False,
    )
    unpacked_retry_help = subprocess.run(
        [str(extract_dir / 'usr/bin/waygate'), 'retry', '--help'],
        cwd=tmp_path,
        env={**env, 'WAYGATE_LIB_DIR': str(extract_dir / 'usr/lib/waygate')},
        text=True,
        capture_output=True,
        check=False,
    )
    control_dir = tmp_path / 'control'
    subprocess.run(
        ['dpkg-deb', '-e', str(deb_path), str(control_dir)],
        text=True,
        capture_output=True,
        check=True,
    )
    postinst = (control_dir / 'postinst').read_text(encoding='utf-8')

    assert package_name == 'waygate'
    assert version == __version__
    assert unpacked_version.returncode == 0, unpacked_version.stderr + unpacked_version.stdout
    assert unpacked_version.stdout.strip() == f'waygate {__version__}'
    assert unpacked_start.returncode == 0, unpacked_start.stderr + unpacked_start.stdout
    assert re.match(_timestamped_version_line_re(), unpacked_start.stdout.splitlines()[0])
    assert unpacked_retry_help.returncode == 0, unpacked_retry_help.stderr + unpacked_retry_help.stdout
    assert 'usage: waygate retry' in unpacked_retry_help.stdout
    assert '--state-dir' in unpacked_retry_help.stdout
    assert './usr/bin/waygate' in contents
    assert './usr/lib/waygate/workflow_controller/cli.py' in contents
    assert './usr/share/doc/waygate/README.md' in contents
    assert './usr/share/doc/waygate/README.zh-CN.md' in contents
    assert './usr/share/doc/waygate/USAGE.md' in contents
    assert './usr/share/doc/waygate/USAGE.zh-CN.md' in contents
    assert './usr/share/doc/waygate/ROADMAP.md' in contents
    assert './usr/share/doc/waygate/ROADMAP.zh-CN.md' in contents
    assert './usr/share/doc/waygate/docs/architecture.md' in contents
    assert './usr/share/doc/waygate/docs/architecture/external-spec-intake-and-annotation-architecture.md' in contents
    assert './usr/share/doc/waygate/docs/README.md' in contents
    assert './usr/share/doc/waygate/docs/workflow.zh-CN.md' in contents
    assert './usr/share/doc/waygate/docs/workflow/external-spec-intake-and-annotation-policy.md' in contents
    assert './usr/share/doc/waygate/docs/workflow/prototype-fidelity-policy.md' in contents
    assert './usr/share/doc/waygate/docs/workflow/ui-ux-skill-policy.md' in contents
    assert './usr/share/doc/waygate/docs/product/waygate-introduction-and-best-practices.md' in contents
    assert './usr/share/doc/waygate/docs/product/waygate-introduction-and-best-practices.zh-CN.md' in contents
    assert './usr/share/doc/waygate/docs/operations/recommended-environment.md' in contents
    assert './usr/share/doc/waygate/docs/operations/recommended-environment.zh-CN.md' in contents
    assert '.local/bin/waygate' in postinst
    assert 'WARNING' in postinst
    assert 'rm -f' not in postinst

    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    readme_zh = (ROOT / 'README.zh-CN.md').read_text(encoding='utf-8')
    usage = (ROOT / 'USAGE.md').read_text(encoding='utf-8')
    usage_zh = (ROOT / 'USAGE.zh-CN.md').read_text(encoding='utf-8')
    roadmap = (ROOT / 'ROADMAP.md').read_text(encoding='utf-8')
    roadmap_zh = (ROOT / 'ROADMAP.zh-CN.md').read_text(encoding='utf-8')
    changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    changelog_zh = (ROOT / 'CHANGELOG.zh-CN.md').read_text(encoding='utf-8')
    recommended_env = (ROOT / 'docs/operations/recommended-environment.md').read_text(encoding='utf-8')
    recommended_env_zh = (ROOT / 'docs/operations/recommended-environment.zh-CN.md').read_text(encoding='utf-8')
    product_intro = (ROOT / 'docs/product/waygate-introduction-and-best-practices.md').read_text(encoding='utf-8')
    product_intro_zh = (ROOT / 'docs/product/waygate-introduction-and-best-practices.zh-CN.md').read_text(encoding='utf-8')
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
    for doc in [readme, readme_zh, usage, usage_zh, roadmap, roadmap_zh, changelog, changelog_zh]:
        assert 'V0.6.1' in doc or '0.6.1' in doc
        assert 'recommended-environment' in doc or '推荐环境' in doc
        assert 'doctor' in doc or '环境检测' in doc or '介绍' in doc

    packaged_docs = '\n'.join(
        [readme, readme_zh, usage, usage_zh, roadmap, roadmap_zh, changelog, changelog_zh, recommended_env, recommended_env_zh]
    )
    for expected in [
        '.tmux.conf',
        'mouse on',
        'history-limit 100000',
        '@scroll-speed 5',
        '@copy-mode-vi',
        'tmux_config',
        'summary:',
        'focus:',
        'action_required',
        '--color',
        '0.6.1',
    ]:
        assert expected in packaged_docs

    for doc in [recommended_env, recommended_env_zh]:
        assert 'Python 3.11' in doc
        assert 'Python 3.12' in doc
        assert 'Python 3.10' in doc
        assert 'python3 -m pytest workflow_controller/tests -q' in doc
        assert 'tmux-claude' in doc
        assert 'tmux-codex' in doc
        assert '20000' in doc
        assert 'skills' in doc or 'skill' in doc
        assert 'ui-ux-pro-max' in doc
        assert 'frontend-design' in doc
        assert 'cannot replace' in doc or '不能替代' in doc
        assert 'claude_assets' in doc
        assert 'PATH shadow' in doc

    ui_policy = (ROOT / 'docs/workflow/ui-ux-skill-policy.md').read_text(encoding='utf-8')
    assert '0.6.0k' in ui_policy
    assert 'ui-ux-pro-max' in ui_policy
    assert 'frontend-design' in ui_policy
    assert '不能替代' in ui_policy or 'cannot replace' in ui_policy

    for doc in [product_intro, product_intro_zh]:
        assert 'Requirements' in doc
        assert 'Unit Plan' in doc
        assert 'Builder' in doc
        assert 'Refiner' in doc
        assert 'Reviewer' in doc
        assert 'Verifier' in doc
        assert 'Final Acceptance' in doc
        assert 'session.json' in doc
        assert 'events.jsonl' in doc
        assert 'approvals/' in doc
        assert 'artifacts/' in doc
        assert 'PPT' in doc


def test_build_deb_rejects_control_version_mismatch(tmp_path: Path) -> None:
    if shutil.which('dpkg-deb') is None:
        pytest.skip('dpkg-deb is required to build Debian packages')

    script = ROOT / 'packaging' / 'debian' / 'build-deb.sh'
    env = os.environ.copy()
    env['WAYGATE_DIST_DIR'] = str(tmp_path / 'dist')
    env['WAYGATE_BUILD_ROOT'] = str(tmp_path / 'build')
    env['WAYGATE_VERSION'] = '9.9.9'

    result = subprocess.run(
        ['bash', str(script)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert 'must match workflow_controller.__version__' in result.stderr
