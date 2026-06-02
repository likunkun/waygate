from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding='utf-8')


def test_v062g_prototype_docs_script_emits_visual_evidence_markers() -> None:
    result = subprocess.run(
        ['bash', 'scripts/verify/v062g-prototype-and-docs.sh'],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    marker_values: dict[str, str] = {}
    visual_payload = None
    for line in result.stdout.splitlines():
        for marker in ('PROTOTYPE_SCREENSHOT:', 'PRODUCTION_SCREENSHOT:', 'INTERACTION_SCREENSHOT:'):
            if line.startswith(marker):
                marker_values[marker] = line[len(marker):].strip()
        if line.startswith('VISUAL_EVIDENCE:'):
            visual_payload = json.loads(line[len('VISUAL_EVIDENCE:'):].strip())

    assert set(marker_values) == {
        'PROTOTYPE_SCREENSHOT:',
        'PRODUCTION_SCREENSHOT:',
        'INTERACTION_SCREENSHOT:',
    }
    for path in marker_values.values():
        assert (ROOT / path).exists()
    assert visual_payload == {
        'viewport': 'artifact-review-1280x900',
        'entrypoint': 'controller module, artifact, state, and event surfaces',
        'action_path': [
            'inspect annotation runtime policy',
            'select Prompt Contract',
            'select Subprocess Runtime',
            'select Backend Migration',
            'select Deprecated Env Handling',
            'compare mapped controller targets',
        ],
        'fidelity_level': 'structural_interaction',
    }


def test_v061_roadmaps_cover_docs_regression_scope() -> None:
    roadmap = _read('ROADMAP.md')
    roadmap_zh = _read('ROADMAP.zh-CN.md')

    for expected in [
        'OpenSpec',
        'Spec Kit',
        'gate ordering',
        'role-based annotation',
        'opencode',
        'codex',
        'Legacy Waygate built-in Claude annotation configs migrate to OpenCode',
        'prompt contract',
        'flexible evidence',
        'docs/workflow/external-spec-intake-and-annotation-policy.md',
        'docs/architecture/external-spec-intake-and-annotation-architecture.md',
    ]:
        assert expected in roadmap

    for expected in [
        'OpenSpec',
        'Spec Kit',
        'gate 顺序',
        '按 role 可配置',
        'opencode',
        'codex',
        '旧的 Waygate 内置 Claude annotation 配置迁移到 OpenCode',
        '提示词合同',
        '灵活验收证据',
        'docs/workflow/external-spec-intake-and-annotation-policy.md',
        'docs/architecture/external-spec-intake-and-annotation-architecture.md',
    ]:
        assert expected in roadmap_zh


def test_v061_required_formal_docs_and_registry_exist() -> None:
    workflow_doc = _read('docs/workflow/external-spec-intake-and-annotation-policy.md')
    architecture_doc = _read('docs/architecture/external-spec-intake-and-annotation-architecture.md')
    registry = _read('docs/README.md')

    for expected in [
        'OpenSpec',
        'Spec Kit',
        'Gate Ordering',
        'requirements_annotation',
        'unit_plan_annotation',
        'final_acceptance_verification_assist',
        'opencode',
        'codex',
        'claude-code',
        'non-approval',
        'flexible evidence',
        'human_review_required',
        'production_readonly_gap',
        'runtime_dependency_gap',
        'verification_env_gap',
        'PRODUCTION_WEB_BASE_URL',
        'PRODUCTION_API_BASE_URL',
        'Docker Compose',
    ]:
        assert expected in workflow_doc

    for expected in [
        'spec_sources.py',
        'requirements_dialogue_brief.py',
        'annotation_agents.py',
        'rrc_real_runtime.py',
        'verification.json',
        'role-based annotation config',
        'prompt template registry',
        'Final Acceptance Evidence Matrix',
        'strict command rows',
        'descriptive command rows',
        'environment availability checklist',
    ]:
        assert expected in architecture_doc

    assert 'docs/workflow/external-spec-intake-and-annotation-policy.md' in registry
    assert 'docs/architecture/external-spec-intake-and-annotation-architecture.md' in registry


def test_staged_requirements_docs_and_roadmap_registry_exist() -> None:
    workflow_doc = _read('docs/workflow/staged-requirements-package-policy.md')
    handoff_doc = _read('docs/workflow/unit-continuity-handoff-policy.md')
    architecture_doc = _read('docs/architecture/staged-requirements-package-architecture.md')
    review_policy_doc = _read('docs/workflow/human-review-control-policy.md')
    review_architecture_doc = _read('docs/architecture/human-review-control-architecture.md')
    registry = _read('docs/README.md')
    roadmap = _read('ROADMAP.md')
    roadmap_zh = _read('ROADMAP.zh-CN.md')

    for expected in [
        'Staged Requirements Package',
        'Requirements Scope',
        'Product Design Brief',
        'Technical Architecture Brief',
        'Requirements Test Strategy Brief',
        '需求范围检查点',
        '产品设计简报',
        'waygate revise --gate requirements --checkpoint product-design',
        'final human Requirements approval gate',
        'Infrastructure / Execution Context Matrix',
        'downstream invalidation',
        'requirements_annotation',
        'requirementsSurfaceClassification',
        'target product UX',
        'unit_handoff',
        'human review control',
        'Approval Notes Non-Contract Context',
    ]:
        assert expected in workflow_doc

    for expected in [
        'workflow_controller/requirements_package.py',
        'workflow_controller/requirements_surface.py',
        'workflow_controller/prompts/requirements_package.py',
        'workflow_controller/steps/requirements_package.py',
        'workflow_controller/rrc_controller.py',
        'validate_staged_requirements_package_consistency',
        'Unit Plan prompt',
        'artifact path/hash/status',
        'requirementsSurfaceClassification',
        'Requirements checkpoint revise',
        'workflow_controller/unit_handoff.py',
        'handoff-evidence.json',
        'workflow_controller/approval_notes.py',
        'human_interrupt',
    ]:
        assert expected in architecture_doc

    for expected in [
        'Unit Continuity Gate',
        'depends_on',
        'handoff',
        'Handoff Matrix',
        'handoff-evidence.json',
        'blockedContext',
        'unit_handoff',
    ]:
        assert expected in handoff_doc

    assert 'docs/workflow/staged-requirements-package-policy.md' in registry
    assert 'docs/workflow/unit-continuity-handoff-policy.md' in registry
    assert 'docs/workflow/human-review-control-policy.md' in registry
    assert 'docs/architecture/staged-requirements-package-architecture.md' in registry
    assert 'docs/architecture/human-review-control-architecture.md' in registry
    assert 'V0.6.2f' in registry
    assert 'open-spec-package' in registry
    for expected in [
        'Approval Notes Non-Contract Context',
        'AO-001',
        'non-contract context',
        'approved gate body wins',
        'blockedContext.category=human_interrupt',
        'waygate approve --reason',
        'waygate revise',
        'legacy',
        'review-bundle/prototype conformance',
        'V0.6.3 Strict Test Presence',
    ]:
        assert expected in review_policy_doc
    for expected in [
        'workflow_controller/approval_notes.py',
        'workflow_controller/rrc_controller.py',
        'workflow_controller/prompts/unit_plan.py',
        'workflow_controller/prompts/builder.py',
        'gateApprovalNotes',
        'gateDraftMerge',
        'pendingGateReview.baseline_body_hash',
        'blockedContext.category=human_interrupt',
        'human_interrupt_recorded',
        'review-bundle',
    ]:
        assert expected in review_architecture_doc
    assert 'V0.6.2 - Staged Requirements Package' in roadmap
    assert 'V0.6.2a - Staged Requirements Target Product Perspective' in roadmap
    assert 'V0.6.2c - Chinese Checkpoint Names and Targeted Revise' in roadmap
    assert 'V0.6.2d - Unit Continuity Gate' in roadmap
    assert 'V0.6.2e - Requirements Package Directory Intake' in roadmap
    assert 'V0.6.2f - Human Review Control and Interruption Recovery' in roadmap
    assert 'V0.6.3 - Strict Test Presence and Per-Role Runner Configuration' in roadmap
    assert 'Merge the original V0.6.2 Strict Test Presence scope into V0.6.3.' in roadmap
    assert 'V0.6.2 - Staged Requirements Package' in roadmap_zh
    assert 'V0.6.2a - Staged Requirements 目标产品视角修复' in roadmap_zh
    assert 'V0.6.2c - 中文 Checkpoint 命名与定点 Revise' in roadmap_zh
    assert 'V0.6.2d - Unit Continuity Gate' in roadmap_zh
    assert 'V0.6.2e - Requirements Package Directory Intake' in roadmap_zh
    assert 'V0.6.2f - Human Review Control and Interruption Recovery' in roadmap_zh
    assert 'V0.6.3 - Strict Test Presence and Per-Role Runner Configuration' in roadmap_zh
    assert '原 V0.6.2 Strict Test Presence 范围并入 V0.6.3。' in roadmap_zh


def test_unit_plan_evidence_row_preflight_policy_doc_and_registry_exist() -> None:
    workflow_doc = _read('docs/workflow/unit-plan-evidence-row-preflight-policy.md')
    registry = _read('docs/README.md')

    for expected in [
        'exactly matches',
        'verification_commands',
        'verification_assist',
        'Manual evidence does not satisfy automated evidence-row preflight',
        'FINAL_WALKTHROUGH_PREPARE',
        'waygate revise --gate unit-plan',
        'preserves Requirements approval',
    ]:
        assert expected in workflow_doc

    assert 'docs/workflow/unit-plan-evidence-row-preflight-policy.md' in registry


def test_annotation_policy_docs_use_current_codex_cli_contract() -> None:
    workflow_doc = _read('docs/workflow/external-spec-intake-and-annotation-policy.md')
    usage = _read('USAGE.md')
    usage_zh = _read('USAGE.zh-CN.md')

    for text in (workflow_doc, usage, usage_zh):
        assert '--ask-for-approval' not in text

    assert (
        '"exec", "--sandbox", "workspace-write", "-o", "{artifact_path}"'
        in workflow_doc
    )
    assert 'annotation runtime blocker' in workflow_doc


def test_annotation_policy_docs_cover_subprocess_runtime_and_revision_freshness() -> None:
    workflow_doc = _read('docs/workflow/external-spec-intake-and-annotation-policy.md')
    usage = _read('USAGE.md')
    usage_zh = _read('USAGE.zh-CN.md')

    for expected in [
        'subprocess only',
        'WAYGATE_ANNOTATION_TMUX',
        'deprecated no-op',
        'opencode',
        'codex',
        'env key-only',
        '标注 Agent 开始',
        '标注 Agent 完成',
        '标注 Agent 失败',
        'Requirements revision',
        'gate_content_hash',
        'WAYGATE_ANNOTATION_REVIEW_BEGIN',
        'Annotation Agent 风险批注',
        'approval Markdown',
        'gate_body()',
    ]:
        assert expected in workflow_doc

    assert '[annotation]' not in workflow_doc
    assert '标注 Agent 开始' in usage
    assert '标注 Agent 完成' in usage
    assert '[annotation]' not in usage
    assert '[annotation]' not in usage_zh
    assert 'subprocess runtime' in usage
    assert 'deprecated no-op' in usage
    assert 'subprocess runtime' in usage_zh
    assert '废弃' in usage_zh
    assert '标注 Agent 开始' in usage_zh
    assert '标注 Agent 完成' in usage_zh
    assert 'Requirements 修订' in usage_zh
