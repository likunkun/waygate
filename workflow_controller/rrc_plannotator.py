from __future__ import annotations

import json
import os
import shlex
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


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
