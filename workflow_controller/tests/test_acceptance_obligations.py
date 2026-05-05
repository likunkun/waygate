from __future__ import annotations

from pathlib import Path

import pytest

from workflow_controller.acceptance_obligations import (
    append_acceptance_obligations,
    render_acceptance_obligations_markdown,
)
from workflow_controller.gates.validators import validate_unit_plan_acceptance_obligation_coverage
from workflow_controller.gates.validators import validate_requirements_acceptance_quality
from workflow_controller.gates.validators import validate_unit_plan_design_architecture_traceability


def test_plannotator_annotations_become_distinct_acceptance_obligations() -> None:
    state: dict = {}

    append_acceptance_obligations(
        state,
        source='plannotator_feedback',
        source_ref='unit-plan:revision-1',
        feedback_text='Reviewer submitted three annotations.',
        annotations=[
            {'quote': 'Step 5', 'comment': '模型选择不清楚'},
            {'quote': 'Materials', 'comment': '15 个材料没有逐项证明'},
            {'quote': 'i18n', 'comment': '英文 locale 下仍有中文文案'},
        ],
    )

    obligations = state['acceptanceObligations']
    assert [item['id'] for item in obligations] == ['AO-001', 'AO-002', 'AO-003']
    assert [item['title'] for item in obligations] == [
        '模型选择不清楚',
        '15 个材料没有逐项证明',
        '英文 locale 下仍有中文文案',
    ]
    assert all(item['priority'] == 'must' for item in obligations)
    assert all(item['status'] == 'open' for item in obligations)
    assert obligations[0]['sourceRef'] == 'unit-plan:revision-1'
    assert 'Step 5' in obligations[0]['description']


def test_numbered_feedback_becomes_distinct_acceptance_obligations() -> None:
    state: dict = {}

    append_acceptance_obligations(
        state,
        source='human_feedback',
        source_ref='final-acceptance:rejection-1',
        feedback_text='''
1. 六步 UX 不清楚，用户不知道当前在哪一步。
2. 15 个材料没有完整覆盖。
3. i18n 不完整，按钮仍有英文。
''',
    )

    obligations = state['acceptanceObligations']
    assert [item['id'] for item in obligations] == ['AO-001', 'AO-002', 'AO-003']
    assert [item['title'] for item in obligations] == [
        '六步 UX 不清楚，用户不知道当前在哪一步。',
        '15 个材料没有完整覆盖。',
        'i18n 不完整，按钮仍有英文。',
    ]


def test_acceptance_obligation_markdown_preserves_original_items() -> None:
    state = {
        'acceptanceObligations': [
            {
                'id': 'AO-001',
                'title': '六步 UX 不清楚',
                'description': '用户不知道当前在哪一步。',
                'source': 'human_feedback',
                'sourceRef': 'final-acceptance:rejection-1',
                'priority': 'must',
                'status': 'open',
                'ownerStage': 'requirements',
                'mappedAcceptanceCriteria': [],
                'mappedUnits': [],
                'mappedTestCases': [],
                'evidence': [],
            }
        ]
    }

    markdown = render_acceptance_obligations_markdown(state)

    assert '# Acceptance Obligation Ledger' in markdown
    assert '## AO-001: 六步 UX 不清楚' in markdown
    assert '用户不知道当前在哪一步。' in markdown
    assert 'Mapped Test Cases: pending' in markdown


def test_unit_plan_approval_blocks_missing_acceptance_obligation_coverage(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Test Case Matrix\n'
        '| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AC-1 covers AO-001 | TC-1 | integration | pytest tests/test_a.py -q | AO-001 works |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
            {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
        ],
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-1',
                        'acceptance_criterion': 'AC-1',
                        'covers_obligations': ['AO-001'],
                        'layer': 'integration',
                        'command': 'pytest tests/test_a.py -q',
                        'expected': 'AO-001 works',
                    }
                ],
                'verification_commands': ['pytest tests/test_a.py -q'],
            }
        ],
    }

    with pytest.raises(ValueError, match='AO-002'):
        validate_unit_plan_acceptance_obligation_coverage(gate, state)


def test_unit_plan_approval_does_not_count_copied_ledger_as_coverage(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Acceptance Obligation Ledger\n'
        '## AO-001: 六步 UX 不清楚\n'
        '## AO-002: 15 个材料没有覆盖\n\n'
        '## Test Case Matrix\n'
        '| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AC-1 covers AO-001 | TC-1 | integration | pytest tests/test_a.py -q | AO-001 works |\n'
        'AO-002 still needs work.\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
            {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
        ],
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-1',
                        'acceptance_criterion': 'AC-1',
                        'covers_obligations': ['AO-001'],
                        'layer': 'integration',
                        'command': 'pytest tests/test_a.py -q',
                        'expected': 'AO-001 works',
                    }
                ],
                'verification_commands': ['pytest tests/test_a.py -q'],
            }
        ],
    }

    with pytest.raises(ValueError, match='AO-002'):
        validate_unit_plan_acceptance_obligation_coverage(gate, state)


def test_unit_plan_approval_passes_when_all_must_obligations_are_covered(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Test Case Matrix\n'
        '| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AC-1 covers AO-001 | TC-1 | integration | pytest tests/test_a.py -q | AO-001 works |\n'
        '| AC-2 covers AO-002 | TC-2 | e2e | pnpm playwright test material.spec.ts | AO-002 works |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
            {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
        ],
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-1',
                        'acceptance_criterion': 'AC-1',
                        'covers_obligations': ['AO-001'],
                        'layer': 'integration',
                        'command': 'pytest tests/test_a.py -q',
                        'expected': 'AO-001 works',
                    },
                    {
                        'id': 'TC-2',
                        'acceptance_criterion': 'AC-2',
                        'covers_obligations': ['AO-002'],
                        'layer': 'e2e',
                        'command': 'pnpm playwright test material.spec.ts',
                        'expected': 'AO-002 works',
                    },
                ],
                'verification_commands': [
                    'pytest tests/test_a.py -q',
                    'pnpm playwright test material.spec.ts',
                ],
            }
        ],
    }

    validate_unit_plan_acceptance_obligation_coverage(gate, state)


