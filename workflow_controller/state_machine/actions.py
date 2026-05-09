from __future__ import annotations

from typing import Any

from workflow_controller.state_machine.transitions import unit_needs_ui_design


def compute_next_allowed_action(state: dict[str, Any]) -> str | None:
    if state.get('status') == 'blocked':
        return None

    step = state.get('currentStep')
    scope_approved = state.get('scopeApproved', False)
    human_gates_required = bool(state.get('humanGatesRequired'))

    if step == 'REQUIREMENTS_DRAFT':
        return 'run_requirements_drafter'
    if step == 'UNIT_PLAN_DRAFT':
        return 'run_unit_plan_drafter'
    if step == 'WAITING_REQUIREMENTS_ACCEPTANCE':
        return 'check_requirements_acceptance'
    if step == 'WAITING_UNIT_PLAN_APPROVAL':
        return 'check_unit_plan_approval'
    if step == 'WAITING_FINAL_ACCEPTANCE':
        return 'check_final_acceptance'
    if step == 'FINAL_ACCEPTANCE_AGENT_SYNC':
        return 'sync_final_acceptance_agent'
    if step == 'WAITING_BUG_FIX_GATE':
        return 'check_bug_fix_gate'
    if step == 'BUG_FIX':
        return 'run_bug_fix'
    if step == 'BUG_FIX_VERIFY':
        return 'run_bug_fix_verifier'

    if human_gates_required and not state.get('requirementsAccepted', False):
        return 'check_requirements_acceptance'
    if human_gates_required and step == 'PLAN_CREATED' and not state.get('unitPlanAccepted', False):
        return 'check_unit_plan_approval'
    if human_gates_required and step == 'RELEASE_GATE' and not state.get('finalAcceptanceAccepted', False):
        return 'check_final_acceptance'

    if step == 'PLAN_CREATED' and not scope_approved:
        return 'require_scope_approval'
    if step == 'PLAN_APPROVED' and unit_needs_ui_design(state):
        return 'run_ui_design'
    if step in {'PLAN_APPROVED', 'UI_DESIGN_DONE', 'EXECUTE_UNIT'}:
        return 'run_builder'
    if step == 'REFINE_UNIT':
        return 'run_refiner'
    if step == 'REVIEW_UNIT':
        return 'run_reviewer'
    if step == 'VERIFY_UNIT':
        return 'run_verifier'
    if step == 'UNIT_COMPLETE':
        return 'complete_unit'
    if step == 'RELEASE_GATE':
        return 'require_release_approval'
    return None
