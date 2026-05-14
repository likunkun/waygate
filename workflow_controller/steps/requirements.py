from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from workflow_controller.runners import RunnerRequest, make_runner, run_agent_backend
from workflow_controller.runners.base import DEFAULT_AGENT_TIMEOUT_SECONDS
from workflow_controller.gates import format_requirements_gate_body, render_requirements_gate_body, write_gate_file
from workflow_controller.prompts.requirements import _render_requirements_draft_prompt
from workflow_controller.requirements_dialogue_brief import write_requirements_dialogue_brief
from workflow_controller.steps._common import StepResult, _write_json, _now_iso


REQUIREMENTS_DRAFT_WAIT_TIMEOUT_MESSAGE = (
    '等了太久，先休息一下，等agent好了，再接着干。'
    '下次继续会接上这轮 Requirements Draft，不会重新讨论需求。'
)
_PENDING_REQUIREMENTS_DRAFT_STATUSES = {'timeout', 'agent_idle_without_done'}
DEFAULT_REQUIREMENTS_DRAFT_RESUME_POLL_SECONDS = 5.0


def run_requirements_drafter(
    state: dict[str, Any],
    approvals_dir: Path,
    artifacts_dir: Path,
    dry_run: bool = False,
) -> StepResult:
    draft_dir = artifacts_dir / 'requirements-draft'
    draft_dir.mkdir(parents=True, exist_ok=True)
    gate_path = approvals_dir / 'requirements-and-acceptance.md'
    body_path = draft_dir / 'requirements-body.md'
    summary_path = draft_dir / 'requirements-draft-summary.json'
    dialogue_brief = write_requirements_dialogue_brief(state, artifacts_dir)
    state['requirementsDialogueBriefPath'] = dialogue_brief['artifact_paths']['markdown']
    state['requirementsDialogueBriefHash'] = dialogue_brief['brief_hash']

    if dry_run or state.get('agentRunner') not in {'tmux-claude', 'tmux-codex'}:
        body = render_requirements_gate_body(state)
        write_gate_file(gate_path, body)
        body_path.write_text(body, encoding='utf-8')
        _write_json(summary_path, {
            'status': 'ok',
            'mode': 'local-template',
            'gate_path': str(gate_path),
            'body_path': str(body_path),
            'requirements_dialogue_brief_path': dialogue_brief['artifact_paths']['markdown'],
            'requirements_dialogue_brief_hash': dialogue_brief['brief_hash'],
            'requirements_spec': _requirements_spec_summary(state),
            'generated_at': _now_iso(),
        })
        return StepResult(
            summary='requirements draft generated',
            outputs=[str(gate_path), str(summary_path), dialogue_brief['artifact_paths']['markdown']],
        )

    resumed = _resume_pending_requirements_draft_if_ready(
        state=state,
        gate_path=gate_path,
        body_path=body_path,
        summary_path=summary_path,
        dialogue_brief=dialogue_brief,
    )
    if resumed is not None:
        return resumed

    prompt_path = draft_dir / 'requirements-draft-prompt.md'
    if body_path.exists():
        body_path.unlink()
    prompt_path.write_text(
        _render_requirements_draft_prompt(state, body_path),
        encoding='utf-8',
    )
    workspace_path = state.get('executionWorkspacePath') or state.get('workspacePath')
    if not workspace_path:
        raise RuntimeError('requirements drafter requires workspacePath or executionWorkspacePath')

    runner = make_runner(state)
    result = run_agent_backend(RunnerRequest(
        backend=runner.backend,
        workspace_dir=Path(workspace_path),
        prompt_path=prompt_path,
        artifact_dir=draft_dir,
        unit_id='requirements-draft',
        agent_command=runner.agent_command,
        tmux_target=runner.tmux_target,
        role=runner.role,
        env=runner.env,
        timeout_seconds=int(_requirements_draft_resume_timeout_seconds(state)),
    ))
    _write_json(summary_path, {
        'status': result.status,
        'mode': result.backend,
        'runner_run_dir': str(result.run_dir),
        'done_path': str(result.done_path) if result.done_path else None,
        'done_payload': result.done_payload,
        'agent_command': result.command,
        'runner_metadata': result.runner_metadata,
        'exit_code': result.returncode,
        'stdout': result.stdout,
        'stderr': result.stderr,
        'user_message': (
            REQUIREMENTS_DRAFT_WAIT_TIMEOUT_MESSAGE
            if result.status in _PENDING_REQUIREMENTS_DRAFT_STATUSES
            else None
        ),
        'gate_path': str(gate_path),
        'body_path': str(body_path),
        'requirements_dialogue_brief_path': dialogue_brief['artifact_paths']['markdown'],
        'requirements_dialogue_brief_hash': dialogue_brief['brief_hash'],
        'requirements_spec': _requirements_spec_summary(state),
        'generated_at': _now_iso(),
    })
    if result.status in _PENDING_REQUIREMENTS_DRAFT_STATUSES:
        raise RuntimeError(REQUIREMENTS_DRAFT_WAIT_TIMEOUT_MESSAGE)
    if result.returncode != 0:
        raise RuntimeError(
            f"Requirements drafter failed with exit code {result.returncode}. See {summary_path}"
        )
    if not body_path.exists():
        raise FileNotFoundError(
            f"Requirements drafter did not write {body_path}. See {summary_path}"
        )

    write_gate_file(gate_path, format_requirements_gate_body(state, body_path.read_text(encoding='utf-8')))
    return StepResult(
        summary='requirements draft generated',
        outputs=[str(gate_path), str(summary_path), dialogue_brief['artifact_paths']['markdown']],
    )


