from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any

from workflow_controller.requirements_ids import acceptance_criterion_ids_in_text


REAL_E2E_ENVIRONMENT_KINDS = {'local_real', 'production_readonly'}
MOCK_ENVIRONMENT_KINDS = {'component_mock', 'contract_mock', 'visual'}
BROWSER_RUNTIME_FIELDS = (
    'browser_console_errors',
    'page_errors',
    'request_failures',
    'screenshot_refs',
)
VISUAL_EVIDENCE_REF_FIELDS = (
    'prototype_screenshot',
    'production_screenshot',
    'interaction_screenshot',
    'viewport',
    'entrypoint',
    'action_path',
    'fidelity_level',
)
RUNTIME_ERROR_FIELDS = (
    'browser_console_errors',
    'page_errors',
    'request_failures',
)
DEFAULT_FIDELITY_LEVEL = 'structural_interaction'
FIDELITY_LEVEL_ORDER = {
    'visual_evidence': 1,
    'structural_interaction': 2,
    'screenshot_regression': 3,
    'pixel_exact': 4,
}
FIDELITY_LEVEL_LABELS = {
    'visual_evidence': 'L1 visual_evidence',
    'structural_interaction': 'L2 structural_interaction',
    'screenshot_regression': 'L3 screenshot_regression',
    'pixel_exact': 'L4 pixel_exact',
}

_TEST_FILE_EXTENSIONS = {
    '.cjs',
    '.cts',
    '.js',
    '.jsx',
    '.mjs',
    '.mts',
    '.py',
    '.ts',
    '.tsx',
}


def case_environment_kind(case: dict[str, Any], result: dict[str, Any] | None = None) -> str:
    raw = _first_present(
        case,
        'environment_kind',
        'environmentKind',
        'environment',
        'env_kind',
        'envKind',
    )
    if raw is None and isinstance(result, dict):
        raw = _first_present(result, 'environment_kind', 'environmentKind', 'environment')
    value = str(raw or '').strip()
    if value:
        return value
    if case_allows_mock(case):
        return 'contract_mock'
    return 'local_real'


def case_real_entrypoint(case: dict[str, Any], command: str | None = None) -> str | None:
    raw = _first_present(case, 'real_entrypoint', 'realEntrypoint', 'entrypoint', 'entry_point')
    if raw is not None:
        value = str(raw).strip()
        return value or None
    targets = _string_list(
        case.get('production_targets')
        or case.get('productionTargets')
        or case.get('implementation_targets')
        or case.get('implementationTargets')
        or case.get('real_targets')
        or case.get('realTargets')
    )
    if targets:
        return targets[0]
    return command.strip() if command and command.strip() else None


def case_allows_mock(case: dict[str, Any]) -> bool:
    return case.get('allows_mock') is True or case.get('allowsMock') is True


def case_declares_core_api_mock(case: dict[str, Any]) -> bool:
    if case.get('uses_core_api_mock') is True or case.get('usesCoreApiMock') is True:
        return True
    return any(_route_is_core_api(route) for route in case_declared_mocked_routes(case))


def case_declared_mocked_routes(case: dict[str, Any]) -> list[str]:
    return _dedupe_strings(
        _string_list(case.get('mocked_routes') or case.get('mockedRoutes') or case.get('mock_routes'))
    )


def case_has_prototype_conformance(case: dict[str, Any]) -> bool:
    return bool(
        _string_list(case.get('prototype_conformance') or case.get('prototypeConformance'))
    )


def normalize_fidelity_required(value: Any, *, default: str = DEFAULT_FIDELITY_LEVEL) -> str:
    texts = _flatten_text_values(value)
    if not texts:
        return default if default in FIDELITY_LEVEL_ORDER else DEFAULT_FIDELITY_LEVEL
    normalized = ' '.join(texts).lower().replace('-', '_')
    if 'pixel_exact' in normalized or 'pixel exact' in normalized or 'near_pixel' in normalized or 'l4' in normalized:
        return 'pixel_exact'
    if (
        'screenshot_regression' in normalized
        or 'screenshot regression' in normalized
        or 'visual_regression' in normalized
        or 'visual regression' in normalized
        or 'l3' in normalized
    ):
        return 'screenshot_regression'
    if 'structural_interaction' in normalized or 'structural interaction' in normalized or 'interaction' in normalized or 'l2' in normalized:
        return 'structural_interaction'
    if 'visual_evidence' in normalized or 'visual evidence' in normalized or 'screenshot' in normalized or 'l1' in normalized:
        return 'visual_evidence'
    return default if default in FIDELITY_LEVEL_ORDER else DEFAULT_FIDELITY_LEVEL


