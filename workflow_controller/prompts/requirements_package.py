from __future__ import annotations

from pathlib import Path
from typing import Any

from workflow_controller.requirements_package import (
    STAGE_LABELS,
    scope_requires_initial_human_clarification,
)
from workflow_controller.requirements_surface import (
    render_requirements_surface_classification_markdown,
)

SUPPORTED_REQUIREMENTS_SPEC_SOURCE_TYPES = {
    'waygate-markdown',
    'openspec',
    'open-spec-package',
    'spec-kit',
}

_FALSE_FLAG_NO_UI_MARKERS = (
    'currentUnitNeedsUiDesign=false',
    'currentUnitIsWebSystem=false',
    'ignored as no-UI evidence',
    'ignored as no-Web evidence',
)

_NO_UI_BASIS_MARKERS = (
    'backend/API/CLI-only',
    'backend api cli only',
    'CLI-only',
    'API-only',
    'no UI/Web/prototype',
    'no-UI/no-prototype',
    'no UI',
    'no Web',
    'no prototype',
    '无 UI',
    '无 Web',
    '无原型',
    '不需要 UI',
    '不需要原型',
)


def render_scope_prompt(state: dict[str, Any], *, output_path: Path) -> str:
    spec_section = _render_requirements_spec_section(state)
    surface_section = render_requirements_surface_classification_markdown(state)
    return f"""生成 {STAGE_LABELS['scope']}，并写入这个精确文件：
{output_path}

使用简体中文。保留命令、路径、JSON key 和代码标识符原文。
本 checkpoint 只负责聚焦需求范围，不展开后续分段的详细内容。

目标：
- 请求目标：`{state.get('requestedOutcome')}`
- 可行目标：`{state.get('feasibleOutcome')}`
- 当前单元：`{state.get('currentUnitId')}`

{spec_section}

{_render_initial_scope_clarification_section(state)}

目标产品表面初步分类：
{surface_section}

{_render_revision_feedback_section(state)}

必须覆盖：
- 需求范围：当前版本要解决的问题、目标、非目标。
- 用户旅程：目标产品/目标系统的正常路径、局部返工路径、失败恢复路径和 legacy 兼容路径。
- 可见产品表面：列出入口、页面、状态回看、详情页、控制台、API/CLI 输出等当前版本可审阅表面；把当前版本需求和后续版本候选分开记录。
- 验收标准：稳定 AC id、verification layer、fixture/setup、可断言 expected。
- Product Journey Contract：按真实用户任务记录 actor、任务起点、主业务对象、关键状态/事件、成功终点、AC/Journey 映射和 production target；这是所有后续 Agent 的共同事实源。
- verification layer 必须是非占位值；常用行为验证层为 unit / functional / integration / e2e / manual，Requirements 辅助类 AC 可使用 static / regression / prerequisite。
- AO traceability：active must AO 的覆盖、延期、拒绝或范围外理由。
- 最小上下文：只记录后续 checkpoint 必须继承的事实、约束和 artifact 入口。
- 风险：需要人工 review 的假设、版本边界和迁移风险。
- 如果 `requirementsSurfaceClassification` 里任一字段是 `unknown`，必须在 Scope 中写明未知原因和下一步；不得静默写“无 UI”。
- 如果分类是 `not_required`，必须说明依据，例如纯 backend/API/CLI 且没有浏览器页面、控制台、详情页或可见入口。
- 如果声明真实 E2E / browser review，Scope 必须映射到 canonical AC 或 Journey：AC 行用 `AC-V04-001 [verification: e2e]`，或 Journey 表使用 exact `Status=active` 与 `Verification Layer=e2e`。示例：`| J-V04-001 | Classroom happy path | active | Open page -> assert persisted status | AC-V04-001 | e2e |`。不要写 `是`、`real integration + DB assertion` 等自然语言值。
- Journey Acceptance Matrix 必须使用 controller 可解析表头：`| Journey | Title | Status | Steps | AC | Verification Layer |`；没有独立标题时 `Title` 可填 Journey ID，`Steps` 用 `->` 分隔关键路径。
- prototype-only artifact review 不触发真实 E2E `## 4.6` 命令校验；它应通过 Product Design prototype manifest 和 Unit Plan prototype conformance 合同承接。

输出必须是 Markdown checkpoint 正文，不要写 Human Confirmation 段落。
"""