def _resume_pending_requirements_draft_if_ready(
    *,
    state: dict[str, Any],
    gate_path: Path,
    body_path: Path,
    summary_path: Path,
    dialogue_brief: dict[str, Any],
) -> StepResult | None:
    if not summary_path.exists():
        return None
    summary = _read_json_object(summary_path)
    summary_status = str(summary.get('status') or '')
    if summary_status not in _PENDING_REQUIREMENTS_DRAFT_STATUSES and summary_status != 'done':
        return None
    if summary_status == 'done' and str(state.get('requirementsRevisionFeedback') or '').strip():
        return None

    timeout_mtime = _requirements_draft_timeout_mtime(summary_path, summary)
    done_candidate = _wait_for_existing_requirements_draft_if_needed(
        state=state,
        summary_path=summary_path,
        summary=summary,
        body_path=body_path,
        timeout_mtime=timeout_mtime,
    )
    if done_candidate is None:
        done_candidate = _find_existing_requirements_done_signal(
            summary_path,
            summary,
            body_path=body_path,
            timeout_mtime=timeout_mtime,
        )

    if done_candidate is None and summary_status == 'done' and body_path.exists():
        done_path = None
        done_payload: dict[str, Any] = dict(summary.get('done_payload') or {'status': 'done'})
    elif done_candidate is None:
        raise RuntimeError(REQUIREMENTS_DRAFT_WAIT_TIMEOUT_MESSAGE)
    else:
        done_path, done_payload = done_candidate
    done_status = str(done_payload.get('status') or 'done')
    if done_status == 'pending':
        raise RuntimeError(REQUIREMENTS_DRAFT_WAIT_TIMEOUT_MESSAGE)

    expected_run_id = Path(str(summary.get('runner_run_dir') or '')).name
    actual_run_id = str(done_payload.get('run_id') or '')
    if expected_run_id and actual_run_id != expected_run_id:
        raise RuntimeError(
            f'Requirements drafter DONE_FILE has wrong run_id: expected {expected_run_id}, actual {actual_run_id}.'
        )
    if done_status != 'done':
        raise RuntimeError(
            f"Requirements drafter returned status={done_status!r}: {done_payload.get('summary') or 'no summary'}"
        )
    if not body_path.exists():
        raise FileNotFoundError(
            f"Requirements drafter wrote DONE_FILE but did not write {body_path}. See {summary_path}"
        )
    if timeout_mtime is not None and (
        body_path.stat().st_mtime <= timeout_mtime
        or (done_path is not None and done_path.stat().st_mtime <= timeout_mtime)
    ):
        raise RuntimeError(REQUIREMENTS_DRAFT_WAIT_TIMEOUT_MESSAGE)

    write_gate_file(gate_path, format_requirements_gate_body(state, body_path.read_text(encoding='utf-8')))
    _write_json(summary_path, {
        **summary,
        'status': 'done',
        **({'done_path': str(done_path)} if done_path is not None else {}),
        'done_payload': done_payload,
        'exit_code': 0,
        'resumed_from_pending_run': True,
        'gate_path': str(gate_path),
        'body_path': str(body_path),
        'requirements_dialogue_brief_path': dialogue_brief['artifact_paths']['markdown'],
        'requirements_dialogue_brief_hash': dialogue_brief['brief_hash'],
        'requirements_spec': _requirements_spec_summary(state),
        'generated_at': _now_iso(),
    })
    return StepResult(
        summary='requirements draft generated',
        outputs=[str(gate_path), str(summary_path), dialogue_brief['artifact_paths']['markdown']],
    )


