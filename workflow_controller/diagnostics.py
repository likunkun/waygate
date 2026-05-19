from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from workflow_controller import __version__

RECOMMENDED_SKILL_GROUPS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ('startup', ('using-superpowers', 'superpowers:using-superpowers'), 'Install a startup skill so agents check applicable skills before acting.'),
    ('planning', ('writing-plans', 'superpowers:writing-plans', 'planning-with-files'), 'Install a planning skill for auditable unit plans and long-running work.'),
    ('requirements', ('brainstorming', 'superpowers:brainstorming'), 'Install brainstorming for requirements discovery and scope shaping.'),
    ('builder_tdd', ('test-driven-development', 'superpowers:test-driven-development'), 'Install TDD support for builder and bug-fix work.'),
    ('debugging', ('systematic-debugging', 'superpowers:systematic-debugging'), 'Install systematic debugging for runner, verifier, and defect investigations.'),
    ('test_strategy', ('test-strategy', 'testing-strategy'), 'Install test-strategy or testing-strategy for Requirements and Unit Plan test matrices.'),
    ('refiner', ('code-simplifier',), 'Install code-simplifier for post-builder cleanup and maintainability review.'),
    ('verification', ('verification-before-completion', 'superpowers:verification-before-completion'), 'Install verification-before-completion so agents do not claim success without evidence.'),
)


def render_doctor_report(
    *,
    env: dict[str, str] | None = None,
    argv0: str | None = None,
    module_file: str | None = None,
    dpkg_version_provider: Callable[[], str] | None = None,
) -> str:
    environment = env if env is not None else os.environ
    candidates = _waygate_path_candidates(environment)
    module_path = module_file or str(Path(__file__).resolve().parent / '__init__.py')
    dpkg_version = (dpkg_version_provider or _dpkg_waygate_version)()
    info = {
        'executable_path': _current_executable_path(argv0 or sys.argv[0], environment, candidates),
        'module_path': module_path,
        'module_version': __version__,
        'dpkg_version': dpkg_version,
        'path_candidates': candidates,
        'warnings': _doctor_warnings(candidates, module_version=__version__, dpkg_version=dpkg_version),
        'environment_checks': _environment_checks(environment),
        'skill_roots': _skill_root_checks(environment),
        'installed_skills': _installed_skill_checks(environment),
        'skill_recommendations': _skill_recommendations(environment),
    }
    return _format_doctor_report(info)


def _current_executable_path(argv0: str, env: dict[str, str], candidates: list[str]) -> str:
    if argv0:
        argv_path = Path(argv0).expanduser()
        if argv_path.name == 'waygate':
            if not argv_path.is_absolute():
                argv_path = Path.cwd() / argv_path
            return str(argv_path.resolve() if argv_path.exists() else argv_path)
    if candidates:
        return candidates[0]
    discovered = shutil.which('waygate', path=env.get('PATH'))
    return discovered or sys.executable


def _waygate_path_candidates(env: dict[str, str]) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for directory in env.get('PATH', '').split(os.pathsep):
        if not directory:
            continue
        base = Path(directory).expanduser()
        if not base.is_absolute():
            base = Path.cwd() / base
        candidate = base / 'waygate'
        if not candidate.exists() or not os.access(candidate, os.X_OK):
            continue
        candidate_text = str(candidate.resolve())
        if candidate_text in seen:
            continue
        seen.add(candidate_text)
        candidates.append(candidate_text)
    return candidates


