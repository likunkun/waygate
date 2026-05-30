from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

REQUIREMENTS_PACKAGE_VERSION = 'v0.6.2-staged'

STAGED_REQUIREMENTS_STEPS = [
    'scope',
    'product_design',
    'architecture',
    'test_strategy',
    'final_gate',
]
CHECKPOINT_STAGES = STAGED_REQUIREMENTS_STEPS[:-1]
STAGE_LABELS = {
    'scope': '需求范围检查点 (Requirements Scope Checkpoint)',
    'product_design': '产品设计简报 (Product Design Brief)',
    'architecture': '技术架构简报 (Technical Architecture Brief)',
    'test_strategy': '需求测试策略简报 (Requirements Test Strategy Brief)',
    'final_gate': '最终需求确认门禁 (Final Requirements Gate)',
}

STAGE_TO_STEP = {
    'scope': 'REQUIREMENTS_SCOPE_DRAFT',
    'product_design': 'REQUIREMENTS_PRODUCT_DESIGN_BRIEF',
    'architecture': 'REQUIREMENTS_TECH_ARCH_BRIEF',
    'test_strategy': 'REQUIREMENTS_TEST_STRATEGY_BRIEF',
    'final_gate': 'REQUIREMENTS_PACKAGE_ASSEMBLE',
}
STEP_TO_STAGE = {step: stage for stage, step in STAGE_TO_STEP.items()}

STAGE_TO_ACTION = {
    'scope': 'run_requirements_scope_drafter',
    'product_design': 'run_requirements_product_design_brief',
    'architecture': 'run_requirements_architecture_brief',
    'test_strategy': 'run_requirements_test_strategy_brief',
    'final_gate': 'assemble_requirements_package',
}

STAGE_ARTIFACT_FILENAMES = {
    'scope': 'requirements-scope.md',
    'product_design': 'product-design-brief.md',
    'architecture': 'architecture-brief.md',
    'test_strategy': 'test-strategy-brief.md',
    'final_gate': 'requirements-and-acceptance.md',
}

STAGE_APPENDIX_TITLES = {
    'scope': '附录 A：需求范围检查点 (Requirements Scope Checkpoint)',
    'product_design': '附录 B：产品设计简报 (Product Design Brief)',
    'architecture': '附录 C：技术架构简报 (Technical Architecture Brief)',
    'test_strategy': '附录 D：需求测试策略简报 (Requirements Test Strategy Brief)',
}

CHECKPOINT_STAGE_ALIASES = {
    'scope': (
        'scope',
        'requirements-scope',
        'requirements_scope',
        'requirements scope',
        'requirements scope checkpoint',
        '需求范围',
        '需求范围检查点',
    ),
    'product_design': (
        'product-design',
        'product_design',
        'product design',
        'product design brief',
        '产品设计',
        '产品设计简报',
        '产品原型',
    ),
    'architecture': (
        'architecture',
        'technical-architecture',
        'technical_architecture',
        'technical architecture',
        'technical architecture brief',
        '技术架构',
        '技术架构简报',
        '架构',
    ),
    'test_strategy': (
        'test-strategy',
        'test_strategy',
        'test strategy',
        'requirements-test-strategy',
        'requirements test strategy',
        'requirements test strategy brief',
        '测试策略',
        '需求测试策略',
        '需求测试策略简报',
    ),
}


def staged_requirements_enabled(state: dict[str, Any]) -> bool:
    if state.get('stagedRequirementsEnabled') is True:
        return True

    package = state.get('requirementsPackage')
    if isinstance(package, dict) and package.get('version') == REQUIREMENTS_PACKAGE_VERSION:
        return True

    return state.get('currentStep') in STEP_TO_STAGE


def checkpoint_cli_name(stage: str) -> str:
    _validate_checkpoint_stage(stage)
    return stage.replace('_', '-')


def checkpoint_public_label(stage: str) -> str:
    _validate_stage(stage)
    return STAGE_LABELS[stage]


def normalize_requirements_checkpoint(value: str) -> str:
    normalized = _checkpoint_alias_key(value)
    for stage, aliases in CHECKPOINT_STAGE_ALIASES.items():
        if normalized in {_checkpoint_alias_key(alias) for alias in aliases}:
            return stage
    choices = ', '.join(checkpoint_cli_name(stage) for stage in CHECKPOINT_STAGES)
    raise ValueError(f'Unknown requirements checkpoint: {value}. Expected one of: {choices}')


def ensure_requirements_package(state: dict[str, Any]) -> dict[str, Any]:
    package = state.get('requirementsPackage')
    if not isinstance(package, dict):
        package = {}
        state['requirementsPackage'] = package

    package['version'] = REQUIREMENTS_PACKAGE_VERSION
    artifacts = package.get('artifacts')
    if not isinstance(artifacts, dict):
        package['artifacts'] = {}

    return package


def artifact_hash(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def mark_stage_artifact(state: dict[str, Any], stage: str, path: str | Path) -> dict[str, str]:
    _validate_stage(stage)
    package = ensure_requirements_package(state)
    artifacts = package['artifacts']
    artifact_path = Path(path)

    record = {
        'stage': stage,
        'path': str(artifact_path),
        'hash': artifact_hash(artifact_path),
        'status': 'complete',
    }
    artifacts[stage] = record
    return record


def invalidate_stage_and_downstream(
    state: dict[str, Any],
    stage: str,
    reason: str | None = None,
) -> None:
    _validate_stage(stage)
    package = ensure_requirements_package(state)
    artifacts = package['artifacts']
    start = STAGED_REQUIREMENTS_STEPS.index(stage)

    for stale_stage in STAGED_REQUIREMENTS_STEPS[start:]:
        record = artifacts.setdefault(stale_stage, {'stage': stale_stage})
        record['stage'] = stale_stage
        record['status'] = 'stale'
        if reason is None:
            record.pop('stale_reason', None)
        else:
            record['stale_reason'] = reason


def package_artifacts_complete(state: dict[str, Any]) -> bool:
    package = state.get('requirementsPackage')
    if not isinstance(package, dict):
        return False
    if package.get('version') != REQUIREMENTS_PACKAGE_VERSION:
        return False

    artifacts = package.get('artifacts')
    if not isinstance(artifacts, dict):
        return False

    for stage in CHECKPOINT_STAGES:
        record = artifacts.get(stage)
        if not isinstance(record, dict):
            return False
        if record.get('status') != 'complete':
            return False

        path = record.get('path')
        expected_hash = record.get('hash')
        if not isinstance(path, str) or not isinstance(expected_hash, str):
            return False

        try:
            if artifact_hash(path) != expected_hash:
                return False
        except OSError:
            return False

    return True


def _validate_stage(stage: str) -> None:
    if stage not in STAGED_REQUIREMENTS_STEPS:
        raise ValueError(f'Unknown requirements package stage: {stage}')


def _validate_checkpoint_stage(stage: str) -> None:
    if stage not in CHECKPOINT_STAGES:
        raise ValueError(f'Unknown requirements checkpoint: {stage}')


def _checkpoint_alias_key(value: str) -> str:
    text = str(value or '').strip().lower()
    text = text.replace('（', '(').replace('）', ')')
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', text)
