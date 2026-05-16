from __future__ import annotations

import json
from pathlib import Path

import pytest

from workflow_controller.acceptance_obligations import (
    append_acceptance_obligations,
    render_acceptance_obligations_markdown,
)
from workflow_controller.gates.validators import validate_unit_plan_acceptance_obligation_coverage
from workflow_controller.gates.validators import validate_requirements_acceptance_quality
from workflow_controller.gates.validators import validate_unit_plan_design_architecture_traceability
from workflow_controller.gates.validators import validate_unit_plan_prototype_conformance
from workflow_controller.prototype_review import validate_final_prototype_conformance


def _write_prototype_manifest_for_gate(
    gate: Path,
    *,
    prototype_type: str = 'html',
    ac: str = 'AC-10',
    url: str = 'http://localhost:4173/prototype',
) -> Path:
    state_root = gate.parent.parent if gate.parent.name == 'approvals' else gate.parent
    draft_dir = state_root / 'artifacts' / 'requirements-draft'
    draft_dir.mkdir(parents=True, exist_ok=True)
    prototype_entry = {
        'id': 'requirements-prototype',
        'type': prototype_type,
        'title': 'Requirements prototype',
        'linked_acceptance_criteria': [ac],
        'linked_journeys': ['J-01'],
        'page_states': ['Dashboard', 'Preview'],
        'click_path': ['Open dashboard', 'Click preview'],
        'implementation_targets': [
            {'kind': 'route', 'path': '/dashboard/preview'},
        ],
        'review_guidance': 'Review the mapped prototype before approving Requirements.',
    }
    if prototype_type == 'url':
        prototype_entry['url'] = url
    else:
        extension = 'html' if prototype_type == 'html' else 'png'
        prototype_path = draft_dir / f'requirements-prototype.{extension}'
        if prototype_type == 'html':
            prototype_path.write_text('<button>Preview</button>\n', encoding='utf-8')
        else:
            prototype_path.write_bytes(b'\x89PNG\r\n\x1a\n')
        prototype_entry['path'] = str(prototype_path)
    manifest_path = draft_dir / 'prototype-manifest.json'
    manifest_path.write_text(
        json.dumps(
            {
                'prototypes': [prototype_entry]
            }
        ),
        encoding='utf-8',
    )
    return manifest_path


def _write_surface_prototype_manifest_for_gate(gate: Path) -> Path:
    state_root = gate.parent.parent if gate.parent.name == 'approvals' else gate.parent
    draft_dir = state_root / 'artifacts' / 'requirements-draft'
    draft_dir.mkdir(parents=True, exist_ok=True)
    prototype_path = draft_dir / 'course-ops.html'
    prototype_path.write_text('<button>发布对象</button><button>分配管理</button>\n', encoding='utf-8')
    manifest_path = draft_dir / 'prototype-manifest.json'
    manifest_path.write_text(
        json.dumps(
            {
                'prototypes': [
                    {
                        'id': 'v291-course-ops-prototype-contract',
                        'type': 'html',
                        'path': str(prototype_path),
                        'title': 'Course ops prototype',
                        'linked_acceptance_criteria': ['AC-21'],
                        'linked_journeys': ['J-01'],
                        'page_states': ['Teacher dashboard'],
                        'click_path': ['Open dashboard'],
                        'implementation_targets': [{'kind': 'route', 'path': '/dashboard/teacher'}],
                        'surface_contracts': [
                            {
                                'id': 'publish-target-dialog',
                                'title': 'Publish target dialog',
                                'kind': 'dialog',
                                'page_states': ['Teacher dashboard', 'Publish target dialog'],
                                'click_path': ['Open dashboard', 'Click 发布对象'],
                                'entrypoints': ['CourseCard -> 发布对象'],
                                'implementation_targets': [
                                    {'kind': 'component', 'path': 'OpenMAIC/components/course/PublishTargetDialog.tsx'}
                                ],
                                'linked_acceptance_criteria': ['AC-21'],
                                'required': True,
                            },
                            {
                                'id': 'assignment-management-dialog',
                                'title': 'Assignment management dialog',
                                'kind': 'dialog',
                                'page_states': ['Teacher dashboard', 'Assign management dialog'],
                                'click_path': ['Open dashboard', 'Click 分配管理'],
                                'entrypoints': ['CourseCard -> 分配管理'],
                                'implementation_targets': [
                                    {'kind': 'component', 'path': 'OpenMAIC/components/course/AssignManageDialog.tsx'}
                                ],
                                'linked_acceptance_criteria': ['AC-21'],
                                'required': True,
                            },
                        ],
                    }
                ]
            }
        ),
        encoding='utf-8',
    )
    return manifest_path


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