def product_design_prompt_contract(state: dict[str, Any]) -> dict[str, Any]:
    spec = state.get('requirementsSpec') if isinstance(state.get('requirementsSpec'), dict) else None
    supported_spec = _requirements_spec_is_supported(spec)
    classification = state.get('requirementsSurfaceClassification')
    if not isinstance(classification, dict):
        classification = {}
    no_ui_basis = _explicit_no_ui_basis_snippets(classification)
    backend_only = (
        classification.get('product_ui') == 'not_required'
        and classification.get('web_system') == 'not_required'
        and classification.get('prototype_required') == 'not_required'
        and bool(no_ui_basis)
    )
    if supported_spec:
        branch = 'supported_spec'
        requires_brainstorming = False
        requires_page_entrypoint_confirmation = False
        requires_no_ui_confirmation = False
    elif backend_only:
        branch = 'backend_api_cli_only'
        requires_brainstorming = False
        requires_page_entrypoint_confirmation = False
        requires_no_ui_confirmation = True
    else:
        branch = 'no_spec_visible_surface'
        requires_brainstorming = True
        requires_page_entrypoint_confirmation = True
        requires_no_ui_confirmation = False
    return {
        'branch': branch,
        'supported_requirements_spec': supported_spec,
        'requires_brainstorming': requires_brainstorming,
        'requires_page_entrypoint_confirmation': requires_page_entrypoint_confirmation,
        'requires_no_ui_confirmation': requires_no_ui_confirmation,
        'no_ui_basis': no_ui_basis,
        'visible_surfaces': list(classification.get('visible_surfaces') or []),
    }


