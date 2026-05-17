from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from workflow_controller.acceptance_obligations import render_acceptance_obligations_markdown
from workflow_controller.requirements_dialogue_brief import render_requirements_dialogue_brief_prompt_section
from workflow_controller.steps._common import _find_unit


def _markdown_code_fence_for(text: str) -> str:
    longest = 2
    for match in re.finditer(r'`{3,}', text):
        longest = max(longest, len(match.group(0)))
    return '`' * max(3, longest + 1)


def _render_requirements_draft_prompt(state: dict[str, Any], body_path: Path) -> str:
    unit = _find_unit(state, state.get('currentUnitId'))
    context_files = '\n'.join(f'- {path}' for path in state.get('targetContextFiles') or [])
    verification_commands = '\n'.join(
        f"- `{command}`" for command in (unit.get('verification_commands') or state.get('verificationCommands') or [])
    ) or '- Not specified'
    done_when = '\n'.join(f"- {item}" for item in unit.get('done_when') or []) or '- Infer from the target and context files'
    scope = '\n'.join(f"- {item}" for item in unit.get('scope') or []) or '- Infer from the target and context files'
    non_goals = '\n'.join(f"- {item}" for item in unit.get('non_goals') or []) or '- Do not expand beyond the requested target'
    obligation_ledger = render_acceptance_obligations_markdown(state)
    obligation_section = ''
    if state.get('acceptanceObligations'):
        obligation_section = f"""
Acceptance Obligation Ledger:

```md
{obligation_ledger}
```

Every must AO must be covered by at least one Acceptance Criterion, or explicitly deferred/rejected/out_of_scope with reason.
Use the Requirements Traceability Matrix to record that decision for every active must AO.
Do not collapse multiple AO items into one vague requirement.
"""
    revision_feedback = state.get('requirementsRevisionFeedback')
    revision_section = ''
    if revision_feedback:
        revision_fence = _markdown_code_fence_for(str(revision_feedback))
        revision_section = f"""
已有草案及人工批注：

{revision_fence}md
{revision_feedback}
{revision_fence}

Controller 会记录本轮 requirements revision diff artifact；请解决这些反馈，但不要复制审阅评论。
除非审阅意见本身属于最终需求内容，否则不要把审阅者评论原样带入正文。
"""
    dialogue_brief_section = render_requirements_dialogue_brief_prompt_section(state)
    requirements_spec = state.get('requirementsSpec') if isinstance(state.get('requirementsSpec'), dict) else None
    spec_section = ''
    clarification_section = """Agent-side requirements clarification:
- 没有 `--spec` 时，写正式 Requirements Gate 前，必须先提出简洁、集中的澄清问题，并在当前 tmux agent pane 里等待用户回答。
- 第一条回复只能包含澄清问题；不得先读取项目文件、检索代码、生成 Requirements 正文或写入 body_path。
- 等待用户回答期间不得写 `DONE_FILE`；收到用户回答后，再继续生成 Requirements Gate，但该回答必须是具体澄清回答。
- 如果用户只回复「继续」、「按你理解」、「你看着办」或类似非具体回答，不能视为有效澄清回答；必须继续追问或写 blocked DONE_FILE，不能靠保守假设直接生成。
- 用户回答后，将澄清结果写入本 Requirements Gate 的 `## 4.8 已澄清事项、关键假设与待确认风险`，并同步反映到需求、范围外、验收标准和测试策略中。
- 只有收到具体澄清回答后，才可以读取项目上下文并用保守假设补齐非阻断细节；这些假设必须写入 gate。
- 不要因为一般不确定性反复提问；但未完成首次澄清前，不能进入 drafting。
"""
    if requirements_spec:
        spec_section = f"""
Supported Requirements Spec:
- Path: `{requirements_spec.get('path')}`
- Hash: `{requirements_spec.get('hash')}`
- Source type: `{requirements_spec.get('sourceType')}`
- Imported at: `{requirements_spec.get('importedAt')}`

Read the Waygate Markdown spec file at the path above as a requirements fact source.
Because a supported spec is available, do not perform the mandatory agent-side clarification before drafting.
Instead, directly expand Requirements, AO, AC, Journey, Design/Architecture, and Test Strategy matrices from the spec and controller context.
If the spec has ambiguity, record conservative assumptions and review risks in `## 4.8 已澄清事项、关键假设与待确认风险`; only ask a blocking question when no safe assumption exists.
"""
        clarification_section = """Spec-backed requirements drafting:
- Read the Waygate Markdown spec file before writing the Requirements Gate.
- Do not ask mandatory pre-draft clarification questions when the supported spec provides enough facts.
- Directly expand Requirements, AO, AC, Journey, Design/Architecture, and Test Strategy matrices from the spec.
- Record assumptions and review risks in `## 4.8 已澄清事项、关键假设与待确认风险`.
"""
    elif revision_feedback:
        clarification_section = """Requirements revision drafting:
- 这是 Requirements 预检或人工反馈后的修订，不是首次 requirements intake。
- 已有草案、controller validation error、Requirements Dialogue Brief 和 `requirementsRevisionFeedback` 是本轮修订事实源。
- 不要重复询问已有 gate、`## 4.8 已澄清事项、关键假设与待确认风险`、Requirements Dialogue Brief 或 revision feedback 中已经澄清的问题。
- 先复用已有 `## 4.8` 中的已澄清事项；如果修订会改变这些结论，必须在新 gate 中明确写出变化原因。
- 只在当前 controller validation error 或人工反馈无法从已有事实解决时，才提出新的阻断澄清问题并等待用户回答。
- 如果只是补正 controller preflight 错误，例如 AC layer、Journey layer、AO 映射、prototype manifest 或 implementation target，不要向用户重复确认已澄清范围；直接修订 Requirements Gate 和相关 artifact。
- 将新增澄清、沿用澄清和仍需人工确认的风险写入 `## 4.8 已澄清事项、关键假设与待确认风险`。
"""
    infrastructure_intake_section = _target_project_infrastructure_intake_prompt_section(state)

    return f"""为 workflow-controller 生成"需求与验收确认"Markdown 正文。

{clarification_section}

将 Markdown 正文写入这个精确文件：
{body_path}
Write the Markdown body to this exact file:
{body_path}

使用简体中文展示所有面向人工审阅的标题、说明、表格、清单、证据和验收内容。
保留命令、路径、代码标识符、JSON key、HTTP route、枚举值、文件名和产品名的原文。
不要包含 `## Human Confirmation` 段落；controller 会自动追加确认段落和内容 hash。
不要修改应用源代码；这是规划/门禁文档生成任务。
使用 `test-strategy` skill 将每条验收标准映射到适当验证层级、具体测试用例、命令、fixture、环境和人工证据。
Requirements approval 会被 controller 预检：每条 AC 必须声明 verification layer；每个 active must AO 必须映射到 AC，或显式 deferred/rejected/out_of_scope 并写明原因。
V0.3.4 还要求每条 covered AC 在 Design/Architecture Traceability Matrix 中同时映射 Product Design Ref 和 Technical Architecture Ref。
UI/原型设计约束：
- 当生成 prototype evidence、可审阅设计说明或 clickable webpage prototype 时，原型设计默认必须遵循现有系统风格。
- 除非用户或 spec 明确要求创新、重设计或探索新视觉方向，不要引入与现有产品明显不一致的新视觉语言、布局模式或交互范式。
- 必须先从目标项目代码、现有页面、历史设计、截图、文档或参考环境中提取风格基线，并保持信息架构、导航结构、组件形态、视觉密度、颜色/字体/间距、交互模式和文案语气的一致性。
- 如果确实需要偏离现有系统风格，偏离点必须写入 `## 4.8 已澄清事项、关键假设与待确认风险`，并说明偏离原因、影响范围和需要人工确认的风险。

{infrastructure_intake_section}

目标：
- 请求目标：`{state.get('requestedOutcome')}`
- 可行目标：`{state.get('feasibleOutcome')}`
- 当前单元 id：`{state.get('currentUnitId')}`
- 当前单元名称：`{unit.get('name', state.get('currentUnitId'))}`

已知范围：
{scope}

已知非目标：
{non_goals}

已知完成条件 / 验收提示：
{done_when}

已知验证命令：
{verification_commands}

如存在，请读取这些上下文文件：
{context_files or '- None'}

{spec_section}

{dialogue_brief_section}

{obligation_section}
{revision_section}

必须使用以下 Markdown 结构：

# 需求与验收确认

## 1. 需求

## 2. 用户旅程

覆盖正常路径、异常路径、角色/权限路径、重试/恢复路径、持久化/数据路径，以及适用的导入/导出或集成路径。

## 3. 验收标准

使用可观察、可测试的标准。每条标准都要说明可证明它的证据。
每条验收标准必须有稳定 ID（如 `AC-01`、`AC-02`），并描述可观察行为；不要写“体验良好”“流程正常”等不可测试表述。
每条验收标准必须声明 verification layer：unit / functional / integration / e2e / manual，推荐格式：`- AC-01 [verification: e2e]: ...`。
涉及用户可见闭环、数据流、导入导出、列表、状态流转、权限或持久化的 AC，必须包含固定测试数据或 fixture、操作路径、可断言的期望值（如字段值、数量、排序、状态、错误文案、导出内容）。
后续 E2E 必须从这些 AC 生成测试用例，不能用截图或人工观察替代断言。

## 4. 需求可追溯矩阵（Requirements Traceability Matrix）

必须包含这个表头：

| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |

规则：
- 每个 active must AO 必须有一行。
- `covered` 行必须填写 AC ID 和 verification layer。
- 不能在一个模糊 AC 里合并多个 AO；如果多个 AO 共享同一个 AC，也要逐行列出 AO。
- 如果 AO 不进入本版本，Status 必须是 `deferred`、`rejected` 或 `out_of_scope`，并在 Evidence/Reason 写明原因。
- Status 只能使用 covered/deferred/rejected/out_of_scope。
- Verification Layer 只能使用 unit / functional / integration / e2e / manual。

## 4.5 设计与架构可追溯矩阵（Design/Architecture Traceability Matrix）

必须包含这个表头：

| AC | Product Design Ref | Technical Architecture Ref | Notes |
| --- | --- | --- | --- |

规则：
- 每条 covered AC 必须有一行。
- Product Design Ref 必须指向本文件 `## 7. 产品设计概要` 中的具体用户流程、关键页面/状态、API/CLI 输出或产品行为说明。
- Technical Architecture Ref 必须指向本文件 `## 8. 架构概要` 中的具体模块边界、数据流、外部依赖或风险说明。
- 不要使用 `TBD`、`pending`、`待补`、`无` 作为引用值；不确定时应补完整设计/架构概要，而不是让 gate 通过。
- 这一节建立 requirements 层设计/架构引用；Verifier evidence schema 会在验证阶段消费 Unit Plan test cases，并进入最终验收矩阵。

## 4.7 Journey Acceptance Matrix

必须包含这个表头：

| Journey | Title | Status | Steps | AC | Verification Layer | Verification Command | Test Case | Unit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

规则：
- 如果出现 e2e 或 workflow_validation_level=closure，必须至少一行 active Journey。
- Status 只能使用 active / deferred / rejected / out_of_scope。
- active Journey 必须填写 Journey ID、Title、Steps、AC 和 Verification Layer。
- Steps 使用 `->` 分隔关键路径步骤；AC 必须列出关联的 AC ID。
- Verification Layer 只能使用 functional / integration / e2e / manual。
- Verification Command、Test Case、Unit 如尚未由 Unit Plan 生成，可写明预期命令、预期测试用例 ID 或待 Unit Plan 映射的说明。
- 不涉及跨页面、跨模块、端到端或 closure 验收时，可以保留表头并不填写数据行。

## 4.8 已澄清事项、关键假设与待确认风险

记录 agent-side clarification 的结果：
- 已澄清事项：如 agent 在 tmux pane 中向用户提问，必须列出用户回答形成的具体决策。
- 关键假设：列出为避免打断而采用的保守假设，并说明这些假设如何影响需求和验收。
- 待确认风险：列出仍需人工在 gate 审阅时重点确认的风险；不能把阻断性缺口藏在这里。

## 4.9 目标项目基础设施信息

必须覆盖以下 7 类目标项目基础设施信息。每类都必须写具体事实；如果某类确实不涉及，可以写“不涉及”，但必须附具体理由，不能空置或使用 TBD/待补/不清楚等占位内容。

- 代码仓库：
- 项目部署运行时环境：
- 调试分析方法：
- 参考环境：
- 文档地址：
- 架构/交互逻辑/接口说明：
- 依赖信息：

## 5. 测试策略（Test Strategy）

按适用情况区分单元测试、功能/API 测试、集成检查和 E2E/人工验收。

## 6. 范围外

## 7. 产品设计概要

描述核心用户流程（正常路径 + 主要异常路径）、关键页面或系统状态的文字/ASCII 示意；如果没有 UI，就描述 API 响应结构、CLI 输出或关键状态变化；再补充"完成后应该长什么样"的验收示意。

## 8. 架构概要

描述参与本次变更的模块边界与职责划分、核心数据流（输入 → 处理 → 输出）、外部依赖（系统/服务/API/环境），以及主要技术风险和约束。

## 9. 人工审阅清单

使用未勾选的 Markdown checkbox。
"""


