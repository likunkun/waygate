from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONFIRMATION_HEADING = '## Human Confirmation'
CONTROLLER_STATE_PATCH_HEADING = '## Controller State Patch'
CONTROLLER_STATE_PATCH_HEADING_ALIASES = (
    'Controller State Patch',
    '控制器状态补丁',
)
ALLOWED_COVERAGE_STATUSES = {'partial', 'covered'}

FINAL_ACCEPTANCE_REJECTION_ROUTES = (
    ('requirements', '需求变更', '已批准需求不完整或存在错误。'),
    ('defect_fix', '验收缺陷修复', '已批准需求正确，最终验收发现已完成工作存在缺陷。'),
    ('unit_plan', 'Unit Plan 修订', '单元范围或验证命令不正确。'),
    ('implementation', '实现返工', '已批准需求正确，但实现需要修改。'),
    ('blocked', '阻塞', '由于环境、数据、权限或证据缺失，暂时无法判断。'),
)
FINAL_ACCEPTANCE_REJECTION_ROUTE_ALIASES = {
    'requirements': ('需求变更', 'Requirements revision'),
    'defect_fix': ('验收缺陷修复', 'Defect fix'),
    'unit_plan': ('Unit Plan 修订', 'Unit plan revision'),
    'implementation': ('实现返工', 'Implementation rework'),
    'blocked': ('阻塞', 'Blocked'),
}


# ---------------------------------------------------------------------------
# Plannotator gate review
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlannotatorReviewResult:
    gate: str
    gate_path: Path
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    summary_path: Path
    process_id: int | None = None


