from __future__ import annotations

import json
import html
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


PROTOTYPE_REVIEW_VERSION = 'v0.6.0b'
SOURCE_MANIFEST_NAME = 'prototype-manifest.json'
REVIEW_MANIFEST_NAME = 'prototype-review-manifest.json'
REVIEW_BUNDLE_NAME = 'plannotator-review.md'
REVIEW_BUNDLE_HTML_NAME = 'plannotator-review.html'
PROTOTYPES_DIR_NAME = 'prototypes'
ALLOWED_PROTOTYPE_TYPES = {'html', 'image', 'markdown', 'md', 'url'}
ALLOWED_SURFACE_KINDS = {'route', 'page', 'component', 'dialog', 'drawer', 'panel', 'form', 'other'}
BROWSER_SURFACE_KINDS = {'route', 'page', 'component', 'dialog', 'drawer', 'panel', 'form'}
MULTI_SURFACE_SIGNAL_KEYWORDS = (
    '弹窗',
    '抽屉',
    '选择器',
    '管理',
    '面板',
    'drawer',
    'dialog',
    'modal',
    'selector',
    'panel',
    'management',
)
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
    html_review_path: Path | None = None


@dataclass
class PrototypePreviewServer:
    httpd: ThreadingHTTPServer
    thread: threading.Thread
    base_url: str
    review_name: str = REVIEW_BUNDLE_NAME

    @property
    def preview_url(self) -> str:
        return f'{self.base_url}/{self.review_name}'

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
    html_review_path = draft_dir / REVIEW_BUNDLE_HTML_NAME
    normalized['review_bundle_path'] = str(review_path)
    normalized['review_html_path'] = str(html_review_path)
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
    html_review_path.write_text(
        render_prototype_review_html(normalized, requirements_path=requirements_path),
        encoding='utf-8',
    )
    return PrototypeReviewBundle(
        review_path=review_path,
        html_review_path=html_review_path,
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
    require_implementation_targets: bool = False,
) -> dict[str, Any]:
    normalized = _build_normalized_manifest(
        manifest_path,
        requirements_path=requirements_path,
        artifacts_dir=artifacts_dir,
        require_clickable=require_clickable,
        require_implementation_targets=require_implementation_targets,
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


def prototype_review_html_path(artifacts_dir: Path) -> Path:
    return artifacts_dir / 'requirements-draft' / REVIEW_BUNDLE_HTML_NAME


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
        '| Prototype | Title | Type | AC | Journeys | Production Targets | Page States | Click Path |',
        '| --- | --- | --- | --- | --- | --- | --- | --- |',
    ])
    for prototype in prototypes:
        if not isinstance(prototype, dict):
            continue
        lines.append(
            '| {id} | {title} | {type} | {acs} | {journeys} | {targets} | {states} | {click_path} |'.format(
                id=_table_cell(prototype.get('id')),
                title=_table_cell(prototype.get('title')),
                type=_table_cell(prototype.get('type')),
                acs=_table_cell('; '.join(prototype.get('linked_acceptance_criteria') or [])),
                journeys=_table_cell('; '.join(prototype.get('linked_journeys') or [])),
                targets=_table_cell('; '.join(_implementation_target_label(target) for target in prototype.get('implementation_targets') or [])),
                states=_table_cell('; '.join(prototype.get('page_states') or [])),
                click_path=_table_cell(' -> '.join(prototype.get('click_path') or [])),
            )
        )

    lines.extend(_prototype_surface_coverage_markdown_lines(prototypes))

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


