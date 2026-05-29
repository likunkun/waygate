from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding='utf-8')


def test_v061_roadmaps_cover_docs_regression_scope() -> None:
    roadmap = _read('ROADMAP.md')
    roadmap_zh = _read('ROADMAP.zh-CN.md')

    for expected in [
        'OpenSpec',
        'Spec Kit',
        'gate ordering',
        'role-based annotation',
        'claude-code',
        'opencode',
        'codex',
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
        'claude-code',
        'opencode',
        'codex',
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
        'claude-code',
        'opencode',
        'codex',
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
    architecture_doc = _read('docs/architecture/staged-requirements-package-architecture.md')
    registry = _read('docs/README.md')
    roadmap = _read('ROADMAP.md')
    roadmap_zh = _read('ROADMAP.zh-CN.md')

    for expected in [
        'Staged Requirements Package',
        'Requirements Scope',
        'Product Design Brief',
        'Technical Architecture Brief',
        'Requirements Test Strategy Brief',
        'final human Requirements approval gate',
        'Infrastructure / Execution Context Matrix',
        'downstream invalidation',
        'requirements_annotation',
        'requirementsSurfaceClassification',
        'target product UX',
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
    ]:
        assert expected in architecture_doc

    assert 'docs/workflow/staged-requirements-package-policy.md' in registry
    assert 'docs/architecture/staged-requirements-package-architecture.md' in registry
    assert 'V0.6.2 - Staged Requirements Package' in roadmap
    assert 'V0.6.2a - Staged Requirements Target Product Perspective' in roadmap
    assert 'V0.6.3 - Strict Test Presence and Per-Role Runner Configuration' in roadmap
    assert 'Merge the original V0.6.2 Strict Test Presence scope into V0.6.3.' in roadmap
    assert 'V0.6.2 - Staged Requirements Package' in roadmap_zh
    assert 'V0.6.2a - Staged Requirements 目标产品视角修复' in roadmap_zh
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


def test_annotation_policy_docs_cover_visibility_and_revision_freshness() -> None:
    workflow_doc = _read('docs/workflow/external-spec-intake-and-annotation-policy.md')
    usage = _read('USAGE.md')
    usage_zh = _read('USAGE.zh-CN.md')

    for expected in [
        'controller-side subprocess',
        'not appear in the tmux builder pane',
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
    assert 'controller-side subprocess' in usage
    assert 'controller 侧 subprocess' in usage_zh
    assert '标注 Agent 开始' in usage_zh
    assert '标注 Agent 完成' in usage_zh
    assert 'Requirements 修订' in usage_zh
