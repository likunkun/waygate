from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workflow_controller.runners import RunnerRequest, make_runner, run_agent_backend
from workflow_controller.steps._common import (
    StepResult,
    _now_iso,
    _read_json_object,
    _write_json,
)


FINAL_ACCEPTANCE_SYNC_DIRNAME = 'final-acceptance-sync'
FINAL_ACCEPTANCE_SYNC_SUMMARY = 'final-sync-summary.json'


def final_acceptance_agent_sync_required(state: dict[str, Any]) -> bool:
    if state.get('finalAcceptanceAgentSyncEnabled') is False:
        return False
    workspace_path = state.get('executionWorkspacePath') or state.get('workspacePath')
    if not workspace_path:
        return False
    if state.get('finalAcceptanceAgentSyncEnabled') is True:
        return True
    return bool(state.get('tmuxTarget')) and state.get('agentRunner') in {
        'tmux-claude',
        'tmux-codex',
    }


def run_final_acceptance_agent_sync(
    state: dict[str, Any],
    *,
    state_dir: Path,
    artifacts_dir: Path,
    dry_run: bool = False,
) -> StepResult:
    sync_dir = artifacts_dir / FINAL_ACCEPTANCE_SYNC_DIRNAME
    sync_dir.mkdir(parents=True, exist_ok=True)
    summary_path = sync_dir / FINAL_ACCEPTANCE_SYNC_SUMMARY
    workspace_path = state.get('executionWorkspacePath') or state.get('workspacePath')
    runner = make_runner(state, role='final_sync')

    if dry_run:
        _write_sync_summary(
            summary_path,
            state=state,
            status='skipped',
            mode='dry-run',
            reason='dry run',
        )
        return StepResult(summary='final acceptance agent sync skipped', outputs=[FINAL_ACCEPTANCE_SYNC_SUMMARY])
    if not workspace_path:
        _write_sync_summary(
            summary_path,
            state=state,
            status='skipped',
            mode='no-workspace',
            reason='workspacePath is not configured',
        )
        return StepResult(summary='final acceptance agent sync skipped', outputs=[FINAL_ACCEPTANCE_SYNC_SUMMARY])
    if not final_acceptance_agent_sync_required(state):
        _write_sync_summary(
            summary_path,
            state=state,
            status='skipped',
            mode=runner.backend,
            reason='no live agent pane configured',
        )
        return StepResult(summary='final acceptance agent sync skipped', outputs=[FINAL_ACCEPTANCE_SYNC_SUMMARY])

    prompt_path = sync_dir / 'final-sync-prompt.md'
    prompt_path.write_text(
        _render_final_acceptance_sync_prompt(
            state=state,
            state_dir=state_dir,
            workspace_dir=Path(workspace_path),
            summary_path=summary_path,
        ),
        encoding='utf-8',
    )
    if summary_path.exists():
        summary_path.unlink()

    result = run_agent_backend(
        RunnerRequest(
            backend=runner.backend,
            workspace_dir=Path(workspace_path),
            prompt_path=prompt_path,
            artifact_dir=sync_dir,
            unit_id='final-acceptance-sync',
            agent_command=runner.agent_command,
            tmux_target=runner.tmux_target,
            role='final_sync',
            env=runner.env,
            timeout_seconds=int(state.get('finalAcceptanceAgentSyncTimeoutSeconds') or 1800),
        )
    )
    if result.returncode != 0:
        _write_sync_summary(
            summary_path,
            state=state,
            status='failed',
            mode=result.backend,
            reason=result.stderr.strip() or f'runner returned {result.returncode}',
            runner_result=result,
        )
        raise RuntimeError(f'final acceptance agent sync failed with exit code {result.returncode}')

    summary = _read_json_object(summary_path)
    if not summary:
        _write_sync_summary(
            summary_path,
            state=state,
            status='failed',
            mode=result.backend,
            reason=f'agent did not write {summary_path}',
            runner_result=result,
        )
        raise RuntimeError(f'final acceptance agent sync did not write {summary_path}')
    if str(summary.get('status') or '').lower() not in {'ok', 'done', 'skipped'}:
        raise RuntimeError(
            f"final acceptance agent sync summary has non-ok status: {summary.get('status')}"
        )

    summary.setdefault('task_id', state.get('task_id'))
    summary.setdefault('requested_outcome', state.get('requestedOutcome'))
    summary.setdefault('unit_id', state.get('currentUnitId'))
    summary.setdefault('mode', result.backend)
    summary.setdefault('runner_metadata', result.runner_metadata or {})
    summary.setdefault('generated_at', _now_iso())
    _write_json(summary_path, summary)
    return StepResult(summary='final acceptance agent sync complete', outputs=[FINAL_ACCEPTANCE_SYNC_SUMMARY])


