from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SUPPORTED_SOURCE_TYPE = 'waygate-markdown'
OPENSPEC_SOURCE_TYPE = 'openspec'
SPEC_KIT_SOURCE_TYPE = 'spec-kit'
ASYNCAPI_SOURCE_TYPE = 'asyncapi'
SUPPORTED_EXTERNAL_SOURCE_TYPES = {OPENSPEC_SOURCE_TYPE, SPEC_KIT_SOURCE_TYPE}
SENSITIVE_KEY_PATTERN = re.compile(r'(token|password|secret|api[_-]?key|signature|database[_-]?url)', re.I)
DATABASE_URL_PATTERN = re.compile(r'\b[a-z][a-z0-9+.-]*://[^@\s:/]+:[^@\s]+@[^)\]\s,;]+', re.I)
HTTP_METHODS = {'get', 'post', 'put', 'delete', 'patch', 'options', 'head'}


def requirements_spec_metadata(
    raw_path: str | Path,
    *,
    artifacts_dir: str | Path | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    path = Path(raw_path).expanduser()
    if not path.exists():
        raise ValueError(
            _spec_error(
                source_type='missing',
                status='missing',
                path=path,
                reason=f'spec path does not exist: {path}',
                next_action='provide an existing Waygate Markdown, OpenSpec/OpenAPI, or Spec Kit path',
            )
        )

    classification = classify_requirements_spec_path(path)
    source_type = classification['sourceType']
    if source_type == 'unsupported':
        raise ValueError(
            _spec_error(
                source_type=source_type,
                status='unsupported',
                path=path,
                reason=classification['label'],
                next_action='use Waygate Markdown, OpenSpec/OpenAPI, or Spec Kit input, or convert this source first',
            )
        )
    if source_type == ASYNCAPI_SOURCE_TYPE:
        raise ValueError(
            _spec_error(
                source_type=source_type,
                status='deferred',
                path=path,
                reason='AsyncAPI-like input is recognized but not enabled in V0.6.1',
                next_action='convert it to OpenAPI/OpenSpec, Spec Kit, or Waygate Markdown for this release',
            )
        )

    resolved = path.resolve()
    content = _read_bytes_for_hash(resolved, source_type=source_type)
    metadata: dict[str, Any] = {
        'path': str(resolved),
        'hash': 'sha256:' + hashlib.sha256(content).hexdigest(),
        'sourceType': source_type,
        'importedAt': datetime.now(timezone.utc).isoformat(),
    }
    if source_type == SUPPORTED_SOURCE_TYPE:
        return metadata

    if source_type not in SUPPORTED_EXTERNAL_SOURCE_TYPES:
        raise ValueError(
            _spec_error(
                source_type=source_type,
                status='unsupported',
                path=path,
                reason=classification['label'],
                next_action='use Waygate Markdown, OpenSpec/OpenAPI, or Spec Kit input',
            )
        )
    if not _external_spec_intake_enabled(target):
        raise ValueError(
            f"{classification['label']} is unsupported in V0.5.6 and deferred to V0.6.1: {path} "
            f"(sourceType={source_type}; next action: run a V0.6.1 or later target, or convert to Waygate Markdown)"
        )

    if artifacts_dir is None:
        return metadata

    conversion = _convert_external_spec(
        resolved,
        source_type=source_type,
        source_hash=metadata['hash'],
        imported_at=metadata['importedAt'],
        artifacts_dir=Path(artifacts_dir),
    )
    metadata.update({
        'sourceMetadata': conversion['source_metadata'],
        'conversionArtifacts': conversion['artifact_paths'],
    })
    return metadata


def classify_requirements_spec_path(path: Path) -> dict[str, str]:
    if path.is_dir():
        if _looks_like_openspec_dir(path):
            return {'sourceType': OPENSPEC_SOURCE_TYPE, 'label': 'OpenSpec-like spec path'}
        if _looks_like_spec_kit_dir(path):
            return {'sourceType': SPEC_KIT_SOURCE_TYPE, 'label': 'Spec Kit-like spec path'}
        if _looks_like_asyncapi_dir(path):
            return {'sourceType': ASYNCAPI_SOURCE_TYPE, 'label': 'AsyncAPI-like spec path'}
        raise ValueError(f'spec path must be a readable Markdown file: {path}')

    if not path.is_file():
        raise ValueError(f'spec path must be a readable Markdown file: {path}')

    name = path.name.lower()
    if _looks_like_spec_kit_file(path):
        return {'sourceType': SPEC_KIT_SOURCE_TYPE, 'label': 'Spec Kit-like spec path'}
    if _looks_like_openspec_file(path):
        return {'sourceType': OPENSPEC_SOURCE_TYPE, 'label': 'OpenSpec-like spec path'}
    if _looks_like_asyncapi_file(path):
        return {'sourceType': ASYNCAPI_SOURCE_TYPE, 'label': 'AsyncAPI-like spec path'}
    if path.suffix.lower() not in {'.md', '.markdown'}:
        return {'sourceType': 'unsupported', 'label': f'unsupported spec path format: {path.suffix or path.name}'}
    if 'openspec' in name:
        return {'sourceType': OPENSPEC_SOURCE_TYPE, 'label': 'OpenSpec-like spec path'}
    return {'sourceType': SUPPORTED_SOURCE_TYPE, 'label': 'Waygate Markdown spec path'}


def same_requirements_spec(existing: dict[str, Any] | None, incoming: dict[str, Any] | None) -> bool:
    if not existing or not incoming:
        return False
    return (
        str(existing.get('path') or '') == str(incoming.get('path') or '')
        and str(existing.get('hash') or '') == str(incoming.get('hash') or '')
        and str(existing.get('sourceType') or '') == str(incoming.get('sourceType') or '')
    )


def _convert_external_spec(
    path: Path,
    *,
    source_type: str,
    source_hash: str,
    imported_at: str,
    artifacts_dir: Path,
) -> dict[str, Any]:
    if source_type == OPENSPEC_SOURCE_TYPE:
        payloads = _convert_openspec(path, source_hash=source_hash, imported_at=imported_at)
    elif source_type == SPEC_KIT_SOURCE_TYPE:
        payloads = _convert_spec_kit(path, source_hash=source_hash, imported_at=imported_at)
    else:
        raise ValueError(
            _spec_error(
                source_type=source_type,
                status='unsupported',
                path=path,
                reason='no converter registered for source type',
                next_action='use OpenSpec/OpenAPI, Spec Kit, or Waygate Markdown input',
            )
        )

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifact_specs = {
        'importSummary': ('import-summary.json', payloads['import_summary']),
        'normalizedRequirements': ('normalized-requirements.json', payloads['normalized_requirements']),
        'sourceMap': ('source-map.json', payloads['source_map']),
        'validationReport': ('validation-report.json', payloads['validation_report']),
    }
    artifact_paths: dict[str, str] = {}
    for key, (filename, payload) in artifact_specs.items():
        artifact_path = artifacts_dir / filename
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        artifact_paths[key] = str(artifact_path)
    return {
        'artifact_paths': artifact_paths,
        'source_metadata': payloads['source_metadata'],
    }


def _convert_openspec(path: Path, *, source_hash: str, imported_at: str) -> dict[str, Any]:
    source_file = _openspec_entrypoint(path)
    document = _load_openspec_document(source_file)
    if not isinstance(document, dict):
        _raise_invalid(OPENSPEC_SOURCE_TYPE, path, 'OpenSpec/OpenAPI document must be an object')
    if not document.get('openapi'):
        _raise_invalid(OPENSPEC_SOURCE_TYPE, path, 'OpenSpec/OpenAPI document must include openapi version')
    info = document.get('info') if isinstance(document.get('info'), dict) else {}
    title = str(info.get('title') or '').strip()
    version = str(info.get('version') or '').strip()
    if not title:
        _raise_invalid(OPENSPEC_SOURCE_TYPE, path, 'OpenSpec/OpenAPI info.title is required')
    paths = document.get('paths') if isinstance(document.get('paths'), dict) else {}
    if not paths:
        _raise_invalid(OPENSPEC_SOURCE_TYPE, path, 'OpenSpec/OpenAPI paths must include at least one operation')

    redactions: list[dict[str, str]] = []
    sanitized_document = _redact_value(document, redactions, location='document')
    requirements: list[dict[str, Any]] = []
    acceptance_candidates: list[dict[str, Any]] = []
    mappings: list[dict[str, str]] = []
    for route, route_item in paths.items():
        if not isinstance(route_item, dict):
            continue
        for method, operation in route_item.items():
            method_name = str(method).lower()
            if method_name not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            summary = _first_text(operation.get('summary'), operation.get('description'), f'{method_name.upper()} {route}')
            requirement_id = f'REQ-{len(requirements) + 1:03d}'
            requirements.append({
                'id': requirement_id,
                'text': _redact_text(f'{method_name.upper()} {route}: {summary}', redactions, f'requirements.{requirement_id}'),
                'sourcePointer': f'/paths/{route}/{method_name}',
            })
            responses = operation.get('responses') if isinstance(operation.get('responses'), dict) else {}
            for status_code, response in responses.items():
                if not isinstance(response, dict):
                    continue
                description = str(response.get('description') or '').strip()
                if not description:
                    continue
                acceptance_id = f'AC-CANDIDATE-{len(acceptance_candidates) + 1:03d}'
                acceptance_candidates.append({
                    'id': acceptance_id,
                    'text': _redact_text(
                        f'{method_name.upper()} {route} returns {status_code}: {description}',
                        redactions,
                        f'acceptanceCandidates.{acceptance_id}',
                    ),
                    'sourcePointer': f'/paths/{route}/{method_name}/responses/{status_code}',
                })
            mappings.append({
                'target': f'normalizedRequirements.requirements.{requirement_id}',
                'sourcePath': str(source_file),
                'sourcePointer': f'/paths/{route}/{method_name}',
            })

    if not requirements:
        _raise_invalid(OPENSPEC_SOURCE_TYPE, path, 'OpenSpec/OpenAPI paths must include at least one HTTP operation')

    source_metadata = {
        'title': title,
        'version': version,
        'openapiVersion': str(document.get('openapi')),
        'entrypoint': str(source_file),
    }
    server_urls = []
    for server in document.get('servers') or []:
        if isinstance(server, dict) and server.get('url'):
            server_urls.append(_redact_text(str(server.get('url')), redactions, 'servers.url'))
    if server_urls:
        source_metadata['serverUrls'] = server_urls

    normalized = {
        'sourceType': OPENSPEC_SOURCE_TYPE,
        'title': title,
        'version': version,
        'requirements': requirements,
        'acceptanceCandidates': acceptance_candidates,
        'nonGoals': [],
        'assumptions': [],
    }
    return _conversion_payloads(
        source_type=OPENSPEC_SOURCE_TYPE,
        source_path=path,
        source_file=source_file,
        source_hash=source_hash,
        imported_at=imported_at,
        source_metadata=source_metadata,
        normalized_requirements=normalized,
        mappings=mappings,
        redactions=redactions,
        sanitized_source=sanitized_document,
    )


def _convert_spec_kit(path: Path, *, source_hash: str, imported_at: str) -> dict[str, Any]:
    source_file = _spec_kit_entrypoint(path)
    try:
        content = source_file.read_text(encoding='utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError(
            _spec_error(
                source_type=SPEC_KIT_SOURCE_TYPE,
                status='unreadable',
                path=path,
                reason=f'Spec Kit input is not valid UTF-8: {exc}',
                next_action='save the Spec Kit markdown as UTF-8 text and retry',
            )
        ) from exc
    except OSError as exc:
        raise ValueError(
            _spec_error(
                source_type=SPEC_KIT_SOURCE_TYPE,
                status='unreadable',
                path=path,
                reason=str(exc),
                next_action='make the Spec Kit markdown readable and retry',
            )
        ) from exc

    redactions: list[dict[str, str]] = []
    title = _markdown_title(content) or 'Spec Kit import'
    sections = _markdown_sections(content)
    requirements = _section_bullets(sections, 'requirements', 'requirement')
    acceptance = _section_bullets(sections, 'acceptance criteria', 'acceptance')
    non_goals = _section_bullets(sections, 'non-goals', 'non goals', 'out of scope')
    assumptions = _section_bullets(sections, 'assumptions')
    if not requirements and not acceptance:
        _raise_invalid(SPEC_KIT_SOURCE_TYPE, path, 'Spec Kit input must include Requirements or Acceptance Criteria bullets')

    normalized_requirements: list[dict[str, Any]] = []
    mappings: list[dict[str, str]] = []
    for index, item in enumerate(requirements, start=1):
        req_id = f'REQ-{index:03d}'
        normalized_requirements.append({
            'id': req_id,
            'text': _redact_text(_strip_markdown_item_id(item), redactions, f'requirements.{req_id}'),
            'sourcePointer': f'#requirements/{index}',
        })
        mappings.append({
            'target': f'normalizedRequirements.requirements.{req_id}',
            'sourcePath': str(source_file),
            'sourcePointer': f'#requirements/{index}',
        })

    acceptance_candidates: list[dict[str, Any]] = []
    for index, item in enumerate(acceptance, start=1):
        candidate_id = f'AC-CANDIDATE-{index:03d}'
        acceptance_candidates.append({
            'id': candidate_id,
            'text': _redact_text(_strip_markdown_item_id(item), redactions, f'acceptanceCandidates.{candidate_id}'),
            'sourcePointer': f'#acceptance/{index}',
        })
        mappings.append({
            'target': f'normalizedRequirements.acceptanceCandidates.{candidate_id}',
            'sourcePath': str(source_file),
            'sourcePointer': f'#acceptance/{index}',
        })

    normalized = {
        'sourceType': SPEC_KIT_SOURCE_TYPE,
        'title': title,
        'requirements': normalized_requirements,
        'acceptanceCandidates': acceptance_candidates,
        'nonGoals': [_redact_text(_strip_markdown_item_id(item), redactions, f'nonGoals.{index}') for index, item in enumerate(non_goals, start=1)],
        'assumptions': [_redact_text(_strip_markdown_item_id(item), redactions, f'assumptions.{index}') for index, item in enumerate(assumptions, start=1)],
    }
    source_metadata = {
        'title': title,
        'entrypoint': str(source_file),
        'requirementCount': len(normalized_requirements),
        'acceptanceCandidateCount': len(acceptance_candidates),
    }
    return _conversion_payloads(
        source_type=SPEC_KIT_SOURCE_TYPE,
        source_path=path,
        source_file=source_file,
        source_hash=source_hash,
        imported_at=imported_at,
        source_metadata=source_metadata,
        normalized_requirements=normalized,
        mappings=mappings,
        redactions=redactions,
        sanitized_source={'markdownTitle': title},
    )


def _conversion_payloads(
    *,
    source_type: str,
    source_path: Path,
    source_file: Path,
    source_hash: str,
    imported_at: str,
    source_metadata: dict[str, Any],
    normalized_requirements: dict[str, Any],
    mappings: list[dict[str, str]],
    redactions: list[dict[str, str]],
    sanitized_source: Any,
) -> dict[str, Any]:
    validation_report = {
        'status': 'passed',
        'sourceType': source_type,
        'sourcePath': str(source_path),
        'entrypoint': str(source_file),
        'errors': [],
        'warnings': [],
        'redactions': redactions,
    }
    if redactions:
        validation_report['warnings'].append('Sensitive values were redacted from conversion artifacts.')
    import_summary = {
        'sourceType': source_type,
        'sourcePath': str(source_path),
        'entrypoint': str(source_file),
        'sourceHash': source_hash,
        'importedAt': imported_at,
        'sourceMetadata': source_metadata,
        'redactionCount': len(redactions),
    }
    source_map = {
        'sourceType': source_type,
        'sourcePath': str(source_path),
        'entrypoint': str(source_file),
        'mappings': mappings,
    }
    if isinstance(sanitized_source, dict):
        source_map['sanitizedSourceSummary'] = sanitized_source
    return {
        'import_summary': import_summary,
        'normalized_requirements': normalized_requirements,
        'source_map': source_map,
        'validation_report': validation_report,
        'source_metadata': source_metadata,
    }


def _read_bytes_for_hash(path: Path, *, source_type: str) -> bytes:
    try:
        if path.is_dir():
            return _directory_hash_bytes(path)
        return path.read_bytes()
    except OSError as exc:
        raise ValueError(
            _spec_error(
                source_type=source_type,
                status='unreadable',
                path=path,
                reason=str(exc),
                next_action='make the spec path readable and retry',
            )
        ) from exc


def _directory_hash_bytes(path: Path) -> bytes:
    parts: list[bytes] = []
    for child in sorted(item for item in path.rglob('*') if item.is_file()):
        try:
            content = child.read_bytes()
        except OSError:
            continue
        parts.append(str(child.relative_to(path)).encode('utf-8') + b'\0' + content)
    return b'\n'.join(parts)


def _load_openspec_document(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError(
            _spec_error(
                source_type=OPENSPEC_SOURCE_TYPE,
                status='unreadable',
                path=path,
                reason=f'OpenSpec/OpenAPI input is not valid UTF-8: {exc}',
                next_action='save the OpenSpec/OpenAPI file as UTF-8 text and retry',
            )
        ) from exc
    except OSError as exc:
        raise ValueError(
            _spec_error(
                source_type=OPENSPEC_SOURCE_TYPE,
                status='unreadable',
                path=path,
                reason=str(exc),
                next_action='make the OpenSpec/OpenAPI file readable and retry',
            )
        ) from exc
    if path.suffix.lower() == '.json':
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            _raise_invalid(OPENSPEC_SOURCE_TYPE, path, f'OpenSpec/OpenAPI JSON is invalid: {exc}')
        if not isinstance(payload, dict):
            _raise_invalid(OPENSPEC_SOURCE_TYPE, path, 'OpenSpec/OpenAPI JSON root must be an object')
        return payload
    try:
        import yaml  # type: ignore
    except ImportError:
        return _parse_openapi_yaml_subset(text)
    try:
        payload = yaml.safe_load(text)
    except Exception as exc:  # pragma: no cover - depends on optional PyYAML.
        _raise_invalid(OPENSPEC_SOURCE_TYPE, path, f'OpenSpec/OpenAPI YAML is invalid: {exc}')
    if not isinstance(payload, dict):
        _raise_invalid(OPENSPEC_SOURCE_TYPE, path, 'OpenSpec/OpenAPI YAML root must be an object')
    return payload


def _parse_openapi_yaml_subset(text: str) -> dict[str, Any]:
    title = _yaml_scalar_after(text, 'title')
    version = _yaml_scalar_after(text, 'version')
    openapi = _yaml_scalar_after(text, 'openapi')
    paths: dict[str, Any] = {}
    lines = text.splitlines()
    in_paths = False
    current_route: str | None = None
    current_method: str | None = None
    for raw_line in lines:
        if not raw_line.strip() or raw_line.lstrip().startswith('#'):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(' '))
        stripped = raw_line.strip()
        if indent == 0:
            in_paths = stripped == 'paths:'
            current_route = None
            current_method = None
            continue
        if not in_paths:
            continue
        if indent == 2 and stripped.endswith(':') and stripped.startswith('/'):
            current_route = stripped[:-1]
            paths.setdefault(current_route, {})
            current_method = None
            continue
        if indent == 4 and stripped.endswith(':') and stripped[:-1].lower() in HTTP_METHODS and current_route:
            current_method = stripped[:-1].lower()
            paths[current_route][current_method] = {}
            continue
        if indent >= 6 and current_route and current_method and ':' in stripped:
            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip().strip('"\'')
            if key in {'summary', 'description'}:
                paths[current_route][current_method][key] = value
            if key == 'responses':
                paths[current_route][current_method].setdefault('responses', {})
        if indent >= 8 and current_route and current_method and stripped.endswith(':'):
            status = stripped[:-1].strip('"\'')
            if re.fullmatch(r'\d{3}|default', status):
                paths[current_route][current_method].setdefault('responses', {}).setdefault(status, {})
        if indent >= 10 and current_route and current_method and stripped.startswith('description:'):
            value = stripped.partition(':')[2].strip().strip('"\'')
            responses = paths[current_route][current_method].setdefault('responses', {})
            if responses:
                last_key = next(reversed(responses))
                responses[last_key]['description'] = value
    return {
        'openapi': openapi,
        'info': {'title': title, 'version': version},
        'paths': paths,
    }


def _yaml_scalar_after(text: str, key: str) -> str:
    match = re.search(rf'(?m)^\s*{re.escape(key)}:\s*["\']?([^"\'\n]+)["\']?\s*$', text)
    return match.group(1).strip() if match else ''


def _openspec_entrypoint(path: Path) -> Path:
    if path.is_file():
        return path
    for name in ('openapi.yaml', 'openapi.yml', 'openapi.json', 'openspec.yaml', 'openspec.yml'):
        candidate = path / name
        if candidate.exists() and candidate.is_file():
            return candidate
    _raise_invalid(OPENSPEC_SOURCE_TYPE, path, 'OpenSpec-like directory must include openapi.yaml, openapi.yml, openapi.json, openspec.yaml, or openspec.yml')


def _spec_kit_entrypoint(path: Path) -> Path:
    if path.is_file():
        return path
    for name in ('spec.md', 'requirements.md', 'feature.md'):
        candidate = path / name
        if candidate.exists() and candidate.is_file():
            return candidate
    markdown_files = sorted(path.glob('*.md'))
    if markdown_files:
        return markdown_files[0]
    _raise_invalid(SPEC_KIT_SOURCE_TYPE, path, 'Spec Kit-like directory must include a markdown spec file')


def _markdown_title(content: str) -> str:
    match = re.search(r'(?m)^#\s+(.+?)\s*$', content)
    return match.group(1).strip() if match else ''


def _markdown_sections(content: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = ''
    for line in content.splitlines():
        heading = re.match(r'^(#{2,6})\s+(.+?)\s*$', line)
        if heading:
            current = _normalize_section_name(heading.group(2))
            sections.setdefault(current, [])
            continue
        if current:
            sections.setdefault(current, []).append(line)
    return sections


def _section_bullets(sections: dict[str, list[str]], *names: str) -> list[str]:
    result: list[str] = []
    normalized_names = {_normalize_section_name(name) for name in names}
    for section_name, lines in sections.items():
        if section_name not in normalized_names:
            continue
        for line in lines:
            match = re.match(r'\s*[-*]\s+(.+?)\s*$', line)
            if match:
                result.append(match.group(1).strip())
    return result


def _normalize_section_name(value: str) -> str:
    return re.sub(r'\s+', ' ', value.strip().lower())


def _strip_markdown_item_id(value: str) -> str:
    return re.sub(r'^(?:REQ|AC|NFR|FR)[-_ ]?\d+[:.)]\s*', '', value.strip(), flags=re.I).strip()


def _redact_value(value: Any, redactions: list[dict[str, str]], *, location: str) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            child_location = f'{location}.{key_text}'
            if SENSITIVE_KEY_PATTERN.search(key_text):
                result[key_text] = '[REDACTED]'
                redactions.append({'location': child_location, 'reason': 'sensitive key'})
                continue
            result[key_text] = _redact_value(item, redactions, location=child_location)
        return result
    if isinstance(value, list):
        return [_redact_value(item, redactions, location=f'{location}[{index}]') for index, item in enumerate(value)]
    if isinstance(value, str):
        return _redact_text(value, redactions, location)
    return value


def _redact_text(text: str, redactions: list[dict[str, str]], location: str) -> str:
    redacted = DATABASE_URL_PATTERN.sub('[REDACTED_DATABASE_URL]', text)
    if redacted != text:
        redactions.append({'location': location, 'reason': 'database URL'})
    try:
        split = urlsplit(redacted)
    except ValueError:
        return redacted
    if not split.query:
        return redacted
    changed = False
    pairs: list[tuple[str, str]] = []
    for key, value in parse_qsl(split.query, keep_blank_values=True):
        if SENSITIVE_KEY_PATTERN.search(key):
            pairs.append((key, 'REDACTED'))
            changed = True
            redactions.append({'location': location, 'reason': f'sensitive query key {key}'})
        else:
            pairs.append((key, value))
    if not changed:
        return redacted
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(pairs), split.fragment))


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or '').strip()
        if text:
            return text
    return ''


