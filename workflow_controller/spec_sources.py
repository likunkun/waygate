from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPPORTED_SOURCE_TYPE = 'waygate-markdown'


def requirements_spec_metadata(raw_path: str | Path) -> dict[str, Any]:
    path = Path(raw_path).expanduser()
    if not path.exists():
        raise ValueError(f'spec path does not exist: {path}')

    classification = classify_requirements_spec_path(path)
    source_type = classification['sourceType']
    if source_type != SUPPORTED_SOURCE_TYPE:
        raise ValueError(
            f"{classification['label']} is unsupported in V0.5.6 and deferred to V0.6.1: {path}"
        )

    resolved = path.resolve()
    try:
        content = resolved.read_bytes()
    except OSError as exc:
        raise ValueError(f'spec path must be a readable Markdown file: {path}: {exc}') from exc
    return {
        'path': str(resolved),
        'hash': 'sha256:' + hashlib.sha256(content).hexdigest(),
        'sourceType': source_type,
        'importedAt': datetime.now(timezone.utc).isoformat(),
    }


def classify_requirements_spec_path(path: Path) -> dict[str, str]:
    if path.is_dir():
        if _looks_like_openspec_dir(path):
            return {'sourceType': 'openspec', 'label': 'OpenSpec-like spec path'}
        if _looks_like_spec_kit_dir(path):
            return {'sourceType': 'spec-kit', 'label': 'Spec Kit-like spec path'}
        raise ValueError(f'spec path must be a readable Markdown file: {path}')

    if not path.is_file():
        raise ValueError(f'spec path must be a readable Markdown file: {path}')

    name = path.name.lower()
    if _looks_like_spec_kit_file(path):
        return {'sourceType': 'spec-kit', 'label': 'Spec Kit-like spec path'}
    if _looks_like_openspec_file(path):
        return {'sourceType': 'openspec', 'label': 'OpenSpec-like spec path'}
    if path.suffix.lower() not in {'.md', '.markdown'}:
        raise ValueError(f'spec path must be a readable Markdown file: {path}')
    if 'openspec' in name:
        return {'sourceType': 'openspec', 'label': 'OpenSpec-like spec path'}
    return {'sourceType': SUPPORTED_SOURCE_TYPE, 'label': 'Waygate Markdown spec path'}


def same_requirements_spec(existing: dict[str, Any] | None, incoming: dict[str, Any] | None) -> bool:
    if not existing or not incoming:
        return False
    return (
        str(existing.get('path') or '') == str(incoming.get('path') or '')
        and str(existing.get('hash') or '') == str(incoming.get('hash') or '')
        and str(existing.get('sourceType') or '') == str(incoming.get('sourceType') or '')
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


def _read_text_excerpt(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')[:2048]
    except OSError:
        return ''
    except UnicodeDecodeError:
        return ''
