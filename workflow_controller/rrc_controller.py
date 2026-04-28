from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from workflow_controller.rrc_human_gates import (
    apply_unit_plan_state_patch_from_gate,
    approve_gate_file,
    check_gate_file,
    ensure_final_acceptance_gate,
    ensure_requirements_gate,
    ensure_unit_plan_gate,
    migrate_unit_plan_gate_to_state_patch,
    validate_unit_plan_test_strategy,
    validate_unit_plan_verification_environment,
)
from workflow_controller.rrc_plannotator import run_plannotator_gate_review
from workflow_controller.rrc_real_runtime import build_state_from_ralph, render_target_acceptance_prompt
from workflow_controller.rrc_state_store import StateStore
from workflow_controller.rrc_validators import (
    compute_next_allowed_action,
    reconcile_state,
    rollback_to_last_verified_step,
    validate_objective_coverage,
    validate_required_artifacts,
    validate_review_verdict,
    validate_verification_verdict,
)
from workflow_controller.rrc_steps import (
    ask_human_release_approval,
    ask_human_scope_approval,
    mark_current_unit_covered,
    prepare_builder_prompt,
    run_builder,
    run_refiner,
    run_reviewer,
    run_requirements_drafter,
    run_unit_plan_drafter,
    run_ui_design_if_needed,
    run_verifier,
    select_next_unit,
    target_acceptance_covered,
)


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
}

DEFAULT_MAX_AUTOMATIC_STEPS = 2000
DEFAULT_MAX_NO_PROGRESS_STEPS = 50
DEFAULT_SAME_FAILURE_MAX_RETRIES = 1
COLOR_MODES = ('auto', 'always', 'never')
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
    'run_unit_plan_drafter': '生成 Unit Plan',
    'check_requirements_acceptance': '检查需求与验收确认',
    'check_unit_plan_approval': '检查 Unit Plan 确认',
    'check_final_acceptance': '检查最终验收确认',
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

COMPACT_RESULT_LABELS = {
    'ok': '通过',
    'failed': '未通过',
}

COMPACT_RETRY_REASONS = {
    'review failed': '评审未通过',
    'verification failed': '验证未通过',
}