def render_product_design_prompt(state: dict[str, Any], *, output_path: Path) -> str:
    contract = product_design_prompt_contract(state)
    stage_rules = [
        '必须围绕目标产品或目标系统的用户体验，不得设计 Waygate staged package、checkpoint 操作者体验或 controller 人工 gate 流程，除非目标项目本身就是 Waygate/controller。',
        '如果需要 UI/Web/prototype，必须说明原型证据、审阅入口、页面状态、核心点击路径和 AC/Journey 映射。',
        'V0.6.2i 1:1 用户任务原型合同：每个 prototype/surface 必须对应一个真实用户任务，写明 actor、任务起点、点击路径、页面状态、主业务对象、成功终点、AC/Journey 映射和 production target。',
        'prototype artifact 不能替代产品旅程闭环；fixture、工程层、截图或静态原型只能作为辅助证据，不能单独证明真实用户任务从起点到成功终点闭合。',
        '如果确实不需要 UI/原型，必须引用 Scope 中的明确 backend/API/CLI-only 依据。',
    ]
    if contract['branch'] == 'no_spec_visible_surface':
        stage_rules.extend([
            'V0.6.2g no-spec Product Design prompt contract: because no supported `requirementsSpec` is present for this Product Design run, you MUST use the `brainstorming` skill in the same tmux conversation before writing Product Design artifacts.',
            'Confirm one page or entrypoint at a time with the human: purpose, target user, entrypoint, states, interaction path, AC/Journey mapping, prototype expectation, and risk.',
            'Write `product-design-brief.md` and any required `artifacts/requirements-draft/prototype-manifest.json` only after those confirmations; summarize the confirmed pages or entrypoints in the brief when practical.',
        ])
    elif contract['branch'] == 'supported_spec':
        stage_rules.extend([
            'V0.6.2g supported `requirementsSpec` compatibility path: keep the existing staged artifact flow and inherit the spec path/hash/source metadata as the fact source.',
            'Do not add mandatory page-by-page confirmation for supported spec sessions; if the spec already defines surfaces, summarize them directly in `product-design-brief.md` and preserve the staged artifact package.',
        ])
    elif contract['branch'] == 'backend_api_cli_only':
        basis = '; '.join(contract['no_ui_basis']) or 'Scope declares backend/API/CLI-only no UI/Web/prototype basis.'
        stage_rules.extend([
            'V0.6.2g backend/API/CLI-only prompt contract: ask once for an explicit no-UI/no-prototype confirmation instead of page-by-page confirmation.',
            f'Use this positive Scope basis for the confirmation: {basis}',
            'Do not cite default false controller UI/Web flags as the basis; default false flags are not no-UI/no-prototype evidence.',
        ])
    classification = state.get('requirementsSurfaceClassification')
    if isinstance(classification, dict) and (
        classification.get('prototype_required') == 'required'
        or classification.get('web_system') == 'required'
    ):
        manifest_path = output_path.parent.parent / 'requirements-draft' / 'prototype-manifest.json'
        stage_rules.append(
            '因为 `requirementsSurfaceClassification.prototype_required=required` 或 '
            '`web_system=required`，本 checkpoint 必须同时生成 '
            f'`artifacts/requirements-draft/prototype-manifest.json`（精确文件：`{manifest_path}`）。'
        )
        stage_rules.append(
            '`prototype-manifest.json` 必须包含 clickable prototype access method、'
            '`page_states`、`click_path`、`linked_acceptance_criteria`、`linked_journeys`、'
            '`implementation_targets` 和 `surface_contracts`；本地 HTML/图片/Markdown path 必须指向真实文件，'
            '且必须相对 `artifacts/requirements-draft/prototype-manifest.json` 所在目录解析；'
            'URL 不得包含 token/password/secret/api_key/signature 等敏感 query。'
        )
        stage_rules.append(
            '本地原型文件必须先生成或复制到 `artifacts/requirements-draft/prototypes/<prototype-id>/index.html` '
            '或 `artifacts/requirements-draft/` 下的等价 artifact-local 路径，再在 manifest 中写相对路径；'
            '不要写 workspace-relative 的 `docs/prototypes/...`，除非该文件也已经存在于 '
            '`artifacts/requirements-draft/docs/prototypes/...`。'
        )
        stage_rules.append(
            '`prototype-manifest.json` 顶层必须是 JSON object，且必须使用以下 canonical 最小 schema；'
            '按真实目标替换示例值，可以增加 `thumbnail`、`preview_hint` 和 `review_guidance`：\n'
            '```json\n'
            '{\n'
            '  "prototypes": [\n'
            '    {\n'
            '      "id": "course-center",\n'
            '      "type": "html",\n'
            '      "title": "课程生产中心",\n'
            '      "actor": "teacher",\n'
            '      "task_start": "teacher opens /teacher/course-center with one draftable course",\n'
            '      "main_business_object": "course draft",\n'
            '      "success_endpoint": "course draft detail shows generated chapter count and ready status",\n'
            '      "path": "prototypes/course-center/index.html",\n'
            '      "linked_acceptance_criteria": ["AC-07"],\n'
            '      "linked_journeys": ["J-01"],\n'
            '      "page_states": ["入口页", "生成中状态", "草稿详情"],\n'
            '      "click_path": ["打开课程生产中心", "点击生成课程", "查看草稿详情"],\n'
            '      "implementation_targets": [\n'
            '        {"kind": "route", "path": "/teacher/course-center"}\n'
            '      ],\n'
            '      "surface_contracts": [\n'
            '        {\n'
            '          "id": "course-center-page",\n'
            '          "title": "课程生产中心页面",\n'
            '          "kind": "page",\n'
            '          "actor": "teacher",\n'
            '          "task_start": "teacher opens /teacher/course-center",\n'
            '          "main_business_object": "course draft",\n'
            '          "success_endpoint": "draft detail is reachable and shows ready status",\n'
            '          "page_states": ["入口页", "生成中状态", "草稿详情"],\n'
            '          "click_path": ["打开课程生产中心", "点击生成课程", "查看草稿详情"],\n'
            '          "entrypoints": ["/teacher/course-center"],\n'
            '          "implementation_targets": [\n'
            '            {"kind": "route", "path": "/teacher/course-center"}\n'
            '          ],\n'
            '          "linked_acceptance_criteria": ["AC-07"],\n'
            '          "linked_journeys": ["J-01"],\n'
            '          "required": true\n'
            '        }\n'
            '      ]\n'
            '    }\n'
            '  ]\n'
            '}\n'
            '```\n'
            '示例中的 `actor`、`task_start`、`main_business_object` 和 `success_endpoint` 是 required surface 的 controller validator 必填字段，'
            '用于防止示意图冒充产品任务；每个 required `surface_contracts[]` object 都必须声明。\n'
            '不要把 `clickable_prototype_access_method`、`page_states`、`click_path` 写成扁平顶层字段；'
            '这些字段必须位于 `prototypes[]` 的 prototype object 或 `surface_contracts[]` object 内。'
        )
    return _render_downstream_prompt(
        state,
        output_path=output_path,
        title=STAGE_LABELS['product_design'],
        stage_goal='说明目标产品 UX、目标用户如何进入并审阅可见表面、原型/审阅入口证据、页面/状态/详情/API 输出的交互行为。',
        stage_rules=stage_rules,
        upstream_stages=['scope'],
    )


