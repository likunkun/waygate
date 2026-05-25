from __future__ import annotations

import hashlib
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
    'scope': 'Requirements Scope Checkpoint',
    'product_design': 'Product Design Brief',
    'architecture': 'Technical Architecture Brief',
    'test_strategy': 'Requirements Test Strategy Brief',
    'final_gate': 'Final Requirements Gate',
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
    'scope': '附录 A：Requirements Scope Checkpoint',
    'product_design': '附录 B：Product Design Brief',
    'architecture': '附录 C：Technical Architecture Brief',
    'test_strategy': '附录 D：Requirements Test Strategy Brief',
}


def staged_requirements_enabled(state: dict[str, Any]) -> bool:
    if state.get('stagedRequirementsEnabled') is True:
        return True

    package = state.get('requirementsPackage')
    if isinstance(package, dict) and package.get('version') == REQUIREMENTS_PACKAGE_VERSION:
        return True

    return state.get('currentStep') in STEP_TO_STAGE


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