def test_plannotator_plain_file_feedback_becomes_distinct_acceptance_obligations() -> None:
    state: dict = {}

    append_acceptance_obligations(
        state,
        source='requirements_feedback',
        source_ref='requirements:revision-1',
        feedback_text='''
# File Feedback
I've reviewed this file and have 2 pieces of feedback:

## 1. General feedback about the file
> 这个需求就是瞎扯淡

## 2. General feedback about the file
> 这才是我要的需求：
> - 默认只展示 changed / added / removed。
> - 增加一个轻量开关：显示相同项，默认关闭。
''',
    )

    obligations = state['acceptanceObligations']
    assert [item['id'] for item in obligations] == ['AO-001', 'AO-002']
    assert [item['title'] for item in obligations] == [
        '这个需求就是瞎扯淡',
        '这才是我要的需求：',
    ]
    assert '默认只展示 changed / added / removed。' in obligations[1]['description']


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


def test_unit_plan_approval_accepts_non_padded_ao_ids(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Test Case Matrix\n'
        '| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AC-1 covers AO-01 | TC-1 | integration | pytest tests/test_a.py -q | AO-01 works |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
        ],
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-1',
                        'acceptance_criterion': 'AC-1',
                        'covers_obligations': ['AO-01'],
                        'layer': 'integration',
                        'command': 'pytest tests/test_a.py -q',
                        'expected': 'AO-01 works',
                    }
                ],
                'verification_commands': ['pytest tests/test_a.py -q'],
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


def test_requirements_approval_accepts_non_padded_ao_ids(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: integration]: 六步 UX 清楚展示。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-01 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
        ],
    }

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


def test_requirements_approval_accepts_out_of_scope_with_blank_ac_and_reason(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: manual]: 当前目标不修改旧 stream handler。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-069 |  | out_of_scope | manual | `sdk/api/handlers` 属于旧 stream 目标。 |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {
                'id': 'AO-069',
                'title': '`sdk/api/handlers` 属于旧 stream 目标。',
                'priority': 'must',
                'status': 'open',
            },
        ],
    }

    validate_requirements_acceptance_quality(gate, state)


def test_v0_6_0_uiux_project_requires_prototype_before_requirements_human_confirmation(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 1. 需求\n'
        '目标项目需要 UI/UX 设计，但尚未提供原型证据。\n\n'
        '## 3. 验收标准\n'
        '- AC-10 [verification: functional]: UI/UX 项目必须在人工确认前提供 prototype 证据。\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-10 | PD-INFRA-10 | TA-UIDESIGN-01, TA-PREFLIGHT-01 | UI 原型预检。 |\n',
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='UI/UX.*prototype'):
        validate_requirements_acceptance_quality(gate, {'currentUnitNeedsUiDesign': True})

    gate.write_text(
        gate.read_text(encoding='utf-8')
        + '\n## 7. 产品设计概要\n'
        + '- Prototype Evidence: `docs/product/prototype.md` 记录页面、状态和 AC 映射。\n',
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='valid prototype manifest'):
        validate_requirements_acceptance_quality(gate, {'currentUnitNeedsUiDesign': True})

    _write_prototype_manifest_for_gate(gate, prototype_type='url', ac='AC-10')
    validate_requirements_acceptance_quality(gate, {'currentUnitNeedsUiDesign': True})


