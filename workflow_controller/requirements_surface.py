from __future__ import annotations

import re
from pathlib import Path
from typing import Any


CLASSIFICATION_VALUES = {'required', 'not_required', 'unknown'}
SURFACE_CLASSIFICATION_FIELDS = ('product_ui', 'web_system', 'prototype_required')
_MAX_SCAN_CHARS = 200_000


def classify_requirements_surface(state: dict[str, Any]) -> dict[str, Any]:
    evidence_items = _surface_evidence_items(state)
    visible_surfaces = _visible_surface_labels(evidence_items)
    has_surface = bool(visible_surfaces)
    has_web_surface = has_surface and _positive_evidence_has_any(evidence_items, _WEB_SURFACE_PATTERNS)
    has_prototype = _positive_evidence_has_any(evidence_items, _PROTOTYPE_PATTERNS)
    has_explicit_no_ui_basis = _evidence_has_any(evidence_items, _NO_UI_BASIS_PATTERNS)

    true_ui_flag = state.get('currentUnitNeedsUiDesign') is True
    true_web_flag = state.get('currentUnitIsWebSystem') is True

    product_ui = _classification_value(
        required=true_ui_flag or has_surface or _positive_evidence_has_any(evidence_items, _UI_SURFACE_PATTERNS),
        not_required=has_explicit_no_ui_basis,
    )
    web_system = _classification_value(
        required=true_web_flag or has_web_surface or _positive_evidence_has_any(evidence_items, _WEB_SYSTEM_PATTERNS),
        not_required=has_explicit_no_ui_basis,
    )
    prototype_required = _classification_value(
        required=product_ui == 'required' or web_system == 'required' or has_prototype,
        not_required=has_explicit_no_ui_basis,
    )

    snippets = _classification_snippets(evidence_items, visible_surfaces)
    if state.get('currentUnitNeedsUiDesign') is False:
        snippets.append('currentUnitNeedsUiDesign=false (ignored as no-UI evidence)')
    if state.get('currentUnitIsWebSystem') is False:
        snippets.append('currentUnitIsWebSystem=false (ignored as no-Web evidence)')

    return {
        'product_ui': product_ui,
        'web_system': web_system,
        'prototype_required': prototype_required,
        'visible_surfaces': visible_surfaces,
        'evidence_snippets': _dedupe_strings(snippets)[:12],
    }


def refresh_requirements_surface_classification(state: dict[str, Any]) -> dict[str, Any]:
    classification = classify_requirements_surface(state)
    state['requirementsSurfaceClassification'] = classification
    return classification


def requirements_surface_classification(state: dict[str, Any]) -> dict[str, Any]:
    existing = state.get('requirementsSurfaceClassification')
    if _valid_surface_classification(existing):
        return existing
    return classify_requirements_surface(state)


def render_requirements_surface_classification_markdown(state: dict[str, Any]) -> str:
    classification = requirements_surface_classification(state)
    visible = classification.get('visible_surfaces') or []
    evidence = classification.get('evidence_snippets') or []
    visible_lines = '\n'.join(f'- {item}' for item in visible) or '- 未识别到；必须在 Scope 中说明依据或回到澄清。'
    evidence_lines = '\n'.join(f'- {item}' for item in evidence) or '- 无。'
    return (
        'requirementsSurfaceClassification:\n'
        f"- product_ui: `{classification.get('product_ui', 'unknown')}`\n"
        f"- web_system: `{classification.get('web_system', 'unknown')}`\n"
        f"- prototype_required: `{classification.get('prototype_required', 'unknown')}`\n"
        '- visible_surfaces:\n'
        f'{visible_lines}\n'
        '- evidence_snippets:\n'
        f'{evidence_lines}\n'
        '\n'
        '规则：不得把默认 false 当成不需要 UI/原型的证据；'
        '只有明确的 backend/API/CLI-only 依据才能写 `not_required`。'
    )


def requirements_surface_requires_product_ui(state: dict[str, Any]) -> bool:
    return requirements_surface_classification(state).get('product_ui') == 'required'


def requirements_surface_requires_web_system(state: dict[str, Any]) -> bool:
    return requirements_surface_classification(state).get('web_system') == 'required'


def requirements_surface_requires_prototype(state: dict[str, Any]) -> bool:
    return requirements_surface_classification(state).get('prototype_required') == 'required'


def requirements_surface_is_unknown(state: dict[str, Any]) -> bool:
    classification = requirements_surface_classification(state)
    return any(classification.get(field) == 'unknown' for field in SURFACE_CLASSIFICATION_FIELDS)