def test_unit_plan_test_case_matrix_with_design_columns_requires_real_test_evidence(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Test Case Matrix\n'
        '| Acceptance Criterion | Test Case | Layer | Product Design Ref | Technical Architecture Ref | Fixture | Command/Evidence | Expected Result |\n'
        '| --- | --- | --- | --- | --- | --- | --- | --- |\n'
        '| AC-1 covers AO-001 | TC-1 | integration | PD-1 | TA-1 | fixture.json |  |  |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
        ],
        'units': [{'id': 'unit-01', 'passes': False, 'verification_commands': []}],
    }

    with pytest.raises(ValueError, match='AO-001'):
        validate_unit_plan_acceptance_obligation_coverage(gate, state)

    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Test Case Matrix\n'
        '| Acceptance Criterion | Test Case | Layer | Product Design Ref | Technical Architecture Ref | Fixture | Command/Evidence | Expected Result |\n'
        '| --- | --- | --- | --- | --- | --- | --- | --- |\n'
        '| AC-1 covers AO-001 | TC-1 | integration | PD-1 | TA-1 | fixture.json | pytest tests/test_a.py -q | AO-001 works |\n',
        encoding='utf-8',
    )

    validate_unit_plan_acceptance_obligation_coverage(gate, state)


def test_requirements_approval_blocks_unmapped_must_obligation(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: integration]: 六步 UX 清楚展示。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-001 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
            {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
        ],
    }

    with pytest.raises(ValueError, match='AO-002'):
        validate_requirements_acceptance_quality(gate, state)


def test_requirements_approval_requires_verification_layer_for_each_ac(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1: 六步 UX 清楚展示。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-001 | AC-1 | covered |  | pytest tests/test_delivery.py -q |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
        ],
    }

    with pytest.raises(ValueError, match='AC-1.*verification layer'):
        validate_requirements_acceptance_quality(gate, state)


def test_requirements_approval_does_not_count_layer_words_in_ac_description(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1: Manual import behavior works with fixed data.\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-001 | AC-1 | covered |  | pytest tests/test_delivery.py -q |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '手工导入行为需明确', 'priority': 'must', 'status': 'open'},
        ],
    }

    with pytest.raises(ValueError, match='AC-1.*verification layer'):
        validate_requirements_acceptance_quality(gate, state)


def test_requirements_approval_accepts_mapped_and_explicitly_deferred_obligations(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: integration]: 六步 UX 清楚展示。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-001 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |\n'
        '| AO-002 | deferred | deferred | manual | 本版本不包含 15 个材料导入，已记录到后续范围。 |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
            {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
        ],
    }

    validate_requirements_acceptance_quality(gate, state)


def test_requirements_approval_requires_design_and_architecture_refs_for_each_ac(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: integration]: 六步 UX 清楚展示。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-001 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-1 | PD-1 |  | missing architecture |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
        ],
    }

    with pytest.raises(ValueError, match='AC-1.*design/architecture traceability'):
        validate_requirements_acceptance_quality(gate, state)


def test_requirements_approval_accepts_design_and_architecture_traceability(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: integration]: 六步 UX 清楚展示。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-001 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-1 | PD-AC1-six-step-flow | TA-AC1-state-model | runtime design and module boundary |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
        ],
    }

    validate_requirements_acceptance_quality(gate, state)


def test_unit_plan_approval_requires_test_cases_to_preserve_design_architecture_refs(tmp_path: Path) -> None:
    requirements = tmp_path / 'requirements-and-acceptance.md'
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: integration]: 六步 UX 清楚展示。\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-1 | PD-AC1-six-step-flow | TA-AC1-state-model | runtime design and module boundary |\n',
        encoding='utf-8',
    )
    unit_plan = tmp_path / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n', encoding='utf-8')
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-1',
                        'acceptance_criterion': 'AC-1',
                        'layer': 'integration',
                        'command': 'pytest tests/test_delivery.py -q',
                        'expected': 'AO-001 works',
                    }
                ],
            }
        ]
    }

    with pytest.raises(ValueError, match='AC-1.*design/architecture traceability'):
        validate_unit_plan_design_architecture_traceability(requirements, unit_plan, state)


def test_unit_plan_approval_accepts_test_case_design_architecture_refs(tmp_path: Path) -> None:
    requirements = tmp_path / 'requirements-and-acceptance.md'
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: integration]: 六步 UX 清楚展示。\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-1 | PD-AC1-six-step-flow | TA-AC1-state-model | runtime design and module boundary |\n',
        encoding='utf-8',
    )
    unit_plan = tmp_path / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n', encoding='utf-8')
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-1',
                        'acceptance_criterion': 'AC-1',
                        'product_design_refs': ['PD-AC1-six-step-flow'],
                        'technical_architecture_refs': ['TA-AC1-state-model'],
                        'layer': 'integration',
                        'command': 'pytest tests/test_delivery.py -q',
                        'expected': 'AO-001 works',
                    }
                ],
            }
        ]
    }

    validate_unit_plan_design_architecture_traceability(requirements, unit_plan, state)
