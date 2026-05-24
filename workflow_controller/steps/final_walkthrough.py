from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib import request
from urllib.error import URLError

from workflow_controller.gates.parsers import _current_unit
from workflow_controller.steps._common import StepResult, _now_iso, _write_json


LAUNCH_ARTIFACT_NAME = 'final-walkthrough-launch.json'
LAUNCH_LOG_NAME = 'final-walkthrough-launch.log'
DEFAULT_READY_TIMEOUT_SECONDS = 120


def run_final_walkthrough_prepare(
    state: dict[str, Any],
    *,
    artifacts_dir: Path,
    workspace_dir: Path,
    dry_run: bool = False,
) -> StepResult:
    unit = _current_unit(state)
    unit_id = str(unit.get('id') or state.get('currentUnitId') or 'unknown-unit')
    unit_dir = artifacts_dir / unit_id
    unit_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = unit_dir / LAUNCH_ARTIFACT_NAME
    log_path = unit_dir / LAUNCH_LOG_NAME
    launch = _launch_config(unit)
    mode = str(launch.get('mode') or 'not_required').strip() if launch else 'not_required'

    if dry_run:
        payload = _base_payload(unit_id, launch, workspace_dir)
        payload.update({
            'status': 'skipped',
            'reason': 'dry-run',
            'log_path': str(log_path),
        })
        _write_json(artifact_path, payload)
        return StepResult(summary='final walkthrough launch skipped', outputs=[LAUNCH_ARTIFACT_NAME])

    if mode == 'manual_only':
        payload = _base_payload(unit_id, launch, workspace_dir)
        payload.update({
            'status': 'manual_only',
            'manual_launch_instructions': str(launch.get('manual_launch_instructions') or '').strip(),
            'log_path': None,
        })
        _write_json(artifact_path, payload)
        return StepResult(summary='final walkthrough launch manual', outputs=[LAUNCH_ARTIFACT_NAME])

    if mode == 'not_required':
        payload = _base_payload(unit_id, launch, workspace_dir)
        payload.update({
            'status': 'not_required',
            'reason': str(launch.get('reason') or 'launch not required').strip(),
            'log_path': None,
        })
        _write_json(artifact_path, payload)
        return StepResult(summary='final walkthrough launch not required', outputs=[LAUNCH_ARTIFACT_NAME])

    if mode != 'agent_start':
        payload = _base_payload(unit_id, launch, workspace_dir)
        payload.update({
            'status': 'failed',
            'error': f'unsupported launch mode: {mode or "missing"}',
            'log_path': None,
        })
        _write_json(artifact_path, payload)
        return StepResult(summary='final walkthrough launch failed', outputs=[LAUNCH_ARTIFACT_NAME])

    payload = _run_agent_start_launch(
        unit_id=unit_id,
        launch=launch,
        workspace_dir=workspace_dir,
        log_path=log_path,
    )
    _write_json(artifact_path, payload)
    summary = 'final walkthrough launch ready' if payload.get('status') == 'ready' else 'final walkthrough launch failed'
    return StepResult(summary=summary, outputs=[LAUNCH_ARTIFACT_NAME, LAUNCH_LOG_NAME])


def _run_agent_start_launch(
    *,
    unit_id: str,
    launch: dict[str, Any],
    workspace_dir: Path,
    log_path: Path,
) -> dict[str, Any]:
    cwd = _launch_cwd(launch, workspace_dir)
    command = str(launch.get('command') or '').strip()
    timeout_seconds = _ready_timeout_seconds(launch)
    payload = _base_payload(unit_id, launch, cwd)
    payload['log_path'] = str(log_path)
    payload['cwd'] = str(cwd)

    with log_path.open('w', encoding='utf-8') as log_file:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            shell=True,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
            env=os.environ.copy(),
        )

    payload['pid'] = process.pid
    deadline = time.monotonic() + timeout_seconds
    last_ready_check: dict[str, Any] = {'status': 'pending'}
    while time.monotonic() < deadline:
        ready, ready_check = _readiness_passed(launch, cwd, log_path)
        last_ready_check = ready_check
        if ready:
            payload.update({
                'status': 'ready',
                'returncode': None,
                'ready_check': ready_check,
            })
            return payload
        returncode = process.poll()
        if returncode is not None:
            payload.update({
                'status': 'failed',
                'returncode': returncode,
                'ready_check': ready_check,
                'error': 'launch command exited before readiness',
                'manual_launch_instructions': str(launch.get('manual_launch_instructions') or '').strip(),
            })
            return payload
        time.sleep(0.1)

    _terminate_process_group(process)
    payload.update({
        'status': 'failed',
        'returncode': process.poll(),
        'ready_check': last_ready_check,
        'error': f'readiness timed out after {timeout_seconds} seconds',
        'manual_launch_instructions': str(launch.get('manual_launch_instructions') or '').strip(),
    })
    return payload


