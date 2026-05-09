from __future__ import annotations

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
    state.setdefault('testStrategistEnabled', False)
    state.setdefault('codeSimplifierEnabled', True)
    state['units'] = [
        dict(unit)
        for unit in state.get('units', [])
        if isinstance(unit, dict)
    ]
    state['objectiveCoverage'] = [
        dict(item)
        for item in state.get('objectiveCoverage', [])
        if isinstance(item, dict)
    ]
    current_step = state.get('currentStep')

    _reopen_covered_objectives_with_incomplete_units(state)

    if (
        current_step in {'WAITING_FINAL_ACCEPTANCE', 'FINAL_ACCEPTANCE_AGENT_SYNC', 'RELEASE_GATE'}
        and not validate_objective_coverage(state)
    ):
        next_unit = first_incomplete_unit_id(state)
        if next_unit:
            state['currentUnitId'] = next_unit
            state['currentStep'] = 'EXECUTE_UNIT'
            state['status'] = 'active'
            state['blockedReason'] = None
            state['finalAcceptanceAccepted'] = False
            state.pop('finalAcceptanceAcceptedHash', None)
            state.pop('finalAcceptanceAcceptedBy', None)

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


def validate_objective_coverage(state: dict[str, Any]) -> bool:
    coverage = state.get('objectiveCoverage', [])
    return bool(coverage) and all(
        item.get('status') == 'covered' and objective_coverage_units_passed(state, item)
        for item in coverage
    )


def objective_coverage_units_passed(state: dict[str, Any], coverage_item: dict[str, Any]) -> bool:
    unit_passes = {
        str(unit.get('id')): bool(unit.get('passes'))
        for unit in state.get('units', [])
        if isinstance(unit, dict) and unit.get('id')
    }
    unit_ids = [str(unit_id) for unit_id in coverage_item.get('units', []) if str(unit_id)]
    return bool(unit_ids) and all(unit_passes.get(unit_id, False) for unit_id in unit_ids)


def first_incomplete_unit_id(state: dict[str, Any]) -> str | None:
    for unit in state.get('units', []):
        if isinstance(unit, dict) and unit.get('id') and not unit.get('passes'):
            return str(unit['id'])
    return None


def unit_needs_ui_design(state: dict[str, Any]) -> bool:
    return bool(state.get('currentUnitNeedsUiDesign'))


def rollback_to_last_verified_step(state: dict[str, Any]) -> dict[str, Any]:
    state = dict(state)
    state['currentStep'] = state.get('lastVerifiedStep') or 'EXECUTE_UNIT'
    state['status'] = 'active'
    state['blockedReason'] = None
    return state


def _reopen_covered_objectives_with_incomplete_units(state: dict[str, Any]) -> None:
    for item in state.get('objectiveCoverage', []):
        if item.get('status') == 'covered' and not objective_coverage_units_passed(state, item):
            item['status'] = 'partial'
