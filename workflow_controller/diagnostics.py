from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from workflow_controller import __version__


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
    return '\n'.join(lines) + '\n'
