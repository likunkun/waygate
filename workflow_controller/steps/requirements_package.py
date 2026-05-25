from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from workflow_controller.prompts.requirements_package import (
    render_architecture_prompt,
    render_product_design_prompt,
    render_scope_prompt,
    render_test_strategy_prompt,
)
from workflow_controller.requirements_package import (
    STAGE_ARTIFACT_FILENAMES,
    mark_stage_artifact,
)
from workflow_controller.runners import RunnerRequest, make_runner, run_agent_backend
from workflow_controller.runners.base import DEFAULT_AGENT_TIMEOUT_SECONDS
from workflow_controller.steps._common import (
    RecoverableAgentWait,
    StepResult,
    _now_iso,
    _write_json,
    is_recoverable_agent_status,
)


STAGE_ARTIFACT_DIRNAMES = {
    'scope': 'requirements-scope',
    'product_design': 'requirements-product-design',
    'architecture': 'requirements-architecture',
    'test_strategy': 'requirements-test-strategy',
}
NEXT_STAGE_STEP = {
    'scope': 'REQUIREMENTS_PRODUCT_DESIGN_BRIEF',
    'product_design': 'REQUIREMENTS_TECH_ARCH_BRIEF',
    'architecture': 'REQUIREMENTS_TEST_STRATEGY_BRIEF',
    'test_strategy': 'REQUIREMENTS_PACKAGE_ASSEMBLE',
}

_PROMPT_RENDERERS: dict[str, Callable[[dict[str, Any], Path], str]] = {
    'scope': lambda state, output_path: render_scope_prompt(state, output_path=output_path),
    'product_design': lambda state, output_path: render_product_design_prompt(state, output_path=output_path),
    'architecture': lambda state, output_path: render_architecture_prompt(state, output_path=output_path),
    'test_strategy': lambda state, output_path: render_test_strategy_prompt(state, output_path=output_path),
}


def run_requirements_package_stage(
    state: dict[str, Any],
    artifacts_dir: Path,
    *,
    stage: str,
    dry_run: bool = False,
) -> StepResult:
    if stage not in _PROMPT_RENDERERS:
        raise ValueError(f'Unsupported requirements package stage: {stage}')

    stage_dir = artifacts_dir / STAGE_ARTIFACT_DIRNAMES[stage]
    stage_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = stage_dir / STAGE_ARTIFACT_FILENAMES[stage]
    summary_path = stage_dir / f'{artifact_path.stem}-summary.json'
    prompt_path = stage_dir / f'{artifact_path.stem}-prompt.md'

    prompt = _PROMPT_RENDERERS[stage](state, artifact_path)
    prompt_path.write_text(prompt, encoding='utf-8')

    if dry_run or state.get('agentRunner') not in {'tmux-claude', 'tmux-codex'}:
        artifact_path.write_text(_local_template_artifact(stage, state), encoding='utf-8')
        record = mark_stage_artifact(state, stage, artifact_path)
        _write_stage_summary(
            summary_path,
            status='ok',
            mode='local-template',
            stage=stage,
            prompt_path=prompt_path,
            artifact_path=artifact_path,
            artifact_record=record,
        )
        return StepResult(
            summary=f'requirements package stage {stage} generated',
            outputs=[str(artifact_path), str(summary_path), str(prompt_path)],
        )

    runner = make_runner(state)
    workspace_path = state.get('executionWorkspacePath') or state.get('workspacePath')
    if not workspace_path:
        raise RuntimeError('requirements package stage runner requires workspacePath or executionWorkspacePath')

    result = run_agent_backend(RunnerRequest(
        backend=runner.backend,
        workspace_dir=Path(workspace_path),
        prompt_path=prompt_path,
        artifact_dir=stage_dir,
        unit_id=f'requirements-{stage}',
        agent_command=runner.agent_command,
        tmux_target=runner.tmux_target,
        role=runner.role,
        env=runner.env,
        timeout_seconds=DEFAULT_AGENT_TIMEOUT_SECONDS,
    ))
    summary_payload = {
        'status': result.status,
        'mode': result.backend,
        'stage': stage,
        'prompt_path': str(prompt_path),
        'artifact_path': str(artifact_path),
        'runner_run_dir': str(result.run_dir),
        'done_path': str(result.done_path) if result.done_path else None,
        'done_payload': result.done_payload,
        'agent_command': result.command,
        'runner_metadata': result.runner_metadata,
        'exit_code': result.returncode,
        'stdout': result.stdout,
        'stderr': result.stderr,
        'generated_at': _now_iso(),
    }
    _write_json(summary_path, summary_payload)
    if is_recoverable_agent_status(result.status):
        raise RecoverableAgentWait(
            f'requirements package stage {stage} waiting for agent completion',
            stage=str(state.get('currentStep') or ''),
            runner_status=result.status,
            summary_path=summary_path,
            run_dir=result.run_dir,
            done_path=result.done_path,
        )
    if result.returncode != 0:
        raise RuntimeError(f'Requirements package stage {stage} failed with exit code {result.returncode}')
    if not artifact_path.exists():
        raise FileNotFoundError(f'Requirements package stage {stage} did not write {artifact_path}')

    record = mark_stage_artifact(state, stage, artifact_path)
    summary_payload.update({
        'status': 'done',
        'artifact_record': record,
        'generated_at': _now_iso(),
    })
    _write_json(summary_path, summary_payload)
    return StepResult(
        summary=f'requirements package stage {stage} generated',
        outputs=[str(artifact_path), str(summary_path), str(prompt_path)],
    )


def _write_stage_summary(
    path: Path,
    *,
    status: str,
    mode: str,
    stage: str,
    prompt_path: Path,
    artifact_path: Path,
    artifact_record: dict[str, str],
) -> None:
    _write_json(path, {
        'status': status,
        'mode': mode,
        'stage': stage,
        'prompt_path': str(prompt_path),
        'artifact_path': str(artifact_path),
        'artifact_record': artifact_record,
        'generated_at': _now_iso(),
    })


def _local_template_artifact(stage: str, state: dict[str, Any]) -> str:
    stage_title = {
        'scope': 'Requirements Scope Checkpoint',
        'product_design': 'Product Design Brief',
        'architecture': 'Technical Architecture Brief',
        'test_strategy': 'Requirements Test Strategy Brief',
    }[stage]
    return (
        f'# {stage_title}\n\n'
        f'- Requested outcome: `{state.get("requestedOutcome")}`\n'
        f'- Current unit: `{state.get("currentUnitId")}`\n'
        f'- Stage: `{stage}`\n'
    )