def _external_spec_intake_enabled(target: str | None) -> bool:
    if not target:
        return True
    normalized = str(target).strip().lower().lstrip('v')
    match = re.match(r'(\d+)\.(\d+)\.(\d+)', normalized)
    if not match:
        return True
    version = tuple(int(part) for part in match.groups())
    return version >= (0, 6, 1)


def _raise_invalid(source_type: str, path: Path, reason: str) -> None:
    raise ValueError(
        _spec_error(
            source_type=source_type,
            status='invalid',
            path=path,
            reason=reason,
            next_action='fix the source according to the supported import contract and retry',
        )
    )


def _spec_error(*, source_type: str, status: str, path: Path, reason: str, next_action: str) -> str:
    return (
        f'spec intake error: sourceType={source_type} status={status} path={path} '
        f'reason={reason}; next action: {next_action}'
    )


def _looks_like_openspec_dir(path: Path) -> bool:
    names = {child.name.lower() for child in path.iterdir()}
    return bool({'openapi.yaml', 'openapi.yml', 'openapi.json', 'openspec.yaml', 'openspec.yml'} & names)


def _looks_like_spec_kit_dir(path: Path) -> bool:
    names = {child.name.lower() for child in path.iterdir()}
    if '.specify' in names or 'specify' in path.name.lower() or 'spec-kit' in path.name.lower():
        return True
    spec_file = path / 'spec.md'
    return spec_file.exists() and _looks_like_spec_kit_file(spec_file)