def _prototype_surface_coverage_markdown_lines(prototypes: list[Any]) -> list[str]:
    rows: list[str] = []
    for prototype in prototypes:
        if not isinstance(prototype, dict):
            continue
        prototype_id = str(prototype.get('id') or '').strip()
        for surface in prototype.get('surface_contracts') or []:
            if not isinstance(surface, dict):
                continue
            rows.append(
                '| {prototype} | {surface} | {kind} | {entrypoint} | {acs} | {targets} | {states} | {click_path} | {required} |'.format(
                    prototype=_table_cell(prototype_id),
                    surface=_table_cell(surface.get('id')),
                    kind=_table_cell(surface.get('kind')),
                    entrypoint=_table_cell('; '.join(surface.get('entrypoints') or [])),
                    acs=_table_cell('; '.join(surface.get('linked_acceptance_criteria') or [])),
                    targets=_table_cell('; '.join(_implementation_target_label(target) for target in surface.get('implementation_targets') or [])),
                    states=_table_cell('; '.join(surface.get('page_states') or [])),
                    click_path=_table_cell(' -> '.join(surface.get('click_path') or [])),
                    required='yes' if surface.get('required') is True else 'no',
                )
            )
    lines = [
        '',
        '## Prototype Surface Coverage Matrix',
        '',
        '| Prototype | Surface | Kind | Entry Point | AC | Production Targets | Page States | Click Path | Required |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- |',
    ]
    if rows:
        lines.extend(rows)
    else:
        lines.append('| - | - | - | - | - | - | - | - | - |')
    return lines


