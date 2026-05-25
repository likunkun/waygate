from __future__ import annotations

import json
from pathlib import Path

import pytest

from workflow_controller.requirements_package import (
    REQUIREMENTS_PACKAGE_VERSION,
    STAGED_REQUIREMENTS_STEPS,
    artifact_hash,
    invalidate_stage_and_downstream,
    mark_stage_artifact,
    package_artifacts_complete,
)
from workflow_controller.gates.generators import render_staged_requirements_package_gate_body
from workflow_controller.gates.parsers import approve_gate_file, write_gate_file
from workflow_controller.gates.validators import (
    validate_requirements_acceptance_quality,
    validate_staged_requirements_package_consistency,
)
from workflow_controller.prompts.requirements_package import (
    render_architecture_prompt,
    render_product_design_prompt,
    render_scope_prompt,
    render_test_strategy_prompt,
)
from workflow_controller.rrc_controller import RalphRefinerController
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


def _complete_checkpoint_artifacts_with_content(tmp_path: Path) -> dict:
    state: dict = {}
    for stage in ['scope', 'product_design', 'architecture', 'test_strategy']:
        path = _write_artifact(tmp_path, f'{stage}.md', _staged_checkpoint_body(stage))
        mark_stage_artifact(state, stage, path)
    return state


def test_staged_requirements_steps_are_ordered() -> None:
    assert REQUIREMENTS_PACKAGE_VERSION == 'v0.6.2-staged'
    assert STAGED_REQUIREMENTS_STEPS == [
        'scope',
        'product_design',
        'architecture',
        'test_strategy',
        'final_gate',
    ]


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
    assert '## 附录 A：Requirements Scope Checkpoint' in gate
    assert '## 附录 B：Product Design Brief' in gate
    assert '## 附录 C：Technical Architecture Brief' in gate
    assert '## 附录 D：Requirements Test Strategy Brief' in gate
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
            valid_gate.replace('## 附录 B：Product Design Brief', '## Removed Product Design Brief'),
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


def test_staged_validator_skips_legacy_4_9_but_legacy_still_requires_it(tmp_path: Path) -> None:
    state = _complete_checkpoint_artifacts_with_content(tmp_path)
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(render_staged_requirements_package_gate_body(state), encoding='utf-8')

    validate_requirements_acceptance_quality(gate, state)

    legacy_gate = tmp_path / 'legacy-requirements.md'
    legacy_gate.write_text(gate.read_text(encoding='utf-8'), encoding='utf-8')
    with pytest.raises(ValueError, match='4\\.9.*目标项目基础设施信息'):
        validate_requirements_acceptance_quality(legacy_gate, {'requestedOutcome': 'V1.0'})


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