def test_v0_6_0_web_system_requires_clickable_webpage_prototype(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    base = (
        '# 需求与验收确认\n\n'
        '## 1. 需求\n'
        '目标项目是 Web 系统，需要浏览器可见体验。\n\n'
        '## 3. 验收标准\n'
        '- AC-11 [verification: functional]: Web 系统必须提供可点击网页原型。\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-11 | PD-INFRA-11 | TA-WEBPROTO-01, TA-PREFLIGHT-01 | Web 原型预检。 |\n'
    )
    gate.write_text(
        base
        + '\n## 7. 产品设计概要\n'
        + '- Prototype Evidence: 静态截图 `prototype.png` 和文字说明。\n',
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='clickable webpage prototype'):
        validate_requirements_acceptance_quality(gate, {'currentUnitIsWebSystem': True})

    gate.write_text(
        base
        + '\n## 7. 产品设计概要\n'
        + '- Web Prototype Evidence: clickable webpage prototype at `http://localhost:4173/prototype`; '
        + 'start command `python -m http.server 4173`; pages `Dashboard`, `Settings`, `Preview`; '
        + 'click path `Dashboard -> Settings -> Preview`; maps to AC-11.\n',
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='valid prototype manifest'):
        validate_requirements_acceptance_quality(gate, {'currentUnitIsWebSystem': True})

    _write_prototype_manifest_for_gate(gate, prototype_type='html', ac='AC-11')
    validate_requirements_acceptance_quality(gate, {'currentUnitIsWebSystem': True})


def test_v0_6_0_web_prototype_manual_evidence_maps_to_ac(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 1. 需求\n'
        '目标项目是 Web 系统。\n\n'
        '## 3. 验收标准\n'
        '- AC-12 [verification: manual]: Web 系统网页原型必须记录人工点击证据。\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-12 | PD-INFRA-12 | TA-WEBPROTO-02 | 人工点击证据。 |\n\n'
        '## 7. 产品设计概要\n'
        '- Web Prototype Evidence: clickable webpage prototype at `http://localhost:4173/prototype`; '
        + 'start command `python -m http.server 4173`; pages `Dashboard`, `Settings`, `Preview`; '
        + 'click path `Dashboard -> Settings -> Preview`; maps to AC-12.\n'
        '- Manual Click Evidence: reviewer opened `http://localhost:4173/prototype`, '
        + 'clicked `Dashboard -> Settings -> Preview`, observed page states `Dashboard`, `Settings`, `Preview`, '
        + 'and mapped evidence to AC-12.\n',
        encoding='utf-8',
    )

    _write_prototype_manifest_for_gate(gate, prototype_type='html', ac='AC-12')
    validate_requirements_acceptance_quality(gate, {'currentUnitIsWebSystem': True})


def test_v0_6_0_policy_gate_does_not_require_its_own_web_prototype(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 1. 需求\n'
        'V0.6.0 让 Waygate 在处理目标项目时梳理基础设施信息。\n'
        '当目标项目是 Web 系统时，Requirements Gate 必须要求网页原型。\n\n'
        '## 3. 验收标准\n'
        '- AC-10 [verification: functional]: 当目标项目需要 UI/UX 时，Requirements Gate 要求 prototype evidence。\n'
        '- AC-11 [verification: functional]: 当目标项目是 Web 系统时，Requirements Gate 要求 clickable webpage prototype。\n'
        '- AC-12 [verification: manual]: Web 系统网页原型人工证据记录访问方式和 AC 映射。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-004 | AC-10, AC-11, AC-12 | covered | functional | Web/UI policy coverage. |\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-10 | PD-INFRA-10 | TA-UIDESIGN-01, TA-PREFLIGHT-01 | UI/UX 原型预检。 |\n'
        '| AC-11 | PD-INFRA-11 | TA-WEBPROTO-01, TA-PREFLIGHT-01 | Web 原型预检。 |\n'
        '| AC-12 | PD-INFRA-12 | TA-WEBPROTO-02 | 人工点击证据。 |\n',
        encoding='utf-8',
    )

    validate_requirements_acceptance_quality(
        gate,
        {
            'requestedOutcome': 'V0.6.0',
            'currentUnitId': 'v0-6-0-u1-infrastructure-intake-gate',
            'currentUnitNeedsUiDesign': False,
        },
    )


def test_requirements_text_prototype_contract_requires_manifest_even_without_state_flags(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 1. 需求\n'
        '教师工作台必须以 clickable webpage prototype 作为 UI contract，落到真实 route `/dashboard/teacher`。\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: `/dashboard/teacher` 的信息架构、主操作和关键交互必须符合原型合约。\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-21 | PD-TEACHER-01 | TA-ROUTE-01 | 原型合约映射到真实 route。 |\n',
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='valid prototype manifest'):
        validate_requirements_acceptance_quality(gate, {})


def test_unit_plan_rejects_static_prototype_only_conformance_test(tmp_path: Path) -> None:
    requirements = tmp_path / 'requirements-and-acceptance.md'
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 教师工作台必须符合原型合约。\n',
        encoding='utf-8',
    )
    _write_prototype_manifest_for_gate(requirements, ac='AC-21')
    unit_plan = tmp_path / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n\n## Test Case Matrix\n', encoding='utf-8')
    state = {
        'currentUnitId': 'unit-01',
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-STATIC',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'fixture': 'static prototype artifact',
                        'command': 'npx playwright test artifacts/requirements-draft/prototypes/requirements-prototype.spec.ts',
                        'expected': 'prototype opens and matches screenshot',
                        'prototype_conformance': ['requirements-prototype'],
                        'production_targets': ['/dashboard/preview'],
                    }
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match='production UI conformance'):
        validate_unit_plan_prototype_conformance(requirements, unit_plan, state)


