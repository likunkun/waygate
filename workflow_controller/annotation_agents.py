from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import shlex
import subprocess
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from workflow_controller.gates.parsers import gate_body, hash_gate_body


ANNOTATION_ROLES = (
    'requirements_annotation',
    'unit_plan_annotation',
    'final_acceptance_verification_assist',
)

ANNOTATION_BACKENDS = (
    'opencode',
    'codex',
)

DEFAULT_VERIFICATION_ASSIST_ROLE = 'final_acceptance_verification_assist'
VERIFICATION_ASSIST_CASE_STATUSES = {'passed', 'failed', 'blocked', 'needs_human_review'}

FAILURE_POLICIES = {'block', 'warn'}

DEFAULT_ANNOTATION_PROXY_ENV_KEYS = (
    'HTTP_PROXY',
    'HTTPS_PROXY',
    'ALL_PROXY',
    'NO_PROXY',
    'http_proxy',
    'https_proxy',
    'all_proxy',
    'no_proxy',
)

ROLE_ALIASES = {
    'requirements': 'requirements_annotation',
    'requirements-annotation': 'requirements_annotation',
    'requirements_annotation': 'requirements_annotation',
    'unit-plan': 'unit_plan_annotation',
    'unit_plan': 'unit_plan_annotation',
    'unit-plan-annotation': 'unit_plan_annotation',
    'unit_plan_annotation': 'unit_plan_annotation',
    'final-acceptance': 'final_acceptance_verification_assist',
    'final_acceptance': 'final_acceptance_verification_assist',
    'final-acceptance-verification-assist': 'final_acceptance_verification_assist',
    'final_acceptance_verification_assist': 'final_acceptance_verification_assist',
}

BACKEND_ALIASES = {
    'opencode': 'opencode',
    'codex': 'codex',
}

DEFAULT_ANNOTATION_REQUEST = (
    'Read {prompt_path}. Output only the requested risk-only JSON annotation artifact. '
    'Do not approve, skip, modify, or bypass any Waygate gate.'
)

ROLE_STAGES = {
    'requirements_annotation': 'requirements',
    'unit_plan_annotation': 'unit_plan',
    'final_acceptance_verification_assist': 'final_acceptance',
}

ROLE_TITLES = {
    'requirements_annotation': 'Requirements risk annotation',
    'unit_plan_annotation': 'Unit Plan risk annotation',
    'final_acceptance_verification_assist': 'Final Acceptance verification assist',
}

ROLE_NON_APPROVAL_RULES = {
    'requirements_annotation': 'must not approve Requirements',
    'unit_plan_annotation': 'must not approve Unit Plan',
    'final_acceptance_verification_assist': 'must not approve Final Acceptance and must not rewrite deterministic verifier status',
}

DEFAULT_ARTIFACT_PATHS = {
    'requirements_annotation': 'requirements-draft/requirements-annotations.json',
    'unit_plan_annotation': 'unit-plan-draft/unit-plan-annotations.json',
    'final_acceptance_verification_assist': 'final-acceptance/final-acceptance-annotations.json',
}

PRODUCT_CONTRACT_RISK_CATEGORIES = (
    'product_contract_gap',
    'information_degradation',
    'product_field_mapping_gap',
    'out_of_scope_boundary_risk',
)

ROLE_RISK_CATEGORIES = {
    'requirements_annotation': (
        'high_risk_claim',
        'weak_evidence',
        'missing_mapping',
        'ambiguous_acceptance',
        *PRODUCT_CONTRACT_RISK_CATEGORIES,
        'infrastructure_gap',
        'production_readonly_gap',
        'runtime_dependency_gap',
        'unsupported_spec_risk',
    ),
    'unit_plan_annotation': (
        'weak_assertion',
        'fake_fixture',
        'broad_command',
        'missing_command',
        'production_readonly_gap',
        'runtime_dependency_gap',
        'verification_env_gap',
        'doc_gap',
        'mapping_gap',
        *PRODUCT_CONTRACT_RISK_CATEGORIES,
        'descriptive_item_risk',
    ),
    'final_acceptance_verification_assist': (
        'weak_evidence',
        'missing_evidence',
        'inconsistent_status',
        'manual_review_required',
        *PRODUCT_CONTRACT_RISK_CATEGORIES,
        'missing_manual_observation',
        'risk_assumption',
    ),
}

STAGE_FOCUS = {
    'requirements_annotation': (
        'Review Requirements claims, AC/AO/Journey mapping, infrastructure facts, '
        'external spec conversion evidence, and unsupported or deferred source risks.'
    ),
    'unit_plan_annotation': (
        'Review test cases, commands, fixtures, expected assertions, mock policy, '
        'AC/AO/Journey mapping, document deliverables, and descriptive acceptance items.'
    ),
    'final_acceptance_verification_assist': (
        'Review verification.json, final matrix evidence, scope audit, document evidence, '
        'changed-files summaries, Agent-provided manual walkthrough entrypoints, and manual '
        'observation record risks without changing verifier status.'
    ),
}

ENVIRONMENT_AVAILABILITY_CHECKS = {
    'requirements_annotation': (
        'If Requirements request remote, post-deploy, production page, production environment, '
        'or production_readonly evidence, flag missing external access details such as '
        'PRODUCTION_WEB_BASE_URL or PRODUCTION_API_BASE_URL as production_readonly_gap.',
        'Check whether Docker, Docker Compose, Playwright/browser installation, required ports, '
        'service dependencies, databases, caches, and external APIs are named as available, '
        'deferred, or manually blocked before approval.',
        'When Requirements defer executable configuration to verification_env, remember that '
        'verification_env key names do not prove executable values or reachable services.',
    ),
    'unit_plan_annotation': (
        'For every production_readonly test case or verification command, flag missing real '
        'external URL/API endpoint details such as PRODUCTION_WEB_BASE_URL or '
        'PRODUCTION_API_BASE_URL as production_readonly_gap.',
        'Check Docker, Docker Compose, Playwright/browser installation, required ports, '
        'service dependencies, databases, caches, and external APIs against the declared '
        'fixture/setup, command, cwd, and entrypoint.',
        'Treat verification_env as key declarations only; verification_env key names do not '
        'prove executable values, deployed services, or reachable production environments.',
    ),
    'final_acceptance_verification_assist': (
        'For final production_readonly evidence, flag missing real external URL/API endpoint '
        'references, unavailable production environment details, or manual review required '
        'runtime assumptions without changing deterministic verifier status.',
        'Check whether Docker, Docker Compose, Playwright/browser runtime, ports, services, '
        'and declared environment keys are actually evidenced by verification artifacts.',
    ),
}

FORBIDDEN_APPROVAL_FIELD_KEYS = {
    'requirementsaccepted',
    'unitplanaccepted',
    'finalacceptanceaccepted',
    'requirementsacceptedhash',
    'unitplanacceptedhash',
    'finalacceptanceacceptedhash',
    'requirementsacceptedby',
    'unitplanacceptedby',
    'finalacceptanceacceptedby',
    'humanconfirmationhash',
    'approvalstatus',
}


def add_annotation_agent_cli_arguments(parser: Any) -> None:
    parser.add_argument(
        '--annotation-agent',
        action='append',
        metavar='BACKEND|ROLE=BACKEND',
        dest='annotation_agent',
        help='Enable risk-only annotation agents for all roles or for ROLE only',
    )
    parser.add_argument(
        '--no-annotation-agent',
        action='append',
        metavar='ROLE|all',
        dest='no_annotation_agent',
        help='Disable risk-only annotation agents for ROLE or all roles',
    )
    parser.add_argument(
        '--annotation-agent-cmd',
        action='append',
        metavar="ROLE='COMMAND ...'",
        dest='annotation_agent_cmd',
        help='Override an annotation role command line; parsed with shlex.split',
    )
    parser.add_argument(
        '--annotation-agent-env-key',
        action='append',
        metavar='ROLE=KEY',
        dest='annotation_agent_env_key',
        help='Allow one additional non-proxy environment variable key through to an annotation role without storing its value',
    )
    parser.add_argument(
        '--annotation-agent-timeout',
        action='append',
        metavar='ROLE=SECONDS',
        dest='annotation_agent_timeout',
        help='Set an annotation role timeout in seconds',
    )
    parser.add_argument(
        '--annotation-agent-failure-policy',
        action='append',
        metavar='ROLE=block|warn',
        dest='annotation_agent_failure_policy',
        help='Set whether annotation failure blocks the gate or only writes warning evidence',
    )


