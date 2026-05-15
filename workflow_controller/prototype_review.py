from __future__ import annotations

import json
import mimetypes
import posixpath
import re
import shutil
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit


PROTOTYPE_REVIEW_VERSION = 'v0.6.0a'
SOURCE_MANIFEST_NAME = 'prototype-manifest.json'
REVIEW_MANIFEST_NAME = 'prototype-review-manifest.json'
REVIEW_BUNDLE_NAME = 'plannotator-review.md'
PROTOTYPES_DIR_NAME = 'prototypes'
ALLOWED_PROTOTYPE_TYPES = {'html', 'image', 'url'}
SENSITIVE_QUERY_KEYS = {
    'access_token',
    'api_key',
    'apikey',
    'auth',
    'credential',
    'credentials',
    'key',
    'password',
    'secret',
    'session',
    'signature',
    'sig',
    'token',
}


@dataclass(frozen=True)
class PrototypeReviewBundle:
    review_path: Path
    manifest_path: Path
    source_manifest_path: Path
    prototypes_dir: Path


@dataclass
class PrototypePreviewServer:
    httpd: ThreadingHTTPServer
    thread: threading.Thread
    base_url: str

    @property
    def preview_url(self) -> str:
        return f'{self.base_url}/{REVIEW_BUNDLE_NAME}'

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)


def prepare_prototype_review_bundle(
    *,
    artifacts_dir: Path,
    requirements_path: Path,
    state: dict[str, Any] | None = None,
) -> PrototypeReviewBundle | None:
    del state
    draft_dir = artifacts_dir / 'requirements-draft'
    source_manifest_path = draft_dir / SOURCE_MANIFEST_NAME
    if not source_manifest_path.exists():
        return None

    prototypes_dir = draft_dir / PROTOTYPES_DIR_NAME
    normalized = _build_normalized_manifest(
        source_manifest_path,
        requirements_path=requirements_path,
        artifacts_dir=artifacts_dir,
        copy_assets=True,
    )
    prototypes_dir.mkdir(parents=True, exist_ok=True)
    review_manifest_path = draft_dir / REVIEW_MANIFEST_NAME
    review_path = draft_dir / REVIEW_BUNDLE_NAME
    normalized['review_bundle_path'] = str(review_path)
    normalized['approval_gate_path'] = str(requirements_path)
    normalized['prototypes_dir'] = str(prototypes_dir)
    review_manifest_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    review_path.write_text(
        render_prototype_review_markdown(normalized, requirements_path=requirements_path),
        encoding='utf-8',
    )
    return PrototypeReviewBundle(
        review_path=review_path,
        manifest_path=review_manifest_path,
        source_manifest_path=source_manifest_path,
        prototypes_dir=prototypes_dir,
    )


def validate_prototype_review_manifest(
    manifest_path: Path,
    *,
    requirements_path: Path,
    artifacts_dir: Path,
    require_clickable: bool = False,
) -> dict[str, Any]:
    normalized = _build_normalized_manifest(
        manifest_path,
        requirements_path=requirements_path,
        artifacts_dir=artifacts_dir,
        require_clickable=require_clickable,
        copy_assets=False,
    )
    return normalized


def prototype_review_paths(artifacts_dir: Path) -> tuple[Path, Path, Path]:
    draft_dir = artifacts_dir / 'requirements-draft'
    return (
        draft_dir / REVIEW_BUNDLE_NAME,
        draft_dir / REVIEW_MANIFEST_NAME,
        draft_dir / PROTOTYPES_DIR_NAME,
    )


def source_prototype_manifest_path_for_requirements(requirements_path: Path) -> tuple[Path, Path]:
    state_root = requirements_path.parent.parent if requirements_path.parent.name == 'approvals' else requirements_path.parent
    artifacts_dir = state_root / 'artifacts'
    return artifacts_dir / 'requirements-draft' / SOURCE_MANIFEST_NAME, artifacts_dir


