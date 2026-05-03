from __future__ import annotations

from pathlib import Path

import pytest

from workflow_controller.acceptance_obligations import (
    append_acceptance_obligations,
    render_acceptance_obligations_markdown,
)
from workflow_controller.gates.validators import validate_unit_plan_acceptance_obligation_coverage


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
