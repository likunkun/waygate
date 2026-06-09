from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workflow_controller.acceptance_obligations import render_acceptance_obligations_markdown
from workflow_controller.approval_notes import render_approval_notes_context
from workflow_controller.requirements_package import CHECKPOINT_STAGES, REQUIREMENTS_PACKAGE_VERSION
from workflow_controller.steps._common import _find_unit


def _render_unit_plan_draft_prompt(state: dict[str, Any], requirements_path: Path, body_path: Path) -> str:
    requirements_content = ''
    if requirements_path.exists():
        requirements_content = requirements_path.read_text(encoding='utf-8')
    unit = _find_unit(state, state.get('currentUnitId'))
    context_files = '\n'.join(f'- {path}' for path in state.get('targetContextFiles') or [])
    units = json.dumps(state.get('units') or [], ensure_ascii=False, indent=2)
    coverage = json.dumps(state.get('objectiveCoverage') or [], ensure_ascii=False, indent=2)
    obligation_ledger = render_acceptance_obligations_markdown(state)
    obligation_section = ''
    if state.get('acceptanceObligations'):
        obligation_section = f"""
Acceptance Obligation Ledger:

```md
{obligation_ledger}
```

Acceptance Obligation Coverage:
- Every must AO must appear in the Unit Plan coverage matrix.
- Each covered AO must map to at least one test case or manual evidence.
- Do not collapse multiple AO items into one vague closure.
- Keep AO ids such as `AO-001` in Test Case Matrix rows and in `test_cases[].covers_obligations`.
"""
    revision_feedback = state.get('unitPlanRevisionFeedback')
    revision_section = ''
    if revision_feedback:
        revision_section = f"""
已有 Unit Plan 草案及人工批注：

```md
{revision_feedback}
```

请在重新生成的 Markdown 正文中解决这些人工批注。保持 `Controller State Patch` 与人工可读的 Unit Plan 章节一致。
"""
    defect_fix_section = ''
    if state.get('unitPlanRevisionMode') == 'defect_fix' or state.get('finalAcceptanceRejectionRoute') == 'defect_fix':
        defect_fix_section = """
最终验收缺陷修复模式：
- 将最终验收反馈视为已批准需求下的缺陷。
- 不要修改已批准需求，也不要重新解释请求目标。
- 生成一个或多个只聚焦最终验收缺陷的 bug-fix 单元。
- 将受影响的已覆盖目标重新打开为 `partial`，并在 objectiveCoverage 中加入新的 bug-fix unit id。
- 除非必须重新执行，否则已完成单元不要放回 `units`；`units` 应只包含下一步要执行的缺陷修复单元。
- 将 `currentUnitId` 设置为第一个缺陷修复单元。
"""
    staged_requirements_section = _staged_requirements_unit_plan_section(state)
    approval_notes_section = render_approval_notes_context(state, 'requirements')

    return f"""为 workflow-controller 生成"单元计划确认"Markdown 正文。

将 Unit Plan Markdown 正文写入这个精确文件：
{body_path}
Write the Unit Plan Markdown body to this exact file:
{body_path}

使用简体中文展示所有面向人工审阅的标题、说明、表格、清单、证据和验收内容。
保留命令、路径、代码标识符、JSON key、HTTP route、枚举值、文件名和产品名的原文。
控制器状态补丁标题可使用 `## 控制器状态补丁` 或 `## Controller State Patch`，正文必须包含 fenced JSON patch。
不要包含 `## Human Confirmation` 段落；controller 会自动追加确认段落和内容 hash。
不要修改应用源代码；这是规划/门禁文档生成任务。
使用 `test-strategy` skill 将每条验收标准映射到适当验证层级、具体测试用例、命令、fixture、环境和人工证据。

Document Deliverables Matrix 约束：
- 如果当前 unit 会改变长期产品事实、架构事实、运维事实、工作流规则、审批流程、验收流程、证据规则或文档生命周期，必须声明对应文档动作。
- 文档动作优先落到正式 `docs/` 目录：`docs/product/` 记录产品背景、用户旅程和需求说明；`docs/architecture/` 记录技术架构、模块边界和关键设计决策；`docs/workflow/` 记录 Agent 协作、审批流程、验收流程、证据规则和文档生命周期；`docs/operations/` 记录运行、部署、排障和运维说明。
- 纯代码小修可以声明“不需要正式文档变更”，但必须写清楚原因；不能用沉默来表示不需要。
- `Required For Acceptance` 为 `true` 的文档动作会在 Final Acceptance 阻断缺失文件；历史缺失但未声明 required 的文档不作为本 unit 终验阻断。

UI/UX skill policy:
- UI/Web/prototype test case 必须保留 `ui-ux-pro-max` 设计/交互检查；不能只写 `frontend-design` 或泛化“使用设计技能”。
- `frontend-design` 只能作为全新视觉探索或局部视觉润色的可选辅助，不能替代既有产品 UI/原型一致性工作。
- 计划中的 UI/Web/prototype 验证必须覆盖交互、可访问性、布局、遮挡检查，并映射到真实 route、DOM/组件、既有页面结构、截图、历史设计或参考环境。

Verification command script-entry policy:
- `command` 必须是 `scripts/verify/` 下的脚本入口，例如 `bash scripts/verify/<case>.sh`、`sh scripts/verify/<case>.sh`、`python3 scripts/verify/<case>.py`、`python scripts/verify/<case>.py`、`./scripts/verify/<case>.sh` 或 `./scripts/verify/<case>.py`。
- `verification_commands` 只能列脚本入口；每个自动化 test case 的 `command` 必须与其中一个脚本入口精确匹配。
- 脚本内部可以运行 pytest、Playwright、环境准备或多步 shell；Unit Plan 只声明脚本入口和脚本应覆盖的 AC/断言。
- 不要在 Unit Plan 中写 `pytest ...`、`playwright test ...`、`bash -lc`、`python -c`、管道或内联 shell；把这些内容写入 `scripts/verify/<case>.sh` 或 `scripts/verify/<case>.py`。

Unit continuity / handoff policy:
- 多单元 Unit Plan 必须写 `## 单元连贯性摘要`，用人能读懂的话说明每个上游单元给下游单元留下什么可消费成果，以及下游如何消费。
- 多单元 Unit Plan 必须写 `## Handoff Matrix`，列出 Upstream Unit、Downstream Unit、Produced Artifacts / Readiness、Consumed Inputs、Evidence Path、Failure Route。
- Controller State Patch 中有依赖的 unit 必须写 `depends_on`；参与上游/下游交接的 unit 必须写 `handoff.human_summary`、`handoff.produces`、`handoff.requires`、`handoff.ready_checks`、`handoff.evidence_artifacts`。
- `human_summary` 不能只写 “environment ready / 环境就绪 / ready / done”；必须命名具体 artifact、状态或接口。
- 下游 `handoff.requires[]` 必须匹配其 `depends_on` 上游的 `handoff.produces[]`；`ready_checks[]` 必须映射到本 unit 的 test case id、test case command 或 `verification_commands[]`。
- producer unit 的 verifier 会写 `artifacts/<unit-id>/handoff-evidence.json`；下游 Builder 启动前会检查依赖单元的 handoff evidence，缺失或 failed 会以 `blockedContext.category=unit_handoff` 阻止下游执行。

Product Journey Contract 约束：
- 已批准 Requirements、staged Scope/Product Design/Architecture/Test Strategy artifact path/hash/status 是 Product Journey Contract 的事实源；不要从聊天上下文重建用户任务。
- Unit Plan 必须把 Product Journey Contract 展开为 `## 主业务对象血缘拆分矩阵`，按 `主业务对象 -> 起点 -> 状态/事件 -> 成功终点` 拆分每个单元和测试用例。
- 每行必须写 actor、真实用户任务、主业务对象、起点、产生/读取的状态或事件、成功终点、AC/Journey 映射、生产目标、覆盖单元和验证方式。
- fixture、工程层、截图或 prototype artifact 都不能替代产品旅程闭环；它们只能证明准备、辅助视觉或实现细节，不能单独证明真实用户任务闭合。

E2E 单元约束（`workflow_validation_level: closure` 的单元必须遵守）：
- 测试用例矩阵必须以 AC 为主键；每个 test case 必须包含 `id`、`acceptance_criterion`、`layer`、`fixture` 或测试数据准备方式、`command`、`expected`。
- 必须沿用已批准 Requirements `## 4.6` 中的 E2E 方法、真实入口、fixture/setup、命令意图、环境类型、mock policy 和断言意图，并在 Unit Plan 中落成具体 test case、exact command、fixture 初始化脚本和 evidence row；除非创建 Requirements change request 并重新通过 Requirements gate，否则 Unit Plan 不得弱化这些前置审阅结论。
- 如果已批准 requirements 包含 `Design/Architecture Traceability Matrix`，每个 test case 还必须保留对应 AC 的 `product_design_refs` 和 `technical_architecture_refs`，并与 requirements 中的 Product Design Ref / Technical Architecture Ref 一致。
- 如果已批准 requirements 包含 active Journey，closure/E2E test case 必须在 JSON `test_cases[]` 中显式写 Journey 映射字段。推荐使用 `covers_journeys: ["J-001"]` 或 `journey_ids: ["J-001"]`；`journey_refs` / `journeyRefs` 只是历史兼容别名，不作为推荐输出字段。
- Journey 映射不能只放在 Markdown prose、Journey Acceptance Matrix、设计引用或架构引用中；controller 只从 `test_cases[]` 的结构化字段生成 Journey 合约和证据。
- Verifier 会从 test cases 生成 `verification.json` 的 `evidence_rows`；因此每个 test case 的 AC、AO、layer、command/evidence、expected 和 `golden_path` 必须可直接审计。
- 每个浏览器或运行时测试用例必须声明或可推导 `environment_kind`：真实本地 E2E 使用 `local_real`，只读生产验收使用 `production_readonly`；只有 `component_mock` / `contract_mock` / `visual` 辅助测试可以设置 `allows_mock: true` 和 `mocked_routes`。
- `layer=e2e`、`golden_path: true`、`prototype_conformance`、Journey closure 或 Web 系统验收测试不得 mock/stub 核心业务 API。包含 `page.route("**/api/...")`、`route.fulfill()`、mock API server、fixture-only server 或 `route_common(page, ...)` 的浏览器测试只能作为非 E2E 辅助证据，不能覆盖 AC/Journey/golden path/prototype surface。
- `golden_path: true` 必须同时声明 `layer: "e2e"`、`environment_kind: "local_real"` 或 `"production_readonly"`、`entrypoint` 或 `real_entrypoint`、真实 fixture/setup 或 test data、脚本入口 `command`、强 `expected` 断言，并且 `command` 必须出现在 `verification_commands`。
- 真实 E2E 测试必须写 `entrypoint` 或 `real_entrypoint`（真实页面/route/URL/CLI/API/service 入口），并使用真实服务/API 与真实测试数据准备；截图只能作为补充 artifact，不能替代 DOM/API/行为断言。API-only 或 service-only 项目的 golden path 可以使用 pytest/API/service E2E，不要求浏览器。
- 至少一个 E2E test case 必须标记 `golden_path: true`，表示人工最终验收前必须先跑通的核心正常流程。
- closure/Web/UI unit 必须在 Controller State Patch 的对应 unit 中写 `final_acceptance_walkthrough.inspection`，由 Agent 提供人工可见系统走查入口；Controller 不猜入口。字段必须包含 `surface_kind: "browser" | "api" | "cli" | "artifact"`、`entrypoint`、`manual_steps[]` 和 `expected_observations[]`。`manual_steps` 必须是真实系统操作，不得只写 `pytest`、`playwright test`、golden path command 或其他测试命令。
- closure unit 如需最终人工走查启动真实应用，必须同时写 `final_acceptance_walkthrough.launch`：`mode` 只能是 `agent_start` / `manual_only` / `not_required`；`agent_start` 必须写完整 `command`，并至少写一个 `ready_url` / `ready_command` / `ready_output_contains`；`manual_only` 必须写 `manual_launch_instructions`；`env_keys` 只能保存环境变量名，不能保存 secret 值。
- `verification_env` 只能保存真实、可执行、非敏感的环境变量值；secret、外部服务 URL 或只能声明 key 名的变量必须写入 `env_keys`，不要用 `required key name only`、`value must not be recorded` 或 `<...>` 占位值。
- `verification_commands` 必须是可执行脚本入口，并由脚本实际执行 E2E 测试、golden path、环境准备和断言；不接受"截图留证"或人工步骤作为完成条件。
- `done_when` 必须是"测试命令退出码为 0 且断言覆盖 AC"，不接受"截图已上传"、"人工确认"或"浏览器路径已验证"。
- 每个测试用例必须追溯到一条 AC，并在 `expected` 字段中描述可断言的具体值（如字段值、数组长度、排序关系），不接受"页面正常渲染"、"无报错"或"截图留存"作为唯一断言。
- 如果 Requirements 的 prototype manifest 包含 `surface_contracts`，每个 `required: true` surface 的每个 `implementation_targets[]` 必须至少有一个真实生产 UI 一致性测试；相邻弹窗、抽屉或面板的测试不能代替当前 surface。
- 测试用例必须在 Controller State Patch 的 `test_cases[]` 中写 `prototype_conformance: ["<prototype-id>"]`、`prototype_surfaces: ["<surface-id>"]`、`production_targets: ["<route-or-target>"]`、`user_steps[]`，并包含具体 `command` 与非弱断言 `expected`。旧 prototype-level manifest 没有 `surface_contracts` 时仍用 `implementation_targets` 做兼容验收。
- Prototype conformance 的普通 required UI surface 默认 fidelity 合同是 `visual_evidence + structural_interaction`（等同 L1+L2）。关联 active E2E Journey、E2E AC 或 golden-path 候选的 route/page/dialog/drawer/panel/form surface 默认 `screenshot_regression`（L3）。如果 Requirements 或 manifest 明确 `fidelity_required: pixel_exact`，测试用例必须保留同等或更高 fidelity，并声明像素级证据计划。
- 每个 prototype conformance test case 必须包含 `visual_evidence_plan`：`prototype_screenshot`、`production_screenshot`、`viewport`、`entrypoint`、`action_path` 必填；`entrypoint` 必须是真实 production entrypoint，`action_path` 必须覆盖 manifest surface 的 click path；交互 surface 还必须包含 `interaction_screenshot`。L3/L4 必须额外声明 `screenshot_regression`、`pixel_tolerance` 或等价像素断言计划。
- `expected` 不能只写 route/text visible、页面正常或截图留存；必须包含视觉/布局/结构顺序断言和真实点击后的交互断言，并明确检查 fixed header、badge、modal、overlay 等不会遮挡关键控件。
- Prototype conformance E2E 命令必须在 stdout/stderr 输出可解析 marker：`PROTOTYPE_SCREENSHOT: <path>`、`PRODUCTION_SCREENSHOT: <path>`、交互 surface 的 `INTERACTION_SCREENSHOT: <path>`，以及 `VISUAL_EVIDENCE: {{...}}` JSON（至少包含 viewport、entrypoint、action_path、fidelity_level）。
- 浏览器 route/page/dialog/drawer/panel/form/component surface 的 prototype conformance 测试层级必须是 `e2e`，命令必须从真实生产入口打开该 surface（如 Playwright 打开 `/dashboard/teacher` 后点击 `CourseCard -> 分配管理`）；只测试 `requirements-draft/prototypes`、`prototype-review`、`file://...prototype` 或静态 prototype spec，只能证明 artifact 有效，不能算生产 UI 一致性。
- 对不适合 E2E 的 AC，必须说明为什么降级到 unit/functional/integration，并保留可执行命令。
- 使用 `webapp-testing` skill 生成带真实数据断言的 Playwright 测试文件，而不是人工操作步骤清单。

以下已批准需求与验收门禁是事实来源：

```md
{requirements_content}
```

目标：
- 请求目标：`{state.get('requestedOutcome')}`
- 可行目标：`{state.get('feasibleOutcome')}`
- 当前单元 id：`{state.get('currentUnitId')}`
- 当前单元名称：`{unit.get('name', state.get('currentUnitId'))}`

{staged_requirements_section}

{approval_notes_section}

controller state 中的已知目标覆盖：

```json
{coverage}
```

controller state 中的已知单元：

```json
{units}
```

如存在，请读取这些上下文文件：
{context_files or '- None'}

{obligation_section}
{revision_section}
{defect_fix_section}

必须使用以下 Markdown 结构：

# 单元计划确认（Unit Plan Confirmation）

## 目标覆盖矩阵

将每条需求和验收标准映射到一个或多个单元。

## 测试用例矩阵（Test Case Matrix）

创建一张表，表达以下精确映射：

Acceptance Criterion -> Test Case -> Journey -> Layer -> Environment -> Real Entry -> Core API Mock -> Golden Path -> Command/Evidence -> Expected Result

缺陷修复模式下，每条验收标准和每个最终验收缺陷都必须至少有一个具体测试用例或明确人工证据。typecheck/lint/tsc 等静态检查可以出现，但不能单独算作行为覆盖。
E2E 层的测试用例必须有可执行 `command`（`scripts/verify/` 脚本入口），并声明 `fixture` 或测试数据准备方式；`evidence` 字段留空；`expected` 必须描述具体可断言的值，不接受"页面渲染成功"、"无报错"或"截图留存"。
如果测试用例覆盖 Journey，在表格中写出 Journey id，并在 Controller State Patch 的对应 `test_cases[]` JSON 对象中写 `covers_journeys` 或 `journey_ids`。

## 单元连贯性摘要

多单元计划必须用自然语言说明上游单元完成后给下游单元留下什么具体 artifact、状态或 ready condition。单单元计划可写“不涉及跨单元 handoff”。

## Handoff Matrix

多单元计划必须创建一张表，表达以下精确映射：

Upstream Unit -> Downstream Unit -> Produced Artifacts / Readiness -> Consumed Inputs -> Evidence Path -> Failure Route

## 主业务对象血缘拆分矩阵

必须创建一张表，表达以下精确映射：

Actor -> 用户任务 -> 主业务对象 -> 起点 -> 状态/事件 -> 成功终点 -> AC/Journey -> Production Target -> Unit -> Test Case/Evidence

## 文档交付矩阵（Document Deliverables Matrix）

创建一张表，表达以下精确映射：

Area -> Target Path -> Action -> Required For Acceptance -> Evidence / Reason

规则：
- 涉及 `workflow`、`architecture`、`operations`、`product` 长期事实变更时，必须至少有一行说明要创建、更新或登记的正式文档。
- 流程规则变更必须落到 `docs/workflow/`，例如 Agent 协作、审批流程、验收流程、证据规则或文档生命周期。
- 外部 Agent 文档、人工沟通文档或 `.rrc-controller-*` artifact 如需长期使用，先在 `docs/README.md` 登记，再决定是否提升到正式 `docs/*`。
- 纯代码小修可写 `Target Path = 不需要正式文档变更`、`Action = none`、`Required For Acceptance = false`，并在 `Evidence / Reason` 写明原因。
- `Required For Acceptance = true` 只用于本 unit 必须完成的文档动作；不要把历史 backlog 文档缺口标成 required。

## 执行单元

每个单元必须包含：
- 范围
- 非目标
- 覆盖目标
- 覆盖验收标准
- 影响的工作流片段
- 工作流验证层级：`fragment` 或 `closure`
- 完成条件
- 映射到测试用例矩阵的测试用例
- 验证命令
- 命令依赖的验证环境，例如 Playwright/E2E 数据库测试需要的 `DATABASE_URL`
- 所需证据
- 风险

## 控制器状态补丁

包含一个 fenced `json` 对象，controller 会在人工批准后安全应用：

```json
{{
  "currentUnitId": "<first unit to execute>",
  "objectiveCoverage": [
    {{"objective": "<objective>", "units": ["<unit-id>"], "status": "partial"}}
  ],
  "units": [
    {{
      "id": "<unit-id>",
      "name": "<unit name>",
      "passes": false,
      "scope": ["<scope item>"],
      "non_goals": ["<non-goal item>"],
      "done_when": ["<observable completion condition>"],
      "depends_on": ["<upstream unit id, omit or [] for first independent units>"],
      "handoff": {{
        "human_summary": "<具体说明本 unit 产出/消费什么，不得写 environment ready 这类占位语>",
        "produces": ["<artifact/readiness/state this unit makes available to downstream units>"],
        "requires": ["<inputs consumed from depends_on units; [] for first producer units>"],
        "ready_checks": ["<test case id or exact script entry command proving the handoff is ready>"],
        "evidence_artifacts": ["<artifact path such as export.json or reports/schema-ready.json>"]
      }},
      "workflow_validation_level": "fragment",
      "test_cases": [
        {{
          "id": "<stable test case id>",
          "acceptance_criterion": "<criterion or defect covered>",
          "covers_journeys": ["<J-... for closure/e2e journey coverage>"],
          "product_design_refs": ["<Product Design Ref from requirements>"],
          "technical_architecture_refs": ["<Technical Architecture Ref from requirements>"],
          "layer": "unit|functional|integration|e2e|manual",
          "environment_kind": "local_real|production_readonly|component_mock|contract_mock|visual",
          "entrypoint": "<real page route, URL, or command entrypoint>",
          "allows_mock": false,
          "mocked_routes": [],
          "uses_core_api_mock": false,
          "golden_path": true,
          "fixture": "<test data or setup path for runtime tests>",
          "command": "bash scripts/verify/<case>.sh",
          "evidence": "<manual evidence if not automated>",
          "expected": "<observable expected result>",
          "prototype_conformance": ["<prototype id from requirements prototype manifest when applicable>"],
          "prototype_surfaces": ["<surface id from surface_contracts when applicable>"],
          "production_targets": ["<route/page/component target from implementation_targets when applicable>"],
          "fidelity_required": "structural_interaction|screenshot_regression|pixel_exact",
          "user_steps": ["<open real production route>", "<click real entrypoint to open the surface>"],
          "visual_evidence_plan": {{
            "prototype_screenshot": "<baseline prototype screenshot path>",
            "production_screenshot": "<production implementation screenshot path>",
            "interaction_screenshot": "<post-click screenshot path when interactive>",
            "viewport": "<viewport size/device>",
            "entrypoint": "<real production entrypoint>",
            "action_path": ["<open route>", "<click target>"],
            "screenshot_regression": "<required for L3/L4, include threshold or result artifact>",
            "pixel_tolerance": "<required for L4 when pixel_exact>"
          }}
        }}
      ],
      "verification_commands": ["bash scripts/verify/<case>.sh"],
      "verification_env": {{"DATABASE_URL": "file:./tmp/test.db"}},
      "env_keys": ["OPENMAIC_BASE_URL", "OPENMAIC_API_KEY"]
    }}
  ],
  "currentUnitNeedsUiDesign": false,
  "currentUnitIsWebSystem": false
}}
```

JSON 必须合法，且 `units` 必须列出下一步要执行的每个可执行单元。
每个未完成的 `partial` objectiveCoverage unit id 都必须存在于 `units`。
已完成的既有 unit id 如果在 objectiveCoverage 中标记为 `covered`，可以不出现在 `units` 中；这用于同时引用已完成和剩余工作的 rollup objective。
除非必须重新执行，否则不要把已经 covered 的历史单元重新加入 `units`。
如果用更小的可执行单元替换合成 target unit，请从 partial objectiveCoverage 中移除合成 target unit id，或将该 objective 映射到新的可执行 unit id。

## 人工审阅清单

使用未勾选的 Markdown checkbox。
"""