def requirements_surface_declares_no_ui_basis(content: str) -> bool:
    normalized = _normalize(content)
    return any(pattern.search(normalized) for pattern in _NO_UI_BASIS_PATTERNS)


def requirements_surface_explains_unknown(content: str) -> bool:
    normalized = _normalize(content)
    if not any(pattern.search(normalized) for pattern in _UNKNOWN_SURFACE_PATTERNS):
        return False
    return any(marker in normalized for marker in (
        'requirementssurfaceclassification',
        '目标产品表面',
        '可见产品表面',
        'ui/prototypebasis',
        'surfaceclassification',
    ))


def requirements_surface_uses_false_flag_as_no_ui_basis(content: str) -> bool:
    normalized = _normalize(content)
    has_false_flag = 'currentunitneedsuidesign=false' in normalized or 'currentunitiswebsystem=false' in normalized
    has_no_ui_claim = any(pattern.search(normalized) for pattern in _NO_UI_CLAIM_PATTERNS)
    rejects_false_flag_basis = any(marker in normalized for marker in (
        '不得把默认false当成不需要',
        '不能把默认false当成不需要',
        '不得把falseflag当作不需要',
        '不能把falseflag当作不需要',
        '不得把falseflag当成不需要',
        '不能把falseflag当成不需要',
        'cannotbeusedasno-uibasis',
        'cannotbeusedasnoubasis',
        'falseflagcannotbeusedasno-uibasis',
        'falseflagcannotbeusedasnoubasis',
        'ignoredasnouvievidence',
        'ignoredasno-uievidence',
        'ignoredasno-webevidence',
    ))
    rejects_false_flag_basis = rejects_false_flag_basis or _rejects_false_flag_no_ui_basis(normalized)
    if rejects_false_flag_basis and not any(marker in normalized for marker in (
        '因为currentunitneedsuidesign=false所以',
        'becausecurrentunitneedsuidesign=false',
        'currentunitneedsuidesign=false所以不需要',
        'currentunitiswebsystem=false所以不需要',
    )):
        return False
    return has_false_flag and has_no_ui_claim


def _rejects_false_flag_no_ui_basis(normalized: str) -> bool:
    if not any(marker in normalized for marker in (
        'falseflag',
        '默认false',
        'currentunitneedsuidesign=false',
        'currentunitiswebsystem=false',
    )):
        return False
    has_rejection = any(marker in normalized for marker in ('不能', '不得', '不可', 'cannot', 'mustnot', 'donot'))
    has_basis = any(marker in normalized for marker in ('证据', '依据', 'basis', 'evidence'))
    has_no_ui = any(marker in normalized for marker in ('不需要ui', '无ui', '不需要原型', 'no-ui', 'noui', 'no-web', 'noweb'))
    return has_rejection and has_basis and has_no_ui


def state_targets_waygate_controller(state: dict[str, Any]) -> bool:
    candidates = [
        state.get('requestedOutcome'),
        state.get('feasibleOutcome'),
        state.get('currentUnitId'),
        state.get('task_id'),
        state.get('workspacePath'),
        state.get('executionWorkspacePath'),
        state.get('targetProjectContext'),
        state.get('target_project_context'),
    ]
    text = _normalize('\n'.join(str(item or '') for item in candidates))
    if any(marker in text for marker in ('workflow-controller', 'waygate', 'rrc-controller')):
        return True
    return bool(re.search(r'\bv0[.-]6[.-]\d+[a-z]?\b|\bv0-6-\d+[a-z]?\b', text))


def surface_text_mentions_visible_surface(text: str, state: dict[str, Any]) -> bool:
    normalized = _normalize(text)
    classification = requirements_surface_classification(state)
    for surface in classification.get('visible_surfaces') or []:
        if _normalize(str(surface)) in normalized:
            return True
    return any(pattern.search(normalized) for pattern in _UI_SURFACE_PATTERNS)


def controller_perspective_issue(text: str, state: dict[str, Any], *, label: str) -> str | None:
    if state_targets_waygate_controller(state):
        return None
    normalized = _normalize(text)
    controller_hits = sum(1 for pattern in _CONTROLLER_PERSPECTIVE_PATTERNS if pattern.search(normalized))
    if controller_hits < 2:
        return None
    if surface_text_mentions_visible_surface(text, state):
        return None
    return (
        f'{label} is describing Waygate/controller workflow instead of target product perspective; '
        'rewrite it around the target product/system surfaces, APIs, data flow, and runtime boundaries'
    )


