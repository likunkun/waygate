from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import workflow_controller.rrc_controller as rrc_controller_module
from workflow_controller.requirements_package import (
    REQUIREMENTS_PACKAGE_VERSION,
    STAGED_REQUIREMENTS_STEPS,
    STAGE_APPENDIX_TITLES,
    STAGE_LABELS,
    artifact_hash,
    invalidate_stage_and_downstream,
    mark_stage_artifact,
    normalize_requirements_checkpoint,
    package_artifacts_complete,
)
from workflow_controller.requirements_revision_routing import (
    requirements_auto_revision_semantic_key,
    select_requirements_revision_stage,
)
from workflow_controller.requirements_surface import (
    classify_requirements_surface,
    requirements_surface_uses_false_flag_as_no_ui_basis,
)
from workflow_controller.gates.generators import render_staged_requirements_package_gate_body
from workflow_controller.gates.parsers import approve_gate_file, write_gate_file
from workflow_controller.gates.validators import (
    validate_requirements_acceptance_quality,
    validate_staged_requirements_package_consistency,
    validate_staged_requirements_stage_output,
)
from workflow_controller.journeys import validate_and_write_journey_contract
from workflow_controller.prompts.requirements_package import (
    render_architecture_prompt,
    render_product_design_prompt,
    render_scope_prompt,
    render_test_strategy_prompt,
)
from workflow_controller.rrc_controller import RalphRefinerController, format_stop_guidance
from workflow_controller.steps.requirements_package import run_requirements_package_stage


def _write_artifact(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding='utf-8')
    return path


def _complete_checkpoint_artifacts(tmp_path: Path) -> dict:
    state: dict = {}
    for stage in STAGED_REQUIREMENTS_STEPS:
        path = _write_artifact(tmp_path, f'{stage}.md', f'# {stage}\n')
        mark_stage_artifact(state, stage, path)
    return state


def _staged_checkpoint_body(stage: str) -> str:
    return (
        f'# {stage}\n\n'
        '## 验收标准\n'
        f'- AC-07 [verification: functional]: {stage} preserves staged package facts.\n\n'
        '## Journey Acceptance Matrix\n'
        '| Journey | Status | AC |\n'
        '| --- | --- | --- |\n'
        '| J-01 | active | AC-07 |\n\n'
        '## AO Traceability\n'
        '| AO | AC | Status |\n'
        '| --- | --- | --- |\n'
        '| AO-001 | AC-07 | covered |\n'
    )


def _scope_with_e2e_journey(*, status: str = 'active', layer: str = 'e2e') -> str:
    return (
        '# Requirements Scope Checkpoint\n\n'
        '## Acceptance Criteria\n'
        '- AC-V04-001 [verification: integration]: Classroom state is persisted.\n\n'
        '## Test Strategy\n'
        '- Playwright browser E2E review is required for the classroom production flow.\n\n'
        '## Journey Acceptance Matrix\n'
        '| Journey | Title | Status | Steps | AC | Verification Layer |\n'
        '| --- | --- | --- | --- | --- | --- |\n'
        f'| J-V04-001 | Classroom production | {status} | Open course center -> inspect status | AC-V04-001 | {layer} |\n'
    )


def _requirements_4_6_matrix(
    row_ids: str = 'J-V04-001',
    *,
    command: str = (
        '`pnpm exec playwright test tests/e2e/classroom-v04.spec.ts '
        '--project=chromium --grep @J-V04-001`'
    ),
) -> str:
    return (
        '## 4.6 E2E 测试方法与前置依赖矩阵（E2E Test Method & Prerequisite Matrix）\n'
        '| AC / Journey | E2E Method | Real Entrypoint | User Steps | Fixture / Test Data / Setup | Verification Command | Environment Kind | Required Env / Dependencies | Mock Policy | Expected Assertions | Human Review Notes |\n'
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n'
        f'| {row_ids} | Playwright browser test in Chromium against local app | `/teacher/course-production` production route | Open `/teacher/course-production` -> inspect status row -> confirm chapter count | Seed classroom fixture `tests/fixtures/classroom-v04.json` and teacher user `teacher@example.test` | {command} | local_real | local app server and seeded SQLite test DB | No core API mocks; no `page.route("**/api/**")`; external services use test account only | Assert persisted status `ready`, chapter count 3, and visible row count 1 | Reviewer confirms route, fixture, command, env, mock policy, and assertions before approval |\n'
    )


def _complete_checkpoint_artifacts_with_content(tmp_path: Path) -> dict:
    state: dict = {}
    for stage in ['scope', 'product_design', 'architecture', 'test_strategy']:
        path = _write_artifact(tmp_path, f'{stage}.md', _staged_checkpoint_body(stage))
        mark_stage_artifact(state, stage, path)
    return state