def build_annotation_agent_cli_overrides(args: Any) -> dict[str, Any] | None:
    requested = list(getattr(args, 'annotation_agent', None) or [])
    disabled = list(getattr(args, 'no_annotation_agent', None) or [])
    command_overrides = list(getattr(args, 'annotation_agent_cmd', None) or [])
    env_keys = list(getattr(args, 'annotation_agent_env_key', None) or [])
    timeouts = list(getattr(args, 'annotation_agent_timeout', None) or [])
    failure_policies = list(getattr(args, 'annotation_agent_failure_policy', None) or [])
    if not any([requested, disabled, command_overrides, env_keys, timeouts, failure_policies]):
        return None

    configs: dict[str, dict[str, Any]] = {}

    def role_config(role: str) -> dict[str, Any]:
        return configs.setdefault(role, {'role': role})

    for raw in requested:
        role_text: str | None
        backend_text: str
        if '=' in raw:
            role_text, backend_text = _split_assignment('--annotation-agent', raw)
            roles = _annotation_roles_for_cli(role_text)
        else:
            backend_text = raw
            roles = ANNOTATION_ROLES
        backend = _annotation_backend_for_cli(backend_text)
        for role in roles:
            configs[role] = _default_cli_annotation_agent_config(role, backend)

    for raw in command_overrides:
        role_text, command_line = _split_assignment('--annotation-agent-cmd', raw)
        parts = shlex.split(command_line)
        if not parts:
            raise ValueError('--annotation-agent-cmd requires a non-empty command line')
        for role in _annotation_roles_for_cli(role_text):
            config = role_config(role)
            config['command'] = parts[0]
            config['args'] = parts[1:]

    for raw in env_keys:
        role_text, key = _split_assignment('--annotation-agent-env-key', raw)
        key = key.strip()
        if not key:
            raise ValueError('--annotation-agent-env-key requires a non-empty env key')
        if '=' in key:
            raise ValueError('--annotation-agent-env-key accepts env key names only, not KEY=VALUE secrets')
        for role in _annotation_roles_for_cli(role_text):
            config = role_config(role)
            keys = list(config.get('env_keys') or [])
            if key not in keys:
                keys.append(key)
            config['env_keys'] = keys

    for raw in timeouts:
        role_text, timeout_text = _split_assignment('--annotation-agent-timeout', raw)
        try:
            timeout_seconds = int(timeout_text.strip())
        except ValueError as exc:
            raise ValueError('--annotation-agent-timeout requires ROLE=positive integer seconds') from exc
        if timeout_seconds <= 0:
            raise ValueError('--annotation-agent-timeout requires ROLE=positive integer seconds')
        for role in _annotation_roles_for_cli(role_text):
            role_config(role)['timeout_seconds'] = timeout_seconds

    for raw in failure_policies:
        role_text, policy_text = _split_assignment('--annotation-agent-failure-policy', raw)
        policy = policy_text.strip().lower()
        if policy not in FAILURE_POLICIES:
            raise ValueError('annotation agent failure policy must be block or warn')
        for role in _annotation_roles_for_cli(role_text):
            role_config(role)['failure_policy'] = policy

    for raw in disabled:
        for role in _annotation_roles_for_cli(raw):
            role_config(role)['enabled'] = False

    return {'annotationAgents': configs}


def _annotation_roles_for_cli(raw: str) -> tuple[str, ...]:
    key = raw.strip()
    if not key:
        raise ValueError('Unsupported annotation role: empty')
    if key == 'all':
        return ANNOTATION_ROLES
    role = ROLE_ALIASES.get(key)
    if not role:
        raise ValueError(f'Unsupported annotation role: {raw}')
    return (role,)


def _annotation_backend_for_cli(raw: str) -> str:
    backend = BACKEND_ALIASES.get(raw.strip())
    if not backend:
        raise ValueError(
            'Unsupported annotation backend: '
            f'{raw}; expected one of opencode, codex'
        )
    return backend


def _split_assignment(option: str, raw: str) -> tuple[str, str]:
    left, sep, right = raw.partition('=')
    if not sep or not left.strip() or not right.strip():
        raise ValueError(f'{option} requires ROLE=value')
    return left.strip(), right.strip()


def _default_cli_annotation_agent_config(role: str, backend: str) -> dict[str, Any]:
    _validate_role(role)
    backend = _annotation_backend_for_cli(backend)
    if backend == 'codex':
        command = 'codex'
        args = _current_codex_annotation_args()
    else:
        command = 'opencode'
        args = _current_opencode_annotation_args()
    return {
        'role': role,
        'enabled': True,
        'backend': backend,
        'command': command,
        'args': args,
        'env_keys': [],
        'timeout_seconds': 7200,
        'artifact_path': DEFAULT_ARTIFACT_PATHS[role],
        'prompt_template': 'risk-json-v1',
        'failure_policy': 'block',
    }


def _current_codex_annotation_args() -> list[str]:
    return [
        'exec',
        '--sandbox',
        'workspace-write',
        '-o',
        '{artifact_path}',
        DEFAULT_ANNOTATION_REQUEST,
    ]


def _current_opencode_annotation_args() -> list[str]:
    return [
        'run',
        DEFAULT_ANNOTATION_REQUEST,
    ]


def _legacy_builtin_codex_annotation_args() -> list[str]:
    return [
        'exec',
        '--sandbox',
        'workspace-write',
        '--ask-for-approval',
        'never',
        '-o',
        '{artifact_path}',
        DEFAULT_ANNOTATION_REQUEST,
    ]


def _legacy_builtin_claude_code_annotation_args() -> list[str]:
    return [
        '-p',
        DEFAULT_ANNOTATION_REQUEST,
        '--permission-mode',
        'bypassPermissions',
    ]


def _current_builtin_claude_code_annotation_args() -> list[str]:
    return [
        '--bare',
        '--no-session-persistence',
        '-p',
        DEFAULT_ANNOTATION_REQUEST,
        '--permission-mode',
        'bypassPermissions',
    ]


def _is_legacy_builtin_codex_annotation_config(
    config: dict[str, Any],
    role: str,
    args: list[str],
) -> bool:
    configured_role = str(config.get('role') or role).strip()
    backend = str(config.get('backend') or 'codex').strip()
    command = str(config.get('command') or '').strip()
    return (
        configured_role == role
        and backend == 'codex'
        and command == 'codex'
        and args == _legacy_builtin_codex_annotation_args()
    )


def _is_builtin_claude_code_annotation_config(
    config: dict[str, Any],
    role: str,
    args: list[str],
) -> bool:
    configured_role = str(config.get('role') or role).strip()
    backend = str(config.get('backend') or 'codex').strip()
    command = str(config.get('command') or '').strip()
    return (
        configured_role == role
        and backend == 'claude-code'
        and command == 'claude'
        and tuple(args) in {
            tuple(_legacy_builtin_claude_code_annotation_args()),
            tuple(_current_builtin_claude_code_annotation_args()),
        }
    )


def migrate_legacy_annotation_agent_configs(state: dict[str, Any]) -> bool:
    """Normalize Waygate's old built-in annotation args in persisted state."""
    changed = False
    for container_key in ('annotationAgents', 'annotationAgentConfig', 'annotation_agents'):
        container = state.get(container_key)
        if not isinstance(container, dict):
            continue
        for role, raw_config in list(container.items()):
            if role not in ANNOTATION_ROLES or not isinstance(raw_config, dict):
                continue
            raw_args = raw_config.get('args') or []
            if not isinstance(raw_args, list):
                continue
            args = [str(arg) for arg in raw_args]
            if _is_legacy_builtin_codex_annotation_config(raw_config, role, args):
                raw_config['args'] = _current_codex_annotation_args()
                changed = True
            elif _is_builtin_claude_code_annotation_config(raw_config, role, args):
                raw_config['backend'] = 'opencode'
                raw_config['command'] = 'opencode'
                raw_config['args'] = _current_opencode_annotation_args()
                changed = True
    return changed


