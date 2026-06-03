from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any

from workflow_controller.acceptance_obligations import (
    active_must_obligations,
    covered_obligation_ids_from_state_and_text,
)
from workflow_controller.evidence_policy import (
    MOCK_ENVIRONMENT_KINDS,
    REAL_E2E_ENVIRONMENT_KINDS,
    BROWSER_RUNTIME_FIELDS,
    case_visual_evidence_plan,
    case_allows_mock,
    case_declares_core_api_mock,
    case_declared_mocked_routes,
    case_environment_kind,
    case_requires_real_e2e,
    command_core_api_mock_routes,
    evidence_row_real_e2e_issue,
    fidelity_rank,
    normalize_fidelity_required,
)
from workflow_controller.document_deliverables import (
    final_document_deliverable_issues,
    parse_document_deliverables_from_unit_plan,
    unit_plan_declares_no_formal_doc_change,
    unit_plan_requires_document_deliverables,
)
from workflow_controller.gates.parsers import (
    ALLOWED_COVERAGE_STATUSES,
    CONTROLLER_STATE_PATCH_HEADING,
    _controller_state_patch,
    _find_controller_state_patch_heading,
    _markdown_section,
    _unit_test_cases,
    extract_unit_plan_state_patch,
    gate_body,
    write_gate_file,
)
from workflow_controller.prototype_review import (
    implementation_target_is_browser_route,
    prototype_required_target_contracts,
    prototype_test_case_covers_target,
    source_prototype_manifest_path_for_requirements,
    surface_contract_requires_browser_e2e,
    validate_prototype_review_manifest,
)
from workflow_controller.requirements_package import (
    CHECKPOINT_STAGES,
    REQUIREMENTS_PACKAGE_VERSION,
    STAGE_APPENDIX_TITLES,
    artifact_hash,
)
from workflow_controller.requirements_ids import (
    AC_ID_PATTERN,
    JOURNEY_ID_PATTERN,
    acceptance_criterion_ids_in_text,
    journey_ids_in_text,
)
from workflow_controller.requirements_surface import (
    controller_perspective_issue,
    requirements_surface_declares_no_ui_basis,
    requirements_surface_explains_unknown,
    requirements_surface_is_unknown,
    requirements_surface_requires_product_ui,
    requirements_surface_requires_prototype,
    requirements_surface_requires_web_system,
    requirements_surface_uses_false_flag_as_no_ui_basis,
    state_targets_waygate_controller,
)
from workflow_controller.unit_handoff import (
    handoff_evidence_artifacts,
    handoff_human_summary,
    handoff_produces,
    handoff_ready_checks,
    handoff_requires,
    handoff_summary_is_vague,
    handoff_text_matches,
    ready_check_is_mapped,
    unit_depends_on,
    unit_handoff,
)


VERIFICATION_EVIDENCE_SCHEMA_VERSION = 'v0.3.5'
VERIFICATION_EVIDENCE_ROW_FIELDS = {
    'unit_id',
    'test_case_id',
    'acceptance_criterion',
    'acceptance_obligations',
    'layer',
    'command',
    'manual_evidence',
    'expected',
    'status',
    'result_index',
    'returncode',
    'artifact_refs',
    'golden_path',
    'environment_kind',
    'real_entrypoint',
    'uses_core_api_mock',
    'mocked_routes',
    'browser_console_errors',
    'page_errors',
    'request_failures',
    'screenshot_refs',
    'visual_evidence_refs',
}
DESCRIPTIVE_EVIDENCE_ROW_FIELDS = {
    'evidence_type',
    'description',
    'agent_assisted_judgement',
    'risk_annotations',
    'structured_evidence_refs',
    'human_review_required',
}
AGENT_ASSISTED_CASE_ROW_FIELDS = {
    'evidence_type',
    'description',
    'agent_assisted_judgement',
    'risk_annotations',
    'structured_evidence_refs',
    'human_review_required',
    'assist_artifact_path',
}
VERIFICATION_EVIDENCE_ROW_STATUSES = {
    'passed',
    'failed',
    'missing',
    'manual',
    'invalid',
    'blocked',
    'needs_human_review',
}


# ---------------------------------------------------------------------------
# Validators from rrc_validators.py (artifact validation)
# ---------------------------------------------------------------------------

def validate_required_artifacts(unit_dir: Path, filenames: list[str]) -> None:
    missing = [name for name in filenames if not (unit_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f'Missing required artifacts in {unit_dir}: {missing}')


def validate_review_verdict(review_path: Path) -> dict[str, Any]:
    review = _load_json(review_path)
    if 'passed' not in review:
        raise ValueError(f"Review verdict missing 'passed': {review_path}")
    return review


def validate_verification_verdict(verification_path: Path) -> dict[str, Any]:
    verification = _load_json(verification_path)
    if 'passed' not in verification:
        raise ValueError(f"Verification verdict missing 'passed': {verification_path}")
    return verification


def validate_verification_evidence_schema(verification_path: Path) -> dict[str, Any]:
    verification = _load_json(verification_path)
    if verification.get('evidence_schema_version') != VERIFICATION_EVIDENCE_SCHEMA_VERSION:
        raise ValueError(f'Verification evidence schema missing evidence_schema_version: {verification_path}')

    rows = verification.get('evidence_rows')
    if not isinstance(rows, list):
        raise ValueError(f'Verification evidence_rows must be a list: {verification_path}')

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f'Verification evidence row {index} must be an object: {verification_path}')
        missing_fields = sorted(VERIFICATION_EVIDENCE_ROW_FIELDS - set(row))
        if missing_fields:
            raise ValueError(
                f'Verification evidence row {index} missing field(s) {missing_fields}: {verification_path}'
            )
        if row.get('status') not in VERIFICATION_EVIDENCE_ROW_STATUSES:
            raise ValueError(f'Verification evidence row {index} has invalid status: {verification_path}')
        if not isinstance(row.get('acceptance_obligations'), list):
            raise ValueError(f'Verification evidence row {index} acceptance_obligations must be a list: {verification_path}')
        if not isinstance(row.get('artifact_refs'), list):
            raise ValueError(f'Verification evidence row {index} artifact_refs must be a list: {verification_path}')
        if not isinstance(row.get('golden_path'), bool):
            raise ValueError(f'Verification evidence row {index} golden_path must be a boolean: {verification_path}')
        if not isinstance(row.get('environment_kind'), str):
            raise ValueError(f'Verification evidence row {index} environment_kind must be a string: {verification_path}')
        if row.get('real_entrypoint') is not None and not isinstance(row.get('real_entrypoint'), str):
            raise ValueError(f'Verification evidence row {index} real_entrypoint must be a string or null: {verification_path}')
        if not isinstance(row.get('uses_core_api_mock'), bool):
            raise ValueError(f'Verification evidence row {index} uses_core_api_mock must be a boolean: {verification_path}')
        for runtime_field in ('mocked_routes', *BROWSER_RUNTIME_FIELDS):
            if not isinstance(row.get(runtime_field), list):
                raise ValueError(
                    f'Verification evidence row {index} {runtime_field} must be a list: {verification_path}'
                )
        if not isinstance(row.get('visual_evidence_refs'), dict):
            raise ValueError(
                f'Verification evidence row {index} visual_evidence_refs must be an object: {verification_path}'
            )
        if _is_agent_assisted_case_row(row):
            missing_agent_fields = sorted(AGENT_ASSISTED_CASE_ROW_FIELDS - set(row))
            if missing_agent_fields:
                raise ValueError(
                    f'Verification agent-assisted evidence row {index} missing field(s) '
                    f'{missing_agent_fields}: {verification_path}'
                )
            if row.get('evidence_type') != 'agent_assisted_case':
                raise ValueError(f'Verification agent-assisted evidence row {index} has invalid evidence_type: {verification_path}')
            _validate_agent_assisted_fields(row, index, verification_path, row_label='agent-assisted')
            if row.get('assist_artifact_path') is not None and not isinstance(row.get('assist_artifact_path'), str):
                raise ValueError(
                    f'Verification agent-assisted evidence row {index} assist_artifact_path must be a string or null: {verification_path}'
                )
        elif _is_descriptive_evidence_row(row):
            missing_descriptive_fields = sorted(DESCRIPTIVE_EVIDENCE_ROW_FIELDS - set(row))
            if missing_descriptive_fields:
                raise ValueError(
                    f'Verification descriptive evidence row {index} missing field(s) '
                    f'{missing_descriptive_fields}: {verification_path}'
                )
            if row.get('evidence_type') != 'descriptive_command':
                raise ValueError(f'Verification descriptive evidence row {index} has invalid evidence_type: {verification_path}')
            _validate_agent_assisted_fields(row, index, verification_path, row_label='descriptive')
    return verification


def _is_descriptive_evidence_row(row: dict[str, Any]) -> bool:
    if row.get('evidence_type') == 'agent_assisted_case':
        return False
    if row.get('evidence_type') == 'descriptive_command':
        return True
    return any(field in row for field in DESCRIPTIVE_EVIDENCE_ROW_FIELDS)


def _is_agent_assisted_case_row(row: dict[str, Any]) -> bool:
    return row.get('evidence_type') == 'agent_assisted_case'


def _validate_agent_assisted_fields(row: dict[str, Any], index: int, verification_path: Path, *, row_label: str) -> None:
    prefix = f'Verification {row_label} evidence row {index}'
    if not isinstance(row.get('description'), str):
        raise ValueError(f'{prefix} description must be a string: {verification_path}')
    if not isinstance(row.get('agent_assisted_judgement'), dict):
        raise ValueError(f'{prefix} agent_assisted_judgement must be an object: {verification_path}')
    if not isinstance(row.get('risk_annotations'), list):
        raise ValueError(f'{prefix} risk_annotations must be a list: {verification_path}')
    if not isinstance(row.get('structured_evidence_refs'), list):
        raise ValueError(f'{prefix} structured_evidence_refs must be a list: {verification_path}')
    if not isinstance(row.get('human_review_required'), bool):
        raise ValueError(f'{prefix} human_review_required must be a boolean: {verification_path}')


def validate_simplifier_result(result_path: Path) -> dict[str, Any]:
    result = _load_json(result_path)
    if not isinstance(result, dict):
        raise ValueError(f'Simplifier result must be a JSON object: {result_path}')

    status = result.get('status')
    if status not in {'ok', 'changes_requested', 'failed', 'skipped'}:
        raise ValueError(f'Simplifier result has invalid status: {result_path}')

    mode = result.get('mode')
    if mode not in {'disabled', 'dry-run', 'role-runner', 'no-workspace'}:
        raise ValueError(f'Simplifier result has invalid mode: {result_path}')

    if not isinstance(result.get('changed_files'), list):
        raise ValueError(f'Simplifier result changed_files must be a list: {result_path}')
    if not isinstance(result.get('findings'), list):
        raise ValueError(f'Simplifier result findings must be a list: {result_path}')
    if not isinstance(result.get('runner_metadata'), dict):
        raise ValueError(f'Simplifier result runner_metadata must be an object: {result_path}')
    if 'generated_at' not in result:
        raise ValueError(f'Simplifier result missing generated_at: {result_path}')
    return result


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


# ---------------------------------------------------------------------------
# Unit plan validators (from rrc_human_gates.py)
# ---------------------------------------------------------------------------

def validate_unit_plan_test_strategy(
    requirements_path: Path,
    unit_plan_path: Path,
    state: dict[str, Any],
) -> None:
    if not requirements_path.exists():
        return
    required_layers = _required_test_layers(requirements_path.read_text(encoding='utf-8'))
    if not required_layers:
        return

    unit_plan_content = gate_body(unit_plan_path.read_text(encoding='utf-8')).lower()
    unit_state_content = json.dumps({
        'units': state.get('units') or [],
        'objectiveCoverage': state.get('objectiveCoverage') or [],
    }, ensure_ascii=False).lower()
    haystack = f'{unit_plan_content}\n{unit_state_content}'
    missing = [
        layer
        for layer in sorted(required_layers)
        if not _test_layer_is_covered(layer, haystack)
    ]
    if missing:
        raise ValueError(
            'unit plan does not cover approved test strategy layer(s): '
            + ', '.join(missing)
        )


def validate_unit_plan_test_case_coverage(
    unit_plan_path: Path,
    state: dict[str, Any],
) -> None:
    if not unit_plan_path.exists():
        return
    content = gate_body(unit_plan_path.read_text(encoding='utf-8'))
    gaps: list[str] = []
    for unit in state.get('units') or []:
        if not isinstance(unit, dict) or bool(unit.get('passes')):
            continue
        unit_id = str(unit.get('id') or 'unknown-unit')
        commands = [str(command) for command in unit.get('verification_commands') or []]
        test_cases = _unit_test_cases(unit)
        if test_cases:
            continue
        if _unit_plan_body_has_test_case_matrix_entry(content, unit_id):
            continue
        if commands and all(_is_static_verification_command(command) for command in commands):
            gaps.append(
                f'unit {unit_id} has only static verification commands; add test_cases or Test Case Matrix evidence'
            )
    if gaps:
        raise ValueError('unit plan test case coverage is incomplete: ' + '; '.join(gaps))


def validate_unit_plan_acceptance_obligation_coverage(
    unit_plan_path: Path,
    state: dict[str, Any],
) -> None:
    if not unit_plan_path.exists():
        return
    obligations = active_must_obligations(state)
    if not obligations:
        return
    content = gate_body(unit_plan_path.read_text(encoding='utf-8'))
    covered = covered_obligation_ids_from_state_and_text(state, content)
    missing = [
        obligation
        for obligation in obligations
        if str(obligation.get('id') or '').upper() not in covered
    ]
    if missing:
        summary = ', '.join(
            f"{obligation.get('id')} {obligation.get('title', '')}".strip()
            for obligation in missing
        )
        raise ValueError('missing Acceptance Obligation coverage: ' + summary)


def validate_unit_plan_design_architecture_traceability(
    requirements_path: Path,
    unit_plan_path: Path,
    state: dict[str, Any],
) -> None:
    if not requirements_path.exists() or not unit_plan_path.exists():
        return
    requirements_content = gate_body(requirements_path.read_text(encoding='utf-8'))
    required_trace = _requirements_design_architecture_traceability(requirements_content)
    if not required_trace:
        return

    missing: list[str] = []
    for unit in state.get('units') or []:
        if not isinstance(unit, dict) or bool(unit.get('passes')):
            continue
        unit_id = str(unit.get('id') or 'unknown-unit')
        for case in _unit_test_cases(unit):
            if not isinstance(case, dict):
                continue
            ac_ids = _requirements_ac_ids_in_text(
                str(case.get('acceptance_criterion') or case.get('acceptanceCriterion') or '')
            )
            for ac_id in sorted(ac_ids & set(required_trace)):
                required = required_trace[ac_id]
                product_refs = _trace_refs_from_case(
                    case,
                    'product_design_refs',
                    'productDesignRefs',
                    'product_design_ref',
                    'productDesignRef',
                    'design_refs',
                    'designRefs',
                )
                architecture_refs = _trace_refs_from_case(
                    case,
                    'technical_architecture_refs',
                    'technicalArchitectureRefs',
                    'technical_architecture_ref',
                    'technicalArchitectureRef',
                    'architecture_refs',
                    'architectureRefs',
                )
                product_refs_ok = required['product_design_refs'].issubset(product_refs)
                architecture_refs_ok = required['technical_architecture_refs'].issubset(architecture_refs)
                if not product_refs_ok or not architecture_refs_ok:
                    missing.append(
                        f'unit {unit_id} test case {case.get("id", "unknown-test")} for {ac_id} '
                        'missing design/architecture traceability'
                    )
    if missing:
        raise ValueError('unit plan design/architecture traceability is incomplete: ' + '; '.join(missing))


def validate_unit_plan_prototype_conformance(
    requirements_path: Path,
    unit_plan_path: Path,
    state: dict[str, Any],
) -> None:
    del unit_plan_path
    if not requirements_path.exists():
        return
    manifest_path, artifacts_dir = source_prototype_manifest_path_for_requirements(requirements_path)
    if not manifest_path.exists():
        return
    try:
        normalized = validate_prototype_review_manifest(
            manifest_path,
            requirements_path=requirements_path,
            artifacts_dir=artifacts_dir,
            require_implementation_targets=True,
        )
    except ValueError as exc:
        raise ValueError('unit plan prototype conformance is incomplete: ' + str(exc)) from exc

    issues: list[str] = []
    test_cases = [
        case
        for unit in state.get('units') or []
        if isinstance(unit, dict)
        for case in _unit_test_cases(unit)
        if isinstance(case, dict)
    ]
    for contract in prototype_required_target_contracts(normalized):
        prototype_id = str(contract.get('prototype_id') or '').strip()
        surface_id = str(contract.get('surface_id') or '').strip()
        target = contract.get('target') if isinstance(contract.get('target'), dict) else {}
        matched_cases = [
            case for case in test_cases
            if prototype_test_case_covers_target(case, prototype_id, target, surface_id=surface_id)
        ]
        valid_cases = [
            case for case in matched_cases
            if not _prototype_conformance_case_issue(case, target, contract)
        ]
        if valid_cases:
            continue
        contract_label = _prototype_contract_label(contract)
        if not matched_cases:
            issues.append(
                f'{contract_label} missing production UI conformance test; '
                'add test_cases[] metadata prototype_conformance, prototype_surfaces, production_targets, and user_steps'
            )
            continue
        case_summaries = ', '.join(
            f"{case.get('id') or 'unknown-test'} ({_prototype_conformance_case_issue(case, target, contract)})"
            for case in matched_cases
        )
        issues.append(
            f'{contract_label} has no valid production UI conformance test: '
            + case_summaries
        )
    if issues:
        raise ValueError('unit plan prototype conformance is incomplete: ' + '; '.join(issues))


def validate_unit_plan_document_deliverables(
    unit_plan_path: Path,
    state: dict[str, Any],
) -> None:
    if not unit_plan_path.exists():
        return
    content = gate_body(unit_plan_path.read_text(encoding='utf-8'))
    deliverables = parse_document_deliverables_from_unit_plan(unit_plan_path)
    if unit_plan_requires_document_deliverables(state):
        if not deliverables and not unit_plan_declares_no_formal_doc_change(content):
            raise ValueError(
                'unit plan document deliverables are incomplete: add a Document Deliverables Matrix '
                'or explicitly declare 不需要正式文档变更 with a concrete reason'
            )

    issues: list[str] = []
    for row in deliverables:
        target_path = str(row.get('target_path') or '').strip()
        action = str(row.get('action') or '').strip()
        reason = str(row.get('reason') or '').strip()
        required = bool(row.get('required_for_acceptance'))
        if required and not target_path:
            issues.append('required document deliverable is missing Target Path')
        if required and any(marker in target_path.lower() for marker in ['待补', 'tbd', 'todo', '...']):
            issues.append(f'required document deliverable {target_path} must name a concrete docs path')
        if required and target_path and '不需要正式文档变更' in target_path:
            issues.append('no-formal-doc-change row cannot be Required For Acceptance=true')
        if required and not action:
            issues.append(f'required document deliverable {target_path} is missing Action')
        if not required and '不需要正式文档变更' in target_path and len(reason) < 8:
            issues.append('不需要正式文档变更 must include a concrete reason')
    if issues:
        raise ValueError('unit plan document deliverables are incomplete: ' + '; '.join(issues))


def validate_unit_plan_infrastructure_execution_context_matrix(
    unit_plan_path: Path,
    state: dict[str, Any],
) -> None:
    if not _staged_requirements_package_state(state):
        return
    if not unit_plan_path.exists():
        return
    content = gate_body(unit_plan_path.read_text(encoding='utf-8'))
    section = (
        _markdown_section(content, 'Infrastructure / Execution Context Matrix')
        or _markdown_section(content, 'Infrastructure / Execution Context')
        or _markdown_section(content, '执行上下文矩阵')
    )
    if not section.strip():
        raise ValueError(
            'Unit Plan missing `Infrastructure / Execution Context Matrix`; '
            'add repository, runtime, debugging, reference environment, documentation, architecture/interface, and dependencies'
        )
    normalized = _normalized_requirements_text(section)
    missing = [
        label
        for label, aliases in _REQUIREMENTS_INFRASTRUCTURE_CATEGORIES
        if not any(_normalized_requirements_text(alias) in normalized for alias in aliases)
    ]
    if missing:
        raise ValueError(
            'Unit Plan Infrastructure / Execution Context Matrix missing category: '
            + ', '.join(missing)
        )


def validate_final_document_deliverables(
    unit_plan_path: Path,
    state: dict[str, Any],
) -> None:
    if not unit_plan_path.exists():
        return
    issues = final_document_deliverable_issues(unit_plan_path, state)
    if issues:
        raise ValueError('document deliverables are incomplete: ' + '; '.join(issues))