def _staged_requirements_unit_plan_section(state: dict[str, Any]) -> str:
    package = state.get('requirementsPackage')
    if not isinstance(package, dict) or package.get('version') != REQUIREMENTS_PACKAGE_VERSION:
        return ''
    artifacts = package.get('artifacts')
    if not isinstance(artifacts, dict):
        artifacts = {}
    lines = [
        'Staged Requirements Package artifact inheritance:',
        '',
        '| Stage | Path | Hash | Status |',
        '| --- | --- | --- | --- |',
    ]
    for stage in CHECKPOINT_STAGES:
        record = artifacts.get(stage)
        if isinstance(record, dict):
            lines.append(
                f"| {stage} | `{record.get('path')}` | `{record.get('hash')}` | `{record.get('status')}` |"
            )
        else:
            lines.append(f'| {stage} | missing | missing | missing |')
    lines.extend([
        '',
        'Unit Plan 必须从以上 staged artifact path/hash/status 继承 AC、Journey、Product Design、Architecture、Test Strategy、E2E 方法、界面相关义务和风险义务；不要从聊天上下文重建这些事实。',
        'Unit Plan 必须把 Scope/Product Design 中的 Product Journey Contract 作为所有 Agent 的共同事实源，并在 `主业务对象血缘拆分矩阵` 中按主业务对象血缘拆分单元。',
        '',
        'Infrastructure / Execution Context Matrix 约束：',
        '- Unit Plan 必须新增 `Infrastructure / Execution Context Matrix`。',
        '- 矩阵必须覆盖七类事实：代码仓库、项目部署运行时环境、调试分析方法、参考环境、文档地址、架构/交互逻辑/接口说明、依赖信息。',
        '- 每行必须写事实、来源和 Unit Plan 消费方式；环境变量只写 key 名，不写 secret 值。',
    ])
    return '\n'.join(lines)


