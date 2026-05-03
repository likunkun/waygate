from __future__ import annotations

from pathlib import Path

import pytest

from workflow_controller.state_machine.actions import compute_next_allowed_action
from workflow_controller.state_machine.transitions import (
    first_incomplete_unit_id,
    objective_coverage_units_passed,
    reconcile_state,
    rollback_to_last_verified_step,
    unit_needs_ui_design,
    validate_objective_coverage,
)


def _make_state(**kwargs: object) -> dict:
    base: dict = {
        'currentStep': 'PLAN_APPROVED',
        'status': 'active',
        'scopeApproved': True,
        'humanGatesRequired': False,
        'units': [{'id': 'unit-1', 'passes': False}],
        'objectiveCoverage': [{'objective': 'test', 'units': ['unit-1'], 'status': 'partial'}],
        'blockedReason': None,
    }
    base.update(kwargs)
    return base


class TestComputeNextAllowedAction:
    def test_blocked_returns_none(self) -> None:
        state = _make_state(status='blocked')
        assert compute_next_allowed_action(state) is None

    def test_requirements_draft(self) -> None:
        state = _make_state(currentStep='REQUIREMENTS_DRAFT')
        assert compute_next_allowed_action(state) == 'run_requirements_drafter'

    def test_unit_plan_draft(self) -> None:
        state = _make_state(currentStep='UNIT_PLAN_DRAFT')
        assert compute_next_allowed_action(state) == 'run_unit_plan_drafter'

    def test_waiting_requirements_acceptance(self) -> None:
        state = _make_state(currentStep='WAITING_REQUIREMENTS_ACCEPTANCE')
        assert compute_next_allowed_action(state) == 'check_requirements_acceptance'

    def test_waiting_unit_plan_approval(self) -> None:
        state = _make_state(currentStep='WAITING_UNIT_PLAN_APPROVAL')
        assert compute_next_allowed_action(state) == 'check_unit_plan_approval'

    def test_waiting_final_acceptance(self) -> None:
        state = _make_state(currentStep='WAITING_FINAL_ACCEPTANCE')
        assert compute_next_allowed_action(state) == 'check_final_acceptance'

    def test_plan_created_no_scope_approval(self) -> None:
        state = _make_state(currentStep='PLAN_CREATED', scopeApproved=False)
        assert compute_next_allowed_action(state) == 'require_scope_approval'

    def test_plan_approved_runs_builder(self) -> None:
        state = _make_state(currentStep='PLAN_APPROVED')
        assert compute_next_allowed_action(state) == 'run_builder'

    def test_execute_unit_runs_builder(self) -> None:
        state = _make_state(currentStep='EXECUTE_UNIT')
        assert compute_next_allowed_action(state) == 'run_builder'

    def test_refine_unit_runs_refiner(self) -> None:
        state = _make_state(currentStep='REFINE_UNIT')
        assert compute_next_allowed_action(state) == 'run_refiner'

    def test_review_unit_runs_reviewer(self) -> None:
        state = _make_state(currentStep='REVIEW_UNIT')
        assert compute_next_allowed_action(state) == 'run_reviewer'

    def test_verify_unit_runs_verifier(self) -> None:
        state = _make_state(currentStep='VERIFY_UNIT')
        assert compute_next_allowed_action(state) == 'run_verifier'

    def test_unit_complete_completes_unit(self) -> None:
        state = _make_state(currentStep='UNIT_COMPLETE')
        assert compute_next_allowed_action(state) == 'complete_unit'

    def test_release_gate_requires_release_approval(self) -> None:
        state = _make_state(currentStep='RELEASE_GATE', scopeApproved=True)
        assert compute_next_allowed_action(state) == 'require_release_approval'

    def test_human_gates_check_requirements_when_not_accepted(self) -> None:
        state = _make_state(
            currentStep='PLAN_APPROVED',
            humanGatesRequired=True,
            requirementsAccepted=False,
        )
        assert compute_next_allowed_action(state) == 'check_requirements_acceptance'

    def test_plan_approved_with_ui_design_needed(self) -> None:
        state = _make_state(currentStep='PLAN_APPROVED', currentUnitNeedsUiDesign=True)
        assert compute_next_allowed_action(state) == 'run_ui_design'