def _readiness_passed(launch: dict[str, Any], cwd: Path, log_path: Path) -> tuple[bool, dict[str, Any]]:
    output_contains = str(launch.get('ready_output_contains') or '').strip()
    if output_contains:
        log_text = log_path.read_text(encoding='utf-8', errors='replace') if log_path.exists() else ''
        if output_contains in log_text:
            return True, {'type': 'output', 'status': 'passed', 'contains': output_contains}
        return False, {'type': 'output', 'status': 'pending', 'contains': output_contains}

    ready_command = str(launch.get('ready_command') or '').strip()
    if ready_command:
        result = subprocess.run(
            ready_command,
            cwd=str(cwd),
            shell=True,
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
            env=os.environ.copy(),
        )
        status = 'passed' if result.returncode == 0 else 'pending'
        return result.returncode == 0, {
            'type': 'command',
            'status': status,
            'command': ready_command,
            'returncode': result.returncode,
            'stdout_tail': result.stdout[-1000:],
            'stderr_tail': result.stderr[-1000:],
        }

    ready_url = str(launch.get('ready_url') or '').strip()
    if ready_url:
        try:
            with request.urlopen(ready_url, timeout=1) as response:
                status_code = getattr(response, 'status', 200)
            passed = int(status_code) < 500
            return passed, {
                'type': 'url',
                'status': 'passed' if passed else 'pending',
                'url': ready_url,
                'status_code': status_code,
            }
        except (OSError, URLError) as exc:
            return False, {'type': 'url', 'status': 'pending', 'url': ready_url, 'error': str(exc)}

    return False, {'type': 'none', 'status': 'missing'}


def _base_payload(unit_id: str, launch: dict[str, Any], cwd: Path) -> dict[str, Any]:
    return {
        'schema_version': 'v0.6-final-walkthrough-launch',
        'unit_id': unit_id,
        'launch': _sanitized_launch(launch),
        'cwd': str(cwd),
        'generated_at': _now_iso(),
    }


def _sanitized_launch(launch: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        'mode',
        'command',
        'cwd',
        'env_keys',
        'ready_url',
        'ready_command',
        'ready_output_contains',
        'ready_timeout_seconds',
        'stop_command',
        'manual_launch_instructions',
        'reason',
    }
    sanitized: dict[str, Any] = {}
    for key in allowed_keys:
        if key not in launch:
            continue
        value = launch.get(key)
        if key == 'env_keys' and isinstance(value, list):
            sanitized[key] = [str(item) for item in value]
        elif isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[key] = value
    return sanitized


def _launch_config(unit: dict[str, Any]) -> dict[str, Any]:
    walkthrough = unit.get('final_acceptance_walkthrough') or unit.get('finalAcceptanceWalkthrough')
    if not isinstance(walkthrough, dict):
        return {'mode': 'not_required'}
    launch = walkthrough.get('launch')
    if not isinstance(launch, dict):
        return {'mode': 'not_required'}
    return launch


def _launch_cwd(launch: dict[str, Any], workspace_dir: Path) -> Path:
    raw_cwd = str(launch.get('cwd') or '').strip()
    if not raw_cwd:
        return workspace_dir
    candidate = Path(raw_cwd)
    return candidate if candidate.is_absolute() else workspace_dir / candidate


def _ready_timeout_seconds(launch: dict[str, Any]) -> float:
    try:
        value = float(launch.get('ready_timeout_seconds') or DEFAULT_READY_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        return float(DEFAULT_READY_TIMEOUT_SECONDS)
    return value if value > 0 else float(DEFAULT_READY_TIMEOUT_SECONDS)


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            process.kill()
        process.wait(timeout=2)