class AnnotationAgentError(RuntimeError):
    """Raised when an enabled annotation pass cannot safely complete."""

    def __init__(self, message: str, *, runner_metadata: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.runner_metadata = runner_metadata or {}


@dataclass(frozen=True)
class AnnotationAgentConfig:
    role: str
    enabled: bool
    backend: str = 'codex'
    command: str = ''
    args: list[str] = field(default_factory=list)
    env_keys: list[str] = field(default_factory=list)
    timeout_seconds: int = 7200
    artifact_path: Path = Path('')
    prompt_template: str = 'risk-json-v1'
    failure_policy: str = 'block'

    def to_metadata(self) -> dict[str, Any]:
        return {
            'role': self.role,
            'enabled': self.enabled,
            'backend': self.backend,
            'command': self.command,
            'args': list(self.args),
            'env_keys': _annotation_effective_env_keys(self),
            'timeout_seconds': self.timeout_seconds,
            'artifact_path': str(self.artifact_path),
            'prompt_template': self.prompt_template,
            'failure_policy': self.failure_policy,
        }


@dataclass(frozen=True)
class AnnotationRunResult:
    role: str
    backend: str
    status: str
    artifact_path: Path
    prompt_path: Path
    prompt_template_hash: str
    runner_metadata: dict[str, Any]
    returncode: int | None = None
    stdout: str = ''
    stderr: str = ''


@dataclass(frozen=True)
class VerificationAssistRunResult:
    role: str
    backend: str
    status: str
    artifact_path: Path
    prompt_path: Path
    prompt_template_hash: str
    payload: dict[str, Any]
    runner_metadata: dict[str, Any]
    returncode: int | None = None
    stdout: str = ''
    stderr: str = ''


def normalize_annotation_config(
    state: dict[str, Any],
    role: str,
    *,
    artifacts_dir: Path,
) -> AnnotationAgentConfig:
    _validate_role(role)
    raw_config = _raw_role_config(state, role)
    enabled = bool(raw_config.get('enabled', False))
    configured_role = str(raw_config.get('role') or role).strip()
    if configured_role != role:
        raise ValueError(f'Annotation role mismatch: expected {role}, got {configured_role}')

    backend = str(raw_config.get('backend') or 'codex').strip()
    command = str(raw_config.get('command') or '').strip()
    raw_args = raw_config.get('args') or []
    if not isinstance(raw_args, list):
        raise ValueError(f'Annotation config for {role} args must be a list')
    args = [str(arg) for arg in raw_args]

    if _is_builtin_claude_code_annotation_config(raw_config, role, args):
        backend = 'opencode'
        command = 'opencode'
        args = _current_opencode_annotation_args()

    if backend not in ANNOTATION_BACKENDS:
        raise ValueError(
            'Unsupported annotation backend: '
            f'{backend}; expected one of {", ".join(ANNOTATION_BACKENDS)}'
        )

    if enabled and not command:
        raise ValueError(f'Annotation config for {role} must include command when enabled')

    if _is_legacy_builtin_codex_annotation_config(raw_config, role, args):
        args = _current_codex_annotation_args()

    raw_env_keys = raw_config.get('env_keys') or raw_config.get('envKeys') or []
    if not isinstance(raw_env_keys, list):
        raise ValueError(f'Annotation config for {role} env_keys must be a list')
    env_keys = sorted({str(key).strip() for key in raw_env_keys if str(key).strip()})

    timeout_seconds = int(raw_config.get('timeout_seconds') or raw_config.get('timeoutSeconds') or 7200)
    if timeout_seconds <= 0:
        raise ValueError(f'Annotation config for {role} timeout_seconds must be positive')

    artifact_text = str(raw_config.get('artifact_path') or raw_config.get('artifactPath') or DEFAULT_ARTIFACT_PATHS[role]).strip()
    if not artifact_text:
        raise ValueError(f'Annotation config for {role} artifact_path cannot be empty')
    artifact_path = Path(artifact_text)
    if not artifact_path.is_absolute():
        artifact_path = artifacts_dir / artifact_path

    prompt_template = str(raw_config.get('prompt_template') or raw_config.get('promptTemplate') or 'risk-json-v1').strip()
    failure_policy = str(raw_config.get('failure_policy') or raw_config.get('failurePolicy') or 'block').strip().lower()
    if failure_policy == 'continue':
        failure_policy = 'warn'
    if failure_policy not in FAILURE_POLICIES:
        raise ValueError(f'Annotation config for {role} failure_policy must be block or warn')

    return AnnotationAgentConfig(
        role=role,
        enabled=enabled,
        backend=backend,
        command=command,
        args=args,
        env_keys=env_keys,
        timeout_seconds=timeout_seconds,
        artifact_path=artifact_path,
        prompt_template=prompt_template,
        failure_policy=failure_policy,
    )


def default_annotation_issue_categories(role: str) -> tuple[str, ...]:
    _validate_role(role)
    return ROLE_RISK_CATEGORIES[role]


def render_annotation_prompt(
    role: str,
    *,
    artifact_path: Path,
    gate_path: Path | None = None,
    validator_summary: str | dict[str, Any] | None = None,
    evidence_refs: list[str] | None = None,
    prompt_template: str = 'risk-json-v1',
    gate_content_hash: str | None = None,
) -> str:
    _validate_role(role)
    stage = ROLE_STAGES[role]
    risk_categories = ROLE_RISK_CATEGORIES[role]
    evidence_refs = evidence_refs or []
    validator_text = _stringify_validator_summary(validator_summary)
    gate_ref = str(gate_path) if gate_path else 'not provided'
    evidence_lines = '\n'.join(f'- {ref}' for ref in evidence_refs) or '- No additional evidence refs provided.'
    categories = '\n'.join(f'- {category}' for category in risk_categories)
    non_approval_rule = ROLE_NON_APPROVAL_RULES[role]
    environment_checks = '\n'.join(
        f'- {check}' for check in ENVIRONMENT_AVAILABILITY_CHECKS[role]
    )
    product_contract_audit = _product_contract_traceability_audit_section()

    return (
        f'# {ROLE_TITLES[role]}\n\n'
        '## Role\n'
        f'- Role id: `{role}`\n'
        f'- Stage: `{stage}`\n'
        '- Duty: produce risk-only annotation notes for the human reviewer.\n'
        '- AO-001: configurable non-approval annotation / verification-assist agent coverage.\n\n'
        '## Inputs\n'
        f'- Gate file: `{gate_ref}`\n'
        f'- Gate content hash: `{gate_content_hash or "unavailable"}`\n'
        f'- Artifact path: `{artifact_path}`\n'
        f'- Prompt template: `{prompt_template}`\n'
        f'- Validator summary: {validator_text}\n'
        '- Evidence refs:\n'
        f'{evidence_lines}\n\n'
        '## Rules\n'
        f'- You {non_approval_rule}.\n'
        '- You must not skip, bypass, satisfy, or close a controller gate.\n'
        '- You must not write approval state, confirmation hash, human confirmation metadata, or deterministic verifier result changes.\n'
        '- Focus only on high-risk claims, weak evidence, missing mappings, risk assumptions, and ambiguous acceptance language.\n'
        '- 所有人类可见批注字段必须使用简体中文；这包括 summary、issues[].message、non_approval_statement。taxonomy key、AC/AO/Journey id、文件路径和命令可以保留原文。\n'
        f'- Stage focus: {STAGE_FOCUS[role]}\n\n'
        '## Environment Availability Checks\n'
        f'{environment_checks}\n\n'
        f'{product_contract_audit}\n\n'
        '## Output\n'
        f'- Write one JSON artifact to `{artifact_path}`.\n'
        '- The artifact is advisory evidence for a human reviewer and is not a completion basis by itself.\n'
        '- Keep environment variable values out of the artifact; mention env key names only when relevant.\n\n'
        '## Schema\n'
        '```json\n'
        '{\n'
        f'  "role": "{role}",\n'
        f'  "stage": "{stage}",\n'
        '  "human_language": "zh-CN",\n'
        '  "summary": "简短的中文风险摘要",\n'
        '  "issues": [\n'
        '    {\n'
        '      "category": "one risk taxonomy value",\n'
        '      "severity": "low|medium|high",\n'
        '      "location": "file, section, row, or evidence ref",\n'
        '      "linked_ac": "AC id or null",\n'
        '      "linked_ao": "AO id or null",\n'
        '      "linked_journey": "Journey id or null",\n'
        '      "message": "具体的中文风险批注",\n'
        '      "evidence_refs": ["optional evidence paths"]\n'
        '    }\n'
        '  ],\n'
        '  "non_approval_statement": "本标注只提供风险提示，不批准或修改 controller gate 状态。"\n'
        '}\n'
        '```\n\n'
        '## Risk taxonomy\n'
        f'{categories}\n'
    )


def verification_assist_spec_from_case(case: dict[str, Any]) -> dict[str, Any] | None:
    raw = case.get('verification_assist')
    if raw is None:
        raw = case.get('verificationAssist')
    if raw is None:
        return None
    if isinstance(raw, dict):
        return dict(raw)
    return {'description': str(raw)}


def verification_assist_role_for_case(case: dict[str, Any]) -> str:
    spec = verification_assist_spec_from_case(case) or {}
    role, _backend = _verification_assist_role_backend(spec)
    return role


def normalize_verification_assist_config(
    state: dict[str, Any],
    case: dict[str, Any],
    *,
    artifacts_dir: Path,
) -> AnnotationAgentConfig:
    spec = verification_assist_spec_from_case(case) or {}
    role, expected_backend = _verification_assist_role_backend(spec)
    config = normalize_annotation_config(state, role, artifacts_dir=artifacts_dir)
    if expected_backend and config.backend != expected_backend:
        raise ValueError(
            'verification_assist.agent backend mismatch: '
            f'case requested {expected_backend}, but {role} is configured for {config.backend}'
        )
    return config


def render_verification_assist_case_prompt(
    *,
    role: str,
    artifact_path: Path,
    unit_id: str,
    case: dict[str, Any],
    verification_assist: dict[str, Any],
    prompt_template: str = 'verification-assist-case-v1',
    evidence_refs: list[str] | None = None,
) -> str:
    _validate_role(role)
    evidence_refs = evidence_refs or []
    case_id = _verification_assist_case_id(case)
    description = _string_value(verification_assist.get('description') or case.get('description'))
    expected = _jsonish_text(verification_assist.get('expected'))
    evidence_required = _jsonish_text(
        verification_assist.get('evidence_required') or verification_assist.get('evidenceRequired')
    )
    user_steps = _jsonish_text(
        case.get('user_steps') or case.get('userSteps') or verification_assist.get('user_steps') or verification_assist.get('userSteps')
    )
    entrypoint = _string_value(
        case.get('real_entrypoint')
        or case.get('realEntrypoint')
        or case.get('entrypoint')
        or case.get('entry_point')
        or verification_assist.get('entrypoint')
    )
    existing_evidence = '\n'.join(f'- {ref}' for ref in evidence_refs) or '- No existing evidence refs provided.'
    human_review_required = verification_assist.get('human_review_required')
    if human_review_required is None:
        human_review_required = verification_assist.get('humanReviewRequired')
    if human_review_required is None:
        human_review_required = True

    return (
        '# Verification-Assist Test Case\n\n'
        '## Role\n'
        f'- Role id: `{role}`\n'
        '- Duty: execute or judge this one declared verification item when a stable command is not available.\n'
        '- This is not a Requirements/Unit Plan annotation pass and is not a gate approval.\n\n'
        '## Test Case\n'
        f'- Unit id: `{unit_id}`\n'
        f'- Test case id: `{case_id}`\n'
        f'- Acceptance criterion: `{_string_value(case.get("acceptance_criterion") or case.get("acceptanceCriterion")) or "not provided"}`\n'
        f'- Layer: `{_string_value(case.get("layer")) or "not provided"}`\n'
        f'- Environment kind: `{_string_value(case.get("environment_kind") or case.get("environmentKind")) or "not provided"}`\n'
        f'- Entry point: `{entrypoint or "not provided"}`\n'
        f'- Description: {description or "not provided"}\n'
        f'- User steps: {user_steps or "not provided"}\n'
        f'- Expected observations: {expected or "not provided"}\n'
        f'- Evidence required: {evidence_required or "not provided"}\n'
        f'- Human review required: `{str(bool(human_review_required)).lower()}`\n'
        f'- Artifact path: `{artifact_path}`\n'
        f'- Prompt template: `{prompt_template}`\n\n'
        '## Existing Evidence Refs\n'
        f'{existing_evidence}\n\n'
        '## Rules\n'
        '- Judge only this test case. Do not approve Requirements, Unit Plan, Final Acceptance, or any Waygate gate.\n'
        '- Do not rewrite deterministic command verifier results or claim a failed command passed.\n'
        '- Prefer concrete evidence refs such as screenshots, logs, DOM state, traces, or manual observation entrypoints.\n'
        '- Keep environment variable values, tokens, database URLs, and other secrets out of the artifact.\n'
        '- If the case cannot be verified from the available environment or evidence, use status `blocked` or `needs_human_review`.\n\n'
        '## Output\n'
        f'- Write one JSON artifact to `{artifact_path}`.\n'
        '- The artifact is controller evidence for this test case, not approval.\n\n'
        '## Schema\n'
        '```json\n'
        '{\n'
        '  "agent_assisted_judgement": {\n'
        '    "status": "passed|failed|blocked|needs_human_review",\n'
        '    "summary": "concise judgement tied to observed evidence"\n'
        '  },\n'
        '  "risk_annotations": [\n'
        '    {"severity": "low|medium|high", "category": "risk taxonomy or free-form key", "note": "risk note"}\n'
        '  ],\n'
        '  "structured_evidence_refs": ["screenshot, log, DOM, trace, artifact, or observation refs"],\n'
        '  "human_review_required": true\n'
        '}\n'
        '```\n'
    )


def run_verification_assist_case(
    state: dict[str, Any],
    case: dict[str, Any],
    *,
    unit_id: str,
    state_dir: Path,
    artifacts_dir: Path,
    workspace_dir: Path,
    unit_dir: Path,
    evidence_refs: list[str] | None = None,
    event_sink: Callable[[str, dict[str, Any]], None] | None = None,
) -> VerificationAssistRunResult:
    del state_dir
    spec = verification_assist_spec_from_case(case) or {}
    config = normalize_verification_assist_config(state, case, artifacts_dir=artifacts_dir)
    case_id = _verification_assist_case_id(case)
    artifact_path = _verification_assist_artifact_path(
        config,
        unit_id=unit_id,
        case_id=case_id,
        artifacts_dir=artifacts_dir,
    )
    prompt_dir = artifacts_dir / 'verification-assist-prompts'
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = prompt_dir / f'{_safe_path_segment(unit_id)}-{_safe_path_segment(case_id)}.md'
    prompt = render_verification_assist_case_prompt(
        role=config.role,
        artifact_path=artifact_path,
        unit_id=unit_id,
        case=case,
        verification_assist=spec,
        prompt_template=config.prompt_template,
        evidence_refs=evidence_refs,
    )
    prompt_path.write_text(prompt, encoding='utf-8')
    prompt_hash = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    case_config = replace(config, artifact_path=artifact_path)
    runner_metadata = case_config.to_metadata()
    runner_metadata['prompt_template_hash'] = prompt_hash
    runner_metadata['prompt_path'] = str(prompt_path)
    runner_metadata['test_case_id'] = case_id

    if not case_config.enabled:
        payload = _write_verification_assist_failure_artifact(
            case_config,
            prompt_hash,
            unit_id=unit_id,
            case=case,
            message=f'verification-assist agent config is disabled for {case_config.role}',
            returncode=None,
            timeout=False,
        )
        return VerificationAssistRunResult(
            role=case_config.role,
            backend=case_config.backend,
            status='blocked',
            artifact_path=artifact_path,
            prompt_path=prompt_path,
            prompt_template_hash=prompt_hash,
            payload=payload,
            runner_metadata=runner_metadata,
        )

    if not _command_available(case_config.command):
        payload = _write_verification_assist_failure_artifact(
            case_config,
            prompt_hash,
            unit_id=unit_id,
            case=case,
            message=f'verification-assist backend {case_config.backend} command unavailable: {case_config.command}',
            returncode=None,
            timeout=False,
        )
        return VerificationAssistRunResult(
            role=case_config.role,
            backend=case_config.backend,
            status='blocked',
            artifact_path=artifact_path,
            prompt_path=prompt_path,
            prompt_template_hash=prompt_hash,
            payload=payload,
            runner_metadata=runner_metadata,
        )

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    env = _annotation_subprocess_env(case_config, prompt_path)
    env.update(
        {
            'WAYGATE_VERIFICATION_ASSIST_UNIT_ID': unit_id,
            'WAYGATE_VERIFICATION_ASSIST_CASE_ID': case_id,
        }
    )
    command = _expanded_command(case_config, prompt_path)
    _emit_event(
        event_sink,
        'verification_assist_case_started',
        {
            **_event_payload(case_config, state, prompt_path, prompt_hash, gate_content_hash=None),
            'unit_id': unit_id,
            'test_case_id': case_id,
        },
    )
    try:
        completed = subprocess.run(
            command,
            cwd=str(workspace_dir),
            env=env,
            text=True,
            capture_output=True,
            timeout=case_config.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _redact_text(exc.output or '', _allowed_env_values(case_config))
        stderr = _redact_text(exc.stderr or '', _allowed_env_values(case_config))
        payload = _write_verification_assist_failure_artifact(
            case_config,
            prompt_hash,
            unit_id=unit_id,
            case=case,
            message=f'verification-assist case timed out after {case_config.timeout_seconds}s',
            returncode=124,
            timeout=True,
            stdout=stdout,
            stderr=stderr,
        )
        _emit_event(
            event_sink,
            'verification_assist_case_failed',
            {
                **_event_payload(case_config, state, prompt_path, prompt_hash, gate_content_hash=None),
                'unit_id': unit_id,
                'test_case_id': case_id,
                'reason': payload['agent_assisted_judgement']['summary'],
            },
        )
        return VerificationAssistRunResult(
            role=case_config.role,
            backend=case_config.backend,
            status='blocked',
            artifact_path=artifact_path,
            prompt_path=prompt_path,
            prompt_template_hash=prompt_hash,
            payload=payload,
            runner_metadata=runner_metadata,
            returncode=124,
            stdout=stdout,
            stderr=stderr,
        )

    stdout = _redact_text(completed.stdout or '', _allowed_env_values(case_config))
    stderr = _redact_text(completed.stderr or '', _allowed_env_values(case_config))
    if completed.returncode != 0:
        payload = _write_verification_assist_failure_artifact(
            case_config,
            prompt_hash,
            unit_id=unit_id,
            case=case,
            message=f'verification-assist case failed with exit code {completed.returncode}',
            returncode=completed.returncode,
            timeout=False,
            stdout=stdout,
            stderr=stderr,
        )
        _emit_event(
            event_sink,
            'verification_assist_case_failed',
            {
                **_event_payload(case_config, state, prompt_path, prompt_hash, gate_content_hash=None),
                'unit_id': unit_id,
                'test_case_id': case_id,
                'returncode': completed.returncode,
            },
        )
        return VerificationAssistRunResult(
            role=case_config.role,
            backend=case_config.backend,
            status='blocked',
            artifact_path=artifact_path,
            prompt_path=prompt_path,
            prompt_template_hash=prompt_hash,
            payload=payload,
            runner_metadata=runner_metadata,
            returncode=completed.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    if not artifact_path.exists():
        payload = _write_verification_assist_failure_artifact(
            case_config,
            prompt_hash,
            unit_id=unit_id,
            case=case,
            message=f'verification-assist case did not write artifact: {artifact_path}',
            returncode=completed.returncode,
            timeout=False,
            stdout=stdout,
            stderr=stderr,
        )
        return VerificationAssistRunResult(
            role=case_config.role,
            backend=case_config.backend,
            status='blocked',
            artifact_path=artifact_path,
            prompt_path=prompt_path,
            prompt_template_hash=prompt_hash,
            payload=payload,
            runner_metadata=runner_metadata,
            returncode=completed.returncode,
            stdout=stdout,
            stderr=stderr,
        )

    try:
        payload = _normalize_verification_assist_artifact(
            case_config,
            prompt_hash,
            unit_id=unit_id,
            case=case,
        )
    except AnnotationAgentError as exc:
        payload = _write_verification_assist_failure_artifact(
            case_config,
            prompt_hash,
            unit_id=unit_id,
            case=case,
            message=str(exc),
            returncode=completed.returncode,
            timeout=False,
            stdout=stdout,
            stderr=stderr,
        )

    _emit_event(
        event_sink,
        'verification_assist_case_completed',
        {
            **_event_payload(case_config, state, prompt_path, prompt_hash, gate_content_hash=None),
            'unit_id': unit_id,
            'test_case_id': case_id,
            'case_status': payload.get('status'),
            'returncode': completed.returncode,
        },
    )
    return VerificationAssistRunResult(
        role=case_config.role,
        backend=case_config.backend,
        status=str(payload.get('status') or 'blocked'),
        artifact_path=artifact_path,
        prompt_path=prompt_path,
        prompt_template_hash=prompt_hash,
        payload=payload,
        runner_metadata=runner_metadata,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def run_annotation_pass(
    state: dict[str, Any],
    role: str,
    *,
    state_dir: Path,
    artifacts_dir: Path,
    workspace_dir: Path,
    gate_path: Path | None = None,
    validator_summary: str | dict[str, Any] | None = None,
    evidence_refs: list[str] | None = None,
    event_sink: Callable[[str, dict[str, Any]], None] | None = None,
) -> AnnotationRunResult:
    config = normalize_annotation_config(state, role, artifacts_dir=artifacts_dir)
    gate_content_hash = gate_content_hash_for_annotation(gate_path)
    prompt_dir = artifacts_dir / 'annotation-prompts'
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = prompt_dir / f'{role}-prompt.md'
    prompt = render_annotation_prompt(
        role,
        artifact_path=config.artifact_path,
        gate_path=gate_path,
        validator_summary=validator_summary,
        evidence_refs=evidence_refs or _default_evidence_refs(role, state, artifacts_dir, state_dir),
        prompt_template=config.prompt_template,
        gate_content_hash=gate_content_hash,
    )
    prompt_path.write_text(prompt, encoding='utf-8')
    prompt_hash = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    runner_metadata = config.to_metadata()
    runner_metadata['prompt_template_hash'] = prompt_hash
    runner_metadata['prompt_path'] = str(prompt_path)
    runner_metadata['gate_content_hash'] = gate_content_hash
    runner_metadata['runtime'] = 'subprocess'

    if not config.enabled:
        runner_metadata['runtime'] = 'skipped'
        return AnnotationRunResult(
            role=role,
            backend=config.backend,
            status='skipped',
            artifact_path=config.artifact_path,
            prompt_path=prompt_path,
            prompt_template_hash=prompt_hash,
            runner_metadata=runner_metadata,
        )

    if not _command_available(config.command):
        message = f'annotation backend {config.backend} command unavailable: {config.command}'
        return _handle_annotation_failure(
            config,
            role=role,
            prompt_path=prompt_path,
            prompt_hash=prompt_hash,
            runner_metadata=runner_metadata,
            message=message,
            event_sink=event_sink,
            gate_content_hash=gate_content_hash,
        )

    config.artifact_path.parent.mkdir(parents=True, exist_ok=True)
    env = _annotation_subprocess_env(config, prompt_path)
    command = _expanded_command(config, prompt_path)

    _emit_event(
        event_sink,
        'annotation_pass_started',
        _event_payload(config, state, prompt_path, prompt_hash, gate_content_hash=gate_content_hash),
    )
    try:
        completed = subprocess.run(
            command,
            cwd=str(workspace_dir),
            env=env,
            text=True,
            capture_output=True,
            timeout=config.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        message = f'annotation pass timed out after {config.timeout_seconds}s for {role}'
        return _handle_annotation_failure(
            config,
            role=role,
            prompt_path=prompt_path,
            prompt_hash=prompt_hash,
            runner_metadata=runner_metadata,
            message=message,
            event_sink=event_sink,
            stdout=_redact_text(exc.output or '', _allowed_env_values(config)),
            stderr=_redact_text(exc.stderr or '', _allowed_env_values(config)),
            timeout=True,
            gate_content_hash=gate_content_hash,
        )

    stdout = _redact_text(completed.stdout or '', _allowed_env_values(config))
    stderr = _redact_text(completed.stderr or '', _allowed_env_values(config))
    if completed.returncode != 0:
        message = f'annotation pass failed for {role} with exit code {completed.returncode}'
        return _handle_annotation_failure(
            config,
            role=role,
            prompt_path=prompt_path,
            prompt_hash=prompt_hash,
            runner_metadata=runner_metadata,
            message=message,
            event_sink=event_sink,
            stdout=stdout,
            stderr=stderr,
            returncode=completed.returncode,
            gate_content_hash=gate_content_hash,
        )
    if not config.artifact_path.exists():
        message = f'annotation pass did not write artifact: {config.artifact_path}'
        return _handle_annotation_failure(
            config,
            role=role,
            prompt_path=prompt_path,
            prompt_hash=prompt_hash,
            runner_metadata=runner_metadata,
            message=message,
            event_sink=event_sink,
            stdout=stdout,
            stderr=stderr,
            returncode=completed.returncode,
            gate_content_hash=gate_content_hash,
        )

    try:
        _normalize_annotation_artifact(config, prompt_hash, gate_path=gate_path, gate_content_hash=gate_content_hash)
    except AnnotationAgentError as exc:
        _emit_event(
            event_sink,
            'annotation_pass_failed',
            {
                **_event_payload(config, state, prompt_path, prompt_hash, gate_content_hash=gate_content_hash),
                'reason': str(exc),
            },
        )
        raise

    _emit_event(
        event_sink,
        'annotation_pass_completed',
        {
            **_event_payload(config, state, prompt_path, prompt_hash, gate_content_hash=gate_content_hash),
            'returncode': completed.returncode,
        },
    )
    return AnnotationRunResult(
        role=role,
        backend=config.backend,
        status='completed',
        artifact_path=config.artifact_path,
        prompt_path=prompt_path,
        prompt_template_hash=prompt_hash,
        runner_metadata=runner_metadata,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def annotation_enabled(state: dict[str, Any], role: str, *, artifacts_dir: Path) -> bool:
    return normalize_annotation_config(state, role, artifacts_dir=artifacts_dir).enabled


def gate_content_hash_for_annotation(gate_path: Path | None) -> str | None:
    if gate_path is None or not gate_path.exists():
        return None
    try:
        body = gate_body(gate_path.read_text(encoding='utf-8'))
    except OSError:
        return None
    return 'sha256:' + hash_gate_body(body)


def annotation_artifact_matches_gate(artifact_path: Path, gate_path: Path | None) -> bool:
    expected_hash = gate_content_hash_for_annotation(gate_path)
    if expected_hash is None or not artifact_path.exists():
        return False
    try:
        payload = json.loads(artifact_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get('status') not in {'completed', 'warning'}:
        return False
    if payload.get('human_language') != 'zh-CN':
        return False
    return payload.get('gate_content_hash') == expected_hash


def _validate_role(role: str) -> None:
    if role not in ANNOTATION_ROLES:
        raise ValueError(f'Unsupported annotation role: {role}')


def _raw_role_config(state: dict[str, Any], role: str) -> dict[str, Any]:
    for key in ('annotationAgents', 'annotationAgentConfig', 'annotation_agents'):
        raw = state.get(key)
        if isinstance(raw, dict):
            value = raw.get(role)
            if isinstance(value, dict):
                return dict(value)
    return {}


def _stringify_validator_summary(summary: str | dict[str, Any] | None) -> str:
    if summary is None:
        return 'not provided'
    if isinstance(summary, dict):
        return json.dumps(summary, ensure_ascii=False, sort_keys=True)
    text = str(summary).strip()
    return text or 'not provided'


def _product_contract_traceability_audit_section() -> str:
    return (
        '## Product Contract Traceability Audit\n'
        '- 审查目标：辅助人工确认当前版本产品合同的验收标准完整、无歧义，并识别产品合同保真风险；这是 advisory risk-only 标注，不是完整性证明或审批来源。\n'
        '- 抽取当前版本已经纳入合同的入口字段、选择器、受控主体选择、用户步骤、主业务对象、成功终点、错误态、request payload、response/readback、DOM/API/DB/截图/action path 证据要求。\n'
        '- 对照链路：Requirements/Product Design/Spec -> AC/Journey -> Unit Plan test case -> command/user_steps/expected -> Final Acceptance evidence。\n'
        '- 高风险信息衰减：上游字段或 selector 在下游消失；受控主体选择退化成泛化角色按钮；只剩截图或自然语言摘要；只测 route 不测 request payload、response/readback、DOM/API/DB 读回或 action path。\n'
        '- 使用分类：product_contract_gap、information_degradation、product_field_mapping_gap、out_of_scope_boundary_risk；保留 ambiguous_acceptance 用于验收语言本身不清楚的风险。\n'
        '- Scope guard：忽略明确标记为 out-of-scope、future、backlog 或 open question 的事项；但密码/MFA/SSO 排除不能吞掉 trial-login 的用户标识、受控主体选择、actorContext/headerBundle 等正向义务。'
    )


def _command_available(command: str) -> bool:
    if not command:
        return False
    command_path = Path(command)
    if command_path.exists():
        return True
    return shutil.which(command) is not None


def _annotation_subprocess_env(config: AnnotationAgentConfig, prompt_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ('PATH', 'PYTHONPATH', 'HOME', 'LANG', 'LC_ALL'):
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    for key in _annotation_effective_env_keys(config):
        if key in os.environ:
            env[key] = os.environ[key]
    env.update(
        {
            'WAYGATE_ANNOTATION_ROLE': config.role,
            'WAYGATE_ANNOTATION_STAGE': ROLE_STAGES[config.role],
            'WAYGATE_ANNOTATION_PROMPT': str(prompt_path),
            'WAYGATE_ANNOTATION_ARTIFACT': str(config.artifact_path),
        }
    )
    return env


def _annotation_effective_env_keys(config: AnnotationAgentConfig) -> list[str]:
    env_keys = {key for key in config.env_keys if key}
    env_keys.update(
        key for key in DEFAULT_ANNOTATION_PROXY_ENV_KEYS if key in os.environ
    )
    return sorted(env_keys)


def _expanded_command(config: AnnotationAgentConfig, prompt_path: Path) -> list[str]:
    placeholders = {
        'role': config.role,
        'stage': ROLE_STAGES[config.role],
        'prompt_path': str(prompt_path),
        'artifact_path': str(config.artifact_path),
    }
    command = _expand_known_placeholders(config.command, placeholders)
    args = [_expand_known_placeholders(arg, placeholders) for arg in config.args]
    return [command, *args]


def _expand_known_placeholders(value: str, placeholders: dict[str, str]) -> str:
    expanded = value
    for key, replacement in placeholders.items():
        expanded = expanded.replace('{' + key + '}', replacement)
    return expanded


def _normalize_annotation_artifact(
    config: AnnotationAgentConfig,
    prompt_hash: str,
    *,
    gate_path: Path | None,
    gate_content_hash: str | None,
) -> None:
    env_values = _allowed_env_values(config)
    raw_text = _redact_text(config.artifact_path.read_text(encoding='utf-8', errors='replace'), env_values)
    parsed: Any
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = {'summary': raw_text.strip(), 'issues': []}
    approval_markers = _approval_like_markers(parsed, raw_text)
    parsed = annotation_payload_with_promoted_summary_json(parsed)
    approval_markers.update(_approval_like_markers(parsed, raw_text))
    if approval_markers:
        _write_rejected_annotation_artifact(
            config,
            prompt_hash,
            approval_markers,
            gate_path=gate_path,
            gate_content_hash=gate_content_hash,
        )
        raise AnnotationAgentError(
            'annotation artifact contains approval-like field(s): '
            + ', '.join(sorted(approval_markers))
        )
    if not isinstance(parsed, dict):
        parsed = {'summary': str(parsed), 'issues': []}

    issues = _normalized_issues(parsed.get('issues'), config.role)
    summary = _redact_text(str(parsed.get('summary') or ''), env_values).strip()
    if not summary:
        summary = '请查看下方中文风险条目。' if issues else '未发现需要人工关注的额外风险。'
    language_violations = _annotation_language_violations(summary, issues)
    if language_violations:
        _write_language_rejected_annotation_artifact(
            config,
            prompt_hash,
            language_violations,
            gate_path=gate_path,
            gate_content_hash=gate_content_hash,
        )
        raise AnnotationAgentError(
            'annotation artifact human-facing field(s) must be Simplified Chinese: '
            + ', '.join(language_violations)
        )
    payload = {
        'status': 'completed',
        'role': config.role,
        'stage': ROLE_STAGES[config.role],
        'backend': config.backend,
        'human_language': 'zh-CN',
        'prompt_template': config.prompt_template,
        'prompt_template_hash': prompt_hash,
        'gate_path': str(gate_path) if gate_path else None,
        'gate_content_hash': gate_content_hash,
        'artifact_path': str(config.artifact_path),
        'env_keys': _annotation_effective_env_keys(config),
        'summary': summary,
        'issues': issues,
        'risk_taxonomy': list(ROLE_RISK_CATEGORIES[config.role]),
        'non_approval_statement': '本标注 artifact 只提供风险提示，不批准或修改 controller gate 状态。',
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
    config.artifact_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )


def annotation_payload_with_promoted_summary_json(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    summary = value.get('summary')
    if not isinstance(summary, str):
        return value
    text = summary.strip()
    if not text or text[0] not in '{[':
        return value
    try:
        parsed_summary = json.loads(text)
    except json.JSONDecodeError:
        return value
    if not isinstance(parsed_summary, dict):
        return value

    promoted = dict(value)
    nested_summary = parsed_summary.get('summary')
    if nested_summary is not None:
        promoted['summary'] = nested_summary
    nested_issues = parsed_summary.get('issues')
    top_level_issues = promoted.get('issues')
    if isinstance(nested_issues, list) and (
        not isinstance(top_level_issues, list) or not top_level_issues
    ):
        promoted['issues'] = nested_issues
    return promoted


def _verification_assist_role_backend(spec: dict[str, Any]) -> tuple[str, str | None]:
    raw_agent = str(spec.get('agent') or spec.get('role') or '').strip()
    if not raw_agent:
        return DEFAULT_VERIFICATION_ASSIST_ROLE, None
    normalized = raw_agent.replace('_', '-').lower()
    role = ROLE_ALIASES.get(raw_agent) or ROLE_ALIASES.get(normalized)
    if role:
        return role, None
    backend = BACKEND_ALIASES.get(raw_agent) or BACKEND_ALIASES.get(normalized)
    if backend:
        return DEFAULT_VERIFICATION_ASSIST_ROLE, backend
    raise ValueError(f'Unsupported verification_assist.agent: {raw_agent}')


def _verification_assist_case_id(case: dict[str, Any]) -> str:
    value = str(case.get('id') or case.get('name') or 'unknown-case').strip()
    return value or 'unknown-case'


def _verification_assist_artifact_path(
    config: AnnotationAgentConfig,
    *,
    unit_id: str,
    case_id: str,
    artifacts_dir: Path,
) -> Path:
    default_path = artifacts_dir / DEFAULT_ARTIFACT_PATHS[config.role]
    if config.artifact_path == default_path:
        return artifacts_dir / unit_id / 'verification-assist' / f'{_safe_path_segment(case_id)}.json'
    raw = str(config.artifact_path)
    try:
        formatted = raw.format(
            role=config.role,
            stage=ROLE_STAGES[config.role],
            unit_id=unit_id,
            case_id=case_id,
            safe_unit_id=_safe_path_segment(unit_id),
            safe_case_id=_safe_path_segment(case_id),
        )
    except (KeyError, ValueError):
        formatted = raw
    return Path(formatted)


def _safe_path_segment(value: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9_.-]+', '-', str(value).strip())
    return cleaned.strip('.-') or 'item'


def _normalize_verification_assist_artifact(
    config: AnnotationAgentConfig,
    prompt_hash: str,
    *,
    unit_id: str,
    case: dict[str, Any],
) -> dict[str, Any]:
    env_values = _allowed_env_values(config)
    raw_text = _redact_text(config.artifact_path.read_text(encoding='utf-8', errors='replace'), env_values)
    try:
        parsed: Any = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = {'agent_assisted_judgement': {'status': 'needs_human_review', 'summary': raw_text.strip()}}
    approval_markers = _approval_like_markers(parsed, raw_text)
    if approval_markers:
        raise AnnotationAgentError(
            'verification-assist artifact contains approval-like field(s): '
            + ', '.join(sorted(approval_markers))
        )
    if not isinstance(parsed, dict):
        parsed = {'agent_assisted_judgement': {'status': 'needs_human_review', 'summary': str(parsed)}}

    judgement = _verification_assist_judgement(parsed)
    status = str(judgement.get('status') or '').strip().lower()
    if status not in VERIFICATION_ASSIST_CASE_STATUSES:
        status = 'needs_human_review'
        judgement['status'] = status
    if not str(judgement.get('summary') or '').strip():
        judgement['summary'] = 'Agent-assisted judgement did not include a summary.'

    spec = verification_assist_spec_from_case(case) or {}
    human_review_required = parsed.get('human_review_required')
    if human_review_required is None:
        human_review_required = parsed.get('humanReviewRequired')
    if human_review_required is None:
        human_review_required = spec.get('human_review_required')
    if human_review_required is None:
        human_review_required = spec.get('humanReviewRequired')
    if human_review_required is None:
        human_review_required = True

    payload = {
        'status': status,
        'role': config.role,
        'stage': 'verification_assist_case',
        'backend': config.backend,
        'prompt_template': config.prompt_template,
        'prompt_template_hash': prompt_hash,
        'unit_id': unit_id,
        'test_case_id': _verification_assist_case_id(case),
        'artifact_path': str(config.artifact_path),
        'env_keys': _annotation_effective_env_keys(config),
        'agent_assisted_judgement': judgement,
        'risk_annotations': _verification_assist_risk_annotations(parsed.get('risk_annotations') or parsed.get('riskAnnotations')),
        'structured_evidence_refs': _string_list(
            parsed.get('structured_evidence_refs')
            or parsed.get('structuredEvidenceRefs')
            or parsed.get('evidence_refs')
            or parsed.get('evidenceRefs')
        ),
        'human_review_required': bool(human_review_required),
        'non_approval_statement': 'This verification-assist artifact is evidence for one test case and does not approve any Waygate gate.',
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
    config.artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return payload


def _write_verification_assist_failure_artifact(
    config: AnnotationAgentConfig,
    prompt_hash: str,
    *,
    unit_id: str,
    case: dict[str, Any],
    message: str,
    returncode: int | None,
    timeout: bool,
    stdout: str = '',
    stderr: str = '',
) -> dict[str, Any]:
    config.artifact_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'status': 'blocked',
        'role': config.role,
        'stage': 'verification_assist_case',
        'backend': config.backend,
        'prompt_template': config.prompt_template,
        'prompt_template_hash': prompt_hash,
        'unit_id': unit_id,
        'test_case_id': _verification_assist_case_id(case),
        'artifact_path': str(config.artifact_path),
        'env_keys': _annotation_effective_env_keys(config),
        'agent_assisted_judgement': {
            'status': 'blocked',
            'summary': message,
        },
        'risk_annotations': [
            {
                'severity': 'high',
                'category': 'verification_assist_unavailable' if not timeout else 'verification_assist_timeout',
                'note': message,
            }
        ],
        'structured_evidence_refs': [],
        'human_review_required': True,
        'returncode': returncode,
        'timeout': timeout,
        'stdout': stdout[-2000:],
        'stderr': stderr[-2000:],
        'non_approval_statement': 'This verification-assist failure artifact does not approve any Waygate gate.',
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
    config.artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return payload


def _verification_assist_judgement(parsed: dict[str, Any]) -> dict[str, Any]:
    raw = (
        parsed.get('agent_assisted_judgement')
        or parsed.get('agentAssistedJudgement')
        or parsed.get('judgement')
        or parsed.get('judgment')
    )
    if isinstance(raw, dict):
        judgement = dict(raw)
    else:
        judgement = {'summary': str(raw or '').strip()}
    top_level_status = str(parsed.get('status') or '').strip().lower()
    if top_level_status in VERIFICATION_ASSIST_CASE_STATUSES and not judgement.get('status'):
        judgement['status'] = top_level_status
    if not judgement.get('status'):
        judgement['status'] = 'needs_human_review'
    return judgement


def _verification_assist_risk_annotations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    risks: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        severity = str(raw.get('severity') or 'medium').strip().lower()
        if severity not in {'low', 'medium', 'high'}:
            severity = 'medium'
        category = str(raw.get('category') or raw.get('type') or 'risk_assumption').strip() or 'risk_assumption'
        note = str(raw.get('note') or raw.get('message') or raw.get('summary') or '').strip()
        risks.append({'severity': severity, 'category': category, 'note': note})
    return risks


def _string_value(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _jsonish_text(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple) or isinstance(value, set):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _normalized_issues(raw_issues: Any, role: str) -> list[dict[str, Any]]:
    if not isinstance(raw_issues, list):
        return []
    allowed = set(ROLE_RISK_CATEGORIES[role])
    normalized: list[dict[str, Any]] = []
    for raw in raw_issues:
        if not isinstance(raw, dict):
            continue
        category = str(raw.get('category') or 'weak_evidence').strip()
        if category not in allowed:
            category = 'weak_evidence' if 'weak_evidence' in allowed else next(iter(allowed))
        severity = str(raw.get('severity') or 'medium').strip().lower()
        if severity not in {'low', 'medium', 'high'}:
            severity = 'medium'
        normalized.append(
            {
                'category': category,
                'severity': severity,
                'location': str(raw.get('location') or '').strip() or None,
                'linked_ac': str(raw.get('linked_ac') or raw.get('linkedAC') or '').strip() or None,
                'linked_ao': str(raw.get('linked_ao') or raw.get('linkedAO') or '').strip() or None,
                'linked_journey': str(raw.get('linked_journey') or raw.get('linkedJourney') or '').strip() or None,
                'message': str(raw.get('message') or '').strip(),
                'evidence_refs': [
                    str(ref)
                    for ref in raw.get('evidence_refs', [])
                    if str(ref).strip()
                ] if isinstance(raw.get('evidence_refs'), list) else [],
            }
        )
    return normalized


def _annotation_language_violations(summary: str, issues: list[dict[str, Any]]) -> list[str]:
    violations: list[str] = []
    if not _contains_cjk(summary):
        violations.append('summary')
    for index, issue in enumerate(issues):
        message = str(issue.get('message') or '').strip()
        if not message or not _contains_cjk(message):
            violations.append(f'issues[{index}].message')
    return violations


def _contains_cjk(text: str) -> bool:
    return re.search(r'[\u3400-\u9fff]', text) is not None


def _approval_like_markers(value: Any, raw_text: str) -> set[str]:
    markers: set[str] = set()
    if 'Status: approved' in raw_text:
        markers.add('Status: approved')
    markers.update(_approval_like_fields(value))
    return markers


def _approval_like_fields(value: Any, prefix: str = '') -> set[str]:
    markers: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            normalized = re.sub(r'[^a-z0-9]', '', key_text.lower())
            path = f'{prefix}.{key_text}' if prefix else key_text
            if normalized in FORBIDDEN_APPROVAL_FIELD_KEYS:
                markers.add(path)
            if normalized == 'status' and str(child).strip().lower() == 'approved':
                markers.add(path)
            markers.update(_approval_like_fields(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            markers.update(_approval_like_fields(child, f'{prefix}[{index}]'))
    elif isinstance(value, str):
        text = value.strip()
        if text and text[0] in '{[':
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return markers
            markers.update(_approval_like_fields(parsed, prefix))
    return markers


def _write_rejected_annotation_artifact(
    config: AnnotationAgentConfig,
    prompt_hash: str,
    approval_markers: set[str],
    *,
    gate_path: Path | None,
    gate_content_hash: str | None,
) -> None:
    safe_markers = [
        'approval_status_marker' if marker == 'Status: approved' else marker
        for marker in sorted(approval_markers)
    ]
    payload = {
        'status': 'rejected',
        'role': config.role,
        'stage': ROLE_STAGES[config.role],
        'backend': config.backend,
        'human_language': 'zh-CN',
        'prompt_template': config.prompt_template,
        'prompt_template_hash': prompt_hash,
        'gate_path': str(gate_path) if gate_path else None,
        'gate_content_hash': gate_content_hash,
        'artifact_path': str(config.artifact_path),
        'env_keys': _annotation_effective_env_keys(config),
        'issues': [
            {
                'category': 'approval_like_payload',
                'severity': 'high',
                'location': 'annotation artifact',
                'linked_ac': None,
                'linked_ao': 'AO-001',
                'linked_journey': None,
                'message': 'Annotation 输出包含类似批准状态的字段，已被拒绝。',
                'evidence_refs': [],
            }
        ],
        'rejected_fields': safe_markers,
        'non_approval_statement': '本标注 artifact 已被拒绝，不批准或修改 controller gate 状态。',
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
    config.artifact_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )


def _write_language_rejected_annotation_artifact(
    config: AnnotationAgentConfig,
    prompt_hash: str,
    language_violations: list[str],
    *,
    gate_path: Path | None,
    gate_content_hash: str | None,
) -> None:
    payload = {
        'status': 'rejected',
        'role': config.role,
        'stage': ROLE_STAGES[config.role],
        'backend': config.backend,
        'human_language': 'zh-CN',
        'prompt_template': config.prompt_template,
        'prompt_template_hash': prompt_hash,
        'gate_path': str(gate_path) if gate_path else None,
        'gate_content_hash': gate_content_hash,
        'artifact_path': str(config.artifact_path),
        'env_keys': _annotation_effective_env_keys(config),
        'summary': 'Annotation 输出的人类可见批注字段不是简体中文，已被拒绝。',
        'issues': [
            {
                'category': 'weak_evidence',
                'severity': 'high',
                'location': 'annotation artifact',
                'linked_ac': None,
                'linked_ao': 'AO-001',
                'linked_journey': None,
                'message': '人类可见批注字段必须使用简体中文；请重新生成中文 summary 和中文风险批注。',
                'evidence_refs': [],
            }
        ],
        'language_violations': list(language_violations),
        'non_approval_statement': '本标注 artifact 已被拒绝，不批准或修改 controller gate 状态。',
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
    config.artifact_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )


def _handle_annotation_failure(
    config: AnnotationAgentConfig,
    *,
    role: str,
    prompt_path: Path,
    prompt_hash: str,
    runner_metadata: dict[str, Any],
    message: str,
    event_sink: Callable[[str, dict[str, Any]], None] | None,
    gate_content_hash: str | None,
    stdout: str = '',
    stderr: str = '',
    returncode: int | None = None,
    timeout: bool = False,
) -> AnnotationRunResult:
    status = 'warning' if config.failure_policy == 'warn' else 'failed'
    _write_failure_artifact(
        config,
        prompt_hash=prompt_hash,
        status=status,
        message=message,
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
        timeout=timeout,
        gate_content_hash=gate_content_hash,
    )
    event_name = 'annotation_pass_warning' if status == 'warning' else 'annotation_pass_failed'
    _emit_event(
        event_sink,
        event_name,
        {
            'role': role,
            'stage': ROLE_STAGES[role],
            'backend': config.backend,
            'artifact_path': str(config.artifact_path),
            'prompt_path': str(prompt_path),
            'prompt_template_hash': prompt_hash,
            'gate_content_hash': gate_content_hash,
            'env_keys': _annotation_effective_env_keys(config),
            'failure_policy': config.failure_policy,
            'reason': message,
            'returncode': returncode,
            'timeout': timeout,
        },
    )
    result = AnnotationRunResult(
        role=role,
        backend=config.backend,
        status=status,
        artifact_path=config.artifact_path,
        prompt_path=prompt_path,
        prompt_template_hash=prompt_hash,
        runner_metadata=runner_metadata,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )
    if config.failure_policy == 'warn':
        return result
    raise AnnotationAgentError(message, runner_metadata=runner_metadata)


def _write_failure_artifact(
    config: AnnotationAgentConfig,
    *,
    prompt_hash: str,
    status: str,
    message: str,
    stdout: str,
    stderr: str,
    returncode: int | None,
    timeout: bool,
    gate_content_hash: str | None,
) -> None:
    config.artifact_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'status': status,
        'role': config.role,
        'stage': ROLE_STAGES[config.role],
        'backend': config.backend,
        'human_language': 'zh-CN',
        'prompt_template': config.prompt_template,
        'prompt_template_hash': prompt_hash,
        'gate_content_hash': gate_content_hash,
        'artifact_path': str(config.artifact_path),
        'env_keys': _annotation_effective_env_keys(config),
        'failure_policy': config.failure_policy,
        'summary': f'标注运行失败：{message}',
        'returncode': returncode,
        'timeout': timeout,
        'stdout': stdout[-2000:],
        'stderr': stderr[-2000:],
        'issues': [
            {
                'category': 'annotation_pass_unavailable' if not timeout else 'annotation_pass_timeout',
                'severity': 'high' if config.failure_policy == 'block' else 'medium',
                'location': 'annotation runner',
                'linked_ac': None,
                'linked_ao': 'AO-001',
                'linked_journey': None,
                'message': f'标注运行失败：{message}',
                'evidence_refs': [],
            }
        ],
        'non_approval_statement': '本标注失败 artifact 不批准或修改 controller gate 状态。',
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
    config.artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _default_evidence_refs(role: str, state: dict[str, Any], artifacts_dir: Path, state_dir: Path) -> list[str]:
    refs: list[str] = []
    if role == 'requirements_annotation':
        _append_state_artifact_ref(refs, state, 'scope')
        _append_existing_ref(
            refs,
            artifacts_dir / 'requirements-scope' / 'requirements-scope.md',
            artifacts_dir / 'requirements-draft' / 'requirements-scope.md',
        )
        _append_state_artifact_ref(refs, state, 'product_design')
        _append_existing_ref(
            refs,
            artifacts_dir / 'requirements-product-design' / 'product-design-brief.md',
            artifacts_dir / 'requirements-draft' / 'product-design.md',
            artifacts_dir / 'requirements-draft' / 'product-design-brief.md',
        )
        _append_state_artifact_ref(refs, state, 'test_strategy')
        _append_existing_ref(
            refs,
            artifacts_dir / 'requirements-test-strategy' / 'test-strategy-brief.md',
            artifacts_dir / 'requirements-draft' / 'requirements-test-strategy.md',
            artifacts_dir / 'requirements-draft' / 'test-strategy-brief.md',
        )
        _append_existing_ref(
            refs,
            artifacts_dir / 'requirements-spec-intake' / 'source-map.json',
            artifacts_dir / 'requirements-spec-intake' / 'normalized-requirements.json',
            artifacts_dir / 'requirements-draft' / 'prototype-manifest.json',
        )
    elif role == 'unit_plan_annotation':
        _append_existing_ref(
            refs,
            artifacts_dir / 'unit-plan-draft' / 'unit-plan-body.md',
            state_dir / 'approvals' / 'requirements-and-acceptance.md',
        )
        _append_state_artifact_ref(refs, state, 'product_design')
        _append_state_artifact_ref(refs, state, 'test_strategy')
        _append_existing_ref(
            refs,
            artifacts_dir / 'requirements-product-design' / 'product-design-brief.md',
            artifacts_dir / 'requirements-draft' / 'product-design.md',
            artifacts_dir / 'requirements-test-strategy' / 'test-strategy-brief.md',
            artifacts_dir / 'requirements-draft' / 'requirements-test-strategy.md',
            artifacts_dir / 'journeys' / 'journeys.json',
            artifacts_dir / 'requirements-draft' / 'prototype-manifest.json',
        )
    else:
        current_unit = str(state.get('currentUnitId') or '').strip()
        if current_unit:
            _append_existing_ref(refs, artifacts_dir / current_unit / 'verification.json')
        _append_existing_ref(
            refs,
            state_dir / 'approvals' / 'requirements-and-acceptance.md',
            state_dir / 'approvals' / 'unit-plan.md',
            artifacts_dir / 'final-scope-audit.json',
            artifacts_dir / 'final-acceptance' / 'final-scope-audit.json',
            artifacts_dir / 'final-acceptance' / 'prototype-conformance-matrix.json',
        )
    return refs


def _append_existing_ref(refs: list[str], *paths: Path) -> None:
    for path in paths:
        if path.exists():
            _append_ref(refs, str(path))


def _append_state_artifact_ref(refs: list[str], state: dict[str, Any], stage: str) -> None:
    package = state.get('requirementsPackage')
    artifacts = package.get('artifacts') if isinstance(package, dict) else None
    record = artifacts.get(stage) if isinstance(artifacts, dict) else None
    if not isinstance(record, dict):
        return
    path = str(record.get('path') or '').strip()
    if path:
        _append_ref(refs, path)


def _append_ref(refs: list[str], ref: str) -> None:
    if ref and ref not in refs:
        refs.append(ref)


def _allowed_env_values(config: AnnotationAgentConfig) -> list[str]:
    values: list[str] = []
    for key in _annotation_effective_env_keys(config):
        value = os.environ.get(key)
        if value:
            values.append(value)
    return values


def _redact_text(text: str | bytes | None, secret_values: list[str]) -> str:
    if text is None:
        redacted = ''
    elif isinstance(text, bytes):
        redacted = text.decode(errors='replace')
    else:
        redacted = text
    for value in sorted(secret_values, key=len, reverse=True):
        if value:
            redacted = redacted.replace(value, '[redacted]')
    return redacted


def _event_payload(
    config: AnnotationAgentConfig,
    state: dict[str, Any],
    prompt_path: Path,
    prompt_hash: str,
    *,
    gate_content_hash: str | None = None,
) -> dict[str, Any]:
    return {
        'task_id': state.get('task_id'),
        'unit_id': state.get('currentUnitId'),
        'role': config.role,
        'stage': ROLE_STAGES[config.role],
        'backend': config.backend,
        'artifact_path': str(config.artifact_path),
        'prompt_path': str(prompt_path),
        'prompt_template': config.prompt_template,
        'prompt_template_hash': prompt_hash,
        'gate_content_hash': gate_content_hash,
        'env_keys': _annotation_effective_env_keys(config),
        'failure_policy': config.failure_policy,
    }


def _emit_event(
    event_sink: Callable[[str, dict[str, Any]], None] | None,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    if event_sink is not None:
        event_sink(event_type, payload)