def _write_sync_summary(
    path: Path,
    *,
    state: dict[str, Any],
    status: str,
    mode: str,
    reason: str,
    runner_result: Any | None = None,
) -> None:
    payload: dict[str, Any] = {
        'status': status,
        'mode': mode,
        'reason': reason,
        'task_id': state.get('task_id'),
        'requested_outcome': state.get('requestedOutcome'),
        'unit_id': state.get('currentUnitId'),
        'updated_files': [],
        'generated_at': _now_iso(),
    }
    if runner_result is not None:
        payload.update({
            'runner_metadata': runner_result.runner_metadata or {},
            'exit_code': runner_result.returncode,
            'stdout': runner_result.stdout,
            'stderr': runner_result.stderr,
        })
    _write_json(path, payload)


def _render_final_acceptance_sync_prompt(
    *,
    state: dict[str, Any],
    state_dir: Path,
    workspace_dir: Path,
    summary_path: Path,
) -> str:
    context_files = _existing_workspace_files(
        workspace_dir,
        [
            'AGENTS.md',
            'ROADMAP.md',
            'task_plan.md',
            'progress.md',
            'findings.md',
        ],
    )
    context_files.extend(
        str(path)
        for path in state.get('targetContextFiles') or []
        if str(path).strip() and str(path) not in context_files
    )
    context_lines = '\n'.join(f'- {path}' for path in context_files) or '- None'
    state_json = json.dumps(
        {
            'task_id': state.get('task_id'),
            'requestedOutcome': state.get('requestedOutcome'),
            'currentUnitId': state.get('currentUnitId'),
            'currentStep': state.get('currentStep'),
            'status': state.get('status'),
            'finalAcceptanceAccepted': state.get('finalAcceptanceAccepted'),
            'finalAcceptanceAcceptedBy': state.get('finalAcceptanceAcceptedBy'),
            'finalAcceptanceAcceptedHash': state.get('finalAcceptanceAcceptedHash'),
            'objectiveCoverage': state.get('objectiveCoverage'),
            'units': state.get('units'),
        },
        ensure_ascii=False,
        indent=2,
    )
    return f"""# Final Acceptance Controller Status Sync

Final acceptance has been approved by the controller. The workflow is about to move to release/DONE.

This is a status synchronization task, not an implementation task.

Execution workspace: {workspace_dir}
Controller state dir: {state_dir}
Session fact source: {state_dir / 'session.json'}
Event history: {state_dir / 'events.jsonl'}
Final acceptance gate: {state_dir / 'approvals' / 'final-acceptance.md'}
Sync summary artifact to write: {summary_path}

Controller acceptance snapshot:

```json
{state_json}
```

Read the project agent rules and planning files that exist:
{context_lines}

Required work:
- Read `AGENTS.md` first when present, then `ROADMAP.md`, `task_plan.md`, `progress.md`, `findings.md`, and the controller `session.json`.
- Update the human-readable project status documents that exist in the workspace so they reflect the approved final acceptance.
- If `task_plan.md` still marks the accepted target, version, phase, or unit as `in_progress`, change it to complete.
- Add a short `progress.md` entry for the final acceptance and any status-document changes.
- Add a `findings.md` note only if this final acceptance exposed a workflow decision, defect, or risk.
- Do not modify approved gate files, controller state files, artifacts other than the summary below, source code, tests, package metadata, or unrelated docs.
- Do not invent version scope. Use `ROADMAP.md` and `session.json` as the version and controller-state facts.

When finished, write this exact JSON file:
{summary_path}

Use this schema:

```json
{{
  "status": "ok",
  "updated_files": ["task_plan.md", "progress.md"],
  "notes": ["brief note about what changed"]
}}
```
"""


def _existing_workspace_files(workspace_dir: Path, names: list[str]) -> list[str]:
    paths: list[str] = []
    for name in names:
        path = workspace_dir / name
        if path.exists():
            paths.append(str(path))
    return paths