def render_prototype_review_markdown(
    normalized_manifest: dict[str, Any],
    *,
    requirements_path: Path,
) -> str:
    prototypes = normalized_manifest.get('prototypes') if isinstance(normalized_manifest.get('prototypes'), list) else []
    lines = [
        '# Prototype Review Bundle for Plannotator',
        '',
        f'- Approval gate: `{requirements_path}`',
        f"- Source manifest: `{normalized_manifest.get('source_manifest') or '-'}`",
        f"- Normalized manifest: `{normalized_manifest.get('review_manifest_path') or REVIEW_MANIFEST_NAME}`",
        '',
        '## Prototype Links',
        '',
    ]
    if prototypes:
        for prototype in prototypes:
            if not isinstance(prototype, dict):
                continue
            title = str(prototype.get('title') or prototype.get('id') or 'prototype')
            href = str(prototype.get('review_href') or '')
            lines.append(f"- [{_escape_markdown_text(title)}]({href})")
    else:
        lines.append('- No prototypes declared.')

    lines.extend([
        '',
        '## AC/Journey Mapping',
        '',
        '| Prototype | Title | Type | AC | Journeys | Page States | Click Path |',
        '| --- | --- | --- | --- | --- | --- | --- |',
    ])
    for prototype in prototypes:
        if not isinstance(prototype, dict):
            continue
        lines.append(
            '| {id} | {title} | {type} | {acs} | {journeys} | {states} | {click_path} |'.format(
                id=_table_cell(prototype.get('id')),
                title=_table_cell(prototype.get('title')),
                type=_table_cell(prototype.get('type')),
                acs=_table_cell('; '.join(prototype.get('linked_acceptance_criteria') or [])),
                journeys=_table_cell('; '.join(prototype.get('linked_journeys') or [])),
                states=_table_cell('; '.join(prototype.get('page_states') or [])),
                click_path=_table_cell(' -> '.join(prototype.get('click_path') or [])),
            )
        )

    lines.extend([
        '',
        '## Review Guidance',
        '',
    ])
    for prototype in prototypes:
        if not isinstance(prototype, dict):
            continue
        guidance = str(prototype.get('review_guidance') or prototype.get('preview_hint') or '').strip()
        if guidance:
            lines.append(f"- `{prototype.get('id')}`: {guidance}")
    if lines[-1] == '':
        lines.append('- Review each linked prototype against its mapped AC and Journey rows.')
    lines.extend([
        '',
        '## Approval Gate',
        '',
        f'Approve or request changes on `{requirements_path}` after reviewing this bundle.',
    ])
    return '\n'.join(lines).rstrip() + '\n'


def start_prototype_review_preview_server(
    *,
    review_path: Path,
    manifest_path: Path,
    prototypes_dir: Path,
    approval_gate_path: Path,
) -> PrototypePreviewServer:
    allowed = {
        f'/{REVIEW_BUNDLE_NAME}': review_path.resolve(),
        f'/{REVIEW_MANIFEST_NAME}': manifest_path.resolve(),
        '/requirements-and-acceptance.md': approval_gate_path.resolve(),
    }
    prototypes_root = prototypes_dir.resolve()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            target = _preview_target_for_request(
                self.path,
                allowed=allowed,
                prototypes_root=prototypes_root,
            )
            if target is None or not target.exists() or not target.is_file():
                self.send_error(404)
                return
            content = target.read_bytes()
            content_type = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
            if content_type.startswith('text/') or content_type in {'application/json'}:
                content_type = f'{content_type}; charset=utf-8'
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    return PrototypePreviewServer(httpd=httpd, thread=thread, base_url=f'http://{host}:{port}')


