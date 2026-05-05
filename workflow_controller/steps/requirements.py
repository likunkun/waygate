from __future__ import annotations

from pathlib import Path
from typing import Any

from workflow_controller.runners import RunnerRequest, make_runner, run_agent_backend
from workflow_controller.gates import format_requirements_gate_body, render_requirements_gate_body, write_gate_file
from workflow_controller.prompts.requirements import _render_requirements_draft_prompt
from workflow_controller.requirements_dialogue_brief import write_requirements_dialogue_brief
from workflow_controller.steps._common import StepResult, _write_json, _now_iso


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
            'generated_at': _now_iso(),
        })
        return StepResult(
            summary='requirements draft generated',
            outputs=[str(gate_path), str(summary_path), dialogue_brief['artifact_paths']['markdown']],
        )

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
        timeout_seconds=int(state.get('requirementsDraftTimeoutSeconds') or 1800),
    ))
    _write_json(summary_path, {
        'status': result.status,
        'mode': result.backend,
        'runner_run_dir': str(result.run_dir),
        'done_payload': result.done_payload,
        'agent_command': result.command,
        'runner_metadata': result.runner_metadata,
        'exit_code': result.returncode,
        'stdout': result.stdout,
        'stderr': result.stderr,
        'gate_path': str(gate_path),
        'body_path': str(body_path),
        'requirements_dialogue_brief_path': dialogue_brief['artifact_paths']['markdown'],
        'requirements_dialogue_brief_hash': dialogue_brief['brief_hash'],
        'generated_at': _now_iso(),
    })
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