def validate_requirements_acceptance_quality(
    requirements_path: Path,
    state: dict[str, Any],
) -> None:
    if not requirements_path.exists():
        return

    content = gate_body(requirements_path.read_text(encoding='utf-8'))
    ac_ids = _requirements_acceptance_criterion_ids(content)
    ac_layers = _requirements_acceptance_criterion_layers(content)
    missing_layers = [
        ac_id
        for ac_id in sorted(ac_ids)
        if ac_id not in ac_layers
    ]

    issues: list[str] = []
    if missing_layers:
        issues.append(
            ', '.join(f'{ac_id} missing verification layer' for ac_id in missing_layers)
            + '; add a non-placeholder verification layer such as unit, functional, integration, '
            + 'static, regression, prerequisite, e2e, or manual in the AC line or '
            + 'Requirements Traceability Matrix'
        )

    obligations = active_must_obligations(state)
    if obligations:
        trace = _requirements_obligation_traceability(content)
        missing_obligations = [
            obligation
            for obligation in obligations
            if str(obligation.get('id') or '').upper() not in trace
        ]
        if missing_obligations:
            summary = ', '.join(
                f"{obligation.get('id')} {obligation.get('title', '')}".strip()
                for obligation in missing_obligations
            )
            issues.append(
                'missing Acceptance Obligation requirements mapping: '
                + summary
                + '; map every active must AO to an AC, or mark it deferred, '
                + 'rejected, or out_of_scope with a reason'
            )

    if _requirements_has_design_architecture_matrix(content):
        design_architecture_trace = _requirements_design_architecture_traceability(content)
        missing_design_architecture = [
            ac_id
            for ac_id in sorted(ac_ids)
            if ac_id not in design_architecture_trace
            or not design_architecture_trace[ac_id]['product_design_refs']
            or not design_architecture_trace[ac_id]['technical_architecture_refs']
        ]
        if missing_design_architecture:
            issues.append(
                ', '.join(
                    f'{ac_id} missing design/architecture traceability'
                    for ac_id in missing_design_architecture
                )
                + '; add Product Design Ref and Technical Architecture Ref for every AC'
            )

    issues.extend(_requirements_e2e_review_matrix_issues(content, state))

    staged_package = _staged_requirements_package_state(state)
    if staged_package and state.get('requirementsSurfaceClassification') and not state_targets_waygate_controller(state):
        if (
            requirements_surface_is_unknown(state)
            and not requirements_surface_declares_no_ui_basis(content)
            and not requirements_surface_explains_unknown(content)
        ):
            issues.append(
                'requirementsSurfaceClassification is unknown; Scope/Product Design must explain whether '
                'target product UI/Web/prototype is required, or give explicit backend/API/CLI-only no-UI basis'
            )
        if requirements_surface_uses_false_flag_as_no_ui_basis(content):
            issues.append(
                'default currentUnitNeedsUiDesign/currentUnitIsWebSystem false flags cannot be used as no-UI basis; '
                'classify the target product surfaces from spec/context/human feedback'
            )

    prototype_contract_source = (
        _staged_requirements_appendices_content(content)
        if staged_package
        else content
    )
    prototype_contract_content = _requirements_content_without_e2e_review_section(
        _requirements_prototype_contract_content(prototype_contract_source)
    )
    content_declares_prototype_contract = _requirements_declares_prototype_contract(prototype_contract_content, state)
    needs_uiux_prototype = _requirements_need_uiux_prototype(state)
    needs_clickable_web_prototype = _requirements_need_clickable_web_prototype(state)
    declares_clickable_web_prototype = _requirements_declares_clickable_web_prototype_contract(
        prototype_contract_content,
        state,
    )
    prototype_manifest_required = (
        needs_uiux_prototype
        or needs_clickable_web_prototype
        or content_declares_prototype_contract
    )
    valid_prototype_manifest = False
    prototype_manifest_issue: str | None = None
    if prototype_manifest_required:
        manifest_path, artifacts_dir = source_prototype_manifest_path_for_requirements(requirements_path)
        if not manifest_path.exists():
            prototype_manifest_issue = (
                'UI/UX, Web, or prototype UI contract requires a valid prototype manifest before Requirements human confirmation; '
                f'write artifacts/requirements-draft/{manifest_path.name}'
            )
        else:
            try:
                validate_prototype_review_manifest(
                    manifest_path,
                    requirements_path=requirements_path,
                    artifacts_dir=artifacts_dir,
                    require_clickable=(
                        needs_clickable_web_prototype
                        or declares_clickable_web_prototype
                    ),
                    require_implementation_targets=True,
                )
                valid_prototype_manifest = True
            except ValueError as exc:
                prototype_manifest_issue = str(exc)

    if (
        needs_uiux_prototype
        and not valid_prototype_manifest
        and not _requirements_has_uiux_prototype_evidence(prototype_contract_content)
    ):
        issues.append(
            'UI/UX target requires prototype evidence before Requirements human confirmation; '
            'add prototype evidence or reviewable design evidence mapped to Product Design Ref'
        )

    if (
        needs_clickable_web_prototype
        and not valid_prototype_manifest
        and not _requirements_has_clickable_web_prototype_evidence(prototype_contract_content)
    ):
        issues.append(
            'Web system requires clickable webpage prototype evidence before Requirements human confirmation; '
            'record access method or URL/start command, page states, click path, and AC mapping'
        )

    if prototype_manifest_issue:
        issues.append(prototype_manifest_issue)

    if staged_package:
        issues.extend(_staged_requirements_package_consistency_issues(content, state))
        issues.extend(_staged_requirements_target_perspective_issues(state))
    elif _requirements_target_infrastructure_required(state):
        issues.extend(_requirements_target_infrastructure_issues(content))

    if issues:
        raise ValueError('; '.join(issues))


def validate_staged_requirements_package_consistency(
    requirements: Path | str,
    state: dict[str, Any],
) -> None:
    content = requirements.read_text(encoding='utf-8') if isinstance(requirements, Path) else str(requirements)
    issues = _staged_requirements_package_consistency_issues(gate_body(content), state)
    if issues:
        raise ValueError('; '.join(issues))


def validate_staged_requirements_stage_output(
    state: dict[str, Any],
    artifacts_dir: Path,
    stage: str,
    *,
    artifact_path: Path | None = None,
) -> None:
    content = _staged_requirements_stage_content(state, stage, artifact_path=artifact_path)
    scope_content = content if stage == 'scope' else _staged_requirements_stage_content(state, 'scope')
    known_scope_ids = _staged_scope_reference_ids(scope_content)
    issues: list[str] = []

    if stage == 'scope':
        issues.extend(_requirements_scope_stage_contract_issues(content))
    elif stage == 'product_design':
        issues.extend(_staged_output_unknown_reference_issues(content, known_scope_ids, label='Product Design checkpoint'))
        issues.extend(_product_design_stage_manifest_issues(state, artifacts_dir, known_scope_ids))
    elif stage == 'architecture':
        issues.extend(_staged_output_unknown_reference_issues(content, known_scope_ids, label='Architecture checkpoint'))
        issues.extend(_architecture_stage_e2e_handoff_issues(content, scope_content))
    elif stage == 'test_strategy':
        issues.extend(_staged_output_unknown_reference_issues(content, known_scope_ids, label='Test Strategy checkpoint'))
        issues.extend(_test_strategy_stage_e2e_matrix_issues(content, scope_content, state))
    else:
        raise ValueError(f'Unsupported requirements package stage validation: {stage}')

    if issues:
        raise ValueError('; '.join(issues))


def _staged_requirements_stage_content(
    state: dict[str, Any],
    stage: str,
    *,
    artifact_path: Path | None = None,
) -> str:
    path = artifact_path
    if path is None:
        package = state.get('requirementsPackage')
        artifacts = package.get('artifacts') if isinstance(package, dict) else {}
        record = artifacts.get(stage) if isinstance(artifacts, dict) else None
        path_text = record.get('path') if isinstance(record, dict) else None
        if not path_text:
            return ''
        path = Path(str(path_text))
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return ''


def _staged_scope_reference_ids(scope_content: str) -> dict[str, set[str]]:
    return {
        'acs': _requirements_acceptance_criterion_ids(scope_content),
        'journeys': _requirements_journey_ids_in_text(scope_content),
    }


def _requirements_scope_stage_contract_issues(content: str) -> list[str]:
    if not _stage_declares_real_e2e_or_browser_review(content):
        return []
    e2e_ac_ids = _requirements_e2e_acceptance_criterion_ids(content)
    e2e_journey_ids = _requirements_active_e2e_journey_ids(content)
    if e2e_ac_ids or e2e_journey_ids:
        return []
    return [
        'Requirements Scope checkpoint declares E2E/browser review but does not map it '
        'to a canonical e2e AC or active e2e Journey; '
        + _requirements_e2e_mapping_guidance()
    ]


def _staged_output_unknown_reference_issues(
    content: str,
    known_scope_ids: dict[str, set[str]],
    *,
    label: str,
) -> list[str]:
    known_acs = known_scope_ids.get('acs') or set()
    known_journeys = known_scope_ids.get('journeys') or set()
    unknown_acs = sorted(_requirements_current_ac_ids_in_text(content) - known_acs)
    unknown_journeys = sorted(_requirements_journey_ids_in_text(content) - known_journeys)
    issues: list[str] = []
    if unknown_acs:
        issues.append(f'{label} references unknown acceptance criteria: {", ".join(unknown_acs)}')
    if unknown_journeys:
        issues.append(f'{label} references unknown Journey: {", ".join(unknown_journeys)}')
    return issues


def _architecture_stage_e2e_handoff_issues(content: str, scope_content: str) -> list[str]:
    scope_e2e_ids = _requirements_e2e_acceptance_criterion_ids(scope_content) | _requirements_active_e2e_journey_ids(scope_content)
    if not scope_e2e_ids and not _stage_declares_real_e2e_or_browser_review(content):
        return []
    if not scope_e2e_ids:
        return [
            'Architecture checkpoint declares E2E/browser handoff but Scope has no canonical '
            'e2e AC or active e2e Journey; ' + _requirements_e2e_mapping_guidance()
        ]
    stage_ids = _requirements_ac_ids_in_text(content) | _requirements_journey_ids_in_text(content)
    if stage_ids & scope_e2e_ids:
        return []
    return [
        'Architecture checkpoint inherits E2E/browser handoff and must reference Scope canonical '
        'e2e AC/Journey: ' + ', '.join(sorted(scope_e2e_ids))
    ]


def _test_strategy_stage_e2e_matrix_issues(
    content: str,
    scope_content: str,
    state: dict[str, Any],
) -> list[str]:
    scope_declares_e2e = (
        bool(_requirements_e2e_acceptance_criterion_ids(scope_content))
        or bool(_requirements_active_e2e_journey_ids(scope_content))
        or _stage_declares_real_e2e_or_browser_review(scope_content)
    )
    stage_declares_e2e = _stage_declares_real_e2e_or_browser_review(content)
    if not scope_declares_e2e and not stage_declares_e2e:
        return []
    if not _requirements_has_fixed_4_6_e2e_heading(content):
        return [
            'Requirements Test Strategy checkpoint declares or inherits E2E/browser review but is missing '
            f'fixed heading `## {_REQUIREMENTS_E2E_REVIEW_FIXED_HEADING}` with the fixed 11-column table'
        ]
    scope_contract_content = _requirements_content_without_e2e_review_section(scope_content)
    combined = scope_contract_content.rstrip() + '\n\n' + content
    return _requirements_e2e_review_matrix_issues(combined, state)


def _product_design_stage_manifest_issues(
    state: dict[str, Any],
    artifacts_dir: Path,
    known_scope_ids: dict[str, set[str]],
) -> list[str]:
    if not _product_design_stage_requires_prototype_manifest(state):
        return []

    manifest_path = artifacts_dir / 'requirements-draft' / 'prototype-manifest.json'
    if not manifest_path.exists():
        return [
            'Product Design checkpoint requires artifacts/requirements-draft/prototype-manifest.json '
            'when prototype_required=required or web_system=required'
        ]

    try:
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        return [f'Product Design checkpoint prototype-manifest.json is invalid JSON: {exc.msg}']
    if not isinstance(payload, dict):
        return ['Product Design checkpoint prototype-manifest.json must be a JSON object']

    prototypes = payload.get('prototypes')
    if not isinstance(prototypes, list) or not prototypes:
        flat_keys = sorted(key for key in _FLAT_PROTOTYPE_MANIFEST_KEYS if key in payload)
        if flat_keys:
            return [
                'Product Design checkpoint prototype-manifest.json missing `prototypes[]`; '
                'flat top-level prototype manifest keys are not accepted: '
                + ', '.join(flat_keys)
                + '. Put prototype access, page_states, click_path, AC/Journey mapping, '
                'implementation_targets, and surface_contracts under each item in `prototypes[]`.'
            ]
        return ['Product Design checkpoint prototype-manifest.json must contain a non-empty `prototypes[]` list']

    issues: list[str] = []
    for index, prototype in enumerate(prototypes):
        if not isinstance(prototype, dict):
            issues.append(f'prototype[{index}] must be an object')
            continue
        label = str(prototype.get('id') or index)
        _stage_require_non_empty(prototype, ['id', 'type', 'title'], f'prototype {label}', issues)
        prototype_type = str(prototype.get('type') or '').strip().lower()
        path_value = str(prototype.get('path') or '').strip()
        url_value = str(prototype.get('url') or '').strip()
        review_href = str(prototype.get('review_href') or prototype.get('reviewHref') or '').strip()
        if not path_value and not url_value and not review_href:
            issues.append(f'prototype {label} missing clickable prototype access method path/url/review_href')
        if path_value and prototype_type in {'html', 'image', 'markdown', 'md'}:
            resolved_path = Path(path_value)
            if not resolved_path.is_absolute():
                resolved_path = manifest_path.parent / resolved_path
            if not resolved_path.exists() or not resolved_path.is_file():
                guidance = (
                    f'prototype {label} path does not exist: {path_value} '
                    f'(resolved path: {resolved_path}; paths are resolved relative to '
                    'artifacts/requirements-draft/prototype-manifest.json parent; '
                    'copy or generate the prototype into artifacts/requirements-draft, '
                    'or use an intentional absolute path)'
                )
                if path_value.startswith('docs/prototypes/'):
                    guidance += (
                        '; workspace-relative docs/prototypes path detected; either copy it under '
                        'artifacts/requirements-draft/docs/prototypes or rewrite the manifest path '
                        'to an artifact-local prototypes/<prototype-id>/... file'
                    )
                issues.append(guidance)
        if prototype_type == 'url' and not url_value:
            issues.append(f'prototype {label} type=url requires url')
        if _product_design_stage_requires_clickable_web_manifest(state) and prototype_type not in {'html', 'url'}:
            issues.append(f'prototype {label} must be html or url for web_system=required')

        if not _stage_list_value(prototype, 'page_states', 'pageStates'):
            issues.append(f'prototype {label} missing page_states')
        if not _stage_list_value(prototype, 'click_path', 'clickPath'):
            issues.append(f'prototype {label} missing click_path')
        if not _stage_list_value(
            prototype,
            'linked_acceptance_criteria',
            'acceptance_criteria',
            'linked_acs',
            'acs',
        ):
            issues.append(f'prototype {label} missing linked_acceptance_criteria')
        if not _stage_list_value(prototype, 'linked_journeys', 'journeys'):
            issues.append(f'prototype {label} missing linked_journeys')
        if not _stage_list_value(prototype, 'implementation_targets', 'production_targets', 'real_targets'):
            issues.append(f'prototype {label} missing implementation_targets')
        issues.extend(_prototype_scope_reference_issues(prototype, known_scope_ids, f'prototype {label}'))

        surface_contracts = _stage_list_value(prototype, 'surface_contracts', 'ui_surfaces', 'page_state_targets')
        if not surface_contracts:
            issues.append(f'prototype {label} missing surface_contracts')
        else:
            for surface_index, surface in enumerate(surface_contracts):
                if not isinstance(surface, dict):
                    issues.append(f'prototype {label} surface_contracts[{surface_index}] must be an object')
                    continue
                surface_label = str(surface.get('id') or surface_index)
                _stage_require_non_empty(surface, ['id', 'title', 'kind'], f'prototype {label} surface {surface_label}', issues)
                if not _stage_list_value(surface, 'page_states', 'pageStates'):
                    issues.append(f'prototype {label} surface {surface_label} missing page_states')
                if not _stage_list_value(surface, 'click_path', 'clickPath'):
                    issues.append(f'prototype {label} surface {surface_label} missing click_path')
                if not _stage_list_value(surface, 'entrypoints', 'entry_points', 'entryPoints'):
                    issues.append(f'prototype {label} surface {surface_label} missing entrypoints')
                if not _stage_list_value(surface, 'implementation_targets', 'production_targets', 'real_targets'):
                    issues.append(f'prototype {label} surface {surface_label} missing implementation_targets')
                if not _stage_list_value(
                    surface,
                    'linked_acceptance_criteria',
                    'acceptance_criteria',
                    'linked_acs',
                    'acs',
                ):
                    issues.append(f'prototype {label} surface {surface_label} missing linked_acceptance_criteria')
                issues.extend(_prototype_scope_reference_issues(
                    surface,
                    known_scope_ids,
                    f'prototype {label} surface {surface_label}',
                ))

    if issues:
        return ['Product Design checkpoint prototype-manifest.json is incomplete: ' + '; '.join(issues)]
    return []


_FLAT_PROTOTYPE_MANIFEST_KEYS = {
    'clickable_prototype_access_method',
    'page_states',
    'pageStates',
    'click_path',
    'clickPath',
    'linked_acceptance_criteria',
    'linked_journeys',
    'implementation_targets',
    'production_targets',
    'real_targets',
    'surface_contracts',
    'ui_surfaces',
    'page_state_targets',
}


def _prototype_scope_reference_issues(
    payload: dict[str, Any],
    known_scope_ids: dict[str, set[str]],
    label: str,
) -> list[str]:
    known_acs = known_scope_ids.get('acs') or set()
    known_journeys = known_scope_ids.get('journeys') or set()
    acs = {str(value).upper() for value in _stage_list_value(
        payload,
        'linked_acceptance_criteria',
        'acceptance_criteria',
        'linked_acs',
        'acs',
    )}
    journeys = {str(value).upper() for value in _stage_list_value(payload, 'linked_journeys', 'journeys')}
    issues: list[str] = []
    unknown_acs = sorted(acs - known_acs)
    unknown_journeys = sorted(journeys - known_journeys)
    if unknown_acs:
        issues.append(f'{label} unknown acceptance criteria: {", ".join(unknown_acs)}')
    if unknown_journeys:
        issues.append(f'{label} unknown Journey: {", ".join(unknown_journeys)}')
    return issues


def _product_design_stage_requires_prototype_manifest(state: dict[str, Any]) -> bool:
    classification = state.get('requirementsSurfaceClassification')
    if not isinstance(classification, dict):
        return False
    return (
        str(classification.get('prototype_required') or '').strip().lower() == 'required'
        or str(classification.get('web_system') or '').strip().lower() == 'required'
    )


def _product_design_stage_requires_clickable_web_manifest(state: dict[str, Any]) -> bool:
    classification = state.get('requirementsSurfaceClassification')
    return (
        isinstance(classification, dict)
        and str(classification.get('web_system') or '').strip().lower() == 'required'
    )


def _stage_require_non_empty(
    payload: dict[str, Any],
    keys: list[str],
    label: str,
    issues: list[str],
) -> None:
    for key in keys:
        if not str(payload.get(key) or '').strip():
            issues.append(f'{label} missing {key}')