def _dpkg_waygate_version() -> str:
    if shutil.which('dpkg-query') is None:
        return 'not available'
    result = subprocess.run(
        ['dpkg-query', '-W', '-f=${Version}', 'waygate'],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return 'not installed'
    return result.stdout.strip() or 'unknown'


def _doctor_warnings(candidates: list[str], *, module_version: str, dpkg_version: str) -> list[str]:
    warnings: list[str] = []
    packaged_index = next((index for index, candidate in enumerate(candidates) if _is_packaged_waygate(candidate)), None)
    if packaged_index is not None:
        packaged = candidates[packaged_index]
        for candidate in candidates[:packaged_index]:
            if _is_user_level_waygate(candidate):
                warnings.append(
                    f'PATH shadow: {candidate} appears before packaged {packaged}. '
                    'Rename/remove the user-level wrapper or run /usr/bin/waygate explicitly, then run `hash -r`.'
                )
                break
        if not warnings and candidates and candidates[0] != packaged:
            warnings.append(
                f'PATH shadow: {candidates[0]} appears before packaged {packaged}. '
                'Confirm which executable your shell resolves before approving gates.'
            )
    if dpkg_version not in {'not available', 'not installed', 'unknown'} and dpkg_version != module_version:
        warnings.append(
            f'version mismatch: module version {module_version} differs from dpkg package version {dpkg_version}.'
        )
    return warnings


def _environment_checks(env: dict[str, str]) -> list[str]:
    path = env.get('PATH')
    return [
        f'python: status=ok executable={sys.executable} version={_python_version()}',
        _command_check('pytest', 'pytest', path, required=True),
        _command_check('tmux', 'tmux', path, required=True),
        _tmux_session_check(env),
        _command_check(
            'Claude Code',
            'claude',
            path,
            required=False,
            manual_action='Install Claude Code or choose a subprocess runner for tasks that do not need Claude.',
        ),
        _command_check(
            'Codex',
            'codex',
            path,
            required=False,
            manual_action='Install Codex CLI or use another configured agent runner.',
        ),
        _command_check(
            'Plannotator',
            'plannotator',
            path,
            required=False,
            manual_action='Install Plannotator for browser-assisted gate review, or use terminal/manual approval.',
        ),
        _command_check('dpkg-deb', 'dpkg-deb', path, required=True),
        'recommended_plannotator_port: 20000',
    ]


def _python_version() -> str:
    return '.'.join(str(part) for part in sys.version_info[:3])


def _command_check(
    label: str,
    command: str,
    path: str | None,
    *,
    required: bool,
    manual_action: str | None = None,
) -> str:
    discovered = shutil.which(command, path=path)
    if discovered:
        return f'{label}: status=ok path={discovered}'
    if required:
        return f'{label}: status=warning path=missing manual_action=Install `{command}` before running verification that depends on it.'
    action = manual_action or f'Install `{command}` if this workflow path needs it.'
    return f'{label}: status=warning path=missing manual_action={action}'


def _tmux_session_check(env: dict[str, str]) -> str:
    if env.get('TMUX'):
        return 'tmux_session: status=ok active=true'
    return 'tmux_session: status=warning active=false manual_action=Run inside tmux before using tmux-claude or tmux-codex runners.'


def _skill_roots(env: dict[str, str]) -> list[Path]:
    home = Path(env.get('HOME') or str(Path.home())).expanduser()
    codex_home = Path(env.get('CODEX_HOME') or home / '.codex').expanduser()
    config_home = Path(env.get('XDG_CONFIG_HOME') or home / '.config').expanduser()
    explicit_roots = [
        Path(root).expanduser()
        for root in env.get('WAYGATE_SKILL_ROOTS', '').split(os.pathsep)
        if root
    ]
    roots = [
        home / '.agents' / 'skills',
        codex_home / 'skills',
        codex_home / 'superpowers' / 'skills',
        config_home / 'opencode' / 'skills',
        *explicit_roots,
    ]
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


def _skill_root_checks(env: dict[str, str]) -> list[str]:
    return [
        f'{root}: status={"found" if root.is_dir() else "missing"}'
        for root in _skill_roots(env)
    ]


def _discover_skills(env: dict[str, str]) -> dict[str, list[str]]:
    discovered: dict[str, list[str]] = {}
    for root in _skill_roots(env):
        if not root.is_dir():
            continue
        for skill_file in sorted(root.rglob('SKILL.md')):
            if not skill_file.is_file():
                continue
            skill_name = _skill_name_from_file(skill_file)
            discovered.setdefault(skill_name, []).append(str(skill_file))
    return discovered


def _skill_name_from_file(skill_file: Path) -> str:
    try:
        text = skill_file.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return skill_file.parent.name
    for line in text.splitlines()[:20]:
        stripped = line.strip()
        if stripped.startswith('name:'):
            name = stripped.partition(':')[2].strip().strip('"\'')
            if name:
                return name
    return skill_file.parent.name


def _installed_skill_checks(env: dict[str, str]) -> list[str]:
    discovered = _discover_skills(env)
    if not discovered:
        return []
    checks: list[str] = []
    for name in sorted(discovered):
        paths = sorted(discovered[name])
        suffix = f' duplicates={len(paths)}' if len(paths) > 1 else ''
        checks.append(f'{name}: status=ok path={paths[0]}{suffix}')
    return checks


def _skill_recommendations(env: dict[str, str]) -> list[str]:
    installed = set(_discover_skills(env))
    normalized_installed = installed | {name.split(':', 1)[1] for name in installed if ':' in name}
    checks: list[str] = []
    for group, candidates, manual_action in RECOMMENDED_SKILL_GROUPS:
        matched = next(
            (
                candidate
                for candidate in candidates
                if candidate in installed or candidate in normalized_installed or candidate.split(':')[-1] in normalized_installed
            ),
            None,
        )
        if matched:
            checks.append(f'{group}: status=ok matched={matched}')
        else:
            checks.append(
                f'{group}: status=warning missing={"/".join(candidates)} manual_action={manual_action}'
            )
    return checks


def _is_packaged_waygate(path: str) -> bool:
    normalized = path.replace('\\', '/')
    return normalized.endswith('/usr/bin/waygate')


def _is_user_level_waygate(path: str) -> bool:
    normalized = path.replace('\\', '/')
    return normalized.endswith('/.local/bin/waygate') or '/.local/bin/waygate' in normalized


def _format_doctor_report(info: dict[str, object]) -> str:
    lines = [
        'Waygate doctor',
        f"executable_path: {info['executable_path']}",
        f"module_path: {info['module_path']}",
        f"module_version: {info['module_version']}",
        f"dpkg_version: {info['dpkg_version']}",
        'path_candidates:',
    ]
    candidates = info.get('path_candidates')
    if isinstance(candidates, list) and candidates:
        lines.extend(f'- {candidate}' for candidate in candidates)
    else:
        lines.append('- none')
    warnings = info.get('warnings')
    if isinstance(warnings, list) and warnings:
        lines.append('warnings:')
        lines.extend(f'- {warning}' for warning in warnings)
    environment_checks = info.get('environment_checks')
    if isinstance(environment_checks, list) and environment_checks:
        lines.append('environment_checks:')
        lines.extend(f'- {check}' for check in environment_checks)
    skill_roots = info.get('skill_roots')
    if isinstance(skill_roots, list) and skill_roots:
        lines.append('skill_roots:')
        lines.extend(f'- {root}' for root in skill_roots)
    installed_skills = info.get('installed_skills')
    lines.append('installed_skills:')
    if isinstance(installed_skills, list) and installed_skills:
        lines.extend(f'- {skill}' for skill in installed_skills)
    else:
        lines.append('- none')
    skill_recommendations = info.get('skill_recommendations')
    if isinstance(skill_recommendations, list) and skill_recommendations:
        lines.append('skill_recommendations:')
        lines.extend(f'- {recommendation}' for recommendation in skill_recommendations)
    return '\n'.join(lines) + '\n'