def _build_normalized_manifest(
    manifest_path: Path,
    *,
    requirements_path: Path,
    artifacts_dir: Path,
    require_clickable: bool = False,
    copy_assets: bool = False,
) -> dict[str, Any]:
    raw = _load_manifest(manifest_path)
    raw_prototypes = raw.get('prototypes')
    if not isinstance(raw_prototypes, list) or not raw_prototypes:
        raise ValueError('prototype manifest must contain a non-empty prototypes list')

    requirements_ac_ids = _requirements_ac_ids(requirements_path)
    draft_dir = artifacts_dir / 'requirements-draft'
    prototypes_dir = draft_dir / PROTOTYPES_DIR_NAME
    issues: list[str] = []
    normalized_prototypes: list[dict[str, Any]] = []

    for index, raw_prototype in enumerate(raw_prototypes):
        if not isinstance(raw_prototype, dict):
            issues.append(f'prototype[{index}] must be an object')
            continue
        normalized = _normalize_prototype(
            raw_prototype,
            index=index,
            manifest_path=manifest_path,
            prototypes_dir=prototypes_dir,
            requirements_ac_ids=requirements_ac_ids,
            require_clickable=require_clickable,
            copy_assets=copy_assets,
            issues=issues,
        )
        if normalized is not None:
            normalized_prototypes.append(normalized)

    if require_clickable and not any(item.get('type') in {'html', 'url'} for item in normalized_prototypes):
        issues.append('clickable prototype required for Web system: add an html or url prototype')

    if issues:
        raise ValueError('invalid prototype manifest: ' + '; '.join(issues))

    return {
        'version': PROTOTYPE_REVIEW_VERSION,
        'source_manifest': str(manifest_path),
        'review_manifest_path': str(draft_dir / REVIEW_MANIFEST_NAME),
        'review_bundle_path': str(draft_dir / REVIEW_BUNDLE_NAME),
        'prototypes_dir': str(prototypes_dir),
        'prototypes': normalized_prototypes,
    }


def _normalize_prototype(
    raw: dict[str, Any],
    *,
    index: int,
    manifest_path: Path,
    prototypes_dir: Path,
    requirements_ac_ids: set[str],
    require_clickable: bool,
    copy_assets: bool,
    issues: list[str],
) -> dict[str, Any] | None:
    raw_id = str(raw.get('id') or '').strip()
    prototype_id = _safe_id(raw_id)
    if not raw_id:
        issues.append(f'prototype[{index}] missing id')
    prototype_type = str(raw.get('type') or '').strip().lower()
    if prototype_type not in ALLOWED_PROTOTYPE_TYPES:
        issues.append(f'prototype {raw_id or index} has unsupported type: {prototype_type or "-"}')
    title = str(raw.get('title') or '').strip()
    if not title:
        issues.append(f'prototype {raw_id or index} missing title')

    acs = _string_list(
        raw.get('linked_acceptance_criteria')
        or raw.get('acceptance_criteria')
        or raw.get('linked_acs')
        or raw.get('acs')
    )
    unknown_acs = sorted({ac.upper() for ac in acs if ac.upper() not in requirements_ac_ids})
    if not acs:
        issues.append(f'prototype {raw_id or index} missing AC mapping')
    if unknown_acs:
        issues.append(f'prototype {raw_id or index} unknown acceptance criteria: {", ".join(unknown_acs)}')

    page_states = _string_list(raw.get('page_states') or raw.get('pageStates'))
    click_path = _string_list(raw.get('click_path') or raw.get('clickPath'))
    if not page_states:
        issues.append(f'prototype {raw_id or index} missing page_states')
    if not click_path:
        issues.append(f'prototype {raw_id or index} missing click_path')

    source_path = ''
    url = str(raw.get('url') or '').strip()
    review_href = str(raw.get('review_href') or '').strip()
    if prototype_type == 'url':
        if not url:
            issues.append(f'prototype {raw_id or index} missing url')
        else:
            _validate_url(url, raw_id or str(index), issues)
            review_href = url
    elif prototype_type in {'html', 'image'}:
        raw_path = str(raw.get('path') or '').strip()
        if not raw_path:
            issues.append(f'prototype {raw_id or index} missing path')
        else:
            resolved_source = _resolve_manifest_path(raw_path, manifest_path)
            source_path = str(resolved_source)
            if not resolved_source.exists() or not resolved_source.is_file():
                issues.append(f'prototype {raw_id or index} missing file: {resolved_source}')
            elif copy_assets and prototype_id:
                target_dir = prototypes_dir / prototype_id
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / resolved_source.name
                if resolved_source.resolve() != target.resolve():
                    shutil.copy2(resolved_source, target)
                review_href = _relative_posix(target, prototypes_dir.parent)
            elif not review_href:
                review_href = _relative_posix(resolved_source, manifest_path.parent)

    if require_clickable and prototype_type == 'image':
        issues.append(f'prototype {raw_id or index} is image-only; Web system requires html or url clickable prototype')

    if not prototype_id or prototype_type not in ALLOWED_PROTOTYPE_TYPES or not title:
        return None
    return {
        'id': prototype_id,
        'type': prototype_type,
        'title': title,
        'source_path': source_path,
        'url': url,
        'review_href': review_href,
        'linked_acceptance_criteria': [ac.upper() for ac in acs],
        'linked_journeys': _string_list(raw.get('linked_journeys') or raw.get('journeys')),
        'page_states': page_states,
        'click_path': click_path,
        'thumbnail': str(raw.get('thumbnail') or '').strip(),
        'preview_hint': str(raw.get('preview_hint') or raw.get('previewHint') or '').strip(),
        'review_guidance': str(raw.get('review_guidance') or raw.get('reviewGuidance') or '').strip(),
    }


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise ValueError(f'prototype manifest not found: {manifest_path}') from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f'prototype manifest JSON is invalid: {exc.msg}') from exc
    if not isinstance(payload, dict):
        raise ValueError('prototype manifest must be a JSON object')
    return payload