class TestReconcileState:
    def test_preserves_active_state(self, tmp_path: Path) -> None:
        state = _make_state(currentStep='EXECUTE_UNIT')
        result = reconcile_state(state, tmp_path)
        assert result['currentStep'] == 'EXECUTE_UNIT'

    def test_resets_done_when_objectives_incomplete(self, tmp_path: Path) -> None:
        state = _make_state(
            currentStep='DONE',
            units=[{'id': 'unit-1', 'passes': False}],
            objectiveCoverage=[{'objective': 'test', 'units': ['unit-1'], 'status': 'covered'}],
        )
        result = reconcile_state(state, tmp_path)
        assert result['currentStep'] == 'RELEASE_GATE'
        assert result['status'] == 'blocked'

    def test_plan_created_advances_to_plan_approved_when_scope_approved(self, tmp_path: Path) -> None:
        state = _make_state(
            currentStep='PLAN_CREATED',
            scopeApproved=True,
            humanGatesRequired=False,
        )
        result = reconcile_state(state, tmp_path)
        assert result['currentStep'] == 'PLAN_APPROVED'

    def test_sets_test_strategist_enabled_default(self, tmp_path: Path) -> None:
        state = _make_state()
        state.pop('testStrategistEnabled', None)
        result = reconcile_state(state, tmp_path)
        assert result['testStrategistEnabled'] is False


class TestValidateObjectiveCoverage:
    def test_all_covered_and_passed(self) -> None:
        state = {
            'units': [{'id': 'unit-1', 'passes': True}],
            'objectiveCoverage': [{'objective': 'test', 'units': ['unit-1'], 'status': 'covered'}],
        }
        assert validate_objective_coverage(state) is True

    def test_partial_not_covered(self) -> None:
        state = {
            'units': [{'id': 'unit-1', 'passes': True}],
            'objectiveCoverage': [{'objective': 'test', 'units': ['unit-1'], 'status': 'partial'}],
        }
        assert validate_objective_coverage(state) is False

    def test_unit_not_passed(self) -> None:
        state = {
            'units': [{'id': 'unit-1', 'passes': False}],
            'objectiveCoverage': [{'objective': 'test', 'units': ['unit-1'], 'status': 'covered'}],
        }
        assert validate_objective_coverage(state) is False

    def test_empty_coverage(self) -> None:
        state = {'units': [], 'objectiveCoverage': []}
        assert validate_objective_coverage(state) is False


class TestFirstIncompleteUnitId:
    def test_returns_first_incomplete(self) -> None:
        state = {
            'units': [
                {'id': 'unit-1', 'passes': True},
                {'id': 'unit-2', 'passes': False},
            ]
        }
        assert first_incomplete_unit_id(state) == 'unit-2'

    def test_returns_none_when_all_pass(self) -> None:
        state = {'units': [{'id': 'unit-1', 'passes': True}]}
        assert first_incomplete_unit_id(state) is None

    def test_returns_none_when_empty(self) -> None:
        assert first_incomplete_unit_id({'units': []}) is None


class TestRollbackToLastVerifiedStep:
    def test_restores_last_verified_step(self) -> None:
        state = {
            'currentStep': 'VERIFY_UNIT',
            'lastVerifiedStep': 'EXECUTE_UNIT',
            'status': 'blocked',
            'blockedReason': 'verification failed',
        }
        result = rollback_to_last_verified_step(state)
        assert result['currentStep'] == 'EXECUTE_UNIT'
        assert result['status'] == 'active'
        assert result['blockedReason'] is None

    def test_defaults_to_execute_unit_when_no_last_verified(self) -> None:
        state = {'currentStep': 'VERIFY_UNIT', 'status': 'blocked', 'blockedReason': 'x'}
        result = rollback_to_last_verified_step(state)
        assert result['currentStep'] == 'EXECUTE_UNIT'


class TestUnitNeedsUiDesign:
    def test_returns_true_when_flag_set(self) -> None:
        assert unit_needs_ui_design({'currentUnitNeedsUiDesign': True}) is True

    def test_returns_false_when_flag_not_set(self) -> None:
        assert unit_needs_ui_design({'currentUnitNeedsUiDesign': False}) is False

    def test_returns_false_when_key_missing(self) -> None:
        assert unit_needs_ui_design({}) is False


class TestObjectiveCoverageUnitsPassed:
    def test_all_units_passed(self) -> None:
        state = {'units': [{'id': 'u1', 'passes': True}, {'id': 'u2', 'passes': True}]}
        coverage_item = {'units': ['u1', 'u2']}
        assert objective_coverage_units_passed(state, coverage_item) is True

    def test_one_unit_not_passed(self) -> None:
        state = {'units': [{'id': 'u1', 'passes': True}, {'id': 'u2', 'passes': False}]}
        coverage_item = {'units': ['u1', 'u2']}
        assert objective_coverage_units_passed(state, coverage_item) is False

    def test_empty_unit_list(self) -> None:
        state = {'units': [{'id': 'u1', 'passes': True}]}
        coverage_item = {'units': []}
        assert objective_coverage_units_passed(state, coverage_item) is False