def _render_test_strategist_prompt(
    *,
    state: dict[str, Any],
    requirements_path: Path,
    unit_plan_body_path: Path,
    draft_dir: Path,
) -> str:
    requirements_content = requirements_path.read_text(encoding='utf-8') if requirements_path.exists() else ''
    unit = _find_unit(state, state.get('currentUnitId'))
    unit_plan_body = unit_plan_body_path.read_text(encoding='utf-8') if unit_plan_body_path.exists() else ''
    return f"""Create Test Strategist artifacts for the workflow-controller Unit Plan draft.

Write these exact artifacts in this directory:
{draft_dir}

Required files:
- test-strategy.json
- test-strategy.md
- unit-plan-gap-report.json
- unit-plan-review-package.json

Use the requirements context, Unit Plan body target path, target context, constraints, and verification requirements below.
Validate every acceptance criterion has at least one concrete behavioral test case or manual evidence.
Reject static-only strategy coverage by reporting a Critical gap.
Do not modify source code.

CRITICAL: test-strategy.json MUST use this exact top-level schema or the controller will reject it:
{{
  "acceptance_criteria": [
    {{
      "id": "AC-X-Y",
      "test_cases": [
        {{
          "id": "TC-X-Y-a",
          "layer": "unit|functional|integration|e2e|manual",
          "command": "script entrypoint under scripts/verify, e.g. bash scripts/verify/<case>.sh",
          "evidence": "manual evidence description (use instead of command for manual cases)",
          "expected": "expected result"
        }}
      ]
    }}
  ]
}}
The top-level key must be "acceptance_criteria" (a list). Each entry must have "id" and "test_cases" (a non-empty list). Each test case must have either "command" or "evidence". Do not rename these keys or wrap them in another structure.

Requirements context:

```md
{requirements_content}
```

Unit Plan body path:
{unit_plan_body_path}

Unit Plan body:

```md
{unit_plan_body}
```

Target context:
- requestedOutcome: {state.get('requestedOutcome')}
- feasibleOutcome: {state.get('feasibleOutcome')}
- currentUnitId: {state.get('currentUnitId')}
- currentUnit: {json.dumps(unit, ensure_ascii=False, indent=2)}
- objectiveCoverage: {json.dumps(state.get('objectiveCoverage') or [], ensure_ascii=False, indent=2)}
- targetContextFiles: {json.dumps(state.get('targetContextFiles') or [], ensure_ascii=False, indent=2)}

Constraints:
- Keep planner and strategist outputs independent.
- Static checks such as lint, typecheck, eslint, prettier, biome, or tsc cannot be the only coverage for an acceptance criterion.
- Prefer user-visible or behavior-visible verification when the requirement has observable runtime behavior.
- For E2E or closure coverage, derive test cases directly from AC IDs and include executable commands plus concrete assertions over real fixture data.
- Use the Product Journey Contract as the shared fact source: each real user task must preserve actor, main business object, task start, state/event lineage, success endpoint, AC/Journey mapping, and production target.
- Flag any strategy that treats fixture, engineering layer, screenshot, or prototype artifact as a substitute for real user task closure.
- Unit Plan commands must be script entrypoints under scripts/verify. Do not suggest direct `pytest ...`, `playwright test ...`, `python -c`, `bash -lc`, pipes, or inline shell as Unit Plan commands.
- Put the direct pytest, Playwright, environment setup, or multi-step shell commands inside the referenced scripts instead.
- Do not use screenshots, page-load checks, or manual observation as the only E2E evidence.
- E2E or closure tests cannot rely only on a fake runner, mock-only flow, or stubbed API-only flow.
- If a proposed E2E or closure test does not use a real application entrypoint, real fixture or setup data, and concrete expected assertions, report a gap.
- controller workflow orchestration tests may use fake runners to validate this controller, but target project feature acceptance cannot treat fake runner output as E2E evidence.
- Use mocks or stubs only for external dependencies the target project cannot control; core user journeys, state changes, data reads and writes, and permission flows must be asserted through real runtime paths.

verification requirements:
- Include test case id, acceptance criterion, layer, fixture or setup data, command or evidence, and expected result.
- Include gap severity as Critical, Major, or Minor.
- Severity guidance: Critical when an AC is marked e2e or closure but has only fake/mock/stubbed/page-load/screenshot evidence.
- Severity guidance: Major when an E2E command exists but fixture, real entrypoint, or expected assertion is unclear.
- Severity guidance: Minor when the command is executable but artifact or evidence references are unclear.
- For every gap, include a "suggested_fix" field with a concrete, actionable instruction for the Planner: specify which AC needs what kind of test, what layer (unit/integration/e2e/manual), and an example scripts/verify entrypoint or evidence format.
- In "suggested_fix", name the script entrypoint and the real test it should run internally, such as Playwright or pytest with fixture data/setup, and the specific expected assertion it must check.
- Summarize review readiness in unit-plan-review-package.json.
"""