HUMAN_GATE_LABELS = {
    'requirements': '需求与验收',
    'unit-plan': 'Unit Plan',
    'final-acceptance': '最终验收',
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
        plannotator_command: str = 'plannotator',
        plannotator_port: int | None = 20000,
    ) -> None:
        self.state_dir = state_dir or Path('.plan-ralph')
        self.dry_run = dry_run
        self.auto_approve = auto_approve
        self.workspace_dir = workspace_dir
        self.agent_command = agent_command
        self.agent_runner = agent_runner
        self.tmux_target = tmux_target
        self.target = target
        self.unsafe_skip_human_gates = unsafe_skip_human_gates
        self.plannotator_command = plannotator_command
        self.plannotator_port = plannotator_port
        self.store = StateStore(
            session_path=self.state_dir / 'session.json',
            events_path=self.state_dir / 'events.jsonl',
        )
        self.approvals_dir = self.state_dir / 'approvals'
        self.artifacts_dir = self.state_dir / 'artifacts'

    def init_state(
        self,
        initial_state: dict[str, Any] | None = None,
        force: bool = False,
        from_ralph: bool = False,
    ) -> dict[str, Any]:
        self.store.ensure_layout()
        if self.store.session_path.exists() and not force:
            raise FileExistsError(
                f'Session already exists: {self.store.session_path}. Use --force to overwrite.'
            )
        if from_ralph:
            workspace_dir = self.workspace_dir or Path.cwd()
            state = build_state_from_ralph(
                workspace_dir=workspace_dir,
                agent_command=self.agent_command or 'claude',
                agent_runner=self.agent_runner or 'subprocess',
                tmux_target=self.tmux_target,
                target=self.target,
            )
            if self.target and state.get('targetMatchedPlanStep') is False:
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
        state['autoApprove'] = self.auto_approve
        self._save_state(state)
        return state

    def get_status(self) -> dict[str, Any]:
        state = self.store.load_state()
        state['autoApprove'] = self.auto_approve or state.get('autoApprove', False)
        if self.agent_command:
            state['agentCommand'] = self.agent_command
        if self.agent_runner:
            state['agentRunner'] = self.agent_runner
        if self.tmux_target:
            state['tmuxTarget'] = self.tmux_target
        state = reconcile_state(state, self.artifacts_dir)
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
            gate_path = ensure_final_acceptance_gate(state, self.approvals_dir, self.artifacts_dir)
        else:
            raise ValueError(f'Unknown human gate: {gate}')
        approve_gate_file(gate_path, actor=actor)
        self.store.append_event('human_gate_approved', {
            'task_id': state.get('task_id'),
            'gate': gate,
            'actor': actor,
            'path': str(gate_path),
        })
        return gate_path

    def revise_human_gate(self, gate: str) -> Path:
        if gate == 'requirements':
            return self._revise_requirements_gate()
        if gate == 'unit-plan':
            return self._revise_unit_plan_gate()
        raise ValueError(f'Unsupported gate revision: {gate}')

    def reject_final_acceptance_gate(self) -> Path:
        state = self.store.load_state()
        if state.get('currentStep') != 'WAITING_FINAL_ACCEPTANCE':
            raise ValueError('Final acceptance can only be rejected at WAITING_FINAL_ACCEPTANCE')

        gate_path = ensure_final_acceptance_gate(state, self.approvals_dir, self.artifacts_dir)
        state['finalAcceptanceRejectionFeedback'] = gate_path.read_text(encoding='utf-8')
        state['finalAcceptanceRejectionCount'] = int(state.get('finalAcceptanceRejectionCount') or 0) + 1
        state['finalAcceptanceAccepted'] = False
        state.pop('finalAcceptanceAcceptedHash', None)
        state.pop('finalAcceptanceAcceptedBy', None)
        state['blockedReason'] = None
        state['status'] = 'active'
        self._mark_current_unit_incomplete(state)
        state['currentStep'] = 'EXECUTE_UNIT'
        self.store.append_event('final_acceptance_rejected', {
            'task_id': state.get('task_id'),
            'path': str(gate_path),
            'revision_count': state.get('finalAcceptanceRejectionCount'),
        })
        self._save_state(state)
        return gate_path

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

    def _revise_requirements_gate(self) -> Path:
        state = self.store.load_state()
        if state.get('currentStep') not in {'WAITING_REQUIREMENTS_ACCEPTANCE', 'WAITING_UNIT_PLAN_APPROVAL'}:
            raise ValueError(
                'Requirements can only be revised before unit plan approval'
            )

        gate_path = self.approvals_dir / 'requirements-and-acceptance.md'
        if not gate_path.exists():
            raise FileNotFoundError(
                f'Requirements gate not found: {gate_path}. Run the requirements drafter first.'
            )

        state['requirementsRevisionFeedback'] = gate_path.read_text(encoding='utf-8')
        state['requirementsRevisionCount'] = int(state.get('requirementsRevisionCount') or 0) + 1
        state['requirementsAccepted'] = False
        state['unitPlanAccepted'] = False
        state.pop('requirementsAcceptedHash', None)
        state.pop('requirementsAcceptedBy', None)
        state.pop('unitPlanAcceptedHash', None)
        state.pop('unitPlanAcceptedBy', None)
        state['unitPlanDraftGenerated'] = False
        (self.approvals_dir / 'unit-plan.md').unlink(missing_ok=True)

        run_requirements_drafter(state, self.approvals_dir, self.artifacts_dir, dry_run=self.dry_run)
        validate_required_artifacts(
            self.artifacts_dir / 'requirements-draft',
            ['requirements-draft-summary.json', 'requirements-body.md'],
        )
        validate_required_artifacts(self.approvals_dir, ['requirements-and-acceptance.md'])

        state.pop('requirementsRevisionFeedback', None)
        state['requirementsDraftGenerated'] = True
        state['currentStep'] = 'WAITING_REQUIREMENTS_ACCEPTANCE'
        self.store.append_event('requirements_draft_revised', {
            'task_id': state.get('task_id'),
            'path': str(gate_path),
            'revision_count': state.get('requirementsRevisionCount'),
        })
        self._save_state(state)
        return gate_path

    def _revise_unit_plan_gate(self) -> Path:
        state = self.store.load_state()
        if state.get('currentStep') != 'WAITING_UNIT_PLAN_APPROVAL':
            raise ValueError('Unit plan can only be revised at WAITING_UNIT_PLAN_APPROVAL')

        gate_path = self.approvals_dir / 'unit-plan.md'
        if not gate_path.exists():
            raise FileNotFoundError(
                f'Unit plan gate not found: {gate_path}. Run the unit plan drafter first.'
            )

        state['unitPlanRevisionFeedback'] = gate_path.read_text(encoding='utf-8')
        state['unitPlanRevisionCount'] = int(state.get('unitPlanRevisionCount') or 0) + 1
        state['unitPlanAccepted'] = False
        state.pop('unitPlanAcceptedHash', None)
        state.pop('unitPlanAcceptedBy', None)

        run_unit_plan_drafter(state, self.approvals_dir, self.artifacts_dir, dry_run=self.dry_run)
        validate_required_artifacts(
            self.artifacts_dir / 'unit-plan-draft',
            ['unit-plan-draft-summary.json', 'unit-plan-body.md'],
        )
        validate_required_artifacts(self.approvals_dir, ['unit-plan.md'])

        state.pop('unitPlanRevisionFeedback', None)
        state['unitPlanDraftGenerated'] = True
        state['unitPlanAccepted'] = False
        state['currentStep'] = 'WAITING_UNIT_PLAN_APPROVAL'
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
        from_ralph: bool = False,
        max_steps: int = DEFAULT_MAX_AUTOMATIC_STEPS,
        verbose: bool = False,
        color_mode: str = 'auto',
        actor: str = 'human',
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print,
        timestamp_output: bool = True,
    ) -> dict[str, Any]:
        if timestamp_output:
            output_func = _timestamped_output(output_func)

        if self.store.session_path.exists():
            if force:
                output_func('[初始化] --force 已指定，重新创建 controller 状态')
                self.init_state(force=True, from_ralph=from_ralph)
            else:
                existing_state = self.store.load_state()
                self._validate_start_compatible(existing_state)
                output_func(f'[继续] 使用已有状态：{self.store.session_path}')
        else:
            output_func('[初始化] 创建新的 controller 状态')
            self.init_state(force=False, from_ralph=from_ralph)

        return self.drive(
            max_steps=max_steps,
            verbose=verbose,
            color_mode=color_mode,
            actor=actor,
            input_func=input_func,
            output_func=output_func,
            timestamp_output=False,
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
        if mismatches:
            raise ValueError(
                'Existing session does not match start arguments: '
                + '; '.join(mismatches)
                + '. Use --force to reinitialize.'
            )

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
            state['requirementsDraftGenerated'] = True
            state['currentStep'] = 'WAITING_REQUIREMENTS_ACCEPTANCE'
            self.store.append_event('requirements_draft_generated', {
                'task_id': state.get('task_id'),
                'path': str(self.approvals_dir / 'requirements-and-acceptance.md'),
            })
            self._save_state(state)
            return state

        if action == 'run_unit_plan_drafter':
            run_unit_plan_drafter(state, self.approvals_dir, self.artifacts_dir, dry_run=self.dry_run)
            validate_required_artifacts(self.artifacts_dir / 'unit-plan-draft', ['unit-plan-draft-summary.json', 'unit-plan-body.md'])
            validate_required_artifacts(self.approvals_dir, ['unit-plan.md'])
            state['unitPlanDraftGenerated'] = True
            state['unitPlanAccepted'] = False
            state['currentStep'] = 'WAITING_UNIT_PLAN_APPROVAL'
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
                state['currentStep'] = 'PLAN_CREATED'
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
                    validate_unit_plan_verification_environment(state)
                except ValueError as exc:
                    state['unitPlanAccepted'] = False
                    state['currentStep'] = 'WAITING_UNIT_PLAN_APPROVAL'
                    state['blockedReason'] = f'unit plan gate invalid: {exc}'
                    self._save_state(state)
                    return state
                state['unitPlanAcceptedHash'] = gate.content_hash
                state['unitPlanAcceptedBy'] = gate.confirmed_by
                state['blockedReason'] = None
                state['currentStep'] = 'PLAN_CREATED'
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
            gate_path = ensure_final_acceptance_gate(state, self.approvals_dir, self.artifacts_dir)
            if self._unsafe_skip_gate(state, 'final_acceptance', gate_path):
                state['finalAcceptanceAccepted'] = True
                state['currentStep'] = 'RELEASE_GATE'
                self._save_state(state)
                return state
            gate = check_gate_file(gate_path)
            state['finalAcceptanceAccepted'] = gate.approved
            if gate.approved:
                state['finalAcceptanceAcceptedHash'] = gate.content_hash
                state['finalAcceptanceAcceptedBy'] = gate.confirmed_by
                state.pop('finalAcceptanceRejectionFeedback', None)
                state['blockedReason'] = None
                state['currentStep'] = 'RELEASE_GATE'
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

        if action == 'run_builder':
            prepare_builder_prompt(state, self.approvals_dir, unit_dir)
            run_builder(state, unit_dir, dry_run=self.dry_run)
            validate_required_artifacts(unit_dir, ['builder-summary.json', 'changed-files.txt'])
            state['currentStep'] = 'REFINE_UNIT'
            self._save_state(state)
            return state

        if action == 'run_refiner':
            run_refiner(state, unit_dir, dry_run=self.dry_run)
            validate_required_artifacts(unit_dir, ['refinement-summary.json'])
            state['currentStep'] = 'REVIEW_UNIT'
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
            run_verifier(
                state,
                unit_dir,
                dry_run=self.dry_run,
                progress_callback=verification_progress_callback,
            )
            verification = validate_verification_verdict(unit_dir / 'verification.json')
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
                    ensure_final_acceptance_gate(state, self.approvals_dir, self.artifacts_dir, force=True)
                else:
                    state['currentStep'] = 'RELEASE_GATE'
            else:
                next_unit = select_next_unit(state)
                if next_unit == 'RELEASE_GATE':
                    if state.get('humanGatesRequired') and not state.get('finalAcceptanceAccepted', False):
                        state['currentStep'] = 'WAITING_FINAL_ACCEPTANCE'
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

    def _save_state(self, state: dict[str, Any]) -> None:
        next_action = compute_next_allowed_action(state)
        state['nextAllowedActions'] = [next_action] if next_action else []
        self.store.save_state(state)

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
    ) -> dict[str, Any]:
        if timestamp_output:
            output_func = _timestamped_output(output_func)

        steps = 0
        no_progress_steps = 0
        color_enabled = _color_enabled(color_mode)
        compact_reporter = None if verbose else _CompactDriveReporter(output_func, color_enabled=color_enabled)
        state = self.get_status()
        while state.get('status') not in {'done', 'blocked', 'failed'}:
            if verbose:
                self._print_drive_progress(state, output_func)
            else:
                compact_reporter.print_roadmap_if_needed(state)

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

        if state.get('status') == 'done':
            output_func(_paint('[完成] 工作流已完成。', 'green', color_enabled))
        elif state.get('status') == 'blocked':
            output_func(_paint(f"[阻塞] {state.get('blockedReason') or '工作流已阻塞'}", 'red', color_enabled))
        else:
            output_func(f"[停止] 工作流状态：{state.get('status')}。")
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
            path = ensure_final_acceptance_gate(state, self.approvals_dir, self.artifacts_dir)
            can_revise = False
            can_rework = True
        else:
            return None

        check = check_gate_file(path)
        approved_but_invalid = _approved_gate_invalid_reason(gate, state)
        if check.approved and not approved_but_invalid:
            return None
        return {
            'gate': gate,
            'path': path,
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
        output_func(f"[人工确认] {gate_info['label']}")
        output_func(f"  文件：{gate_info['path']}")
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
                try:
                    result = run_plannotator_gate_review(
                        gate=str(gate_info['gate']),
                        label=str(gate_info['label']),
                        gate_path=Path(gate_info['path']),
                        state_dir=self.state_dir,
                        command=self.plannotator_command,
                        port=self.plannotator_port,
                    )
                except Exception as exc:
                    output_func(f'[Plannotator] 启动失败：{exc}')
                    continue
                self.store.append_event('plannotator_review_requested', {
                    'gate': gate_info['gate'],
                    'path': str(gate_info['path']),
                    'command': result.command,
                    'summary_path': str(result.summary_path),
                })
                output_func('[Plannotator] 已打开辅助审阅。')
                output_func(f'  审阅记录：{result.summary_path}')
                _print_plannotator_output(result.stdout, output_func)
                if result.stderr.strip():
                    _print_plannotator_output(result.stderr, output_func)
                output_func('  完成审阅后，请回到这里输入 a 通过、r 返工或 q 退出。')
                continue
            if choice in {'a', 'approve'}:
                self.approve_human_gate(str(gate_info['gate']), actor=actor)
                output_func(f"[确认] {gate_info['label']} 已确认，继续推进。")
                return True
            if choice in {'r', 'revise'} and gate_info.get('can_revise'):
                self.revise_human_gate(str(gate_info['gate']))
                output_func(f"[修订] 已重新生成 {gate_info['label']}，请重新阅读确认。")
                return True
            if choice in {'r', 'reject', 'rework'} and gate_info.get('can_rework'):
                self.reject_final_acceptance_gate()
                output_func('[返工] 最终验收未通过，已回到 Builder。')
                return True
            if choice in {'p', 'path'}:
                output_func(f"  文件：{gate_info['path']}")
                continue
            if choice in {'q', 'quit', 'exit'}:
                output_func('[退出] 已停止在人工确认点。')
                return False
            output_func('[提示] 请输入 v / a / r / p / q。')


def _gate_reason_label(reason: str) -> str:
    return GATE_REASON_LABELS.get(reason, reason)


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
        self.attempt_number = 0
        self.stage_results: dict[str, str] = {}

    def print_roadmap_if_needed(self, state: dict[str, Any]) -> None:
        unit_id = str(state.get('currentUnitId') or '-')
        if unit_id == self.current_unit_id:
            return
        self.current_unit_id = unit_id
        self.attempt_number = 0
        self.stage_results = {}
        self.output_func(_compact_roadmap(state, color_enabled=self.color_enabled))

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
            self.stage_results['Refiner'] = 'ok'
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


def _compact_roadmap(state: dict[str, Any], *, color_enabled: bool = False) -> str:
    unit_id = str(state.get('currentUnitId') or '-')
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
    current_stage = _stage_for_state(state)
    action = state.get('nextAction') or compute_next_allowed_action(state)
    now = ACTION_LABELS.get(action, action) if action else '-'
    return (
        f"{_paint('▶', 'green', color_enabled)} {_paint(str(state.get('requestedOutcome') or '-'), 'bold', color_enabled)}\n"
        f"          {_paint('单元', 'cyan', color_enabled)}   {index}/{total}  {unit_id}\n"
        f"          {_paint('阶段', 'cyan', color_enabled)} {_stage_tokens(current_stage, color_enabled=color_enabled)}\n"
        f"          {_paint('当前', 'cyan', color_enabled)}   {_paint(str(now), 'yellow', color_enabled) if now != '-' else now}\n"
        f"          {_paint('剩余', 'cyan', color_enabled)}   {_paint(str(remaining_after), 'dim', color_enabled)} 个单元"
    )


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
    return ' '.join(
        _paint(f'[{COMPACT_STAGE_LABELS[stage]}*]', 'yellow', color_enabled) if stage == current_stage else _paint(f'[{COMPACT_STAGE_LABELS[stage]}]', 'dim', color_enabled)
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
    if gate == 'unit-plan' and reason.startswith('unit plan gate invalid:'):
        return reason
    return None


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
        if line.strip():
            output_func(f'  {line}')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Ralph Refiner Controller', allow_abbrev=False)
    subparsers = parser.add_subparsers(dest='command', required=True)

    init_parser = subparsers.add_parser(
        'init',
        help='Initialize a new session state directory',
        allow_abbrev=False,
    )
    init_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and artifacts/')
    init_parser.add_argument('--force', action='store_true', help='Overwrite an existing session.json')
    init_parser.add_argument('--auto-approve', action='store_true', help='Auto-generate approval artifacts during init and runtime')
    init_parser.add_argument('--workspace-dir', default=None, help='Workspace containing .plan-ralph/session.json')
    init_parser.add_argument('--from-ralph', action='store_true', help='Initialize controller state from an existing Ralph session')
    init_parser.add_argument('--agent', default='claude', help='Agent command used by the real builder runtime')
    init_parser.add_argument('--runner', default='subprocess', help='Agent runner backend: subprocess or tmux-claude')
    init_parser.add_argument('--tmux-target', default=None, help='tmux pane target for --runner tmux-claude, for example 1.2')
    init_parser.add_argument('--target', default=None, help='Target Ralph step id or acceptance label to run')
    init_parser.add_argument('--unsafe-skip-human-gates', action='store_true', help='Bypass Markdown human gates and write an audit event')

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
        choices=['requirements', 'unit-plan', 'final-acceptance'],
        help='Markdown human gate to approve',
    )
    approve_parser.add_argument('--actor', default='human', help='Name recorded in the Human Confirmation block')

    revise_parser = subparsers.add_parser(
        'revise',
        help='Regenerate a Markdown gate from human feedback in the current draft',
        allow_abbrev=False,
    )
    revise_parser.add_argument('--state-dir', default='.plan-ralph', help='Directory containing session.json and approvals/')
    revise_parser.add_argument(
        '--gate',
        required=True,
        choices=['requirements', 'unit-plan'],
        help='Markdown human gate to revise',
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
    start_parser.add_argument('--workspace-dir', default=None, help='Workspace containing .plan-ralph/session.json')
    start_parser.add_argument('--from-ralph', action='store_true', help='Initialize controller state from an existing Ralph session')
    start_parser.add_argument('--agent', default=None, help='Agent command used by the real builder runtime')
    start_parser.add_argument('--runner', default=None, help='Agent runner backend: subprocess or tmux-claude')
    start_parser.add_argument('--tmux-target', default=None, help='tmux pane target for --runner tmux-claude, for example 1.2')
    start_parser.add_argument('--target', default=None, help='Target Ralph step id or acceptance label to run')
    start_parser.add_argument('--actor', default='human', help='Name recorded when approving a Human Confirmation gate')
    start_parser.add_argument('--unsafe-skip-human-gates', action='store_true', help='Bypass Markdown human gates and write an audit event')
    start_parser.add_argument('--plannotator-command', default='plannotator', help='Command used for Plannotator-assisted human gate review')
    start_parser.add_argument('--plannotator-port', type=int, default=20000, help='Port exported to Plannotator as PLANNOTATOR_PORT')
    start_parser.add_argument('--verbose', action='store_true', help='Show raw per-step progress and execution lines')
    start_parser.add_argument('--color', choices=COLOR_MODES, default='auto', help='Color compact output: auto, always, or never')

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
    drive_parser.add_argument('--runner', default=None, help='Override agent runner backend: subprocess or tmux-claude')
    drive_parser.add_argument('--tmux-target', default=None, help='Override tmux pane target for --runner tmux-claude')
    drive_parser.add_argument('--target', default=None, help='Target Ralph step id or acceptance label to run')
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
    run_parser.add_argument('--runner', default=None, help='Override agent runner backend: subprocess or tmux-claude')
    run_parser.add_argument('--tmux-target', default=None, help='Override tmux pane target for --runner tmux-claude')
    run_parser.add_argument('--target', default=None, help='Target Ralph step id or acceptance label to run')
    run_parser.add_argument('--unsafe-skip-human-gates', action='store_true', help='Bypass Markdown human gates and write an audit event')

    return parser.parse_args()


def render_status_line(state: dict[str, Any]) -> str:
    next_action = state.get('nextAction') or compute_next_allowed_action(state)
    return (
        f"currentStep={state.get('currentStep')} "
        f"status={state.get('status')} "
        f"nextAction={next_action}"
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
        plannotator_command=getattr(args, 'plannotator_command', 'plannotator'),
        plannotator_port=getattr(args, 'plannotator_port', 20000),
    )

    if args.command == 'init':
        state = controller.init_state(force=args.force, from_ralph=args.from_ralph)
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
            gate_path = controller.revise_human_gate(args.gate)
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

    if args.command == 'start':
        try:
            controller.start(
                force=args.force,
                from_ralph=args.from_ralph,
                max_steps=args.max_steps,
                verbose=args.verbose,
                color_mode=args.color,
                actor=args.actor,
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
