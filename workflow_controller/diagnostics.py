from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from workflow_controller import __version__

ANSI_RESET = '\033[0m'
ANSI_STYLES = {
    'bold': '\033[1m',
    'bold_cyan': '\033[1;36m',
    'bold_yellow': '\033[1;33m',
    'cyan': '\033[36m',
    'dim': '\033[2m',
    'green': '\033[32m',
    'red': '\033[31m',
    'yellow': '\033[33m',
}

RECOMMENDED_SKILL_GROUPS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ('startup', ('using-superpowers', 'superpowers:using-superpowers'), 'Install a startup skill so agents check applicable skills before acting.'),
    ('persistent_planning', ('planning-with-files',), 'Install planning-with-files for persistent project memory and recovery.'),
    ('planning', ('writing-plans', 'superpowers:writing-plans'), 'Install writing-plans for auditable implementation plans.'),
    ('requirements', ('brainstorming', 'superpowers:brainstorming'), 'Install brainstorming for requirements discovery and scope shaping.'),
    ('builder_tdd', ('test-driven-development', 'superpowers:test-driven-development'), 'Install TDD support for builder and bug-fix work.'),
    ('debugging', ('systematic-debugging', 'superpowers:systematic-debugging'), 'Install systematic debugging for runner, verifier, and defect investigations.'),
    ('test_strategy', ('test-strategy', 'testing-strategy'), 'Install test-strategy or testing-strategy for Requirements and Unit Plan test matrices.'),
    ('refiner', ('code-simplifier',), 'Install code-simplifier for post-builder cleanup and maintainability review.'),
    ('verification', ('verification-before-completion', 'superpowers:verification-before-completion'), 'Install verification-before-completion so agents do not claim success without evidence.'),
    ('code_review', ('requesting-code-review', 'superpowers:requesting-code-review', 'receiving-code-review', 'superpowers:receiving-code-review'), 'Install requesting-code-review or receiving-code-review for concrete review and rework loops.'),
    ('plan_execution', ('executing-plans', 'superpowers:executing-plans', 'subagent-driven-development', 'superpowers:subagent-driven-development'), 'Install executing-plans or subagent-driven-development for approved multi-step plan execution.'),
    ('webapp_testing', ('webapp-testing',), 'Install webapp-testing for browser-visible workflow verification.'),
    ('ui_ux_design', ('frontend-design', 'ui-ux-pro-max'), 'Install frontend-design or ui-ux-pro-max for UI-heavy requirements.'),
)

RECOMMENDED_TMUX_CONFIG: tuple[tuple[str, str, str], ...] = (
    ('mouse', 'on', 'set -g mouse on'),
    ('history-limit', '100000', 'set -g history-limit 100000'),
    ('@scroll-speed', '5', 'set -g @scroll-speed 5'),
    ('@copy-mode-vi', 'on', "set -g @copy-mode-vi 'on'"),
)


def render_doctor_report(
    *,
    env: dict[str, str] | None = None,
    argv0: str | None = None,
    module_file: str | None = None,
    dpkg_version_provider: Callable[[], str] | None = None,
    color_mode: str = 'auto',
    color_stream: object | None = None,
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
        'tmux_config': _tmux_config_checks(environment),
        'skill_roots': _skill_root_checks(environment),
        'installed_skills': _installed_skill_checks(environment),
        'skill_recommendations': _skill_recommendations(environment),
        'claude_assets': _claude_asset_checks(environment),
    }
    color_enabled = _doctor_color_enabled(color_mode, color_stream, environment)
    return _format_doctor_report(info, color_enabled=color_enabled)


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


def _tmux_config_checks(env: dict[str, str]) -> list[str]:
    home = Path(env.get('HOME') or str(Path.home())).expanduser()
    config_path = home / '.tmux.conf'
    values = _parse_tmux_config(config_path) if config_path.exists() else {}
    checks = [f'{config_path}: status={"found" if config_path.exists() else "missing"}']
    for key, expected, command in RECOMMENDED_TMUX_CONFIG:
        actual = values.get(key, 'missing')
        if actual == expected:
            checks.append(f'{key}: status=ok expected={expected} actual={actual}')
            continue
        manual_action = f'Add `{command}` to ~/.tmux.conf and reload tmux config.'
        checks.append(
            f'{key}: status=warning expected={expected} actual={actual} manual_action={manual_action}'
        )
    return checks