def fidelity_rank(level: Any) -> int:
    return FIDELITY_LEVEL_ORDER.get(normalize_fidelity_required(level), FIDELITY_LEVEL_ORDER[DEFAULT_FIDELITY_LEVEL])


def fidelity_label(level: Any) -> str:
    normalized = normalize_fidelity_required(level)
    return FIDELITY_LEVEL_LABELS.get(normalized, FIDELITY_LEVEL_LABELS[DEFAULT_FIDELITY_LEVEL])


def case_requires_real_e2e(
    case: dict[str, Any],
    *,
    current_unit_is_web_system: bool = False,
    e2e_acceptance_criteria: set[str] | None = None,
) -> bool:
    layer = str(case.get('layer') or '').strip().lower()
    if layer == 'e2e':
        return True
    if case.get('golden_path') is True or case_has_prototype_conformance(case):
        return True
    if _case_acceptance_criteria(case) & (e2e_acceptance_criteria or set()):
        return True
    if current_unit_is_web_system and not _case_is_explicit_mock_auxiliary(case):
        return _command_looks_browser_based(str(case.get('command') or '')) or bool(case.get('command'))
    return False


def evidence_row_real_e2e_issue(row: dict[str, Any]) -> str:
    status = str(row.get('status') or '').strip().lower()
    if status != 'passed':
        return status or 'missing'
    layer = str(row.get('layer') or '').strip().lower()
    if layer != 'e2e':
        return 'not e2e evidence'
    if row.get('uses_core_api_mock') is True:
        return 'core API mock'
    environment_kind = str(row.get('environment_kind') or 'local_real').strip()
    if environment_kind not in REAL_E2E_ENVIRONMENT_KINDS:
        return f'environment_kind={environment_kind or "missing"} is not real E2E'
    if not str(row.get('real_entrypoint') or '').strip():
        return 'missing real entrypoint'
    if evidence_row_runtime_error_count(row):
        return 'browser runtime errors'
    return ''


def evidence_row_runtime_error_count(row: dict[str, Any]) -> int:
    return sum(len(_string_list(row.get(field))) for field in RUNTIME_ERROR_FIELDS)


def browser_runtime_fields(
    *,
    case: dict[str, Any],
    result: dict[str, Any] | None,
) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for field in BROWSER_RUNTIME_FIELDS:
        fields[field] = _dedupe_strings([
            *_string_list(case.get(field) or case.get(_camel_case(field))),
            *_string_list((result or {}).get(field) if isinstance(result, dict) else None),
            *_runtime_markers_from_result(result, field),
        ])
    return fields


def case_visual_evidence_plan(case: dict[str, Any]) -> dict[str, Any]:
    raw = _first_present(
        case,
        'visual_evidence_plan',
        'visualEvidencePlan',
        'visual_evidence_refs',
        'visualEvidenceRefs',
    )
    if not isinstance(raw, dict):
        return {}
    return _normalize_visual_evidence_refs(raw)