def _requirements_spec_is_supported(spec: dict[str, Any] | None) -> bool:
    if not spec:
        return False
    source_type = str(spec.get('sourceType') or '').strip()
    path = str(spec.get('path') or '').strip()
    return bool(path and source_type in SUPPORTED_REQUIREMENTS_SPEC_SOURCE_TYPES)


def _explicit_no_ui_basis_snippets(classification: dict[str, Any]) -> list[str]:
    snippets = classification.get('evidence_snippets') or []
    result: list[str] = []
    for raw in snippets:
        text = str(raw).strip()
        if not text:
            continue
        if any(marker in text for marker in _FALSE_FLAG_NO_UI_MARKERS):
            continue
        normalized = text.lower()
        if any(marker.lower() in normalized for marker in _NO_UI_BASIS_MARKERS):
            result.append(text)
    return result


def render_architecture_prompt(state: dict[str, Any], *, output_path: Path) -> str:
    return _render_downstream_prompt(
        state,
        output_path=output_path,
        title=STAGE_LABELS['architecture'],
        stage_goal='说明目标系统交互架构、模块边界、API、数据流、状态写入/回看、外部系统调用和运行时依赖。',
        stage_rules=[
            '必须围绕目标系统怎样完成业务交互、数据写入、状态回看和外部系统调用。',
            '不得默认输出 Waygate/controller 编排、runner 合同、checkpoint state transition 或 artifact hash 流程，除非目标项目本身就是 Waygate/controller。',
            '如果 Scope 已声明真实 E2E/browser review，必须引用 Scope 中已有的 canonical e2e AC 或 active e2e Journey，不允许只写自然语言测试策略。',
        ],
        upstream_stages=['scope', 'product_design'],
    )