def _wait_for_existing_requirements_draft_if_needed(
    *,
    state: dict[str, Any],
    summary_path: Path,
    summary: dict[str, Any],
    body_path: Path,
    timeout_mtime: float | None,
) -> tuple[Path, dict[str, Any]] | None:
    if str(summary.get('status') or '') not in _PENDING_REQUIREMENTS_DRAFT_STATUSES:
        return None

    candidate = _find_existing_requirements_done_signal(
        summary_path,
        summary,
        body_path=body_path,
        timeout_mtime=timeout_mtime,
    )
    if candidate is not None:
        return candidate

    timeout_seconds = _requirements_draft_resume_timeout_seconds(state)
    deadline = time.monotonic() + timeout_seconds
    poll_seconds = _requirements_draft_resume_poll_seconds(state)
    while time.monotonic() < deadline:
        time.sleep(poll_seconds)
        candidate = _find_existing_requirements_done_signal(
            summary_path,
            summary,
            body_path=body_path,
            timeout_mtime=timeout_mtime,
        )
        if candidate is not None:
            return candidate
    return None


def _requirements_draft_resume_timeout_seconds(state: dict[str, Any]) -> float:
    raw = state.get('requirementsDraftTimeoutSeconds')
    if raw is None:
        raw = state.get('agentTimeoutSeconds')
    if raw is None:
        raw = DEFAULT_AGENT_TIMEOUT_SECONDS
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return float(DEFAULT_AGENT_TIMEOUT_SECONDS)


def _requirements_draft_resume_poll_seconds(state: dict[str, Any]) -> float:
    raw = state.get('requirementsDraftResumePollSeconds')
    if raw is None:
        return DEFAULT_REQUIREMENTS_DRAFT_RESUME_POLL_SECONDS
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return DEFAULT_REQUIREMENTS_DRAFT_RESUME_POLL_SECONDS


def _find_existing_requirements_done_signal(
    summary_path: Path,
    summary: dict[str, Any],
    *,
    body_path: Path,
    timeout_mtime: float | None,
) -> tuple[Path, dict[str, Any]] | None:
    candidates: list[Path] = []
    done_path_text = str(summary.get('done_path') or '').strip()
    if done_path_text:
        candidates.append(Path(done_path_text))

    run_dir_text = str(summary.get('runner_run_dir') or '').strip()
    if run_dir_text:
        candidates.append(Path(run_dir_text) / 'done.json')

    runs_dir = summary_path.parent / 'runs'
    if runs_dir.exists():
        candidates.extend(
            sorted(
                runs_dir.glob('*/done.json'),
                key=lambda path: path.stat().st_mtime if path.exists() else 0,
                reverse=True,
            )
        )

    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen or not candidate.exists():
            continue
        seen.add(candidate)
        payload = _read_json_object(candidate)
        status = str(payload.get('status') or 'done')
        if status == 'pending':
            continue
        if timeout_mtime is not None:
            if candidate.stat().st_mtime <= timeout_mtime:
                continue
            if status == 'done' and (not body_path.exists() or body_path.stat().st_mtime <= timeout_mtime):
                continue
        if status != 'done':
            return candidate, payload
        run_id = str(payload.get('run_id') or '')
        if run_id and run_id != candidate.parent.name:
            continue
        return candidate, payload
    return None


def _requirements_draft_timeout_mtime(summary_path: Path, summary: dict[str, Any]) -> float | None:
    if str(summary.get('status') or '') not in _PENDING_REQUIREMENTS_DRAFT_STATUSES:
        return None
    generated_at = str(summary.get('generated_at') or '').strip()
    if generated_at:
        try:
            return datetime.fromisoformat(generated_at.replace('Z', '+00:00')).timestamp()
        except ValueError:
            pass
    return summary_path.stat().st_mtime


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'{path} is not valid JSON: {exc}') from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f'{path} is not a JSON object')
    return payload


def _requirements_spec_summary(state: dict[str, Any]) -> dict[str, Any] | None:
    spec = state.get('requirementsSpec') if isinstance(state.get('requirementsSpec'), dict) else None
    if not spec:
        return None
    return {
        'path': spec.get('path'),
        'hash': spec.get('hash'),
        'sourceType': spec.get('sourceType'),
        'importedAt': spec.get('importedAt'),
    }
