from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from workflow_controller.agent_guides import ensure_agent_operating_guides
from workflow_controller.gates.generators import (
    ensure_bug_fix_gate,
    ensure_final_acceptance_gate,
    ensure_requirements_gate,
    ensure_unit_plan_gate,
    normalize_final_acceptance_rejection_routing,
)
from workflow_controller.gates.parsers import (
    FINAL_ACCEPTANCE_REJECTION_ROUTE_ALIASES,
    approve_gate_file,
    check_gate_file,
    extract_patch_list,
    gate_body,
    hash_gate_body,
    write_gate_file,
)
from workflow_controller.acceptance_obligations import (
    append_acceptance_obligations,
    render_acceptance_obligations_markdown,
    write_acceptance_obligation_artifacts,
)
from workflow_controller.gates.validators import (
    apply_unit_plan_state_patch_from_gate,
    migrate_unit_plan_gate_to_state_patch,
    validate_requirements_acceptance_quality,
    validate_required_artifacts,
    validate_review_verdict,
    validate_simplifier_result,
    validate_unit_plan_acceptance_obligation_coverage,
    validate_unit_plan_design_architecture_traceability,
    validate_unit_plan_golden_path,
    validate_unit_plan_test_case_coverage,
    validate_unit_plan_test_strategy,
    validate_unit_plan_verification_environment,
    validate_verification_evidence_schema,
    validate_verification_verdict,
)
from workflow_controller.journeys import (
    validate_final_journey_acceptance,
    validate_and_enrich_journey_unit_plan,
    validate_and_write_journey_contract,
)
from workflow_controller.scope_audit import (
    validate_final_scope_audit,
    write_final_scope_audit,
)
from workflow_controller.spec_sources import (
    requirements_spec_metadata,
    same_requirements_spec,
)
from workflow_controller.prototype_review import (
    prepare_prototype_review_bundle,
    prototype_review_paths,
    start_prototype_review_preview_server,
)
from workflow_controller.rrc_plannotator import run_plannotator_gate_review
from workflow_controller.rrc_real_runtime import (
    VerificationEnvironmentError,
    build_state_from_target_acceptance,
    render_target_acceptance_prompt,
)
from workflow_controller.state_machine.actions import compute_next_allowed_action
from workflow_controller.state_machine.store import StateStore
from workflow_controller.state_machine.transitions import (
    reconcile_state,
    rollback_to_last_verified_step,
    validate_objective_coverage,
)
from workflow_controller.steps._common import (
    TestStrategistBlocked,
    TestStrategistFallbackBlocked,
)
from workflow_controller.steps.builder import (
    ask_human_release_approval,
    ask_human_scope_approval,
    mark_current_unit_covered,
    prepare_builder_prompt,
    run_builder,
    run_refiner,
    run_reviewer,
    run_ui_design_if_needed,
    run_verifier,
    select_next_unit,
    target_acceptance_covered,
)
from workflow_controller.steps.bug_fix import run_bug_fix
from workflow_controller.steps.final_sync import (
    FINAL_ACCEPTANCE_SYNC_DIRNAME,
    FINAL_ACCEPTANCE_SYNC_SUMMARY,
    final_acceptance_agent_sync_required,
    run_final_acceptance_agent_sync,
)
from workflow_controller.steps.requirements import run_requirements_drafter
from workflow_controller.steps.unit_plan import run_unit_plan_drafter


DEFAULT_INITIAL_STATE: dict[str, Any] = {
    'task_id': 'demo-login-flow',
    'currentUnitId': 'unit-01',
    'currentStep': 'PLAN_CREATED',
    'lastVerifiedStep': 'PLAN_CREATED',
    'status': 'active',
    'requestedOutcome': 'usable-system',
    'feasibleOutcome': 'usable-system',
    'scopeApproved': False,
    'autoApprove': False,
    'testStrategistEnabled': False,
    'codeSimplifierEnabled': True,
    'currentUnitNeedsUiDesign': False,
    'objectiveCoverage': [
        {
            'objective': '用户可以完成登录流程',
            'units': ['unit-01'],
            'status': 'partial',
        }
    ],
    'units': [
        {
            'id': 'unit-01',
            'passes': False,
        }
    ],
    'nextAllowedActions': ['require_scope_approval'],
    'blockedReason': None,
    'updatedAt': '2026-04-26T00:00:00+00:00',
}

WAITING_HUMAN_GATE_STEPS = {
    'WAITING_REQUIREMENTS_ACCEPTANCE',
    'WAITING_UNIT_PLAN_APPROVAL',
    'WAITING_FINAL_ACCEPTANCE',
    'WAITING_BUG_FIX_GATE',
}

DEFAULT_MAX_AUTOMATIC_STEPS = 2000
DEFAULT_MAX_NO_PROGRESS_STEPS = 50
DEFAULT_SAME_FAILURE_MAX_RETRIES = 1
DEFAULT_MAX_REQUIREMENTS_AUTO_REVISIONS = 2
DEFAULT_MAX_UNIT_PLAN_AUTO_REVISIONS = 5
COLOR_MODES = ('auto', 'always', 'never')
TMUX_AGENT_BACKENDS = {'tmux-claude', 'tmux-codex'}
TMUX_DETECTED_AGENT_BACKENDS = {
    'claude': 'tmux-claude',
    'codex': 'tmux-codex',
}
ANSI_STYLES = {
    'bold': '\033[1m',
    'dim': '\033[2m',
    'cyan': '\033[36m',
    'green': '\033[32m',
    'yellow': '\033[33m',
    'red': '\033[31m',
    'blue': '\033[34m',
}
ANSI_RESET = '\033[0m'

ACTION_LABELS = {
    'run_requirements_drafter': '生成需求与验收草案',
    'run_unit_plan_drafter': '生成 Unit Plan 草案',
    'check_requirements_acceptance': '检查需求与验收确认',
    'check_unit_plan_approval': '检查 Unit Plan 确认',
    'check_final_acceptance': '检查最终验收确认',
    'sync_final_acceptance_agent': '同步终验状态给 Agent',
    'check_bug_fix_gate': '检查 Bug Fix Gate',
    'run_bug_fix': '运行 Bug Fix Agent',
    'run_bug_fix_verifier': '运行 Bug Fix 回归验证',
    'require_scope_approval': '范围确认',
    'run_ui_design': '生成 UI 设计简报',
    'run_builder': '运行构建器',
    'run_refiner': '运行精修器',
    'run_reviewer': '运行评审器',
    'run_verifier': '运行验证器',
    'complete_unit': '完成当前 Unit',
    'require_release_approval': '发布确认',
}

COMPACT_STAGE_LABELS = {
    'Builder': '构建',
    'Refiner': '精修',
    'Reviewer': '评审',
    'Verifier': '验证',
    'Unit done': '单元完成',
}

COMPACT_PLANNING_STAGE_LABELS = {
    'Requirements draft': '需求草案',
    'Requirements confirmation': '需求确认',
    'Unit plan': 'Unit Plan',
    'Unit plan confirmation': 'Unit Plan确认',
    'Builder': '构建',
}

COMPACT_PLANNING_ACTION_STAGES = {
    'run_requirements_drafter': 'Requirements draft',
    'check_requirements_acceptance': 'Requirements confirmation',
    'run_unit_plan_drafter': 'Unit plan',
    'check_unit_plan_approval': 'Unit plan confirmation',
}

COMPACT_RESULT_LABELS = {
    'ok': '通过',
    'failed': '未通过',
}

COMPACT_RETRY_REASONS = {
    'refinement failed': '精修未通过',
    'review failed': '评审未通过',
    'verification failed': '验证未通过',
}

HUMAN_GATE_LABELS = {
    'requirements': '需求与验收',
    'unit-plan': 'Unit Plan',
    'final-acceptance': '最终验收',
    'bug-fix': 'Bug Fix',
}
HUMAN_REVIEW_TMUX_REMINDER = (
    'Agent结论已形成，已进入人工评审阶段，请不要和Agent再继续沟通！ '
    'The agent has reached its conclusion and the workflow is now in human review. '
    'Please do not continue chatting with the agent.'
)

FINAL_ACCEPTANCE_REJECTION_ROUTE_LABELS = {
    'requirements': 'Requirements revision',
    'defect_fix': 'Defect fix',
    'unit_plan': 'Unit plan revision',
    'implementation': 'Implementation rework',
    'blocked': 'Blocked',
}
FINAL_ACCEPTANCE_REJECTION_ROUTE_PRIORITY = (
    'requirements',
    'defect_fix',
    'unit_plan',
    'implementation',
    'blocked',
)
FINAL_ACCEPTANCE_REJECTION_ROUTE_MESSAGES = {
    'requirements': '最终验收未通过，已回到需求变更流程。',
    'defect_fix': '最终验收未通过，已进入验收缺陷修复流程。',
    'unit_plan': '最终验收未通过，已回到 Unit Plan 修订流程。',
    'implementation': '最终验收未通过，已回到 Builder。',
    'blocked': '最终验收未通过，已阻塞等待人工处理。',
}

GATE_REASON_LABELS = {
    'missing': '文件缺失',
    'not_approved': '待确认',
    'stale': '内容已变更，需要重新确认',
}