def _looks_like_asyncapi_dir(path: Path) -> bool:
    names = {child.name.lower() for child in path.iterdir()}
    return bool({'asyncapi.yaml', 'asyncapi.yml', 'asyncapi.json'} & names)


def _looks_like_spec_kit_file(path: Path) -> bool:
    name = path.name.lower()
    if 'specify' in name or 'spec-kit' in name:
        return True
    excerpt = _read_text_excerpt(path).lower()
    return 'spec kit' in excerpt or 'feature specification' in excerpt


def _looks_like_openspec_file(path: Path) -> bool:
    name = path.name.lower()
    if name in {'openapi.yaml', 'openapi.yml', 'openapi.json', 'openspec.yaml', 'openspec.yml'}:
        return True
    excerpt = _read_text_excerpt(path).lower()
    return 'openapi:' in excerpt or '"openapi"' in excerpt


def _looks_like_asyncapi_file(path: Path) -> bool:
    name = path.name.lower()
    if name in {'asyncapi.yaml', 'asyncapi.yml', 'asyncapi.json'}:
        return True
    excerpt = _read_text_excerpt(path).lower()
    return 'asyncapi:' in excerpt or '"asyncapi"' in excerpt


def _read_text_excerpt(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')[:2048]
    except OSError:
        return ''
    except UnicodeDecodeError:
        return ''