def _render_test_strategist_patch_prompt(
    *,
    state: dict[str, Any],
    draft_dir: Path,
    gap_report: dict[str, Any],
) -> str:
    strategy_path = draft_dir / 'test-strategy.json'
    strategy_content = strategy_path.read_text(encoding='utf-8') if strategy_path.exists() else '{}'
    return f"""你是 Test Strategist。初始测试策略存在以下空缺，请直接填补，不要发送反馈。

当前 test-strategy.json 路径：
{strategy_path}

当前 test-strategy.json 内容：
```json
{strategy_content}
```

需要修复的空缺（gap report）：
```json
{json.dumps(gap_report, ensure_ascii=False, indent=2)}
```

操作要求：
1. 对每个 gap，在对应 acceptance_criteria 条目中添加或补全 test_cases。
2. 对每个你【新增或修改】以填补空缺的 test_case，在该对象上加 `"codex_patch": true`。
3. 将完整更新后的 test-strategy.json 写回：{strategy_path}
4. 对原本已有效的 test_case，不要加 `"codex_patch"` 标记。
5. 如果某条 AC 描述过于模糊，你无法生成有意义的测试用例，则保持该 gap 条目不变。
6. 不要修改 unit-plan-gap-report.json 或其他任何文件。
7. 不要修改源代码。

已修补的 test_case 示例结构：
{{
  "id": "TC-X-Y-a",
  "layer": "unit|functional|integration|e2e|manual",
  "command": "具体的 shell 命令",
  "expected": "预期结果",
  "codex_patch": true
}}
"""