def render_test_strategy_prompt(state: dict[str, Any], *, output_path: Path) -> str:
    return _render_downstream_prompt(
        state,
        output_path=output_path,
        title=STAGE_LABELS['test_strategy'],
        stage_goal='在策略层说明风险、验证层级、真实 E2E/浏览器/API/service 审阅方法、mock policy 和证据形态。',
        stage_rules=[
            '只写 Requirements 阶段测试策略，不要提前生成 Unit Plan 级别的 exact commands、完整测试用例矩阵或实现任务。',
            '必须继承 Scope/Product Design 的 Product Journey Contract，并按真实用户任务、主业务对象、起点、状态/事件、成功终点来说明测试策略风险。',
            '必须说明哪些风险需要 Unit Plan 承接为 fixtures、commands、assertions 和 evidence rows。',
            '如果 Scope 或本 checkpoint 声明真实 E2E / browser review，必须写固定标题 `## 4.6 E2E 测试方法与前置依赖矩阵（E2E Test Method & Prerequisite Matrix）`，并使用 11 列：`AC / Journey`, `E2E Method`, `Real Entrypoint`, `User Steps`, `Fixture / Test Data / Setup`, `Verification Command`, `Environment Kind`, `Required Env / Dependencies`, `Mock Policy`, `Expected Assertions`, `Human Review Notes`。',
            '`Environment Kind` 只能填写 `local_real` 或 `production_readonly`；`component_mock`、`contract_mock`、`visual` 只能留到 Unit Plan 的辅助非 E2E 测试。',
            '`Real Entrypoint` 必须写真实 route、URL、page、command 或 service entrypoint；`User Steps` 必须写具体用户/API/service 操作步骤；`Fixture / Test Data / Setup` 必须写固定 fixture、测试账号、seed data 或 setup。',
            '`Verification Command` 列填写命令意图、command family 或 runner intent，不写最终 exact command；例如 `Unit Plan must create Go service/API E2E command for services/api real OpenMAIC PDF integration`。只写 `pytest`、`playwright test` 或 `待 Unit Plan 补充` 不合格。',
            '`Mock Policy` 必须声明核心业务 API 不得 mock/stub；只允许说明外部不可控依赖的沙箱、测试账号或只读策略。',
            '`Expected Assertions` 必须写 machine-checkable 断言，例如 DOM/API/数据库/状态/数量/排序/权限/导出内容；截图不能作为唯一断言，只能作为辅助 artifact。',
            '每个 active e2e Journey 至少一行；e2e AC 如果未被 mapped Journey row 覆盖，才需要独立行。不要用 `## 6 E2E / Browser 审阅映射` 或其它标题替代 `## 4.6`。',
            '如果本 checkpoint 复述或补充 Journey 合同，必须使用 controller 可解析表头：`| Journey | Title | Status | Steps | AC | Verification Layer |`；不要只写 prose 或自定义表头。',
        ],
        upstream_stages=['scope', 'product_design', 'architecture'],
    )


def _render_downstream_prompt(
    state: dict[str, Any],
    *,
    output_path: Path,
    title: str,
    stage_goal: str,
    stage_rules: list[str],
    upstream_stages: list[str],
) -> str:
    spec_section = _render_requirements_spec_section(state)
    surface_section = render_requirements_surface_classification_markdown(state)
    rules = '\n'.join(f'- {rule}' for rule in stage_rules)
    return f"""生成 {title}，并写入这个精确文件：
{output_path}

使用简体中文。保留命令、路径、JSON key 和代码标识符原文。

本 checkpoint 目标：
{stage_goal}

{spec_section}

目标产品表面初步分类：
{surface_section}

{_render_revision_feedback_section(state)}

必须读取并继承以下上游 artifact path/hash/status：
{_render_upstream_artifacts(state, upstream_stages)}

要求：
- 不要依赖聊天上下文猜测上游事实；以上游 artifact path/hash 为事实入口。
- 若发现上游事实不足，写入明确风险和需要回到哪个 stage 返工。
{rules}
- 输出必须是 Markdown checkpoint 正文，不要写 Human Confirmation 段落。
"""


def _render_upstream_artifacts(state: dict[str, Any], stages: list[str]) -> str:
    package = state.get('requirementsPackage')
    artifacts = package.get('artifacts') if isinstance(package, dict) else {}
    if not isinstance(artifacts, dict):
        artifacts = {}

    lines = []
    for stage in stages:
        record = artifacts.get(stage)
        if isinstance(record, dict):
            lines.append(
                f"- {STAGE_LABELS.get(stage, stage)} (`{stage}`): path=`{record.get('path')}` hash=`{record.get('hash')}` status=`{record.get('status')}`"
            )
        else:
            lines.append(f'- {STAGE_LABELS.get(stage, stage)} (`{stage}`): missing artifact metadata')
    return '\n'.join(lines)