def visual_evidence_refs_from_result(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    refs: dict[str, Any] = {}
    raw = _first_present(result, 'visual_evidence_refs', 'visualEvidenceRefs', 'visual_evidence', 'visualEvidence')
    if isinstance(raw, dict):
        refs.update(_normalize_visual_evidence_refs(raw))
    for source_field in ('stdout', 'stderr'):
        refs.update(_visual_evidence_markers_from_text(str(result.get(source_field) or '')))
    return _normalize_visual_evidence_refs(refs)


def visual_evidence_issue(
    refs: dict[str, Any],
    *,
    fidelity_level: Any = DEFAULT_FIDELITY_LEVEL,
    requires_interaction: bool = True,
) -> str:
    normalized = _normalize_visual_evidence_refs(refs)
    required_level = normalize_fidelity_required(fidelity_level)
    rank = fidelity_rank(required_level)
    if not str(normalized.get('prototype_screenshot') or '').strip():
        return 'missing prototype screenshot'
    if not str(normalized.get('production_screenshot') or '').strip():
        return 'missing production screenshot'
    if rank >= FIDELITY_LEVEL_ORDER['structural_interaction']:
        if not _string_list(normalized.get('action_path')):
            return 'missing action path'
        if requires_interaction and not str(normalized.get('interaction_screenshot') or '').strip():
            return 'missing interaction screenshot'
        if _visual_evidence_reports_obstruction(normalized):
            return 'interaction target obstructed'
    if rank >= FIDELITY_LEVEL_ORDER['screenshot_regression'] and not _visual_evidence_has_regression_result(normalized):
        return 'missing screenshot regression result'
    return ''


def command_core_api_mock_routes(
    command: str | None,
    *,
    workspace_dir: Path | None,
) -> list[str]:
    if not command or workspace_dir is None:
        return []
    routes: list[str] = []
    for path in _command_candidate_files(command, workspace_dir):
        routes.extend(scan_file_for_core_api_mocks(path))
    return _dedupe_strings(routes)


def scan_file_for_core_api_mocks(path: Path) -> list[str]:
    try:
        content = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return []
    return scan_text_for_core_api_mocks(content)


def scan_text_for_core_api_mocks(content: str) -> list[str]:
    routes: list[str] = []
    for match in re.finditer(
        r'\b(?:page|context|browserContext)\.route\s*\((.{0,320})',
        content,
        flags=re.DOTALL,
    ):
        snippet = match.group(1)
        if not _snippet_mentions_core_api(snippet):
            continue
        route = _first_route_literal(snippet) or 'page.route(<core api>)'
        routes.append(route)
    if 'route_common(page' in content or 'route_common(' in content:
        routes.append('route_common(page)')
    if re.search(r'\broute\.fulfill\s*\(', content) and _snippet_mentions_core_api(content):
        if not routes:
            routes.append('route.fulfill(<core api>)')
    mock_server_patterns = [
        r'\bmock\s+api\s+server\b',
        r'\bstub(?:bed)?\s+api\s+server\b',
        r'\bfixture[-\s]+only\s+server\b',
        r'\bfixture\s+api\b',
    ]
    lowered = content.lower()
    if any(re.search(pattern, lowered) for pattern in mock_server_patterns) and _snippet_mentions_core_api(content):
        routes.append('mock API server')
    return _dedupe_strings(route for route in routes if _route_is_core_api(route) or route in {
        'route_common(page)',
        'route.fulfill(<core api>)',
        'mock API server',
    })


def _command_candidate_files(command: str, workspace_dir: Path) -> list[Path]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    candidates: list[Path] = []
    for token in tokens:
        normalized = _normalize_command_path_token(token)
        if not normalized:
            continue
        path = Path(normalized)
        if not path.is_absolute():
            path = workspace_dir / path
        if not path.exists():
            continue
        if path.is_file() and path.suffix in _TEST_FILE_EXTENSIONS:
            candidates.append(path)
        elif path.is_dir():
            candidates.extend(_test_files_under(path))

    lowered = command.lower()
    if not candidates and _command_looks_browser_based(lowered):
        for default_dir in ('tests/e2e', 'e2e', 'playwright', 'tests'):
            path = workspace_dir / default_dir
            if path.exists() and path.is_dir():
                candidates.extend(_test_files_under(path))
                break
    return _dedupe_paths(candidates)


def _normalize_command_path_token(token: str) -> str:
    stripped = token.strip().strip('"\'')
    if not stripped or stripped.startswith('-'):
        return ''
    if '=' in stripped and not any(sep in stripped for sep in ('/', '\\')):
        return ''
    stripped = re.sub(r'(?::\d+(?::\d+)?)$', '', stripped)
    if stripped.startswith(('http://', 'https://')):
        return ''
    if any(char in stripped for char in '*?[]{}'):
        return ''
    suffix = Path(stripped).suffix
    if suffix and suffix not in _TEST_FILE_EXTENSIONS:
        return ''
    return stripped


def _test_files_under(path: Path) -> list[Path]:
    files: list[Path] = []
    for child in path.rglob('*'):
        if child.is_file() and child.suffix in _TEST_FILE_EXTENSIONS:
            files.append(child)
        if len(files) >= 200:
            break
    return files


def _first_route_literal(snippet: str) -> str | None:
    string_match = re.search(r'''(['"`])(.+?)\1''', snippet, flags=re.DOTALL)
    if string_match:
        return re.sub(r'\s+', ' ', string_match.group(2)).strip()
    regex_match = re.search(r'/((?:\\/|[^/])*)/[a-z]*', snippet)
    if regex_match:
        return '/' + regex_match.group(1).replace('\\/', '/') + '/'
    return None


def _snippet_mentions_core_api(snippet: str) -> bool:
    normalized = snippet.replace('\\/', '/').lower()
    return bool(re.search(r'(?:^|[^a-z0-9_-])(?:\*\*/)?api(?:/|[^a-z0-9_-]|$)', normalized))


def _route_is_core_api(route: str) -> bool:
    normalized = str(route or '').replace('\\/', '/').lower()
    if 'route_common(page)' in normalized or 'mock api server' in normalized:
        return True
    return bool(re.search(r'(?:^|[^a-z0-9_-])(?:\*\*/)?api(?:/|[^a-z0-9_-]|$)', normalized))


def _case_is_explicit_mock_auxiliary(case: dict[str, Any]) -> bool:
    return case_allows_mock(case) and case_environment_kind(case) in MOCK_ENVIRONMENT_KINDS


def _command_looks_browser_based(command: str) -> bool:
    lowered = str(command or '').lower()
    return any(term in lowered for term in ('playwright', 'browser', 'page.', 'tests/e2e', '/e2e/'))


def _case_acceptance_criteria(case: dict[str, Any]) -> set[str]:
    raw = (
        case.get('acceptance_criteria')
        or case.get('acceptanceCriteria')
        or case.get('acceptance_criterion')
        or case.get('acceptanceCriterion')
    )
    refs = set()
    for item in _string_list(raw):
        refs.update(acceptance_criterion_ids_in_text(item))
    return refs


def _runtime_markers_from_result(result: dict[str, Any] | None, field: str) -> list[str]:
    if not isinstance(result, dict):
        return []
    values: list[str] = []
    for source_field in ('stdout', 'stderr'):
        text = str(result.get(source_field) or '')
        values.extend(_runtime_markers_from_text(text, field))
    return values


def _runtime_markers_from_text(text: str, field: str) -> list[str]:
    if not text:
        return []
    values: list[str] = []
    marker_prefixes = {
        'browser_console_errors': ('BROWSER_CONSOLE_ERROR:', 'CONSOLE_ERROR:'),
        'page_errors': ('PAGE_ERROR:',),
        'request_failures': ('REQUEST_FAILED:', 'REQUEST_FAILURE:', 'API_RESPONSE_ERROR:'),
        'screenshot_refs': ('SCREENSHOT:', 'SCREENSHOT_REF:'),
    }
    for line in text.splitlines():
        stripped = line.strip()
        for prefix in marker_prefixes.get(field, ()):
            if stripped.startswith(prefix):
                values.append(stripped[len(prefix):].strip())
        if not (stripped.startswith('{') and stripped.endswith('}')):
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            values.extend(_string_list(payload.get(field)))
    return values


def _visual_evidence_markers_from_text(text: str) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    if not text:
        return refs
    marker_fields = {
        'PROTOTYPE_SCREENSHOT:': 'prototype_screenshot',
        'PRODUCTION_SCREENSHOT:': 'production_screenshot',
        'INTERACTION_SCREENSHOT:': 'interaction_screenshot',
    }
    for line in text.splitlines():
        stripped = line.strip()
        for prefix, field in marker_fields.items():
            if stripped.startswith(prefix):
                refs[field] = stripped[len(prefix):].strip()
        if stripped.startswith('VISUAL_EVIDENCE:'):
            payload_text = stripped[len('VISUAL_EVIDENCE:'):].strip()
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                refs.update(_normalize_visual_evidence_refs(payload))
            continue
        if not (stripped.startswith('{') and stripped.endswith('}')):
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        raw_refs = payload.get('visual_evidence_refs') or payload.get('visualEvidenceRefs')
        if isinstance(raw_refs, dict):
            refs.update(_normalize_visual_evidence_refs(raw_refs))
    return refs


def _normalize_visual_evidence_refs(raw: dict[str, Any]) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    alias_map = {
        'prototype_screenshot': ('prototype_screenshot', 'prototypeScreenshot', 'prototype', 'baseline_screenshot'),
        'production_screenshot': ('production_screenshot', 'productionScreenshot', 'production', 'actual_screenshot'),
        'interaction_screenshot': ('interaction_screenshot', 'interactionScreenshot', 'after_interaction_screenshot'),
        'viewport': ('viewport', 'viewport_size', 'viewportSize'),
        'entrypoint': ('entrypoint', 'entry_point', 'real_entrypoint', 'realEntrypoint'),
        'action_path': ('action_path', 'actionPath', 'click_path', 'clickPath', 'user_steps', 'userSteps'),
        'fidelity_level': ('fidelity_level', 'fidelityLevel', 'fidelity_required', 'fidelityRequired'),
        'screenshot_regression': ('screenshot_regression', 'screenshotRegression', 'screenshot_regression_result'),
        'pixel_exact': ('pixel_exact', 'pixelExact', 'pixel_exact_result'),
        'pixel_diff': ('pixel_diff', 'pixelDiff'),
        'pixel_tolerance': ('pixel_tolerance', 'pixelTolerance'),
        'interaction_target_obstructed': (
            'interaction_target_obstructed',
            'interactionTargetObstructed',
            'target_obstructed',
            'targetObstructed',
        ),
        'obstruction_check': ('obstruction_check', 'obstructionCheck'),
    }
    for canonical, aliases in alias_map.items():
        value = _first_present(raw, *aliases)
        if value is None:
            continue
        if canonical == 'action_path':
            items = _string_list(value)
            if items:
                refs[canonical] = items
        elif canonical == 'fidelity_level':
            refs[canonical] = normalize_fidelity_required(value)
        else:
            refs[canonical] = value
    _merge_nested_visual_evidence_refs(refs, raw)
    return refs


def _merge_nested_visual_evidence_refs(refs: dict[str, Any], raw: dict[str, Any]) -> None:
    for nested_key in (
        'screenshot_regression_result',
        'screenshotRegressionResult',
        'screenshot_regression',
        'screenshotRegression',
        'pixel_exact_result',
        'pixelExactResult',
        'pixel_exact',
        'pixelExact',
    ):
        nested = raw.get(nested_key)
        if not isinstance(nested, dict) or nested is raw:
            continue
        action_path = _first_present(
            nested,
            'action_path',
            'actionPath',
            'click_path',
            'clickPath',
            'user_steps',
            'userSteps',
        )
        if 'action_path' not in refs:
            items = _string_list(action_path)
            if items:
                refs['action_path'] = items
        entrypoint = _first_present(nested, 'entrypoint', 'entry_point', 'real_entrypoint', 'realEntrypoint')
        if entrypoint is not None and 'entrypoint' not in refs:
            value = str(entrypoint).strip()
            if value:
                refs['entrypoint'] = value
        fidelity_level = _first_present(nested, 'fidelity_level', 'fidelityLevel', 'fidelity_required', 'fidelityRequired')
        if fidelity_level is not None and 'fidelity_level' not in refs:
            refs['fidelity_level'] = normalize_fidelity_required(fidelity_level)
        pixel_tolerance = _first_present(nested, 'pixel_tolerance', 'pixelTolerance', 'threshold')
        if pixel_tolerance is not None and 'pixel_tolerance' not in refs:
            refs['pixel_tolerance'] = pixel_tolerance
        compared = _first_present(nested, 'compared_screenshots', 'comparedScreenshots')
        if isinstance(compared, dict):
            compared_refs = _normalize_visual_evidence_refs(compared)
            for field in ('prototype_screenshot', 'production_screenshot', 'interaction_screenshot'):
                if field not in refs and compared_refs.get(field):
                    refs[field] = compared_refs[field]


def _visual_evidence_reports_obstruction(refs: dict[str, Any]) -> bool:
    if refs.get('interaction_target_obstructed') is True:
        return True
    check = str(refs.get('obstruction_check') or '').strip().lower()
    if not check:
        return False
    if any(term in check for term in ('fail', 'failed', 'blocked', 'obstructed', '遮挡', '拦截')):
        return True
    return False


def _visual_evidence_has_regression_result(refs: dict[str, Any]) -> bool:
    for field in ('screenshot_regression', 'pixel_exact', 'pixel_diff', 'pixel_tolerance'):
        value = refs.get(field)
        if value is not None and str(value).strip():
            return True
    return False


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple) or isinstance(value, set):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r'[,;\n]', text) if part.strip()]


def _flatten_text_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        texts: list[str] = []
        for key in ('level', 'fidelity', 'required', 'mode', 'name'):
            if key in value:
                texts.extend(_flatten_text_values(value.get(key)))
        if not texts:
            texts.extend(str(item) for item in value.values())
        return [text.strip() for text in texts if str(text).strip()]
    if isinstance(value, (list, tuple, set)):
        texts = []
        for item in value:
            texts.extend(_flatten_text_values(item))
        return texts
    text = str(value).strip()
    return [text] if text else []


def _dedupe_strings(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(path)
    return result


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _camel_case(value: str) -> str:
    parts = value.split('_')
    return parts[0] + ''.join(part.capitalize() for part in parts[1:])