def _surface_evidence_items(state: dict[str, Any]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for key in (
        'requestedOutcome',
        'feasibleOutcome',
        'targetProjectType',
        'target_project_type',
        'targetProjectKind',
        'target_project_kind',
        'targetProjectContext',
        'target_project_context',
        'requirementsTargetType',
        'requirements_target_type',
        'requirementsRevisionFeedback',
        'promptPath',
    ):
        value = state.get(key)
        if value:
            items.append((key, str(value)))
    for flag in ('currentUnitNeedsUiDesign', 'currentUnitIsWebSystem'):
        if state.get(flag) is True:
            items.append((flag, f'{flag}=true'))
    unit = _current_unit(state)
    if isinstance(unit, dict):
        for key in ('name', 'description', 'scope', 'done_when', 'non_goals'):
            value = unit.get(key)
            if value:
                items.append((f'unit.{key}', _stringify(value)))
    spec = state.get('requirementsSpec') if isinstance(state.get('requirementsSpec'), dict) else None
    if spec:
        path_text = spec.get('path')
        if path_text:
            items.extend(_path_evidence_items(Path(str(path_text)), source='requirementsSpec.path'))
        conversion_artifacts = spec.get('conversionArtifacts')
        if isinstance(conversion_artifacts, dict):
            for key, value in sorted(conversion_artifacts.items()):
                if value:
                    items.extend(_path_evidence_items(Path(str(value)), source=f'requirementsSpec.conversionArtifacts.{key}'))
    for path_text in state.get('targetContextFiles') or []:
        if path_text:
            items.extend(_path_evidence_items(Path(str(path_text)), source='targetContextFiles'))
    return items


def _path_evidence_items(path: Path, *, source: str) -> list[tuple[str, str]]:
    try:
        if path.is_dir():
            result: list[tuple[str, str]] = []
            for child in sorted(path.iterdir()):
                if child.name in {'spec.md', 'requirements.md', 'feature.md'} or child.suffix.lower() in {'.md', '.json', '.yaml', '.yml'}:
                    result.extend(_path_evidence_items(child, source=f'{source}:{child.name}'))
                    if result:
                        return result
            return result
        if not path.is_file() or path.suffix.lower() not in {'.md', '.txt', '.json', '.yaml', '.yml'}:
            return []
        text = path.read_text(encoding='utf-8', errors='replace')[:_MAX_SCAN_CHARS]
    except OSError:
        return []
    return [(f'{source}:{path}', line.strip()) for line in text.splitlines() if line.strip()]


def _current_unit(state: dict[str, Any]) -> dict[str, Any] | None:
    unit_id = str(state.get('currentUnitId') or '')
    for unit in state.get('units') or []:
        if isinstance(unit, dict) and str(unit.get('id') or '') == unit_id:
            return unit
    return None


def _visible_surface_labels(items: list[tuple[str, str]]) -> list[str]:
    labels: list[str] = []
    for _source, text in items:
        normalized = _normalize(text)
        if any(pattern.search(normalized) for pattern in _GENERIC_SURFACE_CONTEXT_PATTERNS):
            continue
        if not any(pattern.search(normalized) for pattern in _VISIBLE_SURFACE_PATTERNS):
            continue
        if any(pattern.search(normalized) for pattern in _NO_UI_BASIS_PATTERNS):
            continue
        labels.append(_surface_label(text))
    return _dedupe_strings(labels)[:16]


def _surface_label(text: str) -> str:
    cleaned = re.sub(r'^\s*[-*+]\s*', '', text.strip())
    cleaned = re.sub(r'^\s*\d+[.)、]\s*', '', cleaned)
    cleaned = re.split(r'[：:。.;；]', cleaned, maxsplit=1)[0].strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return _sanitize_snippet(cleaned[:160])


def _classification_snippets(items: list[tuple[str, str]], visible_surfaces: list[str]) -> list[str]:
    snippets = list(visible_surfaces)
    for source, text in items:
        normalized = _normalize(text)
        if any(pattern.search(normalized) for pattern in (*_VISIBLE_SURFACE_PATTERNS, *_NO_UI_BASIS_PATTERNS, *_PROTOTYPE_PATTERNS)):
            snippets.append(f'{source}: {_sanitize_snippet(text[:220])}')
    return snippets


def _evidence_has_any(items: list[tuple[str, str]], patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(_normalize(text)) for _source, text in items for pattern in patterns)


def _positive_evidence_has_any(items: list[tuple[str, str]], patterns: tuple[re.Pattern[str], ...]) -> bool:
    for _source, text in items:
        normalized = _normalize(text)
        if any(pattern.search(normalized) for pattern in _GENERIC_SURFACE_CONTEXT_PATTERNS):
            continue
        if any(pattern.search(normalized) for pattern in _NO_UI_BASIS_PATTERNS):
            continue
        if any(pattern.search(normalized) for pattern in patterns):
            return True
    return False


def _classification_value(*, required: bool, not_required: bool) -> str:
    if required:
        return 'required'
    if not_required:
        return 'not_required'
    return 'unknown'


def _valid_surface_classification(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return all(value.get(field) in CLASSIFICATION_VALUES for field in SURFACE_CLASSIFICATION_FIELDS)


def _stringify(value: Any) -> str:
    if isinstance(value, list):
        return '\n'.join(str(item) for item in value)
    if isinstance(value, dict):
        return '\n'.join(f'{key}: {item}' for key, item in value.items())
    return str(value)


def _sanitize_snippet(text: str) -> str:
    snippet = re.sub(r'\s+', ' ', text).strip()
    snippet = re.sub(r'(?i)(token|password|secret|api[_-]?key|signature|database[_-]?url)\s*[:=]\s*[^,\s)]+', r'\1=<redacted>', snippet)
    snippet = re.sub(r'(?i)([?&](?:token|password|secret|api[_-]?key|signature)=)[^&\s)]+', r'\1<redacted>', snippet)
    return snippet


def _normalize(text: str) -> str:
    compact = text.replace('＝', '=')
    compact = re.sub(r'\s+', ' ', compact.strip().lower())
    compact = compact.replace(' ', '')
    return compact


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _patterns(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)


_VISIBLE_SURFACE_PATTERNS = _patterns(
    r'课程生产中心',
    r'课程草稿详情',
    r'状态回看',
    r'可见产品',
    r'产品入口',
    r'入口',
    r'页面',
    r'详情页?',
    r'控制台',
    r'工作台',
    r'dashboard',
    r'console',
    r'portal',
    r'page',
    r'screen',
    r'route',
    r'browser',
    r'frontend',
    r'webui',
    r'webapp',
)
_UI_SURFACE_PATTERNS = _patterns(
    r'ui/ux',
    r'uiux',
    r'用户界面',
    r'产品交互',
    r'交互样稿',
    r'前端',
    r'页面',
    r'详情页?',
    r'控制台',
    r'工作台',
    r'frontend',
    r'browserui',
    r'webui',
)
_WEB_SURFACE_PATTERNS = _patterns(
    r'页面',
    r'详情页?',
    r'控制台',
    r'工作台',
    r'网页',
    r'browser',
    r'frontend',
    r'web',
    r'route',
    r'dashboard',
    r'console',
    r'portal',
)
_WEB_SYSTEM_PATTERNS = _patterns(
    r'websystem',
    r'web系统',
    r'webapp',
    r'网页系统',
    r'浏览器',
    r'前端',
)
_PROTOTYPE_PATTERNS = _patterns(
    r'prototype',
    r'原型',
    r'交互样稿',
    r'可点击',
)
_NO_UI_BASIS_PATTERNS = _patterns(
    r'纯backend',
    r'纯后端',
    r'backend/api/cli',
    r'api-only',
    r'apionly',
    r'clionly',
    r'cli-only',
    r'无浏览器页面',
    r'没有浏览器页面',
    r'无产品ui',
    r'没有产品ui',
    r'无ui',
    r'没有ui',
    r'不需要ui',
    r'不需要原型',
    r'无需原型',
    r'noui',
    r'withoutui',
    r'nobrowser',
    r'noweb',
    r'headless',
    r'serviceonly',
)
_NO_UI_CLAIM_PATTERNS = _patterns(
    r'不产出产品交互样稿',
    r'不需要ui',
    r'无ui',
    r'没有ui',
    r'不需要原型',
    r'无需原型',
    r'noui',
    r'withoutui',
)
_GENERIC_SURFACE_CONTEXT_PATTERNS = _patterns(
    r'anybrowser-visibleacceptanceisexplicitlyverifiedwhenuistouched',
    r'browser-visibleacceptance.*whenuistouched',
    r'uiistouched',
    r'如果.*涉及ui',
    r'当.*涉及ui',
)
_UNKNOWN_SURFACE_PATTERNS = _patterns(
    r'unknown',
    r'未知',
    r'未识别',
    r'待确认',
    r'需要澄清',
    r'回到scope',
    r'回到productdesign',
)
_CONTROLLER_PERSPECTIVE_PATTERNS = _patterns(
    r'waygate',
    r'controller',
    r'workflowcontroller',
    r'rrc-controller',
    r'stagedpackage',
    r'requirementspackage',
    r'checkpoint',
    r'humangate',
    r'artifacthash',
    r'orchestration',
    r'statetransition',
    r'runnercontract',
    r'操作者体验',
    r'分段流程',
    r'门禁流程',
)