def _render_revision_feedback_section(state: dict[str, Any]) -> str:
    feedback = str(state.get('requirementsRevisionFeedback') or '').strip()
    if not feedback:
        return 'Controller revision feedback: 无。'
    lines = [
        'Controller revision feedback:',
        '```text',
        feedback,
        '```',
    ]
    normalized = feedback.lower()
    if 'e2e' in normalized or 'browser' in normalized or '4.6' in normalized or '浏览器' in normalized:
        lines.extend([
            '',
            'E2E/browser revision examples:',
            '- Scope canonical Journey: `| J-V04-001 | Classroom happy path | active | Open page -> assert persisted status | AC-V04-001 | e2e |`。',
            '- Test Strategy fixed heading: `## 4.6 E2E 测试方法与前置依赖矩阵（E2E Test Method & Prerequisite Matrix）`。',
            '- 不接受自然语言替代值：`Status=是`、`Verification Layer=real integration + DB assertion`、`## 6 E2E / Browser 审阅映射`。',
        ])
    return '\n'.join(lines)


def _render_initial_scope_clarification_section(state: dict[str, Any]) -> str:
    if not scope_requires_initial_human_clarification(state):
        return ''
    return (
        '无 supported `requirementsSpec` 的 Scope 首轮人工澄清：\n'
        '- 这是无 `--spec` 的 staged Requirements Scope 首轮；`--auto-approve` 不能跳过这一步。\n'
        '- 先在 tmux agent pane 向人工提 1 个需求澄清问题，问题必须同时确认：'
        '当前版本目标、明确非目标、验收重点、成功/失败证据和范围边界、事实来源/文档入口。\n'
        '- 在人工回答前，不要立即读取项目上下文，不要立即写 `requirements-scope.md`，也不要输出 artifact。\n'
        '- 等待人工回答后，再读取 `AGENTS.md`、`ROADMAP.md`、`task_plan.md`、'
        '`progress.md`、`findings.md`、`docs/README.md` 和 Controller state-dir `session.json`，'
        '然后基于人工回答和事实源写 `requirements-scope.md`。\n'
    )


def _render_requirements_spec_section(state: dict[str, Any]) -> str:
    spec = state.get('requirementsSpec') if isinstance(state.get('requirementsSpec'), dict) else None
    if not spec:
        return 'Supported Requirements Spec: 未提供；必须使用目标项目上下文和人工反馈作为事实源。'
    source_type = str(spec.get('sourceType') or '')
    source_instruction = '- 读取上述 spec 或 conversion artifacts，作为目标产品/目标系统事实源；不要只根据 controller 版本或最近聊天推断范围。'
    if source_type == 'open-spec-package':
        source_instruction = '- Path 是 Open Spec package directory；必须读取 package docs 和 conversion artifacts，作为目标产品/目标系统事实源。'
    elif source_type == 'spec-kit':
        source_instruction = '- Path 是 Spec Kit feature package 或 spec.md；必须读取 feature docs 和 conversion artifacts，作为目标产品/目标系统事实源。'
    lines = [
        'Supported Requirements Spec:',
        f"- Path: `{spec.get('path')}`",
        f"- Hash: `{spec.get('hash')}`",
        f"- Source type: `{spec.get('sourceType')}`",
        f"- Imported at: `{spec.get('importedAt')}`",
        source_instruction,
    ]
    conversion_artifacts = spec.get('conversionArtifacts') if isinstance(spec.get('conversionArtifacts'), dict) else None
    if conversion_artifacts:
        for key, value in sorted(conversion_artifacts.items()):
            lines.append(f"- Conversion artifact {key}: `{value}`")
    return '\n'.join(lines)