def _gap_identifier(gap: dict[str, Any]) -> str:
    return str(gap.get('id') or gap.get('type') or gap.get('message') or 'unknown-critical-gap')


def _render_codex_patch_summary(draft_dir: Path, strategy: dict[str, Any]) -> str:
    patched: list[tuple[str, dict[str, Any]]] = []
    for ac in strategy.get('acceptance_criteria') or []:
        ac_id = ac.get('id') or '?'
        for tc in ac.get('test_cases') or []:
            if tc.get('codex_patch'):
                patched.append((ac_id, tc))
    if not patched:
        return ''
    lines = [
        '',
        '## 📝 Codex Test Strategist 自动补充',
        '',
        '以下测试用例由 Codex 自动填补策略空缺，请确认合理性（不影响后续执行）：',
        '',
    ]
    for ac_id, tc in patched:
        tc_id = tc.get('id') or '?'
        layer = tc.get('layer') or '?'
        cmd = tc.get('command') or tc.get('evidence') or '(no command)'
        expected = tc.get('expected') or ''
        lines.append(f'- **{tc_id}** (AC: {ac_id} · {layer})')
        lines.append(f'  - 命令/证据: `{cmd}`')
        if expected:
            lines.append(f'  - 预期: {expected}')
    return '\n'.join(lines)