def run_plannotator_gate_review(
    *,
    gate: str,
    label: str,
    gate_path: Path,
    state_dir: Path,
    command: str = 'plannotator',
    port: int | None = 20000,
    timeout_seconds: int = 30,
) -> PlannotatorReviewResult:
    if not gate_path.exists():
        raise FileNotFoundError(f'Human gate file not found: {gate_path}')

    command_parts = shlex.split(command)
    if not command_parts:
        raise ValueError('Plannotator command cannot be empty')
    if shutil.which(command_parts[0]) is None and not Path(command_parts[0]).exists():
        raise FileNotFoundError(f'Plannotator command not found: {command_parts[0]}')

    review_dir = state_dir / 'plannotator'
    review_dir.mkdir(parents=True, exist_ok=True)
    summary_path = review_dir / f'{gate}-last-review.json'
    stdout_path = review_dir / f'{gate}-last-review.stdout.log'
    stderr_path = review_dir / f'{gate}-last-review.stderr.log'

    full_command = [*command_parts, 'annotate', str(gate_path), '--gate', '--json']
    env = os.environ.copy()
    if port is not None:
        env['PLANNOTATOR_PORT'] = str(port)
    with stdout_path.open('w', encoding='utf-8') as stdout_file, stderr_path.open('w', encoding='utf-8') as stderr_file:
        process = subprocess.Popen(
            full_command,
            cwd=str(gate_path.parent),
            text=True,
            stdout=stdout_file,
            stderr=stderr_file,
            env=env,
        )

    deadline = time.monotonic() + timeout_seconds
    while True:
        returncode = process.poll()
        stdout = _read_text(stdout_path)
        stderr = _read_text(stderr_path)

        if returncode is not None:
            _write_summary(
                summary_path=summary_path,
                gate=gate,
                label=label,
                gate_path=gate_path,
                full_command=full_command,
                plannotator_port=env.get('PLANNOTATOR_PORT'),
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                process_id=process.pid,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
            if returncode != 0:
                raise RuntimeError(
                    f'Plannotator failed with exit code {returncode}. See {summary_path}'
                )
            return PlannotatorReviewResult(
                gate=gate,
                gate_path=gate_path,
                command=full_command,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                summary_path=summary_path,
                process_id=process.pid,
            )

        server_ready = (
            _has_review_link(stdout)
            or _has_review_link(stderr)
            or (port is not None and _is_local_port_ready(port))
        )
        if server_ready:
            _write_summary(
                summary_path=summary_path,
                gate=gate,
                label=label,
                gate_path=gate_path,
                full_command=full_command,
                plannotator_port=env.get('PLANNOTATOR_PORT'),
                returncode=None,
                stdout=stdout,
                stderr=stderr,
                process_id=process.pid,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
            return PlannotatorReviewResult(
                gate=gate,
                gate_path=gate_path,
                command=full_command,
                returncode=None,
                stdout=stdout,
                stderr=stderr,
                summary_path=summary_path,
                process_id=process.pid,
            )

        if time.monotonic() >= deadline:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            stdout = _read_text(stdout_path)
            stderr = _read_text(stderr_path)
            _write_summary(
                summary_path=summary_path,
                gate=gate,
                label=label,
                gate_path=gate_path,
                full_command=full_command,
                plannotator_port=env.get('PLANNOTATOR_PORT'),
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                process_id=process.pid,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                timed_out=True,
            )
            raise subprocess.TimeoutExpired(full_command, timeout_seconds, output=stdout, stderr=stderr)

        time.sleep(0.1)


def _has_review_link(output: str) -> bool:
    return 'share.plannotator.ai/#' in output or 'Open this link on your local machine to annotate' in output


def _is_local_port_ready(port: int) -> bool:
    try:
        with socket.create_connection(('localhost', port), timeout=0.5):
            return True
    except OSError:
        return False


def _read_text(path: Path) -> str:
    if not path.exists():
        return ''
    return path.read_text(encoding='utf-8', errors='replace')


def _write_summary(
    *,
    summary_path: Path,
    gate: str,
    label: str,
    gate_path: Path,
    full_command: list[str],
    plannotator_port: str | None,
    returncode: int | None,
    stdout: str,
    stderr: str,
    process_id: int | None,
    stdout_path: Path,
    stderr_path: Path,
    timed_out: bool = False,
) -> None:
    summary_path.write_text(
        json.dumps(
            {
                'gate': gate,
                'label': label,
                'gate_path': str(gate_path),
                'command': full_command,
                'plannotator_port': plannotator_port,
                'returncode': returncode,
                'stdout': stdout,
                'stderr': stderr,
                'process_id': process_id,
                'stdout_path': str(stdout_path),
                'stderr_path': str(stderr_path),
                'timed_out': timed_out,
                'reviewed_at': datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )


# ---------------------------------------------------------------------------
# Gate file reading / parsing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GateCheck:
    approved: bool
    reason: str | None = None
    content_hash: str | None = None
    confirmed_by: str | None = None


def gate_body(content: str) -> str:
    if CONFIRMATION_HEADING not in content:
        return content.rstrip() + '\n'
    return content.split(CONFIRMATION_HEADING, 1)[0].rstrip() + '\n'


def hash_gate_body(body: str) -> str:
    return hashlib.sha256((body.rstrip() + '\n').encode('utf-8')).hexdigest()


def _confirmation_fields(content: str) -> dict[str, str]:
    if CONFIRMATION_HEADING not in content:
        return {}
    block = content.split(CONFIRMATION_HEADING, 1)[1]
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        fields[key.strip().lower()] = value.strip()
    return fields


def check_gate_file(path: Path) -> GateCheck:
    if not path.exists():
        return GateCheck(False, reason='missing')
    content = path.read_text(encoding='utf-8')
    fields = _confirmation_fields(content)
    body = gate_body(content)
    actual_hash = hash_gate_body(body)
    expected_hash = fields.get('content hash', '').removeprefix('sha256:')

    if fields.get('status', '').strip().lower() != 'approved':
        return GateCheck(False, reason='not_approved', content_hash=actual_hash)
    if expected_hash != actual_hash:
        return GateCheck(False, reason='stale', content_hash=actual_hash, confirmed_by=fields.get('confirmed by'))
    return GateCheck(True, content_hash=actual_hash, confirmed_by=fields.get('confirmed by'))


def approve_gate_file(path: Path, actor: str = 'human') -> None:
    content = path.read_text(encoding='utf-8')
    body = gate_body(content)
    content_hash = hash_gate_body(body)
    approved = (
        body.rstrip()
        + '\n\n'
        + f'{CONFIRMATION_HEADING}\n\n'
        + 'Status: approved\n'
        + f'Confirmed by: {actor}\n'
        + f'Confirmed at: {datetime.now(timezone.utc).isoformat()}\n'
        + f'Content hash: sha256:{content_hash}\n'
    )
    path.write_text(approved, encoding='utf-8')


def write_gate_file(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_body = body.rstrip() + '\n'
    content_hash = hash_gate_body(normalized_body)
    path.write_text(
        f"{normalized_body}\n"
        f"{CONFIRMATION_HEADING}\n\n"
        "Status: pending\n"
        "Confirmed by: \n"
        "Confirmed at: \n"
        f"Content hash: sha256:{content_hash}\n",
        encoding='utf-8',
    )


def extract_unit_plan_state_patch(content: str) -> dict[str, Any]:
    body = gate_body(content)
    heading = _find_controller_state_patch_heading(body)
    if not heading:
        raise ValueError('Unit plan is missing ## Controller State Patch')

    section = body[heading.end():]
    next_heading = re.search(r'(?m)^##\s+', section)
    if next_heading:
        section = section[:next_heading.start()]

    fence = re.search(r'```(?:json)?\s*\n(.*?)\n```', section, flags=re.DOTALL | re.IGNORECASE)
    if not fence:
        raise ValueError('Controller State Patch must contain a fenced JSON object')

    try:
        patch = json.loads(fence.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f'Controller State Patch JSON is invalid: {exc.msg}') from exc

    if not isinstance(patch, dict):
        raise ValueError('Controller State Patch must be a JSON object')
    return patch


def _find_controller_state_patch_heading(body: str) -> re.Match[str] | None:
    names = '|'.join(re.escape(name) for name in CONTROLLER_STATE_PATCH_HEADING_ALIASES)
    return re.search(rf'(?im)^##+\s+(?:{names})\s*$', body)


def extract_patch_list(gate_content: str) -> str | None:
    """Return non-empty lines from the ## 修改清单 section, or None if absent/empty."""
    raw = _markdown_section(gate_content, '修改清单')
    without_comments = re.sub(r'<!--.*?-->', '', raw, flags=re.DOTALL)
    lines = [line for line in without_comments.splitlines() if line.strip()]
    return '\n'.join(lines) if lines else None


def _markdown_section(content: str, heading_contains: str) -> str:
    lines = gate_body(content).splitlines()
    heading_lower = heading_contains.lower()
    start: int | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('##') and heading_lower in stripped.lower():
            start = index + 1
            break
    if start is None:
        return ''

    section: list[str] = []
    for line in lines[start:]:
        if line.strip().startswith('##'):
            break
        section.append(line)
    return '\n'.join(section)


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


# ---------------------------------------------------------------------------
# Shared helpers used by both generators and validators
# ---------------------------------------------------------------------------

def _unit_test_cases(unit: dict[str, Any]) -> list[Any]:
    for key in ('test_cases', 'testCases'):
        raw_cases = unit.get(key)
        if isinstance(raw_cases, list) and raw_cases:
            return raw_cases
    return []


def _current_unit(state: dict[str, Any]) -> dict[str, Any]:
    current = state.get('currentUnitId')
    for unit in state.get('units', []):
        if unit.get('id') == current:
            return unit
    return {}


def _controller_state_patch(state: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {
        'currentUnitId': state.get('currentUnitId'),
        'objectiveCoverage': state.get('objectiveCoverage') or [],
        'units': state.get('units') or [],
    }
    if 'currentUnitNeedsUiDesign' in state:
        patch['currentUnitNeedsUiDesign'] = bool(state.get('currentUnitNeedsUiDesign'))
    return patch
