"""Tests for gates/ three-layer structure (AC-02)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from workflow_controller.gates.parsers import (
    GateCheck,
    approve_gate_file,
    check_gate_file,
    extract_unit_plan_state_patch,
    gate_body,
    hash_gate_body,
    write_gate_file,
)
from workflow_controller.gates.generators import (
    ensure_requirements_gate,
    ensure_unit_plan_gate,
    normalize_final_acceptance_rejection_routing,
    render_requirements_gate_body,
    render_unit_plan_gate_body,
)
from workflow_controller.gates.validators import (
    apply_unit_plan_state_patch,
    validate_required_artifacts,
    validate_unit_plan_test_case_coverage,
    validate_unit_plan_test_strategy,
    validate_unit_plan_verification_environment,
)


def _minimal_state() -> dict:
    return {
        'requestedOutcome': 'test',
        'feasibleOutcome': 'test',
        'currentUnitId': 'u1',
        'objectiveCoverage': [{'objective': 'obj', 'units': ['u1'], 'status': 'partial'}],
        'units': [
            {
                'id': 'u1',
                'name': 'Unit 1',
                'passes': False,
                'scope': ['Do something'],
                'non_goals': [],
                'done_when': ['It is done'],
                'workflow_validation_level': 'fragment',
                'verification_commands': ['python -m pytest tests/ -q'],
                'test_cases': [
                    {
                        'id': 'TC-1',
                        'acceptance_criterion': 'AC-1',
                        'layer': 'unit',
                        'command': 'python -m pytest tests/ -q',
                        'expected': 'all pass',
                    }
                ],
            }
        ],
    }


class TestParsersLayer:
    def test_gate_body_strips_confirmation(self, tmp_path: Path) -> None:
        gate = tmp_path / 'test.md'
        write_gate_file(gate, '# Body\ncontent')
        content = gate.read_text()
        body = gate_body(content)
        assert '## Human Confirmation' not in body
        assert 'content' in body

    def test_hash_gate_body_stable(self) -> None:
        h1 = hash_gate_body('# Test\ncontent\n')
        h2 = hash_gate_body('# Test\ncontent\n')
        assert h1 == h2
        assert len(h1) == 64

    def test_check_gate_file_missing(self, tmp_path: Path) -> None:
        result = check_gate_file(tmp_path / 'nonexistent.md')
        assert not result.approved
        assert result.reason == 'missing'

    def test_write_and_check_pending(self, tmp_path: Path) -> None:
        gate = tmp_path / 'gate.md'
        write_gate_file(gate, '# Test')
        result = check_gate_file(gate)
        assert not result.approved
        assert result.reason == 'not_approved'

    def test_write_approve_check(self, tmp_path: Path) -> None:
        gate = tmp_path / 'gate.md'
        write_gate_file(gate, '# Test')
        approve_gate_file(gate)
        result = check_gate_file(gate)
        assert result.approved

    def test_extract_unit_plan_state_patch(self) -> None:
        patch_data = {'currentUnitId': 'u1', 'objectiveCoverage': [], 'units': []}
        content = (
            '# Unit Plan\n\n## Controller State Patch\n\n'
            f'```json\n{json.dumps(patch_data)}\n```\n\n'
            '## Human Confirmation\n\nStatus: pending\n'
        )
        patch = extract_unit_plan_state_patch(content)
        assert patch['currentUnitId'] == 'u1'

    def test_gate_check_dataclass(self) -> None:
        gc = GateCheck(approved=True, content_hash='abc', confirmed_by='human')
        assert gc.approved
        assert gc.content_hash == 'abc'


class TestGeneratorsLayer:
    def test_render_requirements_gate_body(self) -> None:
        body = render_requirements_gate_body(_minimal_state())
        assert '# 需求与验收确认' in body
        assert 'It is done' in body

    def test_render_unit_plan_gate_body(self) -> None:
        body = render_unit_plan_gate_body(_minimal_state())
        assert '# 单元计划确认' in body
        assert 'Controller State Patch' in body

    def test_ensure_requirements_gate_creates_file(self, tmp_path: Path) -> None:
        path = ensure_requirements_gate(_minimal_state(), tmp_path)
        assert path.exists()
        assert path.name == 'requirements-and-acceptance.md'

    def test_ensure_unit_plan_gate_creates_file(self, tmp_path: Path) -> None:
        path = ensure_unit_plan_gate(_minimal_state(), tmp_path)
        assert path.exists()
        assert path.name == 'unit-plan.md'

    def test_normalize_final_acceptance_rejection_routing_adds_routing(self) -> None:
        body = '# Final\n\nsome content\n'
        normalized = normalize_final_acceptance_rejection_routing(body)
        assert '返工路由' in normalized


class TestValidatorsLayer:
    def test_validate_required_artifacts_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match='Missing required artifacts'):
            validate_required_artifacts(tmp_path, ['needed.json'])

    def test_validate_required_artifacts_present(self, tmp_path: Path) -> None:
        (tmp_path / 'needed.json').write_text('{}')
        validate_required_artifacts(tmp_path, ['needed.json'])  # should not raise

    def test_apply_unit_plan_state_patch_basic(self) -> None:
        state = _minimal_state()
        patch = {
            'currentUnitId': 'u1',
            'objectiveCoverage': [{'objective': 'obj', 'units': ['u1'], 'status': 'partial'}],
            'units': [{'id': 'u1', 'name': 'Unit 1', 'passes': False, 'verification_commands': []}],
        }
        new_state = apply_unit_plan_state_patch(state, patch)
        assert new_state['currentUnitId'] == 'u1'

    def test_validate_unit_plan_test_case_coverage_no_cases(self, tmp_path: Path) -> None:
        state = {
            'units': [
                {
                    'id': 'u1',
                    'passes': False,
                    'verification_commands': [],
                    'test_cases': [],
                }
            ]
        }
        gate = tmp_path / 'unit-plan.md'
        write_gate_file(gate, '# Unit Plan\n\nsome content')
        validate_unit_plan_test_case_coverage(gate, state)  # no commands → no gap

    def test_validate_unit_plan_verification_environment_clean(self) -> None:
        state = {
            'units': [
                {
                    'id': 'u1',
                    'verification_commands': ['python -m pytest tests/ -q'],
                    'verification_env': {},
                }
            ]
        }
        validate_unit_plan_verification_environment(state)  # no DATABASE_URL needed

    def test_validate_unit_plan_test_strategy_no_requirements(self, tmp_path: Path) -> None:
        state = _minimal_state()
        requirements = tmp_path / 'req.md'
        unit_plan = tmp_path / 'up.md'
        write_gate_file(unit_plan, '# Unit Plan')
        # no requirements file → should not raise
        validate_unit_plan_test_strategy(requirements, unit_plan, state)
