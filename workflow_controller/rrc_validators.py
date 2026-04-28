from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def reconcile_state(state: dict[str, Any], artifacts_root: Path) -> dict[str, Any]:
    """Best-effort recovery hook.

    Current behavior is intentionally conservative and minimal:
    - if the workflow somehow claims DONE while objectives are incomplete, block it
    - keep other step states intact; the step handlers themselves are responsible
      for creating their expected artifacts when that step is executed

    Expand this first when hardening the controller.
    """
    state = dict(state)
    current_step = state.get('currentStep')

    if current_step == 'DONE' and not validate_objective_coverage(state):
        state['currentStep'] = 'RELEASE_GATE'
        state['status'] = 'blocked'
        state['blockedReason'] = 'objectives not fully covered'

    if (
        current_step == 'PLAN_CREATED'
        and state.get('scopeApproved', False)
        and (not state.get('humanGatesRequired') or state.get('unitPlanAccepted', False))
    ):
        state['currentStep'] = 'PLAN_APPROVED'
        state['lastVerifiedStep'] = 'PLAN_CREATED'

    return state


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


def validate_required_artifacts(unit_dir: Path, filenames: list[str]) -> None:
    missing = [name for name in filenames if not (unit_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f'Missing required artifacts in {unit_dir}: {missing}')


def validate_review_verdict(review_path: Path) -> dict[str, Any]:
    review = _load_json(review_path)
    if 'passed' not in review:
        raise ValueError(f"Review verdict missing 'passed': {review_path}")
    return review


def validate_verification_verdict(verification_path: Path) -> dict[str, Any]:
    verification = _load_json(verification_path)
    if 'passed' not in verification:
        raise ValueError(f"Verification verdict missing 'passed': {verification_path}")
    return verification


def validate_objective_coverage(state: dict[str, Any]) -> bool:
    allowed = {'covered'}
    coverage = state.get('objectiveCoverage', [])
    return bool(coverage) and all(item.get('status') in allowed for item in coverage)


def unit_needs_ui_design(state: dict[str, Any]) -> bool:
    return bool(state.get('currentUnitNeedsUiDesign'))


def rollback_to_last_verified_step(state: dict[str, Any]) -> dict[str, Any]:
    state = dict(state)
    state['currentStep'] = state.get('lastVerifiedStep') or 'EXECUTE_UNIT'
    state['status'] = 'active'
    state['blockedReason'] = None
    return state


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))