def test_unit_plan_accepts_real_route_prototype_conformance_test(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 教师工作台必须符合原型合约。\n',
        encoding='utf-8',
    )
    _write_prototype_manifest_for_gate(requirements, ac='AC-21')
    unit_plan = tmp_path / 'approvals' / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n\n## Test Case Matrix\n', encoding='utf-8')
    state = {
        'currentUnitId': 'unit-01',
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-REAL-ROUTE',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'fixture': 'teacher with one active course and one pending review',
                        'command': 'npx playwright test tests/e2e/teacher-dashboard.spec.ts --project=chromium',
                        'expected': 'route /dashboard/preview shows Dashboard and Preview states, preserves the primary action order, and opens the preview panel after clicking Preview',
                        'prototype_conformance': ['requirements-prototype'],
                        'production_targets': ['/dashboard/preview'],
                    }
                ],
            }
        ],
    }

    validate_unit_plan_prototype_conformance(requirements, unit_plan, state)


def test_unit_plan_requires_each_surface_target_not_adjacent_dialog(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 课程运营原型中的每个弹窗 surface 必须落到真实入口。\n',
        encoding='utf-8',
    )
    _write_surface_prototype_manifest_for_gate(requirements)
    unit_plan = tmp_path / 'approvals' / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n\n## Test Case Matrix\n', encoding='utf-8')
    state = {
        'currentUnitId': 'unit-01',
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-PUBLISH-DIALOG',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'fixture': 'teacher dashboard with a published course',
                        'command': 'npx playwright test tests/e2e/publish-target-dialog.spec.ts --project=chromium',
                        'expected': 'CourseCard opens the PublishTargetDialog and shows the selected class count',
                        'prototype_conformance': ['v291-course-ops-prototype-contract'],
                        'prototype_surfaces': ['publish-target-dialog'],
                        'production_targets': ['component:OpenMAIC/components/course/PublishTargetDialog.tsx'],
                        'user_steps': ['Open /dashboard/teacher', 'Click CourseCard 发布对象'],
                    }
                ],
            }
        ],
    }

    with pytest.raises(
        ValueError,
        match='prototype v291-course-ops-prototype-contract surface assignment-management-dialog target component:OpenMAIC/components/course/AssignManageDialog.tsx missing production UI conformance test',
    ):
        validate_unit_plan_prototype_conformance(requirements, unit_plan, state)


def test_unit_plan_accepts_required_surface_target_with_real_entrypoint_steps(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 课程运营原型中的每个弹窗 surface 必须落到真实入口。\n',
        encoding='utf-8',
    )
    _write_surface_prototype_manifest_for_gate(requirements)
    unit_plan = tmp_path / 'approvals' / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n\n## Test Case Matrix\n', encoding='utf-8')
    state = {
        'currentUnitId': 'unit-01',
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-PUBLISH-DIALOG',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'fixture': 'teacher dashboard with a published course',
                        'command': 'npx playwright test tests/e2e/course-dialogs.spec.ts --project=chromium',
                        'expected': 'CourseCard opens PublishTargetDialog and shows selected class count',
                        'prototype_conformance': ['v291-course-ops-prototype-contract'],
                        'prototype_surfaces': ['publish-target-dialog'],
                        'production_targets': ['component:OpenMAIC/components/course/PublishTargetDialog.tsx'],
                        'user_steps': ['Open /dashboard/teacher', 'Click CourseCard 发布对象'],
                    },
                    {
                        'id': 'TC-PROTO-ASSIGN-MANAGE-DIALOG',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'fixture': 'teacher dashboard with one assignable course and two students',
                        'command': 'npx playwright test tests/e2e/course-dialogs.spec.ts --project=chromium',
                        'expected': 'CourseCard opens AssignManageDialog, lists two students, toggles one assignment, and shows saved count 1',
                        'prototype_conformance': ['v291-course-ops-prototype-contract'],
                        'prototype_surfaces': ['assignment-management-dialog'],
                        'production_targets': ['component:OpenMAIC/components/course/AssignManageDialog.tsx'],
                        'user_steps': ['Open /dashboard/teacher', 'Click CourseCard 分配管理'],
                    },
                ],
            }
        ],
    }

    validate_unit_plan_prototype_conformance(requirements, unit_plan, state)