def _stage_list_value(payload: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [part.strip() for part in value.replace(';', ',').split(',') if part.strip()]
    return []


def _stage_declares_real_e2e_or_browser_review(content: str) -> bool:
    return _requirements_text_explicitly_requires_e2e_review(content, {})


def _requirements_has_fixed_4_6_e2e_heading(content: str) -> bool:
    return re.search(
        rf'(?m)^\s{{0,3}}##\s+{re.escape(_REQUIREMENTS_E2E_REVIEW_FIXED_HEADING)}\s*#*\s*$',
        content,
    ) is not None


def _requirements_e2e_mapping_guidance() -> str:
    return (
        'canonical Journey rows must use `Status=active` and `Verification Layer=e2e`; '
        'natural-language values such as `是` or `real integration + DB assertion` are not accepted; '
        f'after mapping, Test Strategy must include `## {_REQUIREMENTS_E2E_REVIEW_FIXED_HEADING}`. '
        'Minimal example: `| J-V04-001 | Classroom happy path | active | Open page -> assert persisted status | AC-V04-001 | e2e |`.'
    )


def _staged_requirements_package_state(state: dict[str, Any]) -> bool:
    package = state.get('requirementsPackage')
    return isinstance(package, dict) and package.get('version') == REQUIREMENTS_PACKAGE_VERSION


def _staged_requirements_package_consistency_issues(content: str, state: dict[str, Any]) -> list[str]:
    package = state.get('requirementsPackage')
    artifacts = package.get('artifacts') if isinstance(package, dict) else {}
    if not isinstance(artifacts, dict):
        artifacts = {}

    issues: list[str] = []
    hash_section = _markdown_section(content, 'Artifact Hashes')
    for stage in CHECKPOINT_STAGES:
        title = STAGE_APPENDIX_TITLES[stage]
        if not _markdown_heading_exists(content, title, level=2):
            issues.append(f'staged requirements package missing appendix for {title}')
        record = artifacts.get(stage)
        if not isinstance(record, dict):
            issues.append(f'staged requirements package missing artifact record for {stage}')
            continue
        path_text = str(record.get('path') or '')
        expected_hash = str(record.get('hash') or '')
        if not hash_section.strip() or stage not in hash_section or expected_hash not in hash_section:
            issues.append(f'staged requirements package missing artifact hash row for {stage}')
        artifact_path = Path(path_text)
        if not artifact_path.exists():
            issues.append(f'staged requirements package missing artifact file for {stage}: {path_text}')
            continue
        actual_hash = artifact_hash(artifact_path)
        if actual_hash != expected_hash:
            issues.append(
                f'staged requirements package hash mismatch for {stage}: expected {expected_hash}, got {actual_hash}'
            )
    issues.extend(_staged_requirements_conflict_issues(content))
    return issues


def _staged_requirements_target_perspective_issues(state: dict[str, Any]) -> list[str]:
    package = state.get('requirementsPackage')
    artifacts = package.get('artifacts') if isinstance(package, dict) else {}
    if not isinstance(artifacts, dict):
        return []

    issues: list[str] = []
    for stage, label in (
        ('product_design', 'Product Design Brief'),
        ('architecture', 'Technical Architecture Brief'),
    ):
        record = artifacts.get(stage)
        if not isinstance(record, dict):
            continue
        path_text = str(record.get('path') or '')
        if not path_text:
            continue
        try:
            artifact_text = Path(path_text).read_text(encoding='utf-8')
        except OSError:
            continue
        issue = controller_perspective_issue(artifact_text, state, label=label)
        if issue:
            issues.append(issue)
    return issues


def _staged_requirements_appendices_content(content: str) -> str:
    starts: list[int] = []
    for title in STAGE_APPENDIX_TITLES.values():
        match = _markdown_heading_match(content, title, level=2)
        if match:
            starts.append(match.start())
    if not starts:
        return ''
    return content[min(starts):]


def _markdown_heading_exists(content: str, heading_contains: str, *, level: int | None = None) -> bool:
    return _markdown_heading_match(content, heading_contains, level=level) is not None


def _markdown_heading_match(
    content: str,
    heading_contains: str,
    *,
    level: int | None = None,
) -> re.Match[str] | None:
    hashes = f'{{{level}}}' if level is not None else '{1,6}'
    return re.search(
        rf'(?im)^\s{{0,3}}#{hashes}\s+.*{re.escape(heading_contains)}.*\s*#*\s*$',
        content,
    )


def _staged_requirements_conflict_issues(content: str) -> list[str]:
    issues: list[str] = []
    ac_layers: dict[str, set[str]] = {}
    for ac_id, layer in _requirements_ac_layer_pairs(content):
        ac_layers.setdefault(ac_id, set()).add(layer)
    for ac_id, layers in sorted(ac_layers.items()):
        if len(layers) > 1:
            issues.append(f'staged requirements package conflicting AC verification layers for {ac_id}: {sorted(layers)}')

    journey_statuses: dict[str, set[str]] = {}
    for journey_id, status in _requirements_journey_status_pairs(content):
        journey_statuses.setdefault(journey_id, set()).add(status)
    for journey_id, statuses in sorted(journey_statuses.items()):
        if 'active' in statuses and statuses & {'inactive', 'deferred', 'rejected'}:
            issues.append(f'staged requirements package conflicting Journey status for {journey_id}: {sorted(statuses)}')
    return issues


def _requirements_journey_status_pairs(content: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    allowed_statuses = {'active', 'inactive', 'deferred', 'rejected'}
    for rows in _markdown_table_row_groups(content):
        if not rows:
            continue
        indices = _requirements_journey_status_table_indices(rows[0])
        if not indices:
            continue
        for row in rows[1:]:
            status = _normalized_table_value(_cell_at(row, indices.get('status')))
            if status not in allowed_statuses:
                continue
            journey_cell = _cell_at(row, indices.get('journey'))
            for journey_id in _requirements_journey_ids_in_text(journey_cell):
                pairs.append((journey_id, status))
    return pairs


def _requirements_journey_status_table_indices(cells: list[str]) -> dict[str, int]:
    indices: dict[str, int] = {}
    for index, cell in enumerate(cells):
        normalized = _normalized_table_header(cell)
        if normalized in {'journey', 'journeyid', 'journeyids', 'id', '旅程', '旅程id'}:
            indices['journey'] = index
        elif normalized in {'status', 'journeystatus', '状态', '旅程状态'}:
            indices['status'] = index
    if 'journey' not in indices or 'status' not in indices:
        return {}
    return indices


def _markdown_table_row_groups(content: str) -> list[list[list[str]]]:
    groups: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in content.splitlines():
        cells = _markdown_table_cells(line)
        if cells:
            current.append(cells)
            continue
        if _is_markdown_table_separator(line):
            continue
        if current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def validate_unit_plan_golden_path(state: dict[str, Any]) -> None:
    missing: list[str] = []
    workspace_dir = _state_workspace_dir(state)
    for unit in state.get('units') or []:
        if not isinstance(unit, dict) or bool(unit.get('passes')):
            continue
        if not _unit_requires_golden_path(unit):
            continue
        unit_id = str(unit.get('id') or 'unknown-unit')
        commands = [str(command).strip() for command in unit.get('verification_commands') or [] if str(command).strip()]
        golden_cases = [case for case in _unit_test_cases(unit) if _is_golden_path_case(case)]
        if not golden_cases:
            missing.append(f'unit {unit_id} requires a golden_path test case before final acceptance')
            continue
        for case in golden_cases:
            issue = _golden_path_case_issue(case, commands, workspace_dir)
            if issue:
                case_id = str(case.get('id') or case.get('name') or 'unknown-test')
                missing.append(f'unit {unit_id} golden_path test case {case_id} {issue}')
    if missing:
        raise ValueError('unit plan golden_path coverage is incomplete: ' + '; '.join(missing))


def validate_unit_plan_final_acceptance_walkthrough(state: dict[str, Any]) -> None:
    issues: list[str] = []
    workspace_dir = _state_workspace_dir(state)
    for unit in state.get('units') or []:
        if not isinstance(unit, dict):
            continue
        launch = _unit_final_acceptance_launch(unit)
        unit_id = str(unit.get('id') or 'unknown-unit')
        if launch is not None:
            issues.extend(
                f'unit {unit_id} {issue}'
                for issue in _final_acceptance_launch_issues(launch, workspace_dir)
            )
        inspection = _unit_final_acceptance_inspection(unit)
        if _unit_requires_final_acceptance_inspection(unit, state) and inspection is None:
            issues.append(
                f'unit {unit_id} final_acceptance_walkthrough.inspection.entrypoint is required '
                'for closure/Web/UI units'
            )
            continue
        if inspection is not None:
            issues.extend(
                f'unit {unit_id} {issue}'
                for issue in _final_acceptance_inspection_issues(inspection)
            )
    if issues:
        raise ValueError('unit plan final_acceptance_walkthrough is invalid: ' + '; '.join(issues))


def validate_final_acceptance_manual_observation_record(gate_path: Path) -> None:
    content = gate_body(gate_path.read_text(encoding='utf-8'))
    section = _markdown_section(content, '人工系统观察记录（Review Notes）')
    if not section.strip():
        section = _markdown_section(content, '人工系统观察记录（Required）')
    if not section.strip():
        return
    missing = [
        label
        for label in (
            'Observed entrypoint',
            'Actual observation',
            'Data/account/fixture',
            'Issues or evidence path',
        )
        if not _observation_record_field_value(section, label)
    ]
    if missing:
        raise ValueError(
            '人工系统观察记录 is incomplete: '
            + ', '.join(missing)
            + ' must be filled after opening the Agent-provided entrypoint'
        )



def validate_unit_plan_verification_environment(state: dict[str, Any]) -> None:
    issues: list[str] = []
    issues.extend(_verification_env_declaration_issues('state', state))
    missing: list[str] = []
    state_env_keys = _verification_env_keys(state)
    for unit in state.get('units') or []:
        if not isinstance(unit, dict):
            continue
        unit_id = str(unit.get('id') or 'unknown-unit')
        issues.extend(_verification_env_declaration_issues(f'unit {unit_id}', unit))
        env_keys = state_env_keys | _verification_env_keys(unit)
        commands = unit.get('verification_commands') or []
        for command in commands:
            command_text = str(command)
            for required_key in sorted(_required_env_keys_for_verification_command(command_text)):
                if required_key in env_keys or _command_sets_env(command_text, required_key):
                    continue
                missing.append(
                    f'unit {unit_id} command requires {required_key}; '
                    f'add {required_key} to verification_env or inline it in the command: {command_text}'
                )
    if issues:
        raise ValueError('unit plan verification environment is invalid: ' + '; '.join(issues))
    if missing:
        raise ValueError('unit plan verification_env is incomplete: ' + '; '.join(missing))


def validate_unit_plan_verification_assist_contract(
    state: dict[str, Any],
    *,
    artifacts_dir: Path,
) -> None:
    from workflow_controller.annotation_agents import (
        normalize_verification_assist_config,
        verification_assist_spec_from_case,
    )

    issues: list[str] = []
    for unit in state.get('units') or []:
        if not isinstance(unit, dict) or bool(unit.get('passes')):
            continue
        unit_id = str(unit.get('id') or 'unknown-unit')
        for case in _unit_test_cases(unit):
            if not isinstance(case, dict):
                continue
            spec = verification_assist_spec_from_case(case)
            if spec is None:
                continue
            case_id = str(case.get('id') or case.get('name') or 'unknown-test')
            if str(case.get('command') or '').strip():
                issues.append(
                    f'unit {unit_id} test case {case_id} must use either command or verification_assist; '
                    'use evidence_type=descriptive_command when a command still runs and Agent only adds context'
                )
            if not isinstance(spec, dict):
                issues.append(f'unit {unit_id} test case {case_id} verification_assist must be an object')
                continue
            if not str(spec.get('description') or '').strip():
                issues.append(f'unit {unit_id} test case {case_id} verification_assist.description is required')
            expected = spec.get('expected')
            if isinstance(expected, list):
                has_expected = any(str(item).strip() for item in expected)
            else:
                has_expected = bool(str(expected or '').strip())
            if not has_expected:
                issues.append(f'unit {unit_id} test case {case_id} verification_assist.expected is required')
            try:
                config = normalize_verification_assist_config(state, case, artifacts_dir=artifacts_dir)
            except ValueError as exc:
                issues.append(f'unit {unit_id} test case {case_id} verification_assist agent config is invalid: {exc}')
                continue
            if not config.enabled or not config.command:
                issues.append(
                    f'unit {unit_id} test case {case_id} has no enabled verification-assist agent config'
                )
    if issues:
        raise ValueError('unit plan verification_assist contract is invalid: ' + '; '.join(issues))


def validate_unit_plan_evidence_row_preflight(state: dict[str, Any]) -> None:
    issues: list[str] = []
    for unit in state.get('units') or []:
        if not isinstance(unit, dict) or bool(unit.get('passes')):
            continue
        unit_id = str(unit.get('id') or 'unknown-unit')
        verification_commands = {
            str(command).strip()
            for command in unit.get('verification_commands') or []
            if str(command).strip()
        }
        for case in _unit_test_cases(unit):
            if not isinstance(case, dict):
                continue
            if _case_has_verification_assist(case) or _case_is_manual_evidence_case(case):
                continue
            case_id = str(case.get('id') or case.get('name') or 'unknown-test')
            command = str(case.get('command') or '').strip()
            if not command:
                if _case_has_manual_evidence(case):
                    issues.append(
                        f'unit {unit_id} test case {case_id} manual evidence does not satisfy '
                        'automated evidence row preflight; add a command that exactly matches '
                        'verification_commands or declare verification_assist'
                    )
                else:
                    issues.append(
                        f'unit {unit_id} test case {case_id} must declare a command that exactly '
                        'matches verification_commands or declare verification_assist'
                    )
                continue
            if command not in verification_commands:
                issues.append(
                    f'unit {unit_id} test case {case_id} command must exactly match '
                    f'verification_commands: {command}'
                )
    if issues:
        raise ValueError('unit plan evidence row preflight is incomplete: ' + '; '.join(issues))


def validate_unit_plan_handoff_continuity(
    state: dict[str, Any],
    unit_plan_path: Path | None = None,
) -> None:
    units = [
        unit for unit in state.get('units') or []
        if isinstance(unit, dict) and str(unit.get('id') or '').strip()
    ]
    if not units:
        return

    units_by_id = {str(unit.get('id')).strip(): unit for unit in units}
    issues: list[str] = []
    dependency_graph: dict[str, list[str]] = {}
    dependents_by_unit: dict[str, list[str]] = {unit_id: [] for unit_id in units_by_id}
    for unit_id, unit in units_by_id.items():
        dependencies = unit_depends_on(unit)
        dependency_graph[unit_id] = dependencies
        for dependency in dependencies:
            if dependency not in units_by_id:
                issues.append(f'unit {unit_id} depends_on unknown unit {dependency}')
                continue
            if dependency == unit_id:
                issues.append(f'unit {unit_id} depends_on itself')
                continue
            dependents_by_unit.setdefault(dependency, []).append(unit_id)

    issues.extend(_unit_handoff_cycle_issues(dependency_graph))

    has_handoff_contract = any(unit_depends_on(unit) or unit_handoff(unit) for unit in units)
    if len(units) <= 1 and not has_handoff_contract:
        if issues:
            raise ValueError('unit plan handoff continuity is incomplete: ' + '; '.join(issues))
        return
    if len(units) > 1 and has_handoff_contract and unit_plan_path is not None and unit_plan_path.exists():
        content = gate_body(unit_plan_path.read_text(encoding='utf-8'))
        if not _markdown_section(content, '单元连贯性摘要').strip():
            issues.append('Unit Plan missing `## 单元连贯性摘要` for multi-unit handoff continuity')
        if not (
            _markdown_section(content, 'Handoff Matrix').strip()
            or _markdown_section(content, '交接矩阵').strip()
        ):
            issues.append('Unit Plan missing `## Handoff Matrix` for multi-unit handoff continuity')

    for unit_id, unit in units_by_id.items():
        dependencies = [dependency for dependency in unit_depends_on(unit) if dependency in units_by_id]
        dependents = dependents_by_unit.get(unit_id) or []
        handoff = unit_handoff(unit)
        participates = bool(dependencies or dependents or handoff)
        if not participates:
            continue

        if not handoff:
            issues.append(f'unit {unit_id} participates in dependencies but is missing handoff')
            continue

        summary = handoff_human_summary(unit)
        if handoff_summary_is_vague(summary):
            issues.append(f'unit {unit_id} handoff human_summary is vague: {summary or "<missing>"}')

        if dependencies and not handoff_requires(unit):
            issues.append(f'unit {unit_id} depends_on {dependencies} but handoff.requires is empty')
        if dependents and not handoff_produces(unit):
            issues.append(f'unit {unit_id} feeds downstream unit(s) {dependents} but handoff.produces is empty')

        if not bool(unit.get('passes')):
            if not _non_placeholder_items(unit.get('done_when') or unit.get('doneWhen')):
                issues.append(f'unit {unit_id} handoff must be covered by concrete done_when conditions')
            if not handoff_ready_checks(unit):
                issues.append(f'unit {unit_id} handoff.ready_checks is empty')
            if not handoff_evidence_artifacts(unit):
                issues.append(f'unit {unit_id} handoff.evidence_artifacts is empty')
            for ready_check in handoff_ready_checks(unit):
                if not ready_check_is_mapped(unit, ready_check):
                    issues.append(
                        f'unit {unit_id} ready_check {ready_check} is not mapped to verification_commands or test_cases'
                    )

        required_inputs = handoff_requires(unit)
        if dependencies and required_inputs:
            producer_outputs_by_dependency = {
                dependency: handoff_produces(units_by_id[dependency])
                for dependency in dependencies
            }
            for required_input in required_inputs:
                matching_dependencies = [
                    dependency for dependency, producer_outputs in producer_outputs_by_dependency.items()
                    if any(handoff_text_matches(required_input, produced) for produced in producer_outputs)
                ]
                if not matching_dependencies:
                    if len(dependencies) == 1:
                        issues.append(
                            f'unit {unit_id} requires {required_input} but dependency {dependencies[0]} does not produce it'
                        )
                    else:
                        issues.append(
                            f'unit {unit_id} requires {required_input} but no dependency in {dependencies} produces it'
                        )
            for dependency, producer_outputs in producer_outputs_by_dependency.items():
                if not any(
                    handoff_text_matches(required_input, produced)
                    for required_input in required_inputs
                    for produced in producer_outputs
                ):
                    issues.append(
                        f'unit {unit_id} depends_on {dependency} but none of its produces are required by the downstream handoff'
                    )

    if issues:
        raise ValueError('unit plan handoff continuity is incomplete: ' + '; '.join(issues))


def _unit_handoff_cycle_issues(dependency_graph: dict[str, list[str]]) -> list[str]:
    issues: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(unit_id: str, stack: list[str]) -> None:
        if unit_id in visiting:
            cycle = stack[stack.index(unit_id):] + [unit_id] if unit_id in stack else [unit_id, unit_id]
            issues.append('circular dependency in Unit Plan handoff graph: ' + ' -> '.join(cycle))
            return
        if unit_id in visited:
            return
        visiting.add(unit_id)
        for dependency in dependency_graph.get(unit_id) or []:
            if dependency not in dependency_graph:
                continue
            visit(dependency, [*stack, dependency])
        visiting.remove(unit_id)
        visited.add(unit_id)

    for unit_id in dependency_graph:
        visit(unit_id, [unit_id])
    return issues


def _non_placeholder_items(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = [str(item).strip() for item in value if str(item).strip()]
    elif isinstance(value, str) and value.strip():
        raw_items = [value.strip()]
    else:
        raw_items = []
    placeholders = {'tbd', 'todo', '待补', '待定', 'n/a', 'na', 'none', 'environment ready'}
    return [
        item for item in raw_items
        if item.strip().lower() not in placeholders and '...' not in item
    ]


def validate_unit_plan_script_entry_commands(state: dict[str, Any]) -> None:
    issues: list[str] = []
    for unit in state.get('units') or []:
        if not isinstance(unit, dict) or bool(unit.get('passes')):
            continue
        unit_id = str(unit.get('id') or 'unknown-unit')
        for label, command in _unit_commands_for_script_policy(unit):
            if _command_is_script_entrypoint(command):
                continue
            issues.append(
                f'unit {unit_id} {label} must be a script entrypoint under scripts/verify; '
                'write the command into a script file and execute it as '
                '`bash scripts/verify/<case>.sh`, `sh scripts/verify/<case>.sh`, '
                '`python3 scripts/verify/<case>.py`, `python scripts/verify/<case>.py`, '
                '`./scripts/verify/<case>.sh`, or `./scripts/verify/<case>.py`'
            )
    if issues:
        raise ValueError('unit plan command policy is invalid: ' + '; '.join(issues))


def _unit_commands_for_script_policy(unit: dict[str, Any]) -> list[tuple[str, str]]:
    labels_by_command: dict[str, list[str]] = {}

    for case in _unit_test_cases(unit):
        if not isinstance(case, dict):
            continue
        command = str(case.get('command') or '').strip()
        if not command:
            continue
        case_id = str(case.get('id') or case.get('name') or 'unknown-test')
        labels_by_command.setdefault(command, []).append(f'test case {case_id} command')

    for command in unit.get('verification_commands') or []:
        normalized = str(command or '').strip()
        if not normalized:
            continue
        labels_by_command.setdefault(normalized, []).append('verification_commands[] entry')

    return [
        (' and '.join(labels), command)
        for command, labels in labels_by_command.items()
    ]


def _command_is_script_entrypoint(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens:
        return False

    if len(tokens) == 1:
        script = tokens[0]
        return any(
            _script_path_is_allowed(script, suffix=suffix, allow_direct=True)
            for suffix in ('.sh', '.py')
        )

    if len(tokens) != 2:
        return False

    runner, script = tokens
    if runner in {'bash', 'sh'}:
        return _script_path_is_allowed(script, suffix='.sh', allow_direct=False)
    if runner in {'python', 'python3'}:
        return _script_path_is_allowed(script, suffix='.py', allow_direct=False)
    return False


def _script_path_is_allowed(script: str, *, suffix: str, allow_direct: bool) -> bool:
    if any(part in script for part in ('\x00', '\n', '\r')):
        return False
    if script.startswith('./'):
        normalized = script[2:]
        direct = True
    else:
        normalized = script
        direct = False
    if direct and not allow_direct:
        return False
    if not normalized.startswith('scripts/verify/'):
        return False
    if '/../' in f'/{normalized}' or normalized.endswith('/..'):
        return False
    if not normalized.endswith(suffix):
        return False
    return bool(re.fullmatch(r'scripts/verify/[A-Za-z0-9._/-]+', normalized))


def validate_unit_plan_final_evidence_candidates(
    requirements_path: Path,
    state: dict[str, Any],
) -> None:
    if not requirements_path.exists():
        return
    requirements_content = gate_body(requirements_path.read_text(encoding='utf-8'))
    required_ac_ids = sorted(_requirements_acceptance_criterion_ids(requirements_content))
    if not required_ac_ids:
        return

    valid_candidates: dict[str, list[str]] = {ac_id: [] for ac_id in required_ac_ids}
    weak_candidates: dict[str, list[str]] = {ac_id: [] for ac_id in required_ac_ids}
    for unit in state.get('units') or []:
        if not isinstance(unit, dict):
            continue
        unit_id = str(unit.get('id') or 'unknown-unit')
        verification_commands = {
            str(command).strip()
            for command in unit.get('verification_commands') or []
            if str(command).strip()
        }
        for case in _unit_test_cases(unit):
            if not isinstance(case, dict):
                continue
            ac_ids = _case_acceptance_criterion_ids(case)
            mapped_ac_ids = sorted(ac_id for ac_id in ac_ids if ac_id in valid_candidates)
            if not mapped_ac_ids:
                continue
            case_id = str(case.get('id') or case.get('name') or 'unknown-test')
            issue = _final_evidence_candidate_issue(case, verification_commands)
            label = f'unit {unit_id} test case {case_id}'
            for ac_id in mapped_ac_ids:
                if issue:
                    weak_candidates[ac_id].append(f'{label} {issue}')
                else:
                    valid_candidates[ac_id].append(label)

    missing = [ac_id for ac_id in required_ac_ids if not valid_candidates[ac_id]]
    if not missing:
        return

    issues: list[str] = []
    for ac_id in missing:
        weak = weak_candidates.get(ac_id) or []
        if weak:
            issues.append(f'{ac_id} has no final-valid evidence candidate; weak candidate(s): ' + '; '.join(weak))
        else:
            issues.append(f'{ac_id} has no Unit Plan test case with a final-valid evidence candidate')
    raise ValueError(
        'unit plan final evidence candidate preflight is incomplete: '
        + '; '.join(issues)
        + '; add an exact test_cases[].command listed in verification_commands[] '
        'or an explicit manual evidence case'
    )


def validate_unit_plan_real_e2e_evidence_policy(
    requirements_path: Path,
    state: dict[str, Any],
) -> None:
    workspace_dir = _state_workspace_dir(state)
    e2e_ac_ids: set[str] = set()
    requirements_content = ''
    if requirements_path.exists():
        requirements_content = gate_body(requirements_path.read_text(encoding='utf-8'))
        e2e_ac_ids = {
            ac_id for ac_id, layer in _requirements_acceptance_criterion_layers(requirements_content).items()
            if layer == 'e2e'
        }
        e2e_ac_ids.update(_requirements_e2e_acceptance_criterion_ids(requirements_content))
    e2e_journey_ids = _requirements_active_e2e_journey_ids(requirements_content) if requirements_content else set()

    issues: list[str] = []
    real_or_production_cases: list[dict[str, Any]] = []
    covered_e2e_ac_ids: set[str] = set()
    covered_e2e_journey_ids: set[str] = set()
    production_required = _requirements_request_production_readonly_evidence(requirements_content, state)
    state_web_system = bool(state.get('currentUnitIsWebSystem'))
    for unit in state.get('units') or []:
        if not isinstance(unit, dict):
            continue
        unit_id = str(unit.get('id') or 'unknown-unit')
        unit_web_system = state_web_system or bool(unit.get('currentUnitIsWebSystem') or unit.get('web_system'))
        for case in _unit_test_cases(unit):
            if not isinstance(case, dict):
                continue
            case_id = str(case.get('id') or case.get('name') or 'unknown-test')
            command = str(case.get('command') or '').strip()
            environment_kind = case_environment_kind(case)
            if str(case.get('layer') or '').strip().lower() == 'e2e':
                covered_e2e_ac_ids.update(_case_acceptance_criterion_ids(case))
                covered_e2e_journey_ids.update(_case_journey_ids(case))
            if bool(unit.get('passes')):
                continue
            mocked_routes = _case_core_api_mock_routes(case, command, workspace_dir)
            requires_real = case_requires_real_e2e(
                case,
                current_unit_is_web_system=unit_web_system,
                e2e_acceptance_criteria=e2e_ac_ids,
            )
            if environment_kind in REAL_E2E_ENVIRONMENT_KINDS:
                real_or_production_cases.append(case)
            if not mocked_routes and not case_declares_core_api_mock(case):
                continue
            if requires_real:
                issues.append(
                    f'unit {unit_id} test case {case_id} uses core API mock(s) '
                    f'{mocked_routes or case_declared_mocked_routes(case) or ["declared"]}; '
                    'real E2E, golden_path, prototype_conformance, and web-system acceptance evidence '
                    'must use real services/API'
                )
                continue
            if not case_allows_mock(case) or environment_kind not in MOCK_ENVIRONMENT_KINDS:
                issues.append(
                    f'unit {unit_id} test case {case_id} declares core API mock(s) '
                    f'{mocked_routes or case_declared_mocked_routes(case) or ["declared"]} but is not marked as '
                    'allows_mock=true with environment_kind component_mock, contract_mock, or visual'
                )

    for ac_id in sorted(e2e_ac_ids - covered_e2e_ac_ids):
        issues.append(f'requirements e2e acceptance criterion {ac_id} must map to a layer=e2e Unit Plan test case')
    for journey_id in sorted(e2e_journey_ids - covered_e2e_journey_ids):
        issues.append(f'requirements e2e journey {journey_id} must map to a layer=e2e Unit Plan test case')
    if production_required:
        if not any(case_environment_kind(case) == 'production_readonly' for case in real_or_production_cases):
            issues.append(
                'requirements or feedback request production/remote verification; '
                'add a read-only production evidence test case with environment_kind=production_readonly'
            )
    if issues:
        raise ValueError('unit plan real E2E evidence policy is incomplete: ' + '; '.join(issues))


def validate_final_real_e2e_evidence(
    *,
    state: dict[str, Any],
    artifacts_dir: Path,
) -> None:
    issues: list[str] = []
    for row in _final_verification_evidence_rows(state, artifacts_dir):
        if not isinstance(row, dict):
            continue
        if row.get('golden_path') is not True:
            continue
        issue = evidence_row_real_e2e_issue(row)
        if issue:
            issues.append(
                f"golden_path {row.get('test_case_id') or row.get('acceptance_criterion') or 'unknown-test'}: {issue}"
            )
    if issues:
        raise ValueError('real E2E evidence is incomplete: ' + '; '.join(issues))


def apply_unit_plan_state_patch_from_gate(state: dict[str, Any], gate_path: Path) -> dict[str, Any]:
    patch = extract_unit_plan_state_patch(gate_path.read_text(encoding='utf-8'))
    return apply_unit_plan_state_patch(state, patch)


def migrate_unit_plan_gate_to_state_patch(state: dict[str, Any], gate_path: Path) -> bool:
    content = gate_path.read_text(encoding='utf-8')
    if _find_controller_state_patch_heading(gate_body(content)):
        return False

    backup_path = gate_path.with_suffix('.md.before-controller-state-patch')
    if not backup_path.exists():
        backup_path.write_text(content, encoding='utf-8')

    body = gate_body(content).rstrip()
    migrated_body = (
        body
        + '\n\n'
        + CONTROLLER_STATE_PATCH_HEADING
        + '\n\n```json\n'
        + json.dumps(_controller_state_patch(state), ensure_ascii=False, indent=2)
        + '\n```\n'
    )
    write_gate_file(gate_path, migrated_body)
    return True


def apply_unit_plan_state_patch(state: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    if 'units' not in patch or 'objectiveCoverage' not in patch:
        raise ValueError('Controller State Patch must include units and objectiveCoverage')

    normalized_units = _normalize_patch_units(patch.get('units'), state)
    unit_ids = {unit['id'] for unit in normalized_units}
    previous_units = {
        str(unit.get('id')): unit
        for unit in state.get('units', [])
        if isinstance(unit, dict) and unit.get('id')
    }
    normalized_coverage = _normalize_patch_coverage(
        patch.get('objectiveCoverage'),
        unit_ids | set(previous_units),
    )
    preserved_units = _preserved_existing_units_from_coverage(
        normalized_coverage,
        declared_unit_ids=unit_ids,
        previous_units=previous_units,
    )

    explicit_current_unit = patch.get('currentUnitId')
    if explicit_current_unit:
        current_unit_id = str(explicit_current_unit).strip()
        if current_unit_id not in unit_ids:
            raise ValueError(f'currentUnitId is not declared in units: {current_unit_id}')
    else:
        existing_current = str(state.get('currentUnitId') or '').strip()
        current_unit_id = existing_current if existing_current in unit_ids else normalized_units[0]['id']

    next_state = dict(state)
    next_state['units'] = [*normalized_units, *preserved_units]
    next_state['objectiveCoverage'] = normalized_coverage
    next_state['currentUnitId'] = current_unit_id
    if 'currentUnitNeedsUiDesign' in patch:
        next_state['currentUnitNeedsUiDesign'] = bool(patch['currentUnitNeedsUiDesign'])
    else:
        current_unit = next((unit for unit in normalized_units if unit.get('id') == current_unit_id), {})
        if current_unit.get('ui_design_required') is True:
            next_state['currentUnitNeedsUiDesign'] = True
    if 'currentUnitIsWebSystem' in patch:
        next_state['currentUnitIsWebSystem'] = bool(patch['currentUnitIsWebSystem'])
    return next_state


def _preserved_existing_units_from_coverage(
    coverage: list[dict[str, Any]],
    *,
    declared_unit_ids: set[str],
    previous_units: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    completed_existing_ids = {
        unit_id
        for unit_id, unit in previous_units.items()
        if bool(unit.get('passes'))
    }
    completed_existing_ids.update(
        unit_id
        for item in coverage
        if item['status'] == 'covered'
        for unit_id in item['units']
        if unit_id in previous_units
    )

    preserved_ids: list[str] = []
    for item in coverage:
        extra_unit_ids = [unit_id for unit_id in item['units'] if unit_id not in declared_unit_ids]
        if not extra_unit_ids:
            continue
        if item['status'] != 'covered':
            unfinished_extra_unit_ids = [
                unit_id
                for unit_id in extra_unit_ids
                if unit_id not in completed_existing_ids
            ]
            if unfinished_extra_unit_ids:
                raise ValueError(
                    'partial objectiveCoverage may omit only completed existing unit ids from units; '
                    f'declare unfinished unit ids in units: {unfinished_extra_unit_ids}'
                )
        for unit_id in extra_unit_ids:
            if unit_id not in preserved_ids:
                preserved_ids.append(unit_id)

    preserved_units: list[dict[str, Any]] = []
    for unit_id in preserved_ids:
        unit = dict(previous_units[unit_id])
        unit['id'] = unit_id
        unit['passes'] = True
        preserved_units.append(unit)
    return preserved_units


def _normalize_patch_units(raw_units: Any, state: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(raw_units, list) or not raw_units:
        raise ValueError('Controller State Patch units must be a non-empty list')

    previous_passes = {
        str(unit.get('id')): bool(unit.get('passes'))
        for unit in state.get('units', [])
        if isinstance(unit, dict) and unit.get('id')
    }
    normalized_units: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_unit in raw_units:
        if not isinstance(raw_unit, dict):
            raise ValueError('Each Controller State Patch unit must be an object')
        unit_id = str(raw_unit.get('id') or '').strip()
        if not unit_id:
            raise ValueError('Each Controller State Patch unit must include id')
        if unit_id in seen:
            raise ValueError(f'Duplicate unit id in Controller State Patch: {unit_id}')
        seen.add(unit_id)

        unit = dict(raw_unit)
        unit['id'] = unit_id
        if 'passes' not in unit:
            unit['passes'] = previous_passes.get(unit_id, False)
        if 'verification_commands' in unit and not isinstance(unit['verification_commands'], list):
            raise ValueError(f'unit {unit_id} verification_commands must be a list')
        if 'test_cases' in unit and not isinstance(unit['test_cases'], list):
            raise ValueError(f'unit {unit_id} test_cases must be a list')
        if 'testCases' in unit and not isinstance(unit['testCases'], list):
            raise ValueError(f'unit {unit_id} testCases must be a list')
        normalized_units.append(unit)
    return normalized_units


def _normalize_patch_coverage(
    raw_coverage: Any,
    unit_ids: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw_coverage, list) or not raw_coverage:
        raise ValueError('Controller State Patch objectiveCoverage must be a non-empty list')

    normalized_coverage: list[dict[str, Any]] = []
    for raw_item in raw_coverage:
        if not isinstance(raw_item, dict):
            raise ValueError('Each Controller State Patch objectiveCoverage item must be an object')
        objective = str(raw_item.get('objective') or '').strip()
        if not objective:
            raise ValueError('Each Controller State Patch objectiveCoverage item must include objective')
        units = raw_item.get('units')
        if not isinstance(units, list) or not units:
            raise ValueError(f'objectiveCoverage for {objective} must include one or more units')
        normalized_units = [str(unit_id).strip() for unit_id in units if str(unit_id).strip()]
        unknown_units = [unit_id for unit_id in normalized_units if unit_id not in unit_ids]
        if unknown_units:
            raise ValueError(f'objectiveCoverage references unknown unit ids: {unknown_units}')
        status = str(raw_item.get('status') or 'partial').strip()
        if status not in ALLOWED_COVERAGE_STATUSES:
            raise ValueError(f'objectiveCoverage status must be one of {sorted(ALLOWED_COVERAGE_STATUSES)}')
        item = dict(raw_item)
        item['objective'] = objective
        item['units'] = normalized_units
        item['status'] = status
        normalized_coverage.append(item)
    return normalized_coverage


_REQUIREMENTS_RESOLUTION_STATUSES = {'deferred', 'rejected', 'out_of_scope'}

_REQUIREMENTS_INFRASTRUCTURE_CATEGORIES = [
    ('代码仓库', ('代码仓库',)),
    ('项目部署运行时环境', ('项目部署运行时环境', '部署运行时环境', '运行时环境')),
    ('调试分析方法', ('调试分析方法', '调试方法', '排查方法')),
    ('参考环境', ('参考环境',)),
    ('文档地址', ('文档地址', '文档来源')),
    ('架构/交互逻辑/接口说明', ('架构/交互逻辑/接口说明', '架构、交互逻辑、接口说明')),
    ('依赖信息', ('依赖信息',)),
]

_REQUIREMENTS_E2E_REVIEW_COLUMNS = [
    ('ac_journey', 'AC / Journey'),
    ('method', 'E2E Method'),
    ('entrypoint', 'Real Entrypoint'),
    ('user_steps', 'User Steps'),
    ('fixture', 'Fixture / Test Data / Setup'),
    ('command', 'Verification Command'),
    ('environment_kind', 'Environment Kind'),
    ('dependencies', 'Required Env / Dependencies'),
    ('mock_policy', 'Mock Policy'),
    ('assertions', 'Expected Assertions'),
    ('notes', 'Human Review Notes'),
]
_REQUIREMENTS_E2E_REVIEW_FIXED_HEADING = (
    '4.6 E2E 测试方法与前置依赖矩阵（E2E Test Method & Prerequisite Matrix）'
)


def _requirements_e2e_review_matrix_issues(content: str, state: dict[str, Any]) -> list[str]:
    e2e_ac_ids = _requirements_e2e_acceptance_criterion_ids(content)
    e2e_journey_ac_map = _requirements_active_e2e_journey_ac_map(content)
    e2e_journey_ids = set(e2e_journey_ac_map)
    explicit_e2e_text = _requirements_text_explicitly_requires_e2e_review(content, state)
    if explicit_e2e_text and not e2e_ac_ids and not e2e_journey_ids:
        return [
            'Requirements declares E2E/browser review but does not map it to an E2E AC or active e2e Journey; '
            + _requirements_e2e_mapping_guidance()
        ]

    if not e2e_ac_ids and not e2e_journey_ids:
        return []

    section = _requirements_e2e_review_section(content)
    if not section.strip():
        return [
            f'Requirements E2E review requires `## {_REQUIREMENTS_E2E_REVIEW_FIXED_HEADING}` '
            'before human approval; add the fixed-column E2E method/prerequisite matrix for every active e2e Journey '
            'and every e2e AC not covered by a mapped Journey row'
        ]

    rows, header_issue = _requirements_e2e_review_rows(section)
    if header_issue:
        return [header_issue]

    issues: list[str] = []
    row_ids = _requirements_e2e_review_row_ids(rows)
    for ac_id in sorted(e2e_ac_ids):
        if not _requirements_e2e_ac_is_covered_by_review_row(ac_id, row_ids, e2e_journey_ac_map):
            issues.append(f'{ac_id} missing Requirements 4.6 E2E review matrix row')
    for journey_id in sorted(e2e_journey_ids):
        if journey_id not in row_ids:
            issues.append(f'{journey_id} missing Requirements 4.6 E2E review matrix row')

    for row in rows:
        if not _requirements_e2e_review_row_has_required_mapping(row, e2e_ac_ids, e2e_journey_ids):
            continue
        label = row.get('ac_journey') or 'unknown AC/Journey'
        issues.extend(_requirements_e2e_review_row_quality_issues(row, label))
    return issues


def _requirements_e2e_acceptance_criterion_ids(content: str) -> set[str]:
    ids: set[str] = set()
    for section_name in ('验收标准', 'Acceptance Criteria'):
        ids.update(_requirements_e2e_ac_ids_in_section(_markdown_section(content, section_name)))
    ids.update(_requirements_e2e_ac_ids_in_traceability(content))
    return ids


def _requirements_e2e_ac_ids_in_section(section: str) -> set[str]:
    return {ac_id for ac_id, layer in _requirements_ac_layer_pairs(section) if layer == 'e2e'}


def _requirements_e2e_ac_ids_in_traceability(content: str) -> set[str]:
    ids: set[str] = set()
    section = _markdown_section(content, 'Requirements Traceability Matrix') or _markdown_section(content, '需求可追溯矩阵')
    header: dict[str, int] | None = None
    for line in section.splitlines():
        cells = _markdown_table_cells(line)
        if not cells:
            continue
        if _requirements_e2e_traceability_header(cells):
            header = _requirements_e2e_traceability_indices(cells)
            continue
        indices = header or {'ac': 1, 'layer': 3}
        ac_cell = _cell_at(cells, indices.get('ac'))
        layer_cell = _cell_at(cells, indices.get('layer'))
        if _normalize_requirements_verification_layer(layer_cell) == 'e2e':
            ids.update(_requirements_ac_ids_in_text(ac_cell))
    return ids


def _requirements_e2e_traceability_header(cells: list[str]) -> bool:
    normalized = [_normalized_table_header(cell) for cell in cells]
    return 'ac' in normalized and ('verificationlayer' in normalized or '验证层级' in normalized)


def _requirements_e2e_traceability_indices(cells: list[str]) -> dict[str, int]:
    indices: dict[str, int] = {}
    for index, cell in enumerate(cells):
        normalized = _normalized_table_header(cell)
        if normalized == 'ac':
            indices['ac'] = index
        elif normalized in {'verificationlayer', 'layer', '验证层级'}:
            indices['layer'] = index
    return indices


def _requirements_active_e2e_journey_ids(content: str) -> set[str]:
    return set(_requirements_active_e2e_journey_ac_map(content))


def _requirements_active_e2e_journey_ac_map(content: str) -> dict[str, set[str]]:
    section = _markdown_section(content, 'Journey Acceptance Matrix')
    journey_ac_map: dict[str, set[str]] = {}
    header: dict[str, int] | None = None
    for line in section.splitlines():
        cells = _markdown_table_cells(line)
        if not cells:
            continue
        if _requirements_journey_matrix_header(cells):
            header = _requirements_journey_matrix_indices(cells)
            continue
        indices = header or {'journey': 0, 'status': 2, 'ac': 4, 'layer': 5}
        status = _normalized_table_value(_cell_at(cells, indices.get('status')))
        layer = _normalize_requirements_verification_layer(_cell_at(cells, indices.get('layer')))
        if status == 'active' and layer == 'e2e':
            ac_ids = _requirements_ac_ids_in_text(_cell_at(cells, indices.get('ac')))
            for journey_id in _requirements_journey_ids_in_text(_cell_at(cells, indices.get('journey'))):
                journey_ac_map.setdefault(journey_id, set()).update(ac_ids)
    return journey_ac_map


def _requirements_journey_matrix_header(cells: list[str]) -> bool:
    normalized = {_normalized_table_header(cell) for cell in cells}
    return (
        bool(normalized & {'journey', 'journeyid', 'id', '旅程', '旅程id'})
        and bool(normalized & {'status', '状态'})
        and bool(normalized & {'verificationlayer', 'verification', 'layer', '验证层级', '验证方式'})
    )


def _requirements_journey_matrix_indices(cells: list[str]) -> dict[str, int]:
    indices: dict[str, int] = {}
    for index, cell in enumerate(cells):
        normalized = _normalized_table_header(cell)
        if normalized in {'journey', 'journeyid', 'id', '旅程', '旅程id'}:
            indices['journey'] = index
        elif normalized in {
            'ac',
            'acs',
            'linkedac',
            'linkedacs',
            'acceptancecriterion',
            'acceptancecriteria',
            'linkedacceptancecriterion',
            'linkedacceptancecriteria',
            '验收标准',
            '关联ac',
            '关联验收标准',
        }:
            indices['ac'] = index
        elif normalized in {'status', '状态'}:
            indices['status'] = index
        elif normalized in {'verificationlayer', 'verification', 'layer', '验证层级', '验证方式'}:
            indices['layer'] = index
    return indices


def _requirements_text_explicitly_requires_e2e_review(content: str, state: dict[str, Any]) -> bool:
    del state
    test_strategy = _markdown_section(content, 'Test Strategy') or _markdown_section(content, '测试策略')
    if _requirements_text_has_e2e_review_marker(test_strategy):
        return True
    contract_content = _requirements_content_without_e2e_review_section(_requirements_prototype_contract_content(content))
    return _requirements_text_has_real_browser_contract_marker(contract_content)


def _requirements_text_has_e2e_review_marker(text: str) -> bool:
    normalized = _normalized_requirements_text(text)
    if not normalized:
        return False
    e2e_markers = [
        'playwright',
        'cypress',
        'browser e2e',
        'browser test',
        'end-to-end',
        'end to end',
        'e2e',
        '浏览器',
        '端到端',
    ]
    negative_markers = ['不涉及', '无需', '不需要', 'not required', 'not needed', 'not applicable']
    return any(marker in normalized for marker in e2e_markers) and not any(
        marker in normalized for marker in negative_markers
    )


def _requirements_text_has_real_browser_contract_marker(text: str) -> bool:
    for line in text.splitlines():
        normalized = _normalized_requirements_text(line)
        if not normalized or _is_markdown_table_separator(normalized):
            continue
        has_browser = any(
            marker in normalized
            for marker in [
                'real browser proof',
                'real browser evidence',
                'browser proof',
                'playwright proof',
                '真实浏览器证明',
                '真实浏览器证据',
                '浏览器证明',
                '真实浏览器',
            ]
        )
        has_contract = any(
            marker in normalized
            for marker in ['prototype', '原型', 'ui contract', 'ui 合约', 'web', 'production ui', '生产 ui']
        )
        if has_browser and has_contract:
            return True
    return False


def _requirements_content_without_e2e_review_section(content: str) -> str:
    lines = content.splitlines()
    output: list[str] = []
    skipping = False
    skip_level = 0
    for line in lines:
        heading = _requirements_markdown_heading(line)
        if heading:
            level, heading_text = heading
            normalized = _normalized_requirements_text(heading_text)
            if '4.6' in normalized and (
                'e2e' in normalized or '测试方法' in normalized or 'prerequisite' in normalized
            ):
                skipping = True
                skip_level = level
                continue
            if skipping and level <= skip_level:
                skipping = False
        if not skipping:
            output.append(line)
    return '\n'.join(output)


def _requirements_e2e_review_section(content: str) -> str:
    return (
        _markdown_section(content, 'E2E Test Method & Prerequisite Matrix')
        or _markdown_section(content, 'E2E 测试方法')
        or _markdown_section(content, '4.6 E2E')
    )


def _requirements_e2e_review_rows(section: str) -> tuple[list[dict[str, str]], str | None]:
    header_indices: dict[str, int] | None = None
    active_header_indices: dict[str, int] | None = None
    rows: list[dict[str, str]] = []
    lines = section.splitlines()
    for index, line in enumerate(lines):
        if _is_markdown_table_separator(line):
            continue
        cells = _markdown_table_cells(line)
        if not cells:
            active_header_indices = None
            continue
        if _requirements_e2e_review_header(cells):
            header_indices = _requirements_e2e_review_indices(cells)
            active_header_indices = header_indices
            continue
        next_line_is_separator = index + 1 < len(lines) and _is_markdown_table_separator(lines[index + 1])
        if next_line_is_separator:
            active_header_indices = None
            continue
        if active_header_indices is None:
            continue
        row = {
            key: _cell_at(cells, active_header_indices.get(key))
            for key, _label in _REQUIREMENTS_E2E_REVIEW_COLUMNS
        }
        if not any(value.strip() for value in row.values()):
            continue
        rows.append(row)

    if header_indices is None:
        return [], (
            'Requirements 4.6 E2E review matrix missing fixed columns: '
            + ', '.join(label for _key, label in _REQUIREMENTS_E2E_REVIEW_COLUMNS)
        )
    missing = [
        label
        for key, label in _REQUIREMENTS_E2E_REVIEW_COLUMNS
        if key not in header_indices
    ]
    if missing:
        return rows, 'Requirements 4.6 E2E review matrix missing fixed column(s): ' + ', '.join(missing)
    return rows, None


def _requirements_e2e_review_header(cells: list[str]) -> bool:
    normalized = {_normalized_table_header(cell) for cell in cells}
    return 'acjourney' in normalized and 'e2emethod' in normalized


def _requirements_e2e_review_indices(cells: list[str]) -> dict[str, int]:
    expected = {
        _normalized_table_header(label): key
        for key, label in _REQUIREMENTS_E2E_REVIEW_COLUMNS
    }
    indices: dict[str, int] = {}
    for index, cell in enumerate(cells):
        key = expected.get(_normalized_table_header(cell))
        if key:
            indices[key] = index
    return indices


def _requirements_e2e_review_row_ids(rows: list[dict[str, str]]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        ids.update(_requirements_ac_ids_in_text(row.get('ac_journey', '')))
        ids.update(_requirements_journey_ids_in_text(row.get('ac_journey', '')))
    return ids


def _requirements_e2e_ac_is_covered_by_review_row(
    ac_id: str,
    row_ids: set[str],
    e2e_journey_ac_map: dict[str, set[str]],
) -> bool:
    if ac_id in row_ids:
        return True
    for journey_id, journey_ac_ids in e2e_journey_ac_map.items():
        if journey_id in row_ids and ac_id in journey_ac_ids:
            return True
    return False


def _requirements_e2e_review_row_has_required_mapping(
    row: dict[str, str],
    e2e_ac_ids: set[str],
    e2e_journey_ids: set[str],
) -> bool:
    mapped_ids = _requirements_ac_ids_in_text(row.get('ac_journey', '')) | _requirements_journey_ids_in_text(
        row.get('ac_journey', '')
    )
    return bool(mapped_ids & (e2e_ac_ids | e2e_journey_ids))


def _requirements_e2e_review_row_quality_issues(row: dict[str, str], label: str) -> list[str]:
    issues: list[str] = []
    for key, column_label in _REQUIREMENTS_E2E_REVIEW_COLUMNS:
        if _requirements_e2e_cell_is_placeholder(row.get(key, '')):
            issues.append(f'{label} Requirements 4.6 {column_label} is empty or placeholder')

    if not _requirements_e2e_method_is_specific(row.get('method', '')):
        issues.append(f'{label} Requirements 4.6 E2E Method must name a real browser/end-to-end method')
    if not _requirements_e2e_entrypoint_is_real(row.get('entrypoint', '')):
        issues.append(f'{label} Requirements 4.6 Real Entrypoint must be a real route, URL, page, command, or service entrypoint')
    if not _requirements_e2e_user_steps_are_specific(row.get('user_steps', '')):
        issues.append(f'{label} Requirements 4.6 User Steps must describe concrete user actions')
    if not _requirements_e2e_fixture_is_specific(row.get('fixture', '')):
        issues.append(f'{label} Requirements 4.6 Fixture / Test Data / Setup must define fixed data or setup')
    if not _requirements_e2e_command_intent_is_specific(row.get('command', '')):
        issues.append(
            f'{label} Requirements 4.6 Verification Command must describe a non-placeholder '
            'verification command intent; exact command belongs in Unit Plan'
        )
    if _normalized_table_value(row.get('environment_kind', '')) not in REAL_E2E_ENVIRONMENT_KINDS:
        issues.append(
            f"{label} Requirements 4.6 Environment Kind must be local_real or production_readonly, not "
            f"{row.get('environment_kind') or 'missing'}"
        )
    if _requirements_e2e_mock_policy_allows_core_api_mock(row.get('mock_policy', '')):
        issues.append(f'{label} Requirements 4.6 Mock Policy must not allow core API mock/stub routes')
    if not _requirements_e2e_assertions_are_strong(row.get('assertions', '')):
        issues.append(
            f'{label} Requirements 4.6 Expected Assertions must contain concrete machine-checkable assertions; '
            'screenshots or human observation cannot be the only assertion'
        )
    return issues


def _requirements_e2e_cell_is_placeholder(value: str) -> bool:
    normalized = _normalized_table_value(value)
    if not normalized:
        return True
    compact = re.sub(r'[\s`*_，。:：;；、,./\\|-]+', '', normalized)
    placeholders = {
        'tbd',
        'todo',
        'pending',
        'na',
        'n/a',
        'none',
        'null',
        'unknown',
        '待补',
        '待确认',
        '未指定',
        '暂无',
        '无',
        '不涉及',
        '待unitplan映射',
        'expectedcommand',
        '待unitplan补充',
    }
    return normalized in placeholders or compact in placeholders


def _requirements_e2e_method_is_specific(value: str) -> bool:
    normalized = _normalized_table_value(value)
    if _requirements_e2e_cell_is_placeholder(value):
        return False
    method_markers = ['playwright', 'cypress', 'browser', 'end-to-end', 'end to end', 'e2e', 'pytest', '浏览器', '端到端']
    return any(marker in normalized for marker in method_markers)


def _requirements_e2e_entrypoint_is_real(value: str) -> bool:
    normalized = _normalized_table_value(value)
    if _requirements_e2e_cell_is_placeholder(value):
        return False
    invalid_markers = ['requirements-draft', 'prototype-review', 'prototype manifest', 'screenshot', '截图', 'artifact only']
    if any(marker in normalized for marker in invalid_markers):
        return False
    clean_value = re.sub(r'[`*_]+', '', str(value or '')).strip()
    return bool(
        re.search(r'https?://|(?:^|\s)/[A-Za-z0-9_./:-]+', clean_value)
        or any(marker in normalized for marker in ['route', 'url', 'page', 'command', 'cli', 'service', '生产', '真实'])
    )


def _requirements_e2e_user_steps_are_specific(value: str) -> bool:
    normalized = _normalized_table_value(value)
    if _requirements_e2e_cell_is_placeholder(value):
        return False
    action_markers = [
        'open',
        'click',
        'submit',
        'login',
        'navigate',
        'select',
        'type',
        'create',
        '打开',
        '点击',
        '提交',
        '登录',
        '选择',
        '输入',
        '创建',
    ]
    return ('->' in value or len(normalized.split()) >= 4) and any(marker in normalized for marker in action_markers)


def _requirements_e2e_fixture_is_specific(value: str) -> bool:
    normalized = _normalized_table_value(value)
    if _requirements_e2e_cell_is_placeholder(value):
        return False
    fixture_markers = [
        'fixture',
        'seed',
        'test data',
        'setup',
        'migration',
        'database',
        'db',
        'account',
        'user',
        '测试数据',
        '固定数据',
        '测试账号',
        '初始化',
        '迁移',
    ]
    return any(marker in normalized for marker in fixture_markers)


def _requirements_e2e_command_intent_is_specific(value: str) -> bool:
    normalized = _normalized_table_value(value)
    if _requirements_e2e_cell_is_placeholder(value):
        return False
    generic_patterns = [
        r'^(?:npx\s+|pnpm\s+exec\s+|npm\s+exec\s+)?playwright\s+test$',
        r'^pytest$',
        r'^python\s+-m\s+pytest$',
        r'^go\s+test$',
        r'^browser\s+test$',
        r'^e2e\s+test$',
        r'^expected\s+playwright\s+command$',
        r'^后续测试验证$',
        r'^后续验证$',
        r'^测试验证$',
    ]
    if any(re.fullmatch(pattern, normalized) for pattern in generic_patterns):
        return False
    exact_command_markers = [
        'playwright',
        'cypress',
        'pytest',
        'npm',
        'pnpm',
        'yarn',
        'bun',
        'python',
        'go test',
        'jest',
        'vitest',
        'curl',
    ]
    command_family_markers = exact_command_markers + [
        'go service',
        'service/api',
        'api/service',
        'service e2e',
        'api e2e',
        'browser e2e',
        'command',
        '命令',
    ]
    intent_markers = [
        'e2e',
        'end-to-end',
        'end to end',
        'integration',
        'real',
        'production',
        'local_real',
        'browser',
        'service',
        'api',
        '端到端',
        '集成',
        '真实',
        '生产',
        '浏览器',
    ]
    target_markers = bool(
        re.search(r'\btests?/', value)
        or re.search(r'\.(?:spec|test)\.(?:ts|tsx|js|jsx|py)\b', value)
        or re.search(r'\s--(?:grep|project|config|headed|browser)\b', value)
        or re.search(r'\bservices?/[A-Za-z0-9_.-]+', value)
        or re.search(r'\b[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+', value)
        or re.search(r'/(?:api|service|services|routes?|pages?)(?:/|\b)', value, flags=re.IGNORECASE)
    )
    command_text = value.replace('`', '').strip()
    has_shell_script_command = bool(
        re.search(r'^(?:bash|sh)\s+[^\s`|;&]+\.sh(?:\s|$)', command_text)
        or re.search(r'^(?:\./|/|[^\s`|;&]+/)[^\s`|;&]*\.sh(?:\s|$)', command_text)
    )
    if has_shell_script_command:
        return True
    has_command_family = any(marker in normalized for marker in command_family_markers)
    has_verification_intent = any(marker in normalized for marker in intent_markers)
    if not has_command_family or not has_verification_intent:
        return False
    if target_markers:
        return True
    if 'unit plan' in normalized and any(marker in normalized for marker in ['must create', 'create', '生成', '补齐']):
        return has_verification_intent and any(
            marker in normalized
            for marker in ['service', 'api', 'browser', 'route', 'component', 'services/', '真实', '生产']
        )
    return any(marker in normalized for marker in exact_command_markers) and len(normalized.split()) >= 3


def _requirements_e2e_mock_policy_allows_core_api_mock(value: str) -> bool:
    normalized = _normalized_table_value(value).replace('`', '')
    if _requirements_e2e_cell_is_placeholder(value):
        return True
    risky_markers = [
        'core api mock',
        'core api stub',
        'mock core api',
        'stub core api',
        'page.route',
        'route.fulfill',
        'mock api server',
        'mocked api',
        'stubbed api',
        'fixture-only server',
        '核心 api mock',
        '核心业务 api mock',
    ]
    if not any(marker in normalized for marker in risky_markers):
        return False
    negated_patterns = [
        r'\bno\b.{0,80}(core api|page\.route|route\.fulfill|mock|stub)',
        r'\bwithout\b.{0,80}(core api|page\.route|route\.fulfill|mock|stub)',
        r'(禁止|不得|不允许|不能|不).{0,80}(core api|核心|page\.route|route\.fulfill|mock|stub)',
    ]
    return not any(re.search(pattern, normalized) for pattern in negated_patterns)


def _requirements_e2e_assertions_are_strong(value: str) -> bool:
    normalized = _normalized_table_value(value)
    if _requirements_e2e_cell_is_placeholder(value):
        return False
    weak_markers = ['screenshot', '截图', 'human observation', '人工观察', 'manual observe', 'reviewer observes']
    strong_markers = [
        'assert',
        'expect',
        'equals',
        'count',
        'status',
        'field',
        'row',
        'database',
        'persist',
        'api',
        'dom',
        'text',
        'value',
        'sorting',
        'order',
        'permission',
        'export',
        'confirmation',
        'id',
        '断言',
        '数量',
        '状态',
        '字段',
        '持久化',
        '排序',
        '权限',
        '导出',
        '文案',
    ]
    return any(marker in normalized for marker in strong_markers) and not (
        any(marker in normalized for marker in weak_markers)
        and not any(marker in normalized for marker in strong_markers)
    )


def _requirements_journey_ids_in_text(text: str) -> set[str]:
    return journey_ids_in_text(text)


def _normalized_table_header(value: str) -> str:
    return re.sub(r'[\s`*_/\-|（）()]+', '', str(value or '').strip().lower())


def _normalized_table_value(value: str) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip().strip('`*_')).strip().lower()


def _cell_at(cells: list[str], index: int | None) -> str:
    if index is None or index < 0 or index >= len(cells):
        return ''
    return cells[index]


def _requirements_target_infrastructure_required(state: dict[str, Any]) -> bool:
    target_keys = [
        'requestedOutcome',
        'feasibleOutcome',
        'currentUnitId',
        'task_id',
        'workspacePath',
        'executionWorkspacePath',
    ]
    return any(str(state.get(key) or '').strip() for key in target_keys) or bool(state.get('units'))


def _requirements_target_infrastructure_issues(content: str) -> list[str]:
    section = _markdown_section(content, '目标项目基础设施信息')
    if not section.strip():
        return [
            'Requirements Gate missing `## 4.9 目标项目基础设施信息`; '
            'add concrete target project infrastructure facts before Requirements approval'
        ]

    issues: list[str] = []
    clarification_section = _markdown_section(content, '已澄清事项')
    for label, aliases in _REQUIREMENTS_INFRASTRUCTURE_CATEGORIES:
        category_text = _requirements_infrastructure_category_text(section, label, aliases)
        if not category_text.strip():
            issues.append(
                f'Requirements Gate `## 4.9 目标项目基础设施信息` missing infrastructure category: {label}'
            )
            continue
        if _requirements_infrastructure_category_is_placeholder(category_text, aliases):
            issues.append(
                f'Requirements Gate `## 4.9 目标项目基础设施信息` category {label} '
                'is empty or placeholder; replace placeholder text with concrete facts or a specific 不涉及 reason'
            )
            continue
        issues.extend(
            _requirements_infrastructure_absence_traceability_issues(label, category_text, clarification_section)
        )
        issues.extend(
            _requirements_infrastructure_claim_traceability_issues(label, category_text, clarification_section)
        )
        if label == '文档地址':
            issues.extend(_requirements_document_address_quality_issues(category_text))
    return issues


def _requirements_infrastructure_absence_traceability_issues(
    label: str,
    category_text: str,
    clarification_section: str,
) -> list[str]:
    normalized = _normalized_requirements_text(category_text)
    absence_markers = ['未发现', '没有', '当前没有', '不涉及', '暂不清楚']
    if not any(marker in normalized for marker in absence_markers):
        return []

    if any(marker in normalized for marker in ['暂不清楚', '不清楚']):
        return [
            f'Requirements Gate `## 4.9 目标项目基础设施信息` category {label} states an unclear or unknown value; '
            'replace it with checked sources, user confirmation recorded in 4.8, or a specific reason'
        ]

    if '用户确认' in normalized:
        if _requirements_clarification_records_user_confirmation(clarification_section):
            return []
        return [
            f'Requirements Gate `## 4.9 目标项目基础设施信息` category {label} claims 用户确认, '
            'but `## 4.8` lacks the corresponding 用户确认问答 record'
        ]

    if _requirements_infrastructure_text_has_checked_sources(normalized):
        return []
    if _requirements_infrastructure_text_has_specific_absence_reason(normalized):
        return []

    return [
        f'Requirements Gate `## 4.9 目标项目基础设施信息` category {label} states 未发现/没有/不涉及 '
        'but must include 已检查 sources, 用户确认 recorded in 4.8, or a specific reason'
    ]


def _requirements_infrastructure_claim_traceability_issues(
    label: str,
    category_text: str,
    clarification_section: str,
) -> list[str]:
    normalized = _normalized_requirements_text(category_text)
    issues: list[str] = []
    absence_markers = ['未发现', '没有', '当前没有', '不涉及', '暂不清楚']
    if (
        '用户确认' in normalized
        and not any(marker in normalized for marker in absence_markers)
        and not _requirements_clarification_records_user_confirmation(clarification_section)
    ):
        issues.append(
            f'Requirements Gate `## 4.9 目标项目基础设施信息` category {label} claims 用户确认, '
            'but `## 4.8` lacks the corresponding 用户确认问答 record'
        )
    verified_markers = ['已验证', '验证通过', '已核实', 'verified']
    if any(marker in normalized for marker in verified_markers):
        if not _requirements_clarification_records_validation(clarification_section):
            issues.append(
                f'Requirements Gate `## 4.9 目标项目基础设施信息` category {label} claims 已验证, '
                'but `## 4.8` lacks 验证方式 / 验证结论 record'
            )
    return issues


def _requirements_infrastructure_text_has_checked_sources(normalized: str) -> bool:
    check_markers = ['已检查', '检查了', '已核对', '核对了', 'checked', 'inspected']
    source_markers = [
        'docs',
        'readme',
        'usage',
        '.rrc-controller',
        'artifacts',
        'state-dir',
        'package',
        'manifest',
        '配置',
        '测试命令',
        'repo',
        '仓库',
    ]
    return any(marker in normalized for marker in check_markers) and any(
        marker in normalized for marker in source_markers
    )


def _requirements_infrastructure_text_has_specific_absence_reason(normalized: str) -> bool:
    reason_markers = [
        '因为',
        '由于',
        '原因',
        '不适用',
        '不属于',
        '测试 fixture',
        '测试目标',
        '无外部资料',
        '无需',
        '本轮',
        '后续如需',
    ]
    return any(marker in normalized for marker in reason_markers)


def _requirements_clarification_records_user_confirmation(clarification_section: str) -> bool:
    normalized = _normalized_requirements_text(clarification_section)
    if not normalized:
        return False
    has_question = any(marker in normalized for marker in ['追问', '问题', '提问', 'question'])
    has_answer = any(marker in normalized for marker in ['用户回答', '回答：', '用户确认', 'answer'])
    return has_question and has_answer


def _requirements_clarification_records_validation(clarification_section: str) -> bool:
    normalized = _normalized_requirements_text(clarification_section)
    if not normalized:
        return False
    has_method = any(marker in normalized for marker in ['核对方式', '验证方式', '检查方式', '已检查', '已核对'])
    has_conclusion = any(marker in normalized for marker in ['验证结论', '核对结论', '结论'])
    return has_method and has_conclusion


def _requirements_document_address_quality_issues(text: str) -> list[str]:
    cleaned = _normalized_infrastructure_category_content(text, ('文档地址', '文档来源'))
    normalized = _normalized_requirements_text(cleaned).strip()
    compact = re.sub(r'[\s`*_，。:：;；、,./\\|-]+', '', normalized)
    if not normalized:
        return ['Requirements Gate `## 4.9 目标项目基础设施信息` category 文档地址 is empty or placeholder']

    vague_values = {
        'docs',
        'doc',
        'documents',
        'documentation',
        'readme',
        'readmeusage',
        'usagereadme',
        'readmeusageroadmap',
        '暂无',
        '无',
        'none',
        'na',
    }
    if compact in vague_values:
        return [
            'Requirements Gate `## 4.9 目标项目基础设施信息` category 文档地址 is too vague; '
            'inventory formal docs, controller evidence, external agent/human docs, external wiki/design/API docs, '
            'and missing docs with usage or credibility'
        ]

    generic_doc_terms = [
        'docs',
        'readme',
        'usage',
        'roadmap',
        'task_plan',
        'progress',
        'findings',
    ]
    has_only_generic_sources = all(
        token in generic_doc_terms
        for token in re.findall(r'[a-z_]+', normalized)
    ) and any(term in normalized for term in generic_doc_terms)
    purpose_or_credibility_markers = [
        '用途',
        '可信',
        '作为',
        '用于',
        '入口',
        '登记',
        '审计',
        '证据',
        '维护',
        'source',
        'purpose',
        'credibility',
        'audit',
        'evidence',
        'registry',
        'maintained',
    ]
    if has_only_generic_sources and not any(marker in normalized for marker in purpose_or_credibility_markers):
        return [
            'Requirements Gate `## 4.9 目标项目基础设施信息` category 文档地址 lists generic files '
            'without usage or credibility'
        ]

    structured_markers = [
        '正式维护文档',
        'controller 过程证据',
        '过程证据',
        '外部 agent',
        '人工沟通',
        '外部 wiki',
        '设计稿',
        'api 文档',
        '缺失但需要沉淀',
    ]
    if not any(marker in normalized for marker in structured_markers):
        return [
            'Requirements Gate `## 4.9 目标项目基础设施信息` category 文档地址 must be a structured inventory, '
            'not a flat path list'
        ]
    return []


def _requirements_infrastructure_category_text(section: str, label: str, aliases: tuple[str, ...]) -> str:
    matches: list[str] = []
    lines = section.splitlines()
    for index, line in enumerate(lines):
        heading = _requirements_markdown_heading(line)
        if not heading:
            continue
        heading_level, heading_text = heading
        normalized_heading = _normalized_requirements_text(heading_text)
        if not _requirements_infrastructure_category_matches(normalized_heading, label, aliases):
            continue
        category_lines = [line]
        for nested_line in lines[index + 1:]:
            nested_heading = _requirements_markdown_heading(nested_line)
            if nested_heading and nested_heading[0] <= heading_level:
                break
            category_lines.append(nested_line)
        matches.append('\n'.join(category_lines))

    for index, line in enumerate(lines):
        if _requirements_markdown_heading(line):
            continue
        normalized = _normalized_requirements_text(line)
        if not normalized or _is_markdown_table_separator(normalized):
            continue
        if _requirements_infrastructure_category_matches(normalized, label, aliases):
            category_lines = [line]
            base_indent = len(line) - len(line.lstrip())
            for nested_line in lines[index + 1:]:
                if _requirements_markdown_heading(nested_line):
                    break
                nested_normalized = _normalized_requirements_text(nested_line)
                nested_indent = len(nested_line) - len(nested_line.lstrip())
                if (
                    nested_normalized
                    and nested_indent <= base_indent
                    and any(
                        _requirements_infrastructure_category_matches(nested_normalized, other_label, other_aliases)
                        for other_label, other_aliases in _REQUIREMENTS_INFRASTRUCTURE_CATEGORIES
                        if other_label != label
                    )
                ):
                    break
                if nested_line.strip():
                    category_lines.append(nested_line)
            matches.append('\n'.join(category_lines))
    return '\n'.join(matches)


def _requirements_markdown_heading(line: str) -> tuple[int, str] | None:
    match = re.match(r'^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$', line)
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


def _requirements_infrastructure_category_matches(normalized: str, label: str, aliases: tuple[str, ...]) -> bool:
    if label == '架构/交互逻辑/接口说明':
        return (
            any(_normalized_requirements_text(alias) in normalized for alias in aliases)
            or all(term in normalized for term in ['架构', '交互', '接口'])
        )
    return any(_normalized_requirements_text(alias) in normalized for alias in aliases)


def _requirements_infrastructure_category_is_placeholder(text: str, aliases: tuple[str, ...]) -> bool:
    cleaned = _normalized_infrastructure_category_content(text, aliases)
    if not cleaned:
        return True
    lowered = cleaned.lower()
    if re.fullmatch(r'(?:tbd|todo|pending|unknown|n/?a|none|null|待补|不清楚|未知|待确认|暂缺|暂无|无|没有|不涉及|-|—|_)+', lowered):
        return True
    placeholder_terms = ['tbd', 'todo', 'pending', '待补', '不清楚', '待确认', '暂缺', '暂无']
    if any(term in lowered for term in placeholder_terms):
        return True
    if lowered in {'无', '不涉及', '没有', '未知', 'unknown', 'none'}:
        return True
    if '不涉及' in lowered:
        reason = lowered.replace('不涉及', '')
        reason = re.sub(r'[\s:：，。,.；;、`*_|\-—]+', '', reason)
        return len(reason) < 6
    return False


def _normalized_infrastructure_category_content(text: str, aliases: tuple[str, ...]) -> str:
    cleaned = re.sub(r'(?m)^\s*[-*+]\s*', '', text)
    cleaned = re.sub(r'(?m)^\s{0,3}#{1,6}\s*', '', cleaned)
    cleaned = cleaned.replace('|', ' ')
    for alias in aliases:
        cleaned = re.sub(re.escape(alias), ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'[\s:：，。,.；;、`*_|\-—]+', ' ', cleaned).strip()
    return cleaned


def _requirements_declares_prototype_contract(content: str, state: dict[str, Any]) -> bool:
    if _is_controller_prototype_policy_gate(state):
        return False
    for line in content.splitlines():
        normalized = _normalized_requirements_text(line)
        if not normalized or _is_markdown_table_separator(normalized):
            continue
        has_prototype = any(
            keyword in normalized
            for keyword in [
                'prototype',
                '原型',
                'clickable webpage prototype',
                'ui contract',
                'ui/ux contract',
                'ui 合约',
                'ui/ux 合约',
            ]
        )
        if not has_prototype:
            continue
        has_contract_signal = any(
            keyword in normalized
            for keyword in [
                'contract',
                '合约',
                'production',
                'implementation',
                'real route',
                '真实 route',
                '真实页面',
                'route',
                'page',
                'must',
                '必须',
                '验收',
            ]
        )
        if has_contract_signal:
            return True
    return False


def _requirements_prototype_contract_content(content: str) -> str:
    match = re.search(r'(?m)^##\s+附录 A：完整需求与验收正文\s*$', content)
    if match:
        return content[match.end():]
    return content


def _requirements_declares_clickable_web_prototype_contract(content: str, state: dict[str, Any]) -> bool:
    return (
        not _is_controller_prototype_policy_gate(state)
        and bool(
            re.search(
                r'(?i)(clickable webpage prototype|web prototype|可点击网页原型|网页原型)',
                content,
            )
        )
    )


def _is_controller_prototype_policy_gate(state: dict[str, Any]) -> bool:
    candidates = [
        state.get('requestedOutcome'),
        state.get('feasibleOutcome'),
        state.get('currentUnitId'),
        state.get('task_id'),
    ]
    return any(
        re.search(r'(?i)v0[.-]6[.-]0[a-z]?|v0-6-0[a-z]?', str(item or ''))
        for item in candidates
    )


def _requirements_need_uiux_prototype(state: dict[str, Any]) -> bool:
    classification = state.get('requirementsSurfaceClassification')
    if (
        isinstance(classification, dict)
        and classification.get('product_ui') == 'not_required'
        and classification.get('prototype_required') == 'not_required'
        and state.get('currentUnitNeedsUiDesign') is not True
    ):
        return False
    return (
        bool(state.get('currentUnitNeedsUiDesign'))
        or _state_declares_target_uiux(state)
        or requirements_surface_requires_product_ui(state)
        or requirements_surface_requires_prototype(state)
    )


def _requirements_need_clickable_web_prototype(state: dict[str, Any]) -> bool:
    classification = state.get('requirementsSurfaceClassification')
    if (
        isinstance(classification, dict)
        and classification.get('web_system') == 'not_required'
        and state.get('currentUnitIsWebSystem') is not True
    ):
        return False
    return (
        bool(state.get('currentUnitIsWebSystem'))
        or _state_declares_target_web_system(state)
        or requirements_surface_requires_web_system(state)
    )


def _requirements_has_uiux_prototype_evidence(content: str) -> bool:
    for evidence in _requirements_evidence_candidate_texts(content):
        if any(keyword in evidence for keyword in ['prototype', '原型', 'design evidence', '设计说明']):
            return True
    return False


def _requirements_has_clickable_web_prototype_evidence(content: str) -> bool:
    evidence_blocks = _requirements_evidence_candidate_texts(content)
    if not evidence_blocks:
        return False
    evidence = '\n'.join(evidence_blocks)
    if not any(keyword in evidence for keyword in [
        'clickable webpage prototype',
        'clickable web prototype',
        'clickable prototype',
        'clickable html',
        'artifact-local clickable html',
        'web prototype evidence',
        '可点击网页原型',
        '可点击原型',
    ]):
        return False
    has_static_only_marker = any(keyword in evidence for keyword in ['静态截图', 'text-only', '纯文字', '不可点击', 'non-clickable', 'wireframe'])
    has_static_only_rejection = any(keyword in evidence for keyword in ['不能作为', '不接受', '不得', 'not accept', 'cannot be used'])
    if has_static_only_marker and not has_static_only_rejection:
        return False

    has_access_method = bool(
        re.search(r'https?://|file://', evidence)
        or any(keyword in evidence for keyword in [
            'access method',
            'start command',
            '启动命令',
            '访问方式',
            'prototype url',
            'local html',
            'artifact-local',
            'manifest path',
            'prototype-manifest.json',
            '.html',
            'review_href',
        ])
    )
    has_page_states = any(keyword in evidence for keyword in ['page states', 'page_states', 'pages ', '页面状态', '关键页面', 'observed page states'])
    has_click_path = any(keyword in evidence for keyword in ['click path', 'click_path', 'clicked ', '点击路径', '核心点击路径'])
    has_ac_mapping = bool(_requirements_ac_ids_in_text(evidence)) and any(
        keyword in evidence for keyword in [
            'maps to',
            'mapped evidence',
            'ac mapping',
            'ac/journey mapping',
            'journey mapping',
            'linked ac',
            'linked_acceptance_criteria',
            '映射',
            '关联 ac',
        ]
    )
    return has_access_method and has_page_states and has_click_path and has_ac_mapping


def _requirements_evidence_candidate_texts(content: str) -> list[str]:
    lines = content.splitlines()
    evidence_blocks: list[str] = []
    for index, line in enumerate(lines):
        normalized = _normalized_requirements_text(line)
        if not _requirements_line_is_evidence_candidate(normalized):
            continue

        block_lines = [line]
        heading = _requirements_markdown_heading(line)
        if heading:
            heading_level, _heading_text = heading
            for nested_line in lines[index + 1:]:
                nested_heading = _requirements_markdown_heading(nested_line)
                if nested_heading and nested_heading[0] <= heading_level:
                    break
                block_lines.append(nested_line)
        evidence_blocks.append(_normalized_requirements_text('\n'.join(block_lines)))
    return evidence_blocks


def _requirements_line_is_evidence_candidate(normalized_line: str) -> bool:
    if not normalized_line:
        return False
    evidence_markers = [
        'prototype evidence',
        'web prototype evidence',
        'manual click evidence',
        'design evidence',
        '原型证据',
        '人工点击证据',
        '可审阅设计说明',
    ]
    if not any(marker in normalized_line for marker in evidence_markers):
        return False
    requirement_only_markers = [
        '必须',
        '要求',
        '缺少',
        '尚未提供',
        '不接受',
        '不得',
        'should',
        'must',
        'requires',
        'required',
        'missing',
    ]
    return not any(marker in normalized_line for marker in requirement_only_markers)


def _normalized_requirements_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text.strip().lower())


def _state_declares_target_uiux(state: dict[str, Any]) -> bool:
    return _state_target_context_has_any(state, ['ui/ux', 'uiux', 'browser ui', 'web ui', 'frontend', '页面', '工作台'])


def _state_declares_target_web_system(state: dict[str, Any]) -> bool:
    return _state_target_context_has_any(state, ['web system', 'web系统', 'web 系统', 'web app', 'webapp', '网页系统'])


def _state_target_context_has_any(state: dict[str, Any], indicators: list[str]) -> bool:
    context_keys = [
        'targetProjectType',
        'target_project_type',
        'targetProjectKind',
        'target_project_kind',
        'targetProjectContext',
        'target_project_context',
        'requirementsTargetType',
        'requirements_target_type',
    ]
    values = [
        _normalized_requirements_text(str(state.get(key) or ''))
        for key in context_keys
        if state.get(key)
    ]
    return any(indicator in value for value in values for indicator in indicators)


def _prototype_conformance_case_issue(
    case: dict[str, Any],
    target: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> str:
    command = str(case.get('command') or '').strip()
    expected = str(case.get('expected') or case.get('expected_result') or case.get('expectedResult') or '').strip()
    layer = str(case.get('layer') or '').strip().lower()
    surface_kind = str((contract or {}).get('surface_kind') or '').strip().lower()
    if not command:
        return 'missing command'
    if _prototype_command_is_static_artifact_check(command):
        return 'command only opens static prototype artifact, not production UI'
    if (implementation_target_is_browser_route(target) or surface_contract_requires_browser_e2e(surface_kind)) and layer != 'e2e':
        return 'browser route target requires e2e layer'
    if surface_kind and not _case_user_steps(case):
        return 'missing user_steps from production entrypoint'
    if _expected_is_weak(expected):
        return 'missing concrete expected assertion'
    fidelity_required = normalize_fidelity_required((contract or {}).get('fidelity_required'))
    case_fidelity = normalize_fidelity_required(
        case.get('fidelity_required') or case.get('fidelityRequired'),
        default=fidelity_required,
    )
    if fidelity_rank(case_fidelity) < fidelity_rank(fidelity_required):
        return f'fidelity_required {case_fidelity} is below contract {fidelity_required}'
    visual_plan_issue = _prototype_visual_evidence_plan_issue(
        case,
        fidelity_required=fidelity_required,
        requires_interaction=bool(surface_kind or _case_user_steps(case)),
    )
    if visual_plan_issue:
        return visual_plan_issue
    if fidelity_rank(fidelity_required) >= fidelity_rank('pixel_exact') and not _case_has_l4_visual_plan(case):
        return 'missing L4 pixel-exact evidence plan'
    if fidelity_rank(fidelity_required) >= fidelity_rank('screenshot_regression') and not _case_has_l3_visual_plan(case):
        return 'missing L3 screenshot regression evidence plan'
    if fidelity_rank(fidelity_required) >= fidelity_rank('structural_interaction') and _prototype_expected_lacks_l2_assertions(case):
        return 'missing L2 structural/interaction assertions'
    return ''


def _prototype_visual_evidence_plan_issue(
    case: dict[str, Any],
    *,
    fidelity_required: str,
    requires_interaction: bool,
) -> str:
    plan = case_visual_evidence_plan(case)
    if not plan.get('prototype_screenshot') or not plan.get('production_screenshot'):
        return 'missing L1 visual evidence plan'
    if fidelity_rank(fidelity_required) >= fidelity_rank('structural_interaction'):
        if not _case_visual_plan_list(plan.get('action_path')):
            return 'missing L2 action path evidence plan'
        if requires_interaction and not plan.get('interaction_screenshot'):
            return 'missing L2 interaction screenshot evidence plan'
    return ''


def _case_visual_plan_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r'[,;\n]', text) if part.strip()]


def _case_has_l3_visual_plan(case: dict[str, Any]) -> bool:
    plan = case_visual_evidence_plan(case)
    if plan.get('screenshot_regression'):
        return True
    return any(
        case.get(key) is not None
        for key in ('screenshot_regression', 'screenshotRegression', 'visual_regression', 'visualRegression')
    )


def _case_has_l4_visual_plan(case: dict[str, Any]) -> bool:
    plan = case_visual_evidence_plan(case)
    if plan.get('pixel_exact') or plan.get('pixel_diff') or plan.get('pixel_tolerance'):
        return True
    return any(
        case.get(key) is not None
        for key in ('pixel_exact', 'pixelExact', 'pixel_tolerance', 'pixelTolerance', 'pixel_diff', 'pixelDiff')
    )


def _prototype_expected_lacks_l2_assertions(case: dict[str, Any]) -> bool:
    expected = str(case.get('expected') or case.get('expected_result') or case.get('expectedResult') or '')
    combined = ' '.join([expected, ' '.join(_case_user_steps(case))]).lower()
    structure_terms = (
        'layout',
        'order',
        'ordering',
        'region',
        'section',
        'panel',
        'dialog',
        'drawer',
        'form',
        'tab',
        'button',
        'card',
        'list',
        'count',
        'state',
        'placement',
        'size',
        'visual',
        'prototype',
        '信息架构',
        '布局',
        '顺序',
        '区域',
        '面板',
        '弹窗',
        '抽屉',
        '按钮',
        '页签',
        '列表',
        '数量',
        '状态',
        '遮挡',
    )
    interaction_terms = (
        'click',
        'after clicking',
        'open',
        'opens',
        'toggle',
        'select',
        'submit',
        'hover',
        'tab',
        'route',
        'entrypoint',
        '点击',
        '打开',
        '切换',
        '选择',
        '保存',
        '提交',
        '入口',
    )
    return not (
        any(term in combined for term in structure_terms)
        and any(term in combined for term in interaction_terms)
    )


def _prototype_command_is_static_artifact_check(command: str) -> bool:
    normalized = command.replace('\\', '/').lower()
    static_needles = [
        'requirements-draft/prototypes',
        'prototype-review',
        'plannotator-review',
        'prototype-manifest',
        'prototype-review-manifest',
    ]
    if any(needle in normalized for needle in static_needles):
        return True
    return 'file://' in normalized and 'prototype' in normalized


def _prototype_target_label(target: dict[str, Any]) -> str:
    kind = str(target.get('kind') or '').strip()
    path = str(target.get('path') or '').strip()
    if kind and path:
        return f'{kind}:{path}'
    return path or kind or 'unknown-target'


def _prototype_contract_label(contract: dict[str, Any]) -> str:
    prototype_id = str(contract.get('prototype_id') or 'unknown-prototype').strip()
    surface_id = str(contract.get('surface_id') or '').strip()
    target = contract.get('target') if isinstance(contract.get('target'), dict) else {}
    target_label = _prototype_target_label(target)
    if surface_id:
        return f'prototype {prototype_id} surface {surface_id} target {target_label}'
    return f'prototype {prototype_id} target {target_label}'


def _case_user_steps(case: dict[str, Any]) -> list[str]:
    raw = case.get('user_steps') or case.get('userSteps') or case.get('steps')
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw).strip()
    return [text] if text else []


def _requirements_has_design_architecture_matrix(content: str) -> bool:
    return bool(_markdown_section(content, 'Design/Architecture Traceability Matrix'))


def _requirements_design_architecture_traceability(content: str) -> dict[str, dict[str, set[str]]]:
    section = _markdown_section(content, 'Design/Architecture Traceability Matrix')
    trace: dict[str, dict[str, set[str]]] = {}
    if not section:
        return trace

    for line in section.splitlines():
        cells = _markdown_table_cells(line)
        if len(cells) < 3:
            continue
        ac_ids = _requirements_ac_ids_in_text(cells[0])
        if not ac_ids:
            continue
        product_design_refs = _requirements_trace_refs_from_cell(cells[1])
        technical_architecture_refs = _requirements_trace_refs_from_cell(cells[2])
        for ac_id in ac_ids:
            item = trace.setdefault(
                ac_id,
                {'product_design_refs': set(), 'technical_architecture_refs': set()},
            )
            item['product_design_refs'].update(product_design_refs)
            item['technical_architecture_refs'].update(technical_architecture_refs)
    return trace


def _requirements_acceptance_criterion_ids(content: str) -> set[str]:
    return _requirements_current_ac_ids_in_text(content)


def _requirements_current_ac_ids_in_text(content: str) -> set[str]:
    ids: set[str] = set()
    source_ac_indices: set[int] | None = None
    source_provenance_section_level: int | None = None
    for line in content.splitlines():
        heading = _requirements_markdown_heading(line)
        if heading:
            level, heading_text = heading
            if source_provenance_section_level is not None and level <= source_provenance_section_level:
                source_provenance_section_level = None
            if _requirements_heading_is_source_ac_provenance(heading_text):
                source_provenance_section_level = level
        if _is_markdown_table_separator(line):
            continue
        cells = _markdown_table_cells(line)
        if cells:
            header_source_indices = _requirements_source_ac_table_indices(cells)
            if header_source_indices is not None:
                source_ac_indices = header_source_indices
                continue
            if source_ac_indices is not None:
                for index, cell in enumerate(cells):
                    if index in source_ac_indices:
                        continue
                    ids.update(_requirements_ac_ids_in_text(cell))
                continue
            ids.update(_requirements_ac_ids_in_text(line))
            continue
        source_ac_indices = None
        if (
            source_provenance_section_level is not None
            and not _requirements_line_is_explicit_current_ac_declaration(line)
        ):
            continue
        if _requirements_line_is_source_ac_provenance(line):
            continue
        ids.update(_requirements_ac_ids_in_text(line))
    return ids


def _requirements_source_ac_table_indices(cells: list[str]) -> set[int] | None:
    indices: set[int] = set()
    normalized_cells = [_normalized_table_header(cell) for cell in cells]
    table_has_ac_context = any(
        'ac' in value or 'acceptancecriterion' in value or 'acceptancecriteria' in value
        for value in normalized_cells
    )
    for index, cell in enumerate(cells):
        raw = str(cell or '').strip().lower()
        normalized = normalized_cells[index]
        if normalized in {
            'currentac',
            'currentacs',
            'currentacceptancecriterion',
            'currentacceptancecriteria',
            'canonicalac',
            'canonicalacs',
            'targetac',
            'targetacs',
        }:
            continue
        if normalized in {
            'sourceac',
            'sourceacs',
            'sourceactc',
            'importedac',
            'importedacs',
            'originalac',
            'originalacs',
            'sourceid',
            'sourceids',
            'importedid',
            'importedids',
            'originalid',
            'originalids',
            'sourceacceptancecriterion',
            'sourceacceptancecriteria',
            'sourceacceptancecriterionid',
            'sourceacceptancecriteriaid',
            'sourceacceptancecriterionids',
            'sourceacceptancecriteriaids',
            'importedacceptancecriterion',
            'importedacceptancecriteria',
            'importedacceptancecriterionid',
            'importedacceptancecriteriaid',
            'importedacceptancecriterionids',
            'importedacceptancecriteriaids',
            'originalacceptancecriterion',
            'originalacceptancecriteria',
            'originalacceptancecriterionid',
            'originalacceptancecriteriaid',
            'originalacceptancecriterionids',
            'originalacceptancecriteriaids',
        }:
            indices.add(index)
            continue
        if normalized == 'source' and table_has_ac_context:
            indices.add(index)
            continue
        if normalized in {'imported', 'original'} and table_has_ac_context:
            indices.add(index)
            continue
        if normalized.startswith('source') and (
            normalized.endswith('ac')
            or 'actc' in normalized
            or 'acceptancecriterion' in normalized
            or 'acceptancecriteria' in normalized
        ):
            indices.add(index)
            continue
        if normalized.startswith('imported') and (
            normalized.endswith('ac')
            or 'acceptancecriterion' in normalized
            or 'acceptancecriteria' in normalized
        ):
            indices.add(index)
            continue
        if normalized.startswith('original') and (
            normalized.endswith('ac')
            or 'acceptancecriterion' in normalized
            or 'acceptancecriteria' in normalized
        ):
            indices.add(index)
            continue
        if 'source' in raw and re.search(r'(?:^|[^a-z0-9_])acs?(?:$|[^a-z0-9_])|acceptance\s+criter', raw):
            indices.add(index)
            continue
        if (
            ('imported' in raw or 'original' in raw)
            and re.search(r'(?:^|[^a-z0-9_])acs?(?:$|[^a-z0-9_])|acceptance\s+criter', raw)
        ):
            indices.add(index)
    if not indices:
        return None
    return indices


def _requirements_line_is_explicit_current_ac_declaration(line: str) -> bool:
    return bool(_requirements_inline_ac_layer_pairs(line)) or _requirements_line_starts_with_layer_bucket(line)


def _requirements_heading_is_source_ac_provenance(heading: str) -> bool:
    normalized = _normalized_requirements_text(heading)
    compact = _normalized_table_header(heading)
    if any(
        marker in normalized
        for marker in [
            'source map',
            'source mapping',
            'source provenance',
            'source conversion',
            'conversion artifact',
            'conversion matrix',
            'imported ac',
            'original ac',
            'external spec',
            'source spec',
            'source label',
            'provenance',
        ]
    ):
        return True
    if any(marker in compact for marker in ['sourcemap', 'sourcemapping', 'sourceprovenance']):
        return True
    return any(marker in heading for marker in ['来源', '源映射', '映射说明', '导入', '原始', '转换'])


def _requirements_line_is_source_ac_provenance(line: str) -> bool:
    if not _requirements_ac_ids_in_text(line):
        return False
    if _requirements_line_is_explicit_current_ac_declaration(line):
        return False
    normalized = _normalized_requirements_text(line)
    compact = _normalized_table_header(line)
    strong_markers = [
        'source ac',
        'source spec',
        'source id',
        'source label',
        'source map',
        'source-to-current',
        'source to current',
        'provenance',
        'imported ac',
        'original ac',
        'external spec',
        'conversion artifact',
        'conversion matrix',
    ]
    if any(marker in normalized for marker in strong_markers):
        return True
    if any(marker in compact for marker in ['sourceac', 'sourceactc', 'importedac', 'originalac']):
        return True
    if any(marker in line for marker in ['来源', '源 AC', '源AC', '导入 AC', '导入AC', '原始 AC', '原始AC', '转换']):
        return True
    has_mapping_syntax = (
        '->' in line
        or '→' in line
        or '=>' in line
        or '至' in line
        or '映射' in line
        or 'mapped' in normalized
        or 'maps to' in normalized
        or 'mapping' in normalized
    )
    if re.search(r'\bAC-SPEC-[A-Za-z0-9_-]+\b', line, flags=re.IGNORECASE) and has_mapping_syntax:
        return True
    return False


def _requirements_acceptance_criterion_layers(content: str) -> dict[str, str]:
    layers: dict[str, str] = {}
    for ac_id, layer in _requirements_ac_layer_pairs(content):
        layers.setdefault(ac_id, layer)
    return layers


def _requirements_ac_layer_pairs(content: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    table_indices: dict[str, int] | None = None
    for line in content.splitlines():
        if _is_markdown_table_separator(line):
            continue
        cells = _markdown_table_cells(line)
        if cells:
            header_indices = _requirements_ac_layer_table_indices(cells)
            if header_indices:
                table_indices = header_indices
                continue
            if table_indices:
                ac_cell = _cell_at(cells, table_indices.get('ac'))
                layer_cell = _cell_at(cells, table_indices.get('layer'))
                layer = _normalize_requirements_verification_layer(layer_cell)
                if layer:
                    for ac_id in _requirements_ac_ids_in_text(ac_cell):
                        pairs.append((ac_id, layer))
                continue
            for cell in cells:
                pairs.extend(_requirements_inline_ac_layer_pairs(cell))
            continue
        table_indices = None
        ac_ids = _requirements_ac_ids_in_text(line)
        if not ac_ids:
            continue
        inline_pairs = _requirements_inline_ac_layer_pairs(line)
        if inline_pairs:
            pairs.extend(inline_pairs)
            continue
        if (
            _requirements_line_has_journey_inline_verification_marker(line)
            and not _requirements_line_starts_with_layer_bucket(line)
        ):
            continue
        layer = _requirements_verification_layer_from_line(line)
        if not layer:
            continue
        if len(ac_ids) > 1 and not _requirements_line_starts_with_layer_bucket(line):
            continue
        for ac_id in ac_ids:
            pairs.append((ac_id, layer))
    return pairs


def _requirements_inline_ac_layer_pairs(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    patterns = [
        rf'({AC_ID_PATTERN})\s*\[\s*verification\s*:\s*([A-Za-z0-9_-]+)\s*\]',
        rf'({AC_ID_PATTERN})\s*\(\s*(unit|functional|integration|static|regression|prerequisite|e2e|manual)\s*\)',
        rf'({AC_ID_PATTERN})\s+verification(?:\s+layer)?\s*[:：=]\s*([A-Za-z0-9_-]+)\b',
        rf'({AC_ID_PATTERN})\s+验证(?:层级|层|方式)?\s*[:：]\s*([A-Za-z0-9_-]+|单元|集成|静态|回归|前置|前置条件|前置依赖|端到端|人工)\b',
    ]
    seen: set[tuple[str, str]] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            layer = _normalize_requirements_verification_layer(match.group(2))
            if not layer:
                continue
            pair = (match.group(1).upper(), layer)
            if pair in seen:
                continue
            seen.add(pair)
            pairs.append(pair)
    return pairs


def _requirements_line_has_journey_inline_verification_marker(line: str) -> bool:
    patterns = [
        rf'{JOURNEY_ID_PATTERN}\s*\[\s*verification\s*:\s*[A-Za-z0-9_-]+\s*\]',
        rf'{JOURNEY_ID_PATTERN}\s*\(\s*(?:unit|functional|integration|static|regression|prerequisite|e2e|manual)\s*\)',
        rf'{JOURNEY_ID_PATTERN}\s+verification(?:\s+layer)?\s*[:：=]\s*[A-Za-z0-9_-]+\b',
        rf'{JOURNEY_ID_PATTERN}\s+验证(?:层级|层|方式)?\s*[:：]\s*(?:[A-Za-z0-9_-]+|单元|集成|静态|回归|前置|前置条件|前置依赖|端到端|人工)\b',
    ]
    return any(re.search(pattern, line, re.IGNORECASE) for pattern in patterns)


def _requirements_line_starts_with_layer_bucket(line: str) -> bool:
    return bool(
        re.search(
            r'^\s*(?:[-*+]\s*)?(?:unit|functional|integration|static|regression|prerequisite|e2e|manual)\b',
            line,
            re.IGNORECASE,
        )
    )


def _requirements_ac_layer_table_indices(cells: list[str]) -> dict[str, int] | None:
    normalized = [_normalized_table_header(cell) for cell in cells]
    if any(value in {'journey', 'journeyid', 'acjourney'} for value in normalized):
        return None

    ac_index: int | None = None
    layer_index: int | None = None
    for index, value in enumerate(normalized):
        if value in {'ac', 'acid', 'acceptancecriterion', 'acceptancecriteria'}:
            ac_index = index
        elif value in {'verificationlayer', 'verification', 'layer', '验证层级', '验证方式'}:
            layer_index = index
    if ac_index is None or layer_index is None:
        return None
    return {'ac': ac_index, 'layer': layer_index}


def _requirements_obligation_traceability(content: str) -> set[str]:
    traceable: set[str] = set()
    for line in content.splitlines():
        ao_ids = _requirements_ao_ids_in_text(line)
        if not ao_ids:
            continue
        if _requirements_ac_ids_in_text(line):
            traceable.update(ao_ids)
            continue
        if _requirements_line_resolves_obligation(line):
            traceable.update(ao_ids)
    return traceable


def _requirements_ac_ids_in_text(text: str) -> set[str]:
    return acceptance_criterion_ids_in_text(text)


def _requirements_ao_ids_in_text(text: str) -> set[str]:
    return {_normalize_requirements_ao_id(match.group(0)) for match in re.finditer(r'\bAO-\d+\b', text, re.IGNORECASE)}


def _normalize_requirements_ao_id(value: str) -> str:
    match = re.fullmatch(r'AO-(\d+)', str(value or '').strip(), flags=re.IGNORECASE)
    if not match:
        return str(value or '').strip().upper()
    digits = match.group(1)
    return f'AO-{int(digits):0{max(3, len(digits))}d}'


def _requirements_verification_layer_from_line(line: str) -> str | None:
    if _is_markdown_table_separator(line):
        return None
    structured_patterns = [
        r'\bverification(?:\s+layer)?\s*[:：=]\s*([A-Za-z0-9_-]+)\b',
        r'\b验证(?:层级|层|方式)?\s*[:：]\s*([A-Za-z0-9_-]+|单元|集成|静态|回归|前置|前置条件|前置依赖|端到端|人工)\b',
        r'\[\s*verification\s*:\s*([A-Za-z0-9_-]+)\s*\]',
        r'\(\s*(unit|functional|integration|static|regression|prerequisite|e2e|manual)\s*\)',
    ]
    for pattern in structured_patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if not match:
            continue
        layer = _normalize_requirements_verification_layer(match.group(1))
        if layer:
            return layer

    cells = _markdown_table_cells(line)
    if cells:
        for cell in cells:
            layer = _normalize_requirements_verification_layer(cell)
            if layer:
                return layer

    leading_layer = re.search(
        r'^\s*(?:[-*+]\s*)?(unit|functional|integration|static|regression|prerequisite|e2e|manual)\b',
        line,
        re.IGNORECASE,
    )
    if leading_layer:
        return _normalize_requirements_verification_layer(leading_layer.group(1))
    return None


def _normalize_requirements_verification_layer(value: str) -> str | None:
    normalized = re.sub(r'[\s`*_，。:：;；]+', ' ', str(value).strip().lower()).strip()
    if not normalized:
        return None
    aliases = {
        'unit': ('unit', 'unit test', 'unit tests', '单元', '单元测试'),
        'functional': ('functional', 'api', 'api test', 'api tests', '功能', '功能测试', '接口', '接口测试'),
        'integration': ('integration', 'integration test', 'integration tests', '集成', '集成测试'),
        'static': ('static', 'static check', 'static checks', 'static review', '静态', '静态检查', '静态审查'),
        'regression': ('regression', 'regression test', 'regression tests', '回归', '回归测试'),
        'prerequisite': ('prerequisite', 'prerequisites', 'prereq', 'prereqs', '前置', '前置条件', '前置依赖'),
        'e2e': ('e2e', 'end-to-end', 'end to end', 'playwright', 'browser', '端到端', '浏览器'),
        'manual': ('manual', 'manual acceptance', 'uat', '人工', '人工验收', '手工'),
    }
    for layer, candidates in aliases.items():
        if normalized in candidates:
            return layer
    for layer, candidates in aliases.items():
        if any(re.search(rf'\b{re.escape(candidate)}\b', normalized) for candidate in candidates if re.match(r'^[a-z0-9 -]+$', candidate)):
            return layer
    return None


def _requirements_line_resolves_obligation(line: str) -> bool:
    normalized = line.lower()
    if not any(status in normalized for status in _REQUIREMENTS_RESOLUTION_STATUSES):
        return False
    cells = _markdown_table_cells(line)
    if cells:
        return any(_requirements_resolution_reason_is_meaningful(cell) for cell in cells)
    parts = re.split(r'\b(?:deferred|rejected|out_of_scope)\b', line, maxsplit=1, flags=re.IGNORECASE)
    return len(parts) == 2 and _requirements_resolution_reason_is_meaningful(parts[1])


def _requirements_resolution_reason_is_meaningful(text: str) -> bool:
    stripped = str(text).strip()
    if not stripped:
        return False
    lowered = stripped.lower().strip('`*_ -')
    if lowered in {
        'ao',
        'ac',
        'status',
        'verification layer',
        'evidence/reason',
        'reason',
        'deferred',
        'rejected',
        'out_of_scope',
        'manual',
        'unit',
        'functional',
        'integration',
        'e2e',
        'pending',
        'todo',
        'tbd',
        'n/a',
    }:
        return False
    if _requirements_ao_ids_in_text(stripped) or _requirements_ac_ids_in_text(stripped):
        return False
    if _requirements_resolution_reason_is_layer_only(stripped):
        return False
    return True


def _requirements_resolution_reason_is_layer_only(text: str) -> bool:
    normalized = re.sub(r'[\s`*_，。:：;；]+', ' ', str(text).strip().lower()).strip()
    if not normalized:
        return False
    layer_aliases = {
        'unit',
        'unit test',
        'unit tests',
        '单元',
        '单元测试',
        'functional',
        'api',
        'api test',
        'api tests',
        '功能',
        '功能测试',
        '接口',
        '接口测试',
        'integration',
        'integration test',
        'integration tests',
        '集成',
        '集成测试',
        'e2e',
        'end-to-end',
        'end to end',
        'playwright',
        'browser',
        '端到端',
        '浏览器',
        'manual',
        'manual acceptance',
        'uat',
        '人工',
        '人工验收',
        '手工',
    }
    return normalized in layer_aliases


def _requirements_trace_refs_from_cell(value: str) -> set[str]:
    refs: set[str] = set()
    for part in re.split(r'(?:<br\s*/?>|[,，;；、])', str(value), flags=re.IGNORECASE):
        ref = _normalize_requirements_trace_ref(part)
        if not _requirements_trace_ref_is_meaningful(ref):
            continue
        stable_ids = _requirements_trace_ref_ids(ref)
        refs.update(stable_ids or {ref})
    return refs


def _normalize_requirements_trace_ref(value: str) -> str:
    ref = str(value or '').strip().strip('`*_')
    ref = ref.replace('`', '')
    ref = re.sub(r'\s*/\s*', ' / ', ref)
    ref = re.sub(r'\s+', ' ', ref).strip()
    return ref


def _requirements_trace_ref_ids(value: str) -> set[str]:
    return {
        match.group(0).upper()
        for match in re.finditer(r'\b(?:PD|PDR|TA|TAR)(?:-[A-Za-z0-9_.]+)+\b', value, re.IGNORECASE)
    }


def _trace_refs_from_case(case: dict[str, Any], *keys: str) -> set[str]:
    refs: set[str] = set()
    for key in keys:
        value = case.get(key)
        if isinstance(value, list):
            for item in value:
                refs.update(_requirements_trace_refs_from_cell(str(item)))
        elif value is not None:
            refs.update(_requirements_trace_refs_from_cell(str(value)))
    return refs


def _requirements_trace_ref_is_meaningful(value: str) -> bool:
    normalized = re.sub(r'\s+', ' ', value.strip().lower())
    if not normalized:
        return False
    if normalized in {
        '-',
        'n/a',
        'na',
        'none',
        'pending',
        'todo',
        'tbd',
        '待补',
        '未指定',
        '无',
        '无 active must ao',
        'product design ref',
        'technical architecture ref',
        '设计引用',
        '架构引用',
    }:
        return False
    return True


def _markdown_table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith('|') or '|' not in stripped[1:]:
        return []
    if _is_markdown_table_separator(stripped):
        return []
    return [cell.strip() for cell in stripped.strip('|').split('|')]


def _markdown_table_rows(content: str) -> list[list[str]]:
    return [
        cells
        for line in content.splitlines()
        if (cells := _markdown_table_cells(line))
    ]


def _is_markdown_table_separator(line: str) -> bool:
    stripped = line.strip()
    return bool(re.fullmatch(r'\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?', stripped))


def _required_test_layers(content: str) -> set[str]:
    section = _markdown_section(content, 'Test Strategy').lower()
    if not section:
        return set()
    layers: set[str] = set()
    patterns = {
        'unit': ('unit test', 'unit tests'),
        'functional': ('functional', 'api test', 'api tests'),
        'integration': ('integration', 'integrated'),
        'e2e': ('e2e', 'end-to-end', 'end to end', 'playwright', 'browser', 'manual acceptance', 'uat'),
    }
    for layer, needles in patterns.items():
        if any(needle in section for needle in needles):
            layers.add(layer)
    return layers


def _test_layer_is_covered(layer: str, haystack: str) -> bool:
    coverage_terms = {
        'unit': ('unit', 'pytest', 'unittest'),
        'functional': ('functional', 'api', 'route', 'request'),
        'integration': ('integration', 'database', 'db', 'import', 'export'),
        'e2e': ('e2e', 'end-to-end', 'end to end', 'playwright', 'browser', 'manual acceptance', 'uat'),
    }
    return any(term in haystack for term in coverage_terms[layer])


def _unit_plan_body_has_test_case_matrix_entry(content: str, unit_id: str) -> bool:
    if not unit_id:
        return False
    matrix_match = re.search(
        r'(?ims)^##+\s+.*(?:Test Case Matrix|测试用例矩阵).*$([\s\S]*?)(?=^##+\s+|\Z)',
        content,
    )
    if not matrix_match:
        return False
    return unit_id.lower() in matrix_match.group(1).lower()


def _is_static_verification_command(command: str) -> bool:
    lowered = command.lower().replace('--noemit', '--noemit')
    normalized = re.sub(r'\s+', ' ', lowered).strip()
    static_patterns = [
        'tsc --noemit',
        'tsc --no-emit',
        'eslint',
        'biome check',
        'prettier',
        'typecheck',
        'type-check',
        'lint',
    ]
    if any(pattern in normalized for pattern in static_patterns):
        return True
    return re.search(r'\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:lint|typecheck|type-check)\b', normalized) is not None


def _unit_requires_golden_path(unit: dict[str, Any]) -> bool:
    validation_level = str(unit.get('workflow_validation_level') or '').strip().lower()
    if validation_level == 'closure':
        return True
    test_cases = _unit_test_cases(unit)
    if any(str(case.get('layer') or '').strip().lower() == 'e2e' for case in test_cases if isinstance(case, dict)):
        return True
    commands = ' '.join(str(command).lower() for command in unit.get('verification_commands') or [])
    return 'playwright' in commands or 'e2e' in commands


_FINAL_WALKTHROUGH_LAUNCH_MODES = {'agent_start', 'manual_only', 'not_required'}
_FINAL_WALKTHROUGH_SURFACE_KINDS = {'browser', 'api', 'cli', 'artifact'}
_FINAL_WALKTHROUGH_READINESS_KEYS = ('ready_url', 'ready_command', 'ready_output_contains')
_ENV_KEY_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_SECRET_KEY_RE = re.compile(r'(?:password|passwd|token|secret|api[_-]?key|signature|database[_-]?url|db[_-]?url)', re.IGNORECASE)
_SECRET_ASSIGNMENT_RE = re.compile(
    r'(?i)(?:^|\s)(?:[A-Za-z_][A-Za-z0-9_]*_)?'
    r'(?:PASSWORD|PASSWD|TOKEN|SECRET|API_KEY|APIKEY|SIGNATURE|DATABASE_URL|DB_URL)\s*=\s*["\']?[^"\'\s]+'
)
_FORBIDDEN_ENV_VALUE_KEYS = {
    'env',
    'environment',
    'env_values',
    'envValues',
    'env_vars',
    'envVars',
    'secrets',
    'secret_values',
    'secretValues',
}
_TEST_ONLY_MANUAL_STEP_RE = re.compile(
    r'(?i)\b('
    r'pytest|py\.test|unittest|playwright\s+test|cypress|jest|vitest|rspec|phpunit|'
    r'go\s+test|cargo\s+test|mvn\s+test|gradle\s+test|'
    r'npm\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test|yarn\s+(?:run\s+)?test|bun\s+(?:run\s+)?test'
    r')\b'
)
_TEST_ONLY_PHRASE_RE = re.compile(
    r'(?i)(?:run|execute|rerun|运行|执行|跑)(?:\s+the)?\s+'
    r'(?:tests?|verification command|golden path command|测试|验证命令|pytest)'
)


def _unit_final_acceptance_launch(unit: dict[str, Any]) -> dict[str, Any] | None:
    walkthrough = unit.get('final_acceptance_walkthrough') or unit.get('finalAcceptanceWalkthrough')
    if isinstance(walkthrough, dict):
        launch = walkthrough.get('launch')
        if isinstance(launch, dict):
            return launch
        return None
    return None


def _unit_final_acceptance_inspection(unit: dict[str, Any]) -> dict[str, Any] | None:
    walkthrough = unit.get('final_acceptance_walkthrough') or unit.get('finalAcceptanceWalkthrough')
    if isinstance(walkthrough, dict):
        inspection = walkthrough.get('inspection')
        if isinstance(inspection, dict):
            return inspection
    return None


def _unit_requires_final_acceptance_inspection(unit: dict[str, Any], state: dict[str, Any]) -> bool:
    if bool(unit.get('passes')):
        return False
    validation_level = str(unit.get('workflow_validation_level') or '').strip().lower()
    if validation_level == 'closure':
        return True
    for key in (
        'currentUnitIsWebSystem',
        'currentUnitNeedsUiDesign',
        'web_system',
        'ui_system',
        'needs_ui_design',
        'needsUiDesign',
    ):
        if bool(unit.get(key)) or bool(state.get(key)):
            return True
    for case in _unit_test_cases(unit):
        if not isinstance(case, dict):
            continue
        if case.get('golden_path') is True:
            return True
        if str(case.get('layer') or '').strip().lower() == 'e2e':
            return True
        if case.get('prototype_conformance') or case.get('prototype_surfaces'):
            return True
    return False


def _final_acceptance_launch_issues(launch: dict[str, Any], workspace_dir: Path | None) -> list[str]:
    issues: list[str] = []
    mode = str(launch.get('mode') or '').strip()
    if mode not in _FINAL_WALKTHROUGH_LAUNCH_MODES:
        issues.append(
            'final_acceptance_walkthrough.launch.mode must be agent_start, manual_only, or not_required'
        )
        return issues

    issues.extend(_final_acceptance_launch_secret_issues(launch))
    cwd_issue = _final_acceptance_launch_cwd_issue(launch.get('cwd'), workspace_dir)
    if cwd_issue:
        issues.append(cwd_issue)

    timeout = launch.get('ready_timeout_seconds')
    if timeout is not None:
        try:
            timeout_value = float(timeout)
        except (TypeError, ValueError):
            timeout_value = 0
        if timeout_value <= 0:
            issues.append('final_acceptance_walkthrough.launch.ready_timeout_seconds must be greater than 0')

    if mode == 'agent_start':
        if not str(launch.get('command') or '').strip():
            issues.append('final_acceptance_walkthrough.launch.command is required for agent_start')
        if not any(str(launch.get(key) or '').strip() for key in _FINAL_WALKTHROUGH_READINESS_KEYS):
            issues.append(
                'final_acceptance_walkthrough.launch agent_start requires a readiness hint: '
                'ready_url, ready_command, or ready_output_contains'
            )
    elif mode == 'manual_only':
        if not str(launch.get('manual_launch_instructions') or '').strip():
            issues.append(
                'final_acceptance_walkthrough.launch.manual_launch_instructions is required for manual_only'
            )
    return issues


def _final_acceptance_inspection_issues(inspection: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    surface_kind = str(inspection.get('surface_kind') or inspection.get('surfaceKind') or '').strip().lower()
    if surface_kind not in _FINAL_WALKTHROUGH_SURFACE_KINDS:
        issues.append(
            'final_acceptance_walkthrough.inspection.surface_kind must be browser, api, cli, or artifact'
        )
    entrypoint = str(inspection.get('entrypoint') or '').strip()
    if not entrypoint:
        issues.append('final_acceptance_walkthrough.inspection.entrypoint is required')
    elif _url_contains_secret_query(entrypoint):
        issues.append('final_acceptance_walkthrough.inspection.entrypoint contains a secret-like query parameter')

    manual_steps = _inspection_strings(inspection.get('manual_steps') or inspection.get('manualSteps'))
    if not manual_steps:
        issues.append('final_acceptance_walkthrough.inspection.manual_steps is required')
    elif _manual_steps_are_test_only(manual_steps):
        issues.append(
            'final_acceptance_walkthrough.inspection.manual_steps must describe real system operations, '
            'not only pytest, Playwright, golden path, or other test commands'
        )

    expected = _inspection_strings(
        inspection.get('expected_observations') or inspection.get('expectedObservations')
    )
    if not expected:
        issues.append('final_acceptance_walkthrough.inspection.expected_observations is required')
    return issues


def _inspection_strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [line.strip('- ').strip() for line in value.splitlines() if line.strip('- ').strip()]
    return []


def _manual_steps_are_test_only(steps: list[str]) -> bool:
    if not steps:
        return False
    return all(_manual_step_is_test_only(step) for step in steps)


def _manual_step_is_test_only(step: str) -> bool:
    normalized = step.strip().strip('`').lower()
    if not normalized:
        return False
    return bool(_TEST_ONLY_MANUAL_STEP_RE.search(normalized) or _TEST_ONLY_PHRASE_RE.search(normalized))


def _observation_record_field_value(section: str, label: str) -> str:
    pattern = re.compile(rf'(?im)^\s*[-*]\s*{re.escape(label)}\s*:\s*(.+?)\s*$')
    match = pattern.search(section)
    if not match:
        return ''
    value = match.group(1).strip()
    return value if value and value not in {'-', 'N/A', 'n/a', 'TBD', '待填写'} else ''


def _final_acceptance_launch_secret_issues(launch: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for key in sorted(_FORBIDDEN_ENV_VALUE_KEYS):
        if key in launch and _has_non_empty_value(launch.get(key)):
            issues.append(
                f'final_acceptance_walkthrough.launch.{key} must not store env or secret values; '
                'use env_keys with names only'
            )

    env_keys = launch.get('env_keys')
    if env_keys is not None:
        if not isinstance(env_keys, list):
            issues.append('final_acceptance_walkthrough.launch.env_keys must be a list of environment variable names')
        else:
            for env_key in env_keys:
                env_name = str(env_key or '').strip()
                if not _ENV_KEY_RE.match(env_name):
                    issues.append(
                        'final_acceptance_walkthrough.launch.env_keys must contain names only, '
                        f'not secret values: {env_name or "<empty>"}'
                    )

    for key in ('command', 'ready_command', 'manual_launch_instructions'):
        value = str(launch.get(key) or '')
        if value and _SECRET_ASSIGNMENT_RE.search(value):
            issues.append(
                f'final_acceptance_walkthrough.launch.{key} appears to store a secret/env value; '
                'store only env key names in env_keys'
            )

    for key in ('ready_url',):
        value = str(launch.get(key) or '')
        if value and _url_contains_secret_query(value):
            issues.append(
                f'final_acceptance_walkthrough.launch.{key} contains a secret-like query parameter'
            )
    return issues


def _has_non_empty_value(value: Any) -> bool:
    if value is None:
        return False
    if value == '':
        return False
    if isinstance(value, (list, dict, tuple, set)) and not value:
        return False
    return True


def _url_contains_secret_query(value: str) -> bool:
    if '?' not in value:
        return False
    query = value.split('?', 1)[1]
    for part in query.split('&'):
        key = part.split('=', 1)[0]
        if _SECRET_KEY_RE.search(key):
            return True
    return False


def _final_acceptance_launch_cwd_issue(raw_cwd: Any, workspace_dir: Path | None) -> str | None:
    if raw_cwd is None:
        return None
    cwd_text = str(raw_cwd).strip()
    if not cwd_text or '\x00' in cwd_text:
        return 'final_acceptance_walkthrough.launch.cwd is invalid'
    if workspace_dir is None:
        return None
    workspace_root = workspace_dir.resolve()
    candidate = Path(cwd_text)
    resolved = candidate.resolve() if candidate.is_absolute() else (workspace_root / candidate).resolve()
    if not resolved.is_relative_to(workspace_root):
        return 'final_acceptance_walkthrough.launch.cwd must stay inside the workspace'
    return None



def _is_golden_path_case(case: Any) -> bool:
    return isinstance(case, dict) and case.get('golden_path') is True



def _golden_path_case_issue(
    case: dict[str, Any],
    verification_commands: list[str],
    workspace_dir: Path | None,
) -> str:
    layer = str(case.get('layer') or '').strip().lower()
    if layer != 'e2e':
        return 'must be layer=e2e'

    environment_kind = case_environment_kind(case)
    if environment_kind not in REAL_E2E_ENVIRONMENT_KINDS:
        return f'environment_kind must be local_real or production_readonly, not {environment_kind or "missing"}'

    command = str(case.get('command') or '').strip()
    if not _case_has_explicit_real_entrypoint(case):
        return 'must declare real_entrypoint or entrypoint'

    fixture = _case_fixture_or_setup(case)
    expected = str(case.get('expected') or case.get('expected_result') or case.get('expectedResult') or '').strip()
    if not command or not fixture or _expected_is_weak(expected):
        if _case_has_verification_assist(case) and fixture and not _expected_is_weak(expected):
            pass
        else:
            return 'must include command, fixture/setup or test data, and a concrete expected result'
    if _case_has_verification_assist(case):
        mocked_routes = _case_core_api_mock_routes(case, command, workspace_dir)
        if mocked_routes or case_declares_core_api_mock(case):
            return f'must not use core API mock/stub routes: {mocked_routes or case_declared_mocked_routes(case) or ["declared"]}'
        return ''
    if not any(command == candidate or command in candidate or candidate in command for candidate in verification_commands):
        return 'command must appear in verification_commands'

    mocked_routes = _case_core_api_mock_routes(case, command, workspace_dir)
    if mocked_routes or case_declares_core_api_mock(case):
        return f'must not use core API mock/stub routes: {mocked_routes or case_declared_mocked_routes(case) or ["declared"]}'
    return ''


def _case_has_verification_assist(case: dict[str, Any]) -> bool:
    return 'verification_assist' in case or 'verificationAssist' in case


def _case_has_manual_evidence(case: dict[str, Any]) -> bool:
    return bool(
        str(
            case.get('manual_evidence')
            or case.get('manualEvidence')
            or case.get('evidence')
            or case.get('evidence_path')
            or case.get('evidencePath')
            or ''
        ).strip()
    )


def _case_is_manual_evidence_case(case: dict[str, Any]) -> bool:
    layer = str(case.get('layer') or '').strip().lower()
    evidence_type = str(case.get('evidence_type') or case.get('evidenceType') or '').strip().lower()
    return (
        layer in {'manual', 'human', 'inspection'}
        or layer.startswith('manual ')
        or evidence_type in {'manual', 'manual_evidence'}
    )


def _final_evidence_candidate_issue(case: dict[str, Any], verification_commands: set[str]) -> str | None:
    command = str(case.get('command') or '').strip()
    if command:
        if command in verification_commands:
            return None
        return 'command is not an exact verification_commands[] entry'
    if _case_is_manual_evidence_case(case):
        if _case_has_manual_evidence(case):
            return None
        return 'is manual but lacks manual_evidence, evidence, or evidence_path'
    if _case_has_verification_assist(case):
        return 'uses verification_assist; verification_assist is auxiliary and cannot statically prove final-valid AC coverage'
    if _case_has_manual_evidence(case):
        return 'has manual evidence but is not declared as layer=manual or evidence_type=manual_evidence'
    return 'lacks exact command or explicit manual evidence'


def _case_has_explicit_real_entrypoint(case: dict[str, Any]) -> bool:
    return bool(
        str(
            case.get('real_entrypoint')
            or case.get('realEntrypoint')
            or case.get('entrypoint')
            or case.get('entry_point')
            or ''
        ).strip()
    )


def _case_fixture_or_setup(case: dict[str, Any]) -> str:
    value = (
        case.get('fixture')
        or case.get('test_data')
        or case.get('testData')
        or case.get('setup')
        or case.get('fixtures')
    )
    if isinstance(value, list):
        return ' '.join(str(item).strip() for item in value if str(item).strip())
    return str(value or '').strip()


def _case_acceptance_criterion_ids(case: dict[str, Any]) -> set[str]:
    values = _case_string_values(
        case.get('acceptance_criteria')
        or case.get('acceptanceCriteria')
        or case.get('acceptance_criterion')
        or case.get('acceptanceCriterion')
    )
    ids: set[str] = set()
    for value in values:
        ids.update(_requirements_ac_ids_in_text(value))
    return ids


def _case_journey_ids(case: dict[str, Any]) -> set[str]:
    values = _case_string_values(
        case.get('journey_id')
        or case.get('journeyId')
        or case.get('journey')
        or case.get('journeys')
        or case.get('journey_ids')
        or case.get('journeyIds')
        or case.get('covers_journeys')
        or case.get('coversJourneys')
        or case.get('journey_refs')
        or case.get('journeyRefs')
    )
    ids: set[str] = set()
    for value in values:
        ids.update(_requirements_journey_ids_in_text(value))
    return ids


def _case_string_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    return [str(value).strip()] if str(value).strip() else []



def _expected_is_weak(expected: str) -> bool:
    if not expected:
        return True
    normalized = re.sub(r'\s+', '', expected.lower())
    weak_terms = {
        '页面正常',
        '页面正常渲染',
        '渲染成功',
        '无报错',
        '没有报错',
        '截图留存',
        '截图已上传',
        '人工确认',
        '流程正常',
    }
    return normalized in weak_terms



def _verification_env_keys(payload: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for field in ('verification_env', 'verificationEnv'):
        value = payload.get(field)
        if isinstance(value, dict):
            keys.update(str(key).strip() for key in value if str(key).strip())
    for field in ('env_keys', 'envKeys'):
        value = payload.get(field)
        if isinstance(value, list):
            keys.update(str(key).strip() for key in value if _valid_env_key_name(str(key).strip()))
    return keys


def _verification_env_declaration_issues(label: str, payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for field in ('verification_env', 'verificationEnv'):
        value = payload.get(field)
        if not isinstance(value, dict):
            continue
        for key, env_value in value.items():
            key_text = str(key).strip()
            if key_text and _is_key_only_env_value(env_value):
                issues.append(
                    f'{label} {field}.{key_text} uses a key-only placeholder value; '
                    'move the variable name to env_keys and store only real non-sensitive values in verification_env'
                )
    for field in ('env_keys', 'envKeys'):
        value = payload.get(field)
        if value is None:
            continue
        if not isinstance(value, list):
            issues.append(f'{label} {field} must be a list of environment variable names')
            continue
        for env_key in value:
            key_text = str(env_key).strip()
            if not _valid_env_key_name(key_text):
                issues.append(
                    f'{label} {field} must contain names only, not assignments or values: {key_text}'
                )
    return issues


def _valid_env_key_name(value: str) -> bool:
    return bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value))


def _is_key_only_env_value(value: Any) -> bool:
    text = str(value).strip()
    if not text:
        return False
    normalized = re.sub(r'[\s_-]+', ' ', text.lower()).strip()
    key_only_phrases = (
        'required key name only',
        'optional key name only',
        'value must not be recorded',
    )
    if any(phrase in normalized for phrase in key_only_phrases):
        return True
    return bool(re.fullmatch(r'<[^<>]+>', text))


def _required_env_keys_for_verification_command(command: str) -> set[str]:
    lowered = command.lower()
    required: set[str] = set()
    if 'playwright' in lowered or 'prisma' in lowered:
        required.add('DATABASE_URL')
    if re.search(r'\bDATABASE_URL\b', command):
        required.add('DATABASE_URL')
    return required


def _command_sets_env(command: str, key: str) -> bool:
    return re.search(rf'(?:^|[;&\s])(?:export\s+)?{re.escape(key)}\s*=', command) is not None


def _state_workspace_dir(state: dict[str, Any]) -> Path | None:
    raw = state.get('executionWorkspacePath') or state.get('workspacePath')
    if not raw:
        return None
    path = Path(str(raw))
    return path if path.exists() else None


def _case_core_api_mock_routes(
    case: dict[str, Any],
    command: str,
    workspace_dir: Path | None,
) -> list[str]:
    routes = [
        *case_declared_mocked_routes(case),
        *command_core_api_mock_routes(command, workspace_dir=workspace_dir),
    ]
    if case_declares_core_api_mock(case) and not routes:
        routes.append('declared core API mock')
    return _dedupe_strings(routes)


def _requirements_request_production_readonly_evidence(content: str, state: dict[str, Any]) -> bool:
    text = '\n'.join([
        content,
        str(state.get('requestedOutcome') or ''),
        str(state.get('feasibleOutcome') or ''),
        str(state.get('finalAcceptanceRejectionFeedback') or ''),
        str(state.get('unitPlanRevisionFeedback') or ''),
    ]).lower()
    markers = [
        'remote log',
        'remote logs',
        'production page',
        'production environment',
        'post-deploy',
        'post deploy',
        'deployed page',
        'deployment verification',
        '远程日志',
        '生产页面',
        '生产环境',
        '部署后验证',
        '部署后',
    ]
    return any(marker in text for marker in markers)


def _final_verification_evidence_rows(state: dict[str, Any], artifacts_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current_unit_id = str(state.get('currentUnitId') or '').strip()
    candidate_dirs = []
    if current_unit_id:
        candidate_dirs.append(Path(artifacts_dir) / current_unit_id)
    candidate_dirs.extend(path.parent for path in sorted(Path(artifacts_dir).rglob('verification.json')))
    seen: set[Path] = set()
    for unit_dir in candidate_dirs:
        path = unit_dir / 'verification.json'
        resolved = path.resolve()
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        try:
            payload = _load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        for row in payload.get('evidence_rows') or []:
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