class RalphRefinerController:
    def __init__(
        self,
        state_dir: Path | None = None,
        dry_run: bool = False,
        auto_approve: bool = False,
        workspace_dir: Path | None = None,
        agent_command: str | None = 'claude',
        agent_runner: str | None = None,
        tmux_target: str | None = None,
        target: str | None = None,
        unsafe_skip_human_gates: bool = False,
        agent_guides_enabled: bool = True,
        claude_md_enabled: bool = False,
        plannotator_command: str = 'plannotator',
        plannotator_port: int | None = 20000,
        state_dir_explicit: bool = True,
        spec_path: str | Path | None = None,
    ) -> None:
        self.state_dir = state_dir or Path('.plan-ralph')
        self.state_dir_explicit = state_dir_explicit
        self.dry_run = dry_run
        self.auto_approve = auto_approve
        self.workspace_dir = workspace_dir
        self.agent_command = agent_command
        self.agent_runner = agent_runner
        self.tmux_target = tmux_target
        self.target = target
        self.unsafe_skip_human_gates = unsafe_skip_human_gates
        self.agent_guides_enabled = agent_guides_enabled
        self.claude_md_enabled = claude_md_enabled
        self.plannotator_command = plannotator_command
        self.plannotator_port = plannotator_port
        self.spec_path = Path(spec_path) if spec_path else None
        self.store = StateStore(
            session_path=self.state_dir / 'session.json',
            events_path=self.state_dir / 'events.jsonl',
        )
        self.change_requests_path = self.state_dir / 'change_requests.jsonl'
        self.approvals_dir = self.state_dir / 'approvals'
        self.artifacts_dir = self.state_dir / 'artifacts'

    def init_state(
        self,
        initial_state: dict[str, Any] | None = None,
        force: bool = False,
        strategist_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target_workspace_dir: Path | None = None
        if self.target:
            target_workspace_dir = self._target_workspace_dir()
            self._rebase_implicit_state_dir(target_workspace_dir)
        self.store.ensure_layout()
        if self.store.session_path.exists() and not force:
            raise FileExistsError(
                f'Session already exists: {self.store.session_path}. Use --force to overwrite.'
            )
        if self.target:
            workspace_dir = target_workspace_dir or self._target_workspace_dir()
            agent_runner, tmux_target, tmux_resolution = self._resolve_target_agent_runner(
                workspace_dir=workspace_dir,
                state=None,
                allow_auto_create=True,
            )
            state = build_state_from_target_acceptance(
                workspace_dir=workspace_dir,
                target=self.target,
                agent_command=self.agent_command or 'claude',
                agent_runner=agent_runner,
                tmux_target=tmux_target,
            )
            _apply_tmux_target_resolution(state, tmux_resolution)
            prompt_path = self.state_dir / 'target-acceptance-prompt.md'
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            state['promptPath'] = str(prompt_path)
            prompt_path.write_text(render_target_acceptance_prompt(state), encoding='utf-8')
            state.update({
                'humanGatesRequired': True,
                'requirementsAccepted': False,
                'unitPlanAccepted': False,
                'finalAcceptanceAccepted': False,
                'requirementsDraftGenerated': False,
                'currentStep': 'REQUIREMENTS_DRAFT',
                'nextAllowedActions': ['run_requirements_drafter'],
            })
        else:
            state = dict(initial_state or DEFAULT_INITIAL_STATE)
        if self.spec_path:
            state['requirementsSpec'] = requirements_spec_metadata(self.spec_path)
        state['autoApprove'] = self.auto_approve
        state.setdefault('testStrategistEnabled', False)
        state.setdefault('codeSimplifierEnabled', True)
        if strategist_overrides:
            state.update(strategist_overrides)
        state['agentGuideArtifacts'] = ensure_agent_operating_guides(
            _agent_guide_workspace_dir(
                explicit_workspace=self.workspace_dir,
                state_dir=self.state_dir,
                state=state,
            ),
            enabled=self.agent_guides_enabled,
            include_claude=self.claude_md_enabled,
        )
        self._save_state(state)
        return state

    def get_status(self) -> dict[str, Any]:
        state = self.store.load_state()
        state['autoApprove'] = self.auto_approve or state.get('autoApprove', False)
        if self.agent_command:
            state['agentCommand'] = self.agent_command
        before_agent_target = (state.get('agentRunner'), state.get('tmuxTarget'))
        state = self._apply_agent_target_overrides(state, allow_auto_create=False)
        agent_target_changed = before_agent_target != (state.get('agentRunner'), state.get('tmuxTarget'))
        state = reconcile_state(state, self.artifacts_dir)
        before_requirements_validation = _requirements_validation_state_key(state)
        before_validation = _unit_plan_validation_state_key(state)
        state = self._refresh_requirements_gate_validation(state)
        state = self._refresh_unit_plan_gate_validation(state)
        if (
            agent_target_changed
            or _requirements_validation_state_key(state) != before_requirements_validation
            or _unit_plan_validation_state_key(state) != before_validation
        ):
            self._save_state(state)
        state['nextAction'] = compute_next_allowed_action(state)
        return state

    def approve_human_gate(self, gate: str, actor: str = 'human') -> Path:
        state = self.store.load_state()
        current_step = state.get('currentStep')
        if gate == 'requirements':
            if current_step != 'WAITING_REQUIREMENTS_ACCEPTANCE':
                raise ValueError('Requirements can only be approved at WAITING_REQUIREMENTS_ACCEPTANCE')
            gate_path = ensure_requirements_gate(state, self.approvals_dir)
        elif gate == 'unit-plan':
            if current_step != 'WAITING_UNIT_PLAN_APPROVAL':
                raise ValueError('Unit plan can only be approved at WAITING_UNIT_PLAN_APPROVAL')
            gate_path = ensure_unit_plan_gate(state, self.approvals_dir)
        elif gate == 'final-acceptance':
            if current_step != 'WAITING_FINAL_ACCEPTANCE':
                raise ValueError('Final acceptance can only be approved at WAITING_FINAL_ACCEPTANCE')
            self._write_final_scope_audit(state)
            gate_path = ensure_final_acceptance_gate(state, self.approvals_dir, self.artifacts_dir)
        elif gate == 'bug-fix':
            if current_step != 'WAITING_BUG_FIX_GATE':
                raise ValueError('Bug fix gate can only be approved at WAITING_BUG_FIX_GATE')
            gate_path = ensure_bug_fix_gate(state, self.approvals_dir)
        else:
            raise ValueError(f'Unknown human gate: {gate}')
        self._validate_human_gate_before_approval(gate, state, gate_path)
        approve_gate_file(gate_path, actor=actor)
        if gate == 'requirements':
            self._append_pending_requirements_change_request_approval(state, actor)
        self.store.append_event('human_gate_approved', {
            'task_id': state.get('task_id'),
            'gate': gate,
            'actor': actor,
            'path': str(gate_path),
        })
        self._save_state(state)
        return gate_path

    def _validate_human_gate_before_approval(
        self,
        gate: str,
        state: dict[str, Any],
        gate_path: Path,
    ) -> None:
        if gate == 'requirements':
            reason = self._requirements_gate_invalid_reason(state, gate_path)
        elif gate == 'unit-plan':
            reason = self._unit_plan_gate_invalid_reason(state, gate_path)
        elif gate == 'final-acceptance':
            reason = self._final_acceptance_gate_invalid_reason(state)
        else:
            return
        if reason:
            if gate == 'requirements':
                write_gate_file(gate_path, gate_body(gate_path.read_text(encoding='utf-8')))
                state['requirementsAccepted'] = False
                state['currentStep'] = 'WAITING_REQUIREMENTS_ACCEPTANCE'
            elif gate == 'unit-plan':
                write_gate_file(gate_path, gate_body(gate_path.read_text(encoding='utf-8')))
                state['unitPlanAccepted'] = False
                state['currentStep'] = 'WAITING_UNIT_PLAN_APPROVAL'
            else:
                state['finalAcceptanceAccepted'] = False
                state['currentStep'] = 'WAITING_FINAL_ACCEPTANCE'
            state['blockedReason'] = reason
            self._save_state(state)
            raise ValueError(reason)

    def _refresh_unit_plan_gate_validation(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get('currentStep') != 'WAITING_UNIT_PLAN_APPROVAL':
            return state
        gate_path = self.approvals_dir / 'unit-plan.md'
        if not gate_path.exists():
            return state
        reason = self._unit_plan_gate_invalid_reason(state, gate_path)
        if reason:
            state['unitPlanAccepted'] = False
            state['currentStep'] = 'WAITING_UNIT_PLAN_APPROVAL'
            state['blockedReason'] = reason
            return state
        if str(state.get('blockedReason') or '').startswith('unit plan gate invalid:'):
            state['blockedReason'] = None
        return state

    def _refresh_requirements_gate_validation(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get('currentStep') != 'WAITING_REQUIREMENTS_ACCEPTANCE':
            return state
        gate_path = self.approvals_dir / 'requirements-and-acceptance.md'
        if not gate_path.exists():
            return state
        reason = self._requirements_gate_invalid_reason(state, gate_path)
        if reason:
            state['requirementsAccepted'] = False
            state['currentStep'] = 'WAITING_REQUIREMENTS_ACCEPTANCE'
            state['blockedReason'] = reason
            return state
        if str(state.get('blockedReason') or '').startswith('requirements gate invalid:'):
            state['blockedReason'] = None
        return state

    def _unit_plan_gate_invalid_reason(self, state: dict[str, Any], gate_path: Path) -> str | None:
        try:
            candidate_state = apply_unit_plan_state_patch_from_gate(state, gate_path)
            validate_unit_plan_test_strategy(
                self.approvals_dir / 'requirements-and-acceptance.md',
                gate_path,
                candidate_state,
            )
            validate_unit_plan_test_case_coverage(gate_path, candidate_state)
            validate_unit_plan_acceptance_obligation_coverage(gate_path, candidate_state)
            validate_unit_plan_design_architecture_traceability(
                self.approvals_dir / 'requirements-and-acceptance.md',
                gate_path,
                candidate_state,
            )
            validate_unit_plan_verification_environment(candidate_state)
            validate_unit_plan_golden_path(candidate_state)
            validate_and_enrich_journey_unit_plan(
                unit_plan_path=gate_path,
                artifacts_dir=self.artifacts_dir,
                state=candidate_state,
            )
        except ValueError as exc:
            return f'unit plan gate invalid: {exc}'
        return None

    def _requirements_gate_invalid_reason(self, state: dict[str, Any], gate_path: Path) -> str | None:
        try:
            validate_requirements_acceptance_quality(gate_path, state)
            validate_and_write_journey_contract(
                requirements_path=gate_path,
                artifacts_dir=self.artifacts_dir,
                state=state,
                unit_plan_path=self.approvals_dir / 'unit-plan.md',
            )
        except ValueError as exc:
            return f'requirements gate invalid: {exc}'
        return None

    def _prepare_requirements_prototype_review_bundle(self, state: dict[str, Any]) -> None:
        try:
            bundle = prepare_prototype_review_bundle(
                artifacts_dir=self.artifacts_dir,
                requirements_path=self.approvals_dir / 'requirements-and-acceptance.md',
                state=state,
            )
        except ValueError as exc:
            error_path = self.artifacts_dir / 'requirements-draft' / 'prototype-review-error.json'
            error_path.parent.mkdir(parents=True, exist_ok=True)
            error_path.write_text(
                json.dumps(
                    {
                        'status': 'invalid',
                        'error': str(exc),
                        'generated_at': datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + '\n',
                encoding='utf-8',
            )
            self.store.append_event('prototype_review_bundle_invalid', {
                'task_id': state.get('task_id'),
                'error': str(exc),
                'error_path': str(error_path),
            })
            return
        if bundle is None:
            return
        self.store.append_event('prototype_review_bundle_generated', {
            'task_id': state.get('task_id'),
            'review_path': str(bundle.review_path),
            'manifest_path': str(bundle.manifest_path),
            'source_manifest_path': str(bundle.source_manifest_path),
            'prototypes_dir': str(bundle.prototypes_dir),
        })

    def _write_final_scope_audit(self, state: dict[str, Any]) -> dict[str, Any]:
        return write_final_scope_audit(
            state,
            self.artifacts_dir,
            requirements_path=self.approvals_dir / 'requirements-and-acceptance.md',
            workspace_dir=self.workspace_dir,
        )

    def _final_acceptance_gate_invalid_reason(self, state: dict[str, Any]) -> str | None:
        try:
            audit = self._write_final_scope_audit(state)
            validate_final_scope_audit(audit)
            validate_final_journey_acceptance(state, self.artifacts_dir)
        except ValueError as exc:
            return f'final acceptance gate invalid: {exc}'
        return None

    def revise_human_gate(self, gate: str, *, reason: str | None = None) -> Path:
        if gate == 'requirements':
            return self._revise_requirements_gate(change_reason=reason)
        if gate == 'unit-plan':
            return self._revise_unit_plan_gate()
        raise ValueError(f'Unsupported gate revision: {gate}')

    def _revision_feedback_for_gate(self, gate: str, gate_path: Path) -> str:
        feedback, _ = self._revision_feedback_and_annotations_for_gate(gate, gate_path)
        return feedback

    def _acceptance_obligation_feedback_and_annotations_for_gate(
        self,
        gate: str,
        gate_path: Path,
    ) -> tuple[str, list[Any] | None]:
        gate_content = gate_path.read_text(encoding='utf-8')
        plannotator_feedback, plannotator_annotations, _ = _read_plannotator_submitted_feedback(
            self.state_dir,
            gate,
            gate_path,
            gate_content,
        )
        return (plannotator_feedback or '').strip(), plannotator_annotations

    def _revision_feedback_and_annotations_for_gate(
        self,
        gate: str,
        gate_path: Path,
        *,
        allow_controller_validation_only: bool = False,
    ) -> tuple[str, list[Any] | None]:
        gate_content = gate_path.read_text(encoding='utf-8')
        plannotator_feedback, plannotator_annotations, pending_reason = _read_plannotator_submitted_feedback(
            self.state_dir,
            gate,
            gate_path,
            gate_content,
        )
        validation_feedback = self._validation_feedback_for_gate(gate)
        if pending_reason and not (
            (gate == 'requirements' and validation_feedback)
            or (allow_controller_validation_only and validation_feedback)
        ):
            raise ValueError(
                'Plannotator 尚未提交可供 controller 读取的返工反馈；'
                f'{pending_reason}。'
            )
        feedback = _strip_html_comments(gate_content).rstrip()
        if validation_feedback:
            feedback += (
                '\n\n## Controller Validation Error\n\n'
                + validation_feedback.rstrip()
            )
        if plannotator_feedback:
            feedback += (
                '\n\n## Plannotator Feedback\n\n'
                + plannotator_feedback.rstrip()
            )
        return feedback + '\n', plannotator_annotations

    def _validation_feedback_for_gate(self, gate: str) -> str | None:
        state = self.store.load_state()
        reason = str(state.get('blockedReason') or '').strip()
        if gate == 'unit-plan' and reason.startswith('unit plan gate invalid:'):
            return reason
        if gate == 'requirements' and reason.startswith('requirements gate invalid:'):
            return reason
        return None

    def _builder_blocked_unit_plan_revision_feedback(self, state: dict[str, Any]) -> str:
        current_unit_id = str(state.get('currentUnitId') or '').strip()
        if not current_unit_id:
            raise ValueError(
                'Current state does not support Builder recovery to Unit Plan revision: currentUnitId is missing'
            )
        summary_path = self.artifacts_dir / current_unit_id / 'builder-summary.json'
        if not summary_path.exists():
            raise ValueError(
                'Current state does not support Builder recovery to Unit Plan revision: '
                f'missing {summary_path}'
            )
        try:
            builder_summary = json.loads(summary_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise ValueError(
                'Current state does not support Builder recovery to Unit Plan revision: '
                f'{summary_path} is not valid JSON'
            ) from exc
        if not isinstance(builder_summary, dict):
            raise ValueError(
                'Current state does not support Builder recovery to Unit Plan revision: '
                f'{summary_path} is not a JSON object'
            )

        done_payload = builder_summary.get('done_payload')
        if not isinstance(done_payload, dict):
            done_payload = {}
        runner_status = str(builder_summary.get('runner_status') or '').strip().lower()
        done_status = str(done_payload.get('status') or '').strip().lower()
        if runner_status != 'blocked' and done_status != 'blocked':
            raise ValueError(
                'Current state does not support Builder recovery to Unit Plan revision: '
                f'{summary_path} does not show Builder blocked'
            )

        blocker_summary = str(done_payload.get('summary') or '').strip()
        if not blocker_summary:
            blocker_summary = 'Builder reported blocked but did not provide done_payload.summary.'
        return (
            '## Builder Blocked Summary\n\n'
            'Builder returned `blocked` after the approved Unit Plan. '
            'Treat this as Unit Plan revision context, not a Requirements change.\n\n'
            f'{blocker_summary}\n\n'
            f'Builder artifact: {summary_path}\n'
        )

    def _prepend_builder_blocked_unit_plan_feedback(
        self,
        builder_feedback: str,
        revision_feedback: str,
    ) -> str:
        revision_feedback = revision_feedback.strip()
        if not revision_feedback:
            return builder_feedback.rstrip() + '\n'
        return (
            builder_feedback.rstrip()
            + '\n\n## Existing Unit Plan Gate And Human Feedback\n\n'
            + revision_feedback
            + '\n'
        )

    def _optional_builder_blocked_requirements_change_feedback(self, state: dict[str, Any]) -> str | None:
        current_unit_id = str(state.get('currentUnitId') or '').strip()
        if not current_unit_id:
            return None
        summary_path = self.artifacts_dir / current_unit_id / 'builder-summary.json'
        if not summary_path.exists():
            return None
        try:
            builder_summary = json.loads(summary_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            return None
        if not isinstance(builder_summary, dict):
            return None

        done_payload = builder_summary.get('done_payload')
        if not isinstance(done_payload, dict):
            done_payload = {}
        runner_status = str(builder_summary.get('runner_status') or '').strip().lower()
        done_status = str(done_payload.get('status') or '').strip().lower()
        if runner_status != 'blocked' and done_status != 'blocked':
            return None

        blocker_summary = str(done_payload.get('summary') or '').strip()
        if not blocker_summary:
            blocker_summary = 'Builder reported blocked but did not provide done_payload.summary.'
        return (
            '## Recent Builder Blocked Summary\n\n'
            'Builder returned `blocked` after the approved Unit Plan. '
            'Use this as auxiliary context for the Requirements change request; '
            'do not treat it as the only fact source.\n\n'
            f'{blocker_summary}\n\n'
            f'Builder artifact: {summary_path}\n'
        )

    def _requirements_change_revision_feedback(
        self,
        state: dict[str, Any],
        *,
        revision_feedback: str,
        change_reason: str | None,
        include_approved_requirements_change_context: bool,
    ) -> str:
        change_reason = (change_reason or '').strip() or None
        if not change_reason and not include_approved_requirements_change_context:
            return revision_feedback

        sections: list[str] = []
        if include_approved_requirements_change_context:
            sections.append(
                '## Approved Requirements Change Context\n\n'
                '这是 approved Requirements 后的需求变更，不是 Unit Plan 返工。'
                'Unit Plan 只能在已批准 Requirements 内调整实现方案；'
                '如果已批准 Requirements 与可执行实现冲突，必须先变更 Requirements 并重新人工确认。\n\n'
                '本次输出必须是完整的 Requirements Gate，而不是当前 unit 的局部需求。'
                '当前 unit、Unit Plan 和 Builder blocker 只是变更定位上下文；'
                '它们不能替代或缩小已批准 Requirements 的版本范围。\n'
            )
        if include_approved_requirements_change_context and revision_feedback.strip():
            sections.append(
                '## Approved Requirements Baseline (Preserve Unless Explicitly Changed)\n\n'
                '下面是本次变更前已经 approved 的完整 Requirements baseline。'
                '必须保留所有未被本次 `--reason` 或人工反馈明确修改的已批准 Requirements、AC、Journey、'
                'Design/Architecture traceability、范围外、测试策略和人工审阅清单。\n\n'
                '不要把 Requirements 收缩为当前 unit、Builder blocker 或 Unit Plan 片段。'
                '只把本次变更作为 delta 合并进完整 baseline；'
                '如果某条旧需求不受本次变更影响，必须原样或等价保留。\n\n'
                + revision_feedback.strip()
                + '\n'
            )
        if change_reason:
            sections.append(
                '## Human Change Reason\n\n'
                f'{change_reason}\n'
            )
        if include_approved_requirements_change_context:
            unit_plan_path = self.approvals_dir / 'unit-plan.md'
            if unit_plan_path.exists():
                unit_plan_context = _strip_html_comments(unit_plan_path.read_text(encoding='utf-8')).strip()
                sections.append(
                    '## Current Unit Plan Constraint Context\n\n'
                    'The current approved Unit Plan may contain constraints that caused the conflict. '
                    'Use this as context for updating Requirements; do not preserve these constraints '
                    'if the Requirements change intentionally supersedes them.\n\n'
                    f'{unit_plan_context}\n'
                )
            builder_feedback = self._optional_builder_blocked_requirements_change_feedback(state)
            if builder_feedback:
                sections.append(builder_feedback.rstrip())
            sections.append(
                '## Requirements Drafter Instructions For This Change\n\n'
                '- 把变更落实到 Requirements 的需求、验收标准、架构约束、范围外和测试策略；不要只写在评论或说明里。\n'
                '- 更新 AC、Design/Architecture Traceability、Journey、Test Strategy 和 Out of Scope，使新的约束可被 Unit Plan 消费。\n'
                '- 保留 approved baseline 中所有未受影响的需求；不要因为当前执行单元较窄而删除自动生成、小眼睛、前端 UX、closure/E2E 等后续单元需求。\n'
                '- Builder blocked summary 只是辅助上下文；最终需求内容必须以用户变更原因、现有 Requirements 和人工审阅为准。\n'
            )
        if revision_feedback.strip() and not include_approved_requirements_change_context:
            sections.append(
                '## Existing Requirements Gate, Validation Feedback, And Human Feedback\n\n'
                + revision_feedback.strip()
                + '\n'
            )
        return '\n\n'.join(section.rstrip() for section in sections).rstrip() + '\n'

    def _append_acceptance_obligations_from_feedback(
        self,
        state: dict[str, Any],
        *,
        source: str,
        source_ref: str,
        feedback_text: str,
        annotations: list[Any] | None = None,
    ) -> None:
        append_acceptance_obligations(
            state,
            source=source,
            source_ref=source_ref,
            feedback_text=feedback_text,
            annotations=annotations,
        )
        write_acceptance_obligation_artifacts(state, self.artifacts_dir)

    def _consume_plannotator_feedback(self, gate: str, revision_count: int | None) -> None:
        summary_path = _plannotator_summary_path(self.state_dir, gate)
        if not summary_path.exists():
            return
        archive_path = summary_path.with_name(
            f'{gate}-last-review-used-{revision_count or 0}.json'
        )
        if archive_path.exists():
            archive_path.unlink()
        summary_path.rename(archive_path)

    def _write_requirements_revision_artifact(
        self,
        *,
        revision_count: int,
        previous_gate_path: Path,
        updated_gate_path: Path,
        feedback: str,
        annotations: list[Any] | None,
        controller_validation_error: str | None,
        before_body: str,
        after_body: str,
    ) -> Path:
        revisions_dir = self.artifacts_dir / 'requirements-revisions'
        revisions_dir.mkdir(parents=True, exist_ok=True)
        before_hash = hash_gate_body(before_body)
        after_hash = hash_gate_body(after_body)
        generated_at = datetime.now(timezone.utc).isoformat()
        artifact_path = revisions_dir / f'revision-{revision_count}.json'
        payload = {
            'revision_count': revision_count,
            'source_gate': 'requirements',
            'previous_gate_path': str(previous_gate_path),
            'updated_gate_path': str(updated_gate_path),
            'feedback': feedback,
            'annotations': annotations,
            'controller_validation_error': controller_validation_error,
            'before_hash': before_hash,
            'after_hash': after_hash,
            'changed': before_hash != after_hash,
            'diff_summary': _requirements_revision_diff_summary(before_body, after_body),
            'generated_at': generated_at,
        }
        artifact_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        _append_requirements_revision_index(
            revisions_dir / 'requirements-revisions.md',
            artifact_path=artifact_path,
            payload=payload,
        )
        return artifact_path

    def _append_requirements_change_request(
        self,
        state: dict[str, Any],
        *,
        source: str,
        source_gate: str,
        source_ref: str,
        reason: str,
        before_body: str,
        after_body: str,
        previous_gate_path: Path,
        updated_gate_path: Path,
        route: str | None = None,
        revision_count: int | None = None,
        revision_artifact: Path | None = None,
        annotations: list[Any] | None = None,
        controller_validation_error: str | None = None,
    ) -> dict[str, Any]:
        change_request_id = _next_change_request_id(self.change_requests_path)
        before_hash = hash_gate_body(before_body)
        after_hash = hash_gate_body(after_body)
        record = {
            'id': change_request_id,
            'record_type': 'change_request',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'task_id': state.get('task_id'),
            'source': source,
            'source_gate': source_gate,
            'source_ref': source_ref,
            'route': route,
            'reason': reason,
            'impacted': _change_request_impacts(reason, annotations),
            'status': 'pending_requirements_approval',
            'approver': None,
            'approved_at': None,
            'revision_count': revision_count,
            'revision_artifact': str(revision_artifact) if revision_artifact else None,
            'controller_validation_error': controller_validation_error,
            'previous_gate_path': str(previous_gate_path),
            'updated_gate_path': str(updated_gate_path),
            'before_hash': before_hash,
            'after_hash': after_hash,
            'changed': before_hash != after_hash,
        }
        _append_jsonl(self.change_requests_path, record)
        pending_ids = state.setdefault('pendingRequirementChangeRequestIds', [])
        if change_request_id not in pending_ids:
            pending_ids.append(change_request_id)
        return record

    def _append_pending_requirements_change_request_approval(
        self,
        state: dict[str, Any],
        actor: str,
    ) -> None:
        pending_ids = [
            str(item)
            for item in (state.get('pendingRequirementChangeRequestIds') or [])
            if str(item).strip()
        ]
        if not pending_ids:
            return
        approved_at = datetime.now(timezone.utc).isoformat()
        for change_request_id in pending_ids:
            _append_jsonl(self.change_requests_path, {
                'id': change_request_id,
                'record_type': 'change_request_status',
                'created_at': approved_at,
                'task_id': state.get('task_id'),
                'source': 'requirements_approval',
                'source_gate': 'requirements',
                'status': 'approved',
                'approver': actor,
                'approved_at': approved_at,
            })
        state['pendingRequirementChangeRequestIds'] = []
        self._save_state(state)

    def reject_final_acceptance_gate(self) -> Path:
        state = self.store.load_state()
        if state.get('currentStep') != 'WAITING_FINAL_ACCEPTANCE':
            raise ValueError('Final acceptance can only be rejected at WAITING_FINAL_ACCEPTANCE')

        gate_path = ensure_final_acceptance_gate(state, self.approvals_dir, self.artifacts_dir)
        gate_content = gate_path.read_text(encoding='utf-8')
        route = _final_acceptance_rejection_route(gate_content)
        rejection_feedback, rejection_annotations = self._revision_feedback_and_annotations_for_gate('final-acceptance', gate_path)
        self._append_acceptance_obligations_from_feedback(
            state,
            source='final_acceptance_rejection',
            source_ref=f"final-acceptance:rejection-{int(state.get('finalAcceptanceRejectionCount') or 0) + 1}",
            feedback_text=rejection_feedback,
            annotations=rejection_annotations,
        )
        state['finalAcceptanceRejectionFeedback'] = _final_acceptance_rejection_feedback(
            route,
            gate_content,
            rejection_feedback,
        )
        state['finalAcceptanceRejectionRoute'] = route
        state['finalAcceptanceRejectionCount'] = int(state.get('finalAcceptanceRejectionCount') or 0) + 1
        state['finalAcceptanceAccepted'] = False
        state.pop('finalAcceptanceAcceptedHash', None)
        state.pop('finalAcceptanceAcceptedBy', None)
        state['blockedReason'] = None
        state['status'] = 'active'
        change_request: dict[str, Any] | None = None
        if route == 'requirements':
            self._mark_current_unit_incomplete(state)
            change_request = self._route_final_acceptance_rejection_to_requirements(state, rejection_feedback)
        elif route == 'defect_fix':
            state['finalAcceptanceDefectFeedback'] = rejection_feedback
            self._route_final_acceptance_rejection_to_bug_fix(state, rejection_feedback)
        elif route == 'unit_plan':
            self._mark_current_unit_incomplete(state)
            self._route_final_acceptance_rejection_to_unit_plan(state, rejection_feedback)
        elif route == 'implementation':
            self._mark_current_unit_incomplete(state)
            state['currentStep'] = 'EXECUTE_UNIT'
        elif route == 'blocked':
            state['status'] = 'blocked'
            state['currentStep'] = 'WAITING_FINAL_ACCEPTANCE'
            state['blockedReason'] = 'Final acceptance rejected as blocked; resolve the environment, data, access, or evidence issue before continuing.'
        self.store.append_event('final_acceptance_rejected', {
            'task_id': state.get('task_id'),
            'path': str(gate_path),
            'revision_count': state.get('finalAcceptanceRejectionCount'),
            'route': route,
            **({
                'change_request_id': change_request['id'],
                'change_requests_path': str(self.change_requests_path),
            } if change_request else {}),
        })
        self._consume_plannotator_feedback(
            'final-acceptance',
            int(state.get('finalAcceptanceRejectionCount') or 0),
        )
        self._save_state(state)
        return gate_path

    def _route_final_acceptance_rejection_to_requirements(
        self,
        state: dict[str, Any],
        rejection_feedback: str,
    ) -> dict[str, Any]:
        gate_path = self.approvals_dir / 'requirements-and-acceptance.md'
        before_body = (
            gate_body(gate_path.read_text(encoding='utf-8'))
            if gate_path.exists()
            else ''
        )
        state['requirementsRevisionFeedback'] = rejection_feedback
        state['requirementsRevisionCount'] = int(state.get('requirementsRevisionCount') or 0) + 1
        revision_count = int(state.get('requirementsRevisionCount') or 0)
        state['requirementsAccepted'] = False
        state['unitPlanAccepted'] = False
        state.pop('requirementsAcceptedHash', None)
        state.pop('requirementsAcceptedBy', None)
        state.pop('unitPlanAcceptedHash', None)
        state.pop('unitPlanAcceptedBy', None)
        state['requirementsDraftGenerated'] = False
        state['unitPlanDraftGenerated'] = False
        (self.approvals_dir / 'unit-plan.md').unlink(missing_ok=True)

        run_requirements_drafter(state, self.approvals_dir, self.artifacts_dir, dry_run=self.dry_run)
        validate_required_artifacts(
            self.artifacts_dir / 'requirements-draft',
            ['requirements-draft-summary.json', 'requirements-body.md'],
        )
        validate_required_artifacts(self.approvals_dir, ['requirements-and-acceptance.md'])
        self._prepare_requirements_prototype_review_bundle(state)
        after_body = gate_body(gate_path.read_text(encoding='utf-8'))
        change_request = self._append_requirements_change_request(
            state,
            source='final_acceptance_rejection',
            source_gate='final-acceptance',
            source_ref=f"final-acceptance:rejection-{int(state.get('finalAcceptanceRejectionCount') or 0)}",
            route='requirements',
            reason=rejection_feedback,
            before_body=before_body,
            after_body=after_body,
            previous_gate_path=gate_path,
            updated_gate_path=gate_path,
            revision_count=revision_count,
        )

        state.pop('requirementsRevisionFeedback', None)
        state['requirementsDraftGenerated'] = True
        state['currentStep'] = 'WAITING_REQUIREMENTS_ACCEPTANCE'
        return change_request

    def _route_final_acceptance_rejection_to_unit_plan(
        self,
        state: dict[str, Any],
        rejection_feedback: str,
        defect_fix: bool = False,
    ) -> None:
        state['unitPlanRevisionFeedback'] = (
            _defect_fix_unit_plan_revision_feedback(rejection_feedback)
            if defect_fix
            else rejection_feedback
        )
        if defect_fix:
            state['unitPlanRevisionMode'] = 'defect_fix'
        else:
            state.pop('unitPlanRevisionMode', None)
        state['unitPlanRevisionCount'] = int(state.get('unitPlanRevisionCount') or 0) + 1
        state['unitPlanAccepted'] = False
        state.pop('unitPlanAcceptedHash', None)
        state.pop('unitPlanAcceptedBy', None)
        state['unitPlanDraftGenerated'] = False

        try:
            self._run_controller_unit_plan_drafter(state)
        except (TestStrategistBlocked, TestStrategistFallbackBlocked) as exc:
            self._block_on_test_strategist(state, exc)
            return
        validate_required_artifacts(
            self.artifacts_dir / 'unit-plan-draft',
            ['unit-plan-draft-summary.json', 'unit-plan-body.md'],
        )
        validate_required_artifacts(self.approvals_dir, ['unit-plan.md'])

        state.pop('unitPlanRevisionFeedback', None)
        state['unitPlanDraftGenerated'] = True
        state['currentStep'] = 'WAITING_UNIT_PLAN_APPROVAL'
        state = self._refresh_unit_plan_gate_validation(state)

    def _route_final_acceptance_rejection_to_bug_fix(
        self,
        state: dict[str, Any],
        rejection_feedback: str,
    ) -> None:
        state['bugFixAttemptCount'] = int(state.get('bugFixAttemptCount') or 0) + 1
        state['activeBugFixId'] = f"bug-fix-{state['bugFixAttemptCount']}"
        state['bugFixGateGenerated'] = True
        state['bugFixGateAccepted'] = False
        state['bugFixVerified'] = False
        state['bugFixFeedback'] = rejection_feedback
        state['finalAcceptanceAccepted'] = False
        state.pop('finalAcceptanceAcceptedHash', None)
        state.pop('finalAcceptanceAcceptedBy', None)
        state.pop('unitPlanRevisionMode', None)
        state['currentStep'] = 'WAITING_BUG_FIX_GATE'
        ensure_bug_fix_gate(state, self.approvals_dir)

    def _mark_current_unit_incomplete(self, state: dict[str, Any]) -> None:
        current_unit_id = state.get('currentUnitId')
        if not current_unit_id:
            return
        for unit in state.get('units') or []:
            if unit.get('id') == current_unit_id:
                unit['passes'] = False
        for coverage in state.get('objectiveCoverage') or []:
            if current_unit_id in (coverage.get('units') or []):
                coverage['status'] = 'partial'

    def _revise_requirements_gate(
        self,
        *,
        controller_validation_only: bool = False,
        change_reason: str | None = None,
    ) -> Path:
        state = self.store.load_state()
        current_step = str(state.get('currentStep') or '')
        if current_step == 'WAITING_FINAL_ACCEPTANCE':
            raise ValueError(
                'Requirements cannot be revised directly at WAITING_FINAL_ACCEPTANCE; '
                'use the final acceptance rejection route and select Requirements revision.'
            )
        if current_step not in {
            'WAITING_REQUIREMENTS_ACCEPTANCE',
            'WAITING_UNIT_PLAN_APPROVAL',
            'PLAN_APPROVED',
            'EXECUTE_UNIT',
        }:
            raise ValueError(
                'Requirements can only be revised at WAITING_REQUIREMENTS_ACCEPTANCE, '
                'WAITING_UNIT_PLAN_APPROVAL, PLAN_APPROVED, or EXECUTE_UNIT'
            )

        gate_path = self.approvals_dir / 'requirements-and-acceptance.md'
        if not gate_path.exists():
            raise FileNotFoundError(
                f'Requirements gate not found: {gate_path}. Run the requirements drafter first.'
            )

        before_body = gate_body(gate_path.read_text(encoding='utf-8'))
        controller_validation_error = self._validation_feedback_for_gate('requirements')
        raw_revision_feedback, requirements_annotations = self._revision_feedback_and_annotations_for_gate('requirements', gate_path)
        state['requirementsRevisionFeedback'] = self._requirements_change_revision_feedback(
            state,
            revision_feedback=raw_revision_feedback,
            change_reason=change_reason,
            include_approved_requirements_change_context=current_step in {'PLAN_APPROVED', 'EXECUTE_UNIT'},
        )
        state['requirementsRevisionCount'] = int(state.get('requirementsRevisionCount') or 0) + 1
        revision_count = int(state.get('requirementsRevisionCount') or 0)
        revision_feedback = state['requirementsRevisionFeedback']
        if not controller_validation_only:
            obligation_feedback, obligation_annotations = self._acceptance_obligation_feedback_and_annotations_for_gate(
                'requirements',
                gate_path,
            )
            if obligation_feedback or obligation_annotations:
                self._append_acceptance_obligations_from_feedback(
                    state,
                    source='requirements_feedback',
                    source_ref=f"requirements:revision-{revision_count}",
                    feedback_text=obligation_feedback,
                    annotations=obligation_annotations,
                )
        state['requirementsAccepted'] = False
        state['unitPlanAccepted'] = False
        state.pop('requirementsAcceptedHash', None)
        state.pop('requirementsAcceptedBy', None)
        state.pop('unitPlanAcceptedHash', None)
        state.pop('unitPlanAcceptedBy', None)
        state['requirementsDraftGenerated'] = False
        state['unitPlanDraftGenerated'] = False
        state['status'] = 'active'
        state['blockedReason'] = None
        (self.approvals_dir / 'unit-plan.md').unlink(missing_ok=True)

        run_requirements_drafter(state, self.approvals_dir, self.artifacts_dir, dry_run=self.dry_run)
        validate_required_artifacts(
            self.artifacts_dir / 'requirements-draft',
            ['requirements-draft-summary.json', 'requirements-body.md'],
        )
        validate_required_artifacts(self.approvals_dir, ['requirements-and-acceptance.md'])
        self._prepare_requirements_prototype_review_bundle(state)
        after_body = gate_body(gate_path.read_text(encoding='utf-8'))
        revision_artifact = self._write_requirements_revision_artifact(
            revision_count=revision_count,
            previous_gate_path=gate_path,
            updated_gate_path=gate_path,
            feedback=revision_feedback,
            annotations=requirements_annotations,
            controller_validation_error=controller_validation_error,
            before_body=before_body,
            after_body=after_body,
        )
        change_request = self._append_requirements_change_request(
            state,
            source='requirements_revision',
            source_gate='requirements',
            source_ref=f'requirements:revision-{revision_count}',
            reason=revision_feedback,
            before_body=before_body,
            after_body=after_body,
            previous_gate_path=gate_path,
            updated_gate_path=gate_path,
            revision_count=revision_count,
            revision_artifact=revision_artifact,
            annotations=requirements_annotations,
            controller_validation_error=controller_validation_error,
        )

        state.pop('requirementsRevisionFeedback', None)
        state['requirementsDraftGenerated'] = True
        state['currentStep'] = 'WAITING_REQUIREMENTS_ACCEPTANCE'
        self._consume_plannotator_feedback(
            'requirements',
            revision_count,
        )
        self.store.append_event('requirements_draft_revised', {
            'task_id': state.get('task_id'),
            'path': str(gate_path),
            'revision_count': revision_count,
            'revision_artifact': str(revision_artifact),
            'change_request_id': change_request['id'],
            'change_requests_path': str(self.change_requests_path),
        })
        self._save_state(state)
        return gate_path

    def _revise_unit_plan_gate(self, *, controller_validation_only: bool = False) -> Path:
        state = self.store.load_state()
        current_step = state.get('currentStep')
        builder_blocked_feedback: str | None = None
        if current_step == 'WAITING_UNIT_PLAN_APPROVAL':
            pass
        elif current_step in {'PLAN_APPROVED', 'EXECUTE_UNIT'}:
            builder_blocked_feedback = self._builder_blocked_unit_plan_revision_feedback(state)
        else:
            raise ValueError('Unit plan can only be revised at WAITING_UNIT_PLAN_APPROVAL')

        gate_path = self.approvals_dir / 'unit-plan.md'
        if not gate_path.exists():
            raise FileNotFoundError(
                f'Unit plan gate not found: {gate_path}. Run the unit plan drafter first.'
            )

        revision_feedback, unit_plan_annotations = self._revision_feedback_and_annotations_for_gate(
            'unit-plan',
            gate_path,
            allow_controller_validation_only=controller_validation_only,
        )
        if builder_blocked_feedback:
            revision_feedback = self._prepend_builder_blocked_unit_plan_feedback(
                builder_blocked_feedback,
                revision_feedback,
            )
        state['unitPlanRevisionFeedback'] = revision_feedback
        state['unitPlanRevisionCount'] = int(state.get('unitPlanRevisionCount') or 0) + 1
        if not controller_validation_only:
            obligation_feedback, obligation_annotations = self._acceptance_obligation_feedback_and_annotations_for_gate(
                'unit-plan',
                gate_path,
            )
            if obligation_feedback or obligation_annotations:
                self._append_acceptance_obligations_from_feedback(
                    state,
                    source='unit_plan_feedback',
                    source_ref=f"unit-plan:revision-{state['unitPlanRevisionCount']}",
                    feedback_text=obligation_feedback,
                    annotations=obligation_annotations,
                )
        state['unitPlanAccepted'] = False
        state.pop('unitPlanAcceptedHash', None)
        state.pop('unitPlanAcceptedBy', None)
        state['unitPlanDraftGenerated'] = False
        state['status'] = 'active'
        state['blockedReason'] = None

        try:
            self._run_controller_unit_plan_drafter(state)
        except (TestStrategistBlocked, TestStrategistFallbackBlocked) as exc:
            self._block_on_test_strategist(state, exc)
            self._save_state(state)
            return gate_path
        validate_required_artifacts(
            self.artifacts_dir / 'unit-plan-draft',
            ['unit-plan-draft-summary.json', 'unit-plan-body.md'],
        )
        validate_required_artifacts(self.approvals_dir, ['unit-plan.md'])

        state.pop('unitPlanRevisionFeedback', None)
        state['unitPlanDraftGenerated'] = True
        state['unitPlanAccepted'] = False
        state['currentStep'] = 'WAITING_UNIT_PLAN_APPROVAL'
        state = self._refresh_unit_plan_gate_validation(state)
        self._consume_plannotator_feedback(
            'unit-plan',
            int(state.get('unitPlanRevisionCount') or 0),
        )
        self.store.append_event('unit_plan_draft_revised', {
            'task_id': state.get('task_id'),
            'path': str(gate_path),
            'revision_count': state.get('unitPlanRevisionCount'),
        })
        self._save_state(state)
        return gate_path

    def migrate_state(self) -> dict[str, Any]:
        state = self.store.load_state()
        migrated: list[str] = []

        unit_plan_path = self.approvals_dir / 'unit-plan.md'
        if unit_plan_path.exists() and migrate_unit_plan_gate_to_state_patch(state, unit_plan_path):
            migrated.append(str(unit_plan_path))

        state['migrationVersion'] = 1
        self.store.append_event('state_migrated', {
            'task_id': state.get('task_id'),
            'paths': migrated,
        })
        self._save_state(state)
        state['migratedPaths'] = migrated
        return state

    def start(
        self,
        force: bool = False,
        max_steps: int = DEFAULT_MAX_AUTOMATIC_STEPS,
        verbose: bool = False,
        color_mode: str = 'auto',
        actor: str = 'human',
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print,
        timestamp_output: bool = True,
        strategist_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if timestamp_output:
            output_func = _timestamped_output(output_func)

        if self.target:
            self._rebase_implicit_state_dir(self._target_workspace_dir())

        if self.store.session_path.exists():
            if force:
                output_func('[初始化] --force 已指定，重新创建 controller 状态')
                state_for_report = self.init_state(force=True, strategist_overrides=strategist_overrides)
            else:
                existing_state = self.store.load_state()
                existing_state = self._apply_agent_target_overrides(existing_state, allow_auto_create=True)
                self._validate_start_compatible(existing_state)
                self._save_state(existing_state)
                output_func(f'[继续] 使用已有状态：{self.store.session_path}')
                state_for_report = existing_state
        else:
            output_func('[初始化] 创建新的 controller 状态')
            state_for_report = self.init_state(force=False, strategist_overrides=strategist_overrides)

        self._print_agent_target_resolution(state_for_report, output_func)

        return self.drive(
            max_steps=max_steps,
            verbose=verbose,
            color_mode=color_mode,
            actor=actor,
            input_func=input_func,
            output_func=output_func,
            timestamp_output=False,
            print_agent_target=False,
        )

    def _validate_start_compatible(self, state: dict[str, Any]) -> None:
        mismatches: list[str] = []
        if self.target and str(state.get('requestedOutcome') or '') != self.target:
            mismatches.append(
                f"--target={self.target} but session requestedOutcome={state.get('requestedOutcome')}"
            )
        if self.agent_runner and state.get('agentRunner') and state.get('agentRunner') != self.agent_runner:
            mismatches.append(
                f"--runner={self.agent_runner} but session agentRunner={state.get('agentRunner')}"
            )
        if self.tmux_target and state.get('tmuxTarget') and state.get('tmuxTarget') != self.tmux_target:
            mismatches.append(
                f"--tmux-target={self.tmux_target} but session tmuxTarget={state.get('tmuxTarget')}"
            )
        if self.agent_command and state.get('agentCommand') and state.get('agentCommand') != self.agent_command:
            mismatches.append(
                f"--agent={self.agent_command} but session agentCommand={state.get('agentCommand')}"
            )
        if self.workspace_dir and state.get('workspacePath'):
            requested_workspace = self.workspace_dir.expanduser().resolve()
            session_workspace = Path(str(state['workspacePath'])).expanduser().resolve()
            if requested_workspace != session_workspace:
                mismatches.append(
                    f"--workspace-dir={requested_workspace} but session workspacePath={session_workspace}"
                )
        if self.spec_path:
            incoming_spec = requirements_spec_metadata(self.spec_path)
            existing_spec = state.get('requirementsSpec') if isinstance(state.get('requirementsSpec'), dict) else None
            if existing_spec and not same_requirements_spec(existing_spec, incoming_spec):
                mismatches.append(
                    'Existing session already has requirementsSpec.path='
                    f"{existing_spec.get('path')} but --spec={incoming_spec.get('path')}"
                )
            elif not existing_spec:
                mismatches.append(
                    'Existing session has no requirementsSpec; use --force to initialize with --spec'
                )
        if mismatches:
            raise ValueError(
                'Existing session does not match start arguments: '
                + '; '.join(mismatches)
                + '. Use --force to reinitialize.'
            )

    def _target_workspace_dir(self) -> Path:
        if self.workspace_dir is not None:
            return self.workspace_dir
        if self.tmux_target:
            pane_path = _tmux_target_current_path(
                self.tmux_target,
                Path.cwd(),
                tmux_command=_tmux_command_for_controller(self.agent_command),
            )
            if pane_path is not None:
                return pane_path
        return Path.cwd()

    def _rebase_implicit_state_dir(self, workspace_dir: Path) -> None:
        if self.state_dir_explicit or self.state_dir.is_absolute() or self.state_dir.parent != Path('.'):
            return
        self.state_dir = workspace_dir / self.state_dir
        self.store = StateStore(
            session_path=self.state_dir / 'session.json',
            events_path=self.state_dir / 'events.jsonl',
        )
        self.change_requests_path = self.state_dir / 'change_requests.jsonl'
        self.approvals_dir = self.state_dir / 'approvals'
        self.artifacts_dir = self.state_dir / 'artifacts'

    def _resolve_target_agent_runner(
        self,
        *,
        workspace_dir: Path,
        state: dict[str, Any] | None,
        allow_auto_create: bool,
    ) -> tuple[str, str | None, dict[str, Any] | None]:
        explicit_tmux_target = bool(self.tmux_target)
        tmux_target = self.tmux_target or (str(state.get('tmuxTarget')) if state and state.get('tmuxTarget') else None)
        explicit_runner = self.agent_runner
        state_runner = str(state.get('agentRunner')) if state and state.get('agentRunner') else None
        agent_runner = explicit_runner or state_runner

        if tmux_target:
            inspection = _inspect_tmux_target(
                tmux_target,
                workspace_dir,
                tmux_command=_tmux_command_for_controller(self.agent_command),
            )
            detected_backend = inspection.get('detectedBackend')
            if (
                allow_auto_create
                and not explicit_tmux_target
                and state
                and _is_auto_created_tmux_claude_target(state, tmux_target)
                and _tmux_target_inspection_is_missing(inspection)
            ):
                tmux_target = _create_tmux_claude_pane(workspace_dir)
                self.agent_runner = 'tmux-claude'
                self.tmux_target = tmux_target
                return 'tmux-claude', tmux_target, _auto_created_tmux_target_resolution(tmux_target, workspace_dir)
            if detected_backend and explicit_runner and explicit_runner != detected_backend:
                raise ValueError(
                    f'--runner={explicit_runner} conflicts with detected {detected_backend} '
                    f'agent in --tmux-target={tmux_target} '
                    f'({_format_tmux_inspection_details(inspection)})'
                )
            resolved_runner = detected_backend or agent_runner or 'tmux-codex'
            self.agent_runner = resolved_runner
            self.tmux_target = tmux_target
            return resolved_runner, tmux_target, _tmux_target_resolution(
                target=tmux_target,
                runner=resolved_runner,
                inspection=inspection,
                source=_tmux_resolution_source(
                    detected_backend=detected_backend,
                    explicit_runner=explicit_runner,
                    state_runner=state_runner,
                ),
            )

        if agent_runner == 'tmux-codex':
            inspection = _discover_tmux_agent_target(
                'tmux-codex',
                workspace_dir,
                tmux_command=_tmux_command_for_controller(self.agent_command),
            )
            if inspection:
                tmux_target = str(inspection.get('target') or '').strip()
                self.agent_runner = 'tmux-codex'
                self.tmux_target = tmux_target
                return 'tmux-codex', tmux_target, _tmux_target_resolution(
                    target=tmux_target,
                    runner='tmux-codex',
                    inspection=inspection,
                    source='auto-detected',
                )
            raise ValueError(
                '--runner=tmux-codex requires --tmux-target pointing at an existing Codex pane '
                'or a discoverable Codex pane in the current tmux session'
            )

        if agent_runner == 'tmux-claude' or agent_runner is None:
            if not allow_auto_create and agent_runner is None:
                raise ValueError('No tmux target configured for this target acceptance session')
            tmux_target = _create_tmux_claude_pane(workspace_dir)
            self.agent_runner = 'tmux-claude'
            self.tmux_target = tmux_target
            return 'tmux-claude', tmux_target, _auto_created_tmux_target_resolution(tmux_target, workspace_dir)

        self.agent_runner = agent_runner
        return agent_runner, None, None

    def _apply_agent_target_overrides(self, state: dict[str, Any], *, allow_auto_create: bool) -> dict[str, Any]:
        workspace_dir = _agent_guide_workspace_dir(
            explicit_workspace=self.workspace_dir,
            state_dir=self.state_dir,
            state=state,
        )

        if self.tmux_target:
            agent_runner, tmux_target, tmux_resolution = self._resolve_target_agent_runner(
                workspace_dir=workspace_dir,
                state=state,
                allow_auto_create=False,
            )
            state['agentRunner'] = agent_runner
            state['tmuxTarget'] = tmux_target
            _apply_tmux_target_resolution(state, tmux_resolution)
            return state

        if self.agent_runner:
            if self.agent_runner in TMUX_AGENT_BACKENDS:
                agent_runner, tmux_target, tmux_resolution = self._resolve_target_agent_runner(
                    workspace_dir=workspace_dir,
                    state=state,
                    allow_auto_create=allow_auto_create,
                )
                state['agentRunner'] = agent_runner
                state['tmuxTarget'] = tmux_target
                _apply_tmux_target_resolution(state, tmux_resolution)
            else:
                state['agentRunner'] = self.agent_runner
                _apply_tmux_target_resolution(state, None)
            return state

        if state.get('tmuxTarget') and not state.get('agentRunner'):
            agent_runner, tmux_target, tmux_resolution = self._resolve_target_agent_runner(
                workspace_dir=workspace_dir,
                state=state,
                allow_auto_create=False,
            )
            state['agentRunner'] = agent_runner
            state['tmuxTarget'] = tmux_target
            _apply_tmux_target_resolution(state, tmux_resolution)
            return state

        if state.get('tmuxTarget') and _is_auto_created_tmux_claude_target(state, str(state.get('tmuxTarget'))):
            agent_runner, tmux_target, tmux_resolution = self._resolve_target_agent_runner(
                workspace_dir=workspace_dir,
                state=state,
                allow_auto_create=allow_auto_create,
            )
            state['agentRunner'] = agent_runner
            state['tmuxTarget'] = tmux_target
            _apply_tmux_target_resolution(state, tmux_resolution)
            return state

        if (
            allow_auto_create
            and _is_target_acceptance_state(state)
            and not state.get('agentRunner')
            and not state.get('tmuxTarget')
        ):
            agent_runner, tmux_target, tmux_resolution = self._resolve_target_agent_runner(
                workspace_dir=workspace_dir,
                state=state,
                allow_auto_create=True,
            )
            state['agentRunner'] = agent_runner
            state['tmuxTarget'] = tmux_target
            _apply_tmux_target_resolution(state, tmux_resolution)
        return state

    def _print_agent_target_resolution(
        self,
        state: dict[str, Any],
        output_func: Callable[[str], None],
    ) -> None:
        message = _format_tmux_target_resolution(state.get('tmuxTargetResolution'))
        if message:
            output_func(message)

    def _run_controller_unit_plan_drafter(
        self,
        state: dict[str, Any],
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        effective_callback = progress_callback or getattr(self, '_drive_progress_callback', None)
        state['testStrategistCriticalReworkRequired'] = True
        try:
            run_unit_plan_drafter(
                state,
                self.approvals_dir,
                self.artifacts_dir,
                dry_run=self.dry_run,
                progress_callback=effective_callback,
            )
        finally:
            state.pop('testStrategistCriticalReworkRequired', None)

    def _block_on_test_strategist(
        self,
        state: dict[str, Any],
        exc: TestStrategistBlocked | TestStrategistFallbackBlocked,
    ) -> None:
        state['status'] = 'blocked'
        state['currentStep'] = 'UNIT_PLAN_DRAFT'
        state['blockedReason'] = str(exc)
        if isinstance(exc, TestStrategistBlocked):
            state['testStrategistPlannerRetryCount'] = exc.retry_count
            state['unitPlanRetryCount'] = exc.retry_count
        self.store.append_event('unit_plan_draft_blocked', {
            'task_id': state.get('task_id'),
            'reason': str(exc),
        })

    def run_once(self) -> dict[str, Any]:
        return self._run_once()

    def _run_once(
        self,
        verification_progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        state = self.store.load_state()
        state['autoApprove'] = self.auto_approve or state.get('autoApprove', False)
        state = reconcile_state(state, self.artifacts_dir)

        if state.get('status') == 'blocked':
            self._save_state(state)
            return state

        action = compute_next_allowed_action(state)
        state['nextAllowedActions'] = [action] if action else []
        if action is None:
            self._save_state(state)
            return state

        current_unit_id = state.get('currentUnitId')
        unit_dir = self.artifacts_dir / current_unit_id if current_unit_id else self.artifacts_dir
        unit_dir.mkdir(parents=True, exist_ok=True)
        self.approvals_dir.mkdir(parents=True, exist_ok=True)

        if action == 'run_requirements_drafter':
            run_requirements_drafter(state, self.approvals_dir, self.artifacts_dir, dry_run=self.dry_run)
            validate_required_artifacts(self.artifacts_dir / 'requirements-draft', ['requirements-draft-summary.json', 'requirements-body.md'])
            validate_required_artifacts(self.approvals_dir, ['requirements-and-acceptance.md'])
            self._prepare_requirements_prototype_review_bundle(state)
            state['requirementsDraftGenerated'] = True
            state['currentStep'] = 'WAITING_REQUIREMENTS_ACCEPTANCE'
            self.store.append_event('requirements_draft_generated', {
                'task_id': state.get('task_id'),
                'path': str(self.approvals_dir / 'requirements-and-acceptance.md'),
            })
            state = self._auto_revise_invalid_requirements_draft(state)
            self._save_state(state)
            return state

        if action == 'run_unit_plan_drafter':
            try:
                self._run_controller_unit_plan_drafter(state)
            except (TestStrategistBlocked, TestStrategistFallbackBlocked) as exc:
                self._block_on_test_strategist(state, exc)
                self._save_state(state)
                return state
            validate_required_artifacts(self.artifacts_dir / 'unit-plan-draft', ['unit-plan-draft-summary.json', 'unit-plan-body.md'])
            validate_required_artifacts(self.approvals_dir, ['unit-plan.md'])
            state['unitPlanDraftGenerated'] = True
            state['unitPlanAccepted'] = False
            state['currentStep'] = 'WAITING_UNIT_PLAN_APPROVAL'
            state = self._refresh_unit_plan_gate_validation(state)
            state = self._auto_revise_invalid_unit_plan_draft(state)
            self.store.append_event('unit_plan_draft_generated', {
                'task_id': state.get('task_id'),
                'path': str(self.approvals_dir / 'unit-plan.md'),
            })
            self._save_state(state)
            return state

        if action == 'check_requirements_acceptance':
            gate_path = ensure_requirements_gate(state, self.approvals_dir)
            if self._unsafe_skip_gate(state, 'requirements_acceptance', gate_path):
                state['requirementsAccepted'] = True
                state['unitPlanDraftGenerated'] = False
                state['currentStep'] = 'UNIT_PLAN_DRAFT'
                self._save_state(state)
                return state
            gate = check_gate_file(gate_path)
            state['requirementsAccepted'] = gate.approved
            if gate.approved:
                reason = self._requirements_gate_invalid_reason(state, gate_path)
                if reason:
                    state['requirementsAccepted'] = False
                    state['currentStep'] = 'WAITING_REQUIREMENTS_ACCEPTANCE'
                    state['blockedReason'] = reason
                    self._save_state(state)
                    return state
                state['requirementsAcceptedHash'] = gate.content_hash
                state['requirementsAcceptedBy'] = gate.confirmed_by
                state['blockedReason'] = None
                state['unitPlanDraftGenerated'] = False
                state['currentStep'] = 'UNIT_PLAN_DRAFT'
                self.store.append_event('requirements_acceptance_approved', {
                    'task_id': state.get('task_id'),
                    'path': str(gate_path),
                    'content_hash': gate.content_hash,
                    'confirmed_by': gate.confirmed_by,
                })
            else:
                state['blockedReason'] = f'requirements acceptance gate not approved: {gate.reason}'
            self._save_state(state)
            return state

        if action == 'check_unit_plan_approval':
            gate_path = ensure_unit_plan_gate(state, self.approvals_dir)
            if self._unsafe_skip_gate(state, 'unit_plan', gate_path):
                state['unitPlanAccepted'] = True
                state['lastVerifiedStep'] = 'PLAN_CREATED'
                state['currentStep'] = 'PLAN_APPROVED' if state.get('scopeApproved') else 'PLAN_CREATED'
                self._save_state(state)
                return state
            gate = check_gate_file(gate_path)
            state['unitPlanAccepted'] = gate.approved
            if gate.approved:
                try:
                    state = apply_unit_plan_state_patch_from_gate(state, gate_path)
                    validate_unit_plan_test_strategy(
                        self.approvals_dir / 'requirements-and-acceptance.md',
                        gate_path,
                        state,
                    )
                    validate_unit_plan_test_case_coverage(gate_path, state)
                    validate_unit_plan_acceptance_obligation_coverage(gate_path, state)
                    validate_unit_plan_design_architecture_traceability(
                        self.approvals_dir / 'requirements-and-acceptance.md',
                        gate_path,
                        state,
                    )
                    validate_unit_plan_verification_environment(state)
                    validate_unit_plan_golden_path(state)
                    validate_and_enrich_journey_unit_plan(
                        unit_plan_path=gate_path,
                        artifacts_dir=self.artifacts_dir,
                        state=state,
                    )
                except ValueError as exc:
                    state['unitPlanAccepted'] = False
                    state['currentStep'] = 'WAITING_UNIT_PLAN_APPROVAL'
                    state['blockedReason'] = f'unit plan gate invalid: {exc}'
                    self._save_state(state)
                    return state
                state['unitPlanAcceptedHash'] = gate.content_hash
                state['unitPlanAcceptedBy'] = gate.confirmed_by
                state['blockedReason'] = None
                state['lastVerifiedStep'] = 'PLAN_CREATED'
                state['currentStep'] = 'PLAN_APPROVED' if state.get('scopeApproved') else 'PLAN_CREATED'
                self.store.append_event('unit_plan_approved', {
                    'task_id': state.get('task_id'),
                    'path': str(gate_path),
                    'content_hash': gate.content_hash,
                    'confirmed_by': gate.confirmed_by,
                })
            else:
                state['blockedReason'] = f'unit plan gate not approved: {gate.reason}'
            self._save_state(state)
            return state

        if action == 'check_final_acceptance':
            self._write_final_scope_audit(state)
            gate_path = ensure_final_acceptance_gate(state, self.approvals_dir, self.artifacts_dir)
            if self._unsafe_skip_gate(state, 'final_acceptance', gate_path):
                state['finalAcceptanceAccepted'] = True
                self._advance_after_final_acceptance_approval(state)
                self._save_state(state)
                return state
            gate = check_gate_file(gate_path)
            state['finalAcceptanceAccepted'] = gate.approved
            if gate.approved:
                reason = self._final_acceptance_gate_invalid_reason(state)
                if reason:
                    state['finalAcceptanceAccepted'] = False
                    state['currentStep'] = 'WAITING_FINAL_ACCEPTANCE'
                    state['blockedReason'] = reason
                    self._save_state(state)
                    return state
                state['finalAcceptanceAcceptedHash'] = gate.content_hash
                state['finalAcceptanceAcceptedBy'] = gate.confirmed_by
                state.pop('finalAcceptanceRejectionFeedback', None)
                state['blockedReason'] = None
                self._advance_after_final_acceptance_approval(state)
                self.store.append_event('final_acceptance_approved', {
                    'task_id': state.get('task_id'),
                    'path': str(gate_path),
                    'content_hash': gate.content_hash,
                    'confirmed_by': gate.confirmed_by,
                })
            else:
                state['currentStep'] = 'WAITING_FINAL_ACCEPTANCE'
                state['blockedReason'] = f'final acceptance gate not approved: {gate.reason}'
            self._save_state(state)
            return state

        if action == 'sync_final_acceptance_agent':
            summary_path = self.artifacts_dir / FINAL_ACCEPTANCE_SYNC_DIRNAME / FINAL_ACCEPTANCE_SYNC_SUMMARY
            try:
                run_final_acceptance_agent_sync(
                    state,
                    state_dir=self.state_dir,
                    artifacts_dir=self.artifacts_dir,
                    dry_run=self.dry_run,
                )
            except RuntimeError as exc:
                state['status'] = 'blocked'
                state['currentStep'] = 'FINAL_ACCEPTANCE_AGENT_SYNC'
                state['finalAcceptanceAgentSyncStatus'] = 'failed'
                state['blockedReason'] = f'final acceptance agent sync failed: {exc}'
                self.store.append_event('final_acceptance_agent_sync_failed', {
                    'task_id': state.get('task_id'),
                    'summary_path': str(summary_path),
                    'reason': str(exc),
                })
                self._save_state(state)
                return state

            summary = json.loads(summary_path.read_text(encoding='utf-8'))
            sync_status = str(summary.get('status') or '').lower()
            state['finalAcceptanceAgentSyncStatus'] = 'skipped' if sync_status == 'skipped' else 'done'
            state['finalAcceptanceAgentSyncSummaryPath'] = str(summary_path)
            state['blockedReason'] = None
            state['currentStep'] = 'RELEASE_GATE'
            self.store.append_event('final_acceptance_agent_synced', {
                'task_id': state.get('task_id'),
                'summary_path': str(summary_path),
                'status': state.get('finalAcceptanceAgentSyncStatus'),
                'updated_files': summary.get('updated_files') or [],
            })
            self._save_state(state)
            return state

        if action == 'check_bug_fix_gate':
            gate_path = ensure_bug_fix_gate(state, self.approvals_dir)
            gate = check_gate_file(gate_path)
            state['bugFixGateAccepted'] = gate.approved
            if gate.approved:
                state['bugFixGateAcceptedHash'] = gate.content_hash
                state['bugFixGateAcceptedBy'] = gate.confirmed_by
                state['bugFixGateFeedback'] = gate_body(gate_path.read_text(encoding='utf-8'))
                state['blockedReason'] = None
                state['currentStep'] = 'BUG_FIX'
                self.store.append_event('bug_fix_gate_approved', {
                    'task_id': state.get('task_id'),
                    'path': str(gate_path),
                    'content_hash': gate.content_hash,
                    'confirmed_by': gate.confirmed_by,
                    'bug_fix_id': state.get('activeBugFixId'),
                })
            else:
                state['blockedReason'] = f'bug fix gate not approved: {gate.reason}'
            self._save_state(state)
            return state

        if action == 'require_scope_approval':
            result = ask_human_scope_approval(state, self.approvals_dir, dry_run=self.dry_run)
            if result.approved:
                state['currentStep'] = 'PLAN_APPROVED'
                state['scopeApproved'] = True
                self.store.append_event('scope_approved', {'task_id': state.get('task_id')})
            else:
                state['status'] = 'blocked'
                state['blockedReason'] = 'scope approval denied'
            self._save_state(state)
            return state

        if action == 'run_ui_design':
            run_ui_design_if_needed(state, unit_dir, dry_run=self.dry_run)
            validate_required_artifacts(unit_dir, ['ui-design-summary.json'])
            state['currentStep'] = 'UI_DESIGN_DONE'
            self._save_state(state)
            return state

        if action == 'run_bug_fix':
            bug_fix_dir = self._active_bug_fix_dir(state)
            run_bug_fix(state, bug_fix_dir, dry_run=self.dry_run)
            validate_required_artifacts(bug_fix_dir, ['bug-fix-summary.json', 'root-cause.json'])
            bug_fix_summary = json.loads((bug_fix_dir / 'bug-fix-summary.json').read_text(encoding='utf-8'))
            root_cause = json.loads((bug_fix_dir / 'root-cause.json').read_text(encoding='utf-8'))
            state['activeBugFixArtifactDir'] = str(bug_fix_dir)
            state['bugFixRootCause'] = root_cause
            if _bug_fix_requires_unit_plan_escalation(bug_fix_summary, root_cause):
                state['finalAcceptanceRejectionRoute'] = 'unit_plan'
                state['bugFixEscalatedToUnitPlan'] = True
                self._route_final_acceptance_rejection_to_unit_plan(
                    state,
                    _bug_fix_unit_plan_escalation_feedback(state, bug_fix_summary, root_cause),
                )
            elif str(bug_fix_summary.get('status') or '') == 'ok':
                _clear_last_failure(state)
                state['currentStep'] = 'BUG_FIX_VERIFY'
            else:
                _record_or_block_repeated_failure(
                    state,
                    stage='BUG_FIX',
                    verdict=_bug_fix_failure_verdict(bug_fix_summary, root_cause),
                    retry_step='BUG_FIX',
                )
            self.store.append_event('bug_fix_agent_completed', {
                'task_id': state.get('task_id'),
                'bug_fix_id': state.get('activeBugFixId'),
                'artifact_dir': str(bug_fix_dir),
                'status': bug_fix_summary.get('status'),
                'root_cause_route': root_cause.get('route'),
            })
            self._save_state(state)
            return state

        if action == 'run_bug_fix_verifier':
            bug_fix_dir = self._active_bug_fix_dir(state)
            try:
                run_verifier(
                    state,
                    bug_fix_dir,
                    dry_run=self.dry_run,
                    progress_callback=verification_progress_callback,
                )
            except VerificationEnvironmentError as exc:
                state['status'] = 'blocked'
                state['currentStep'] = 'BUG_FIX_VERIFY'
                state['blockedReason'] = str(exc)
                self.store.append_event('bug_fix_verification_environment_blocked', {
                    'task_id': state.get('task_id'),
                    'bug_fix_id': state.get('activeBugFixId'),
                    'reason': str(exc),
                })
                self._save_state(state)
                return state
            verification = validate_verification_verdict(bug_fix_dir / 'verification.json')
            try:
                validate_verification_evidence_schema(bug_fix_dir / 'verification.json')
            except ValueError as exc:
                verification['passed'] = False
                verification.setdefault('issues', []).append({
                    'severity': 'high',
                    'type': 'invalid_evidence_schema',
                    'message': str(exc),
                })
            if verification['passed']:
                _clear_last_failure(state)
                state['bugFixVerified'] = True
                state['finalAcceptanceAccepted'] = False
                state.pop('finalAcceptanceAcceptedHash', None)
                state.pop('finalAcceptanceAcceptedBy', None)
                state['currentStep'] = 'WAITING_FINAL_ACCEPTANCE'
                self._write_final_scope_audit(state)
                ensure_final_acceptance_gate(state, self.approvals_dir, self.artifacts_dir, force=True)
                self.store.append_event('bug_fix_regression_verified', {
                    'task_id': state.get('task_id'),
                    'bug_fix_id': state.get('activeBugFixId'),
                    'artifact_dir': str(bug_fix_dir),
                })
            else:
                _record_or_block_repeated_failure(
                    state,
                    stage='BUG_FIX_VERIFY',
                    verdict=verification,
                    retry_step='BUG_FIX',
                )
            self._save_state(state)
            return state

        if action == 'run_builder':
            prepare_builder_prompt(state, self.approvals_dir, unit_dir)
            run_builder(state, unit_dir, dry_run=self.dry_run)
            validate_required_artifacts(unit_dir, ['builder-summary.json', 'changed-files.txt'])
            state['currentStep'] = 'REFINE_UNIT'
            self._save_state(state)
            return state

        if action == 'run_refiner':
            run_refiner(state, unit_dir, dry_run=self.dry_run)
            validate_required_artifacts(unit_dir, ['simplifier-result.json', 'refinement-summary.json'])
            simplifier = validate_simplifier_result(unit_dir / 'simplifier-result.json')
            simplifier_status = simplifier.get('status')
            if simplifier_status in {'ok', 'skipped'}:
                _clear_last_failure(state)
                state['currentStep'] = 'REVIEW_UNIT'
            elif simplifier_status == 'changes_requested':
                _record_or_block_repeated_failure(
                    state,
                    stage='REFINE_UNIT',
                    verdict=_simplifier_failure_verdict(simplifier),
                    retry_step='EXECUTE_UNIT',
                )
            else:
                _record_or_block_repeated_failure(
                    state,
                    stage='REFINE_UNIT',
                    verdict=_simplifier_failure_verdict(simplifier),
                    retry_step='REFINE_UNIT',
                )
            self._save_state(state)
            return state

        if action == 'run_reviewer':
            run_reviewer(state, unit_dir, dry_run=self.dry_run)
            review = validate_review_verdict(unit_dir / 'review.json')
            if review['passed']:
                _clear_last_failure(state)
                state['currentStep'] = 'VERIFY_UNIT'
            else:
                _record_or_block_repeated_failure(
                    state,
                    stage='REVIEW_UNIT',
                    verdict=review,
                    retry_step='EXECUTE_UNIT',
                )
            self._save_state(state)
            return state

        if action == 'run_verifier':
            try:
                run_verifier(
                    state,
                    unit_dir,
                    dry_run=self.dry_run,
                    progress_callback=verification_progress_callback,
                )
            except VerificationEnvironmentError as exc:
                state['status'] = 'blocked'
                state['currentStep'] = 'VERIFY_UNIT'
                state['blockedReason'] = str(exc)
                self.store.append_event('verification_environment_blocked', {
                    'task_id': state.get('task_id'),
                    'unit_id': state.get('currentUnitId'),
                    'reason': str(exc),
                })
                self._save_state(state)
                return state
            verification = validate_verification_verdict(unit_dir / 'verification.json')
            try:
                validate_verification_evidence_schema(unit_dir / 'verification.json')
            except ValueError as exc:
                verification['passed'] = False
                verification.setdefault('issues', []).append(
                    {
                        'severity': 'high',
                        'type': 'invalid_evidence_schema',
                        'message': str(exc),
                    }
                )
            if verification['passed']:
                _clear_last_failure(state)
                state['lastVerifiedStep'] = 'VERIFY_UNIT'
                state['currentStep'] = 'UNIT_COMPLETE'
            else:
                _record_or_block_repeated_failure(
                    state,
                    stage='VERIFY_UNIT',
                    verdict=verification,
                    retry_step='EXECUTE_UNIT',
                )
            self._save_state(state)
            return state

        if action == 'complete_unit':
            mark_current_unit_covered(state)
            if target_acceptance_covered(state) or validate_objective_coverage(state):
                if state.get('humanGatesRequired') and not state.get('finalAcceptanceAccepted', False):
                    state['currentStep'] = 'WAITING_FINAL_ACCEPTANCE'
                    self._write_final_scope_audit(state)
                    ensure_final_acceptance_gate(state, self.approvals_dir, self.artifacts_dir, force=True)
                else:
                    state['currentStep'] = 'RELEASE_GATE'
            else:
                next_unit = select_next_unit(state)
                if next_unit == 'RELEASE_GATE':
                    if state.get('humanGatesRequired') and not state.get('finalAcceptanceAccepted', False):
                        state['currentStep'] = 'WAITING_FINAL_ACCEPTANCE'
                        self._write_final_scope_audit(state)
                        ensure_final_acceptance_gate(state, self.approvals_dir, self.artifacts_dir, force=True)
                    else:
                        state['currentStep'] = 'RELEASE_GATE'
                else:
                    state['currentUnitId'] = next_unit
                    state['currentStep'] = 'EXECUTE_UNIT'
            self._save_state(state)
            return state

        if action == 'require_release_approval':
            result = ask_human_release_approval(state, self.approvals_dir, dry_run=self.dry_run)
            if result.approved:
                state['currentStep'] = 'DONE'
                state['status'] = 'done'
            else:
                state['status'] = 'blocked'
                state['blockedReason'] = 'release approval denied'
            self._save_state(state)
            return state

        state = rollback_to_last_verified_step(state)
        self._save_state(state)
        return state

    def _advance_after_final_acceptance_approval(self, state: dict[str, Any]) -> None:
        state.pop('finalAcceptanceAgentSyncSummaryPath', None)
        if final_acceptance_agent_sync_required(state):
            state['finalAcceptanceAgentSyncStatus'] = 'pending'
            state['currentStep'] = 'FINAL_ACCEPTANCE_AGENT_SYNC'
            self.store.append_event('final_acceptance_agent_sync_requested', {
                'task_id': state.get('task_id'),
                'runner': state.get('agentRunner'),
                'tmux_target': state.get('tmuxTarget'),
            })
            return
        state['finalAcceptanceAgentSyncStatus'] = 'skipped'
        state['currentStep'] = 'RELEASE_GATE'

    def _save_state(self, state: dict[str, Any]) -> None:
        next_action = compute_next_allowed_action(state)
        state['nextAllowedActions'] = [next_action] if next_action else []
        self.store.save_state(state)

    def _active_bug_fix_dir(self, state: dict[str, Any]) -> Path:
        bug_fix_id = str(state.get('activeBugFixId') or '').strip()
        if not bug_fix_id:
            bug_fix_id = f"bug-fix-{int(state.get('bugFixAttemptCount') or 1)}"
            state['activeBugFixId'] = bug_fix_id
        return self.artifacts_dir / 'bug-fixes' / bug_fix_id

    def _unsafe_skip_gate(self, state: dict[str, Any], gate_name: str, gate_path: Path) -> bool:
        if not self.unsafe_skip_human_gates:
            return False
        self.store.append_event('human_gate_unsafe_skipped', {
            'task_id': state.get('task_id'),
            'gate': gate_name,
            'path': str(gate_path),
        })
        state[f'{gate_name}UnsafeSkipped'] = True
        state['blockedReason'] = None
        return True

    def run_until_done(
        self,
        max_steps: int = DEFAULT_MAX_AUTOMATIC_STEPS,
        max_no_progress_steps: int = DEFAULT_MAX_NO_PROGRESS_STEPS,
    ) -> dict[str, Any]:
        state = self.get_status()
        steps = 0
        no_progress_steps = 0
        while state.get('status') not in {'done', 'blocked', 'failed'} and steps < max_steps:
            action = compute_next_allowed_action(state)
            before_key = _automatic_progress_key(state, action)
            previous_step = state.get('currentStep')
            state = self.run_once()
            steps += 1
            after_action = compute_next_allowed_action(state)
            after_key = _automatic_progress_key(state, after_action)
            if after_key == before_key:
                no_progress_steps += 1
                if no_progress_steps >= max_no_progress_steps:
                    raise RuntimeError(
                        f'No workflow progress after {max_no_progress_steps} repeated automatic steps '
                        f'at currentStep={state.get("currentStep")} nextAction={after_action}'
                    )
            else:
                no_progress_steps = 0
            if state.get('currentStep') == previous_step and previous_step in WAITING_HUMAN_GATE_STEPS:
                break
            if state.get('currentStep') in WAITING_HUMAN_GATE_STEPS:
                break
        if steps >= max_steps and state.get('status') not in {'done', 'blocked', 'failed'}:
            raise RuntimeError(f'Exceeded max steps ({max_steps}) before reaching a terminal state')
        return state

    def drive(
        self,
        max_steps: int = DEFAULT_MAX_AUTOMATIC_STEPS,
        max_no_progress_steps: int = DEFAULT_MAX_NO_PROGRESS_STEPS,
        verbose: bool = False,
        color_mode: str = 'auto',
        actor: str = 'human',
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print,
        timestamp_output: bool = True,
        print_agent_target: bool = True,
    ) -> dict[str, Any]:
        if timestamp_output:
            output_func = _timestamped_output(output_func)

        self._drive_progress_callback: Callable[[str], None] | None = output_func
        steps = 0
        no_progress_steps = 0
        color_enabled = _color_enabled(color_mode)
        compact_reporter = None if verbose else _CompactDriveReporter(output_func, color_enabled=color_enabled)
        self._drive_compact_reporter = compact_reporter
        self._drive_color_enabled = color_enabled
        state = self.get_status()
        if print_agent_target:
            self._print_agent_target_resolution(state, output_func)
        while state.get('status') not in {'done', 'blocked', 'failed'}:
            if verbose:
                self._print_drive_progress(state, output_func)
            else:
                compact_reporter.print_status(state)

            state = self._auto_revise_invalid_requirements_draft(state)
            state = self._auto_revise_invalid_unit_plan_draft(state)
            gate_info = self._pending_gate_info(state)
            if gate_info:
                handled = self._handle_drive_gate(gate_info, actor, input_func, output_func)
                state = self.get_status()
                if not handled:
                    return state
                no_progress_steps = 0
                continue

            if steps >= max_steps:
                output_func(f'[停止] 已达到最大自动步数：{max_steps}。')
                return state

            action = compute_next_allowed_action(state)
            if not action:
                output_func('[停止] 当前没有可执行的下一步。')
                return state

            before_key = _automatic_progress_key(state, action)
            before_state = state
            if verbose:
                output_func(f'[执行] {ACTION_LABELS.get(action, action)}...')
            started_at = time.monotonic()
            verification_progress_callback = (
                _verification_progress_printer(output_func, color_enabled)
                if action == 'run_verifier'
                else None
            )
            if verification_progress_callback is not None and _uses_default_run_once(self):
                state = self._run_once(verification_progress_callback=verification_progress_callback)
            else:
                state = self.run_once()
            elapsed_seconds = time.monotonic() - started_at
            steps += 1
            if compact_reporter is not None:
                compact_reporter.record_transition(before_state, action, state, elapsed_seconds)
            after_action = compute_next_allowed_action(state)
            after_key = _automatic_progress_key(state, after_action)
            if after_key == before_key:
                no_progress_steps += 1
                if no_progress_steps >= max_no_progress_steps:
                    output_func(
                        f'[停止] 连续 {max_no_progress_steps} 次执行未推进'
                        f'（阶段：{state.get("currentStep")}，下一步：{ACTION_LABELS.get(after_action, after_action)}）。'
                    )
                    return state
            else:
                no_progress_steps = 0

        self._drive_progress_callback = None
        if state.get('status') == 'done':
            output_func(_paint('[完成] 工作流已完成。', 'green', color_enabled))
        elif state.get('status') == 'blocked':
            reason = _gate_reason_label(str(state.get('blockedReason') or '工作流已阻塞'))
            output_func(_format_blocked_message(reason, color_enabled=color_enabled))
        else:
            output_func(f"[停止] 工作流状态：{state.get('status')}。")
        self._drive_color_enabled = False
        return state

    def _print_drive_progress(
        self,
        state: dict[str, Any],
        output_func: Callable[[str], None],
    ) -> None:
        action = state.get('nextAction') or compute_next_allowed_action(state)
        output_func(
            f"[进度] 目标：{state.get('requestedOutcome') or '-'}"
            f" | 单元：{state.get('currentUnitId') or '-'}"
            f" | 阶段：{state.get('currentStep')}"
            f" | 下一步：{ACTION_LABELS.get(action, action) if action else '-'}"
        )

    def _pending_gate_info(self, state: dict[str, Any]) -> dict[str, Any] | None:
        step = state.get('currentStep')
        can_rework = False
        if step == 'WAITING_REQUIREMENTS_ACCEPTANCE':
            gate = 'requirements'
            path = ensure_requirements_gate(state, self.approvals_dir)
            can_revise = True
        elif step == 'WAITING_UNIT_PLAN_APPROVAL':
            gate = 'unit-plan'
            path = ensure_unit_plan_gate(state, self.approvals_dir)
            can_revise = True
        elif step == 'WAITING_FINAL_ACCEPTANCE':
            gate = 'final-acceptance'
            self._write_final_scope_audit(state)
            path = ensure_final_acceptance_gate(state, self.approvals_dir, self.artifacts_dir)
            can_revise = False
            can_rework = True
        elif step == 'WAITING_BUG_FIX_GATE':
            gate = 'bug-fix'
            path = ensure_bug_fix_gate(state, self.approvals_dir)
            can_revise = False
        else:
            return None

        check = check_gate_file(path)
        approved_but_invalid = _approved_gate_invalid_reason(gate, state)
        if check.approved and not approved_but_invalid:
            return None
        return {
            'gate': gate,
            'path': path,
            'review_path': _plannotator_review_path_for_gate(self.artifacts_dir, gate, path),
            'label': HUMAN_GATE_LABELS[gate],
            'reason': approved_but_invalid or check.reason,
            'can_revise': can_revise,
            'can_rework': can_rework,
        }

    def _handle_drive_gate(
        self,
        gate_info: dict[str, Any],
        actor: str,
        input_func: Callable[[str], str],
        output_func: Callable[[str], None],
    ) -> bool:
        self._send_human_review_tmux_reminder(self.store.load_state(), str(gate_info['gate']))
        output_func(f"[人工确认] {gate_info['label']}")
        output_func(f"  文件：{gate_info['path']}")
        review_path = Path(gate_info.get('review_path') or gate_info['path'])
        approval_gate_path = Path(gate_info['path'])
        if review_path != approval_gate_path:
            output_func(f'  审阅文件：{review_path}')
            output_func(f'  确认文件：{approval_gate_path}')
        if gate_info.get('reason'):
            output_func(f"  状态：{_gate_reason_label(str(gate_info['reason']))}")
        output_func('  操作：')
        output_func('    v  使用 Plannotator 辅助审阅')
        output_func('    a  确认通过并继续')
        if gate_info.get('can_revise'):
            output_func('    r  我已写批注，让 Claude 重新生成')
        if gate_info.get('can_rework'):
            output_func('    r  验收不通过，带批注返工')
        output_func('    p  打印文件路径')
        output_func('    q  退出')

        while True:
            try:
                choice = input_func('> ').strip().lower()
            except EOFError:
                output_func('[退出] 未收到输入，已停止在人工确认点。')
                return False

            if choice in {'v', 'view', 'plannotator'}:
                prototype_preview_server = None
                prototype_review_manifest_path = None
                prototype_review_preview_url = None
                if str(gate_info['gate']) == 'requirements' and review_path != approval_gate_path:
                    expected_review_path, expected_manifest_path, prototypes_dir = prototype_review_paths(self.artifacts_dir)
                    if review_path == expected_review_path and expected_manifest_path.exists():
                        try:
                            prototype_preview_server = start_prototype_review_preview_server(
                                review_path=review_path,
                                manifest_path=expected_manifest_path,
                                prototypes_dir=prototypes_dir,
                                approval_gate_path=approval_gate_path,
                            )
                        except Exception as exc:
                            output_func(f'[原型预览] 启动失败：{exc}')
                            continue
                        prototype_review_manifest_path = expected_manifest_path
                        prototype_review_preview_url = prototype_preview_server.preview_url
                try:
                    try:
                        result = run_plannotator_gate_review(
                            gate=str(gate_info['gate']),
                            label=str(gate_info['label']),
                            gate_path=review_path,
                            state_dir=self.state_dir,
                            command=self.plannotator_command,
                            port=self.plannotator_port,
                        )
                    except Exception as exc:
                        output_func(f'[Plannotator] 启动失败：{exc}')
                        continue
                    _record_plannotator_review_paths(
                        result.summary_path,
                        approval_gate_path=approval_gate_path,
                        review_path=review_path,
                        prototype_review_manifest_path=prototype_review_manifest_path,
                        prototype_review_preview_url=prototype_review_preview_url,
                    )
                    event_payload = {
                        'gate': gate_info['gate'],
                        'path': str(gate_info['path']),
                        'review_path': str(review_path),
                        'approval_gate_path': str(approval_gate_path),
                        'command': result.command,
                        'summary_path': str(result.summary_path),
                        'stdout_path': str(result.summary_path.with_suffix('.stdout.log')),
                    }
                    if prototype_review_manifest_path is not None:
                        event_payload['prototype_review_manifest_path'] = str(prototype_review_manifest_path)
                    if prototype_review_preview_url:
                        event_payload['prototype_review_preview_url'] = prototype_review_preview_url
                    self.store.append_event('plannotator_review_requested', event_payload)
                    output_func('[Plannotator] 已打开辅助审阅。')
                    if self.plannotator_port is not None:
                        output_func(f'  打开网址：http://localhost:{self.plannotator_port}')
                    if prototype_review_preview_url:
                        output_func(f'  原型预览：{prototype_review_preview_url}')
                    output_func(f'  审阅记录：{result.summary_path}')
                    _print_plannotator_output(result.stdout, output_func)
                    if result.stderr.strip():
                        _print_plannotator_output(result.stderr, output_func)
                    output_func('  请在 Plannotator 浏览器里选择 Approve 或 Close。Approve 会自动继续。')
                    decision = _wait_for_plannotator_gate_decision(
                        self.state_dir,
                        str(gate_info['gate']),
                        Path(gate_info['path']),
                        output_func,
                    )
                    status = decision.get('status')
                    if status == 'approved':
                        try:
                            self.approve_human_gate(str(gate_info['gate']), actor=actor)
                        except ValueError as exc:
                            output_func(f"[确认] {gate_info['label']} 无法确认：{_gate_reason_label(str(exc))}")
                            if self._auto_revise_gate_after_validation_error(gate_info, exc, output_func):
                                return True
                            continue
                        output_func('[Plannotator] 已收到 Approve，等同于人工确认通过。')
                        return True
                    if status == 'feedback' and gate_info.get('can_revise'):
                        output_func(f"[Plannotator] 已收到修改意见，开始重新生成 {gate_info['label']}。")
                        feedback_summary = _plannotator_feedback_summary(decision)
                        if feedback_summary:
                            output_func(f'  修改意见：{feedback_summary}')
                        feedback_preview = _plannotator_feedback_preview(decision)
                        if feedback_preview:
                            output_func(f'  预览：{feedback_preview}')
                        self.store.append_event('plannotator_feedback_received', {
                            'gate': gate_info['gate'],
                            'path': str(gate_info['path']),
                            'feedback_count': _plannotator_feedback_count(decision),
                            'feedback_preview': feedback_preview,
                        })
                        self._print_compact_revision_status(gate_info, source='plannotator')
                        try:
                            self.revise_human_gate(str(gate_info['gate']))
                        except Exception as exc:
                            output_func(f'[修订] 无法返工：{exc}')
                            continue
                        output_func(f"[修订] 已根据 Plannotator 反馈重新生成 {gate_info['label']}。")
                        return True
                    if status == 'feedback' and gate_info.get('can_rework'):
                        output_func('[Plannotator] 已收到最终验收修改意见，请先选择返工流向。')
                        feedback_summary = _plannotator_feedback_summary(decision)
                        if feedback_summary:
                            output_func(f'  修改意见：{feedback_summary}')
                        feedback_preview = _plannotator_feedback_preview(decision)
                        if feedback_preview:
                            output_func(f'  预览：{feedback_preview}')
                        self.store.append_event('plannotator_feedback_received', {
                            'gate': gate_info['gate'],
                            'path': str(gate_info['path']),
                            'feedback_count': _plannotator_feedback_count(decision),
                            'feedback_preview': feedback_preview,
                        })
                        if not _ensure_final_acceptance_rejection_route_from_prompt(
                            Path(gate_info['path']),
                            input_func,
                            output_func,
                        ):
                            return False
                        try:
                            self.reject_final_acceptance_gate()
                        except Exception as exc:
                            output_func(f'[返工] 无法返工：{exc}')
                            continue
                        route = self.store.load_state().get('finalAcceptanceRejectionRoute')
                        message = FINAL_ACCEPTANCE_REJECTION_ROUTE_MESSAGES.get(
                            str(route),
                            '最终验收未通过，已按人工路由处理。',
                        )
                        output_func(f'[返工] {message}')
                        return True
                    if status == 'closed':
                        output_func('[Plannotator] 已关闭，未批准；仍停在人工确认点。')
                        continue
                    output_func('[Plannotator] 未返回可执行决策；仍停在人工确认点。')
                    continue
                finally:
                    if prototype_preview_server is not None:
                        prototype_preview_server.close()

            if choice in {'a', 'approve'}:
                try:
                    self.approve_human_gate(str(gate_info['gate']), actor=actor)
                except ValueError as exc:
                    output_func(f"[确认] {gate_info['label']} 无法确认：{_gate_reason_label(str(exc))}")
                    if self._auto_revise_gate_after_validation_error(gate_info, exc, output_func):
                        return True
                    continue
                output_func(f"[确认] {gate_info['label']} 已确认，继续推进。")
                return True
            if choice in {'r', 'revise'} and gate_info.get('can_revise'):
                self._print_compact_revision_status(gate_info, source='human')
                try:
                    self.revise_human_gate(str(gate_info['gate']))
                except Exception as exc:
                    output_func(f'[修订] 无法返工：{exc}')
                    continue
                output_func(f"[修订] 已重新生成 {gate_info['label']}，请重新阅读确认。")
                return True
            if choice in {'r', 'reject', 'rework'} and gate_info.get('can_rework'):
                if not _ensure_final_acceptance_rejection_route_from_prompt(
                    Path(gate_info['path']),
                    input_func,
                    output_func,
                ):
                    return False
                try:
                    self.reject_final_acceptance_gate()
                except Exception as exc:
                    output_func(f'[返工] 无法返工：{exc}')
                    continue
                route = self.store.load_state().get('finalAcceptanceRejectionRoute')
                message = FINAL_ACCEPTANCE_REJECTION_ROUTE_MESSAGES.get(
                    str(route),
                    '最终验收未通过，已按人工路由处理。',
                )
                output_func(f'[返工] {message}')
                return True
            if choice in {'p', 'path'}:
                output_func(f"  文件：{gate_info['path']}")
                continue
            if choice in {'q', 'quit', 'exit'}:
                output_func('[退出] 已停止在人工确认点。')
                return False
            output_func('[提示] 请输入 v / a / r / p / q。')

    def _send_human_review_tmux_reminder(self, state: dict[str, Any], gate: str) -> None:
        tmux_target = str(state.get('tmuxTarget') or '').strip()
        if not tmux_target:
            return
        workspace_dir = _agent_guide_workspace_dir(
            explicit_workspace=self.workspace_dir,
            state_dir=self.state_dir,
            state=state,
        )
        tmux_command = _tmux_command_for_controller(
            str(state.get('agentCommand') or self.agent_command or 'tmux')
        )
        commands = [
            [*tmux_command, 'set-buffer', HUMAN_REVIEW_TMUX_REMINDER],
            [*tmux_command, 'paste-buffer', '-t', tmux_target],
        ]
        try:
            for command in commands:
                completed = subprocess.run(
                    command,
                    cwd=workspace_dir,
                    text=True,
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                if completed.returncode != 0:
                    self.store.append_event('human_review_tmux_reminder_failed', {
                        'gate': gate,
                        'tmux_target': tmux_target,
                        'returncode': completed.returncode,
                        'stderr': completed.stderr.strip(),
                    })
                    return
        except Exception as exc:
            self.store.append_event('human_review_tmux_reminder_failed', {
                'gate': gate,
                'tmux_target': tmux_target,
                'error': str(exc),
            })
            return
        self.store.append_event('human_review_tmux_reminder_sent', {
            'gate': gate,
            'tmux_target': tmux_target,
        })

    def _print_compact_revision_status(self, gate_info: dict[str, Any], *, source: str) -> None:
        compact_reporter = getattr(self, '_drive_compact_reporter', None)
        if compact_reporter is None:
            return
        gate = str(gate_info.get('gate') or '')
        state = self.store.load_state()
        source_label = 'Plannotator 反馈' if source == 'plannotator' else '人工反馈'
        if gate == 'requirements':
            compact_reporter.print_status(
                state,
                current_label=f'根据{source_label}修订 Requirements 草案',
                planning_stage='Requirements confirmation',
                force=True,
            )
        elif gate == 'unit-plan':
            compact_reporter.print_status(
                state,
                current_label=f'根据{source_label}修订 Unit Plan 草案',
                planning_stage='Unit plan confirmation',
                force=True,
            )

    def _auto_revise_requirements_after_validation_error(
        self,
        gate_info: dict[str, Any],
        error: ValueError,
        output_func: Callable[[str], None],
    ) -> bool:
        if str(gate_info.get('gate')) != 'requirements':
            return False
        if not gate_info.get('can_revise'):
            return False
        if not str(error).startswith('requirements gate invalid:'):
            return False
        output_func(
            _format_auto_revision_message(
                action_label='Controller 校验未通过，已自动打回需求草案生成',
                color_enabled=bool(getattr(self, '_drive_color_enabled', False)),
            )
        )
        try:
            self._revise_requirements_gate(controller_validation_only=True)
            state = self._auto_revise_invalid_requirements_draft(self.store.load_state())
            self._save_state(state)
        except Exception as exc:
            output_func(_format_auto_revision_failure_message(str(exc), color_enabled=bool(getattr(self, '_drive_color_enabled', False))))
            return False
        output_func(f"[修订] 已根据 Controller 校验错误重新生成 {gate_info['label']}。")
        return True

    def _auto_revise_unit_plan_after_validation_error(
        self,
        gate_info: dict[str, Any],
        error: ValueError,
        output_func: Callable[[str], None],
    ) -> bool:
        if str(gate_info.get('gate')) != 'unit-plan':
            return False
        if not gate_info.get('can_revise'):
            return False
        if not str(error).startswith('unit plan gate invalid:'):
            return False
        if not self._unit_plan_auto_revision_enabled(self.store.load_state()):
            return False
        output_func(
            _format_auto_revision_message(
                gate_label='Unit Plan',
                action_label='预检失败，已自动打回',
                reason=_gate_reason_label(_strip_gate_invalid_prefix(str(error))),
                color_enabled=bool(getattr(self, '_drive_color_enabled', False)),
            )
        )
        try:
            self._revise_unit_plan_gate(controller_validation_only=True)
            state = self._auto_revise_invalid_unit_plan_draft(self.store.load_state())
            self._save_state(state)
        except Exception as exc:
            output_func(_format_auto_revision_failure_message(str(exc), color_enabled=bool(getattr(self, '_drive_color_enabled', False))))
            return False
        output_func(f"[修订] 已根据 Controller 校验错误重新生成 {gate_info['label']}。")
        return True

    def _auto_revise_gate_after_validation_error(
        self,
        gate_info: dict[str, Any],
        error: ValueError,
        output_func: Callable[[str], None],
    ) -> bool:
        return (
            self._auto_revise_requirements_after_validation_error(gate_info, error, output_func)
            or self._auto_revise_unit_plan_after_validation_error(gate_info, error, output_func)
        )

    def _auto_revise_invalid_requirements_draft(self, state: dict[str, Any]) -> dict[str, Any]:
        if not self._requirements_auto_revision_enabled(state):
            return state

        gate_path = self.approvals_dir / 'requirements-and-acceptance.md'
        if state.get('currentStep') != 'WAITING_REQUIREMENTS_ACCEPTANCE' or not gate_path.exists():
            return state

        max_revisions = int(
            state.get('requirementsAutoRevisionMax')
            or DEFAULT_MAX_REQUIREMENTS_AUTO_REVISIONS
        )
        output_func = getattr(self, '_drive_progress_callback', None)
        compact_reporter = getattr(self, '_drive_compact_reporter', None)
        attempts = 0
        while attempts < max_revisions:
            if compact_reporter is not None:
                compact_reporter.print_status(
                    state,
                    current_label='预检 Requirements 草案',
                    planning_stage='Requirements confirmation',
                )
            reason = self._requirements_gate_invalid_reason(state, gate_path)
            if not reason:
                state['blockedReason'] = None
                return state

            attempts += 1
            state['requirementsAccepted'] = False
            state['currentStep'] = 'WAITING_REQUIREMENTS_ACCEPTANCE'
            state['blockedReason'] = reason
            self._save_state(state)
            self.store.append_event('requirements_draft_auto_revision_requested', {
                'task_id': state.get('task_id'),
                'path': str(gate_path),
                'reason': reason,
                'attempt': attempts,
            })
            self._write_controller_validation_artifact(
                gate='requirements',
                reason=reason,
                attempt=attempts,
            )
            if compact_reporter is not None:
                compact_reporter.print_status(
                    state,
                    current_label='自动打回 Requirements 草案',
                    planning_stage='Requirements confirmation',
                    force=True,
                )
            if output_func is not None:
                output_func(
                    _format_auto_revision_message(
                        gate_label='Requirements',
                        action_label='草案未通过 controller 预检，自动打回',
                        reason=_gate_reason_label(reason),
                        color_enabled=bool(getattr(self, '_drive_color_enabled', False)),
                    )
                )
            self._revise_requirements_gate(controller_validation_only=True)
            state = self.store.load_state()

        reason = self._requirements_gate_invalid_reason(state, gate_path)
        if reason:
            state['requirementsAccepted'] = False
            state['currentStep'] = 'WAITING_REQUIREMENTS_ACCEPTANCE'
            state['status'] = 'blocked'
            state['blockedReason'] = (
                f'requirements gate invalid after automatic revisions: {reason}'
            )
            self.store.append_event('requirements_draft_auto_revision_blocked', {
                'task_id': state.get('task_id'),
                'path': str(gate_path),
                'reason': reason,
                'attempts': max_revisions,
            })
        else:
            state['blockedReason'] = None
        return state

    def _requirements_auto_revision_enabled(self, state: dict[str, Any]) -> bool:
        if self.dry_run:
            return False
        return state.get('agentRunner') in TMUX_AGENT_BACKENDS

    def _auto_revise_invalid_unit_plan_draft(self, state: dict[str, Any]) -> dict[str, Any]:
        if not self._unit_plan_auto_revision_enabled(state):
            return state

        gate_path = self.approvals_dir / 'unit-plan.md'
        if state.get('currentStep') != 'WAITING_UNIT_PLAN_APPROVAL' or not gate_path.exists():
            return state

        max_revisions = int(
            state.get('unitPlanAutoRevisionMax')
            or DEFAULT_MAX_UNIT_PLAN_AUTO_REVISIONS
        )
        output_func = getattr(self, '_drive_progress_callback', None)
        compact_reporter = getattr(self, '_drive_compact_reporter', None)
        attempts = 0
        while attempts < max_revisions:
            if compact_reporter is not None:
                compact_reporter.print_status(
                    state,
                    current_label='预检 Unit Plan 草案',
                    planning_stage='Unit plan confirmation',
                )
            state = self._refresh_unit_plan_gate_validation(state)
            reason = str(state.get('blockedReason') or '')
            if not reason.startswith('unit plan gate invalid:'):
                return state

            attempts += 1
            state['unitPlanAccepted'] = False
            state['currentStep'] = 'WAITING_UNIT_PLAN_APPROVAL'
            self._save_state(state)
            self.store.append_event('unit_plan_draft_auto_revision_requested', {
                'task_id': state.get('task_id'),
                'path': str(gate_path),
                'reason': reason,
                'attempt': attempts,
            })
            self._write_controller_validation_artifact(
                gate='unit-plan',
                reason=reason,
                attempt=attempts,
            )
            if compact_reporter is not None:
                compact_reporter.print_status(
                    state,
                    current_label='自动打回 Unit Plan 草案',
                    planning_stage='Unit plan confirmation',
                    force=True,
                )
            if output_func is not None:
                output_func(
                    _format_auto_revision_message(
                        gate_label='Unit Plan',
                        action_label='预检失败，已自动打回',
                        reason=_gate_reason_label(_strip_gate_invalid_prefix(reason)),
                        color_enabled=bool(getattr(self, '_drive_color_enabled', False)),
                    )
                )
            self._revise_unit_plan_gate(controller_validation_only=True)
            state = self.store.load_state()

        state = self._refresh_unit_plan_gate_validation(state)
        reason = str(state.get('blockedReason') or '')
        if reason.startswith('unit plan gate invalid:'):
            state['unitPlanAccepted'] = False
            state['currentStep'] = 'WAITING_UNIT_PLAN_APPROVAL'
            state['status'] = 'blocked'
            state['blockedReason'] = (
                f'unit plan gate invalid after automatic revisions: {reason}'
            )
            self.store.append_event('unit_plan_draft_auto_revision_blocked', {
                'task_id': state.get('task_id'),
                'path': str(gate_path),
                'reason': reason,
                'attempts': max_revisions,
            })
        return state

    def _unit_plan_auto_revision_enabled(self, state: dict[str, Any]) -> bool:
        if self.dry_run:
            return False
        return state.get('agentRunner') in TMUX_AGENT_BACKENDS

    def _write_controller_validation_artifact(
        self,
        *,
        gate: str,
        reason: str,
        attempt: int,
    ) -> Path:
        artifact_dir = self.artifacts_dir / f'{gate}-draft'
        artifact_dir.mkdir(parents=True, exist_ok=True)
        path = artifact_dir / 'controller-validation-error.json'
        path.write_text(
            json.dumps(
                {
                    'gate': gate,
                    'attempt': attempt,
                    'reason': reason,
                    'short_reason': _gate_reason_label(_strip_gate_invalid_prefix(reason)),
                    'generated_at': datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding='utf-8',
        )
        return path


def _gate_reason_label(reason: str) -> str:
    label = GATE_REASON_LABELS.get(reason)
    if label:
        return label
    return _compact_controller_reason(reason)


def _format_auto_revision_message(
    *,
    action_label: str,
    color_enabled: bool,
    gate_label: str = '',
    reason: str = '',
) -> str:
    plain_head = '[修订]'
    head = _paint(plain_head, 'cyan', color_enabled)
    gate = f"{_paint(gate_label, 'bold', color_enabled)} " if gate_label else ''
    action = _paint(action_label, 'yellow', color_enabled)
    if reason:
        return f'{head} {gate}{action}：{_highlight_validation_tokens(reason, color_enabled=color_enabled)}'
    return f'{head} {gate}{action}。'


def _format_auto_revision_failure_message(reason: str, *, color_enabled: bool) -> str:
    return (
        f"{_paint('[修订]', 'cyan', color_enabled)} "
        f"{_paint('自动打回失败', 'red', color_enabled)}："
        f'{_highlight_validation_tokens(reason, color_enabled=color_enabled)}'
    )


def _format_blocked_message(reason: str, *, color_enabled: bool) -> str:
    return (
        f"{_paint('[阻塞]', 'red', color_enabled)} "
        f'{_highlight_validation_tokens(reason, color_enabled=color_enabled)}'
    )


def _highlight_validation_tokens(text: str, *, color_enabled: bool) -> str:
    if not color_enabled:
        return text
    token_pattern = re.compile(
        r'(?<![A-Za-z0-9_-])('
        r'(?:AO|AC|TC|J)-[A-Za-z0-9_.-]+'
        r'|(?:target|unit|v\d)[A-Za-z0-9_.-]+'
        r'|/[^\s;:,，。]+'
        r')(?![A-Za-z0-9_-])'
    )
    return token_pattern.sub(lambda match: _paint(match.group(1), 'yellow', True), text)


def _strip_gate_invalid_prefix(reason: str) -> str:
    return re.sub(
        r'^(?:unit plan|requirements|final acceptance) gate invalid:\s*',
        '',
        str(reason or ''),
        flags=re.IGNORECASE,
    ).strip()


def _compact_controller_reason(reason: str, *, max_chars: int = 260) -> str:
    text = ' '.join(str(reason or '').split())
    if not text:
        return text
    if 'missing Acceptance Obligation coverage:' in text:
        prefix, _, detail = text.partition('missing Acceptance Obligation coverage:')
        ids = list(dict.fromkeys(re.findall(r'\bAO-\d+\b', detail)))
        if len(ids) > 5:
            return (
                f'{prefix}missing Acceptance Obligation coverage: '
                f'{len(ids)} AO missing ({ids[0]}..{ids[-1]}); full detail sent to revision prompt'
            ).strip()
    return _short_failure_text(text, max_chars=max_chars)


def _final_acceptance_rejection_route(content: str) -> str:
    body = gate_body(content)
    selected: set[str] = set()
    for route, label in FINAL_ACCEPTANCE_REJECTION_ROUTE_LABELS.items():
        for alias in (label, *FINAL_ACCEPTANCE_REJECTION_ROUTE_ALIASES.get(route, ())):
            pattern = rf'^\s*[-*]\s*\[[xX]\]\s*{re.escape(alias)}\s*:'
            if re.search(pattern, body, flags=re.MULTILINE):
                selected.add(route)
                break

    if not selected:
        raise ValueError(
            'Final acceptance rejection routing must select one option in the '
            'Rejection Routing checklist before rejecting final acceptance.'
        )

    for route in FINAL_ACCEPTANCE_REJECTION_ROUTE_PRIORITY:
        if route in selected:
            return route
    raise ValueError('Final acceptance rejection routing selected an unknown option.')


def _final_acceptance_rejection_feedback(
    route: str,
    gate_content: str,
    rejection_feedback: str,
) -> str:
    if route not in {'implementation', 'defect_fix'}:
        return rejection_feedback
    patch_list = extract_patch_list(gate_content)
    if not patch_list:
        return rejection_feedback
    matrix_context = _final_acceptance_evidence_matrix_context(gate_content)
    if not matrix_context:
        return patch_list
    return patch_list.rstrip() + '\n\n' + matrix_context


def _final_acceptance_evidence_matrix_context(content: str) -> str | None:
    body = gate_body(content)
    match = re.search(
        r'(?ms)^##\s+验收证据矩阵（Final Acceptance Evidence Matrix）\s*$.*?(?=^##\s+|\Z)',
        body,
    )
    if not match:
        return None
    context = match.group(0).strip()
    return context or None


def _strip_html_comments(content: str) -> str:
    return re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)


def _requirements_revision_diff_summary(before_body: str, after_body: str) -> dict[str, Any]:
    before_lines = before_body.rstrip('\n').splitlines()
    after_lines = after_body.rstrip('\n').splitlines()
    unified = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile='before',
        tofile='after',
        lineterm='',
    )
    added_lines: list[str] = []
    removed_lines: list[str] = []
    for line in unified:
        if line.startswith('+++') or line.startswith('---') or line.startswith('@@'):
            continue
        if line.startswith('+'):
            added_lines.append(line[1:])
        elif line.startswith('-'):
            removed_lines.append(line[1:])
    return {
        'added_lines': added_lines,
        'removed_lines': removed_lines,
        'changed_sections': _changed_markdown_sections(before_lines, after_lines),
    }


def _changed_markdown_sections(before_lines: list[str], after_lines: list[str]) -> list[str]:
    sections: list[str] = []
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)
    for tag, before_start, before_end, after_start, after_end in matcher.get_opcodes():
        if tag == 'equal':
            continue
        if tag in {'replace', 'delete'}:
            _append_unique(sections, _markdown_sections_for_range(before_lines, before_start, before_end))
        if tag in {'replace', 'insert'}:
            _append_unique(sections, _markdown_sections_for_range(after_lines, after_start, after_end))
    return sections


def _markdown_sections_for_range(lines: list[str], start: int, end: int) -> list[str]:
    if not lines:
        return ['(document)']
    range_start = max(0, min(start, len(lines) - 1))
    range_end = max(range_start + 1, min(end, len(lines)))
    headings = [
        line.strip()
        for line in lines[range_start:range_end]
        if re.match(r'^#{1,6}\s+\S', line.strip())
    ]
    if headings:
        return headings
    return [_markdown_section_for_index(lines, range_start)]


def _markdown_section_for_index(lines: list[str], index: int) -> str:
    if not lines:
        return '(document)'
    for line_index in range(max(0, min(index, len(lines) - 1)), -1, -1):
        line = lines[line_index].strip()
        if re.match(r'^#{1,6}\s+\S', line):
            return line
    return '(document)'


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _append_requirements_revision_index(
    index_path: Path,
    *,
    artifact_path: Path,
    payload: dict[str, Any],
) -> None:
    if not index_path.exists():
        index_path.write_text('# Requirements Revisions\n\n', encoding='utf-8')
    changed = str(bool(payload.get('changed'))).lower()
    controller_error = payload.get('controller_validation_error') or 'none'
    entry = (
        f"- revision {payload.get('revision_count')}: {artifact_path.name}\n"
        f"  - changed: {changed}\n"
        f"  - before: sha256:{payload.get('before_hash')}\n"
        f"  - after: sha256:{payload.get('after_hash')}\n"
        f"  - controller_validation_error: {controller_error}\n"
        f"  - generated_at: {payload.get('generated_at')}\n"
    )
    with index_path.open('a', encoding='utf-8') as file:
        file.write(entry)


def _next_change_request_id(path: Path) -> str:
    max_number = 0
    if path.exists():
        for record in _read_jsonl(path):
            raw_id = str(record.get('id') or '')
            match = re.fullmatch(r'CR-(\d+)', raw_id)
            if match:
                max_number = max(max_number, int(match.group(1)))
    return f'CR-{max_number + 1:04d}'


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as file:
        file.write(json.dumps(record, ensure_ascii=False) + '\n')


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _change_request_impacts(
    reason: str,
    annotations: list[Any] | None = None,
) -> dict[str, list[str]]:
    searchable = reason
    if annotations:
        searchable += '\n' + json.dumps(annotations, ensure_ascii=False)
    return {
        'acceptance_obligations': _unique_matches(r'(?<![A-Za-z0-9_-])AO-[A-Za-z0-9_-]+', searchable),
        'acceptance_criteria': _unique_matches(r'(?<![A-Za-z0-9_-])AC-[A-Za-z0-9_-]+', searchable),
        'test_cases': _unique_matches(r'(?<![A-Za-z0-9_-])TC-[A-Za-z0-9_-]+', searchable),
        'journeys': _journey_references(searchable),
    }


def _unique_matches(pattern: str, text: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(pattern, text):
        value = match.group(0).strip()
        if value not in values:
            values.append(value)
    return values


def _journey_references(text: str) -> list[str]:
    journeys: list[str] = []
    for pattern in (
        r'(?im)\bJourney\s*[:：=-]\s*([^\n.;]+)',
        r'(?m)用户旅程\s*[:：=-]\s*([^\n。；;]+)',
    ):
        for match in re.finditer(pattern, text):
            value = match.group(1).strip(' `"\t')
            if value and value not in journeys:
                journeys.append(value)
    return journeys



def _defect_fix_unit_plan_revision_feedback(rejection_feedback: str) -> str:
    return (
        'Final acceptance defect-fix request.\n\n'
        'The approved requirements remain valid. Do not route this as a requirements change.\n'
        'Generate focused bug-fix units that address the defects below, and reopen only the affected '
        'covered objectives by adding those bug-fix unit ids with status partial in the Controller State Patch.\n\n'
        f'{rejection_feedback}'
    )


def _bug_fix_requires_unit_plan_escalation(
    bug_fix_summary: dict[str, Any],
    root_cause: dict[str, Any],
) -> bool:
    status = str(bug_fix_summary.get('status') or '').strip()
    route = str(root_cause.get('route') or bug_fix_summary.get('route') or '').strip()
    classification = str(root_cause.get('classification') or '').strip()
    return (
        status == 'escalate_unit_plan'
        or route == 'unit_plan'
        or classification in {'unit_plan_gap', 'architecture_issue'}
    )


def _bug_fix_unit_plan_escalation_feedback(
    state: dict[str, Any],
    bug_fix_summary: dict[str, Any],
    root_cause: dict[str, Any],
) -> str:
    return (
        'Bug Fix root cause requires Unit Plan revision.\n\n'
        f"Bug Fix ID: {state.get('activeBugFixId')}\n"
        f"Classification: {root_cause.get('classification') or 'unknown'}\n"
        f"Root cause: {root_cause.get('summary') or 'not provided'}\n\n"
        'Original final acceptance defect feedback:\n\n'
        f"{state.get('finalAcceptanceDefectFeedback') or state.get('finalAcceptanceRejectionFeedback') or ''}\n\n"
        'Bug fix summary:\n\n'
        f"{json.dumps(bug_fix_summary, ensure_ascii=False, indent=2)}"
    )


def _bug_fix_failure_verdict(
    bug_fix_summary: dict[str, Any],
    root_cause: dict[str, Any],
) -> dict[str, Any]:
    return {
        'passed': False,
        'issues': [
            {
                'severity': 'high',
                'type': 'bug_fix_failed',
                'message': str(
                    bug_fix_summary.get('message')
                    or root_cause.get('summary')
                    or 'Bug Fix Agent did not complete successfully'
                ),
            }
        ],
    }


def _ensure_final_acceptance_rejection_route_from_prompt(
    gate_path: Path,
    input_func: Callable[[str], str],
    output_func: Callable[[str], None],
) -> bool:
    try:
        _final_acceptance_rejection_route(gate_path.read_text(encoding='utf-8'))
        return True
    except ValueError:
        pass

    output_func('[验收路由] 请选择最终验收不通过后的流向：')
    output_func('  1  验收缺陷修复 -> Defect Fix')
    output_func('  2  需求变更 -> Requirements')
    output_func('  3  Unit Plan 问题 -> Unit Plan')
    output_func('  4  实现返工 -> Builder')
    output_func('  5  阻塞/资料环境问题 -> Blocked')
    output_func('  q  取消')
    route_by_choice = {
        '1': 'defect_fix',
        'defect': 'defect_fix',
        'defect-fix': 'defect_fix',
        'defect_fix': 'defect_fix',
        'bug': 'defect_fix',
        'bug-fix': 'defect_fix',
        'bugfix': 'defect_fix',
        'fix': 'defect_fix',
        '缺陷': 'defect_fix',
        '缺陷修复': 'defect_fix',
        '修bug': 'defect_fix',
        '验收缺陷': 'defect_fix',
        '验收缺陷修复': 'defect_fix',
        '2': 'requirements',
        'requirements': 'requirements',
        'requirement': 'requirements',
        'req': 'requirements',
        '需求': 'requirements',
        '需求变更': 'requirements',
        '3': 'unit_plan',
        'unit': 'unit_plan',
        'unit-plan': 'unit_plan',
        'unit_plan': 'unit_plan',
        'plan': 'unit_plan',
        '计划': 'unit_plan',
        '4': 'implementation',
        'implementation': 'implementation',
        'impl': 'implementation',
        'builder': 'implementation',
        '实现': 'implementation',
        '实现返工': 'implementation',
        '5': 'blocked',
        'blocked': 'blocked',
        'block': 'blocked',
        '阻塞': 'blocked',
    }
    while True:
        try:
            choice = input_func('route> ').strip().lower()
        except EOFError:
            output_func('[退出] 未收到验收路由，已停止在人工确认点。')
            return False
        if choice in {'q', 'quit', 'exit'}:
            output_func('[退出] 已取消最终验收返工。')
            return False
        route = route_by_choice.get(choice)
        if route:
            _write_final_acceptance_rejection_route(gate_path, route)
            output_func(f"[验收路由] 已选择：{FINAL_ACCEPTANCE_REJECTION_ROUTE_LABELS[route]}")
            return True
        output_func('[提示] 请输入 1 / 2 / 3 / 4 / 5 / q。')


def _write_final_acceptance_rejection_route(gate_path: Path, route: str) -> None:
    if route not in FINAL_ACCEPTANCE_REJECTION_ROUTE_LABELS:
        raise ValueError(f'Unknown final acceptance rejection route: {route}')
    content = gate_path.read_text(encoding='utf-8')
    write_gate_file(
        gate_path,
        normalize_final_acceptance_rejection_routing(gate_body(content), selected_route=route),
    )


def _verification_progress_printer(
    output_func: Callable[[str], None],
    color_enabled: bool,
) -> Callable[[dict[str, Any]], None]:
    def print_event(event: dict[str, Any]) -> None:
        event_type = event.get('event')
        if event_type == 'verification_started':
            output_func(
                _paint('[验证]', 'cyan', color_enabled)
                + f" 开始 {event.get('total', 0)} 个命令"
            )
            return
        if event_type == 'verification_command_started':
            output_func(
                _paint('[验证]', 'cyan', color_enabled)
                + f" ... {event.get('index')}/{event.get('total')} "
                + _short_command(str(event.get('command') or ''))
            )
            return
        if event_type == 'verification_command_finished':
            status = '通过' if event.get('ok') else '失败'
            style = 'green' if event.get('ok') else 'red'
            output_func(
                _paint('[验证]', 'cyan', color_enabled)
                + f" {_paint(status, style, color_enabled)} {event.get('index')}/{event.get('total')}"
                + f" exit={event.get('returncode')} 用时 {_format_duration(float(event.get('elapsed_seconds') or 0))}"
            )
            return
        if event_type == 'verification_finished':
            status = '通过' if event.get('passed') else '未通过'
            style = 'green' if event.get('passed') else 'red'
            output_func(_paint('[验证]', 'cyan', color_enabled) + f" 完成 {_paint(status, style, color_enabled)}")

    return print_event


def _uses_default_run_once(controller: RalphRefinerController) -> bool:
    return getattr(controller.run_once, '__func__', None) is RalphRefinerController.run_once


def _record_or_block_repeated_failure(
    state: dict[str, Any],
    *,
    stage: str,
    verdict: dict[str, Any],
    retry_step: str,
) -> None:
    unit_id = str(state.get('currentUnitId') or '')
    fingerprint, details = _failure_fingerprint(stage, verdict)
    previous = state.get('lastFailure') if isinstance(state.get('lastFailure'), dict) else {}
    previous = previous or {}
    count = 1
    if (
        previous.get('unit_id') == unit_id
        and previous.get('stage') == stage
        and previous.get('fingerprint') == fingerprint
    ):
        count = int(previous.get('count') or 0) + 1

    summary = _failure_summary(stage, details)
    state['lastFailure'] = {
        'unit_id': unit_id,
        'stage': stage,
        'fingerprint': fingerprint,
        'count': count,
        'summary': summary,
        'details': details,
    }

    max_retries = _same_failure_max_retries(state)
    if count > max_retries:
        state['status'] = 'blocked'
        state['currentStep'] = stage
        state['blockedReason'] = (
            f'Repeated {stage} failure for {unit_id or "unknown unit"} '
            f'({count} consecutive occurrences; limit {max_retries}). {summary}'
        )
        return

    state['status'] = 'active'
    state['currentStep'] = retry_step
    state['blockedReason'] = None


def _simplifier_failure_verdict(result: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    for finding in result.get('findings') or []:
        if not isinstance(finding, dict):
            continue
        finding_type = str(finding.get('type') or result.get('status') or 'simplifier_feedback')
        message = str(
            finding.get('message')
            or finding.get('detail')
            or finding.get('description')
            or finding_type
        )
        issues.append({'type': finding_type, 'message': message})

    if not issues:
        status = str(result.get('status') or 'failed')
        issues.append({
            'type': f'simplifier_{status}',
            'message': f'CodeSimplifier returned status {status}',
        })

    return {
        'issues': issues,
        'simplifier_status': result.get('status'),
        'mode': result.get('mode'),
        'changed_files': result.get('changed_files') or [],
    }


def _clear_last_failure(state: dict[str, Any]) -> None:
    state.pop('lastFailure', None)
    if state.get('status') != 'blocked':
        state['blockedReason'] = None


def _same_failure_max_retries(state: dict[str, Any]) -> int:
    raw_value = state.get('sameFailureMaxRetries', DEFAULT_SAME_FAILURE_MAX_RETRIES)
    try:
        return max(0, int(raw_value))
    except (TypeError, ValueError):
        return DEFAULT_SAME_FAILURE_MAX_RETRIES


def _failure_fingerprint(stage: str, verdict: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    details: dict[str, Any] = {'stage': stage}
    issues = _issue_details(verdict)
    if issues:
        details['issues'] = issues

    if stage == 'VERIFY_UNIT':
        failed_results = [
            result for result in verdict.get('results') or []
            if isinstance(result, dict) and not result.get('ok')
        ]
        if failed_results:
            first = failed_results[0]
            details.update({
                'command': str(first.get('command') or ''),
                'returncode': first.get('returncode'),
                'stdout_tail': _text_tail(str(first.get('stdout') or '')),
                'stderr_tail': _text_tail(str(first.get('stderr') or '')),
            })
        else:
            details['commands'] = [str(command) for command in verdict.get('commands') or []]
    elif stage == 'REVIEW_UNIT':
        details['reviewer'] = verdict.get('reviewer')
    else:
        details['verdict'] = verdict

    fingerprint_source = json.dumps(details, ensure_ascii=False, sort_keys=True)
    fingerprint = hashlib.sha256(fingerprint_source.encode('utf-8')).hexdigest()
    return fingerprint, details


def _issue_details(verdict: dict[str, Any]) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for issue in verdict.get('issues') or []:
        if not isinstance(issue, dict):
            continue
        details.append({
            'type': str(issue.get('type') or ''),
            'message': _text_tail(str(issue.get('message') or ''), max_chars=500),
        })
    return details


def _failure_summary(stage: str, details: dict[str, Any]) -> str:
    if stage == 'VERIFY_UNIT':
        command = details.get('command')
        returncode = details.get('returncode')
        stdout_tail = str(details.get('stdout_tail') or '').strip()
        stderr_tail = str(details.get('stderr_tail') or '').strip()
        parts = []
        if command:
            parts.append(f'command `{command}`')
        if returncode is not None:
            parts.append(f'exit {returncode}')
        if stderr_tail:
            parts.append(f'stderr tail: {stderr_tail}')
        if stdout_tail:
            parts.append(f'stdout tail: {stdout_tail}')
        if parts:
            return '; '.join(parts)
    issues = details.get('issues') or []
    if issues:
        rendered = '; '.join(
            f"{issue.get('type')}: {issue.get('message')}"
            for issue in issues[:3]
        )
        return rendered or f'{stage} failed'
    return f'{stage} failed'


def _text_tail(text: str, max_chars: int = 1000) -> str:
    normalized = '\n'.join(line.rstrip() for line in text.strip().splitlines() if line.strip())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[-max_chars:]


class _CompactDriveReporter:
    def __init__(self, output_func: Callable[[str], None], *, color_enabled: bool) -> None:
        self.output_func = output_func
        self.color_enabled = color_enabled
        self.current_unit_id: str | None = None
        self.last_card_key: tuple[Any, ...] | None = None
        self.last_rendered_card: str | None = None
        self.attempt_number = 0
        self.stage_results: dict[str, str] = {}

    def print_roadmap_if_needed(self, state: dict[str, Any]) -> None:
        self.print_status(state)

    def print_status(
        self,
        state: dict[str, Any],
        *,
        current_label: str | None = None,
        planning_stage: str | None = None,
        force: bool = False,
    ) -> None:
        unit_id = str(state.get('currentUnitId') or '-')
        if unit_id != self.current_unit_id:
            self.current_unit_id = unit_id
            self.attempt_number = 0
            self.stage_results = {}
            self.last_card_key = None
            self.last_rendered_card = None
        action = state.get('nextAction') or compute_next_allowed_action(state)
        card_key = (
            unit_id,
            state.get('currentStep'),
            action,
            current_label,
            planning_stage,
            state.get('blockedReason'),
        )
        if not force and card_key == self.last_card_key:
            return
        self.last_card_key = card_key
        rendered = _compact_roadmap(
            state,
            color_enabled=self.color_enabled,
            current_label=current_label,
            planning_stage=planning_stage,
        )
        if not force and rendered == self.last_rendered_card:
            return
        self.last_rendered_card = rendered
        self.output_func(rendered)

    def record_transition(
        self,
        before_state: dict[str, Any],
        action: str | None,
        after_state: dict[str, Any],
        elapsed_seconds: float,
    ) -> None:
        if before_state.get('currentUnitId') != after_state.get('currentUnitId'):
            self.print_roadmap_if_needed(after_state)
            return
        if action == 'run_builder':
            self._ensure_attempt()
            self.stage_results['Builder'] = _format_duration(elapsed_seconds)
            return
        if action == 'run_refiner':
            self._ensure_attempt()
            failed = after_state.get('currentStep') in {'EXECUTE_UNIT', 'REFINE_UNIT'}
            self.stage_results['Refiner'] = 'failed' if failed else 'ok'
            if failed:
                self._print_attempt_summary()
                self._print_retry('refinement failed', _compact_failure_reason(after_state))
            return
        if action == 'run_reviewer':
            self._ensure_attempt()
            failed = after_state.get('currentStep') == 'EXECUTE_UNIT'
            self.stage_results['Reviewer'] = 'failed' if failed else 'ok'
            if failed:
                self._print_attempt_summary()
                self._print_retry('review failed', _compact_failure_reason(after_state))
            return
        if action == 'run_verifier':
            self._ensure_attempt()
            failed = after_state.get('currentStep') == 'EXECUTE_UNIT'
            self.stage_results['Verifier'] = 'failed' if failed else 'ok'
            self._print_attempt_summary()
            if failed:
                self._print_retry('verification failed', _compact_failure_reason(after_state))

    def _ensure_attempt(self) -> None:
        if self.attempt_number == 0 or self.stage_results.get('_closed') == 'true':
            self.attempt_number += 1
            self.stage_results = {}

    def _print_attempt_summary(self) -> None:
        parts = []
        for stage in ['Builder', 'Refiner', 'Reviewer', 'Verifier']:
            result = self.stage_results.get(stage)
            if not result:
                continue
            stage_label = COMPACT_STAGE_LABELS[stage]
            if stage == 'Builder':
                parts.append(f'{stage_label} {result}')
            else:
                style = 'green' if result == 'ok' else 'red'
                result_label = COMPACT_RESULT_LABELS.get(result, result)
                parts.append(f'{stage_label} {_paint(result_label, style, self.color_enabled)}')
        if parts:
            self.output_func(_paint(f"第 {self.attempt_number} 轮", 'blue', self.color_enabled) + f"  {' -> '.join(parts)}")
        self.stage_results['_closed'] = 'true'

    def _print_retry(self, reason: str, detail: str | None = None) -> None:
        reason_label = COMPACT_RETRY_REASONS.get(reason, reason)
        detail_suffix = f"：{detail}" if detail else ''
        self.output_func(
            _paint(f"重试第 {self.attempt_number + 1} 轮", 'yellow', self.color_enabled)
            + f"    {_stage_tokens('Builder', color_enabled=self.color_enabled)}\n"
            f"          原因 {_paint(reason_label + detail_suffix, 'red', self.color_enabled)}"
        )


def _compact_roadmap(
    state: dict[str, Any],
    *,
    color_enabled: bool = False,
    current_label: str | None = None,
    planning_stage: str | None = None,
) -> str:
    unit_id = str(state.get('currentUnitId') or '-')
    project_target_version = _project_target_version(state)
    units = _display_units_for_state(state)
    unit_ids = [str(unit.get('id')) for unit in units]
    total = len(units) or 1
    try:
        index = unit_ids.index(unit_id) + 1
    except ValueError:
        index = 1
    remaining_after = sum(
        1
        for unit in units[index:]
        if not unit.get('passes')
    )
    action = state.get('nextAction') or compute_next_allowed_action(state)
    now = current_label or _compact_current_label(state, action)
    return (
        f"{_paint('▶', 'green', color_enabled)} {_paint(project_target_version, 'bold', color_enabled)}  项目目标版本/分支\n"
        f"          {_paint('单元', 'cyan', color_enabled)}   {index}/{total}  {unit_id}\n"
        f"          {_paint('阶段', 'cyan', color_enabled)} {_stage_tokens_for_state(state, color_enabled=color_enabled, planning_stage=planning_stage)}\n"
        f"          {_paint('当前', 'cyan', color_enabled)}   {_paint(str(now), 'yellow', color_enabled) if now != '-' else now}\n"
        f"          {_paint('剩余', 'cyan', color_enabled)}   {_paint(str(remaining_after), 'dim', color_enabled)} 个单元"
    )


def _project_target_version(state: dict[str, Any]) -> str:
    return str(state.get('feasibleOutcome') or state.get('requestedOutcome') or '-')


def _compact_current_label(state: dict[str, Any], action: str | None) -> str:
    step = str(state.get('currentStep') or '')
    step_labels = {
        'WAITING_REQUIREMENTS_ACCEPTANCE': '等待需求与验收确认',
        'WAITING_UNIT_PLAN_APPROVAL': '等待 Unit Plan 确认',
        'WAITING_FINAL_ACCEPTANCE': '等待最终验收确认',
        'WAITING_BUG_FIX_GATE': '等待 Bug Fix 确认',
    }
    if step in step_labels:
        return step_labels[step]
    return ACTION_LABELS.get(action, action) if action else '-'


def _display_units_for_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    units = [unit for unit in state.get('units') or [] if isinstance(unit, dict)]
    requested = str(state.get('requestedOutcome') or '').strip().lower()
    if not requested:
        return units

    target_unit_ids: set[str] = set()
    for coverage in state.get('objectiveCoverage') or []:
        objective = str(coverage.get('objective') or '').lower()
        if requested and requested in objective:
            target_unit_ids.update(str(unit_id) for unit_id in coverage.get('units') or [])

    if not target_unit_ids:
        return units

    target_units = [
        unit for unit in units
        if str(unit.get('id')) in target_unit_ids
    ]
    current_unit_id = str(state.get('currentUnitId') or '')
    if target_units and any(str(unit.get('id')) == current_unit_id for unit in target_units):
        return target_units
    return units


def _compact_failure_reason(state: dict[str, Any]) -> str | None:
    last_failure = state.get('lastFailure')
    if not isinstance(last_failure, dict):
        return None
    details = last_failure.get('details')
    if not isinstance(details, dict):
        summary = str(last_failure.get('summary') or '').strip()
        return _short_failure_text(summary) if summary else None

    parts: list[str] = []
    command = str(details.get('command') or '').strip()
    if command:
        parts.append(_short_command(command, max_chars=80))
    returncode = details.get('returncode')
    if returncode is not None:
        parts.append(f'exit {returncode}')
    root_cause = _extract_failure_root_cause(details)
    if root_cause:
        parts.append(root_cause)
    if parts:
        return _short_failure_text(' | '.join(parts))
    summary = str(last_failure.get('summary') or '').strip()
    return _short_failure_text(summary) if summary else None


def _extract_failure_root_cause(details: dict[str, Any]) -> str | None:
    text = '\n'.join(
        str(details.get(key) or '')
        for key in ('stdout_tail', 'stderr_tail')
    )
    if not text.strip():
        return None
    patterns = [
        r'Environment variable not found:\s*([A-Z0-9_]+)',
        r'(DATABASE_URL[^\n]*)',
        r'(Error:\s*[^\n]+)',
        r'(PrismaClientInitializationError[^\n]*)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        if len(match.groups()) == 1 and pattern.startswith('Environment variable'):
            return f'missing env {match.group(1)}'
        return ' '.join(match.group(1).split())
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _short_failure_text(text: str, max_chars: int = 220) -> str:
    normalized = ' '.join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3] + '...'


def _stage_for_state(state: dict[str, Any]) -> str | None:
    step = state.get('currentStep')
    if step in {'PLAN_APPROVED', 'UI_DESIGN_DONE', 'EXECUTE_UNIT'}:
        return 'Builder'
    if step == 'REFINE_UNIT':
        return 'Refiner'
    if step == 'REVIEW_UNIT':
        return 'Reviewer'
    if step == 'VERIFY_UNIT':
        return 'Verifier'
    if step == 'UNIT_COMPLETE':
        return 'Unit done'
    return None


def _stage_tokens(current_stage: str | None, *, color_enabled: bool = False) -> str:
    stages = ['Builder', 'Refiner', 'Reviewer', 'Verifier', 'Unit done']
    return _format_stage_tokens(stages, COMPACT_STAGE_LABELS, current_stage, color_enabled=color_enabled)


def _stage_tokens_for_state(
    state: dict[str, Any],
    *,
    color_enabled: bool = False,
    planning_stage: str | None = None,
) -> str:
    action = state.get('nextAction') or compute_next_allowed_action(state)
    planning_stage = planning_stage or COMPACT_PLANNING_ACTION_STAGES.get(str(action))
    if planning_stage:
        stages = [
            'Requirements draft',
            'Requirements confirmation',
            'Unit plan',
            'Unit plan confirmation',
            'Builder',
        ]
        return _format_stage_tokens(
            stages,
            COMPACT_PLANNING_STAGE_LABELS,
            planning_stage,
            color_enabled=color_enabled,
        )
    return _stage_tokens(_stage_for_state(state), color_enabled=color_enabled)


def _format_stage_tokens(
    stages: list[str],
    labels: dict[str, str],
    current_stage: str | None,
    *,
    color_enabled: bool = False,
) -> str:
    return ' '.join(
        _paint(f'[{labels[stage]}*]', 'yellow', color_enabled)
        if stage == current_stage
        else _paint(f'[{labels[stage]}]', 'dim', color_enabled)
        for stage in stages
    )


def _format_duration(seconds: float) -> str:
    whole_seconds = max(0, int(round(seconds)))
    minutes, seconds = divmod(whole_seconds, 60)
    if minutes:
        return f'{minutes}m{seconds:02d}s'
    return f'{seconds}s'


def _short_command(command: str, max_chars: int = 120) -> str:
    normalized = ' '.join(command.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3] + '...'


def _color_enabled(color_mode: str) -> bool:
    if color_mode == 'always':
        return True
    if color_mode == 'never':
        return False
    return sys.stdout.isatty()


def _paint(text: str, style: str, enabled: bool) -> str:
    if not enabled:
        return text
    code = ANSI_STYLES.get(style)
    if not code:
        return text
    return f'{code}{text}{ANSI_RESET}'


def _automatic_progress_key(state: dict[str, Any], action: str | None) -> tuple[Any, ...]:
    units = tuple(
        (unit.get('id'), bool(unit.get('passes')))
        for unit in state.get('units') or []
        if isinstance(unit, dict)
    )
    coverage = tuple(
        (
            item.get('objective'),
            tuple(item.get('units') or []),
            item.get('status'),
        )
        for item in state.get('objectiveCoverage') or []
        if isinstance(item, dict)
    )
    return (
        state.get('status'),
        state.get('currentStep'),
        state.get('currentUnitId'),
        action,
        state.get('blockedReason'),
        bool(state.get('scopeApproved')),
        bool(state.get('requirementsAccepted')),
        bool(state.get('unitPlanAccepted')),
        bool(state.get('finalAcceptanceAccepted')),
        units,
        coverage,
    )


def _approved_gate_invalid_reason(gate: str, state: dict[str, Any]) -> str | None:
    reason = str(state.get('blockedReason') or '')
    if gate == 'requirements' and reason.startswith('requirements gate invalid:'):
        return reason
    if gate == 'unit-plan' and reason.startswith('unit plan gate invalid:'):
        return reason
    if gate == 'final-acceptance' and reason.startswith('final acceptance gate invalid:'):
        return reason
    return None


def _requirements_validation_state_key(state: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (
        state.get('currentStep'),
        state.get('requirementsAccepted'),
        state.get('blockedReason'),
    )


def _unit_plan_validation_state_key(state: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (
        state.get('currentStep'),
        state.get('unitPlanAccepted'),
        state.get('blockedReason'),
    )


def _timestamped_output(output_func: Callable[[str], None]) -> Callable[[str], None]:
    def emit(message: str) -> None:
        prefix = datetime.now().strftime('[%H:%M:%S] ')
        lines = str(message).splitlines()
        if not lines:
            output_func(prefix.rstrip())
            return
        for line in lines:
            output_func(f'{prefix}{line}')

    return emit


def _print_plannotator_output(output: str, output_func: Callable[[str], None]) -> None:
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or _should_hide_plannotator_output_line(stripped):
            continue
        output_func(f'  {line}')


def _should_hide_plannotator_output_line(line: str) -> bool:
    hidden_prefixes = (
        'Open this link on your local machine to annotate:',
        'https://share.plannotator.ai/#',
    )
    return line.startswith(hidden_prefixes)


def _plannotator_review_path_for_gate(artifacts_dir: Path, gate: str, approval_gate_path: Path) -> Path:
    if gate == 'requirements':
        review_path, manifest_path, _ = prototype_review_paths(artifacts_dir)
        if review_path.exists() and manifest_path.exists():
            return review_path
    return approval_gate_path


def _record_plannotator_review_paths(
    summary_path: Path,
    *,
    approval_gate_path: Path,
    review_path: Path,
    prototype_review_manifest_path: Path | None = None,
    prototype_review_preview_url: str | None = None,
) -> None:
    try:
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return
    if not isinstance(summary, dict):
        return
    summary['review_path'] = str(review_path)
    summary['approval_gate_path'] = str(approval_gate_path)
    summary['full_path'] = str(review_path)
    if prototype_review_manifest_path is not None:
        summary['prototype_review_manifest_path'] = str(prototype_review_manifest_path)
    if prototype_review_preview_url:
        summary['prototype_review_preview_url'] = prototype_review_preview_url
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')


def _plannotator_summary_path(state_dir: Path, gate: str) -> Path:
    return state_dir / 'plannotator' / f'{gate}-last-review.json'


def _read_plannotator_submitted_feedback(
    state_dir: Path,
    gate: str,
    gate_path: Path,
    gate_content: str,
) -> tuple[str | None, list[Any] | None, str | None]:
    decision = _read_plannotator_decision(state_dir, gate, gate_path, gate_content)
    if decision.get('status') == 'stale' and gate == 'final-acceptance':
        decision = _read_plannotator_decision(state_dir, gate, gate_path)
    if decision.get('status') in {'missing', 'stale', 'path-mismatch'}:
        return None, None, None
    if decision.get('status') == 'feedback':
        annotations = decision.get('annotations') if isinstance(decision.get('annotations'), list) else None
        return str(decision.get('feedback') or '').strip(), annotations, None
    if decision.get('status') == 'pending':
        return None, None, '请先在 Plannotator 浏览器完成当前审阅，等待其提交决策后再输入 r'
    if decision.get('status') == 'approved':
        return None, None, 'Plannotator 已返回 Approve；如需通过请直接输入 a，或重新打开审阅'
    return None, None, 'Plannotator 没有返回返工反馈；如需返工，请在确认文件里写批注后输入 r'


def _gate_changed_after_plannotator_review(summary_path: Path, gate_path: Path, gate_content: str) -> bool:
    try:
        return gate_path.stat().st_mtime > summary_path.stat().st_mtime and bool(gate_body(gate_content).strip())
    except FileNotFoundError:
        return False


def _read_optional_text(path: Path) -> str:
    if not path.exists():
        return ''
    return path.read_text(encoding='utf-8', errors='replace')


def _plannotator_feedback_summary(decision: dict[str, Any]) -> str | None:
    feedback = str(decision.get('feedback') or '').strip()
    if not feedback:
        return None
    count = _plannotator_feedback_count(decision)
    if count > 1:
        return f'共 {count} 条，完整反馈已写入 Claude 返工 prompt。'
    if count == 1:
        return '共 1 条，完整反馈已写入 Claude 返工 prompt。'
    return '完整反馈已写入 Claude 返工 prompt。'


def _plannotator_feedback_count(decision: dict[str, Any]) -> int:
    annotations = decision.get('annotations')
    if isinstance(annotations, list) and annotations:
        return len(annotations)
    feedback = str(decision.get('feedback') or '')
    heading_count = len(re.findall(r'(?m)^##\s+\d+\.\s+Feedback on:', feedback))
    if heading_count:
        return heading_count
    match = re.search(r"have\s+(\d+)\s+pieces?\s+of\s+feedback", feedback, flags=re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return 0
    return 1 if feedback.strip() else 0


def _plannotator_feedback_preview(decision: dict[str, Any]) -> str | None:
    feedback = str(decision.get('feedback') or '').strip()
    if not feedback:
        return None
    return _short_failure_text(feedback, max_chars=220)


def _wait_for_plannotator_gate_decision(
    state_dir: Path,
    gate: str,
    gate_path: Path,
    output_func: Callable[[str], None],
) -> dict[str, Any]:
    status_announced = False
    while True:
        decision = _read_plannotator_decision(state_dir, gate, gate_path)
        if decision.get('status') != 'pending':
            return decision
        if not status_announced:
            output_func('  等待 Plannotator 操作结果...')
            status_announced = True
        time.sleep(0.25)


def _read_plannotator_decision(
    state_dir: Path,
    gate: str,
    gate_path: Path,
    gate_content: str | None = None,
) -> dict[str, Any]:
    summary_path = _plannotator_summary_path(state_dir, gate)
    if not summary_path.exists():
        return {'status': 'missing'}
    try:
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {'status': 'missing'}
    summary_gate_path = str(summary.get('gate_path') or '')
    summary_approval_gate_path = str(summary.get('approval_gate_path') or '')
    if summary_gate_path != str(gate_path) and summary_approval_gate_path != str(gate_path):
        return {'status': 'path-mismatch'}
    if gate_content is not None and _gate_changed_after_plannotator_review(summary_path, gate_path, gate_content):
        return {'status': 'stale'}

    stdout = str(summary.get('stdout') or '')
    stdout_path = summary.get('stdout_path')
    if stdout_path:
        stdout = (stdout + '\n' + _read_optional_text(Path(str(stdout_path)))).strip()

    decision = _extract_plannotator_decision(stdout)
    if decision.get('status') != 'none':
        return decision

    if _process_is_alive(summary.get('process_id')):
        return {'status': 'pending'}
    return {'status': 'closed'}


def _extract_plannotator_feedback(output: str) -> str | None:
    decision = _extract_plannotator_decision(output)
    if decision.get('status') == 'feedback':
        return str(decision.get('feedback') or '').strip()
    return None


def _extract_plannotator_decision(output: str) -> dict[str, Any]:
    saw_json = False
    for line in reversed([line.strip() for line in output.splitlines() if line.strip()]):
        if not line.startswith('{'):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        saw_json = True
        decision = str(payload.get('decision') or '').strip().lower()
        if decision in {'approved', 'approve'}:
            return {'status': 'approved'}
        if decision in {'exit', 'closed', 'close', 'dismissed', 'cancelled', 'canceled'}:
            return {'status': 'closed'}
        annotations = payload.get('annotations')
        feedback = str(payload.get('feedback') or payload.get('reason') or '').strip()
        if not feedback and isinstance(annotations, list) and annotations:
            feedback = (
                '# Plannotator Annotations\n\n'
                + json.dumps(annotations, ensure_ascii=False, indent=2)
            )
        if feedback:
            decision_payload = {'status': 'feedback', 'feedback': feedback}
            if isinstance(annotations, list):
                decision_payload['annotations'] = annotations
            return decision_payload
        if decision in {'annotated', 'block', 'blocked', 'feedback', 'rejected', 'revise'}:
            return {'status': 'feedback', 'feedback': ''}
    if saw_json:
        return {'status': 'none'}
    plain_output = output.strip()
    if plain_output and not _has_plannotator_link_only_output(plain_output):
        return {'status': 'feedback', 'feedback': plain_output}
    return {'status': 'none'}


def _has_plannotator_link_only_output(output: str) -> bool:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return False
    ignored_prefixes = (
        'Open this link on your local machine to annotate:',
        'https://share.plannotator.ai/#',
        'Resolved:',
        '(',
    )
    return all(line.startswith(ignored_prefixes) for line in lines)


def _process_is_alive(process_id: Any) -> bool:
    try:
        pid = int(process_id)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        waited_pid, _status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        waited_pid = 0
    if waited_pid == pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _agent_guide_workspace_dir(
    *,
    explicit_workspace: Path | None,
    state_dir: Path,
    state: dict[str, Any],
) -> Path:
    if explicit_workspace is not None:
        return explicit_workspace
    workspace_path = state.get('executionWorkspacePath') or state.get('workspacePath')
    if workspace_path:
        return Path(str(workspace_path))
    return state_dir.parent


def _detect_tmux_target_backend(
    tmux_target: str,
    workspace_dir: Path,
    *,
    tmux_command: list[str] | None = None,
) -> str | None:
    return _inspect_tmux_target(tmux_target, workspace_dir, tmux_command=tmux_command).get('detectedBackend')


def _discover_tmux_agent_target(
    desired_backend: str,
    workspace_dir: Path,
    *,
    tmux_command: list[str] | None = None,
) -> dict[str, Any] | None:
    if not os.environ.get('TMUX'):
        return None
    tmux_targets = _tmux_list_pane_targets(workspace_dir, tmux_command=tmux_command)
    current_pane = _current_tmux_pane_from_environment(tmux_targets)
    inspections: list[dict[str, Any]] = []
    for tmux_target in tmux_targets:
        if current_pane and tmux_target == current_pane:
            continue
        inspection = _inspect_tmux_target(tmux_target, workspace_dir, tmux_command=tmux_command)
        if inspection.get('detectedBackend') != desired_backend:
            continue
        inspections.append(inspection)
        if _tmux_pane_path_matches_workspace(inspection.get('paneCurrentPath'), workspace_dir):
            return inspection
    if len(inspections) == 1:
        return inspections[0]
    return None


def _current_tmux_pane_from_environment(tmux_targets: list[str]) -> str:
    current_pane = os.environ.get('TMUX_PANE', '').strip()
    if current_pane and current_pane in set(tmux_targets):
        return current_pane
    return ''


def _tmux_list_pane_targets(
    workspace_dir: Path,
    *,
    tmux_command: list[str] | None = None,
) -> list[str]:
    completed = _run_tmux_probe(
        [*(tmux_command or ['tmux']), 'list-panes', '-F', '#{pane_id}'],
        workspace_dir,
    )
    if not completed or completed.returncode != 0:
        return []
    targets: list[str] = []
    for line in completed.stdout.splitlines():
        target = line.strip()
        if target:
            targets.append(target)
    return targets


def _tmux_pane_path_matches_workspace(raw_path: Any, workspace_dir: Path) -> bool:
    text = str(raw_path or '').strip()
    if not text:
        return False
    try:
        return Path(text).expanduser().resolve() == workspace_dir.expanduser().resolve()
    except OSError:
        return Path(text).expanduser() == workspace_dir.expanduser()


def _inspect_tmux_target(
    tmux_target: str,
    workspace_dir: Path,
    *,
    tmux_command: list[str] | None = None,
) -> dict[str, Any]:
    pane_command = _tmux_display_message(
        tmux_target,
        '#{pane_current_command}',
        workspace_dir,
        tmux_command=tmux_command,
    ).strip()
    pane_title = _tmux_display_message(
        tmux_target,
        '#{pane_title}',
        workspace_dir,
        tmux_command=tmux_command,
    ).strip()
    pane_current_path = _tmux_display_message(
        tmux_target,
        '#{pane_current_path}',
        workspace_dir,
        tmux_command=tmux_command,
    ).strip()
    pane_pid = _tmux_display_message(
        tmux_target,
        '#{pane_pid}',
        workspace_dir,
        tmux_command=tmux_command,
    ).strip()
    process_tree = _tmux_pane_process_tree(pane_pid, workspace_dir)
    pane_output = _tmux_capture_pane(tmux_target, workspace_dir, tmux_command=tmux_command)
    for source, text in (
        ('command', pane_command),
        ('title', pane_title),
        ('process-tree', process_tree),
        ('pane-output', pane_output),
    ):
        agent = _detect_agent_from_text(text)
        if agent:
            return {
                'target': tmux_target,
                'paneCommand': pane_command,
                'paneTitle': pane_title,
                'paneCurrentPath': pane_current_path,
                'panePid': pane_pid,
                'detectedAgent': agent,
                'detectedBackend': TMUX_DETECTED_AGENT_BACKENDS[agent],
                'detectedSource': source,
            }
    return {
        'target': tmux_target,
        'paneCommand': pane_command,
        'paneTitle': pane_title,
        'paneCurrentPath': pane_current_path,
        'panePid': pane_pid,
        'detectedAgent': None,
        'detectedBackend': None,
        'detectedSource': None,
    }


def _tmux_target_resolution(
    *,
    target: str,
    runner: str,
    inspection: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    return {
        'target': target,
        'runner': runner,
        'detectedBackend': inspection.get('detectedBackend'),
        'detectedSource': inspection.get('detectedSource'),
        'source': source,
        'paneCommand': inspection.get('paneCommand') or '',
        'paneTitle': inspection.get('paneTitle') or '',
        'paneCurrentPath': inspection.get('paneCurrentPath') or '',
        'panePid': inspection.get('panePid') or '',
    }


def _auto_created_tmux_target_resolution(tmux_target: str, workspace_dir: Path) -> dict[str, Any]:
    return {
        'target': tmux_target,
        'runner': 'tmux-claude',
        'detectedBackend': 'tmux-claude',
        'detectedSource': 'auto-created',
        'source': 'auto-created',
        'paneCommand': shlex.join(_auto_claude_pane_command()),
        'workspacePath': str(workspace_dir),
    }


def _is_auto_created_tmux_claude_target(state: dict[str, Any], tmux_target: str) -> bool:
    resolution = state.get('tmuxTargetResolution')
    if not isinstance(resolution, dict):
        return False
    resolution_target = str(resolution.get('target') or state.get('tmuxTarget') or '')
    if resolution_target and resolution_target != tmux_target:
        return False
    return (
        str(state.get('agentRunner') or resolution.get('runner') or '') == 'tmux-claude'
        and (resolution.get('source') == 'auto-created' or resolution.get('detectedSource') == 'auto-created')
    )


def _tmux_target_inspection_is_missing(inspection: dict[str, Any]) -> bool:
    if inspection.get('detectedBackend'):
        return False
    for key in ('paneCommand', 'paneTitle', 'paneCurrentPath', 'panePid'):
        if str(inspection.get(key) or '').strip():
            return False
    return True


def _tmux_resolution_source(
    *,
    detected_backend: str | None,
    explicit_runner: str | None,
    state_runner: str | None,
) -> str:
    if detected_backend:
        return 'detected'
    if explicit_runner:
        return 'explicit-runner'
    if state_runner:
        return 'state-runner'
    return 'fallback-default'


def _apply_tmux_target_resolution(state: dict[str, Any], resolution: dict[str, Any] | None) -> None:
    if resolution:
        state['tmuxTargetResolution'] = resolution
    elif not state.get('tmuxTarget'):
        state.pop('tmuxTargetResolution', None)


def _format_tmux_target_resolution(resolution: Any) -> str | None:
    if not isinstance(resolution, dict):
        return None
    target = _compact_tmux_probe_value(resolution.get('target')) or '-'
    runner = _compact_tmux_probe_value(resolution.get('runner')) or '-'
    detected = _compact_tmux_probe_value(resolution.get('detectedBackend')) or 'unknown'
    source = _compact_tmux_probe_value(resolution.get('source')) or '-'
    parts = [
        f'[tmux] target={target}',
        f'runner={runner}',
        f'detected={detected}',
        f'source={source}',
    ]
    submit_key = _tmux_submit_key_for_report(runner)
    if submit_key:
        parts.append(f'submitKey={submit_key}')
    submit_delay = _tmux_submit_delay_for_report(runner)
    if submit_delay is not None:
        parts.append(f'submitDelay={submit_delay:.1f}s')
    pane_command = _compact_tmux_probe_value(resolution.get('paneCommand'))
    pane_title = _compact_tmux_probe_value(resolution.get('paneTitle'))
    pane_current_path = _compact_tmux_probe_value(resolution.get('paneCurrentPath'))
    workspace_path = _compact_tmux_probe_value(resolution.get('workspacePath'))
    if pane_command:
        parts.append(f'command={pane_command}')
    if pane_title:
        parts.append(f'title={pane_title}')
    if pane_current_path:
        parts.append(f'path={pane_current_path}')
    elif workspace_path:
        parts.append(f'workspace={workspace_path}')
    detected_source = _compact_tmux_probe_value(resolution.get('detectedSource'))
    if detected_source and detected_source != source:
        parts.append(f'detectedSource={detected_source}')
    return ' '.join(parts)


def _tmux_submit_key_for_report(runner: str) -> str:
    if runner == 'tmux-codex':
        return os.environ.get('RRC_TMUX_CODEX_SUBMIT_KEY') or 'Enter'
    if runner == 'tmux-claude':
        return os.environ.get('RRC_TMUX_CLAUDE_SUBMIT_KEY') or 'C-m'
    return ''


def _tmux_submit_delay_for_report(runner: str) -> float | None:
    if runner == 'tmux-codex':
        return _env_float_for_report(
            'RRC_TMUX_CODEX_SUBMIT_DELAY_SECONDS',
            _env_float_for_report('RRC_TMUX_SUBMIT_DELAY_SECONDS', 2.0),
        )
    if runner == 'tmux-claude':
        return _env_float_for_report(
            'RRC_TMUX_CLAUDE_SUBMIT_DELAY_SECONDS',
            _env_float_for_report('RRC_TMUX_SUBMIT_DELAY_SECONDS', 0.5),
        )
    return None


def _env_float_for_report(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _format_tmux_inspection_details(inspection: dict[str, Any]) -> str:
    parts = []
    for key, label in (
        ('paneCommand', 'command'),
        ('paneTitle', 'title'),
        ('paneCurrentPath', 'path'),
        ('panePid', 'pid'),
        ('detectedSource', 'detectedSource'),
    ):
        value = _compact_tmux_probe_value(inspection.get(key))
        if value:
            parts.append(f'{label}={value}')
    return ', '.join(parts) or 'no tmux probe details'


def _compact_tmux_probe_value(value: Any, *, limit: int = 160) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    text = re.sub(r'\s+', ' ', text)
    if len(text) <= limit:
        return text
    return text[:limit - 3] + '...'


def _tmux_target_current_path(
    tmux_target: str,
    cwd: Path,
    *,
    tmux_command: list[str] | None = None,
) -> Path | None:
    raw_path = _tmux_display_message(
        tmux_target,
        '#{pane_current_path}',
        cwd,
        tmux_command=tmux_command,
    ).strip()
    if not raw_path:
        return None
    return Path(raw_path).expanduser()


def _is_target_acceptance_state(state: dict[str, Any]) -> bool:
    return 'targetMatchedPlanStep' in state or bool(state.get('humanGatesRequired'))


def _tmux_display_message(
    tmux_target: str,
    fmt: str,
    workspace_dir: Path,
    *,
    tmux_command: list[str] | None = None,
) -> str:
    completed = _run_tmux_probe(
        [*(tmux_command or ['tmux']), 'display-message', '-p', '-t', tmux_target, fmt],
        workspace_dir,
    )
    return completed.stdout if completed and completed.returncode == 0 else ''


def _tmux_capture_pane(
    tmux_target: str,
    workspace_dir: Path,
    *,
    tmux_command: list[str] | None = None,
) -> str:
    completed = _run_tmux_probe(
        [*(tmux_command or ['tmux']), 'capture-pane', '-t', tmux_target, '-p', '-S', '-80'],
        workspace_dir,
    )
    if not completed or completed.returncode != 0:
        return ''
    return completed.stdout


def _run_tmux_probe(command: list[str], workspace_dir: Path) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            cwd=workspace_dir,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _tmux_pane_process_tree(pane_pid: str, workspace_dir: Path) -> str:
    if not pane_pid:
        return ''
    completed = _run_process_probe(
        ['ps', '-o', 'pid=,ppid=,pgid=,comm=,args=', '-g', pane_pid],
        workspace_dir,
    )
    if completed and completed.returncode == 0:
        return completed.stdout
    return ''


def _run_process_probe(command: list[str], workspace_dir: Path) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            cwd=workspace_dir,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _tmux_command_for_controller(agent_command: str | None) -> list[str]:
    parts = shlex.split(agent_command) if agent_command else []
    if parts and Path(parts[0]).name == 'tmux':
        return parts
    return ['tmux']


def _detect_agent_from_text(text: str) -> str | None:
    lowered = text.lower()
    codex_seen = _has_agent_name_token(lowered, 'codex')
    claude_seen = _has_agent_name_token(lowered, 'claude')
    if codex_seen and not claude_seen:
        return 'codex'
    if claude_seen and not codex_seen:
        return 'claude'
    return None


def _has_agent_name_token(text: str, agent_name: str) -> bool:
    return bool(re.search(rf'(?<!tmux-)\b{re.escape(agent_name)}\b', text))


def _create_tmux_claude_pane(workspace_dir: Path) -> str:
    if not os.environ.get('TMUX'):
        raise ValueError(
            'No --tmux-target was provided and Waygate is not running inside a tmux session. '
            'Pass --tmux-target pointing at an existing Codex or Claude pane, or run the controller inside tmux.'
        )
    claude_command = _auto_claude_pane_command()
    command = [
        'tmux',
        'split-window',
        '-h',
        '-P',
        '-F',
        '#{pane_id}',
        '-c',
        str(workspace_dir),
        *claude_command,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=workspace_dir,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'Failed to create Claude tmux pane: {exc}') from exc
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f'Failed to create Claude tmux pane: {stderr}')
    pane_id = _last_nonempty_line(completed.stdout)
    if not pane_id:
        raise RuntimeError('Failed to create Claude tmux pane: tmux did not return a pane id')
    return pane_id


def _auto_claude_pane_command() -> list[str]:
    raw_command = os.environ.get('WAYGATE_AUTO_CLAUDE_COMMAND')
    if raw_command and raw_command.strip():
        return shlex.split(raw_command)
    permission_mode = os.environ.get('WAYGATE_AUTO_CLAUDE_PERMISSION_MODE', 'bypassPermissions').strip()
    command = ['claude']
    if permission_mode:
        command.extend(['--permission-mode', permission_mode])
    return command


def _last_nonempty_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return ''


def _go_target_slug(target: str) -> str:
    slug = ''.join(
        char.lower() if char.isalnum() or char in '._-' else '-'
        for char in target
    ).strip('-')
    return slug or 'target'


def _go_state_dir_for_target(target: str) -> str:
    return f'.rrc-controller-{_go_target_slug(target)}'


def _go_state_dir_in_workspace(state_dir_name: str, workspace_dir: str | None, workspace_explicit: bool) -> str:
    if workspace_explicit and workspace_dir:
        return str(Path(workspace_dir) / state_dir_name)
    return state_dir_name


def add_go_parser(subparsers: Any) -> argparse.ArgumentParser:
    go_parser = subparsers.add_parser(
        'go',
        help='Infer common defaults, initialize if needed, then continuously drive',
        allow_abbrev=False,
    )
    go_parser.add_argument('target_arg', nargs='?', metavar='TARGET', help='Target label or acceptance version to run')
    go_parser.add_argument('--state-dir', default=None, help='Directory containing session.json and artifacts/')
    go_parser.add_argument('--force', action='store_true', help='Reinitialize an existing session before driving')
    go_parser.add_argument('--dry-run', action='store_true', help='Simulate step execution by writing mock artifacts')
    go_parser.add_argument('--max-steps', type=int, default=DEFAULT_MAX_AUTOMATIC_STEPS, help='Maximum automatic steps to run before stopping')
    go_parser.add_argument('--auto-approve', action='store_true', help='Auto-generate low-risk approval artifacts during runtime')
    go_parser.add_argument('--workspace-dir', default=None, help='Target project workspace directory')
    go_parser.add_argument('--agent', default=None, help='Agent command used by the real builder runtime')
    go_parser.add_argument('--runner', default=None, help='Agent runner backend: subprocess, tmux-claude, or tmux-codex')
    go_parser.add_argument('--tmux-target', default=None, help='tmux pane target for tmux-codex or tmux-claude, for example 1.2')
    go_parser.add_argument('--target', default=None, help='Target label or acceptance version to run')
    go_parser.add_argument('--spec', default=None, help='Path to a supported Waygate Markdown requirements spec')
    go_parser.add_argument('--actor', default='human', help='Name recorded when approving a Human Confirmation gate')
    go_parser.add_argument('--unsafe-skip-human-gates', action='store_true', help='Bypass Markdown human gates and write an audit event')
    go_parser.add_argument('--no-agent-guides', action='store_false', dest='agent_guides', default=True, help='Do not generate AGENTS.md or documentation layout when start initializes state')
    go_parser.add_argument('--claude-md', action='store_true', default=False, help='Also generate a CLAUDE.md shim that points to AGENTS.md when start initializes state')
    go_parser.add_argument('--plannotator-command', default='plannotator', help='Command used for Plannotator-assisted human gate review')
    go_parser.add_argument('--plannotator-port', type=int, default=20000, help='Port exported to Plannotator as PLANNOTATOR_PORT')
    go_parser.add_argument('--verbose', action='store_true', help='Show raw per-step progress and execution lines')
    go_parser.add_argument('--color', choices=COLOR_MODES, default='auto', help='Color compact output: auto, always, or never')
    go_parser.add_argument('--test-strategist', action='store_true', default=False, help='Enable Test Strategist for Unit Plan draft')
    go_parser.add_argument('--test-strategist-command', default=None, help='Override Test Strategist runner command')
    go_parser.add_argument('--test-strategist-env', action='append', metavar='KEY=VALUE', dest='test_strategist_env', help='Inject env var into Test Strategist subprocess only (repeatable)')
    go_parser.add_argument('--code-simplifier', action='store_true', default=None, help='Enable CodeSimplifier for the Refiner stage')
    go_parser.add_argument('--no-code-simplifier', action='store_false', dest='code_simplifier', help='Disable CodeSimplifier for the Refiner stage')
    go_parser.add_argument('--code-simplifier-command', default=None, help='Override CodeSimplifier runner command')
    go_parser.add_argument('--code-simplifier-env', action='append', metavar='KEY=VALUE', dest='code_simplifier_env', help='Inject env var into CodeSimplifier subprocess only (repeatable)')
    return go_parser


def normalize_go_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> argparse.Namespace:
    if getattr(args, 'command', None) == 'revise':
        state_dir_explicit = getattr(args, 'state_dir', None) is not None
        args.state_dir_explicit = state_dir_explicit
        positional_target = getattr(args, 'target_arg', None)
        flag_target = getattr(args, 'target', None)
        if positional_target and flag_target and positional_target != flag_target:
            parser.error('TARGET conflicts with --target')
        target = flag_target or positional_target
        args.target = target
        workspace_arg = getattr(args, 'workspace_dir', None)
        if getattr(args, 'state_dir', None) is None:
            args.state_dir = (
                _go_state_dir_in_workspace(_go_state_dir_for_target(target), args.workspace_dir, workspace_arg is not None)
                if target
                else '.plan-ralph'
            )
        return args

    if getattr(args, 'command', None) != 'go':
        args.state_dir_explicit = True
        return args

    state_dir_explicit = getattr(args, 'state_dir', None) is not None
    args.state_dir_explicit = state_dir_explicit
    positional_target = getattr(args, 'target_arg', None)
    flag_target = getattr(args, 'target', None)
    if positional_target and flag_target and positional_target != flag_target:
        parser.error('TARGET conflicts with --target')

    target = flag_target or positional_target
    args.target = target
    workspace_arg = getattr(args, 'workspace_dir', None)
    if getattr(args, 'state_dir', None) is None:
        if target:
            args.state_dir = _go_state_dir_in_workspace(
                _go_state_dir_for_target(target),
                args.workspace_dir,
                workspace_arg is not None,
            )
        else:
            parser.error('go requires TARGET or --target when --state-dir is omitted')
    return args


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='waygate',
        description='Waygate workflow control surface',
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    init_parser = subparsers.add_parser(
        'init',
        help='Initialize a new session state directory',
        allow_abbrev=False,
    )
    init_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and artifacts/')
    init_parser.add_argument('--force', action='store_true', help='Overwrite an existing session.json')
    init_parser.add_argument('--auto-approve', action='store_true', help='Auto-generate approval artifacts during init and runtime')
    init_parser.add_argument('--workspace-dir', default=None, help='Target project workspace directory')
    init_parser.add_argument('--agent', default='claude', help='Agent command used by the real builder runtime')
    init_parser.add_argument('--runner', default=None, help='Agent runner backend: subprocess, tmux-claude, or tmux-codex')
    init_parser.add_argument('--tmux-target', default=None, help='tmux pane target for tmux-codex or tmux-claude, for example 1.2')
    init_parser.add_argument('--target', default=None, help='Target label or acceptance version to run')
    init_parser.add_argument('--spec', default=None, help='Path to a supported Waygate Markdown requirements spec')
    init_parser.add_argument('--unsafe-skip-human-gates', action='store_true', help='Bypass Markdown human gates and write an audit event')
    init_parser.add_argument('--no-agent-guides', action='store_false', dest='agent_guides', default=True, help='Do not generate AGENTS.md or documentation layout during init')
    init_parser.add_argument('--claude-md', action='store_true', default=False, help='Also generate a CLAUDE.md shim that points to AGENTS.md')
    init_parser.add_argument('--test-strategist', action='store_true', default=False, help='Enable Test Strategist for Unit Plan draft')
    init_parser.add_argument('--test-strategist-command', default=None, help='Override Test Strategist runner command')
    init_parser.add_argument('--test-strategist-env', action='append', metavar='KEY=VALUE', dest='test_strategist_env', help='Inject env var into Test Strategist subprocess only (repeatable)')
    init_parser.add_argument('--code-simplifier', action='store_true', default=None, help='Enable CodeSimplifier for the Refiner stage')
    init_parser.add_argument('--no-code-simplifier', action='store_false', dest='code_simplifier', help='Disable CodeSimplifier for the Refiner stage')
    init_parser.add_argument('--code-simplifier-command', default=None, help='Override CodeSimplifier runner command')
    init_parser.add_argument('--code-simplifier-env', action='append', metavar='KEY=VALUE', dest='code_simplifier_env', help='Inject env var into CodeSimplifier subprocess only (repeatable)')

    status_parser = subparsers.add_parser(
        'status',
        help='Show current workflow status',
        allow_abbrev=False,
    )
    status_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and artifacts/')
    status_parser.add_argument('--auto-approve', action='store_true', help='Reflect auto-approve mode in status/runtime decisions')

    approve_parser = subparsers.add_parser(
        'approve',
        help='Approve a Markdown human gate after manual review',
        allow_abbrev=False,
    )
    approve_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and approvals/')
    approve_parser.add_argument(
        '--gate',
        required=True,
        choices=['requirements', 'unit-plan', 'final-acceptance', 'bug-fix'],
        help='Markdown human gate to approve',
    )
    approve_parser.add_argument('--actor', default='human', help='Name recorded in the Human Confirmation block')

    revise_parser = subparsers.add_parser(
        'revise',
        help='Regenerate a Markdown gate from human feedback in the current draft',
        allow_abbrev=False,
    )
    revise_parser.add_argument('target_arg', nargs='?', metavar='TARGET', help='Target label used to infer .rrc-controller-<target>')
    revise_parser.add_argument('--state-dir', default=None, help='Directory containing session.json and approvals/')
    revise_parser.add_argument('--target', default=None, help='Target label used to infer .rrc-controller-<target>')
    revise_parser.add_argument('--workspace-dir', default=None, help='Target project workspace directory')
    revise_parser.add_argument(
        '--gate',
        required=True,
        choices=['requirements', 'unit-plan'],
        help='Markdown human gate to revise',
    )
    revise_parser.add_argument(
        '--reason',
        default=None,
        help='Human reason to include in a requirements change request prompt',
    )

    migrate_parser = subparsers.add_parser(
        'migrate',
        help='Migrate an existing state directory to the latest gate format',
        allow_abbrev=False,
    )
    migrate_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and approvals/')

    start_parser = subparsers.add_parser(
        'start',
        help='Initialize the workflow if needed, then continuously drive it',
        allow_abbrev=False,
    )
    start_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and artifacts/')
    start_parser.add_argument('--force', action='store_true', help='Reinitialize an existing session before driving')
    start_parser.add_argument('--dry-run', action='store_true', help='Simulate step execution by writing mock artifacts')
    start_parser.add_argument('--max-steps', type=int, default=DEFAULT_MAX_AUTOMATIC_STEPS, help='Maximum automatic steps to run before stopping')
    start_parser.add_argument('--auto-approve', action='store_true', help='Auto-generate low-risk approval artifacts during runtime')
    start_parser.add_argument('--workspace-dir', default=None, help='Target project workspace directory')
    start_parser.add_argument('--agent', default=None, help='Agent command used by the real builder runtime')
    start_parser.add_argument('--runner', default=None, help='Agent runner backend: subprocess, tmux-claude, or tmux-codex')
    start_parser.add_argument('--tmux-target', default=None, help='tmux pane target for tmux-codex or tmux-claude, for example 1.2')
    start_parser.add_argument('--target', default=None, help='Target label or acceptance version to run')
    start_parser.add_argument('--spec', default=None, help='Path to a supported Waygate Markdown requirements spec')
    start_parser.add_argument('--actor', default='human', help='Name recorded when approving a Human Confirmation gate')
    start_parser.add_argument('--unsafe-skip-human-gates', action='store_true', help='Bypass Markdown human gates and write an audit event')
    start_parser.add_argument('--no-agent-guides', action='store_false', dest='agent_guides', default=True, help='Do not generate AGENTS.md or documentation layout when start initializes state')
    start_parser.add_argument('--claude-md', action='store_true', default=False, help='Also generate a CLAUDE.md shim that points to AGENTS.md when start initializes state')
    start_parser.add_argument('--plannotator-command', default='plannotator', help='Command used for Plannotator-assisted human gate review')
    start_parser.add_argument('--plannotator-port', type=int, default=20000, help='Port exported to Plannotator as PLANNOTATOR_PORT')
    start_parser.add_argument('--verbose', action='store_true', help='Show raw per-step progress and execution lines')
    start_parser.add_argument('--color', choices=COLOR_MODES, default='auto', help='Color compact output: auto, always, or never')
    start_parser.add_argument('--test-strategist', action='store_true', default=False, help='Enable Test Strategist for Unit Plan draft')
    start_parser.add_argument('--test-strategist-command', default=None, help='Override Test Strategist runner command')
    start_parser.add_argument('--test-strategist-env', action='append', metavar='KEY=VALUE', dest='test_strategist_env', help='Inject env var into Test Strategist subprocess only (repeatable)')
    start_parser.add_argument('--code-simplifier', action='store_true', default=None, help='Enable CodeSimplifier for the Refiner stage')
    start_parser.add_argument('--no-code-simplifier', action='store_false', dest='code_simplifier', help='Disable CodeSimplifier for the Refiner stage')
    start_parser.add_argument('--code-simplifier-command', default=None, help='Override CodeSimplifier runner command')
    start_parser.add_argument('--code-simplifier-env', action='append', metavar='KEY=VALUE', dest='code_simplifier_env', help='Inject env var into CodeSimplifier subprocess only (repeatable)')

    add_go_parser(subparsers)

    drive_parser = subparsers.add_parser(
        'drive',
        help='Continuously drive the workflow and stop only at human confirmation gates',
        allow_abbrev=False,
    )
    drive_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and artifacts/')
    drive_parser.add_argument('--dry-run', action='store_true', help='Simulate step execution by writing mock artifacts')
    drive_parser.add_argument('--max-steps', type=int, default=DEFAULT_MAX_AUTOMATIC_STEPS, help='Maximum automatic steps to run before stopping')
    drive_parser.add_argument('--auto-approve', action='store_true', help='Auto-generate low-risk approval artifacts during runtime')
    drive_parser.add_argument('--workspace-dir', default=None, help='Override workspace path stored in session.json')
    drive_parser.add_argument('--agent', default=None, help='Override agent command used by the builder runtime')
    drive_parser.add_argument('--runner', default=None, help='Override agent runner backend: subprocess, tmux-claude, or tmux-codex')
    drive_parser.add_argument('--tmux-target', default=None, help='Override tmux pane target for tmux-codex or tmux-claude')
    drive_parser.add_argument('--target', default=None, help='Target label or acceptance version to run')
    drive_parser.add_argument('--actor', default='human', help='Name recorded when approving a Human Confirmation gate')
    drive_parser.add_argument('--unsafe-skip-human-gates', action='store_true', help='Bypass Markdown human gates and write an audit event')
    drive_parser.add_argument('--plannotator-command', default='plannotator', help='Command used for Plannotator-assisted human gate review')
    drive_parser.add_argument('--plannotator-port', type=int, default=20000, help='Port exported to Plannotator as PLANNOTATOR_PORT')
    drive_parser.add_argument('--verbose', action='store_true', help='Show raw per-step progress and execution lines')
    drive_parser.add_argument('--color', choices=COLOR_MODES, default='auto', help='Color compact output: auto, always, or never')

    run_parser = subparsers.add_parser(
        'run',
        help='Advance the workflow by one step or until terminal state',
        allow_abbrev=False,
    )
    run_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and artifacts/')
    run_parser.add_argument('--dry-run', action='store_true', help='Simulate step execution by writing mock artifacts')
    run_parser.add_argument('--until-done', action='store_true', help='Continue running until done/blocked/failed')
    run_parser.add_argument('--max-steps', type=int, default=DEFAULT_MAX_AUTOMATIC_STEPS, help='Maximum steps to run in --until-done mode')
    run_parser.add_argument('--auto-approve', action='store_true', help='Auto-generate approval artifacts during runtime')
    run_parser.add_argument('--workspace-dir', default=None, help='Override workspace path stored in session.json')
    run_parser.add_argument('--agent', default=None, help='Override agent command used by the builder runtime')
    run_parser.add_argument('--runner', default=None, help='Override agent runner backend: subprocess, tmux-claude, or tmux-codex')
    run_parser.add_argument('--tmux-target', default=None, help='Override tmux pane target for tmux-codex or tmux-claude')
    run_parser.add_argument('--target', default=None, help='Target label or acceptance version to run')
    run_parser.add_argument('--unsafe-skip-human-gates', action='store_true', help='Bypass Markdown human gates and write an audit event')

    return normalize_go_args(parser.parse_args(), parser)


def _build_strategist_overrides(args: argparse.Namespace) -> dict[str, Any] | None:
    enabled = getattr(args, 'test_strategist', False)
    command = getattr(args, 'test_strategist_command', None)
    raw_env = getattr(args, 'test_strategist_env', None) or []
    if not enabled and not command and not raw_env:
        return None
    overrides: dict[str, Any] = {'testStrategistEnabled': True}
    if command or raw_env:
        role_runner: dict[str, Any] = {'runner': 'subprocess'}
        if command:
            role_runner['command'] = command
        if raw_env:
            env: dict[str, str] = {}
            for pair in raw_env:
                k, _, v = pair.partition('=')
                env[k] = v
            role_runner['env'] = env
        overrides['roleRunners'] = {'test_strategist': role_runner}
    return overrides


def _build_code_simplifier_overrides(args: argparse.Namespace) -> dict[str, Any] | None:
    enabled = getattr(args, 'code_simplifier', None)
    command = getattr(args, 'code_simplifier_command', None)
    raw_env = getattr(args, 'code_simplifier_env', None) or []
    if enabled is None and not command and not raw_env:
        return None
    overrides: dict[str, Any] = {'codeSimplifierEnabled': enabled is not False}
    if command or raw_env:
        role_runner: dict[str, Any] = {'runner': 'subprocess'}
        if command:
            role_runner['command'] = command
        if raw_env:
            env: dict[str, str] = {}
            for pair in raw_env:
                k, _, v = pair.partition('=')
                env[k] = v
            role_runner['env'] = env
        overrides['roleRunners'] = {'refiner': role_runner}
    return overrides


def _build_role_overrides(args: argparse.Namespace) -> dict[str, Any] | None:
    merged: dict[str, Any] = {}
    for overrides in (_build_strategist_overrides(args), _build_code_simplifier_overrides(args)):
        if not overrides:
            continue
        for key, value in overrides.items():
            if key == 'roleRunners' and isinstance(value, dict):
                merged.setdefault('roleRunners', {}).update(value)
            else:
                merged[key] = value
    return merged or None


def render_status_line(state: dict[str, Any]) -> str:
    next_action = state.get('nextAction') or compute_next_allowed_action(state)
    project_target_version = _project_target_version(state)
    return (
        f"currentStep={state.get('currentStep')} "
        f"status={state.get('status')} "
        f"nextAction={next_action} "
        f"projectTargetVersion={project_target_version}"
    )


def main() -> None:
    args = parse_args()
    controller = RalphRefinerController(
        state_dir=Path(args.state_dir),
        dry_run=getattr(args, 'dry_run', False),
        auto_approve=getattr(args, 'auto_approve', False),
        workspace_dir=Path(args.workspace_dir) if getattr(args, 'workspace_dir', None) else None,
        agent_command=getattr(args, 'agent', None),
        agent_runner=getattr(args, 'runner', None),
        tmux_target=getattr(args, 'tmux_target', None),
        target=getattr(args, 'target', None),
        unsafe_skip_human_gates=getattr(args, 'unsafe_skip_human_gates', False),
        agent_guides_enabled=getattr(args, 'agent_guides', True),
        claude_md_enabled=getattr(args, 'claude_md', False),
        plannotator_command=getattr(args, 'plannotator_command', 'plannotator'),
        plannotator_port=getattr(args, 'plannotator_port', 20000),
        state_dir_explicit=getattr(args, 'state_dir_explicit', True),
        spec_path=getattr(args, 'spec', None),
    )

    if args.command == 'init':
        strategist_overrides = _build_role_overrides(args)
        state = controller.init_state(force=args.force, strategist_overrides=strategist_overrides)
        print(render_status_line(state))
        return

    if args.command == 'status':
        state = controller.get_status()
        print(render_status_line(state))
        return

    if args.command == 'approve':
        try:
            gate_path = controller.approve_human_gate(args.gate, actor=args.actor)
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            raise SystemExit(1) from None
        print(f'gate={args.gate} status=approved path={gate_path}')
        return

    if args.command == 'revise':
        try:
            gate_path = controller.revise_human_gate(args.gate, reason=getattr(args, 'reason', None))
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            raise SystemExit(1) from None
        print(f'gate={args.gate} status=revised path={gate_path}')
        return

    if args.command == 'migrate':
        try:
            state = controller.migrate_state()
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            raise SystemExit(1) from None
        paths = ','.join(state.get('migratedPaths') or [])
        print(f'status=migrated paths={paths}')
        return

    if args.command in {'start', 'go'}:
        try:
            controller.start(
                force=args.force,
                max_steps=args.max_steps,
                verbose=args.verbose,
                color_mode=args.color,
                actor=args.actor,
                strategist_overrides=_build_role_overrides(args),
            )
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            raise SystemExit(1) from None
        return

    if args.command == 'drive':
        try:
            controller.drive(max_steps=args.max_steps, verbose=args.verbose, color_mode=args.color, actor=args.actor)
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            raise SystemExit(1) from None
        return

    if args.command == 'run':
        try:
            state = controller.run_until_done(max_steps=args.max_steps) if args.until_done else controller.run_once()
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            raise SystemExit(1) from None
        print(render_status_line(state))
        return

    raise ValueError(f'Unknown command: {args.command}')


if __name__ == '__main__':
    main()