def test_final_acceptance_blocks_missing_surface_evidence(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 课程运营原型中的每个弹窗 surface 必须落到真实入口。\n',
        encoding='utf-8',
    )
    _write_surface_prototype_manifest_for_gate(requirements)
    artifacts_dir = tmp_path / 'artifacts'
    unit_dir = artifacts_dir / 'unit-01'
    unit_dir.mkdir(parents=True)
    (unit_dir / 'verification.json').write_text(
        json.dumps(
            {
                'evidence_rows': [
                    {
                        'test_case_id': 'TC-PROTO-PUBLISH-DIALOG',
                        'status': 'passed',
                        'command': 'npx playwright test tests/e2e/course-dialogs.spec.ts --project=chromium',
                    }
                ]
            }
        ),
        encoding='utf-8',
    )
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': True,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-PUBLISH-DIALOG',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'command': 'npx playwright test tests/e2e/course-dialogs.spec.ts --project=chromium',
                        'expected': 'CourseCard opens PublishTargetDialog and shows selected class count',
                        'prototype_conformance': ['v291-course-ops-prototype-contract'],
                        'prototype_surfaces': ['publish-target-dialog'],
                        'production_targets': ['component:OpenMAIC/components/course/PublishTargetDialog.tsx'],
                    },
                    {
                        'id': 'TC-PROTO-ASSIGN-MANAGE-DIALOG',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'command': 'npx playwright test tests/e2e/course-dialogs.spec.ts --project=chromium',
                        'expected': 'CourseCard opens AssignManageDialog and saves assignment count 1',
                        'prototype_conformance': ['v291-course-ops-prototype-contract'],
                        'prototype_surfaces': ['assignment-management-dialog'],
                        'production_targets': ['component:OpenMAIC/components/course/AssignManageDialog.tsx'],
                    },
                ],
            }
        ],
    }

    with pytest.raises(
        ValueError,
        match='surface assignment-management-dialog target component:OpenMAIC/components/course/AssignManageDialog.tsx via TC-PROTO-ASSIGN-MANAGE-DIALOG: missing',
    ):
        validate_final_prototype_conformance(
            state=state,
            artifacts_dir=artifacts_dir,
            requirements_path=requirements,
        )


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


def test_unit_plan_approval_accepts_markdown_heading_trace_refs_from_requirements(tmp_path: Path) -> None:
    requirements = tmp_path / 'requirements-and-acceptance.md'
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: functional]: 上游 HTTP 错误分类。\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| `AC-1` | `## 7. 产品设计概要` / `PDR-01 失败诊断卡片` | '
        '`## 8. 架构概要` / `TAR-01 诊断分类器模块边界`、`TAR-02 日志输入到诊断输出数据流` | '
        '覆盖上游 HTTP 错误诊断。 |\n',
        encoding='utf-8',
    )
    unit_plan = tmp_path / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n', encoding='utf-8')
    state = {
        'units': [
            {
                'id': 'unit-v1-5-failure-diagnosis',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-FD-001',
                        'acceptance_criterion': 'AC-1',
                        'product_design_refs': ['## 7. 产品设计概要 / PDR-01 失败诊断卡片'],
                        'technical_architecture_refs': [
                            '## 8. 架构概要 / TAR-01 诊断分类器模块边界',
                            '## 8. 架构概要 / TAR-02 日志输入到诊断输出数据流',
                        ],
                        'layer': 'functional',
                        'command': 'go test ./internal/usagereport/requestlog -run TestDiagnoseFailureClassifiesFixtures -count=1',
                        'expected': 'diagnosis.code=upstream_http_error',
                    }
                ],
            }
        ]
    }

    validate_unit_plan_design_architecture_traceability(requirements, unit_plan, state)