def render_prototype_review_html(
    normalized_manifest: dict[str, Any],
    *,
    requirements_path: Path,
) -> str:
    prototypes = normalized_manifest.get('prototypes') if isinstance(normalized_manifest.get('prototypes'), list) else []
    rows: list[str] = []
    link_rows: list[str] = []
    surface_rows: list[str] = []
    previews: list[str] = []
    for prototype in prototypes:
        if not isinstance(prototype, dict):
            continue
        prototype_id = str(prototype.get('id') or '').strip()
        title = str(prototype.get('title') or prototype_id or 'prototype')
        prototype_type = str(prototype.get('type') or '').strip()
        href = str(prototype.get('review_href') or prototype.get('url') or '').strip()
        targets = '; '.join(_implementation_target_label(target) for target in prototype.get('implementation_targets') or [])
        link_rows.append(
            '<tr>'
            f'<td>{html.escape(prototype_id)}</td>'
            f'<td>{html.escape(prototype_type)}</td>'
            f'<td>{html.escape(title)}</td>'
            f'<td>{_prototype_source_link_html(prototype, href)}</td>'
            f'<td>{html.escape(targets)}</td>'
            '</tr>'
        )
        rows.append(
            '<tr>'
            f'<td>{html.escape(prototype_id)}</td>'
            f'<td>{html.escape(title)}</td>'
            f'<td>{html.escape(prototype_type)}</td>'
            f'<td>{html.escape("; ".join(prototype.get("linked_acceptance_criteria") or []))}</td>'
            f'<td>{html.escape("; ".join(prototype.get("linked_journeys") or []))}</td>'
            f'<td>{html.escape(targets)}</td>'
            f'<td>{html.escape("; ".join(prototype.get("page_states") or []))}</td>'
            f'<td>{html.escape(" -> ".join(prototype.get("click_path") or []))}</td>'
            '</tr>'
        )
        for surface in prototype.get('surface_contracts') or []:
            if not isinstance(surface, dict):
                continue
            surface_rows.append(
                '<tr>'
                f'<td>{html.escape(prototype_id)}</td>'
                f'<td>{html.escape(str(surface.get("id") or ""))}</td>'
                f'<td>{html.escape(str(surface.get("kind") or ""))}</td>'
                f'<td>{html.escape("; ".join(surface.get("entrypoints") or []))}</td>'
                f'<td>{html.escape("; ".join(surface.get("linked_acceptance_criteria") or []))}</td>'
                f'<td>{html.escape("; ".join(_implementation_target_label(target) for target in surface.get("implementation_targets") or []))}</td>'
                f'<td>{html.escape("; ".join(surface.get("page_states") or []))}</td>'
                f'<td>{html.escape(" -> ".join(surface.get("click_path") or []))}</td>'
                f'<td>{html.escape("yes" if surface.get("required") is True else "no")}</td>'
                '</tr>'
            )
        preview = _render_prototype_html_preview(normalized_manifest, prototype, title, href)
        if preview:
            previews.append(preview)
    if not rows:
        rows.append('<tr><td colspan="8">No prototypes declared.</td></tr>')
    if not link_rows:
        link_rows.append('<tr><td colspan="5">No prototypes declared.</td></tr>')
    if not previews:
        previews.append('<p class="muted">No renderable local prototype previews declared.</p>')
    if not surface_rows:
        surface_rows.append('<tr><td colspan="9">No surface contracts declared.</td></tr>')

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Prototype Review Bundle for Plannotator</title>
  <style>
    body {{ margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #172033; background: #f6f8fb; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    section {{ margin: 0 0 24px; }}
    .meta {{ color: #4f5d75; font-size: 14px; }}
    .preview {{ background: #fff; border: 1px solid #d9e2ef; border-radius: 8px; padding: 16px; margin: 16px 0; }}
    .source-link {{ margin: 8px 0 12px; }}
    .prototype-frame {{ width: 100%; min-height: 680px; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d9e2ef; }}
    th, td {{ border: 1px solid #d9e2ef; padding: 8px; text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ background: #edf2f7; }}
    .muted {{ color: #667085; }}
  </style>
</head>
<body>
  <main>
    <h1>Prototype Review Bundle for Plannotator</h1>
    <p class="meta">Approval gate: <code>{html.escape(str(requirements_path))}</code></p>
    <p class="meta">Source manifest: <code>{html.escape(str(normalized_manifest.get('source_manifest') or '-'))}</code></p>

    <section>
      <h2>Prototype Links</h2>
      <table>
        <thead>
          <tr><th>Prototype</th><th>Type</th><th>Title</th><th>Source Link</th><th>Production Targets</th></tr>
        </thead>
        <tbody>{''.join(link_rows)}</tbody>
      </table>
    </section>

    <section>
      <h2>Rendered Prototype Preview</h2>
      {''.join(previews)}
    </section>

    <section>
      <h2>AC/Journey Mapping</h2>
      <table>
        <thead>
          <tr><th>Prototype</th><th>Title</th><th>Type</th><th>AC</th><th>Journeys</th><th>Production Targets</th><th>Page States</th><th>Click Path</th></tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>

    <section>
      <h2>Prototype Surface Coverage Matrix</h2>
      <table>
        <thead>
          <tr><th>Prototype</th><th>Surface</th><th>Kind</th><th>Entry Point</th><th>AC</th><th>Production Targets</th><th>Page States</th><th>Click Path</th><th>Required</th></tr>
        </thead>
        <tbody>{''.join(surface_rows)}</tbody>
      </table>
    </section>

    <section>
      <h2>Approval Gate</h2>
      <p>Approve or request changes on <code>{html.escape(str(requirements_path))}</code> after reviewing this rendered bundle.</p>
    </section>
  </main>
</body>
</html>
"""


def start_prototype_review_preview_server(
    *,
    review_path: Path,
    manifest_path: Path,
    prototypes_dir: Path,
    approval_gate_path: Path,
) -> PrototypePreviewServer:
    allowed = {
        f'/{review_path.name}': review_path.resolve(),
        f'/{REVIEW_MANIFEST_NAME}': manifest_path.resolve(),
        '/requirements-and-acceptance.md': approval_gate_path.resolve(),
    }
    for sibling_name in {REVIEW_BUNDLE_NAME, REVIEW_BUNDLE_HTML_NAME}:
        sibling = review_path.parent / sibling_name
        if sibling.exists() and sibling.is_file():
            allowed[f'/{sibling_name}'] = sibling.resolve()
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
            content_type = _preview_content_type(target)
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
    return PrototypePreviewServer(
        httpd=httpd,
        thread=thread,
        base_url=f'http://{host}:{port}',
        review_name=review_path.name,
    )


def _render_prototype_html_preview(
    normalized_manifest: dict[str, Any],
    prototype: dict[str, Any],
    title: str,
    href: str,
) -> str:
    prototype_type = str(prototype.get('type') or '').strip().lower()
    escaped_title = html.escape(title)
    escaped_href = html.escape(href, quote=True)
    source_link = _prototype_source_link_html(prototype, href)
    if prototype_type == 'html':
        local_file = _local_review_href_path(normalized_manifest, href)
        if local_file is not None and local_file.exists():
            source = local_file.read_text(encoding='utf-8', errors='replace')
            return (
                '<article class="preview">'
                f'<h3>{escaped_title}</h3>'
                f'<p class="source-link">{source_link}</p>'
                f'<iframe class="prototype-frame" title="{escaped_title}" '
                f'srcdoc="{html.escape(source, quote=True)}"></iframe>'
                '</article>'
            )
        if href:
            return (
                '<article class="preview">'
                f'<h3>{escaped_title}</h3>'
                f'<p class="source-link">{source_link}</p>'
                f'<iframe class="prototype-frame" title="{escaped_title}" src="{escaped_href}"></iframe>'
                '</article>'
            )
    if prototype_type == 'markdown' and href:
        return (
            '<article class="preview">'
            f'<h3>{escaped_title}</h3>'
            f'<p class="source-link">{source_link}</p>'
            '<p class="muted">Source document available for review.</p>'
            '</article>'
        )
    if prototype_type == 'image' and href:
        return (
            '<article class="preview">'
            f'<h3>{escaped_title}</h3>'
            f'<p class="source-link">{source_link}</p>'
            f'<img src="{escaped_href}" alt="{escaped_title}" style="max-width: 100%; border: 1px solid #cbd5e1; border-radius: 6px;">'
            '</article>'
        )
    if prototype_type == 'url' and href:
        return (
            '<article class="preview">'
            f'<h3>{escaped_title}</h3>'
            f'<p class="source-link">{source_link}</p>'
            f'<iframe class="prototype-frame" title="{escaped_title}" src="{escaped_href}"></iframe>'
            '</article>'
        )
    return ''


def _prototype_source_link_html(prototype: dict[str, Any], href: str) -> str:
    href = str(href or '').strip()
    if not href:
        return '<span class="muted">No source link</span>'
    label = _prototype_source_link_label(str(prototype.get('type') or ''))
    return f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>'


def _prototype_source_link_label(prototype_type: str) -> str:
    prototype_type = prototype_type.strip().lower()
    if prototype_type == 'html':
        return 'Open rendered source'
    if prototype_type == 'markdown':
        return 'Open markdown/source doc'
    if prototype_type == 'image':
        return 'Open image'
    if prototype_type == 'url':
        return 'Open external prototype'
    return 'Open source'


def _preview_content_type(target: Path) -> str:
    suffix = target.suffix.lower()
    if suffix in {'.md', '.markdown'}:
        return 'text/markdown; charset=utf-8'
    if suffix in {'.html', '.htm'}:
        return 'text/html; charset=utf-8'
    content_type = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
    if content_type.startswith('text/') or content_type in {'application/json'}:
        return f'{content_type}; charset=utf-8'
    return content_type


def _local_review_href_path(normalized_manifest: dict[str, Any], href: str) -> Path | None:
    split = urlsplit(href)
    if split.scheme or split.netloc:
        return None
    review_bundle = str(normalized_manifest.get('review_bundle_path') or '').strip()
    prototypes_dir = str(normalized_manifest.get('prototypes_dir') or '').strip()
    if not review_bundle or not prototypes_dir:
        return None
    relative = PurePosixPath(posixpath.normpath(unquote(split.path).lstrip('/')))
    if str(relative).startswith('..'):
        return None
    draft_dir = Path(review_bundle).parent
    candidate = (draft_dir / Path(*relative.parts)).resolve()
    prototypes_root = Path(prototypes_dir).resolve()
    if candidate == prototypes_root or candidate.is_relative_to(prototypes_root):
        return candidate
    return None


def _build_normalized_manifest(
    manifest_path: Path,
    *,
    requirements_path: Path,
    artifacts_dir: Path,
    require_clickable: bool = False,
    require_implementation_targets: bool = False,
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
            require_implementation_targets=require_implementation_targets,
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
    require_implementation_targets: bool,
    copy_assets: bool,
    issues: list[str],
) -> dict[str, Any] | None:
    raw_id = str(raw.get('id') or '').strip()
    prototype_id = _safe_id(raw_id)
    if not raw_id:
        issues.append(f'prototype[{index}] missing id')
    prototype_type = str(raw.get('type') or '').strip().lower()
    if prototype_type == 'md':
        prototype_type = 'markdown'
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

    implementation_targets = _normalize_implementation_targets(
        raw,
        prototype_label=raw_id or str(index),
        issues=issues,
    )
    surface_contracts = _normalize_surface_contracts(
        raw,
        prototype_label=raw_id or str(index),
        requirements_ac_ids=requirements_ac_ids,
        issues=issues,
    )
    if require_implementation_targets and not implementation_targets and not surface_contracts:
        issues.append(
            f'prototype {raw_id or index} missing implementation_targets; '
            'map the prototype or each surface_contract to at least one production route/page target'
        )

    source_path = ''
    url = str(raw.get('url') or '').strip()
    review_href = str(raw.get('review_href') or '').strip()
    if prototype_type == 'url':
        if not url:
            issues.append(f'prototype {raw_id or index} missing url')
        else:
            _validate_url(url, raw_id or str(index), issues)
            review_href = url
    elif prototype_type in {'html', 'image', 'markdown'}:
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

    if (
        require_implementation_targets
        and prototype_type in {'html', 'url'}
        and not surface_contracts
        and _prototype_has_multi_surface_signal(raw, source_path=source_path)
    ):
        issues.append(
            f'prototype {raw_id or index} appears to contain dialog/drawer/panel/selector/management surfaces; '
            'add surface_contracts[] for each interactive UI surface'
        )

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
        'implementation_targets': implementation_targets,
        'surface_contracts': surface_contracts,
        'thumbnail': str(raw.get('thumbnail') or '').strip(),
        'preview_hint': str(raw.get('preview_hint') or raw.get('previewHint') or '').strip(),
        'review_guidance': str(raw.get('review_guidance') or raw.get('reviewGuidance') or '').strip(),
    }


def _normalize_surface_contracts(
    raw: dict[str, Any],
    *,
    prototype_label: str,
    requirements_ac_ids: set[str],
    issues: list[str],
) -> list[dict[str, Any]]:
    raw_surfaces = _first_present(raw, 'surface_contracts', 'ui_surfaces', 'page_state_targets')
    if raw_surfaces is None:
        return []
    if not isinstance(raw_surfaces, list) or not raw_surfaces:
        issues.append(f'prototype {prototype_label} surface_contracts must be a non-empty list')
        return []

    normalized: list[dict[str, Any]] = []
    for index, surface in enumerate(raw_surfaces):
        if not isinstance(surface, dict):
            issues.append(f'prototype {prototype_label} surface_contracts[{index}] must be an object')
            continue
        surface_label = str(surface.get('id') or f'{index}').strip()
        raw_id = str(surface.get('id') or '').strip()
        surface_id = _safe_id(raw_id)
        if not raw_id:
            issues.append(f'prototype {prototype_label} surface_contracts[{index}] missing id')

        title = str(surface.get('title') or '').strip()
        if not title:
            issues.append(f'prototype {prototype_label} surface {surface_label} missing title')

        kind = str(surface.get('kind') or surface.get('type') or '').strip().lower()
        if not kind:
            issues.append(f'prototype {prototype_label} surface {surface_label} missing kind')
        elif kind not in ALLOWED_SURFACE_KINDS:
            issues.append(f'prototype {prototype_label} surface {surface_label} has unsupported kind: {kind}')

        page_states = _string_list(surface.get('page_states') or surface.get('pageStates'))
        click_path = _string_list(surface.get('click_path') or surface.get('clickPath'))
        entrypoints = _string_list(surface.get('entrypoints') or surface.get('entry_points') or surface.get('entryPoints'))
        if not page_states:
            issues.append(f'prototype {prototype_label} surface {surface_label} missing page_states')
        if not click_path:
            issues.append(f'prototype {prototype_label} surface {surface_label} missing click_path')
        if not entrypoints:
            issues.append(f'prototype {prototype_label} surface {surface_label} missing entrypoints')

        linked_acs = _string_list(
            surface.get('linked_acceptance_criteria')
            or surface.get('acceptance_criteria')
            or surface.get('linked_acs')
            or surface.get('acs')
        )
        unknown_acs = sorted({ac.upper() for ac in linked_acs if ac.upper() not in requirements_ac_ids})
        if not linked_acs:
            issues.append(f'prototype {prototype_label} surface {surface_label} missing linked_acceptance_criteria')
        if unknown_acs:
            issues.append(
                f'prototype {prototype_label} surface {surface_label} unknown acceptance criteria: '
                + ', '.join(unknown_acs)
            )

        implementation_targets = _normalize_implementation_targets(
            surface,
            prototype_label=f'{prototype_label} surface {surface_label}',
            issues=issues,
        )
        if not implementation_targets:
            issues.append(f'prototype {prototype_label} surface {surface_label} missing implementation_targets')

        required = surface.get('required')
        if required is not True:
            issues.append(f'prototype {prototype_label} surface {surface_label} missing required=true')

        if not surface_id or not title or kind not in ALLOWED_SURFACE_KINDS:
            continue
        normalized.append({
            'id': surface_id,
            'title': title,
            'kind': kind,
            'page_states': page_states,
            'click_path': click_path,
            'entrypoints': entrypoints,
            'implementation_targets': implementation_targets,
            'linked_acceptance_criteria': [ac.upper() for ac in linked_acs],
            'required': required is True,
        })
    return normalized


def _prototype_has_multi_surface_signal(raw: dict[str, Any], *, source_path: str) -> bool:
    parts = [
        raw.get('title'),
        raw.get('url'),
        raw.get('review_guidance'),
        raw.get('reviewGuidance'),
        raw.get('preview_hint'),
        raw.get('previewHint'),
        raw.get('page_states'),
        raw.get('pageStates'),
        raw.get('click_path'),
        raw.get('clickPath'),
    ]
    if source_path:
        path = Path(source_path)
        if path.exists() and path.is_file() and path.suffix.lower() in {'.html', '.htm'}:
            try:
                parts.append(path.read_text(encoding='utf-8', errors='replace')[:20000])
            except OSError:
                pass
    haystack = _normalized_signal_text(parts)
    return any(keyword in haystack for keyword in MULTI_SURFACE_SIGNAL_KEYWORDS)


def _normalized_signal_text(value: Any) -> str:
    if isinstance(value, list):
        return ' '.join(_normalized_signal_text(item) for item in value)
    if isinstance(value, dict):
        return ' '.join(_normalized_signal_text(item) for item in value.values())
    return re.sub(r'\s+', ' ', str(value or '').strip().lower())


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def prototype_conformance_matrix_rows(
    *,
    state: dict[str, Any],
    artifacts_dir: Path,
    requirements_path: Path | None = None,
) -> list[dict[str, Any]]:
    requirements_path = requirements_path or artifacts_dir.parent / 'approvals' / 'requirements-and-acceptance.md'
    manifest_path, resolved_artifacts_dir = source_prototype_manifest_path_for_requirements(requirements_path)
    if not manifest_path.exists():
        return []
    normalized = validate_prototype_review_manifest(
        manifest_path,
        requirements_path=requirements_path,
        artifacts_dir=resolved_artifacts_dir,
        require_implementation_targets=True,
    )
    test_cases = _state_test_cases(state)
    evidence_rows = _verification_evidence_rows(artifacts_dir)
    rows: list[dict[str, Any]] = []
    for contract in prototype_required_target_contracts(normalized):
        prototype_id = str(contract.get('prototype_id') or '').strip()
        surface_id = str(contract.get('surface_id') or '').strip()
        target = contract.get('target') if isinstance(contract.get('target'), dict) else {}
        matched_cases = [
            case for case in test_cases
            if prototype_test_case_covers_target(case, prototype_id, target, surface_id=surface_id)
        ]
        base_row = {
            'prototype_id': prototype_id,
            'surface_id': surface_id,
            'surface_title': contract.get('surface_title') or '',
            'surface_kind': contract.get('surface_kind') or '',
            'entrypoints': contract.get('entrypoints') or [],
            'linked_acceptance_criteria': contract.get('linked_acceptance_criteria') or [],
            'production_target': _implementation_target_label(target),
        }
        if not matched_cases:
            rows.append({
                **base_row,
                'test_case_id': '',
                'command': '',
                'status': 'missing',
                'expected': '',
                'artifact_refs': [],
            })
            continue
        for case in matched_cases:
            evidence = _matching_evidence_row(case, evidence_rows)
            rows.append({
                **base_row,
                'test_case_id': str(case.get('id') or '').strip(),
                'command': str(case.get('command') or (evidence or {}).get('command') or '').strip(),
                'status': str((evidence or {}).get('status') or 'missing'),
                'expected': str(case.get('expected') or (evidence or {}).get('expected') or '').strip(),
                'artifact_refs': (evidence or {}).get('artifact_refs') or [],
            })
    return rows


def validate_final_prototype_conformance(
    *,
    state: dict[str, Any],
    artifacts_dir: Path,
    requirements_path: Path | None = None,
) -> None:
    rows = prototype_conformance_matrix_rows(
        state=state,
        artifacts_dir=artifacts_dir,
        requirements_path=requirements_path,
    )
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (
            str(row.get('prototype_id') or '').strip(),
            str(row.get('surface_id') or '').strip(),
            str(row.get('production_target') or '').strip(),
        )
        grouped.setdefault(key, []).append(row)
    incomplete = [
        group_rows[0]
        for group_rows in grouped.values()
        if not any(row.get('status') == 'passed' for row in group_rows)
    ]
    if not incomplete:
        return
    summary = '; '.join(
        _prototype_conformance_row_summary(row)
        for row in incomplete
    )
    raise ValueError('prototype conformance is incomplete: ' + summary)


def _prototype_conformance_row_summary(row: dict[str, Any]) -> str:
    surface_id = str(row.get('surface_id') or '').strip()
    if surface_id:
        return 'prototype {prototype} surface {surface} target {target} via {case}: {status}'.format(
            prototype=row.get('prototype_id') or 'unknown-prototype',
            surface=surface_id,
            target=row.get('production_target') or 'unknown-target',
            case=row.get('test_case_id') or 'missing-test-case',
            status=row.get('status') or 'missing',
        )
    return '{prototype} -> {target} via {case}: {status}'.format(
        prototype=row.get('prototype_id') or 'unknown-prototype',
        target=row.get('production_target') or 'unknown-target',
        case=row.get('test_case_id') or 'missing-test-case',
        status=row.get('status') or 'missing',
    )


def prototype_required_target_contracts(normalized_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    for prototype in normalized_manifest.get('prototypes') or []:
        if not isinstance(prototype, dict):
            continue
        prototype_id = str(prototype.get('id') or '').strip()
        surfaces = [
            surface for surface in prototype.get('surface_contracts') or []
            if isinstance(surface, dict) and surface.get('required') is True
        ]
        if surfaces:
            for surface in surfaces:
                for target in surface.get('implementation_targets') or []:
                    if not isinstance(target, dict):
                        continue
                    contracts.append({
                        'prototype_id': prototype_id,
                        'surface_id': str(surface.get('id') or '').strip(),
                        'surface_title': str(surface.get('title') or '').strip(),
                        'surface_kind': str(surface.get('kind') or '').strip(),
                        'entrypoints': surface.get('entrypoints') or [],
                        'linked_acceptance_criteria': surface.get('linked_acceptance_criteria') or [],
                        'target': target,
                    })
            continue
        for target in prototype.get('implementation_targets') or []:
            if not isinstance(target, dict):
                continue
            contracts.append({
                'prototype_id': prototype_id,
                'surface_id': '',
                'surface_title': '',
                'surface_kind': '',
                'entrypoints': [],
                'linked_acceptance_criteria': prototype.get('linked_acceptance_criteria') or [],
                'target': target,
            })
    return contracts


def prototype_test_case_covers_target(
    case: dict[str, Any],
    prototype_id: str,
    target: dict[str, Any],
    surface_id: str | None = None,
) -> bool:
    prototype_ids = {
        _safe_id(item)
        for item in _string_list(case.get('prototype_conformance') or case.get('prototypeConformance'))
    }
    if _safe_id(prototype_id) not in prototype_ids:
        return False
    if surface_id:
        surface_ids = {
            _safe_id(item)
            for item in _string_list(
                case.get('prototype_surfaces')
                or case.get('prototypeSurfaces')
                or case.get('surface_contracts')
                or case.get('surfaceContracts')
                or case.get('prototype_surface')
                or case.get('prototypeSurface')
            )
        }
        if _safe_id(surface_id) not in surface_ids:
            return False
    declared_targets = _case_production_target_values(case)
    expected_targets = _target_match_values(target)
    return bool(declared_targets & expected_targets)


def surface_contract_requires_browser_e2e(surface_kind: str) -> bool:
    return str(surface_kind or '').strip().lower() in BROWSER_SURFACE_KINDS


def implementation_target_is_browser_route(target: dict[str, Any]) -> bool:
    kind = str(target.get('kind') or '').strip().lower()
    path = str(target.get('path') or '').strip()
    return kind == 'route' or path.startswith('/')


def _normalize_implementation_targets(
    raw: dict[str, Any],
    *,
    prototype_label: str,
    issues: list[str],
) -> list[dict[str, str]]:
    value = (
        raw.get('implementation_targets')
        if raw.get('implementation_targets') is not None
        else raw.get('production_targets')
        if raw.get('production_targets') is not None
        else raw.get('real_targets')
    )
    if value is None:
        return []
    if not isinstance(value, list) or not value:
        issues.append(f'prototype {prototype_label} implementation_targets must be a non-empty list')
        return []
    normalized: list[dict[str, str]] = []
    for index, target in enumerate(value):
        if not isinstance(target, dict):
            issues.append(f'prototype {prototype_label} implementation_targets[{index}] must be an object')
            continue
        kind = str(target.get('kind') or '').strip().lower()
        path = str(target.get('path') or '').strip()
        if not kind:
            issues.append(f'prototype {prototype_label} implementation_targets[{index}] missing kind')
        if not path:
            issues.append(f'prototype {prototype_label} implementation_targets[{index}] missing path')
        if kind and path:
            normalized.append({'kind': kind, 'path': path})
    return normalized


def _implementation_target_label(target: dict[str, Any]) -> str:
    kind = str(target.get('kind') or '').strip()
    path = str(target.get('path') or '').strip()
    if kind and path:
        return f'{kind}:{path}'
    return path or kind


def _target_match_values(target: dict[str, Any]) -> set[str]:
    label = _implementation_target_label(target)
    path = str(target.get('path') or '').strip()
    values = {label, path}
    return {value for value in values if value}


def _case_production_target_values(case: dict[str, Any]) -> set[str]:
    raw = (
        case.get('production_targets')
        or case.get('productionTargets')
        or case.get('implementation_targets')
        or case.get('implementationTargets')
        or case.get('real_targets')
        or case.get('realTargets')
    )
    if raw is None:
        return set()
    raw_items = raw if isinstance(raw, list) else [raw]
    values: set[str] = set()
    for item in raw_items:
        if isinstance(item, dict):
            path = str(item.get('path') or '').strip()
            kind = str(item.get('kind') or '').strip()
            if path:
                values.add(path)
            if kind and path:
                values.add(f'{kind}:{path}')
        else:
            text = str(item or '').strip()
            if text:
                values.add(text)
    return values


def _state_test_cases(state: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for unit in state.get('units') or []:
        if not isinstance(unit, dict):
            continue
        for key in ('test_cases', 'testCases'):
            raw_cases = unit.get(key)
            if not isinstance(raw_cases, list):
                continue
            for case in raw_cases:
                if isinstance(case, dict):
                    cases.append(case)
    return cases


def _verification_evidence_rows(artifacts_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(Path(artifacts_dir).rglob('verification.json')):
        if 'final-scope-audit' in path.parts:
            continue
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        raw_rows = payload.get('evidence_rows')
        if not isinstance(raw_rows, list):
            continue
        for row in raw_rows:
            if isinstance(row, dict):
                copied = dict(row)
                copied.setdefault('artifact_refs', [str(path)])
                rows.append(copied)
    return rows


def _matching_evidence_row(case: dict[str, Any], evidence_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    case_id = str(case.get('id') or '').strip()
    command = str(case.get('command') or '').strip()
    for row in evidence_rows:
        if case_id and str(row.get('test_case_id') or '').strip() == case_id:
            return row
    if case_id:
        return None
    for row in evidence_rows:
        if command and str(row.get('command') or '').strip() == command:
            return row
    return None


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