def _target_project_infrastructure_intake_prompt_section(state: dict[str, Any]) -> str:
    del state
    return """Target Project Infrastructure Intake Requirements:
- 目标项目基础设施 intake 适用于每个 Waygate 目标项目，不再只服务 V0.6.0 controller 自测目标。
- 本要求不是为 `workflow-controller` 自身补一组运维文档，而是让 Waygate 在处理目标项目时具备梳理目标项目基础设施信息的能力。
- Requirements Gate 必须从目标项目视角澄清基础设施信息，不要把当前仓库文档化作为唯一交付。
- Requirements Gate 必须输出固定审阅段落 `## 4.9 目标项目基础设施信息`。
- 必须覆盖 7 类基础设施信息：代码仓库、项目部署运行时环境、调试分析方法、参考环境、文档地址、架构/交互逻辑/接口说明（即架构、交互逻辑、接口说明）、依赖信息。
- 每类都必须写具体事实；如果某类确实不涉及，可以写“不涉及”，但必须附具体理由，不能空置或使用 TBD/待补/不清楚等占位内容。
- 代码仓库必须回答：当前项目涉及哪些代码库、主仓库、相关仓库、工作区边界、文档目录、生成物和 state-dir 边界。
- 项目部署运行时环境必须覆盖：本地、测试、预发、生产或等价环境、启动方式、服务依赖、外部 API、数据存储、agent runner 和验证运行时前置条件。
- 调试分析方法必须覆盖：日志在哪里、如何查看、基本排查思路、状态文件、运行事件、错误输出、monitor 或 trace 入口。
- 参考环境必须覆盖：竞品、同类产品、历史项目、UI/UX 风格样式、交互参考和访问方式，不能简化成普通运行环境。
- 文档地址必须允许本地 `docs/`、wiki、外部网址、历史项目、设计稿、API 文档、部署文档和排障文档，并说明用途或可信度。
- 架构、交互逻辑、接口说明和依赖信息必须覆盖：模块边界、数据流、用户交互、状态流转、API/CLI/事件接口、错误语义、系统依赖、服务依赖和验证依赖，并能被 Unit Plan 消费。
- 当目标项目需要 UI/UX、包含浏览器可见界面或 `currentUnitNeedsUiDesign=true` 时，Requirements Gate 必须在人工确认前包含 prototype evidence 或可审阅设计说明。
- 当目标项目是 Web 系统时，必须包含可点击、可操作、可在浏览器中使用的 clickable webpage prototype，不接受静态截图、纯文字描述或不可点击线框；必须记录访问方式、页面状态、核心点击路径、AC 映射、真实实现目标和每个可交互 UI surface。
- 当目标项目需要 UI/UX、包含浏览器可见界面、是 Web 系统，或 Requirements 声明原型是 UI/UX 合约时，必须额外写出 `artifacts/requirements-draft/prototype-manifest.json`。该 JSON 必须包含 prototypes 列表；每个条目必须包含 prototype id, type, path or URL, title, linked ACs, linked journeys, page states, click path, implementation_targets, surface_contracts, thumbnail or preview hint, and review guidance。
- `implementation_targets` 是原型到真实生产 UI 的验收映射；每个 target 必须至少包含 `kind` 和 `path`，例如 `{ "kind": "route", "path": "/dashboard/teacher" }`。兼容别名为 `production_targets` / `real_targets`，但推荐输出 `implementation_targets`。
- `surface_contracts` 用于拆分原型中的每个可交互 UI surface，兼容别名 `ui_surfaces` / `page_state_targets`。每个 surface 必须包含 `id`, `title`, `kind`（`route | page | component | dialog | drawer | panel | form | other`）, `page_states[]`, `click_path[]`, `entrypoints[]`, `implementation_targets[]`, `linked_acceptance_criteria[]`, `required: true`。
- 写 manifest 前必须扫描真实生产入口；同一个原型动作如果在真实系统有多个入口，例如批量分配、单课分配管理、弹窗、抽屉、选择器、管理面板、批量操作入口和单项操作入口，必须拆成多个 surface contract。
- 原型是后续 Unit Plan、Verifier 和 Final Acceptance 的 UI 合约；不要求像素级一致，但关键布局、信息架构、可见文案、主要状态和核心交互必须落到真实 route/page。
- `prototype-manifest.json` 中的本地图片或 HTML 原型路径必须是真实文件；外部 URL 不能带 token、password、secret、api_key、signature 等 sensitive URL query；linked ACs 必须引用本 Requirements Gate 中存在的 AC。
- 必须保持 environment/runbook facts、Requirements 和 Unit Plan artifacts 的边界：Requirements Gate 负责明确目标项目需要梳理哪些基础设施事实；Unit Plan 负责决定如何实现；`docs/operations/`、wiki 或外部链接只作为事实来源或落点。
"""