def _requirements_ac_ids(requirements_path: Path) -> set[str]:
    if not requirements_path.exists():
        return set()
    return {
        match.group(0).upper()
        for match in re.finditer(
            r'\bAC-\d+(?:[-.]\d+)*\b',
            _gate_body(requirements_path.read_text(encoding='utf-8')),
            re.IGNORECASE,
        )
    }


def _gate_body(content: str) -> str:
    heading = '## Human Confirmation'
    if heading not in content:
        return content.rstrip() + '\n'
    return content.split(heading, 1)[0].rstrip() + '\n'


def _resolve_manifest_path(value: str, manifest_path: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    return (manifest_path.parent / candidate).resolve()


def _relative_posix(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _validate_url(url: str, prototype_id: str, issues: list[str]) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        issues.append(f'prototype {prototype_id} url must be http(s)')
        return
    for key, _value in parse_qsl(parsed.query, keep_blank_values=True):
        normalized_key = key.strip().lower()
        if normalized_key in SENSITIVE_QUERY_KEYS:
            issues.append(f'prototype {prototype_id} sensitive URL query parameter: {normalized_key}')


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = [value]
    items: list[str] = []
    for item in raw_items:
        if isinstance(item, dict):
            text = str(item.get('name') or item.get('title') or item.get('id') or item.get('description') or '').strip()
        else:
            text = str(item or '').strip()
        if text:
            items.append(text)
    return items


def _safe_id(value: str) -> str:
    lowered = str(value or '').strip().lower()
    safe = re.sub(r'[^a-z0-9._-]+', '-', lowered).strip('-._')
    return safe


def _escape_markdown_text(value: str) -> str:
    return value.replace('[', '\\[').replace(']', '\\]')


def _table_cell(value: Any) -> str:
    return str(value or '-').replace('|', '\\|').replace('\n', ' ').strip() or '-'


def _preview_target_for_request(
    request_path: str,
    *,
    allowed: dict[str, Path],
    prototypes_root: Path,
) -> Path | None:
    path = unquote(urlsplit(request_path).path)
    normalized = posixpath.normpath(path)
    if normalized in allowed:
        return allowed[normalized]
    if not normalized.startswith(f'/{PROTOTYPES_DIR_NAME}/'):
        return None
    relative = normalized[len(f'/{PROTOTYPES_DIR_NAME}/'):]
    parts = PurePosixPath(relative).parts
    if not parts or any(part in {'', '.', '..'} for part in parts):
        return None
    candidate = prototypes_root.joinpath(*parts).resolve()
    try:
        candidate.relative_to(prototypes_root)
    except ValueError:
        return None
    return candidate