def _write_required_product_prototype_manifest(draft_dir: Path) -> None:
    prototype_dir = draft_dir / 'prototypes' / 'course-center'
    prototype_dir.mkdir(parents=True)
    (prototype_dir / 'index.html').write_text(
        '<!doctype html><button>生成课程</button>\n',
        encoding='utf-8',
    )
    (draft_dir / 'prototype-manifest.json').write_text(
        json.dumps(
            {
                'prototypes': [
                    {
                        'id': 'course-center',
                        'type': 'html',
                        'path': 'prototypes/course-center/index.html',
                        'title': '课程生产中心',
                        'linked_acceptance_criteria': ['AC-07'],
                        'linked_journeys': ['J-01'],
                        'page_states': ['入口页', '生成中状态', '草稿详情'],
                        'click_path': ['打开课程生产中心', '点击生成课程', '查看草稿详情'],
                        'implementation_targets': [{'kind': 'route', 'path': '/teacher/course-center'}],
                        'surface_contracts': [
                            {
                                'id': 'course-center-page',
                                'title': '课程生产中心页面',
                                'kind': 'page',
                                'page_states': ['入口页', '生成中状态', '草稿详情'],
                                'click_path': ['打开课程生产中心', '点击生成课程', '查看草稿详情'],
                                'entrypoints': ['/teacher/course-center'],
                                'implementation_targets': [{'kind': 'route', 'path': '/teacher/course-center'}],
                                'linked_acceptance_criteria': ['AC-07'],
                                'linked_journeys': ['J-01'],
                                'required': True,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding='utf-8',
    )


def _product_design_preview_state(tmp_path: Path) -> dict:
    state: dict = {}
    scope_path = _write_artifact(tmp_path, 'scope.md', _staged_checkpoint_body('scope'))
    mark_stage_artifact(state, 'scope', scope_path)
    state.update({
        'task_id': 'target-v0-4',
        'currentUnitId': 'target-v0-4',
        'currentStep': 'REQUIREMENTS_PRODUCT_DESIGN_BRIEF',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'Classroom V0.4',
        'feasibleOutcome': 'Classroom V0.4',
        'scopeApproved': True,
        'autoApprove': True,
        'stagedRequirementsEnabled': True,
        'humanGatesRequired': True,
        'requirementsAccepted': False,
        'unitPlanAccepted': False,
        'finalAcceptanceAccepted': False,
        'agentRunner': 'subprocess',
        'currentUnitNeedsUiDesign': True,
        'currentUnitIsWebSystem': True,
        'requirementsSurfaceClassification': {
            'product_ui': 'required',
            'web_system': 'required',
            'prototype_required': 'required',
        },
        'units': [{'id': 'target-v0-4', 'passes': False}],
        'objectiveCoverage': [
            {
                'objective': 'Complete Classroom V0.4',
                'units': ['target-v0-4'],
                'status': 'partial',
            }
        ],
    })
    return state


def _stage_auto_revision_state(tmp_path: Path, *, requirements_accepted: bool = False) -> dict:
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-4',
        'currentUnitId': 'target-v0-4',
        'currentStep': 'REQUIREMENTS_TEST_STRATEGY_BRIEF',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'Classroom V0.4',
        'feasibleOutcome': 'Classroom V0.4',
        'scopeApproved': True,
        'humanGatesRequired': True,
        'requirementsAccepted': requirements_accepted,
        'requirementsDraftGenerated': False,
        'unitPlanAccepted': False,
        'agentRunner': 'tmux-codex',
        'agentCommand': 'codex',
        'tmuxTarget': '2.0',
        'requirementsAutoRevisionMax': 2,
        'units': [{'id': 'target-v0-4', 'passes': False}],
    })
    return state


def _classroom_v04_spec(tmp_path: Path) -> Path:
    return _write_artifact(
        tmp_path,
        'classroom-v0.4-spec.md',
        (
            '# Classroom V0.4\n\n'
            '- 课程生产中心入口：老师可以从主导航进入课程生产中心。\n'
            '- 状态回看页面或 API：操作者可以回看课程生成状态和失败原因。\n'
            '- 课程草稿详情：老师可以打开课程草稿详情，查看章节、素材和发布状态。\n'
        ),
    )


def test_staged_requirements_steps_are_ordered() -> None:
    assert REQUIREMENTS_PACKAGE_VERSION == 'v0.6.2-staged'
    assert STAGED_REQUIREMENTS_STEPS == [
        'scope',
        'product_design',
        'architecture',
        'test_strategy',
        'final_gate',
    ]


def test_staged_requirements_public_checkpoint_labels_are_chinese_primary() -> None:
    assert STAGE_LABELS['scope'].startswith('需求范围检查点')
    assert STAGE_LABELS['product_design'].startswith('产品设计简报')
    assert STAGE_LABELS['architecture'].startswith('技术架构简报')
    assert STAGE_LABELS['test_strategy'].startswith('需求测试策略简报')
    assert STAGE_APPENDIX_TITLES['scope'].startswith('附录 A：需求范围检查点')
    assert STAGE_APPENDIX_TITLES['product_design'].startswith('附录 B：产品设计简报')


def test_normalize_requirements_checkpoint_accepts_cli_and_chinese_aliases() -> None:
    assert normalize_requirements_checkpoint('product-design') == 'product_design'
    assert normalize_requirements_checkpoint('product_design') == 'product_design'
    assert normalize_requirements_checkpoint('产品设计') == 'product_design'
    assert normalize_requirements_checkpoint('技术架构') == 'architecture'
    assert normalize_requirements_checkpoint('测试策略') == 'test_strategy'
    assert normalize_requirements_checkpoint('需求范围') == 'scope'

    with pytest.raises(ValueError, match='Unknown requirements checkpoint'):
        normalize_requirements_checkpoint('deployment')


def test_mark_stage_artifact_records_path_hash_and_status(tmp_path: Path) -> None:
    state: dict = {}
    path = _write_artifact(tmp_path, 'requirements-scope.md', '# Scope\n')

    mark_stage_artifact(state, 'scope', path)

    record = state['requirementsPackage']['artifacts']['scope']
    assert state['requirementsPackage']['version'] == REQUIREMENTS_PACKAGE_VERSION
    assert record == {
        'stage': 'scope',
        'path': str(path),
        'hash': artifact_hash(path),
        'status': 'complete',
    }


def test_mark_stage_artifact_rejects_unknown_stage(tmp_path: Path) -> None:
    path = _write_artifact(tmp_path, 'unknown.md', '# Unknown\n')

    with pytest.raises(ValueError, match='Unknown requirements package stage'):
        mark_stage_artifact({}, 'unknown', path)


def test_package_artifacts_complete_requires_all_checkpoint_artifacts(tmp_path: Path) -> None:
    state: dict = {}
    for stage in ['scope', 'product_design', 'architecture', 'test_strategy']:
        path = _write_artifact(tmp_path, f'{stage}.md', f'# {stage}\n')
        mark_stage_artifact(state, stage, path)

    assert package_artifacts_complete(state) is True

    state['requirementsPackage']['artifacts']['test_strategy']['status'] = 'stale'
    assert package_artifacts_complete(state) is False


def test_package_artifacts_complete_detects_hash_mismatch(tmp_path: Path) -> None:
    state: dict = {}
    paths = {}
    for stage in ['scope', 'product_design', 'architecture', 'test_strategy']:
        paths[stage] = _write_artifact(tmp_path, f'{stage}.md', f'# {stage}\n')
        mark_stage_artifact(state, stage, paths[stage])

    paths['architecture'].write_text('# Architecture changed\n', encoding='utf-8')

    assert package_artifacts_complete(state) is False


def test_invalidate_stage_and_downstream_from_scope_marks_all_stale(tmp_path: Path) -> None:
    state = _complete_checkpoint_artifacts(tmp_path)

    invalidate_stage_and_downstream(state, 'scope', reason='scope revised')

    artifacts = state['requirementsPackage']['artifacts']
    assert [artifacts[stage]['status'] for stage in STAGED_REQUIREMENTS_STEPS] == [
        'stale',
        'stale',
        'stale',
        'stale',
        'stale',
    ]
    assert artifacts['product_design']['stale_reason'] == 'scope revised'


def test_invalidate_stage_and_downstream_from_architecture_preserves_upstream(
    tmp_path: Path,
) -> None:
    state = _complete_checkpoint_artifacts(tmp_path)

    invalidate_stage_and_downstream(state, 'architecture', reason='architecture revised')

    artifacts = state['requirementsPackage']['artifacts']
    assert artifacts['scope']['status'] == 'complete'
    assert artifacts['product_design']['status'] == 'complete'
    assert artifacts['architecture']['status'] == 'stale'
    assert artifacts['test_strategy']['status'] == 'stale'
    assert artifacts['final_gate']['status'] == 'stale'
    assert artifacts['architecture']['stale_reason'] == 'architecture revised'


def test_invalidate_stage_and_downstream_rejects_unknown_stage() -> None:
    with pytest.raises(ValueError, match='Unknown requirements package stage'):
        invalidate_stage_and_downstream({}, 'unknown')


def test_scope_prompt_is_focused_on_scope_and_acceptance() -> None:
    prompt = render_scope_prompt(
        {
            'task_id': 'target-v0-6-2',
            'requestedOutcome': 'V0.6.2',
            'feasibleOutcome': 'V0.6.2',
            'currentUnitId': 'v0-6-2-u2-checkpoint-prompts-runner',
        },
        output_path=Path('/tmp/requirements-scope.md'),
    )

    assert '需求范围' in prompt
    assert '验收标准' in prompt
    assert '用户旅程' in prompt
    assert 'AO traceability' in prompt
    assert '风险' in prompt
    assert '产品设计概要' not in prompt
    assert '架构概要' not in prompt
    assert '测试策略（Test Strategy）' not in prompt
    assert '目标项目基础设施信息' not in prompt


def test_scope_prompt_without_spec_requires_initial_human_clarification() -> None:
    prompt = render_scope_prompt(
        {
            'task_id': 'target-v0-5',
            'requestedOutcome': 'Classroom V0.5',
            'feasibleOutcome': 'Classroom V0.5',
            'currentUnitId': 'target-v0-5',
            'autoApprove': True,
            'stagedRequirementsEnabled': True,
            'requirementsPackage': {'version': 'v0.6.2-staged', 'artifacts': {}},
        },
        output_path=Path('/tmp/requirements-scope.md'),
    )

    assert '无 supported `requirementsSpec` 的 Scope 首轮人工澄清' in prompt
    assert '先在 tmux agent pane 向人工提 1 个需求澄清问题' in prompt
    assert '等待人工回答后' in prompt
    assert '不要立即读取项目上下文' in prompt
    assert '不要立即写 `requirements-scope.md`' in prompt
    assert '`--auto-approve` 不能跳过这一步' in prompt


def test_scope_prompt_with_spec_does_not_require_initial_clarification(tmp_path: Path) -> None:
    spec_path = _classroom_v04_spec(tmp_path)
    prompt = render_scope_prompt(
        {
            'task_id': 'target-v0-5',
            'requestedOutcome': 'Classroom V0.5',
            'feasibleOutcome': 'Classroom V0.5',
            'currentUnitId': 'target-v0-5',
            'autoApprove': True,
            'stagedRequirementsEnabled': True,
            'requirementsSpec': {
                'path': str(spec_path),
                'hash': 'sha256:spec',
                'sourceType': 'waygate-markdown',
                'importedAt': '2026-05-18T00:00:00Z',
            },
            'requirementsPackage': {'version': 'v0.6.2-staged', 'artifacts': {}},
        },
        output_path=Path('/tmp/requirements-scope.md'),
    )

    assert '无 supported `requirementsSpec` 的 Scope 首轮人工澄清' not in prompt
    assert '先在 tmux agent pane 向人工提 1 个需求澄清问题' not in prompt


def test_requirements_surface_classification_detects_classroom_visible_surfaces(
    tmp_path: Path,
) -> None:
    spec_path = _classroom_v04_spec(tmp_path)

    classification = classify_requirements_surface({
        'requestedOutcome': 'Classroom V0.4',
        'requirementsSpec': {'path': str(spec_path), 'sourceType': 'waygate-markdown'},
        'currentUnitNeedsUiDesign': False,
        'currentUnitIsWebSystem': False,
    })

    assert classification['product_ui'] == 'required'
    assert classification['web_system'] == 'required'
    assert classification['prototype_required'] == 'required'
    assert any('课程生产中心入口' in item for item in classification['visible_surfaces'])
    assert any('状态回看页面或 API' in item for item in classification['visible_surfaces'])
    assert any('课程草稿详情' in item for item in classification['visible_surfaces'])
    assert any('currentUnitNeedsUiDesign=false' in item for item in classification['evidence_snippets'])


def test_staged_prompts_anchor_to_target_product_surface_classification(
    tmp_path: Path,
) -> None:
    spec_path = _classroom_v04_spec(tmp_path)
    state = {
        'task_id': 'target-v0-4',
        'requestedOutcome': 'Classroom V0.4',
        'feasibleOutcome': 'Classroom V0.4',
        'currentUnitId': 'target-v0-4',
        'requirementsSpec': {
            'path': str(spec_path),
            'hash': 'sha256:abc123',
            'sourceType': 'waygate-markdown',
        },
        'currentUnitNeedsUiDesign': False,
        'currentUnitIsWebSystem': False,
    }
    state['requirementsSurfaceClassification'] = classify_requirements_surface(state)
    scope_path = _write_artifact(
        tmp_path,
        'scope.md',
        (
            '# Scope\n\n'
            '## 可见产品表面\n'
            '- 课程生产中心入口\n'
            '- 状态回看页面或 API\n'
            '- 课程草稿详情\n'
        ),
    )
    mark_stage_artifact(state, 'scope', scope_path)
    product_path = _write_artifact(tmp_path, 'product.md', '# Product Design\n')
    mark_stage_artifact(state, 'product_design', product_path)

    scope_prompt = render_scope_prompt(state, output_path=tmp_path / 'requirements-scope.md')
    product_prompt = render_product_design_prompt(state, output_path=tmp_path / 'product-design-brief.md')
    architecture_prompt = render_architecture_prompt(state, output_path=tmp_path / 'architecture-brief.md')
    test_strategy_prompt = render_test_strategy_prompt(state, output_path=tmp_path / 'test-strategy-brief.md')

    assert 'requirementsSurfaceClassification' in scope_prompt
    assert '课程生产中心入口' in scope_prompt
    assert 'currentUnitNeedsUiDesign=false' in scope_prompt
    assert '不得把默认 false 当成不需要 UI/原型的证据' in scope_prompt
    assert 'Status=active' in scope_prompt
    assert 'Verification Layer=e2e' in scope_prompt
    assert '| Journey | Title | Status | Steps | AC | Verification Layer |' in scope_prompt
    assert '目标产品 UX' in product_prompt
    assert '课程草稿详情' in product_prompt
    assert 'checkpoint 进度模型' not in product_prompt
    assert '目标系统交互架构' in architecture_prompt
    assert 'canonical e2e AC' in architecture_prompt
    assert 'controller orchestration' not in architecture_prompt
    assert '策略层' in test_strategy_prompt
    assert 'Unit Plan 级别的 exact commands' in test_strategy_prompt
    assert 'Verification Command` 列填写命令意图' in test_strategy_prompt
    assert '## 4.6 E2E 测试方法与前置依赖矩阵' in test_strategy_prompt
    assert '## 6 E2E / Browser 审阅映射' in test_strategy_prompt
    assert '| Journey | Title | Status | Steps | AC | Verification Layer |' in test_strategy_prompt


def test_test_strategy_prompt_names_validator_level_4_6_contract(tmp_path: Path) -> None:
    prompt = render_test_strategy_prompt(
        {'requestedOutcome': 'Classroom V0.4'},
        output_path=tmp_path / 'requirements-test-strategy.md',
    )

    assert 'local_real' in prompt
    assert 'production_readonly' in prompt
    assert 'Real Entrypoint' in prompt
    assert '真实 route、URL、page、command 或 service entrypoint' in prompt
    assert 'User Steps' in prompt
    assert '具体用户/API/service 操作步骤' in prompt
    assert 'Fixture / Test Data / Setup' in prompt
    assert '固定 fixture、测试账号、seed data 或 setup' in prompt
    assert '核心业务 API 不得 mock/stub' in prompt
    assert 'Expected Assertions' in prompt
    assert 'machine-checkable' in prompt
    assert '截图不能作为唯一断言' in prompt


def test_downstream_prompts_require_previous_artifact_hashes() -> None:
    state = {
        'requirementsPackage': {
            'version': REQUIREMENTS_PACKAGE_VERSION,
            'artifacts': {
                'scope': {
                    'stage': 'scope',
                    'path': '/tmp/scope.md',
                    'hash': 'abc123',
                    'status': 'complete',
                }
            },
        }
    }

    prompts = [
        render_product_design_prompt(state, output_path=Path('/tmp/product-design-brief.md')),
        render_architecture_prompt(state, output_path=Path('/tmp/architecture-brief.md')),
        render_test_strategy_prompt(state, output_path=Path('/tmp/test-strategy-brief.md')),
    ]

    for prompt in prompts:
        assert '/tmp/scope.md' in prompt
        assert 'abc123' in prompt


def test_product_design_prompt_requires_manifest_contract_for_required_prototype() -> None:
    state = {
        'requestedOutcome': 'Classroom V0.4',
        'requirementsSurfaceClassification': {
            'product_ui': 'required',
            'web_system': 'required',
            'prototype_required': 'required',
            'visible_surfaces': ['课程生产中心入口', '课程草稿详情'],
        },
    }

    prompt = render_product_design_prompt(state, output_path=Path('/tmp/product-design-brief.md'))

    assert 'artifacts/requirements-draft/prototype-manifest.json' in prompt
    assert 'clickable prototype access method' in prompt
    assert 'page_states' in prompt
    assert 'click_path' in prompt
    assert 'linked_acceptance_criteria' in prompt
    assert 'linked_journeys' in prompt
    assert 'implementation_targets' in prompt
    assert 'surface_contracts' in prompt


def test_scope_stage_validation_rejects_natural_language_e2e_mapping(tmp_path: Path) -> None:
    state: dict = {}
    scope_path = _write_artifact(
        tmp_path,
        'scope.md',
        _scope_with_e2e_journey(status='是', layer='real integration + DB assertion'),
    )
    mark_stage_artifact(state, 'scope', scope_path)

    with pytest.raises(ValueError, match='Status=active.*Verification Layer=e2e.*## 4\\.6'):
        validate_staged_requirements_stage_output(state, tmp_path / 'artifacts', 'scope')


def test_scope_stage_validation_accepts_canonical_e2e_journey_mapping(tmp_path: Path) -> None:
    state: dict = {}
    scope_path = _write_artifact(tmp_path, 'scope.md', _scope_with_e2e_journey())
    mark_stage_artifact(state, 'scope', scope_path)

    validate_staged_requirements_stage_output(state, tmp_path / 'artifacts', 'scope')


def test_product_design_stage_validation_rejects_manifest_references_unknown_scope_ids(
    tmp_path: Path,
) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    draft_dir = artifacts_dir / 'requirements-draft'
    prototype_dir = draft_dir / 'prototypes' / 'course-center'
    prototype_dir.mkdir(parents=True)
    (prototype_dir / 'index.html').write_text('<!doctype html><title>Course center</title>\n', encoding='utf-8')
    (draft_dir / 'prototype-manifest.json').write_text(
        json.dumps(
            {
                'prototypes': [
                    {
                        'id': 'course-center',
                        'type': 'html',
                        'title': '课程生产中心',
                        'path': 'prototypes/course-center/index.html',
                        'linked_acceptance_criteria': ['AC-V04-999'],
                        'linked_journeys': ['J-V04-999'],
                        'page_states': ['入口页'],
                        'click_path': ['打开课程生产中心'],
                        'implementation_targets': [{'kind': 'route', 'path': '/teacher/course-production'}],
                        'surface_contracts': [
                            {
                                'id': 'course-center-page',
                                'title': '课程生产中心页面',
                                'kind': 'page',
                                'page_states': ['入口页'],
                                'click_path': ['打开课程生产中心'],
                                'entrypoints': ['/teacher/course-production'],
                                'implementation_targets': [
                                    {'kind': 'route', 'path': '/teacher/course-production'}
                                ],
                                'linked_acceptance_criteria': ['AC-V04-999'],
                                'required': True,
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    state = {
        'requirementsSurfaceClassification': {
            'product_ui': 'required',
            'web_system': 'required',
            'prototype_required': 'required',
        }
    }
    scope_path = _write_artifact(tmp_path, 'scope.md', _scope_with_e2e_journey())
    product_path = _write_artifact(tmp_path, 'product.md', '# Product Design\n\n- Prototype maps classroom UI.\n')
    mark_stage_artifact(state, 'scope', scope_path)
    mark_stage_artifact(state, 'product_design', product_path)

    with pytest.raises(ValueError, match='unknown acceptance criteria: AC-V04-999.*unknown Journey: J-V04-999'):
        validate_staged_requirements_stage_output(state, artifacts_dir, 'product_design')


def test_architecture_stage_validation_rejects_unknown_scope_ids(tmp_path: Path) -> None:
    state: dict = {}
    scope_path = _write_artifact(tmp_path, 'scope.md', _scope_with_e2e_journey())
    architecture_path = _write_artifact(
        tmp_path,
        'architecture.md',
        '# Technical Architecture Brief\n\n- Architecture links AC-V04-999 and J-V04-999.\n',
    )
    mark_stage_artifact(state, 'scope', scope_path)
    mark_stage_artifact(state, 'architecture', architecture_path)

    with pytest.raises(ValueError, match='unknown acceptance criteria: AC-V04-999.*unknown Journey: J-V04-999'):
        validate_staged_requirements_stage_output(state, tmp_path / 'artifacts', 'architecture')


def test_architecture_stage_validation_requires_scope_e2e_handoff_ids(tmp_path: Path) -> None:
    state: dict = {}
    scope_path = _write_artifact(tmp_path, 'scope.md', _scope_with_e2e_journey())
    architecture_path = _write_artifact(
        tmp_path,
        'architecture.md',
        '# Technical Architecture Brief\n\n'
        '- The runtime supports browser review through real integration and DB assertions.\n',
    )
    mark_stage_artifact(state, 'scope', scope_path)
    mark_stage_artifact(state, 'architecture', architecture_path)

    with pytest.raises(ValueError, match='must reference Scope canonical e2e AC/Journey'):
        validate_staged_requirements_stage_output(state, tmp_path / 'artifacts', 'architecture')


def test_test_strategy_stage_validation_rejects_noncanonical_e2e_heading(tmp_path: Path) -> None:
    state: dict = {}
    scope_path = _write_artifact(tmp_path, 'scope.md', _scope_with_e2e_journey())
    test_strategy_path = _write_artifact(
        tmp_path,
        'test-strategy.md',
        '# Requirements Test Strategy Brief\n\n'
        '## 6 E2E / Browser 审阅映射\n'
        '| AC / Journey | Method |\n'
        '| --- | --- |\n'
        '| J-V04-001 | Playwright browser review |\n',
    )
    mark_stage_artifact(state, 'scope', scope_path)
    mark_stage_artifact(state, 'test_strategy', test_strategy_path)

    with pytest.raises(ValueError, match='## 4\\.6 E2E 测试方法与前置依赖矩阵'):
        validate_staged_requirements_stage_output(state, tmp_path / 'artifacts', 'test_strategy')


def test_test_strategy_stage_validation_accepts_fixed_4_6_matrix_covering_scope_e2e(
    tmp_path: Path,
) -> None:
    state: dict = {}
    scope_path = _write_artifact(tmp_path, 'scope.md', _scope_with_e2e_journey())
    test_strategy_path = _write_artifact(
        tmp_path,
        'test-strategy.md',
        '# Requirements Test Strategy Brief\n\n' + _requirements_4_6_matrix('J-V04-001'),
    )
    mark_stage_artifact(state, 'scope', scope_path)
    mark_stage_artifact(state, 'test_strategy', test_strategy_path)

    validate_staged_requirements_stage_output(state, tmp_path / 'artifacts', 'test_strategy')


def test_test_strategy_stage_validation_accepts_4_6_command_intent_without_exact_command(
    tmp_path: Path,
) -> None:
    state: dict = {}
    scope_path = _write_artifact(tmp_path, 'scope.md', _scope_with_e2e_journey())
    test_strategy_path = _write_artifact(
        tmp_path,
        'test-strategy.md',
        '# Requirements Test Strategy Brief\n\n'
        + _requirements_4_6_matrix(
            'J-V04-001',
            command=(
                'Unit Plan must create Go service/API E2E command for services/api '
                'real OpenMAIC PDF integration'
            ),
        ),
    )
    mark_stage_artifact(state, 'scope', scope_path)
    mark_stage_artifact(state, 'test_strategy', test_strategy_path)

    validate_staged_requirements_stage_output(state, tmp_path / 'artifacts', 'test_strategy')


def test_test_strategy_stage_validation_journey_row_covers_mapped_e2e_ac(
    tmp_path: Path,
) -> None:
    state: dict = {}
    scope_path = _write_artifact(
        tmp_path,
        'scope.md',
        (
            '# Requirements Scope Checkpoint\n\n'
            '## Acceptance Criteria\n'
            '- AC-V04-013 [verification: e2e]: Classroom PDF prerequisite state is prepared.\n\n'
            '## Test Strategy\n'
            '- Service/API E2E review is required for the classroom production flow.\n\n'
            '## Journey Acceptance Matrix\n'
            '| Journey | Title | Status | Steps | AC | Verification Layer |\n'
            '| --- | --- | --- | --- | --- | --- |\n'
            '| J-V04-001 | Classroom production | active | Call OpenMAIC PDF service -> inspect persisted status | AC-V04-013 | e2e |\n'
        ),
    )
    test_strategy_path = _write_artifact(
        tmp_path,
        'test-strategy.md',
        '# Requirements Test Strategy Brief\n\n'
        + _requirements_4_6_matrix(
            'J-V04-001',
            command=(
                'Unit Plan must create Go service/API E2E command for services/api '
                'real OpenMAIC PDF integration'
            ),
        ),
    )
    mark_stage_artifact(state, 'scope', scope_path)
    mark_stage_artifact(state, 'test_strategy', test_strategy_path)

    validate_staged_requirements_stage_output(state, tmp_path / 'artifacts', 'test_strategy')


def test_test_strategy_stage_validation_does_not_promote_prerequisite_row_references_to_e2e(
    tmp_path: Path,
) -> None:
    state: dict = {}
    scope_path = _write_artifact(
        tmp_path,
        'scope.md',
        (
            '# Requirements Scope Checkpoint\n\n'
            '## 验收标准\n'
            '| AC id | 需求断言 | verification layer | fixture/setup | expected |\n'
            '| --- | --- | --- | --- | --- |\n'
            '| `AC-V04-001 [verification: e2e]` | PDF real integration | e2e | real OpenMAIC PDF fixture | persisted draft |\n'
            '| `AC-V04-002 [verification: e2e]` | Text real integration | e2e | real OpenMAIC text input | persisted draft |\n'
            '| `AC-V04-013` | Prerequisite environment and fixture are prepared | prerequisite | fixed fixture, DB, OpenMAIC env | before `AC-V04-001 [verification: e2e]` and `AC-V04-002 [verification: e2e]` real paths |\n'
            '| `AC-V04-014 [verification: e2e]` | Visible surface is reviewable | e2e | API/status/draft surface | visible status and draft detail |\n\n'
            '## Test Strategy\n'
            '- Service/API E2E review is required for the classroom production flow.\n\n'
            '## Journey Acceptance Matrix\n'
            '| Journey | Title | Status | Steps | AC | Verification Layer |\n'
            '| --- | --- | --- | --- | --- | --- |\n'
            '| J-V04-001 | PDF production | active | Call OpenMAIC PDF service -> inspect persisted status | AC-V04-001 | e2e |\n'
            '| J-V04-002 | Text production | active | Call OpenMAIC text service -> inspect persisted status | AC-V04-002 | e2e |\n'
            '| J-V04-005 | Visible surface | active | Inspect API visible status -> inspect draft detail | AC-V04-014 | e2e |\n'
        ),
    )
    test_strategy_path = _write_artifact(
        tmp_path,
        'test-strategy.md',
        '# Requirements Test Strategy Brief\n\n'
        + _requirements_4_6_matrix(
            'J-V04-001 / AC-V04-001 / J-V04-002 / AC-V04-002 / J-V04-005 / AC-V04-014',
            command=(
                'Unit Plan must create Go service/API E2E command for services/api '
                'real OpenMAIC PDF, text, visible-surface status, and draft-detail verification'
            ),
        ),
    )
    mark_stage_artifact(state, 'scope', scope_path)
    mark_stage_artifact(state, 'test_strategy', test_strategy_path)

    validate_staged_requirements_stage_output(state, tmp_path / 'artifacts', 'test_strategy')


def test_scope_stage_validation_allows_prototype_only_review_without_real_e2e_mapping(
    tmp_path: Path,
) -> None:
    state: dict = {}
    scope_path = _write_artifact(
        tmp_path,
        'scope.md',
        (
            '# Requirements Scope Checkpoint\n\n'
            '## Acceptance Criteria\n'
            '- AC-V04-014 [verification: functional]: Classroom prototype review is available.\n\n'
            '## User Journeys\n'
            '- J-V04-005 prototype review only: reviewer opens the prototype artifact and checks layout intent.\n\n'
            '## Prototype Review\n'
            '- Prototype review is limited to artifact inspection; production E2E belongs to Unit Plan prototype conformance if required.\n'
        ),
    )

    validate_staged_requirements_stage_output(
        state,
        tmp_path / 'artifacts',
        'scope',
        artifact_path=scope_path,
    )


def test_product_design_prompt_includes_canonical_manifest_schema_skeleton() -> None:
    state = {
        'requestedOutcome': 'Classroom V0.4',
        'requirementsSurfaceClassification': {
            'product_ui': 'required',
            'web_system': 'required',
            'prototype_required': 'required',
            'visible_surfaces': ['课程生产中心入口', '课程草稿详情'],
        },
    }

    prompt = render_product_design_prompt(state, output_path=Path('/tmp/product-design-brief.md'))

    assert '"prototypes": [' in prompt
    assert '"id": "course-center"' in prompt
    assert '"path": "prototypes/course-center/index.html"' in prompt
    assert '"surface_contracts": [' in prompt
    assert '不要把 `clickable_prototype_access_method`、`page_states`、`click_path` 写成扁平顶层字段' in prompt


def test_product_design_prompt_declares_local_paths_are_artifact_local() -> None:
    state = {
        'requestedOutcome': 'Classroom V0.4',
        'requirementsSurfaceClassification': {
            'product_ui': 'required',
            'web_system': 'required',
            'prototype_required': 'required',
            'visible_surfaces': ['课程生产中心入口', '课程草稿详情'],
        },
    }

    prompt = render_product_design_prompt(
        state,
        output_path=Path('/tmp/artifacts/requirements-product-design/product-design-brief.md'),
    )

    assert '相对 `artifacts/requirements-draft/prototype-manifest.json` 所在目录解析' in prompt
    assert '先生成或复制到 `artifacts/requirements-draft/prototypes/<prototype-id>/index.html`' in prompt
    assert '"path": "prototypes/course-center/index.html"' in prompt
    assert '不要写 workspace-relative 的 `docs/prototypes/...`' in prompt


def test_local_template_writes_artifact_and_summary(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    state = {
        'task_id': 'target-v0-6-2',
        'requestedOutcome': 'V0.6.2',
        'stagedRequirementsEnabled': True,
        'agentRunner': 'subprocess',
    }

    result = run_requirements_package_stage(
        state,
        artifacts_dir,
        stage='scope',
        dry_run=True,
    )

    artifact_path = artifacts_dir / 'requirements-scope' / 'requirements-scope.md'
    summary_path = artifacts_dir / 'requirements-scope' / 'requirements-scope-summary.json'
    assert artifact_path.exists()
    assert summary_path.exists()
    assert str(artifact_path) in (result.outputs or [])

    record = state['requirementsPackage']['artifacts']['scope']
    assert record['path'] == str(artifact_path)
    assert record['hash'] == artifact_hash(artifact_path)
    assert record['status'] == 'complete'

    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    assert summary['status'] == 'ok'
    assert summary['stage'] == 'scope'
    assert summary['artifact_path'] == str(artifact_path)


def test_scope_stage_without_spec_disables_idle_monitor_for_initial_clarification(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import workflow_controller.steps.requirements_package as requirements_package_step
    from workflow_controller.runners import RunnerConfig
    from workflow_controller.runners.base import DEFAULT_AGENT_TIMEOUT_SECONDS, RunnerResult

    artifacts_dir = tmp_path / 'artifacts'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    captured_idle_monitor_enabled: list[bool] = []
    captured_timeout_seconds: list[int | None] = []

    def fake_make_runner(state: dict) -> RunnerConfig:
        return RunnerConfig(backend='tmux-claude', agent_command='fake-claude', tmux_target='2.0')

    def fake_run_agent_backend(request):
        captured_idle_monitor_enabled.append(request.idle_monitor_enabled)
        captured_timeout_seconds.append(request.timeout_seconds)
        artifact_path = artifacts_dir / 'requirements-scope' / 'requirements-scope.md'
        artifact_path.write_text(_staged_checkpoint_body('scope'), encoding='utf-8')
        return RunnerResult(
            backend='tmux-claude',
            status='done',
            command=['fake-claude'],
            returncode=0,
            stdout='ok',
            stderr='',
            run_dir=artifacts_dir / 'requirements-scope' / 'runs' / 'scope-run',
            prompt_path=request.prompt_path,
            done_payload={'status': 'done'},
            runner_metadata={'fake': True},
        )

    monkeypatch.setattr(requirements_package_step, 'make_runner', fake_make_runner)
    monkeypatch.setattr(requirements_package_step, 'run_agent_backend', fake_run_agent_backend)

    run_requirements_package_stage(
        {
            'task_id': 'target-v0-5',
            'requestedOutcome': 'Classroom V0.5',
            'currentUnitId': 'target-v0-5',
            'currentStep': 'REQUIREMENTS_SCOPE_DRAFT',
            'stagedRequirementsEnabled': True,
            'agentRunner': 'tmux-claude',
            'workspacePath': str(workspace),
            'agentCommand': 'claude',
            'tmuxTarget': '2.0',
            'requirementsPackage': {'version': 'v0.6.2-staged', 'artifacts': {}},
        },
        artifacts_dir,
        stage='scope',
    )

    assert captured_idle_monitor_enabled == [False]
    assert captured_timeout_seconds == [DEFAULT_AGENT_TIMEOUT_SECONDS]


def test_scope_stage_with_spec_keeps_idle_monitor_enabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import workflow_controller.steps.requirements_package as requirements_package_step
    from workflow_controller.runners import RunnerConfig
    from workflow_controller.runners.base import RunnerResult

    artifacts_dir = tmp_path / 'artifacts'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    spec_path = _classroom_v04_spec(tmp_path)
    captured_idle_monitor_enabled: list[bool] = []

    def fake_make_runner(state: dict) -> RunnerConfig:
        return RunnerConfig(backend='tmux-claude', agent_command='fake-claude', tmux_target='2.0')

    def fake_run_agent_backend(request):
        captured_idle_monitor_enabled.append(request.idle_monitor_enabled)
        artifact_path = artifacts_dir / 'requirements-scope' / 'requirements-scope.md'
        artifact_path.write_text(_staged_checkpoint_body('scope'), encoding='utf-8')
        return RunnerResult(
            backend='tmux-claude',
            status='done',
            command=['fake-claude'],
            returncode=0,
            stdout='ok',
            stderr='',
            run_dir=artifacts_dir / 'requirements-scope' / 'runs' / 'scope-run',
            prompt_path=request.prompt_path,
            done_payload={'status': 'done'},
            runner_metadata={'fake': True},
        )

    monkeypatch.setattr(requirements_package_step, 'make_runner', fake_make_runner)
    monkeypatch.setattr(requirements_package_step, 'run_agent_backend', fake_run_agent_backend)

    run_requirements_package_stage(
        {
            'task_id': 'target-v0-5',
            'requestedOutcome': 'Classroom V0.5',
            'currentUnitId': 'target-v0-5',
            'currentStep': 'REQUIREMENTS_SCOPE_DRAFT',
            'stagedRequirementsEnabled': True,
            'agentRunner': 'tmux-claude',
            'workspacePath': str(workspace),
            'agentCommand': 'claude',
            'tmuxTarget': '2.0',
            'requirementsSpec': {
                'path': str(spec_path),
                'hash': 'sha256:spec',
                'sourceType': 'waygate-markdown',
                'importedAt': '2026-05-18T00:00:00Z',
            },
            'requirementsPackage': {'version': 'v0.6.2-staged', 'artifacts': {}},
        },
        artifacts_dir,
        stage='scope',
    )

    assert captured_idle_monitor_enabled == [True]


def test_product_design_stage_requires_manifest_when_prototype_is_required(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    state = {
        'task_id': 'target-v0-4',
        'requestedOutcome': 'Classroom V0.4',
        'stagedRequirementsEnabled': True,
        'agentRunner': 'subprocess',
        'requirementsSurfaceClassification': {
            'product_ui': 'required',
            'web_system': 'required',
            'prototype_required': 'required',
        },
    }

    with pytest.raises(ValueError, match='Product Design checkpoint requires.*prototype-manifest\\.json'):
        run_requirements_package_stage(
            state,
            artifacts_dir,
            stage='product_design',
            dry_run=True,
        )


def test_product_design_stage_rejects_flat_manifest_with_missing_prototypes_guidance(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    draft_dir = artifacts_dir / 'requirements-draft'
    draft_dir.mkdir(parents=True)
    (draft_dir / 'prototype-manifest.json').write_text(
        json.dumps({
            'clickable_prototype_access_method': 'open course-center.html',
            'page_states': ['入口页', '草稿详情'],
            'click_path': ['打开课程生产中心', '查看草稿详情'],
            'linked_acceptance_criteria': ['AC-07'],
            'implementation_targets': [{'kind': 'route', 'path': '/teacher/course-center'}],
            'surface_contracts': [{'id': 'course-center-page'}],
        }),
        encoding='utf-8',
    )
    state = {
        'task_id': 'target-v0-4',
        'requestedOutcome': 'Classroom V0.4',
        'stagedRequirementsEnabled': True,
        'agentRunner': 'subprocess',
        'requirementsSurfaceClassification': {
            'product_ui': 'required',
            'web_system': 'required',
            'prototype_required': 'required',
        },
    }

    with pytest.raises(ValueError) as excinfo:
        run_requirements_package_stage(
            state,
            artifacts_dir,
            stage='product_design',
            dry_run=True,
        )

    message = str(excinfo.value)
    assert 'missing `prototypes[]`' in message
    assert 'flat top-level prototype manifest keys are not accepted' in message


def test_product_design_stage_rejects_workspace_relative_manifest_path_with_artifact_local_guidance(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    draft_dir = artifacts_dir / 'requirements-draft'
    draft_dir.mkdir(parents=True)
    workspace_prototype = tmp_path / 'docs' / 'prototypes' / 'customer-course-production.html'
    workspace_prototype.parent.mkdir(parents=True)
    workspace_prototype.write_text('<button>生成课程</button>', encoding='utf-8')
    (draft_dir / 'prototype-manifest.json').write_text(
        json.dumps({
            'prototypes': [
                {
                    'id': 'v04-course-production-center',
                    'type': 'html',
                    'path': 'docs/prototypes/customer-course-production.html',
                    'title': 'V0.4 课程生产中心',
                    'linked_acceptance_criteria': ['AC-07'],
                    'linked_journeys': ['J-01'],
                    'page_states': ['入口页', '生成中状态', '草稿详情'],
                    'click_path': ['打开课程生产中心', '点击生成课程', '查看草稿详情'],
                    'implementation_targets': [{'kind': 'route', 'path': '/teacher/course-center'}],
                    'surface_contracts': [
                        {
                            'id': 'course-center-page',
                            'title': '课程生产中心页面',
                            'kind': 'page',
                            'page_states': ['入口页', '生成中状态', '草稿详情'],
                            'click_path': ['打开课程生产中心', '点击生成课程', '查看草稿详情'],
                            'entrypoints': ['/teacher/course-center'],
                            'implementation_targets': [{'kind': 'route', 'path': '/teacher/course-center'}],
                            'linked_acceptance_criteria': ['AC-07'],
                            'required': True,
                        }
                    ],
                }
            ]
        }),
        encoding='utf-8',
    )
    state = {
        'task_id': 'target-v0-4',
        'requestedOutcome': 'Classroom V0.4',
        'stagedRequirementsEnabled': True,
        'agentRunner': 'subprocess',
        'requirementsSurfaceClassification': {
            'product_ui': 'required',
            'web_system': 'required',
            'prototype_required': 'required',
        },
    }

    with pytest.raises(ValueError) as excinfo:
        run_requirements_package_stage(
            state,
            artifacts_dir,
            stage='product_design',
            dry_run=True,
        )

    message = str(excinfo.value)
    assert 'prototype v04-course-production-center path does not exist: docs/prototypes/customer-course-production.html' in message
    assert str(draft_dir / 'docs' / 'prototypes' / 'customer-course-production.html') in message
    assert 'paths are resolved relative to artifacts/requirements-draft' in message
    assert 'workspace-relative docs/prototypes path' in message


def test_product_design_stage_accepts_docs_path_when_file_exists_under_artifact_tree(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    draft_dir = artifacts_dir / 'requirements-draft'
    prototype_path = draft_dir / 'docs' / 'prototypes' / 'customer-course-production.html'
    prototype_path.parent.mkdir(parents=True)
    prototype_path.write_text('<button>生成课程</button>', encoding='utf-8')
    (draft_dir / 'prototype-manifest.json').write_text(
        json.dumps({
            'prototypes': [
                {
                    'id': 'v04-course-production-center',
                    'type': 'html',
                    'path': 'docs/prototypes/customer-course-production.html',
                    'title': 'V0.4 课程生产中心',
                    'linked_acceptance_criteria': ['AC-07'],
                    'linked_journeys': ['J-01'],
                    'page_states': ['入口页', '生成中状态', '草稿详情'],
                    'click_path': ['打开课程生产中心', '点击生成课程', '查看草稿详情'],
                    'implementation_targets': [{'kind': 'route', 'path': '/teacher/course-center'}],
                    'surface_contracts': [
                        {
                            'id': 'course-center-page',
                            'title': '课程生产中心页面',
                            'kind': 'page',
                            'page_states': ['入口页', '生成中状态', '草稿详情'],
                            'click_path': ['打开课程生产中心', '点击生成课程', '查看草稿详情'],
                            'entrypoints': ['/teacher/course-center'],
                            'implementation_targets': [{'kind': 'route', 'path': '/teacher/course-center'}],
                            'linked_acceptance_criteria': ['AC-07'],
                            'required': True,
                        }
                    ],
                }
            ]
        }),
        encoding='utf-8',
    )
    state = {
        'task_id': 'target-v0-4',
        'requestedOutcome': 'Classroom V0.4',
        'stagedRequirementsEnabled': True,
        'agentRunner': 'subprocess',
        'requirementsSurfaceClassification': {
            'product_ui': 'required',
            'web_system': 'required',
            'prototype_required': 'required',
        },
    }
    scope_path = _write_artifact(tmp_path, 'scope.md', _staged_checkpoint_body('scope'))
    mark_stage_artifact(state, 'scope', scope_path)

    result = run_requirements_package_stage(
        state,
        artifacts_dir,
        stage='product_design',
        dry_run=True,
    )

    assert result.summary == 'requirements package stage product_design generated'
    assert state['requirementsPackage']['artifacts']['product_design']['status'] == 'complete'


def test_product_design_stage_accepts_basic_required_prototype_manifest(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    draft_dir = artifacts_dir / 'requirements-draft'
    draft_dir.mkdir(parents=True)
    prototype_path = draft_dir / 'course-center.html'
    prototype_path.write_text('<button>生成课程</button>', encoding='utf-8')
    (draft_dir / 'prototype-manifest.json').write_text(
        json.dumps({
            'prototypes': [
                {
                    'id': 'course-center',
                    'type': 'html',
                    'path': 'course-center.html',
                    'title': '课程生产中心',
                    'linked_acceptance_criteria': ['AC-07'],
                    'linked_journeys': ['J-01'],
                    'page_states': ['入口页', '生成中状态', '草稿详情'],
                    'click_path': ['打开课程生产中心', '点击生成课程', '查看草稿详情'],
                    'implementation_targets': [{'kind': 'route', 'path': '/teacher/course-center'}],
                    'surface_contracts': [
                        {
                            'id': 'course-center-page',
                            'title': '课程生产中心页面',
                            'kind': 'page',
                            'page_states': ['入口页', '生成中状态', '草稿详情'],
                            'click_path': ['打开课程生产中心', '点击生成课程', '查看草稿详情'],
                            'entrypoints': ['/teacher/course-center'],
                            'implementation_targets': [{'kind': 'route', 'path': '/teacher/course-center'}],
                            'linked_acceptance_criteria': ['AC-07'],
                            'required': True,
                        }
                    ],
                    'preview_hint': '打开 HTML 后点击生成课程按钮。',
                    'review_guidance': '检查入口、状态回看和详情页是否覆盖 AC/Journey。',
                }
            ]
        }),
        encoding='utf-8',
    )
    state = {
        'task_id': 'target-v0-4',
        'requestedOutcome': 'Classroom V0.4',
        'stagedRequirementsEnabled': True,
        'agentRunner': 'subprocess',
        'requirementsSurfaceClassification': {
            'product_ui': 'required',
            'web_system': 'required',
            'prototype_required': 'required',
        },
    }
    scope_path = _write_artifact(tmp_path, 'scope.md', _staged_checkpoint_body('scope'))
    mark_stage_artifact(state, 'scope', scope_path)

    run_requirements_package_stage(
        state,
        artifacts_dir,
        stage='product_design',
        dry_run=True,
    )

    assert state['requirementsPackage']['artifacts']['product_design']['status'] == 'complete'


def test_product_design_run_once_generates_bundle_and_starts_persistent_preview(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv('WAYGATE_PREVIEW_PORT', '0')
    monkeypatch.setenv('WAYGATE_DISPLAY_HOST', '192.0.2.88')
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    controller.init_state(_product_design_preview_state(tmp_path), force=True)
    draft_dir = state_dir / 'artifacts' / 'requirements-draft'
    _write_required_product_prototype_manifest(draft_dir)

    try:
        result = controller.run_once()

        assert result['currentStep'] == 'REQUIREMENTS_TECH_ARCH_BRIEF'
        assert (draft_dir / 'plannotator-review.html').exists()
        review_manifest = json.loads((draft_dir / 'prototype-review-manifest.json').read_text(encoding='utf-8'))
        scope_path = Path(result['requirementsPackage']['artifacts']['scope']['path'])
        assert review_manifest['requirements_reference_path'] == str(scope_path)
        assert 'approval_gate_path' not in review_manifest
        assert result['prototypeReviewPreview']['url'].startswith('http://192.0.2.88:')
        assert result['prototypeReviewPreview']['url'].endswith('/plannotator-review.html')
        events = [
            json.loads(line)
            for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
            if line.strip()
        ]
        preview_event = next(event for event in events if event['type'] == 'prototype_review_preview_started')
        assert preview_event['payload']['stage'] == 'product_design'
        assert preview_event['payload']['preview_url'] == result['prototypeReviewPreview']['url']
        assert preview_event['payload']['review_path'] == str(draft_dir / 'plannotator-review.html')
        assert isinstance(preview_event['payload']['port'], int)
    finally:
        getattr(controller, 'close', lambda: None)()


def test_final_assembly_refreshes_bundle_with_approval_gate_and_reuses_preview_port(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv('WAYGATE_PREVIEW_PORT', '0')
    monkeypatch.setenv('WAYGATE_DISPLAY_HOST', '192.0.2.88')
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    controller.init_state(_product_design_preview_state(tmp_path), force=True)
    draft_dir = state_dir / 'artifacts' / 'requirements-draft'
    _write_required_product_prototype_manifest(draft_dir)

    try:
        product_state = controller.run_once()
        preview_url = product_state['prototypeReviewPreview']['url']
        state = controller.store.load_state()
        architecture_path = _write_artifact(tmp_path, 'architecture-final.md', _staged_checkpoint_body('architecture'))
        test_strategy_path = _write_artifact(tmp_path, 'test-strategy-final.md', _staged_checkpoint_body('test_strategy'))
        mark_stage_artifact(state, 'architecture', architecture_path)
        mark_stage_artifact(state, 'test_strategy', test_strategy_path)
        state['currentStep'] = 'REQUIREMENTS_PACKAGE_ASSEMBLE'
        controller.store.save_state(state)

        final_state = controller.run_once()

        assert final_state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
        assert final_state['prototypeReviewPreview']['url'] == preview_url
        review_manifest = json.loads((draft_dir / 'prototype-review-manifest.json').read_text(encoding='utf-8'))
        assert review_manifest['approval_gate_path'] == str(state_dir / 'approvals' / 'requirements-and-acceptance.md')
        assert review_manifest['requirements_reference_path'] == str(state_dir / 'approvals' / 'requirements-and-acceptance.md')
        events = [
            json.loads(line)
            for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
            if line.strip()
        ]
        preview_events = [event for event in events if event['type'] == 'prototype_review_preview_started']
        assert len(preview_events) == 1
    finally:
        getattr(controller, 'close', lambda: None)()


def test_product_design_run_once_stage_validation_failure_records_recovery_state(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'target-v0-4',
            'currentUnitId': 'target-v0-4',
            'currentStep': 'REQUIREMENTS_PRODUCT_DESIGN_BRIEF',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'Classroom V0.4',
            'feasibleOutcome': 'Classroom V0.4',
            'scopeApproved': True,
            'autoApprove': True,
            'stagedRequirementsEnabled': True,
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'unitPlanAccepted': False,
            'finalAcceptanceAccepted': False,
            'agentRunner': 'subprocess',
            'currentUnitNeedsUiDesign': True,
            'currentUnitIsWebSystem': True,
            'requirementsSurfaceClassification': {
                'product_ui': 'required',
                'web_system': 'required',
                'prototype_required': 'required',
            },
            'requirementsPackage': {
                'version': REQUIREMENTS_PACKAGE_VERSION,
                'artifacts': {
                    'scope': {
                        'stage': 'scope',
                        'path': '/tmp/scope.md',
                        'hash': 'scopehash',
                        'status': 'complete',
                    }
                },
            },
            'units': [{'id': 'target-v0-4', 'passes': False}],
            'objectiveCoverage': [
                {
                    'objective': 'Complete Classroom V0.4',
                    'units': ['target-v0-4'],
                    'status': 'partial',
                }
            ],
        },
        force=True,
    )

    state = controller.run_once()

    assert state['status'] == 'blocked'
    assert state['currentStep'] == 'REQUIREMENTS_PRODUCT_DESIGN_BRIEF'
    assert '产品设计简报' in state['blockedReason']
    assert 'stage validation failed' in state['blockedReason']
    assert 'prototype-manifest.json' in state['blockedReason']
    assert state['blockedContext']['category'] == 'requirements_stage_validation'
    assert state['blockedContext']['action'] == 'run_requirements_product_design_brief'
    validation_path = Path(state['blockedContext']['validation_artifact'])
    assert validation_path.exists()
    validation = json.loads(validation_path.read_text(encoding='utf-8'))
    assert validation['stage'] == 'product_design'
    assert validation['action'] == 'run_requirements_product_design_brief'
    assert 'Rerun 产品设计简报' in validation['guidance']
    assert 'upstream AC/Journey/Requirements contract change' in validation['guidance']
    guidance = format_stop_guidance(state, state_dir=state_dir)
    assert '默认解除阻塞并重跑 产品设计简报' in guidance
    assert 'waygate unblock --state-dir' in guidance
    assert 'waygate revise --gate requirements' in guidance


def test_test_strategy_stage_validation_failure_auto_reworks_unapproved_requirements(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_stage_auto_revision_state(tmp_path), force=True)
    reason = (
        'J-V04-005 Requirements 4.6 Environment Kind must be local_real or '
        'production_readonly, not component_mock'
    )

    def fail_test_strategy_stage(*_args, stage: str, **_kwargs):
        assert stage == 'test_strategy'
        raise ValueError(reason)

    monkeypatch.setattr(rrc_controller_module, 'run_requirements_package_stage', fail_test_strategy_stage)

    result = controller.run_once()

    assert result['status'] == 'active'
    assert result['currentStep'] == 'REQUIREMENTS_TEST_STRATEGY_BRIEF'
    assert result['nextAllowedActions'] == ['run_requirements_test_strategy_brief']
    assert result.get('blockedReason') is None
    assert 'Controller stage validation feedback' in result['requirementsRevisionFeedback']
    assert reason in result['requirementsRevisionFeedback']
    assert result['requirementsPackage']['artifacts']['test_strategy']['status'] == 'stale'

    prompt = render_test_strategy_prompt(
        result,
        output_path=tmp_path / 'requirements-test-strategy.md',
    )
    assert 'Controller stage validation feedback' in prompt
    assert reason in prompt

    events = [
        json.loads(line)
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    requested = [
        event for event in events if event['type'] == 'requirements_stage_auto_revision_requested'
    ]
    assert len(requested) == 1
    assert requested[0]['payload']['stage'] == 'test_strategy'
    assert requested[0]['payload']['action'] == 'run_requirements_test_strategy_brief'
    assert requested[0]['payload']['reason'] == reason
    assert requested[0]['payload']['reason_key'] == 'test_strategy:test_method_quality'
    assert requested[0]['payload']['attempt'] == 1
    assert requested[0]['payload']['total_attempt'] == 1


def test_stage_validation_auto_rework_blocks_after_same_reason_budget(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(_stage_auto_revision_state(tmp_path), force=True)
    reason = (
        'J-V04-005 Requirements 4.6 Expected Assertions must contain concrete '
        'machine-checkable assertions; screenshots or human observation cannot be the only assertion'
    )

    def fail_test_strategy_stage(*_args, stage: str, **_kwargs):
        assert stage == 'test_strategy'
        raise ValueError(reason)

    monkeypatch.setattr(rrc_controller_module, 'run_requirements_package_stage', fail_test_strategy_stage)

    first = controller.run_once()
    assert first['status'] == 'active'
    second = controller.run_once()
    assert second['status'] == 'active'
    blocked = controller.run_once()

    assert blocked['status'] == 'blocked'
    assert blocked['currentStep'] == 'REQUIREMENTS_TEST_STRATEGY_BRIEF'
    assert blocked['blockedContext']['category'] == 'requirements_stage_validation'
    assert 'requirements stage validation invalid after automatic revisions' in blocked['blockedReason']
    guidance = format_stop_guidance(blocked, state_dir=state_dir)
    assert 'waygate unblock --state-dir' in guidance
    assert 'waygate revise --gate requirements' in guidance

    events = [
        json.loads(line)
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    requested = [
        event for event in events if event['type'] == 'requirements_stage_auto_revision_requested'
    ]
    assert [event['payload']['attempt'] for event in requested] == [1, 2]
    assert [event['payload']['total_attempt'] for event in requested] == [1, 2]
    blocked_events = [
        event for event in events if event['type'] == 'requirements_stage_auto_revision_blocked'
    ]
    assert len(blocked_events) == 1
    assert blocked_events[0]['payload']['consecutive_attempts'] == 3
    assert blocked_events[0]['payload']['total_attempts'] == 2


def test_stage_validation_does_not_auto_rework_after_requirements_approved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        _stage_auto_revision_state(tmp_path, requirements_accepted=True),
        force=True,
    )

    def fail_test_strategy_stage(*_args, stage: str, **_kwargs):
        assert stage == 'test_strategy'
        raise ValueError('approved Requirements stage validation must not silently rewrite contract')

    monkeypatch.setattr(rrc_controller_module, 'run_requirements_package_stage', fail_test_strategy_stage)

    result = controller.run_once()

    assert result['status'] == 'blocked'
    assert result['currentStep'] == 'REQUIREMENTS_TEST_STRATEGY_BRIEF'
    assert result['blockedContext']['category'] == 'requirements_stage_validation'
    events = [
        json.loads(line)['type']
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    assert 'requirements_stage_auto_revision_requested' not in events


def test_staged_stage_validation_unblock_injects_controller_error_into_next_prompt(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-4',
        'currentUnitId': 'target-v0-4',
        'currentStep': 'REQUIREMENTS_TEST_STRATEGY_BRIEF',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'blocked',
        'blockedReason': (
            'Test Strategy stage validation failed: J-V04-005 Requirements 4.6 '
            'Real Entrypoint must be a real route, URL, page, command, or service entrypoint'
        ),
        'blockedContext': {
            'category': 'requirements_stage_validation',
            'stage': 'test_strategy',
            'action': 'run_requirements_test_strategy_brief',
        },
        'requestedOutcome': 'Classroom V0.4',
        'scopeApproved': True,
        'requirementsAccepted': False,
        'unitPlanAccepted': False,
        'units': [{'id': 'target-v0-4', 'passes': False}],
    })
    controller.init_state(state, force=True)

    controller.unblock_blocked_workflow(reason='rerun after stage validation failure')
    unblocked = controller.store.load_state()

    prompt = render_test_strategy_prompt(
        unblocked,
        output_path=tmp_path / 'requirements-test-strategy.md',
    )

    assert 'Controller stage validation feedback' in prompt
    assert 'Real Entrypoint must be a real route' in prompt
    assert 'J-V04-005' in prompt


def test_staged_requirements_run_once_advances_one_checkpoint_at_a_time(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'target-v0-6-2',
            'currentUnitId': 'v0-6-2-u2-checkpoint-prompts-runner',
            'currentStep': 'REQUIREMENTS_SCOPE_DRAFT',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'V0.6.2',
            'feasibleOutcome': 'V0.6.2',
            'scopeApproved': True,
            'autoApprove': True,
            'stagedRequirementsEnabled': True,
            'humanGatesRequired': True,
            'requirementsAccepted': False,
            'unitPlanAccepted': False,
            'finalAcceptanceAccepted': False,
            'units': [{'id': 'v0-6-2-u2-checkpoint-prompts-runner', 'passes': False}],
            'objectiveCoverage': [
                {
                    'objective': 'Complete V0.6.2 development acceptance',
                    'units': ['v0-6-2-u2-checkpoint-prompts-runner'],
                    'status': 'partial',
                }
            ],
        },
        force=True,
    )

    expected_steps = [
        'REQUIREMENTS_PRODUCT_DESIGN_BRIEF',
        'REQUIREMENTS_TECH_ARCH_BRIEF',
        'REQUIREMENTS_TEST_STRATEGY_BRIEF',
        'REQUIREMENTS_PACKAGE_ASSEMBLE',
    ]
    for expected_step in expected_steps:
        state = controller.run_once()
        assert state['currentStep'] == expected_step

    package = state['requirementsPackage']['artifacts']
    for stage in ['scope', 'product_design', 'architecture', 'test_strategy']:
        assert package[stage]['status'] == 'complete'
        assert Path(package[stage]['path']).exists()

    events = [
        json.loads(line)
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    generated = [event for event in events if event['type'] == 'requirements_package_stage_generated']
    assert [event['payload']['stage'] for event in generated] == [
        'scope',
        'product_design',
        'architecture',
        'test_strategy',
    ]


def test_final_package_assembly_embeds_checkpoint_appendices_and_hashes(tmp_path: Path) -> None:
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-6-2',
        'requestedOutcome': 'V0.6.2',
        'feasibleOutcome': 'V0.6.2',
        'currentUnitId': 'v0-6-2-u3-package-assembly-validation',
    })

    gate = render_staged_requirements_package_gate_body(state)

    assert '## 审批摘要' in gate
    assert '## Artifact Hashes' in gate
    assert '| Checkpoint | Stage Key | Path | Hash | Status |' in gate
    assert '| 需求范围检查点' in gate
    assert '| 产品设计简报' in gate
    assert '## 附录 A：需求范围检查点' in gate
    assert '## 附录 B：产品设计简报' in gate
    assert '## 附录 C：技术架构简报' in gate
    assert '## 附录 D：需求测试策略简报' in gate
    for record in state['requirementsPackage']['artifacts'].values():
        assert record['path'] in gate
        assert record['hash'] in gate

    validate_staged_requirements_package_consistency(gate, state)

    scope_path = Path(state['requirementsPackage']['artifacts']['scope']['path'])
    scope_path.write_text(scope_path.read_text(encoding='utf-8') + '\nchanged\n', encoding='utf-8')
    with pytest.raises(ValueError, match='hash mismatch'):
        render_staged_requirements_package_gate_body(state)


def test_package_consistency_rejects_missing_appendix_hash_and_conflicts(tmp_path: Path) -> None:
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    valid_gate = render_staged_requirements_package_gate_body(state)

    with pytest.raises(ValueError, match='missing appendix.*Product Design'):
        validate_staged_requirements_package_consistency(
            valid_gate.replace('## 附录 B：产品设计简报', '## Removed Product Design Brief'),
            state,
        )

    product_hash = state['requirementsPackage']['artifacts']['product_design']['hash']
    with pytest.raises(ValueError, match='missing artifact hash row.*product_design'):
        validate_staged_requirements_package_consistency(
            valid_gate.replace(product_hash, ''),
            state,
        )

    scope_path = Path(state['requirementsPackage']['artifacts']['scope']['path'])
    scope_path.write_text(scope_path.read_text(encoding='utf-8') + '\nchanged\n', encoding='utf-8')
    with pytest.raises(ValueError, match='hash mismatch.*scope'):
        validate_staged_requirements_package_consistency(valid_gate, state)

    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    architecture_path = Path(state['requirementsPackage']['artifacts']['architecture']['path'])
    architecture_path.write_text(
        architecture_path.read_text(encoding='utf-8').replace(
            'AC-07 [verification: functional]',
            'AC-07 [verification: integration]',
        ),
        encoding='utf-8',
    )
    mark_stage_artifact(state, 'architecture', architecture_path)
    conflicting_gate = render_staged_requirements_package_gate_body(state)
    with pytest.raises(ValueError, match='conflicting AC.*AC-07'):
        validate_staged_requirements_package_consistency(conflicting_gate, state)


def test_package_consistency_ignores_rejected_word_outside_journey_status_column(
    tmp_path: Path,
) -> None:
    state = _complete_checkpoint_artifacts_with_content(tmp_path)

    scope_path = Path(state['requirementsPackage']['artifacts']['scope']['path'])
    scope_path.write_text(
        scope_path.read_text(encoding='utf-8')
        + (
            '\n| Journey | Title | Status | Steps | AC | Verification Layer |\n'
            '| --- | --- | --- | --- | --- | --- |\n'
            '| J-V062E-004 | Requirements checkpoint validation | active | '
            'Open staged final preflight -> inspect controller feedback | AC-07 | functional |\n'
        ),
        encoding='utf-8',
    )
    mark_stage_artifact(state, 'scope', scope_path)

    product_path = Path(state['requirementsPackage']['artifacts']['product_design']['path'])
    product_path.write_text(
        product_path.read_text(encoding='utf-8')
        + (
            '\n| Journey | Product behavior | Rejection copy |\n'
            '| --- | --- | --- |\n'
            '| J-V062E-004 | Final preflight keeps scope facts | '
            'The invalid checkpoint form is rejected before human approval. |\n'
        ),
        encoding='utf-8',
    )
    mark_stage_artifact(state, 'product_design', product_path)

    strategy_path = Path(state['requirementsPackage']['artifacts']['test_strategy']['path'])
    strategy_path.write_text(
        strategy_path.read_text(encoding='utf-8')
        + (
            '\n| Journey | Test observation | Expected result |\n'
            '| --- | --- | --- |\n'
            '| J-V062E-004 | Submit an invalid checkpoint form | '
            'The command/form is rejected and no Status column is declared here. |\n'
        ),
        encoding='utf-8',
    )
    mark_stage_artifact(state, 'test_strategy', strategy_path)

    gate = render_staged_requirements_package_gate_body(state)

    validate_staged_requirements_package_consistency(gate, state)


def test_package_consistency_rejects_conflicting_journey_status_column(
    tmp_path: Path,
) -> None:
    state = _complete_checkpoint_artifacts_with_content(tmp_path)

    scope_path = Path(state['requirementsPackage']['artifacts']['scope']['path'])
    scope_path.write_text(
        scope_path.read_text(encoding='utf-8')
        + (
            '\n| Journey | Title | Status | Steps | AC | Verification Layer |\n'
            '| --- | --- | --- | --- | --- | --- |\n'
            '| J-V062E-004 | Requirements checkpoint validation | active | '
            'Open staged final preflight -> inspect controller feedback | AC-07 | functional |\n'
        ),
        encoding='utf-8',
    )
    mark_stage_artifact(state, 'scope', scope_path)

    strategy_path = Path(state['requirementsPackage']['artifacts']['test_strategy']['path'])
    strategy_path.write_text(
        strategy_path.read_text(encoding='utf-8')
        + (
            '\n| Journey | Title | Status | Steps | AC | Verification Layer |\n'
            '| --- | --- | --- | --- | --- | --- |\n'
            '| J-V062E-004 | Requirements checkpoint validation | rejected | '
            'Reject invalid package state -> report controller feedback | AC-07 | functional |\n'
        ),
        encoding='utf-8',
    )
    mark_stage_artifact(state, 'test_strategy', strategy_path)

    gate = render_staged_requirements_package_gate_body(state)

    with pytest.raises(ValueError, match='conflicting Journey status.*J-V062E-004'):
        validate_staged_requirements_package_consistency(gate, state)


def test_package_consistency_prefers_explicit_verification_tag_over_api_text(
    tmp_path: Path,
) -> None:
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    scope_path = Path(state['requirementsPackage']['artifacts']['scope']['path'])
    scope_path.write_text(
        scope_path.read_text(encoding='utf-8')
        + '\n- AC-08 [verification: e2e]: Fixed PDF course creation uses the real service path.\n',
        encoding='utf-8',
    )
    mark_stage_artifact(state, 'scope', scope_path)

    product_path = Path(state['requirementsPackage']['artifacts']['product_design']['path'])
    product_path.write_text(
        product_path.read_text(encoding='utf-8')
        + (
            '\n| Journey | Method | AC | Verification Layer | Notes |\n'
            '| --- | --- | --- | --- | --- |\n'
            '| J-08 | PDF real service/API E2E | AC-08 [verification: e2e] | e2e | '
            'Use the real API and DB evidence for this E2E review. |\n'
        ),
        encoding='utf-8',
    )
    mark_stage_artifact(state, 'product_design', product_path)

    gate = render_staged_requirements_package_gate_body(state)

    validate_staged_requirements_package_consistency(gate, state)


def test_package_consistency_does_not_promote_explanatory_table_references_to_e2e(
    tmp_path: Path,
) -> None:
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    scope_path = Path(state['requirementsPackage']['artifacts']['scope']['path'])
    scope_path.write_text(
        scope_path.read_text(encoding='utf-8')
        + (
            '\n- AC-08 [verification: e2e]: Fixed PDF course creation uses the real service path.\n'
            '- AC-09 [verification: integration]: Status and failure states are persisted.\n'
        ),
        encoding='utf-8',
    )
    mark_stage_artifact(state, 'scope', scope_path)

    product_path = Path(state['requirementsPackage']['artifacts']['product_design']['path'])
    product_path.write_text(
        product_path.read_text(encoding='utf-8')
        + (
            '\n| Surface | Review intent | Coverage notes |\n'
            '| --- | --- | --- |\n'
            '| API visible output | API contract / response / DB linkage review | '
            'direct e2e AC `AC-08 [verification: e2e]`, and integration AC `AC-09` | \n'
        ),
        encoding='utf-8',
    )
    mark_stage_artifact(state, 'product_design', product_path)

    gate = render_staged_requirements_package_gate_body(state)

    validate_staged_requirements_package_consistency(gate, state)


def test_staged_validator_skips_legacy_4_9_but_legacy_still_requires_it(tmp_path: Path) -> None:
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(render_staged_requirements_package_gate_body(state), encoding='utf-8')

    validate_requirements_acceptance_quality(gate, state)

    legacy_gate = tmp_path / 'legacy-requirements.md'
    legacy_gate.write_text(gate.read_text(encoding='utf-8'), encoding='utf-8')
    with pytest.raises(ValueError, match='4\\.9.*目标项目基础设施信息'):
        validate_requirements_acceptance_quality(legacy_gate, {'requestedOutcome': 'V1.0'})


def test_staged_requirements_preflight_requires_manifest_for_classified_ui_surface(
    tmp_path: Path,
) -> None:
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    spec_path = _classroom_v04_spec(tmp_path)
    state.update({
        'requestedOutcome': 'Classroom V0.4',
        'requirementsSpec': {'path': str(spec_path), 'sourceType': 'waygate-markdown'},
        'currentUnitNeedsUiDesign': False,
        'currentUnitIsWebSystem': False,
    })
    state['requirementsSurfaceClassification'] = classify_requirements_surface(state)
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(render_staged_requirements_package_gate_body(state), encoding='utf-8')

    with pytest.raises(ValueError, match='valid prototype manifest'):
        validate_requirements_acceptance_quality(gate, state)


def test_staged_requirements_preflight_accepts_valid_clickable_manifest_as_web_evidence(
    tmp_path: Path,
) -> None:
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'requestedOutcome': 'Classroom V0.4',
        'currentUnitNeedsUiDesign': True,
        'currentUnitIsWebSystem': True,
        'requirementsSurfaceClassification': {
            'product_ui': 'required',
            'web_system': 'required',
            'prototype_required': 'required',
            'visible_surfaces': ['teacher dashboard'],
            'evidence_snippets': ['target is a Web classroom UI'],
        },
    })
    approvals_dir = tmp_path / 'approvals'
    approvals_dir.mkdir()
    gate = approvals_dir / 'requirements-and-acceptance.md'
    gate.write_text(render_staged_requirements_package_gate_body(state), encoding='utf-8')
    draft_dir = tmp_path / 'artifacts' / 'requirements-draft'
    draft_dir.mkdir(parents=True)
    html_path = draft_dir / 'teacher-dashboard.html'
    html_path.write_text('<html><body><button>Open class</button></body></html>\n', encoding='utf-8')
    (draft_dir / 'prototype-manifest.json').write_text(
        json.dumps(
            {
                'prototypes': [
                    {
                        'id': 'teacher-dashboard',
                        'type': 'html',
                        'path': str(html_path),
                        'title': 'Teacher dashboard clickable prototype',
                        'linked_acceptance_criteria': ['AC-07'],
                        'linked_journeys': ['J-01'],
                        'page_states': ['Dashboard', 'Course detail'],
                        'click_path': ['Open dashboard', 'Click course card'],
                        'implementation_targets': [{'kind': 'route', 'path': '/teacher/dashboard'}],
                    }
                ]
            }
        ),
        encoding='utf-8',
    )

    validate_requirements_acceptance_quality(gate, state)


def test_clickable_product_design_text_counts_as_evidence_but_still_requires_manifest(
    tmp_path: Path,
) -> None:
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'requestedOutcome': 'Classroom V0.4',
        'currentUnitNeedsUiDesign': True,
        'currentUnitIsWebSystem': True,
        'requirementsSurfaceClassification': {
            'product_ui': 'required',
            'web_system': 'required',
            'prototype_required': 'required',
            'visible_surfaces': ['teacher dashboard'],
            'evidence_snippets': ['target is a Web classroom UI'],
        },
    })
    product_path = Path(state['requirementsPackage']['artifacts']['product_design']['path'])
    product_path.write_text(
        product_path.read_text(encoding='utf-8')
        + (
            '\n## Clickable Prototype Evidence\n'
            '- Artifact-local clickable HTML: `artifacts/requirements-draft/prototypes/teacher-dashboard/index.html`.\n'
            '- Manifest path: `artifacts/requirements-draft/prototype-manifest.json`.\n'
            '- Page states: Dashboard, Course detail, Empty state.\n'
            '- Click path: Open dashboard -> Click course card -> Inspect detail.\n'
            '- AC/Journey mapping: maps to AC-07 and J-01.\n'
        ),
        encoding='utf-8',
    )
    mark_stage_artifact(state, 'product_design', product_path)
    gate = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    gate.parent.mkdir()
    gate.write_text(render_staged_requirements_package_gate_body(state), encoding='utf-8')

    with pytest.raises(ValueError) as excinfo:
        validate_requirements_acceptance_quality(gate, state)

    message = str(excinfo.value)
    assert 'valid prototype manifest' in message
    assert 'Web system requires clickable webpage prototype evidence' not in message


def test_staged_requirements_preflight_accepts_versioned_journey_id_e2e_review_mapping(
    tmp_path: Path,
) -> None:
    state: dict = {
        'requestedOutcome': 'Classroom V0.4',
        'requirementsSurfaceClassification': {
            'product_ui': 'not_required',
            'web_system': 'not_required',
            'prototype_required': 'not_required',
            'visible_surfaces': [],
            'evidence_snippets': ['API-only path for this test fixture.'],
        },
    }
    body = (
        '# Requirements\n\n'
        '## Acceptance Criteria\n'
        '- AC-V04-001 [verification: integration]: API state is persisted.\n\n'
        '## Test Strategy\n'
        '- Playwright browser E2E review is required for the active classroom journey.\n\n'
        '## Journey Acceptance Matrix\n'
        '| Journey | Title | Status | Steps | AC | Verification Layer |\n'
        '| --- | --- | --- | --- | --- | --- |\n'
        '| J-V04-001 | Classroom happy path | active | Open course center -> inspect status | AC-V04-001 | e2e |\n\n'
        '## UI / Prototype Basis\n'
        '- 本测试目标是 API-only fixture；不能把 currentUnitNeedsUiDesign=false 当作不需要 UI/原型的证据。\n'
        '- 独立依据：本 fixture 无浏览器页面，E2E 语义通过 service entrypoint 证明。\n\n'
        '## 4.6 E2E 测试方法与前置依赖矩阵（E2E Test Method & Prerequisite Matrix）\n'
        '| AC / Journey | E2E Method | Real Entrypoint | User Steps | Fixture / Test Data / Setup | Verification Command | Environment Kind | Required Env / Dependencies | Mock Policy | Expected Assertions | Human Review Notes |\n'
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n'
        '| J-V04-001 | Playwright browser test in Chromium against local app | `/teacher/course-production` production route | Open `/teacher/course-production` -> inspect status row -> confirm generated chapter count | Seed classroom fixture `tests/fixtures/classroom-v04.json` and teacher user `teacher@example.test` | `pnpm exec playwright test tests/e2e/classroom-v04.spec.ts --project=chromium --grep @J-V04-001` | local_real | local app server and seeded SQLite test DB | No core API mocks; no `page.route("**/api/**")`; external services use test account only | Assert persisted status `ready`, chapter count 3, and visible row count 1 | Reviewer confirms route, fixture, command, env, mock policy, and assertions before approval |\n'
    )
    for stage in ['scope', 'product_design', 'architecture', 'test_strategy']:
        path = _write_artifact(tmp_path, f'{stage}.md', body)
        mark_stage_artifact(state, stage, path)
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(render_staged_requirements_package_gate_body(state), encoding='utf-8')

    validate_requirements_acceptance_quality(gate, state)


def test_staged_requirements_preflight_accepts_static_regression_and_prerequisite_layers(
    tmp_path: Path,
) -> None:
    state: dict = {
        'requestedOutcome': 'Classroom V0.4',
        'requirementsSurfaceClassification': {
            'product_ui': 'not_required',
            'web_system': 'not_required',
            'prototype_required': 'not_required',
            'visible_surfaces': [],
            'evidence_snippets': ['API-only path for this test fixture.'],
        },
    }
    body = (
        '# Requirements Scope Checkpoint\n\n'
        '## Acceptance Criteria\n'
        '| AC id | Requirement assertion | verification layer | fixture/setup | expected |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AC-V04-008 | V0.4 scope guard rejects publish/enrollment/tutor behavior | static | Requirements and docs review | out-of-scope list is explicit |\n'
        '| AC-V04-009 | Secret handling policy never records model keys or credentialed DB URLs | static | redaction policy review | secret values are not printed |\n'
        '| AC-V04-010 | Required operations and architecture docs are registered | static | docs registry review | docs deliverables are listed |\n'
        '| AC-V04-011 | V0.1-V0.3 baseline behavior stays intact | regression | existing baseline suite | prior endpoints still pass |\n'
        '| AC-V04-012 | Manual release notes record non-goals and residual risks | manual | reviewer checklist | review notes are explicit |\n'
        '| AC-V04-013 | Fixed fixture and real OpenMAIC environment are ready before the real flow | prerequisite | fixture, DB, service env | downstream integration can run |\n\n'
        '## Test Strategy\n'
        '- This checkpoint contains control, baseline and prerequisite ACs only.\n\n'
        '## Journey Acceptance Matrix\n'
        '| Journey | Title | Status | Steps | AC | Verification Layer |\n'
        '| --- | --- | --- | --- | --- | --- |\n'
        '| J-V04-004 | Baseline regression | active | Run baseline suite -> inspect result | AC-V04-011 | regression |\n'
    )
    for stage in ['scope', 'product_design', 'architecture', 'test_strategy']:
        path = _write_artifact(tmp_path, f'{stage}.md', body)
        mark_stage_artifact(state, stage, path)
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(render_staged_requirements_package_gate_body(state), encoding='utf-8')

    validate_requirements_acceptance_quality(gate, state)


def test_journey_contract_accepts_user_steps_and_support_layers(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        (
            '# Requirements\n\n'
            '## Journey Acceptance Matrix\n'
            '| Journey id | Name | Status | User steps | Linked AC | Verification Layer |\n'
            '| --- | --- | --- | --- | --- | --- |\n'
            '| J-V04-006 | Legacy compatibility | active | Run V0.1-V0.3 regression -> inspect scope guard -> review artifact index | AC-V04-011 | regression |\n'
        ),
        encoding='utf-8',
    )

    contract_path = validate_and_write_journey_contract(
        requirements_path=gate,
        artifacts_dir=tmp_path / 'artifacts',
        state={},
    )

    assert contract_path is not None
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    journey = contract['journeys'][0]
    assert journey['journey_id'] == 'J-V04-006'
    assert journey['steps'] == [
        'Run V0.1-V0.3 regression',
        'inspect scope guard',
        'review artifact index',
    ]
    assert journey['linked_acceptance_criteria'] == ['AC-V04-011']
    assert journey['verification_layer'] == 'regression'


def test_journey_contract_accepts_scope_table_without_title_and_contract_steps(
    tmp_path: Path,
) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        (
            '# Requirements\n\n'
            '## Journey Acceptance Matrix\n'
            '| Journey | Status | Acceptance contract | AC | Verification Layer |\n'
            '| --- | --- | --- | --- | --- |\n'
            '| J-V04-007 | active | Open legacy page -> inspect generated draft -> confirm persisted state | AC-V04-011 | regression |\n\n'
            '## Additional Journey Assertions\n'
            '| Journey id | Status | Path / assertion focus | Linked AC | Verification Layer |\n'
            '| --- | --- | --- | --- | --- |\n'
            '| J-V04-008 | active | Import spec -> assemble package -> assert hash handoff | AC-V04-012 | integration |\n'
        ),
        encoding='utf-8',
    )

    contract_path = validate_and_write_journey_contract(
        requirements_path=gate,
        artifacts_dir=tmp_path / 'artifacts',
        state={},
    )

    assert contract_path is not None
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    journeys = {journey['journey_id']: journey for journey in contract['journeys']}
    assert journeys['J-V04-007']['title'] == 'J-V04-007'
    assert journeys['J-V04-007']['steps'] == [
        'Open legacy page',
        'inspect generated draft',
        'confirm persisted state',
    ]
    assert journeys['J-V04-008']['title'] == 'J-V04-008'
    assert journeys['J-V04-008']['steps'] == [
        'Import spec',
        'assemble package',
        'assert hash handoff',
    ]


def test_journey_contract_merges_compatible_duplicate_rows_from_assembled_gate(
    tmp_path: Path,
) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        (
            '# Requirements\n\n'
            '## 4. 用户旅程\n'
            '| Journey ID | Journey | Status | Path / assertion focus | AC | Verification Layer |\n'
            '| --- | --- | --- | --- | --- | --- |\n'
            '| J-V21-001 | Homepage happy path | active | Open overview -> inspect effective badge | AC-02 | e2e |\n\n'
            '## 8. Journey Acceptance Matrix\n'
            '| Journey | Source unit | Target unit | Product surface / entrypoint | AC | Status | Verification Layer | Acceptance contract |\n'
            '| --- | --- | --- | --- | --- | --- | --- | --- |\n'
            '| J-V21-001 | unit-01 | unit-01 | Home page | AC-02 | active | e2e | Browser/API evidence proves the effective badge. |\n\n'
            '## 4.7 Journey Acceptance Matrix\n'
            '| Journey | Title | Status | Steps | AC | Verification Layer | Verification Command | Test Case | Unit |\n'
            '| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n'
            '| J-V21-001 | Homepage happy path | active | Open overview -> wait API -> assert effective badge | AC-02 | e2e | Unit Plan command intent | TC-J001 | unit-01 |\n'
        ),
        encoding='utf-8',
    )

    contract_path = validate_and_write_journey_contract(
        requirements_path=gate,
        artifacts_dir=tmp_path / 'artifacts',
        state={},
    )

    assert contract_path is not None
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    assert [journey['journey_id'] for journey in contract['journeys']] == ['J-V21-001']
    journey = contract['journeys'][0]
    assert '_merge_conflicts' not in journey
    assert journey['steps'] == ['Open overview', 'wait API', 'assert effective badge']
    assert journey['linked_acceptance_criteria'] == ['AC-02']
    assert journey['test_cases'] == ['TC-J001']


def test_journeys_module_can_be_imported_directly() -> None:
    result = subprocess.run(
        [sys.executable, '-c', 'from workflow_controller.journeys import extract_requirement_journeys'],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_staged_requirements_preflight_uses_journey_header_aliases_for_e2e_mapping(
    tmp_path: Path,
) -> None:
    state: dict = {
        'requestedOutcome': 'Classroom V0.4',
        'requirementsSurfaceClassification': {
            'product_ui': 'not_required',
            'web_system': 'not_required',
            'prototype_required': 'not_required',
            'visible_surfaces': [],
            'evidence_snippets': ['API-only path for this test fixture.'],
        },
    }
    body = (
        '# Requirements\n\n'
        '## Acceptance Criteria\n'
        '- AC-V04-001 [verification: integration]: API state is persisted.\n\n'
        '## Test Strategy\n'
        '- Service/API E2E review is required for the active classroom journey.\n\n'
        '## Journey Acceptance Matrix\n'
        '| Name | Journey id | Linked AC | Steps | Verification Layer | Status |\n'
        '| --- | --- | --- | --- | --- | --- |\n'
        '| Classroom happy path | J-V04-001 | AC-V04-001 | Submit PDF -> poll status -> inspect draft detail | e2e | active |\n\n'
        '## UI / Prototype Basis\n'
        '- 本测试目标是 API-only fixture；不能把 currentUnitNeedsUiDesign=false 当作不需要 UI/原型的证据。\n'
        '- 独立依据：本 fixture 无浏览器页面，E2E 语义通过 service entrypoint 证明。\n\n'
        + _requirements_4_6_matrix(
            'J-V04-001',
            command=(
                'Unit Plan must create Go service/API E2E command for services/api '
                'real OpenMAIC PDF draft verification'
            ),
        )
    )
    for stage in ['scope', 'product_design', 'architecture', 'test_strategy']:
        path = _write_artifact(tmp_path, f'{stage}.md', body)
        mark_stage_artifact(state, stage, path)
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(render_staged_requirements_package_gate_body(state), encoding='utf-8')

    validate_requirements_acceptance_quality(gate, state)


def test_requirements_e2e_mapping_blocker_names_canonical_values_and_4_6_example(
    tmp_path: Path,
) -> None:
    state: dict = {
        'requestedOutcome': 'Classroom V0.4',
        'requirementsSurfaceClassification': {
            'product_ui': 'not_required',
            'web_system': 'not_required',
            'prototype_required': 'not_required',
            'visible_surfaces': [],
            'evidence_snippets': ['API-only path for this test fixture.'],
        },
    }
    body = (
        '# Requirements\n\n'
        '## Acceptance Criteria\n'
        '- AC-V04-001 [verification: integration]: API state is persisted.\n\n'
        '## Test Strategy\n'
        '- Playwright browser E2E review is required for the active classroom journey.\n\n'
        '## Journey Acceptance Matrix\n'
        '| Journey | Title | Status | Steps | AC | Verification Layer |\n'
        '| --- | --- | --- | --- | --- | --- |\n'
        '| J-V04-001 | Classroom happy path | 是 | Open course center -> inspect status | AC-V04-001 | real integration + DB assertion |\n'
    )
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(body, encoding='utf-8')

    with pytest.raises(ValueError) as exc_info:
        validate_requirements_acceptance_quality(gate, state)

    message = str(exc_info.value)
    assert 'Status=active' in message
    assert 'Verification Layer=e2e' in message
    assert '## 4.6' in message
    assert '| J-V04-001 |' in message


def test_requirements_auto_revision_routes_declares_e2e_mapping_blocker_to_scope() -> None:
    reason = (
        'requirements gate invalid: Requirements declares E2E/browser review but does not map it '
        'to an e2e AC or active e2e Journey; use Status=active, Verification Layer=e2e, '
        'and add ## 4.6 E2E 测试方法与前置依赖矩阵'
    )

    assert select_requirements_revision_stage(reason) == 'scope'


def test_false_flag_no_ui_detector_ignores_explicit_false_flag_rejection() -> None:
    content = (
        'UI / Prototype Basis:\n'
        '- 不能把 false flag 当作不需要 UI/原型的证据；'
        'currentUnitNeedsUiDesign=false 只是默认 controller state。\n'
        '- 独立依据是本版本为 API-only service，没有浏览器页面。\n'
    )

    assert requirements_surface_uses_false_flag_as_no_ui_basis(content) is False


def test_staged_requirements_preflight_accepts_explicit_backend_no_ui_basis(
    tmp_path: Path,
) -> None:
    state: dict = {
        'requestedOutcome': 'Pure API V1',
        'targetProjectContext': '纯 backend/API/CLI target，无浏览器页面、控制台或产品 UI；通过 REST API 响应审阅。',
    }
    for stage in ['scope', 'product_design', 'architecture', 'test_strategy']:
        body = _staged_checkpoint_body(stage) + (
            '\n## UI / Prototype Basis\n'
            '- 本版本是纯 backend/API/CLI target；没有浏览器页面、控制台、详情页或可见产品入口，因此不需要 UI 原型。\n'
        )
        path = _write_artifact(tmp_path, f'{stage}.md', body)
        mark_stage_artifact(state, stage, path)
    state['requirementsSurfaceClassification'] = classify_requirements_surface(state)
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(render_staged_requirements_package_gate_body(state), encoding='utf-8')

    validate_requirements_acceptance_quality(gate, state)


def test_staged_requirements_preflight_rejects_controller_perspective_for_target_product(
    tmp_path: Path,
) -> None:
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    spec_path = _classroom_v04_spec(tmp_path)
    product_path = tmp_path / 'product_design.md'
    product_path.write_text(
        '# Product Design Brief\n\n'
        '- Waygate staged package 操作者体验展示 checkpoint 进度模型、artifact 审阅体验和返工体验。\n',
        encoding='utf-8',
    )
    mark_stage_artifact(state, 'product_design', product_path)
    architecture_path = tmp_path / 'architecture.md'
    architecture_path.write_text(
        '# Technical Architecture Brief\n\n'
        '- controller orchestration 负责 state transition、runner contract 和 event log。\n',
        encoding='utf-8',
    )
    mark_stage_artifact(state, 'architecture', architecture_path)
    state.update({
        'requestedOutcome': 'Classroom V0.4',
        'requirementsSpec': {'path': str(spec_path), 'sourceType': 'waygate-markdown'},
    })
    state['requirementsSurfaceClassification'] = classify_requirements_surface(state)
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(render_staged_requirements_package_gate_body(state), encoding='utf-8')

    with pytest.raises(ValueError, match='target product perspective'):
        validate_requirements_acceptance_quality(gate, state)


def test_staged_requirements_annotation_ordering_final_assembly_run_once_preflights_before_annotation(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=False)
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-6-2',
        'currentUnitId': 'v0-6-2-u3-package-assembly-validation',
        'currentStep': 'REQUIREMENTS_PACKAGE_ASSEMBLE',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'V0.6.2',
        'feasibleOutcome': 'V0.6.2',
        'scopeApproved': True,
        'autoApprove': False,
        'humanGatesRequired': True,
        'requirementsAccepted': False,
        'unitPlanAccepted': False,
        'finalAcceptanceAccepted': False,
        'annotationAgents': {
            'requirements_annotation': {
                'enabled': True,
                'backend': 'codex',
                'command': 'python3',
                'args': ['-c', 'from pathlib import Path; Path(__import__("os").environ["WAYGATE_ANNOTATION_ARTIFACT"]).write_text("{\\"status\\":\\"completed\\",\\"role\\":\\"requirements_annotation\\",\\"human_language\\":\\"zh-CN\\",\\"summary\\":\\"已完成\\",\\"issues\\":[]}\\n")'],
                'artifact_path': 'requirements-draft/requirements-annotations.json',
                'timeout_seconds': 5,
            }
        },
        'units': [{'id': 'v0-6-2-u3-package-assembly-validation', 'passes': False}],
        'objectiveCoverage': [
            {
                'objective': 'Complete V0.6.2 development acceptance',
                'units': ['v0-6-2-u3-package-assembly-validation'],
                'status': 'partial',
            }
        ],
    })
    controller.init_state(state, force=True)

    result = controller.run_once()

    assert result['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    gate_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    assert gate_path.exists()
    events = [
        json.loads(line)['type']
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    assert events.index('requirements_package_final_assembled') < events.index('requirements_gate_preflight_completed')
    assert events.index('requirements_gate_preflight_completed') < events.index('annotation_pass_started')

    approve_gate_file(gate_path, actor='tester')
    result = controller.run_once()
    assert result['currentStep'] == 'UNIT_PLAN_DRAFT'
    events_after_approval = [
        json.loads(line)['type']
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    assert events_after_approval.count('annotation_pass_started') == 1


def test_staged_requirements_final_assembly_generates_prototype_review_bundle(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=False)
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-6-2',
        'currentUnitId': 'v0-6-2-u3-package-assembly-validation',
        'currentStep': 'REQUIREMENTS_PACKAGE_ASSEMBLE',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'V0.6.2',
        'feasibleOutcome': 'V0.6.2',
        'scopeApproved': True,
        'autoApprove': False,
        'humanGatesRequired': True,
        'requirementsAccepted': False,
        'unitPlanAccepted': False,
        'finalAcceptanceAccepted': False,
        'units': [{'id': 'v0-6-2-u3-package-assembly-validation', 'passes': False}],
        'objectiveCoverage': [
            {
                'objective': 'Complete V0.6.2 development acceptance',
                'units': ['v0-6-2-u3-package-assembly-validation'],
                'status': 'partial',
            }
        ],
    })
    controller.init_state(state, force=True)
    draft_dir = state_dir / 'artifacts' / 'requirements-draft'
    prototype_dir = draft_dir / 'prototypes' / 'teacher-dashboard'
    prototype_dir.mkdir(parents=True)
    (prototype_dir / 'index.html').write_text(
        '<!doctype html><button>Open class</button>\n',
        encoding='utf-8',
    )
    (draft_dir / 'prototype-manifest.json').write_text(
        json.dumps(
            {
                'prototypes': [
                    {
                        'id': 'teacher-dashboard',
                        'type': 'html',
                        'path': 'prototypes/teacher-dashboard/index.html',
                        'title': 'Teacher dashboard clickable prototype',
                        'linked_acceptance_criteria': ['AC-07'],
                        'linked_journeys': ['J-01'],
                        'page_states': ['Dashboard', 'Course detail'],
                        'click_path': ['Open dashboard', 'Click course card'],
                        'implementation_targets': [{'kind': 'route', 'path': '/teacher/dashboard'}],
                    }
                ]
            }
        ),
        encoding='utf-8',
    )

    result = controller.run_once()

    assert result['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert (draft_dir / 'plannotator-review.html').exists()
    assert (draft_dir / 'prototype-review-manifest.json').exists()
    review_manifest = json.loads((draft_dir / 'prototype-review-manifest.json').read_text(encoding='utf-8'))
    assert review_manifest['approval_gate_path'] == str(state_dir / 'approvals' / 'requirements-and-acceptance.md')
    assert review_manifest['prototypes'][0]['review_href'] == 'prototypes/teacher-dashboard/index.html'
    events = [
        json.loads(line)['type']
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    assert 'prototype_review_bundle_generated' in events


def test_requirements_revision_staged_route_rewinds_to_scope_and_stales_downstream(tmp_path: Path) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-6-2',
        'currentUnitId': 'v0-6-2-u3-package-assembly-validation',
        'currentStep': 'PLAN_APPROVED',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'V0.6.2',
        'feasibleOutcome': 'V0.6.2',
        'scopeApproved': True,
        'requirementsAccepted': True,
        'requirementsAcceptedHash': 'sha256:req',
        'requirementsAcceptedBy': 'tester',
        'unitPlanAccepted': True,
        'unitPlanAcceptedHash': 'sha256:unit',
        'unitPlanAcceptedBy': 'tester',
        'unitPlanDraftGenerated': True,
        'units': [{'id': 'v0-6-2-u3-package-assembly-validation', 'passes': False}],
        'objectiveCoverage': [
            {
                'objective': 'Complete V0.6.2 development acceptance',
                'units': ['v0-6-2-u3-package-assembly-validation'],
                'status': 'partial',
            }
        ],
    })
    controller.init_state(state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    write_gate_file(
        approvals_dir / 'requirements-and-acceptance.md',
        render_staged_requirements_package_gate_body(state),
    )
    write_gate_file(approvals_dir / 'unit-plan.md', '# Unit Plan\n')

    controller.revise_human_gate('requirements', reason='scope needs one more journey')

    revised = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert revised['currentStep'] == 'REQUIREMENTS_SCOPE_DRAFT'
    assert revised['requirementsAccepted'] is False
    assert revised['unitPlanAccepted'] is False
    assert 'scope needs one more journey' in revised['requirementsRevisionFeedback']
    artifacts = revised['requirementsPackage']['artifacts']
    assert artifacts['scope']['status'] == 'stale'
    assert artifacts['product_design']['status'] == 'stale'
    assert artifacts['architecture']['status'] == 'stale'
    assert artifacts['test_strategy']['status'] == 'stale'
    assert artifacts['final_gate']['status'] == 'stale'


def test_requirements_revision_staged_routes_product_surface_feedback_to_product_design(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-4',
        'currentUnitId': 'target-v0-4',
        'currentStep': 'PLAN_APPROVED',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'Classroom V0.4',
        'scopeApproved': True,
        'requirementsAccepted': True,
        'unitPlanAccepted': True,
        'units': [{'id': 'target-v0-4', 'passes': False}],
    })
    controller.init_state(state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    write_gate_file(
        approvals_dir / 'requirements-and-acceptance.md',
        render_staged_requirements_package_gate_body(state),
    )
    write_gate_file(approvals_dir / 'unit-plan.md', '# Unit Plan\n')

    controller.revise_human_gate('requirements', reason='产品原型呢？没有 UI 怎么看生成课程。')

    revised = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert revised['currentStep'] == 'REQUIREMENTS_PRODUCT_DESIGN_BRIEF'
    assert revised['nextAllowedActions'] == ['run_requirements_product_design_brief']
    artifacts = revised['requirementsPackage']['artifacts']
    assert artifacts['scope']['status'] == 'complete'
    assert artifacts['product_design']['status'] == 'stale'
    assert artifacts['architecture']['status'] == 'stale'
    assert artifacts['test_strategy']['status'] == 'stale'
    assert artifacts['final_gate']['status'] == 'stale'


def test_requirements_revision_staged_routes_combined_ao_e2e_prototype_preflight_to_scope(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-4',
        'currentUnitId': 'target-v0-4',
        'currentStep': 'PLAN_APPROVED',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'Classroom V0.4',
        'scopeApproved': True,
        'requirementsAccepted': True,
        'unitPlanAccepted': True,
        'units': [{'id': 'target-v0-4', 'passes': False}],
    })
    controller.init_state(state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    write_gate_file(
        approvals_dir / 'requirements-and-acceptance.md',
        render_staged_requirements_package_gate_body(state),
    )
    write_gate_file(approvals_dir / 'unit-plan.md', '# Unit Plan\n')

    controller.revise_human_gate(
        'requirements',
        reason=(
            'requirements gate invalid: missing Acceptance Obligation requirements mapping: AO-006, AO-007; '
            'E2E review is not mapped to an active E2E Journey or AC; '
            'UI/Web contract also requires artifacts/requirements-draft/prototype-manifest.json'
        ),
    )

    revised = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert revised['currentStep'] == 'REQUIREMENTS_SCOPE_DRAFT'
    assert revised['nextAllowedActions'] == ['run_requirements_scope_drafter']
    artifacts = revised['requirementsPackage']['artifacts']
    assert artifacts['scope']['status'] == 'stale'
    assert artifacts['product_design']['status'] == 'stale'
    assert artifacts['architecture']['status'] == 'stale'
    assert artifacts['test_strategy']['status'] == 'stale'
    assert artifacts['final_gate']['status'] == 'stale'


def test_requirements_revision_staged_routes_live_e2e_mapping_reason_to_scope(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-4',
        'currentUnitId': 'target-v0-4',
        'currentStep': 'PLAN_APPROVED',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'Classroom V0.4',
        'scopeApproved': True,
        'requirementsAccepted': True,
        'unitPlanAccepted': True,
        'units': [{'id': 'target-v0-4', 'passes': False}],
    })
    controller.init_state(state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    write_gate_file(
        approvals_dir / 'requirements-and-acceptance.md',
        render_staged_requirements_package_gate_body(state),
    )
    write_gate_file(approvals_dir / 'unit-plan.md', '# Unit Plan\n')

    controller.revise_human_gate(
        'requirements',
        reason=(
            'requirements gate invalid: browser E2E review row does not map it to an e2e AC '
            'or active e2e Journey; prototype/Web page states also mention missing click path'
        ),
    )

    revised = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert revised['currentStep'] == 'REQUIREMENTS_SCOPE_DRAFT'
    assert revised['nextAllowedActions'] == ['run_requirements_scope_drafter']


def test_journey_contract_required_reason_routes_to_scope_with_minimal_header_feedback() -> None:
    reason = (
        'requirements gate invalid: journey contract required for e2e or closure acceptance; '
        'add a Journey Acceptance Matrix with active journey rows'
    )

    assert select_requirements_revision_stage(reason) == 'scope'
    assert requirements_auto_revision_semantic_key(reason) == 'scope:journey_contract_required'

    feedback = rrc_controller_module._requirements_controller_validation_revision_feedback(
        reason=reason,
        stage='scope',
        reason_key='scope:journey_contract_required',
    )

    assert 'Missing fields:' in feedback
    assert 'Journey Acceptance Matrix' in feedback
    assert '| Journey | Title | Status | Steps | AC | Verification Layer |' in feedback


def test_conflicting_journey_status_reason_routes_to_scope_with_status_feedback() -> None:
    reason = (
        "requirements gate invalid: staged requirements package conflicting Journey status "
        "for J-V062E-004: ['active', 'rejected']"
    )

    assert select_requirements_revision_stage(reason) == 'scope'
    assert requirements_auto_revision_semantic_key(reason) == 'scope:journey_status_conflict'

    feedback = rrc_controller_module._requirements_controller_validation_revision_feedback(
        reason=reason,
        stage='scope',
        reason_key='scope:journey_status_conflict',
    )

    assert 'Journey Status' in feedback
    assert 'Status column' in feedback
    assert 'maps each E2E/Web/prototype review obligation' not in feedback
    assert 'E2E mapping' not in feedback


def test_requirements_revision_staged_routes_unknown_ac_prototype_reason_to_scope(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-4',
        'currentUnitId': 'target-v0-4',
        'currentStep': 'PLAN_APPROVED',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'Classroom V0.4',
        'scopeApproved': True,
        'requirementsAccepted': True,
        'unitPlanAccepted': True,
        'units': [{'id': 'target-v0-4', 'passes': False}],
    })
    controller.init_state(state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    write_gate_file(
        approvals_dir / 'requirements-and-acceptance.md',
        render_staged_requirements_package_gate_body(state),
    )
    write_gate_file(approvals_dir / 'unit-plan.md', '# Unit Plan\n')

    controller.revise_human_gate(
        'requirements',
        reason=(
            'invalid prototype manifest: prototypes[0].linked_acs contains unknown '
            'acceptance criteria: AC-V04-001'
        ),
    )

    revised = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert revised['currentStep'] == 'REQUIREMENTS_SCOPE_DRAFT'
    assert revised['nextAllowedActions'] == ['run_requirements_scope_drafter']


def test_requirements_revision_staged_routes_test_method_quality_to_test_strategy(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-4',
        'currentUnitId': 'target-v0-4',
        'currentStep': 'PLAN_APPROVED',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'Classroom V0.4',
        'scopeApproved': True,
        'requirementsAccepted': True,
        'unitPlanAccepted': True,
        'units': [{'id': 'target-v0-4', 'passes': False}],
    })
    controller.init_state(state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    write_gate_file(
        approvals_dir / 'requirements-and-acceptance.md',
        render_staged_requirements_package_gate_body(state),
    )
    write_gate_file(approvals_dir / 'unit-plan.md', '# Unit Plan\n')

    controller.revise_human_gate(
        'requirements',
        reason=(
            'E2E method quality issue: environment_kind is component_mock, mock policy allows '
            'core API stubs, fixture is missing, and expected assertions are too weak'
        ),
    )

    revised = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert revised['currentStep'] == 'REQUIREMENTS_TEST_STRATEGY_BRIEF'
    assert revised['nextAllowedActions'] == ['run_requirements_test_strategy_brief']


def test_requirements_revision_allowed_from_staged_stage_validation_blocker(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-4',
        'currentUnitId': 'target-v0-4',
        'currentStep': 'REQUIREMENTS_TEST_STRATEGY_BRIEF',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'blocked',
        'blockedReason': (
            'Test Strategy stage validation failed: J-V04-005 Requirements 4.6 '
            'Real Entrypoint must be a real route, URL, page, command, or service entrypoint'
        ),
        'blockedContext': {
            'category': 'requirements_stage_validation',
            'stage': 'test_strategy',
            'action': 'run_requirements_test_strategy_brief',
        },
        'requestedOutcome': 'Classroom V0.4',
        'scopeApproved': True,
        'requirementsAccepted': False,
        'unitPlanAccepted': False,
        'units': [{'id': 'target-v0-4', 'passes': False}],
    })
    controller.init_state(state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    write_gate_file(
        approvals_dir / 'requirements-and-acceptance.md',
        render_staged_requirements_package_gate_body(state),
    )

    controller.revise_human_gate(
        'requirements',
        reason=(
            'AC contract change: keep J-V04-005 as e2e but redefine it as local_real '
            'classroom API/service E2E; prototype artifact is auxiliary review only'
        ),
    )

    revised = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert revised['status'] == 'active'
    assert revised['currentStep'] == 'REQUIREMENTS_SCOPE_DRAFT'
    assert revised['nextAllowedActions'] == ['run_requirements_scope_drafter']
    assert 'AC contract change' in revised['requirementsRevisionFeedback']
    assert revised['requirementsPackage']['artifacts']['scope']['status'] == 'stale'


def test_requirements_revision_staged_routes_interaction_architecture_feedback_to_architecture(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, dry_run=True, auto_approve=True)
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-4',
        'currentUnitId': 'target-v0-4',
        'currentStep': 'PLAN_APPROVED',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'Classroom V0.4',
        'scopeApproved': True,
        'requirementsAccepted': True,
        'unitPlanAccepted': True,
        'units': [{'id': 'target-v0-4', 'passes': False}],
    })
    controller.init_state(state, force=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    write_gate_file(
        approvals_dir / 'requirements-and-acceptance.md',
        render_staged_requirements_package_gate_body(state),
    )
    write_gate_file(approvals_dir / 'unit-plan.md', '# Unit Plan\n')

    controller.revise_human_gate('requirements', reason='架构交互缺失，API、状态写入和数据流没有说明。')

    revised = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert revised['currentStep'] == 'REQUIREMENTS_TECH_ARCH_BRIEF'
    assert revised['nextAllowedActions'] == ['run_requirements_architecture_brief']
    artifacts = revised['requirementsPackage']['artifacts']
    assert artifacts['scope']['status'] == 'complete'
    assert artifacts['product_design']['status'] == 'complete'
    assert artifacts['architecture']['status'] == 'stale'
    assert artifacts['test_strategy']['status'] == 'stale'
    assert artifacts['final_gate']['status'] == 'stale'


def test_staged_requirements_auto_revision_returns_after_routing_to_product_design(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True)
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-6-2',
        'currentUnitId': 'v0-6-2-u3-package-assembly-validation',
        'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'V0.6.2',
        'feasibleOutcome': 'V0.6.2',
        'scopeApproved': True,
        'humanGatesRequired': True,
        'requirementsAccepted': False,
        'requirementsDraftGenerated': True,
        'agentRunner': 'tmux-codex',
        'agentCommand': 'codex',
        'tmuxTarget': '2.0',
        'units': [{'id': 'v0-6-2-u3-package-assembly-validation', 'passes': False}],
        'objectiveCoverage': [
            {
                'objective': 'Complete V0.6.2 development acceptance',
                'units': ['v0-6-2-u3-package-assembly-validation'],
                'status': 'partial',
            }
        ],
    })
    gate_path = approvals_dir / 'requirements-and-acceptance.md'
    write_gate_file(gate_path, render_staged_requirements_package_gate_body(state))
    mark_stage_artifact(state, 'final_gate', gate_path)
    controller.init_state(state, force=True)
    reason = 'requirements gate invalid: prototype manifest is required'
    monkeypatch.setattr(
        controller,
        '_requirements_gate_invalid_reason',
        lambda _state, _gate_path: reason,
    )

    revised = controller._auto_revise_invalid_requirements_draft(controller.store.load_state())

    assert revised['status'] == 'active'
    assert revised['currentStep'] == 'REQUIREMENTS_PRODUCT_DESIGN_BRIEF'
    assert revised['nextAllowedActions'] == ['run_requirements_product_design_brief']
    artifacts = revised['requirementsPackage']['artifacts']
    assert [artifacts[stage]['status'] for stage in STAGED_REQUIREMENTS_STEPS] == [
        'complete',
        'stale',
        'stale',
        'stale',
        'stale',
    ]
    events = [
        json.loads(line)['type']
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    assert events.count('requirements_draft_auto_revision_requested') == 1
    assert 'requirements_draft_auto_revision_blocked' not in events


def test_staged_requirements_auto_revision_routes_product_experience_from_controller_reason(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True)
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    scope_path = Path(state['requirementsPackage']['artifacts']['scope']['path'])
    scope_path.write_text(
        scope_path.read_text(encoding='utf-8')
        + (
            '\n## Historical Scope Warning\n'
            '- Old gate text says browser E2E review does not map to an active e2e Journey or e2e AC.\n'
        ),
        encoding='utf-8',
    )
    mark_stage_artifact(state, 'scope', scope_path)
    state.update({
        'task_id': 'target-v0-4',
        'currentUnitId': 'target-v0-4',
        'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'Classroom V0.4',
        'scopeApproved': True,
        'humanGatesRequired': True,
        'requirementsAccepted': False,
        'requirementsDraftGenerated': True,
        'agentRunner': 'tmux-codex',
        'agentCommand': 'codex',
        'tmuxTarget': '2.0',
        'units': [{'id': 'target-v0-4', 'passes': False}],
    })
    gate_path = approvals_dir / 'requirements-and-acceptance.md'
    write_gate_file(gate_path, render_staged_requirements_package_gate_body(state))
    mark_stage_artifact(state, 'final_gate', gate_path)
    controller.init_state(state, force=True)
    reason = (
        'requirements gate invalid: product_design:product_experience missing clickable webpage '
        'prototype evidence; missing artifact-local HTML path, page states, click path, and AC/Journey mapping'
    )
    monkeypatch.setattr(
        controller,
        '_requirements_gate_invalid_reason',
        lambda _state, _gate_path: reason,
    )

    revised = controller._auto_revise_invalid_requirements_draft(controller.store.load_state())

    assert revised['currentStep'] == 'REQUIREMENTS_PRODUCT_DESIGN_BRIEF'
    assert revised['nextAllowedActions'] == ['run_requirements_product_design_brief']
    assert 'Original reason: ' + reason in revised['requirementsRevisionFeedback']
    assert 'Routed stage: product_design' in revised['requirementsRevisionFeedback']
    assert 'page_states' in revised['requirementsRevisionFeedback']
    events = [
        json.loads(line)
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    routed = [event for event in events if event['type'] == 'requirements_staged_revision_routed'][-1]
    assert routed['payload']['stage'] == 'product_design'
    assert routed['payload']['reason_key'] == 'product_design:product_experience'
    assert routed['payload']['routing_source'] == 'controller_validation_error'


def test_drive_staged_requirements_auto_revision_routes_to_product_design_without_stale_final_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True)
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-6-2',
        'currentUnitId': 'v0-6-2-u3-package-assembly-validation',
        'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'V0.6.2',
        'feasibleOutcome': 'V0.6.2',
        'scopeApproved': True,
        'humanGatesRequired': True,
        'requirementsAccepted': False,
        'requirementsDraftGenerated': True,
        'agentRunner': 'tmux-codex',
        'agentCommand': 'codex',
        'tmuxTarget': '2.0',
        'units': [{'id': 'v0-6-2-u3-package-assembly-validation', 'passes': False}],
        'objectiveCoverage': [
            {
                'objective': 'Complete V0.6.2 development acceptance',
                'units': ['v0-6-2-u3-package-assembly-validation'],
                'status': 'partial',
            }
        ],
    })
    gate_path = approvals_dir / 'requirements-and-acceptance.md'
    write_gate_file(gate_path, render_staged_requirements_package_gate_body(state))
    mark_stage_artifact(state, 'final_gate', gate_path)
    controller.init_state(state, force=True)
    monkeypatch.setattr(
        controller,
        '_requirements_gate_invalid_reason',
        lambda _state, _gate_path: 'requirements gate invalid: prototype manifest is required',
    )
    output: list[str] = []

    result = controller.drive(
        input_func=lambda _prompt: (_ for _ in ()).throw(EOFError),
        output_func=output.append,
        timestamp_output=False,
        max_steps=0,
    )

    rendered = '\n'.join(output)
    assert '[人工确认] 需求与验收' not in rendered
    assert result['status'] == 'active'
    assert result['currentStep'] == 'REQUIREMENTS_PRODUCT_DESIGN_BRIEF'
    assert result['nextAllowedActions'] == ['run_requirements_product_design_brief']


def test_drive_staged_requirements_auto_revision_blocked_stops_without_human_gate_or_annotation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True)
    reason = (
        'requirements gate invalid: browser E2E review row does not map it to an e2e AC '
        'or active e2e Journey; prototype/Web page states mention missing click path'
    )
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-4',
        'currentUnitId': 'target-v0-4',
        'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'Classroom V0.4',
        'scopeApproved': True,
        'humanGatesRequired': True,
        'requirementsAccepted': False,
        'requirementsDraftGenerated': True,
        'agentRunner': 'tmux-codex',
        'agentCommand': 'codex',
        'tmuxTarget': '2.0',
        'requirementsAutoRevisionMax': 2,
        'annotationAgents': {
            'requirements_annotation': {
                'enabled': True,
                'backend': 'codex',
                'command': 'python3',
                'args': ['-c', 'raise SystemExit(9)'],
                'artifact_path': 'requirements-draft/requirements-annotations.json',
                'timeout_seconds': 5,
            }
        },
        'units': [{'id': 'target-v0-4', 'passes': False}],
    })
    gate_path = approvals_dir / 'requirements-and-acceptance.md'
    write_gate_file(gate_path, render_staged_requirements_package_gate_body(state))
    mark_stage_artifact(state, 'final_gate', gate_path)
    controller.init_state(state, force=True)
    monkeypatch.setattr(
        controller,
        '_requirements_gate_invalid_reason',
        lambda _state, _gate_path: reason,
    )

    def fake_tmux_reminder(_state: dict, gate: str) -> None:
        controller.store.append_event('human_review_tmux_reminder_sent', {
            'gate': gate,
            'tmux_target': '2.0',
        })

    monkeypatch.setattr(controller, '_send_human_review_tmux_reminder', fake_tmux_reminder)
    original_auto_revise = controller._auto_revise_invalid_requirements_draft
    primed_counter = False

    def auto_revise_with_existing_in_process_attempts(state_arg: dict) -> dict:
        nonlocal primed_counter
        if not primed_counter:
            primed_counter = True
            controller._requirements_auto_revision_last_reason_key = (
                requirements_auto_revision_semantic_key(reason)
            )
            controller._requirements_auto_revision_consecutive_count = 2
            controller._requirements_auto_revision_total_count = 2
        return original_auto_revise(state_arg)

    monkeypatch.setattr(
        controller,
        '_auto_revise_invalid_requirements_draft',
        auto_revise_with_existing_in_process_attempts,
    )
    output: list[str] = []

    result = controller.drive(
        input_func=lambda _prompt: (_ for _ in ()).throw(EOFError),
        output_func=output.append,
        timestamp_output=False,
        max_steps=0,
    )

    rendered = '\n'.join(output)
    assert result['status'] == 'blocked'
    assert '[人工确认] 需求与验收' not in rendered
    assert str(result['blockedReason']).startswith('requirements gate invalid after automatic revisions')
    assert '[阻塞]' in rendered
    assert 'waygate revise --gate requirements' in rendered
    events = [
        json.loads(line)['type']
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    assert 'requirements_draft_auto_revision_blocked' in events
    assert 'human_review_tmux_reminder_sent' not in events
    assert 'annotation_pass_started' not in events


def test_staged_requirements_auto_revision_ignores_stale_persisted_attempts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True)
    reason = (
        'requirements gate invalid: browser E2E review row does not map it to an e2e AC '
        'or active e2e Journey; prototype/Web page states mention missing click path'
    )
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-4',
        'currentUnitId': 'target-v0-4',
        'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'Classroom V0.4',
        'scopeApproved': True,
        'humanGatesRequired': True,
        'requirementsAccepted': False,
        'requirementsDraftGenerated': True,
        'agentRunner': 'tmux-codex',
        'agentCommand': 'codex',
        'tmuxTarget': '2.0',
        'requirementsAutoRevisionMax': 2,
        'requirementsAutoRevisionLastReasonKey': requirements_auto_revision_semantic_key(reason),
        'requirementsAutoRevisionConsecutiveCount': 2,
        'requirementsAutoRevisionTotalCount': 9,
        'units': [{'id': 'target-v0-4', 'passes': False}],
    })
    gate_path = approvals_dir / 'requirements-and-acceptance.md'
    write_gate_file(gate_path, render_staged_requirements_package_gate_body(state))
    mark_stage_artifact(state, 'final_gate', gate_path)
    controller.init_state(state, force=True)
    monkeypatch.setattr(
        controller,
        '_requirements_gate_invalid_reason',
        lambda _state, _gate_path: reason,
    )

    result = controller._auto_revise_invalid_requirements_draft(controller.store.load_state())

    assert result['status'] == 'active'
    assert result['currentStep'] == 'REQUIREMENTS_SCOPE_DRAFT'
    persisted = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert 'requirementsAutoRevisionLastReasonKey' not in persisted
    assert 'requirementsAutoRevisionConsecutiveCount' not in persisted
    assert 'requirementsAutoRevisionTotalCount' not in persisted
    events = [
        json.loads(line)
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    requested_events = [
        event for event in events if event['type'] == 'requirements_draft_auto_revision_requested'
    ]
    assert len(requested_events) == 1
    assert requested_events[0]['payload']['attempt'] == 1
    assert requested_events[0]['payload']['total_attempt'] == 1
    assert 'requirements_draft_auto_revision_blocked' not in [event['type'] for event in events]


def test_staged_requirements_auto_revision_blocks_same_reason_within_controller_instance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True)
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-4',
        'currentUnitId': 'target-v0-4',
        'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'Classroom V0.4',
        'scopeApproved': True,
        'humanGatesRequired': True,
        'requirementsAccepted': False,
        'requirementsDraftGenerated': True,
        'agentRunner': 'tmux-codex',
        'agentCommand': 'codex',
        'tmuxTarget': '2.0',
        'requirementsAutoRevisionMax': 2,
        'units': [{'id': 'target-v0-4', 'passes': False}],
    })
    gate_path = approvals_dir / 'requirements-and-acceptance.md'
    write_gate_file(gate_path, render_staged_requirements_package_gate_body(state))
    mark_stage_artifact(state, 'final_gate', gate_path)
    controller.init_state(state, force=True)
    reasons = iter([
        (
            'requirements gate invalid: browser E2E review row does not map it to an e2e AC '
            'or active e2e Journey; prototype/Web page states mention missing click path'
        ),
        (
            'requirements gate invalid: Web review is not mapped to an active e2e Journey or '
            'e2e AC; prototype manifest page state text changed'
        ),
        (
            'requirements gate invalid: E2E review does not map to active e2e journey or AC; '
            'prototype path wording changed again'
        ),
    ])
    monkeypatch.setattr(
        controller,
        '_requirements_gate_invalid_reason',
        lambda _state, _gate_path: next(reasons),
    )

    first = controller._auto_revise_invalid_requirements_draft(controller.store.load_state())
    assert first['currentStep'] == 'REQUIREMENTS_SCOPE_DRAFT'
    persisted = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert 'requirementsAutoRevisionLastReasonKey' not in persisted
    assert 'requirementsAutoRevisionConsecutiveCount' not in persisted
    assert 'requirementsAutoRevisionTotalCount' not in persisted

    first.update(_complete_checkpoint_artifacts_with_content(tmp_path))
    first['currentStep'] = 'WAITING_REQUIREMENTS_ACCEPTANCE'
    first['status'] = 'active'
    mark_stage_artifact(first, 'final_gate', gate_path)
    controller._save_state(first)

    second = controller._auto_revise_invalid_requirements_draft(controller.store.load_state())
    assert second['currentStep'] == 'REQUIREMENTS_SCOPE_DRAFT'
    persisted = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert 'requirementsAutoRevisionLastReasonKey' not in persisted
    assert 'requirementsAutoRevisionConsecutiveCount' not in persisted
    assert 'requirementsAutoRevisionTotalCount' not in persisted

    second.update(_complete_checkpoint_artifacts_with_content(tmp_path))
    second['currentStep'] = 'WAITING_REQUIREMENTS_ACCEPTANCE'
    second['status'] = 'active'
    mark_stage_artifact(second, 'final_gate', gate_path)
    controller._save_state(second)

    blocked = controller._auto_revise_invalid_requirements_draft(controller.store.load_state())
    assert blocked['status'] == 'blocked'
    assert blocked['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert 'requirementsAutoRevisionLastReasonKey' not in blocked
    assert 'requirementsAutoRevisionConsecutiveCount' not in blocked
    assert 'requirementsAutoRevisionTotalCount' not in blocked
    persisted = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert 'requirementsAutoRevisionLastReasonKey' not in persisted
    assert 'requirementsAutoRevisionConsecutiveCount' not in persisted
    assert 'requirementsAutoRevisionTotalCount' not in persisted
    events = [
        json.loads(line)
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    requested_events = [
        event for event in events if event['type'] == 'requirements_draft_auto_revision_requested'
    ]
    assert [event['payload']['attempt'] for event in requested_events] == [1, 2]
    assert [event['payload']['total_attempt'] for event in requested_events] == [1, 2]
    blocked_events = [event for event in events if event['type'] == 'requirements_draft_auto_revision_blocked']
    assert len(blocked_events) == 1
    assert blocked_events[0]['payload']['consecutive_attempts'] == 3
    assert blocked_events[0]['payload']['total_attempts'] == 2


def test_staged_requirements_manual_revise_clears_stale_auto_revision_budget(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True)
    reason = (
        'requirements gate invalid: browser E2E review row does not map it to an e2e AC '
        'or active e2e Journey; prototype/Web page states mention missing click path'
    )
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    state.update({
        'task_id': 'target-v0-4',
        'currentUnitId': 'target-v0-4',
        'currentStep': 'WAITING_REQUIREMENTS_ACCEPTANCE',
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'Classroom V0.4',
        'scopeApproved': True,
        'humanGatesRequired': True,
        'requirementsAccepted': False,
        'requirementsDraftGenerated': True,
        'agentRunner': 'tmux-codex',
        'agentCommand': 'codex',
        'tmuxTarget': '2.0',
        'requirementsAutoRevisionMax': 2,
        'requirementsAutoRevisionLastReasonKey': requirements_auto_revision_semantic_key(reason),
        'requirementsAutoRevisionConsecutiveCount': 2,
        'requirementsAutoRevisionTotalCount': 4,
        'units': [{'id': 'target-v0-4', 'passes': False}],
    })
    gate_path = approvals_dir / 'requirements-and-acceptance.md'
    write_gate_file(gate_path, render_staged_requirements_package_gate_body(state))
    mark_stage_artifact(state, 'final_gate', gate_path)
    controller.init_state(state, force=True)

    controller._revise_requirements_gate(
        controller_validation_only=False,
        change_reason='Human revised requirements after reviewing controller feedback.',
    )

    revised = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert revised['currentStep'] == 'REQUIREMENTS_SCOPE_DRAFT'
    assert 'requirementsAutoRevisionLastReasonKey' not in revised
    assert 'requirementsAutoRevisionConsecutiveCount' not in revised
    assert 'requirementsAutoRevisionTotalCount' not in revised

    revised.update(_complete_checkpoint_artifacts_with_content(tmp_path))
    revised['currentStep'] = 'WAITING_REQUIREMENTS_ACCEPTANCE'
    revised['status'] = 'active'
    mark_stage_artifact(revised, 'final_gate', gate_path)
    controller._save_state(revised)
    monkeypatch.setattr(
        controller,
        '_requirements_gate_invalid_reason',
        lambda _state, _gate_path: reason,
    )

    result = controller._auto_revise_invalid_requirements_draft(controller.store.load_state())

    assert result['status'] == 'active'
    assert result['currentStep'] == 'REQUIREMENTS_SCOPE_DRAFT'
    events = [
        json.loads(line)
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    ]
    requested_events = [
        event for event in events if event['type'] == 'requirements_draft_auto_revision_requested'
    ]
    assert len(requested_events) == 1
    assert requested_events[0]['payload']['attempt'] == 1