def _render_critical_gap_escalation(gaps: list[dict[str, Any]], gap_report: dict[str, Any], *, retry_count: int) -> str:
    lines = [
        '## ⚠️ Unresolved Critical Test Strategy Gaps — Human Review Required',
        '',
        f'Automatic retry exhausted after {retry_count} attempt(s). The following Critical gaps remain unresolved.',
        'Please review, annotate this gate with concrete fixes, and trigger a revision (r).',
        '',
    ]
    for gap in gaps:
        gap_id = _gap_identifier(gap)
        message = str(gap.get('message') or gap.get('type') or 'No detail provided')
        criterion = gap.get('acceptance_criterion') or gap.get('acceptanceCriterion') or gap.get('criterion')
        suffix = f" (AC: {criterion})" if criterion else ''
        lines.append(f'- `Critical` `{gap_id}`{suffix}: {message}')
        fix = gap.get('suggested_fix')
        if fix:
            lines.append(f'  - Suggested fix: {fix}')
    lines.append('')
    return '\n'.join(lines)


def _render_test_strategy_gap_report(gaps: list[dict[str, Any]], gap_report: dict[str, Any], *, retry_count: int) -> str:
    counts = gap_report.get('gap_counts') if isinstance(gap_report.get('gap_counts'), dict) else _gap_counts_from_list(gaps)
    lines = [
        '## Test Strategy Gap Report',
        '',
        f"- Critical: {int(counts.get('critical') or 0)}",
        f"- Major: {int(counts.get('major') or 0)}",
        f"- Minor: {int(counts.get('minor') or 0)}",
        f'- Planner retry count: {retry_count}',
        '',
    ]
    for gap in gaps:
        gap_id = _gap_identifier(gap)
        severity = str(gap.get('severity') or 'Unknown')
        message = str(gap.get('message') or gap.get('type') or 'No detail provided')
        criterion = gap.get('acceptance_criterion') or gap.get('acceptanceCriterion') or gap.get('criterion')
        suffix = f" (AC: {criterion})" if criterion else ''
        lines.append(f'- `{severity}` `{gap_id}`{suffix}: {message}')
        fix = gap.get('suggested_fix')
        if fix:
            lines.append(f'  - Suggested fix: {fix}')
    lines.append('')
    return '\n'.join(lines)


def _render_critical_gap_feedback(gaps: list[dict[str, Any]], next_retry_count: int) -> str:
    lines = [
        '## Critical Test Strategy Gap Feedback',
        '',
        f'Planner retry count after this revision: {next_retry_count}',
        '',
        'Resolve these Critical gaps before the Unit Plan can enter human approval:',
    ]
    for gap in gaps:
        criterion = gap.get('acceptance_criterion') or gap.get('acceptanceCriterion') or gap.get('criterion')
        suffix = f" (AC: {criterion})" if criterion else ''
        lines.append(f"- {_gap_identifier(gap)}{suffix}: {gap.get('message') or gap.get('type') or 'Critical gap'}")
        fix = gap.get('suggested_fix')
        if fix:
            lines.append(f"  Suggested fix: {fix}")
    lines.append('')
    return '\n'.join(lines)


def _gap_counts_from_list(gaps: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {'critical': 0, 'major': 0, 'minor': 0}
    for gap in gaps:
        severity = str(gap.get('severity') or '').lower()
        if severity in counts:
            counts[severity] += 1
    return counts