def _parse_tmux_config(config_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = config_path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        try:
            tokens = shlex.split(stripped, comments=True, posix=True)
        except ValueError:
            continue
        if len(tokens) < 4:
            continue
        if tokens[0] not in {'set', 'set-option'} or tokens[1] != '-g':
            continue
        key = tokens[2]
        value = ' '.join(tokens[3:]).strip()
        if key and value:
            values[key] = value
    return values


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


def _claude_asset_checks(env: dict[str, str]) -> list[str]:
    home = Path(env.get('HOME') or str(Path.home())).expanduser()
    claude_root = home / '.claude'
    checks: list[str] = []
    for name in ('commands', 'agents', 'rules', 'plugins'):
        directory = claude_root / name
        count = _directory_entry_count(directory) if directory.is_dir() else 0
        checks.append(f'{directory}: status={"found" if directory.is_dir() else "missing"} count={count}')
    return checks


def _directory_entry_count(directory: Path) -> int:
    try:
        return sum(1 for child in directory.iterdir() if child.name not in {'', '.', '..'})
    except OSError:
        return 0


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


def _format_doctor_report(info: dict[str, object], *, color_enabled: bool = False) -> str:
    actions = _doctor_action_required(info)
    warning_count = _doctor_warning_count(info)
    overall_status = 'warning' if warning_count or actions else 'ok'
    lines = [
        _doctor_paint('Waygate doctor', 'bold', color_enabled),
        _doctor_section('summary:', color_enabled),
        (
            '- overall: '
            f'{_doctor_status_token(overall_status, color_enabled)} '
            f'warnings={warning_count} manual_actions={len(actions)}'
        ),
        f"- version: module={info['module_version']} dpkg={info['dpkg_version']}",
        _doctor_section('focus:', color_enabled),
    ]
    for priority, text in _doctor_focus_items(info):
        lines.append(f'- {_doctor_priority_token(priority, color_enabled)} {text}')
    lines.append(_doctor_section('action_required:', color_enabled))
    if actions:
        lines.extend(f'- {_doctor_paint(action, "yellow", color_enabled)}' for action in actions)
    else:
        lines.append(f'- {_doctor_paint("none", "green", color_enabled)}')
    lines.extend([
        f"executable_path: {info['executable_path']}",
        f"module_path: {info['module_path']}",
        f"module_version: {info['module_version']}",
        f"dpkg_version: {info['dpkg_version']}",
        _doctor_section('path_candidates:', color_enabled),
    ])
    candidates = info.get('path_candidates')
    if isinstance(candidates, list) and candidates:
        lines.extend(f'- {candidate}' for candidate in candidates)
    else:
        lines.append('- none')
    warnings = info.get('warnings')
    if isinstance(warnings, list) and warnings:
        lines.append(_doctor_section('warnings:', color_enabled))
        lines.extend(f'- {_doctor_detail_entry(warning, color_enabled)}' for warning in warnings)
    environment_checks = info.get('environment_checks')
    if isinstance(environment_checks, list) and environment_checks:
        lines.append(_doctor_section('environment_checks:', color_enabled))
        lines.extend(f'- {_doctor_detail_entry(check, color_enabled)}' for check in environment_checks)
    tmux_config = info.get('tmux_config')
    if isinstance(tmux_config, list) and tmux_config:
        lines.append(_doctor_section('tmux_config:', color_enabled))
        lines.extend(f'- {_doctor_detail_entry(check, color_enabled)}' for check in tmux_config)
    skill_roots = info.get('skill_roots')
    if isinstance(skill_roots, list) and skill_roots:
        lines.append(_doctor_section('skill_roots:', color_enabled))
        lines.extend(f'- {_doctor_detail_entry(root, color_enabled)}' for root in skill_roots)
    installed_skills = info.get('installed_skills')
    lines.append(_doctor_section('installed_skills:', color_enabled))
    if isinstance(installed_skills, list) and installed_skills:
        lines.extend(f'- {_doctor_detail_entry(skill, color_enabled)}' for skill in installed_skills)
    else:
        lines.append('- none')
    skill_recommendations = info.get('skill_recommendations')
    if isinstance(skill_recommendations, list) and skill_recommendations:
        lines.append(_doctor_section('skill_recommendations:', color_enabled))
        lines.extend(f'- {_doctor_detail_entry(recommendation, color_enabled)}' for recommendation in skill_recommendations)
    claude_assets = info.get('claude_assets')
    if isinstance(claude_assets, list) and claude_assets:
        lines.append(_doctor_section('claude_assets:', color_enabled))
        lines.extend(f'- {_doctor_detail_entry(asset, color_enabled)}' for asset in claude_assets)
    return '\n'.join(lines) + '\n'


def _doctor_warning_count(info: dict[str, object]) -> int:
    count = 0
    warnings = info.get('warnings')
    if isinstance(warnings, list):
        count += len(warnings)
    for section in ('environment_checks', 'tmux_config', 'skill_recommendations'):
        entries = info.get(section)
        if isinstance(entries, list):
            count += sum(1 for entry in entries if 'status=warning' in str(entry))
    return count


def _doctor_focus_items(info: dict[str, object]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    tmux_warnings = _doctor_section_warning_count(info, 'tmux_config')
    if tmux_warnings:
        items.append(('P1', f'tmux_config: {tmux_warnings} warning(s); update ~/.tmux.conf and reload tmux config.'))

    provenance_warnings = [
        warning
        for warning in _section_entries(info, 'warnings')
        if warning.startswith('PATH shadow:') or warning.startswith('version mismatch:')
    ]
    if provenance_warnings:
        items.append(('P1', f'install_provenance: {len(provenance_warnings)} warning(s); fix PATH shadow or version mismatch before trusting this install.'))

    environment_warnings = _doctor_section_warning_count(info, 'environment_checks')
    if environment_warnings:
        items.append(('P2', f'environment_checks: {environment_warnings} warning(s); install missing tools or adjust PATH.'))

    skill_warnings = _doctor_section_warning_count(info, 'skill_recommendations')
    if skill_warnings:
        items.append(('P3', f'skill_recommendations: {skill_warnings} warning(s); install missing workflow skills when this path needs them.'))

    if not items:
        items.append(('OK', 'No manual action required.'))
    return items


def _doctor_section_warning_count(info: dict[str, object], section: str) -> int:
    return sum(1 for entry in _section_entries(info, section) if 'status=warning' in entry)


def _doctor_action_required(info: dict[str, object]) -> list[str]:
    actions: list[str] = []
    for entry in _section_entries(info, 'tmux_config'):
        action = _manual_action_from_entry(entry)
        if action:
            actions.append(f'tmux_config.{_entry_subject(entry)}: {action}')
    for warning in _section_entries(info, 'warnings'):
        if warning.startswith('PATH shadow:'):
            actions.append(f'path_shadow: {warning}')
        elif warning.startswith('version mismatch:'):
            actions.append(
                f'version_mismatch: {warning} Install the matching package or run the matching source tree.'
            )
    for entry in _section_entries(info, 'environment_checks'):
        action = _manual_action_from_entry(entry)
        if action:
            actions.append(f'environment_checks.{_entry_subject(entry)}: {action}')
    for entry in _section_entries(info, 'skill_recommendations'):
        action = _manual_action_from_entry(entry)
        if action:
            actions.append(f'skill_recommendations.{_entry_subject(entry)}: {action}')
    return actions


def _section_entries(info: dict[str, object], section: str) -> list[str]:
    entries = info.get(section)
    if not isinstance(entries, list):
        return []
    return [str(entry) for entry in entries]


def _manual_action_from_entry(entry: str) -> str | None:
    marker = ' manual_action='
    if marker not in entry:
        return None
    return entry.split(marker, 1)[1]


def _entry_subject(entry: str) -> str:
    return entry.split(':', 1)[0]


def _doctor_color_enabled(color_mode: str, color_stream: object | None, env: dict[str, str]) -> bool:
    if color_mode == 'always':
        return True
    if color_mode == 'never':
        return False
    if env.get('NO_COLOR') is not None:
        return False
    stream = color_stream or sys.stdout
    isatty = getattr(stream, 'isatty', None)
    return bool(isatty and isatty())


def _doctor_section(label: str, color_enabled: bool) -> str:
    return _doctor_paint(label, 'bold_cyan', color_enabled)


def _doctor_status_token(status: str, color_enabled: bool) -> str:
    style = 'green' if status == 'ok' else 'yellow'
    return _doctor_paint(f'status={status}', style, color_enabled)


def _doctor_priority_token(priority: str, color_enabled: bool) -> str:
    if priority == 'OK':
        style = 'green'
    elif priority == 'P1':
        style = 'bold_yellow'
    elif priority == 'P2':
        style = 'yellow'
    else:
        style = 'dim'
    return _doctor_paint(f'[{priority}]', style, color_enabled)


def _doctor_detail_entry(entry: str, color_enabled: bool) -> str:
    if not color_enabled:
        return entry
    highlighted = entry
    replacements = [
        ('status=warning', 'yellow'),
        ('status=missing', 'red'),
        ('status=ok', 'green'),
        ('status=found', 'green'),
        ('status=invalid', 'red'),
    ]
    for token, style in replacements:
        highlighted = highlighted.replace(token, _doctor_paint(token, style, True))
    if ' manual_action=' in highlighted:
        prefix, _, action = highlighted.partition(' manual_action=')
        highlighted = f'{prefix} manual_action={_doctor_paint(action, "yellow", True)}'
    elif highlighted.startswith('PATH shadow:') or highlighted.startswith('version mismatch:'):
        highlighted = _doctor_paint(highlighted, 'yellow', True)
    return highlighted


def _doctor_paint(text: str, style: str, enabled: bool) -> str:
    if not enabled:
        return text
    code = ANSI_STYLES.get(style)
    if not code:
        return text
    return f'{code}{text}{ANSI_RESET}'
