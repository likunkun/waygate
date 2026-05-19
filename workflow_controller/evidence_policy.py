from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any


REAL_E2E_ENVIRONMENT_KINDS = {'local_real', 'production_readonly'}
MOCK_ENVIRONMENT_KINDS = {'component_mock', 'contract_mock', 'visual'}
BROWSER_RUNTIME_FIELDS = (
    'browser_console_errors',
    'page_errors',
    'request_failures',
    'screenshot_refs',
)
RUNTIME_ERROR_FIELDS = (
    'browser_console_errors',
    'page_errors',
    'request_failures',
)

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
        refs.update(match.group(0).upper() for match in re.finditer(r'\bAC-\d+(?:[-.]\d+)*\b', item, re.I))
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
