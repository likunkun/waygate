from __future__ import annotations

import json
from pathlib import Path

import pytest

from workflow_controller.acceptance_obligations import (
    append_acceptance_obligations,
    render_acceptance_obligations_markdown,
)
from workflow_controller.gates.generators import format_requirements_gate_body
from workflow_controller.gates.validators import validate_requirements_acceptance_quality
from workflow_controller.gates.validators import validate_final_document_deliverables
from workflow_controller.gates.validators import validate_unit_plan_acceptance_obligation_coverage
from workflow_controller.gates.validators import validate_unit_plan_design_architecture_traceability
from workflow_controller.gates.validators import validate_unit_plan_document_deliverables
from workflow_controller.gates.validators import validate_unit_plan_golden_path
from workflow_controller.gates.validators import validate_unit_plan_infrastructure_execution_context_matrix
from workflow_controller.gates.validators import validate_unit_plan_prototype_conformance
from workflow_controller.gates.validators import validate_unit_plan_real_e2e_evidence_policy
from workflow_controller.gates.validators import validate_unit_plan_evidence_row_preflight
from workflow_controller.prototype_review import validate_final_prototype_conformance
from workflow_controller.requirements_package import REQUIREMENTS_PACKAGE_VERSION


def _staged_package_state() -> dict:
    return {
        'requestedOutcome': 'V0.6.2',
        'requirementsPackage': {
            'version': REQUIREMENTS_PACKAGE_VERSION,
            'artifacts': {
                'scope': {'path': '/tmp/scope.md', 'hash': 'scopehash', 'status': 'complete'},
                'product_design': {'path': '/tmp/product.md', 'hash': 'producthash', 'status': 'complete'},
                'architecture': {'path': '/tmp/arch.md', 'hash': 'archhash', 'status': 'complete'},
                'test_strategy': {'path': '/tmp/test.md', 'hash': 'testhash', 'status': 'complete'},
            },
        },
    }


def _write_prototype_manifest_for_gate(
    gate: Path,
    *,
    prototype_type: str = 'html',
    ac: str = 'AC-10',
    url: str = 'http://localhost:4173/prototype',
) -> Path:
    state_root = gate.parent.parent if gate.parent.name == 'approvals' else gate.parent
    draft_dir = state_root / 'artifacts' / 'requirements-draft'
    draft_dir.mkdir(parents=True, exist_ok=True)
    prototype_entry = {
        'id': 'requirements-prototype',
        'type': prototype_type,
        'title': 'Requirements prototype',
        'linked_acceptance_criteria': [ac],
        'linked_journeys': ['J-01'],
        'page_states': ['Dashboard', 'Preview'],
        'click_path': ['Open dashboard', 'Click preview'],
        'implementation_targets': [
            {'kind': 'route', 'path': '/dashboard/preview'},
        ],
        'review_guidance': 'Review the mapped prototype before approving Requirements.',
    }
    if prototype_type == 'url':
        prototype_entry['url'] = url
    else:
        extension = 'html' if prototype_type == 'html' else 'png'
        prototype_path = draft_dir / f'requirements-prototype.{extension}'
        if prototype_type == 'html':
            prototype_path.write_text('<button>Preview</button>\n', encoding='utf-8')
        else:
            prototype_path.write_bytes(b'\x89PNG\r\n\x1a\n')
        prototype_entry['path'] = str(prototype_path)
    manifest_path = draft_dir / 'prototype-manifest.json'
    manifest_path.write_text(
        json.dumps(
            {
                'prototypes': [prototype_entry]
            }
        ),
        encoding='utf-8',
    )
    return manifest_path


def _visual_evidence_plan(
    *,
    prototype: str = 'artifacts/requirements-draft/prototypes/requirements-prototype/baseline.png',
    production: str = 'artifacts/unit-01/screenshots/dashboard-production.png',
    interaction: str = 'artifacts/unit-01/screenshots/dashboard-preview-after-click.png',
    entrypoint: str = '/dashboard/preview',
) -> dict[str, object]:
    return {
        'prototype_screenshot': prototype,
        'production_screenshot': production,
        'interaction_screenshot': interaction,
        'viewport': 'desktop 1440x900',
        'entrypoint': entrypoint,
        'action_path': ['Open the production entrypoint', 'Click Preview'],
    }


def _write_surface_prototype_manifest_for_gate(gate: Path) -> Path:
    state_root = gate.parent.parent if gate.parent.name == 'approvals' else gate.parent
    draft_dir = state_root / 'artifacts' / 'requirements-draft'
    draft_dir.mkdir(parents=True, exist_ok=True)
    prototype_path = draft_dir / 'course-ops.html'
    prototype_path.write_text('<button>发布对象</button><button>分配管理</button>\n', encoding='utf-8')
    manifest_path = draft_dir / 'prototype-manifest.json'
    manifest_path.write_text(
        json.dumps(
            {
                'prototypes': [
                    {
                        'id': 'v291-course-ops-prototype-contract',
                        'type': 'html',
                        'path': str(prototype_path),
                        'title': 'Course ops prototype',
                        'linked_acceptance_criteria': ['AC-21'],
                        'linked_journeys': ['J-01'],
                        'page_states': ['Teacher dashboard'],
                        'click_path': ['Open dashboard'],
                        'implementation_targets': [{'kind': 'route', 'path': '/dashboard/teacher'}],
                        'surface_contracts': [
                            {
                                'id': 'publish-target-dialog',
                                'title': 'Publish target dialog',
                                'kind': 'dialog',
                                'page_states': ['Teacher dashboard', 'Publish target dialog'],
                                'click_path': ['Open dashboard', 'Click 发布对象'],
                                'entrypoints': ['CourseCard -> 发布对象'],
                                'implementation_targets': [
                                    {'kind': 'component', 'path': 'OpenMAIC/components/course/PublishTargetDialog.tsx'}
                                ],
                                'linked_acceptance_criteria': ['AC-21'],
                                'required': True,
                            },
                            {
                                'id': 'assignment-management-dialog',
                                'title': 'Assignment management dialog',
                                'kind': 'dialog',
                                'page_states': ['Teacher dashboard', 'Assign management dialog'],
                                'click_path': ['Open dashboard', 'Click 分配管理'],
                                'entrypoints': ['CourseCard -> 分配管理'],
                                'implementation_targets': [
                                    {'kind': 'component', 'path': 'OpenMAIC/components/course/AssignManageDialog.tsx'}
                                ],
                                'linked_acceptance_criteria': ['AC-21'],
                                'required': True,
                            },
                        ],
                    }
                ]
            }
        ),
        encoding='utf-8',
    )
    return manifest_path


def _write_non_browser_surface_prototype_manifest_for_gate(gate: Path) -> Path:
    state_root = gate.parent.parent if gate.parent.name == 'approvals' else gate.parent
    draft_dir = state_root / 'artifacts' / 'requirements-draft'
    draft_dir.mkdir(parents=True, exist_ok=True)
    prototype_path = draft_dir / 'workflow-review.html'
    prototype_path.write_text('<button>Prompt Contract</button><button>Audit</button>\n', encoding='utf-8')
    manifest_path = draft_dir / 'prototype-manifest.json'
    manifest_path.write_text(
        json.dumps(
            {
                'prototypes': [
                    {
                        'id': 'workflow-review',
                        'type': 'html',
                        'path': str(prototype_path),
                        'title': 'Workflow review prototype',
                        'linked_acceptance_criteria': ['AC-42'],
                        'linked_journeys': [],
                        'page_states': ['Prompt Contract', 'Audit'],
                        'click_path': ['Open artifact', 'Select Prompt Contract', 'Select Audit'],
                        'implementation_targets': [{'kind': 'module', 'path': 'workflow_controller/prompts/requirements_package.py'}],
                        'surface_contracts': [
                            {
                                'id': 'prompt-contract',
                                'title': 'Prompt contract',
                                'kind': 'other',
                                'page_states': ['Prompt Contract'],
                                'click_path': ['Open artifact', 'Select Prompt Contract'],
                                'entrypoints': ['workflow review artifact -> Prompt Contract tab'],
                                'implementation_targets': [
                                    {'kind': 'module', 'path': 'workflow_controller/prompts/requirements_package.py'},
                                    {'kind': 'artifact', 'path': '.rrc-controller-*/artifacts/<role>/runs/<run-id>/'},
                                    {'kind': 'state', 'path': '.rrc-controller-*/session.json'},
                                    {'kind': 'events', 'path': '.rrc-controller-*/events.jsonl'},
                                ],
                                'linked_acceptance_criteria': ['AC-42'],
                                'required': True,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding='utf-8',
    )
    return manifest_path


def _minimal_requirements_gate_with_infrastructure(infrastructure_section: str | None = None) -> str:
    content = (
        '# 需求与验收确认\n\n'
        '## 1. 需求\n'
        '- V1.8.4 需要完成 proxy-collector 运行时修复。\n\n'
        '## 3. 验收标准\n'
        '- AC-01 [verification: functional]: 代理采集服务按目标环境配置启动并通过验证。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| 无 active must AO | AC-01 | covered | functional | 当前没有 active must AO。 |\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-01 | PD-PROXY-01 | TA-PROXY-01 | 目标服务运行和验证。 |\n\n'
        '## 4.8 已澄清事项、关键假设与待确认风险\n'
        '- 已澄清事项：以 proxy-collector 目标项目为事实源。\n'
    )
    if infrastructure_section is not None:
        content += '\n' + infrastructure_section.strip() + '\n'
    return content


def _valid_infrastructure_section() -> str:
    return (
        '## 4.9 目标项目基础设施信息\n'
        '- 代码仓库：主仓库 `/home/lichangkun/code/proxy-collector`，state-dir `.rrc-controller-v1.8.4`。\n'
        '- 项目部署运行时环境：Go service, Makefile, DEB package, systemd unit, local test runtime。\n'
        '- 调试分析方法：查看 systemd journal、SQLite 文件、config 文件、logs 目录和 verifier 输出。\n'
        '- 参考环境：远程部署节点和当前生产服务行为作为参考，不混同本地运行环境。\n'
        '- 文档地址：正式维护文档：`docs/README.md` 作为入口，`docs/operations` 用于部署运行；'
        'Controller 过程证据：`.rrc-controller-v1.8.4/artifacts` 只作审计；'
        '外部 Agent / 人工沟通生成文档：未发现，已检查 `.rrc-controller-v1.8.4/artifacts`；'
        '外部 wiki / 设计稿 / API 文档：deployment runbook 和 packaging notes 作为参考；'
        '缺失但需要沉淀的文档：proxy 运维 runbook 需要后续沉淀。可信度：本地 docs 为维护入口，controller artifacts 为运行证据。\n'
        '- 架构/交互逻辑/接口说明：collector 模块、proxy config flow、CLI/systemd interaction 和 API contract。\n'
        '- 依赖信息：Go toolchain、SQLite、systemd、DEB tooling、network proxy endpoints 和 pytest verifier。\n'
    )


def _valid_requirements_e2e_matrix_section(
    *,
    ac_journey: str = 'AC-01; J-001',
    method: str = 'Playwright browser test in Chromium against local dev server',
    entrypoint: str = '`/orders` production route via `pnpm dev`',
    user_steps: str = 'Open `/orders` -> click `Create order` -> submit item `SKU-123`',
    fixture: str = 'Seed user `teacher@example.test`, order fixture `tests/fixtures/orders/ac-01.json`, run migrations',
    command: str = 'DATABASE_URL=file:./test.db pnpm exec playwright test tests/e2e/orders.spec.ts --project=chromium --grep @AC-01',
    environment_kind: str = 'local_real',
    dependencies: str = '`DATABASE_URL`, local app server on 127.0.0.1:4173, seeded SQLite test DB',
    mock_policy: str = 'No core API mocks; no `page.route("**/api/**")`; external payment API uses test account only',
    assertions: str = 'Assert confirmation id `ORD-1001`, order row count 1, status `Submitted`, and persisted order total `42.00`',
    notes: str = 'Reviewer confirms route, fixture, command, env, mock policy, and assertions before approval',
) -> str:
    return (
        '## 4.6 E2E 测试方法与前置依赖矩阵（E2E Test Method & Prerequisite Matrix）\n'
        '| AC / Journey | E2E Method | Real Entrypoint | User Steps | Fixture / Test Data / Setup | Verification Command | Environment Kind | Required Env / Dependencies | Mock Policy | Expected Assertions | Human Review Notes |\n'
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n'
        f'| {ac_journey} | {method} | {entrypoint} | {user_steps} | {fixture} | `{command}` | {environment_kind} | {dependencies} | {mock_policy} | {assertions} | {notes} |\n'
    )


def _requirements_gate_with_e2e_policy(
    matrix_section: str | None,
    *,
    acceptance_layer: str = 'e2e',
    journey_layer: str = 'e2e',
    test_strategy: str = '- Playwright E2E covers AC-01 with real browser assertions.\n',
) -> str:
    content = (
        '# 需求与验收确认\n\n'
        '## 1. 需求\n'
        '- 用户可以从订单页面创建订单并看到持久化结果。\n\n'
        '## 2. 用户旅程\n'
        '- J-001 订单创建正常路径：打开订单页面 -> 创建订单 -> 查看确认状态。\n\n'
        '## 3. 验收标准\n'
        f'- AC-01 [verification: {acceptance_layer}]: 用户用固定 fixture 创建订单后，页面显示确认号 `ORD-1001`、列表新增 1 条订单并持久化状态 `Submitted`。\n\n'
        '## 4. 需求可追溯矩阵（Requirements Traceability Matrix）\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        f'| 无 active must AO | AC-01 | covered | {acceptance_layer} | E2E browser evidence required. |\n\n'
        '## 4.5 设计与架构可追溯矩阵（Design/Architecture Traceability Matrix）\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-01 | PD-ORDER-01 | TA-ORDER-01 | 订单创建闭环。 |\n\n'
    )
    if matrix_section is not None:
        content += matrix_section.strip() + '\n\n'
    content += (
        '## 4.7 Journey Acceptance Matrix\n'
        '| Journey | Title | Status | Steps | AC | Verification Layer | Verification Command | Test Case | Unit |\n'
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n'
        f'| J-001 | 订单创建正常路径 | active | Open orders -> create order -> see confirmation | AC-01 | {journey_layer} | expected Playwright command | TC-AC-01-E2E | 待 Unit Plan 映射 |\n\n'
        '## 4.8 已澄清事项、关键假设与待确认风险\n'
        '- 已澄清事项：订单创建验收需要真实浏览器路径和固定 fixture。\n\n'
        f'{_valid_infrastructure_section()}\n'
        '## 5. 测试策略（Test Strategy）\n'
        f'{test_strategy}'
    )
    return content


def _valid_nested_infrastructure_section() -> str:
    return (
        '## 4.9 目标项目基础设施信息\n'
        '### 代码仓库\n'
        '主仓库 `/home/lichangkun/code/proxy-collector`，state-dir `.rrc-controller-v1.9.2`。\n'
        '### 项目部署运行时环境\n'
        '- Go service、Makefile、DEB package、systemd unit 和本地测试 runtime。\n'
        '### 调试分析方法\n'
        '- 查看 systemd journal、SQLite 文件、config 文件、logs 目录和 verifier 输出。\n'
        '### 参考环境\n'
        '- 远程部署节点和当前生产服务行为作为参考，不混同本地运行环境。\n'
        '### 文档地址\n'
        '- 正式维护文档：`docs/README.md` 作为入口，`docs/operations` 用于部署运行。\n'
        '- Controller 过程证据：`.rrc-controller-v1.9.2/artifacts` 只作审计证据。\n'
        '- 外部 Agent / 人工沟通生成文档：未发现，已检查 artifacts、chat notes 和 docs registry。\n'
        '- 外部 wiki / 设计稿 / API 文档：deployment runbook 和 packaging notes 作为参考。\n'
        '- 缺失但需要沉淀的文档：proxy 运维 runbook 需要后续沉淀；本地 docs 可信度最高。\n'
        '### 架构、交互逻辑、接口说明\n'
        '- collector 模块、proxy config flow、CLI/systemd interaction 和 API contract。\n'
        '### 依赖信息\n'
        '- Go toolchain、SQLite、systemd、DEB tooling、network proxy endpoints 和 pytest verifier。\n'
    )


def test_requirements_preflight_rejects_missing_target_infrastructure_section(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(_minimal_requirements_gate_with_infrastructure(), encoding='utf-8')

    with pytest.raises(ValueError, match='4\\.9.*目标项目基础设施信息'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_preflight_rejects_missing_infrastructure_category(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    section = _valid_infrastructure_section().replace(
        '- 依赖信息：Go toolchain、SQLite、systemd、DEB tooling、network proxy endpoints 和 pytest verifier。\n',
        '',
    )
    gate.write_text(_minimal_requirements_gate_with_infrastructure(section), encoding='utf-8')

    with pytest.raises(ValueError, match='依赖信息'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_preflight_rejects_placeholder_infrastructure_category(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    section = _valid_infrastructure_section().replace(
        '主仓库 `/home/lichangkun/code/proxy-collector`，state-dir `.rrc-controller-v1.8.4`。',
        'TBD',
    )
    gate.write_text(_minimal_requirements_gate_with_infrastructure(section), encoding='utf-8')

    with pytest.raises(ValueError, match='代码仓库.*placeholder|代码仓库.*占位'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_preflight_accepts_unknown_as_concrete_infrastructure_value(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    section = _valid_infrastructure_section().replace(
        'collector 模块、proxy config flow、CLI/systemd interaction 和 API contract。',
        'collector 模块、proxy config flow、CLI/systemd interaction、API contract、'
        '缺失进程返回 `未知进程`，缺失公网库返回 `public unknown`。',
    )
    gate.write_text(_minimal_requirements_gate_with_infrastructure(section), encoding='utf-8')

    validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.9.2'})


def test_requirements_preflight_accepts_complete_target_infrastructure_section(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        _minimal_requirements_gate_with_infrastructure(_valid_infrastructure_section()),
        encoding='utf-8',
    )

    validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_preflight_accepts_infrastructure_section_with_nested_headings(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        _minimal_requirements_gate_with_infrastructure(_valid_nested_infrastructure_section()),
        encoding='utf-8',
    )

    validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.9.2'})


def test_requirements_preflight_rejects_vague_docs_directory_reference(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    section = _valid_infrastructure_section().replace(
        '正式维护文档：`docs/README.md` 作为入口，`docs/operations` 用于部署运行；'
        'Controller 过程证据：`.rrc-controller-v1.8.4/artifacts` 只作审计；'
        '外部 Agent / 人工沟通生成文档：未发现，已检查 `.rrc-controller-v1.8.4/artifacts`；'
        '外部 wiki / 设计稿 / API 文档：deployment runbook 和 packaging notes 作为参考；'
        '缺失但需要沉淀的文档：proxy 运维 runbook 需要后续沉淀。可信度：本地 docs 为维护入口，controller artifacts 为运行证据。',
        'docs/',
    )
    gate.write_text(_minimal_requirements_gate_with_infrastructure(section), encoding='utf-8')

    with pytest.raises(ValueError, match='文档地址.*空泛|文档地址.*vague'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_preflight_rejects_vague_readme_usage_reference(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    section = _valid_infrastructure_section().replace(
        '正式维护文档：`docs/README.md` 作为入口，`docs/operations` 用于部署运行；'
        'Controller 过程证据：`.rrc-controller-v1.8.4/artifacts` 只作审计；'
        '外部 Agent / 人工沟通生成文档：未发现，已检查 `.rrc-controller-v1.8.4/artifacts`；'
        '外部 wiki / 设计稿 / API 文档：deployment runbook 和 packaging notes 作为参考；'
        '缺失但需要沉淀的文档：proxy 运维 runbook 需要后续沉淀。可信度：本地 docs 为维护入口，controller artifacts 为运行证据。',
        'README、USAGE',
    )
    gate.write_text(_minimal_requirements_gate_with_infrastructure(section), encoding='utf-8')

    with pytest.raises(ValueError, match='文档地址.*README|文档地址.*空泛|文档地址.*vague'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_preflight_rejects_docs_address_none_placeholder(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    section = _valid_infrastructure_section().replace(
        '正式维护文档：`docs/README.md` 作为入口，`docs/operations` 用于部署运行；'
        'Controller 过程证据：`.rrc-controller-v1.8.4/artifacts` 只作审计；'
        '外部 Agent / 人工沟通生成文档：未发现，已检查 `.rrc-controller-v1.8.4/artifacts`；'
        '外部 wiki / 设计稿 / API 文档：deployment runbook 和 packaging notes 作为参考；'
        '缺失但需要沉淀的文档：proxy 运维 runbook 需要后续沉淀。可信度：本地 docs 为维护入口，controller artifacts 为运行证据。',
        '暂无',
    )
    gate.write_text(_minimal_requirements_gate_with_infrastructure(section), encoding='utf-8')

    with pytest.raises(ValueError, match='文档地址.*placeholder|文档地址.*vague|文档地址.*空泛'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_preflight_rejects_unclear_runtime_environment(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    section = _valid_infrastructure_section().replace(
        'Go service, Makefile, DEB package, systemd unit, local test runtime。',
        '不清楚',
    )
    gate.write_text(_minimal_requirements_gate_with_infrastructure(section), encoding='utf-8')

    with pytest.raises(ValueError, match='项目部署运行时环境.*placeholder|项目部署运行时环境.*占位'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_preflight_accepts_missing_external_agent_docs_after_checked_sources(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    section = _valid_infrastructure_section().replace(
        '外部 Agent / 人工沟通生成文档：未发现，已检查 `.rrc-controller-v1.8.4/artifacts`；',
        '外部 Agent / 人工沟通生成文档：未发现，但已检查 `.rrc-controller-v1.8.4/artifacts`、chat notes 和 docs registry；',
    )
    gate.write_text(_minimal_requirements_gate_with_infrastructure(section), encoding='utf-8')

    validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_preflight_accepts_missing_external_docs_after_checked_sources(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    section = _valid_infrastructure_section().replace(
        '外部 wiki / 设计稿 / API 文档：deployment runbook 和 packaging notes 作为参考；',
        '外部 wiki / 设计稿 / API 文档：未发现，已检查 docs/、README、.rrc-controller-*/artifacts；',
    )
    gate.write_text(_minimal_requirements_gate_with_infrastructure(section), encoding='utf-8')

    validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_preflight_rejects_missing_infrastructure_fact_without_checked_source_or_reason(
    tmp_path: Path,
) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    section = _valid_infrastructure_section().replace(
        '远程部署节点和当前生产服务行为作为参考，不混同本地运行环境。',
        '未发现。',
    )
    gate.write_text(_minimal_requirements_gate_with_infrastructure(section), encoding='utf-8')

    with pytest.raises(ValueError, match='参考环境.*未发现.*已检查|参考环境.*用户确认|参考环境.*reason'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_preflight_accepts_user_confirmed_absent_external_docs_with_qa_record(
    tmp_path: Path,
) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    section = _valid_infrastructure_section().replace(
        '外部 wiki / 设计稿 / API 文档：deployment runbook 和 packaging notes 作为参考；',
        '外部 wiki / 设计稿 / API 文档：用户确认当前没有外部 wiki/API 文档；',
    )
    content = _minimal_requirements_gate_with_infrastructure(section).replace(
        '- 已澄清事项：以 proxy-collector 目标项目为事实源。',
        '- 追问：目标项目是否存在外部 wiki、设计稿或 API 文档？\n'
        '- 用户回答：当前没有外部 wiki/API 文档。\n'
        '- 核对方式：已检查 docs/README.md、README、.rrc-controller-v1.8.4/artifacts，未发现外部链接登记。\n'
        '- 验证结论：用户确认当前没有外部 wiki/API 文档；本地检查未发现可直接验证的外部文档入口。',
    )
    gate.write_text(content, encoding='utf-8')

    validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_preflight_rejects_user_confirmed_fact_without_qa_record(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    section = _valid_infrastructure_section().replace(
        '外部 wiki / 设计稿 / API 文档：deployment runbook 和 packaging notes 作为参考；',
        '外部 wiki / 设计稿 / API 文档：用户确认当前没有外部 wiki/API 文档；',
    )
    gate.write_text(_minimal_requirements_gate_with_infrastructure(section), encoding='utf-8')

    with pytest.raises(ValueError, match='4\\.8.*用户确认|4\\.8.*问答'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_preflight_rejects_verified_infrastructure_fact_without_validation_record(
    tmp_path: Path,
) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    section = _valid_infrastructure_section().replace(
        '主仓库 `/home/lichangkun/code/proxy-collector`，state-dir `.rrc-controller-v1.8.4`。',
        '主仓库 `/home/lichangkun/code/proxy-collector`，已验证存在 state-dir `.rrc-controller-v1.8.4`。',
    )
    gate.write_text(_minimal_requirements_gate_with_infrastructure(section), encoding='utf-8')

    with pytest.raises(ValueError, match='4\\.8.*验证方式|4\\.8.*验证结论'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_preflight_rejects_empty_nested_infrastructure_category(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    section = _valid_nested_infrastructure_section().replace(
        '### 代码仓库\n'
        '主仓库 `/home/lichangkun/code/proxy-collector`，state-dir `.rrc-controller-v1.9.2`。\n',
        '### 代码仓库\n',
    )
    gate.write_text(_minimal_requirements_gate_with_infrastructure(section), encoding='utf-8')

    with pytest.raises(ValueError, match='代码仓库.*placeholder|代码仓库.*占位'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.9.2'})


def test_requirements_summary_prototype_review_reminder_is_not_ui_contract(tmp_path: Path) -> None:
    state = {
        'requestedOutcome': 'V1.8.4',
        'feasibleOutcome': 'V1.8.4',
        'currentUnitId': 'target-v1-8-4',
        'currentUnitNeedsUiDesign': False,
        'currentUnitIsWebSystem': False,
    }
    gate = tmp_path / 'requirements-and-acceptance.md'
    body = format_requirements_gate_body(
        state,
        _minimal_requirements_gate_with_infrastructure(_valid_infrastructure_section()),
    )
    assert 'clickable webpage prototype' in body

    gate.write_text(body, encoding='utf-8')

    validate_requirements_acceptance_quality(gate, state)


def test_plannotator_annotations_become_distinct_acceptance_obligations() -> None:
    state: dict = {}

    append_acceptance_obligations(
        state,
        source='plannotator_feedback',
        source_ref='unit-plan:revision-1',
        feedback_text='Reviewer submitted three annotations.',
        annotations=[
            {'quote': 'Step 5', 'comment': '模型选择不清楚'},
            {'quote': 'Materials', 'comment': '15 个材料没有逐项证明'},
            {'quote': 'i18n', 'comment': '英文 locale 下仍有中文文案'},
        ],
    )

    obligations = state['acceptanceObligations']
    assert [item['id'] for item in obligations] == ['AO-001', 'AO-002', 'AO-003']
    assert [item['title'] for item in obligations] == [
        '模型选择不清楚',
        '15 个材料没有逐项证明',
        '英文 locale 下仍有中文文案',
    ]
    assert all(item['priority'] == 'must' for item in obligations)
    assert all(item['status'] == 'open' for item in obligations)
    assert obligations[0]['sourceRef'] == 'unit-plan:revision-1'
    assert 'Step 5' in obligations[0]['description']


def test_numbered_feedback_becomes_distinct_acceptance_obligations() -> None:
    state: dict = {}

    append_acceptance_obligations(
        state,
        source='human_feedback',
        source_ref='final-acceptance:rejection-1',
        feedback_text='''
1. 六步 UX 不清楚，用户不知道当前在哪一步。
2. 15 个材料没有完整覆盖。
3. i18n 不完整，按钮仍有英文。
''',
    )

    obligations = state['acceptanceObligations']
    assert [item['id'] for item in obligations] == ['AO-001', 'AO-002', 'AO-003']
    assert [item['title'] for item in obligations] == [
        '六步 UX 不清楚，用户不知道当前在哪一步。',
        '15 个材料没有完整覆盖。',
        'i18n 不完整，按钮仍有英文。',
    ]


def test_plannotator_plain_file_feedback_becomes_distinct_acceptance_obligations() -> None:
    state: dict = {}

    append_acceptance_obligations(
        state,
        source='requirements_feedback',
        source_ref='requirements:revision-1',
        feedback_text='''
# File Feedback
I've reviewed this file and have 2 pieces of feedback:

## 1. General feedback about the file
> 这个需求就是瞎扯淡

## 2. General feedback about the file
> 这才是我要的需求：
> - 默认只展示 changed / added / removed。
> - 增加一个轻量开关：显示相同项，默认关闭。
''',
    )

    obligations = state['acceptanceObligations']
    assert [item['id'] for item in obligations] == ['AO-001', 'AO-002']
    assert [item['title'] for item in obligations] == [
        '这个需求就是瞎扯淡',
        '这才是我要的需求：',
    ]
    assert '默认只展示 changed / added / removed。' in obligations[1]['description']


def test_acceptance_obligation_markdown_preserves_original_items() -> None:
    state = {
        'acceptanceObligations': [
            {
                'id': 'AO-001',
                'title': '六步 UX 不清楚',
                'description': '用户不知道当前在哪一步。',
                'source': 'human_feedback',
                'sourceRef': 'final-acceptance:rejection-1',
                'priority': 'must',
                'status': 'open',
                'ownerStage': 'requirements',
                'mappedAcceptanceCriteria': [],
                'mappedUnits': [],
                'mappedTestCases': [],
                'evidence': [],
            }
        ]
    }

    markdown = render_acceptance_obligations_markdown(state)

    assert '# Acceptance Obligation Ledger' in markdown
    assert '## AO-001: 六步 UX 不清楚' in markdown
    assert '用户不知道当前在哪一步。' in markdown
    assert 'Mapped Test Cases: pending' in markdown


def test_unit_plan_approval_blocks_missing_acceptance_obligation_coverage(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Test Case Matrix\n'
        '| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AC-1 covers AO-001 | TC-1 | integration | pytest tests/test_a.py -q | AO-001 works |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
            {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
        ],
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-1',
                        'acceptance_criterion': 'AC-1',
                        'covers_obligations': ['AO-001'],
                        'layer': 'integration',
                        'command': 'pytest tests/test_a.py -q',
                        'expected': 'AO-001 works',
                    }
                ],
                'verification_commands': ['pytest tests/test_a.py -q'],
            }
        ],
    }

    with pytest.raises(ValueError, match='AO-002'):
        validate_unit_plan_acceptance_obligation_coverage(gate, state)


def test_unit_plan_approval_does_not_count_copied_ledger_as_coverage(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Acceptance Obligation Ledger\n'
        '## AO-001: 六步 UX 不清楚\n'
        '## AO-002: 15 个材料没有覆盖\n\n'
        '## Test Case Matrix\n'
        '| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AC-1 covers AO-001 | TC-1 | integration | pytest tests/test_a.py -q | AO-001 works |\n'
        'AO-002 still needs work.\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
            {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
        ],
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-1',
                        'acceptance_criterion': 'AC-1',
                        'covers_obligations': ['AO-001'],
                        'layer': 'integration',
                        'command': 'pytest tests/test_a.py -q',
                        'expected': 'AO-001 works',
                    }
                ],
                'verification_commands': ['pytest tests/test_a.py -q'],
            }
        ],
    }

    with pytest.raises(ValueError, match='AO-002'):
        validate_unit_plan_acceptance_obligation_coverage(gate, state)


def test_unit_plan_approval_passes_when_all_must_obligations_are_covered(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Test Case Matrix\n'
        '| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AC-1 covers AO-001 | TC-1 | integration | pytest tests/test_a.py -q | AO-001 works |\n'
        '| AC-2 covers AO-002 | TC-2 | e2e | pnpm playwright test material.spec.ts | AO-002 works |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
            {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
        ],
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-1',
                        'acceptance_criterion': 'AC-1',
                        'covers_obligations': ['AO-001'],
                        'layer': 'integration',
                        'command': 'pytest tests/test_a.py -q',
                        'expected': 'AO-001 works',
                    },
                    {
                        'id': 'TC-2',
                        'acceptance_criterion': 'AC-2',
                        'covers_obligations': ['AO-002'],
                        'layer': 'e2e',
                        'command': 'pnpm playwright test material.spec.ts',
                        'expected': 'AO-002 works',
                    },
                ],
                'verification_commands': [
                    'pytest tests/test_a.py -q',
                    'pnpm playwright test material.spec.ts',
                ],
            }
        ],
    }

    validate_unit_plan_acceptance_obligation_coverage(gate, state)


def test_unit_plan_golden_path_rejects_non_e2e_layer() -> None:
    state = {
        'units': [
            {
                'id': 'unit-api',
                'passes': False,
                'workflow_validation_level': 'closure',
                'test_cases': [
                    {
                        'id': 'TC-API-GOLDEN',
                        'acceptance_criterion': 'AC-01',
                        'layer': 'integration',
                        'golden_path': True,
                        'environment_kind': 'local_real',
                        'real_entrypoint': 'POST /api/orders',
                        'fixture': 'tests/fixtures/order.json',
                        'command': 'pytest tests/integration/test_orders.py -q',
                        'expected': 'assert response.status_code == 201 and response.json()["id"] is present',
                    }
                ],
                'verification_commands': ['pytest tests/integration/test_orders.py -q'],
            }
        ]
    }

    with pytest.raises(ValueError, match='layer=e2e'):
        validate_unit_plan_golden_path(state)


def test_unit_plan_golden_path_rejects_missing_real_entrypoint() -> None:
    state = {
        'units': [
            {
                'id': 'unit-api',
                'passes': False,
                'workflow_validation_level': 'closure',
                'test_cases': [
                    {
                        'id': 'TC-API-GOLDEN',
                        'acceptance_criterion': 'AC-01',
                        'layer': 'e2e',
                        'golden_path': True,
                        'environment_kind': 'local_real',
                        'fixture': 'tests/fixtures/order.json',
                        'command': 'pytest tests/e2e/test_orders_api.py -q',
                        'expected': 'assert response.status_code == 201 and response.json()["status"] == "created"',
                    }
                ],
                'verification_commands': ['pytest tests/e2e/test_orders_api.py -q'],
            }
        ]
    }

    with pytest.raises(ValueError, match='real_entrypoint'):
        validate_unit_plan_golden_path(state)


def test_unit_plan_golden_path_rejects_mock_environment_kind() -> None:
    state = {
        'units': [
            {
                'id': 'unit-api',
                'passes': False,
                'workflow_validation_level': 'closure',
                'test_cases': [
                    {
                        'id': 'TC-API-GOLDEN',
                        'acceptance_criterion': 'AC-01',
                        'layer': 'e2e',
                        'golden_path': True,
                        'environment_kind': 'component_mock',
                        'real_entrypoint': 'POST /api/orders',
                        'fixture': 'tests/fixtures/order.json',
                        'command': 'pytest tests/e2e/test_orders_api.py -q',
                        'expected': 'assert response.status_code == 201 and response.json()["status"] == "created"',
                    }
                ],
                'verification_commands': ['pytest tests/e2e/test_orders_api.py -q'],
            }
        ]
    }

    with pytest.raises(ValueError, match='environment_kind'):
        validate_unit_plan_golden_path(state)


def test_unit_plan_accepts_api_only_e2e_golden_path(tmp_path: Path) -> None:
    requirements = tmp_path / 'requirements-and-acceptance.md'
    requirements.write_text(
        '# Requirements & Acceptance Confirmation\n\n'
        '## 3. Acceptance Criteria\n'
        '- AC-01 [verification: e2e]: API creates an order through the real service endpoint.\n\n'
        '## 4.6 E2E Test Method & Prerequisite Matrix\n'
        '| AC/Journey | E2E Method | Real Entrypoint | User Steps | Fixture / Test Data / Setup | Verification Command | Environment Kind | Dependencies | Mock Policy | Expected Assertions | Notes |\n'
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n'
        '| AC-01 | pytest API/service E2E | POST /api/orders | POST a real order payload and fetch created order | tests/fixtures/order.json seeded into local service DB | `pytest tests/e2e/test_orders_api.py -q` | local_real | local API service and test database | no core API mocks | assert status_code == 201 and persisted order status == created | API-only system, no browser required |\n',
        encoding='utf-8',
    )
    state = {
        'units': [
            {
                'id': 'unit-api',
                'passes': False,
                'workflow_validation_level': 'closure',
                'test_cases': [
                    {
                        'id': 'TC-API-GOLDEN',
                        'acceptance_criterion': 'AC-01',
                        'layer': 'e2e',
                        'golden_path': True,
                        'environment_kind': 'local_real',
                        'real_entrypoint': 'POST /api/orders',
                        'uses_core_api_mock': False,
                        'mocked_routes': [],
                        'fixture': 'tests/fixtures/order.json and local service DB seed',
                        'command': 'pytest tests/e2e/test_orders_api.py -q',
                        'expected': 'assert response.status_code == 201 and persisted order status == created',
                    }
                ],
                'verification_commands': ['pytest tests/e2e/test_orders_api.py -q'],
            }
        ]
    }

    validate_unit_plan_golden_path(state)
    validate_unit_plan_real_e2e_evidence_policy(requirements, state)


def test_unit_plan_requires_e2e_case_for_e2e_acceptance_criterion(tmp_path: Path) -> None:
    requirements = tmp_path / 'requirements-and-acceptance.md'
    requirements.write_text(
        '# Requirements & Acceptance Confirmation\n\n'
        '## 3. Acceptance Criteria\n'
        '- AC-01 [verification: e2e]: API creates an order through the real service endpoint.\n\n'
        '## 4.6 E2E Test Method & Prerequisite Matrix\n'
        '| AC/Journey | E2E Method | Real Entrypoint | User Steps | Fixture / Test Data / Setup | Verification Command | Environment Kind | Dependencies | Mock Policy | Expected Assertions | Notes |\n'
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n'
        '| AC-01 | pytest API/service E2E | POST /api/orders | POST a real order payload and fetch created order | tests/fixtures/order.json seeded into local service DB | `pytest tests/e2e/test_orders_api.py -q` | local_real | local API service and test database | no core API mocks | assert status_code == 201 and persisted order status == created | API-only system, no browser required |\n',
        encoding='utf-8',
    )
    state = {
        'units': [
            {
                'id': 'unit-api',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-API-INTEGRATION',
                        'acceptance_criterion': 'AC-01',
                        'layer': 'integration',
                        'environment_kind': 'local_real',
                        'real_entrypoint': 'POST /api/orders',
                        'fixture': 'tests/fixtures/order.json',
                        'command': 'pytest tests/integration/test_orders.py -q',
                        'expected': 'assert order repository writes status created',
                    }
                ],
                'verification_commands': ['pytest tests/integration/test_orders.py -q'],
            }
        ]
    }

    with pytest.raises(ValueError, match='AC-01'):
        validate_unit_plan_real_e2e_evidence_policy(requirements, state)


def test_unit_plan_evidence_row_preflight_rejects_aggregate_command() -> None:
    state = {
        'units': [
            {
                'id': 'unit-api',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-API-ONE',
                        'acceptance_criterion': 'AC-01',
                        'layer': 'functional',
                        'command': 'python3 -m pytest tests/test_api.py::test_one -q',
                        'expected': 'first API behavior passes',
                    },
                    {
                        'id': 'TC-API-TWO',
                        'acceptance_criterion': 'AC-02',
                        'layer': 'functional',
                        'command': 'python3 -m pytest tests/test_api.py::test_two -q',
                        'expected': 'second API behavior passes',
                    },
                ],
                'verification_commands': ['python3 -m pytest tests/test_api.py -q'],
            }
        ]
    }

    with pytest.raises(ValueError) as exc:
        validate_unit_plan_evidence_row_preflight(state)

    message = str(exc.value)
    assert 'TC-API-ONE' in message
    assert 'TC-API-TWO' in message
    assert 'exactly match verification_commands' in message


def test_unit_plan_evidence_row_preflight_accepts_exact_commands() -> None:
    command = 'python3 -m pytest tests/test_api.py::test_one -q'
    state = {
        'units': [
            {
                'id': 'unit-api',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-API-ONE',
                        'acceptance_criterion': 'AC-01',
                        'layer': 'functional',
                        'command': command,
                        'expected': 'first API behavior passes',
                    }
                ],
                'verification_commands': [command],
            }
        ]
    }

    validate_unit_plan_evidence_row_preflight(state)


def test_unit_plan_evidence_row_preflight_allows_verification_assist_without_command() -> None:
    state = {
        'units': [
            {
                'id': 'unit-api',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-API-ASSIST',
                        'acceptance_criterion': 'AC-01',
                        'layer': 'e2e',
                        'verification_assist': {
                            'description': 'Inspect the system manually through the configured assist runner.',
                            'expected': 'The assisted judgement records structured evidence.',
                        },
                        'expected': 'The assisted judgement records structured evidence.',
                    }
                ],
                'verification_commands': [],
            }
        ]
    }

    validate_unit_plan_evidence_row_preflight(state)


def test_unit_plan_evidence_row_preflight_rejects_automatic_case_with_manual_evidence_only() -> None:
    state = {
        'units': [
            {
                'id': 'unit-api',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-API-MANUAL-NOTE',
                        'acceptance_criterion': 'AC-01',
                        'layer': 'functional',
                        'evidence': 'Manual note in approvals/unit-plan.md',
                        'expected': 'API behavior is verified.',
                    }
                ],
                'verification_commands': [],
            }
        ]
    }

    with pytest.raises(ValueError) as exc:
        validate_unit_plan_evidence_row_preflight(state)

    assert 'manual evidence does not satisfy automated evidence row preflight' in str(exc.value)


def test_unit_plan_approval_accepts_non_padded_ao_ids(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Test Case Matrix\n'
        '| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AC-1 covers AO-01 | TC-1 | integration | pytest tests/test_a.py -q | AO-01 works |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
        ],
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-1',
                        'acceptance_criterion': 'AC-1',
                        'covers_obligations': ['AO-01'],
                        'layer': 'integration',
                        'command': 'pytest tests/test_a.py -q',
                        'expected': 'AO-01 works',
                    }
                ],
                'verification_commands': ['pytest tests/test_a.py -q'],
            }
        ],
    }

    validate_unit_plan_acceptance_obligation_coverage(gate, state)


def test_unit_plan_blocks_long_lived_workflow_change_without_document_deliverables_matrix(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Test Case Matrix\n'
        '| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AC-1 | TC-1 | functional | pytest tests/test_policy.py -q | policy enforced |\n',
        encoding='utf-8',
    )
    state = {
        'units': [
            {
                'id': 'unit-doc-policy',
                'name': 'Evidence policy workflow change',
                'passes': False,
                'scope': ['Change workflow evidence policy for final acceptance.'],
                'done_when': ['Verifier evidence policy is enforced.'],
            }
        ]
    }

    with pytest.raises(ValueError, match='Document Deliverables Matrix|文档交付矩阵'):
        validate_unit_plan_document_deliverables(gate, state)


def test_unit_plan_accepts_pure_code_fix_declaring_no_formal_doc_change(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Document Deliverables Matrix\n'
        '| Area | Target Path | Action | Required For Acceptance | Evidence / Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| code fix | 不需要正式文档变更 | none | false | 纯解析 bug 修复，不改变长期产品/架构/流程/运维事实。 |\n',
        encoding='utf-8',
    )
    state = {
        'units': [
            {
                'id': 'unit-parser-fix',
                'name': 'Parser bug fix',
                'passes': False,
                'scope': ['Fix malformed JSON parsing for existing command output.'],
                'done_when': ['Regression test passes.'],
            }
        ]
    }

    validate_unit_plan_document_deliverables(gate, state)


def test_unit_plan_accepts_required_workflow_document_deliverable(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Document Deliverables Matrix\n'
        '| Area | Target Path | Action | Required For Acceptance | Evidence / Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| workflow | docs/workflow/evidence-policy.md | update | true | Evidence policy changes are long-term workflow rules. |\n',
        encoding='utf-8',
    )
    state = {
        'units': [
            {
                'id': 'unit-doc-policy',
                'name': 'Evidence policy workflow change',
                'passes': False,
                'scope': ['Change workflow evidence policy for final acceptance.'],
            }
        ]
    }

    validate_unit_plan_document_deliverables(gate, state)


def test_unit_plan_infrastructure_matrix_rejects_missing_matrix(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text('# Unit Plan\n\n## Test Case Matrix\n', encoding='utf-8')

    with pytest.raises(ValueError, match='Infrastructure / Execution Context Matrix'):
        validate_unit_plan_infrastructure_execution_context_matrix(gate, _staged_package_state())


def test_unit_plan_infrastructure_matrix_rejects_missing_category(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan\n\n'
        '## Infrastructure / Execution Context Matrix\n'
        '| 类别 | 事实 | 来源 | Unit Plan 消费方式 |\n'
        '| --- | --- | --- | --- |\n'
        '| 代码仓库 | repo | docs | builder scope |\n'
        '| 项目部署运行时环境 | python3 pytest | progress | verification |\n'
        '| 调试分析方法 | session/events/artifacts | AGENTS | failure triage |\n'
        '| 参考环境 | current workflow | roadmap | keep ordering |\n'
        '| 文档地址 | docs/README.md | docs registry | formal docs |\n'
        '| 架构/交互逻辑/接口说明 | controller modules | requirements | implementation |\n',
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='依赖信息'):
        validate_unit_plan_infrastructure_execution_context_matrix(gate, _staged_package_state())


def test_unit_plan_infrastructure_matrix_accepts_all_categories(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan\n\n'
        '## Infrastructure / Execution Context Matrix\n'
        '| 类别 | 事实 | 来源 | Unit Plan 消费方式 |\n'
        '| --- | --- | --- | --- |\n'
        '| 代码仓库 | repo | docs | builder scope |\n'
        '| 项目部署运行时环境 | python3 pytest | progress | verification |\n'
        '| 调试分析方法 | session/events/artifacts | AGENTS | failure triage |\n'
        '| 参考环境 | current workflow | roadmap | keep ordering |\n'
        '| 文档地址 | docs/README.md | docs registry | formal docs |\n'
        '| 架构/交互逻辑/接口说明 | controller modules | requirements | implementation |\n'
        '| 依赖信息 | Python stdlib and pytest | roadmap | no new deps |\n',
        encoding='utf-8',
    )

    validate_unit_plan_infrastructure_execution_context_matrix(gate, _staged_package_state())


def test_final_acceptance_blocks_missing_required_document_deliverable(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Document Deliverables Matrix\n'
        '| Area | Target Path | Action | Required For Acceptance | Evidence / Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| workflow | docs/workflow/evidence-policy.md | update | true | Evidence policy changes are acceptance-blocking docs. |\n',
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='docs/workflow/evidence-policy.md'):
        validate_final_document_deliverables(gate, {'workspacePath': str(workspace)})


def test_final_acceptance_ignores_missing_non_required_document_deliverable(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Document Deliverables Matrix\n'
        '| Area | Target Path | Action | Required For Acceptance | Evidence / Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| product | docs/product/future-backlog.md | backlog | false | Candidate future backlog; not required for current acceptance. |\n',
        encoding='utf-8',
    )

    validate_final_document_deliverables(gate, {'workspacePath': str(workspace)})


def test_final_acceptance_accepts_existing_required_document_deliverable(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    target = workspace / 'docs' / 'workflow' / 'evidence-policy.md'
    target.parent.mkdir(parents=True)
    target.write_text('# Evidence Policy\n', encoding='utf-8')
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Document Deliverables Matrix\n'
        '| Area | Target Path | Action | Required For Acceptance | Evidence / Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| workflow | docs/workflow/evidence-policy.md | update | true | Evidence policy changes are acceptance-blocking docs. |\n',
        encoding='utf-8',
    )

    validate_final_document_deliverables(gate, {'workspacePath': str(workspace)})


def test_unit_plan_test_case_matrix_with_design_columns_requires_real_test_evidence(tmp_path: Path) -> None:
    gate = tmp_path / 'unit-plan.md'
    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Test Case Matrix\n'
        '| Acceptance Criterion | Test Case | Layer | Product Design Ref | Technical Architecture Ref | Fixture | Command/Evidence | Expected Result |\n'
        '| --- | --- | --- | --- | --- | --- | --- | --- |\n'
        '| AC-1 covers AO-001 | TC-1 | integration | PD-1 | TA-1 | fixture.json |  |  |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
        ],
        'units': [{'id': 'unit-01', 'passes': False, 'verification_commands': []}],
    }

    with pytest.raises(ValueError, match='AO-001'):
        validate_unit_plan_acceptance_obligation_coverage(gate, state)

    gate.write_text(
        '# Unit Plan Confirmation\n\n'
        '## Test Case Matrix\n'
        '| Acceptance Criterion | Test Case | Layer | Product Design Ref | Technical Architecture Ref | Fixture | Command/Evidence | Expected Result |\n'
        '| --- | --- | --- | --- | --- | --- | --- | --- |\n'
        '| AC-1 covers AO-001 | TC-1 | integration | PD-1 | TA-1 | fixture.json | pytest tests/test_a.py -q | AO-001 works |\n',
        encoding='utf-8',
    )

    validate_unit_plan_acceptance_obligation_coverage(gate, state)


def test_requirements_approval_blocks_unmapped_must_obligation(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: integration]: 六步 UX 清楚展示。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-001 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
            {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
        ],
    }

    with pytest.raises(ValueError, match='AO-002'):
        validate_requirements_acceptance_quality(gate, state)


def test_requirements_approval_accepts_non_padded_ao_ids(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: integration]: 六步 UX 清楚展示。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-01 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
        ],
    }

    validate_requirements_acceptance_quality(gate, state)


def test_requirements_approval_requires_verification_layer_for_each_ac(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1: 六步 UX 清楚展示。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-001 | AC-1 | covered |  | pytest tests/test_delivery.py -q |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
        ],
    }

    with pytest.raises(ValueError, match='AC-1.*verification layer'):
        validate_requirements_acceptance_quality(gate, state)


def test_requirements_approval_does_not_count_layer_words_in_ac_description(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1: Manual import behavior works with fixed data.\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-001 | AC-1 | covered |  | pytest tests/test_delivery.py -q |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '手工导入行为需明确', 'priority': 'must', 'status': 'open'},
        ],
    }

    with pytest.raises(ValueError, match='AC-1.*verification layer'):
        validate_requirements_acceptance_quality(gate, state)


def test_requirements_approval_accepts_mapped_and_explicitly_deferred_obligations(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: integration]: 六步 UX 清楚展示。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-001 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |\n'
        '| AO-002 | deferred | deferred | manual | 本版本不包含 15 个材料导入，已记录到后续范围。 |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
            {'id': 'AO-002', 'title': '15 个材料没有覆盖', 'priority': 'must', 'status': 'open'},
        ],
    }

    validate_requirements_acceptance_quality(gate, state)


def test_requirements_approval_accepts_out_of_scope_with_blank_ac_and_reason(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: manual]: 当前目标不修改旧 stream handler。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-069 |  | out_of_scope | manual | `sdk/api/handlers` 属于旧 stream 目标。 |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {
                'id': 'AO-069',
                'title': '`sdk/api/handlers` 属于旧 stream 目标。',
                'priority': 'must',
                'status': 'open',
            },
        ],
    }

    validate_requirements_acceptance_quality(gate, state)


def test_requirements_e2e_ac_requires_4_6_review_matrix(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(_requirements_gate_with_e2e_policy(None), encoding='utf-8')

    with pytest.raises(ValueError, match='E2E.*4\\.6'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_e2e_review_matrix_accepts_complete_ac_and_journey_row(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        _requirements_gate_with_e2e_policy(_valid_requirements_e2e_matrix_section()),
        encoding='utf-8',
    )

    validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_e2e_review_matrix_accepts_command_intent_without_exact_command(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        _requirements_gate_with_e2e_policy(
            _valid_requirements_e2e_matrix_section(
                command=(
                    'Unit Plan must create Go service/API E2E command for services/api '
                    'real OpenMAIC PDF integration'
                )
            )
        ),
        encoding='utf-8',
    )

    validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


@pytest.mark.parametrize(
    'command',
    [
        'bash tests/e2e/verify-orders.sh --journey J-001 --ac AC-01',
        'sh tests/e2e/verify-orders.sh --journey J-001 --ac AC-01',
        './tests/e2e/verify-orders.sh --journey J-001 --ac AC-01',
        'scripts/verify-orders-e2e.sh --journey J-001 --ac AC-01',
        '/home/gaoqi/wkspace/claude_project/karen/dev24/docs/run_cascade_unbind_retain_case.sh',
    ],
)
def test_requirements_e2e_review_matrix_accepts_concrete_shell_e2e_commands(
    tmp_path: Path,
    command: str,
) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        _requirements_gate_with_e2e_policy(
            _valid_requirements_e2e_matrix_section(command=command)
        ),
        encoding='utf-8',
    )

    validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


@pytest.mark.parametrize(
    'command',
    [
        'bash',
        'sh',
        'bash test',
        'sh test',
        './test',
        'echo tests/e2e/verify-orders.sh',
        'run e2e',
    ],
)
def test_requirements_e2e_review_matrix_rejects_vague_shell_commands(
    tmp_path: Path,
    command: str,
) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        _requirements_gate_with_e2e_policy(
            _valid_requirements_e2e_matrix_section(command=command)
        ),
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='Verification Command'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_e2e_review_matrix_requires_rows_for_e2e_ac_and_journey(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        _requirements_gate_with_e2e_policy(
            _valid_requirements_e2e_matrix_section(ac_journey='AC-01')
        ),
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='J-001.*4\\.6'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


@pytest.mark.parametrize(
    ('matrix_kwargs', 'expected_issue'),
    [
        ({'entrypoint': 'TBD'}, 'Real Entrypoint'),
        ({'user_steps': 'pending'}, 'User Steps'),
        ({'fixture': 'N/A'}, 'Fixture / Test Data / Setup'),
        ({'command': 'playwright test'}, 'Verification Command'),
        ({'environment_kind': 'component_mock'}, 'Environment Kind'),
        ({'mock_policy': 'Mock core API with page.route("**/api/orders") and route.fulfill'}, 'Mock Policy'),
        ({'assertions': 'screenshot retained and reviewer observes the page'}, 'Expected Assertions'),
    ],
)
def test_requirements_e2e_review_matrix_rejects_incomplete_or_non_real_rows(
    tmp_path: Path,
    matrix_kwargs: dict[str, str],
    expected_issue: str,
) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        _requirements_gate_with_e2e_policy(
            _valid_requirements_e2e_matrix_section(**matrix_kwargs)
        ),
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match=expected_issue):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


@pytest.mark.parametrize(
    'command',
    [
        '待 Unit Plan 补充',
        'pytest',
        '后续测试验证',
    ],
)
def test_requirements_e2e_review_matrix_rejects_placeholder_or_generic_command_intent(
    tmp_path: Path,
    command: str,
) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        _requirements_gate_with_e2e_policy(
            _valid_requirements_e2e_matrix_section(command=command)
        ),
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='non-placeholder verification command intent'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_explicit_e2e_strategy_must_map_to_e2e_ac_or_active_journey(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        _requirements_gate_with_e2e_policy(
            _valid_requirements_e2e_matrix_section(),
            acceptance_layer='functional',
            journey_layer='functional',
            test_strategy='- Playwright browser E2E must prove the order creation flow.\n',
        ),
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='map.*E2E.*AC.*Journey'):
        validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_requirements_non_e2e_gate_does_not_need_4_6_review_matrix(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(_minimal_requirements_gate_with_infrastructure(_valid_infrastructure_section()), encoding='utf-8')

    validate_requirements_acceptance_quality(gate, {'requestedOutcome': 'V1.8.4'})


def test_v0_6_0_uiux_project_requires_prototype_before_requirements_human_confirmation(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 1. 需求\n'
        '目标项目需要 UI/UX 设计，但尚未提供原型证据。\n\n'
        '## 3. 验收标准\n'
        '- AC-10 [verification: functional]: UI/UX 项目必须在人工确认前提供 prototype 证据。\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-10 | PD-INFRA-10 | TA-UIDESIGN-01, TA-PREFLIGHT-01 | UI 原型预检。 |\n',
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='UI/UX.*prototype'):
        validate_requirements_acceptance_quality(gate, {'currentUnitNeedsUiDesign': True})

    gate.write_text(
        gate.read_text(encoding='utf-8')
        + '\n## 7. 产品设计概要\n'
        + '- Prototype Evidence: `docs/product/prototype.md` 记录页面、状态和 AC 映射。\n',
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='valid prototype manifest'):
        validate_requirements_acceptance_quality(gate, {'currentUnitNeedsUiDesign': True})

    _write_prototype_manifest_for_gate(gate, prototype_type='url', ac='AC-10')
    validate_requirements_acceptance_quality(gate, {'currentUnitNeedsUiDesign': True})


def test_v0_6_0_web_system_requires_clickable_webpage_prototype(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    base = (
        '# 需求与验收确认\n\n'
        '## 1. 需求\n'
        '目标项目是 Web 系统，需要浏览器可见体验。\n\n'
        '## 3. 验收标准\n'
        '- AC-11 [verification: functional]: Web 系统必须提供可点击网页原型。\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-11 | PD-INFRA-11 | TA-WEBPROTO-01, TA-PREFLIGHT-01 | Web 原型预检。 |\n'
    )
    gate.write_text(
        base
        + '\n## 7. 产品设计概要\n'
        + '- Prototype Evidence: 静态截图 `prototype.png` 和文字说明。\n',
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='clickable webpage prototype'):
        validate_requirements_acceptance_quality(gate, {'currentUnitIsWebSystem': True})

    gate.write_text(
        base
        + '\n## 7. 产品设计概要\n'
        + '- Web Prototype Evidence: clickable webpage prototype at `http://localhost:4173/prototype`; '
        + 'start command `python -m http.server 4173`; pages `Dashboard`, `Settings`, `Preview`; '
        + 'click path `Dashboard -> Settings -> Preview`; maps to AC-11.\n',
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='valid prototype manifest'):
        validate_requirements_acceptance_quality(gate, {'currentUnitIsWebSystem': True})

    _write_prototype_manifest_for_gate(gate, prototype_type='html', ac='AC-11')
    validate_requirements_acceptance_quality(gate, {'currentUnitIsWebSystem': True})


def test_v0_6_0_web_system_accepts_clickable_prototype_evidence_table_section(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 1. 需求\n'
        '目标项目是 Web 系统，需要浏览器可见体验。\n\n'
        '## 3. 验收标准\n'
        '- AC-11 [verification: functional]: Web 系统必须提供可点击网页原型。\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-11 | PD-INFRA-11 | TA-WEBPROTO-01, TA-PREFLIGHT-01 | Web 原型预检。 |\n\n'
        '## 4.10 Web 可点击原型证据（clickable webpage prototype evidence）\n\n'
        '| Field | Evidence |\n'
        '| --- | --- |\n'
        '| URL / access method | `file:///tmp/prototype.html`；浏览器直接打开本地 HTML 文件即可点击。 |\n'
        '| page states | Dashboard；Settings；Preview。 |\n'
        '| click path | 打开 HTML 原型 -> 点击 Dashboard -> 点击 Settings -> 点击 Preview。 |\n'
        '| AC mapping | AC-11 映射到 Dashboard、Settings、Preview 三个页面状态。 |\n',
        encoding='utf-8',
    )

    _write_prototype_manifest_for_gate(gate, prototype_type='html', ac='AC-11')

    validate_requirements_acceptance_quality(gate, {'currentUnitIsWebSystem': True})


def test_v0_6_0_web_prototype_manual_evidence_maps_to_ac(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 1. 需求\n'
        '目标项目是 Web 系统。\n\n'
        '## 3. 验收标准\n'
        '- AC-12 [verification: manual]: Web 系统网页原型必须记录人工点击证据。\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-12 | PD-INFRA-12 | TA-WEBPROTO-02 | 人工点击证据。 |\n\n'
        '## 7. 产品设计概要\n'
        '- Web Prototype Evidence: clickable webpage prototype at `http://localhost:4173/prototype`; '
        + 'start command `python -m http.server 4173`; pages `Dashboard`, `Settings`, `Preview`; '
        + 'click path `Dashboard -> Settings -> Preview`; maps to AC-12.\n'
        '- Manual Click Evidence: reviewer opened `http://localhost:4173/prototype`, '
        + 'clicked `Dashboard -> Settings -> Preview`, observed page states `Dashboard`, `Settings`, `Preview`, '
        + 'and mapped evidence to AC-12.\n',
        encoding='utf-8',
    )

    _write_prototype_manifest_for_gate(gate, prototype_type='html', ac='AC-12')
    validate_requirements_acceptance_quality(gate, {'currentUnitIsWebSystem': True})


def test_v0_6_0_policy_gate_does_not_require_its_own_web_prototype(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 1. 需求\n'
        'V0.6.0 让 Waygate 在处理目标项目时梳理基础设施信息。\n'
        '当目标项目是 Web 系统时，Requirements Gate 必须要求网页原型。\n\n'
        '## 3. 验收标准\n'
        '- AC-10 [verification: functional]: 当目标项目需要 UI/UX 时，Requirements Gate 要求 prototype evidence。\n'
        '- AC-11 [verification: functional]: 当目标项目是 Web 系统时，Requirements Gate 要求 clickable webpage prototype。\n'
        '- AC-12 [verification: manual]: Web 系统网页原型人工证据记录访问方式和 AC 映射。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-004 | AC-10, AC-11, AC-12 | covered | functional | Web/UI policy coverage. |\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-10 | PD-INFRA-10 | TA-UIDESIGN-01, TA-PREFLIGHT-01 | UI/UX 原型预检。 |\n'
        '| AC-11 | PD-INFRA-11 | TA-WEBPROTO-01, TA-PREFLIGHT-01 | Web 原型预检。 |\n'
        '| AC-12 | PD-INFRA-12 | TA-WEBPROTO-02 | 人工点击证据。 |\n\n'
        + _valid_infrastructure_section(),
        encoding='utf-8',
    )

    validate_requirements_acceptance_quality(
        gate,
        {
            'requestedOutcome': 'V0.6.0',
            'currentUnitId': 'v0-6-0-u1-infrastructure-intake-gate',
            'currentUnitNeedsUiDesign': False,
        },
    )


def test_requirements_text_prototype_contract_requires_manifest_even_without_state_flags(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 1. 需求\n'
        '教师工作台必须以 clickable webpage prototype 作为 UI contract，落到真实 route `/dashboard/teacher`。\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: `/dashboard/teacher` 的信息架构、主操作和关键交互必须符合原型合约。\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-21 | PD-TEACHER-01 | TA-ROUTE-01 | 原型合约映射到真实 route。 |\n',
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='valid prototype manifest'):
        validate_requirements_acceptance_quality(gate, {})


def test_unit_plan_rejects_static_prototype_only_conformance_test(tmp_path: Path) -> None:
    requirements = tmp_path / 'requirements-and-acceptance.md'
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 教师工作台必须符合原型合约。\n',
        encoding='utf-8',
    )
    _write_prototype_manifest_for_gate(requirements, ac='AC-21')
    unit_plan = tmp_path / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n\n## Test Case Matrix\n', encoding='utf-8')
    state = {
        'currentUnitId': 'unit-01',
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-STATIC',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'fixture': 'static prototype artifact',
                        'command': 'npx playwright test artifacts/requirements-draft/prototypes/requirements-prototype.spec.ts',
                        'expected': 'prototype opens and matches screenshot',
                        'prototype_conformance': ['requirements-prototype'],
                        'production_targets': ['/dashboard/preview'],
                    }
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match='production UI conformance'):
        validate_unit_plan_prototype_conformance(requirements, unit_plan, state)


def test_unit_plan_accepts_real_route_prototype_conformance_test(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 教师工作台必须符合原型合约。\n',
        encoding='utf-8',
    )
    _write_prototype_manifest_for_gate(requirements, ac='AC-21')
    unit_plan = tmp_path / 'approvals' / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n\n## Test Case Matrix\n', encoding='utf-8')
    state = {
        'currentUnitId': 'unit-01',
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-REAL-ROUTE',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'fixture': 'teacher with one active course and one pending review',
                        'command': 'npx playwright test tests/e2e/teacher-dashboard.spec.ts --project=chromium',
                        'expected': 'route /dashboard/preview shows Dashboard and Preview states, preserves the primary action order, and opens the preview panel after clicking Preview',
                        'prototype_conformance': ['requirements-prototype'],
                        'production_targets': ['/dashboard/preview'],
                        'visual_evidence_plan': _visual_evidence_plan(),
                    }
                ],
            }
        ],
    }

    validate_unit_plan_prototype_conformance(requirements, unit_plan, state)


def test_unit_plan_rejects_prototype_conformance_without_l1_l2_visual_evidence_plan(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 教师工作台必须符合原型合约。\n',
        encoding='utf-8',
    )
    _write_prototype_manifest_for_gate(requirements, ac='AC-21')
    unit_plan = tmp_path / 'approvals' / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n\n## Test Case Matrix\n', encoding='utf-8')
    state = {
        'currentUnitId': 'unit-01',
        'currentUnitIsWebSystem': True,
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-NO-VISUAL-EVIDENCE',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'fixture': 'teacher with one active course and one pending review',
                        'command': 'npx playwright test tests/e2e/teacher-dashboard.spec.ts --project=chromium',
                        'expected': 'route /dashboard/preview preserves the primary action order and opens the preview panel after clicking Preview',
                        'prototype_conformance': ['requirements-prototype'],
                        'production_targets': ['/dashboard/preview'],
                        'user_steps': ['Open /dashboard/preview', 'Click Preview'],
                    }
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match='missing L1 visual evidence plan'):
        validate_unit_plan_prototype_conformance(requirements, unit_plan, state)


def test_unit_plan_rejects_route_text_only_prototype_conformance_expected(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 教师工作台必须符合原型合约。\n',
        encoding='utf-8',
    )
    _write_prototype_manifest_for_gate(requirements, ac='AC-21')
    unit_plan = tmp_path / 'approvals' / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n\n## Test Case Matrix\n', encoding='utf-8')
    state = {
        'currentUnitId': 'unit-01',
        'currentUnitIsWebSystem': True,
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-TEXT-ONLY',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'fixture': 'teacher with one active course and one pending review',
                        'command': 'npx playwright test tests/e2e/teacher-dashboard.spec.ts --project=chromium',
                        'expected': 'route /dashboard/preview loads and the text Teacher Dashboard is visible',
                        'prototype_conformance': ['requirements-prototype'],
                        'production_targets': ['/dashboard/preview'],
                        'user_steps': ['Open /dashboard/preview'],
                        'visual_evidence_plan': _visual_evidence_plan(),
                    }
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match='missing L2 structural/interaction assertions'):
        validate_unit_plan_prototype_conformance(requirements, unit_plan, state)


def test_unit_plan_requires_l4_plan_for_explicit_pixel_exact_prototype_contract(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 品牌 Logo surface 必须像素级符合原型合约。\n',
        encoding='utf-8',
    )
    manifest_path = _write_prototype_manifest_for_gate(requirements, ac='AC-21')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['prototypes'][0]['fidelity_required'] = 'pixel_exact'
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    unit_plan = tmp_path / 'approvals' / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n\n## Test Case Matrix\n', encoding='utf-8')
    state = {
        'currentUnitId': 'unit-01',
        'currentUnitIsWebSystem': True,
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-PIXEL-NO-REGRESSION',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'fixture': 'teacher dashboard with brand logo',
                        'command': 'npx playwright test tests/e2e/teacher-dashboard.spec.ts --project=chromium',
                        'expected': 'brand logo region preserves size, placement, color, and opens the preview panel after clicking Preview',
                        'prototype_conformance': ['requirements-prototype'],
                        'production_targets': ['/dashboard/preview'],
                        'user_steps': ['Open /dashboard/preview', 'Click Preview'],
                        'visual_evidence_plan': _visual_evidence_plan(),
                    }
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match='missing L4 pixel-exact evidence plan'):
        validate_unit_plan_prototype_conformance(requirements, unit_plan, state)


def test_unit_plan_visual_fidelity_rules_do_not_apply_without_ui_web_prototype_manifest(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: integration]: CLI 输出 structured summary。\n',
        encoding='utf-8',
    )
    unit_plan = tmp_path / 'approvals' / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n\n## Test Case Matrix\n', encoding='utf-8')

    validate_unit_plan_prototype_conformance(
        requirements,
        unit_plan,
        {'currentUnitId': 'unit-01', 'currentUnitIsWebSystem': False, 'units': []},
    )


def test_unit_plan_requires_each_surface_target_not_adjacent_dialog(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 课程运营原型中的每个弹窗 surface 必须落到真实入口。\n',
        encoding='utf-8',
    )
    _write_surface_prototype_manifest_for_gate(requirements)
    unit_plan = tmp_path / 'approvals' / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n\n## Test Case Matrix\n', encoding='utf-8')
    state = {
        'currentUnitId': 'unit-01',
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-PUBLISH-DIALOG',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'fixture': 'teacher dashboard with a published course',
                        'command': 'npx playwright test tests/e2e/publish-target-dialog.spec.ts --project=chromium',
                        'expected': 'CourseCard opens the PublishTargetDialog and shows the selected class count',
                        'prototype_conformance': ['v291-course-ops-prototype-contract'],
                        'prototype_surfaces': ['publish-target-dialog'],
                        'production_targets': ['component:OpenMAIC/components/course/PublishTargetDialog.tsx'],
                        'user_steps': ['Open /dashboard/teacher', 'Click CourseCard 发布对象'],
                        'visual_evidence_plan': _visual_evidence_plan(
                            prototype='artifacts/requirements-draft/prototypes/course-ops/publish-dialog.png',
                            production='artifacts/unit-01/screenshots/publish-dialog.png',
                            interaction='artifacts/unit-01/screenshots/publish-dialog-after-click.png',
                            entrypoint='/dashboard/teacher',
                        ),
                    }
                ],
            }
        ],
    }

    with pytest.raises(
        ValueError,
        match='prototype v291-course-ops-prototype-contract surface assignment-management-dialog target component:OpenMAIC/components/course/AssignManageDialog.tsx missing production UI conformance test',
    ):
        validate_unit_plan_prototype_conformance(requirements, unit_plan, state)


def test_unit_plan_accepts_required_surface_target_with_real_entrypoint_steps(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 课程运营原型中的每个弹窗 surface 必须落到真实入口。\n',
        encoding='utf-8',
    )
    _write_surface_prototype_manifest_for_gate(requirements)
    unit_plan = tmp_path / 'approvals' / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n\n## Test Case Matrix\n', encoding='utf-8')
    state = {
        'currentUnitId': 'unit-01',
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-PUBLISH-DIALOG',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'fixture': 'teacher dashboard with a published course',
                        'command': 'npx playwright test tests/e2e/course-dialogs.spec.ts --project=chromium',
                        'expected': 'CourseCard opens PublishTargetDialog and shows selected class count',
                        'prototype_conformance': ['v291-course-ops-prototype-contract'],
                        'prototype_surfaces': ['publish-target-dialog'],
                        'production_targets': ['component:OpenMAIC/components/course/PublishTargetDialog.tsx'],
                        'user_steps': ['Open /dashboard/teacher', 'Click CourseCard 发布对象'],
                        'visual_evidence_plan': _visual_evidence_plan(
                            prototype='artifacts/requirements-draft/prototypes/course-ops/publish-dialog.png',
                            production='artifacts/unit-01/screenshots/publish-dialog.png',
                            interaction='artifacts/unit-01/screenshots/publish-dialog-after-click.png',
                            entrypoint='/dashboard/teacher',
                        ),
                    },
                    {
                        'id': 'TC-PROTO-ASSIGN-MANAGE-DIALOG',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'fixture': 'teacher dashboard with one assignable course and two students',
                        'command': 'npx playwright test tests/e2e/course-dialogs.spec.ts --project=chromium',
                        'expected': 'CourseCard opens AssignManageDialog, lists two students, toggles one assignment, and shows saved count 1',
                        'prototype_conformance': ['v291-course-ops-prototype-contract'],
                        'prototype_surfaces': ['assignment-management-dialog'],
                        'production_targets': ['component:OpenMAIC/components/course/AssignManageDialog.tsx'],
                        'user_steps': ['Open /dashboard/teacher', 'Click CourseCard 分配管理'],
                        'visual_evidence_plan': _visual_evidence_plan(
                            prototype='artifacts/requirements-draft/prototypes/course-ops/assign-dialog.png',
                            production='artifacts/unit-01/screenshots/assign-dialog.png',
                            interaction='artifacts/unit-01/screenshots/assign-dialog-after-click.png',
                            entrypoint='/dashboard/teacher',
                        ),
                    },
                ],
            }
        ],
    }

    validate_unit_plan_prototype_conformance(requirements, unit_plan, state)


def test_final_acceptance_blocks_missing_surface_evidence(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 课程运营原型中的每个弹窗 surface 必须落到真实入口。\n',
        encoding='utf-8',
    )
    _write_surface_prototype_manifest_for_gate(requirements)
    artifacts_dir = tmp_path / 'artifacts'
    unit_dir = artifacts_dir / 'unit-01'
    unit_dir.mkdir(parents=True)
    (unit_dir / 'verification.json').write_text(
        json.dumps(
            {
                'evidence_rows': [
                    {
                        'test_case_id': 'TC-PROTO-PUBLISH-DIALOG',
                        'status': 'passed',
                        'command': 'npx playwright test tests/e2e/course-dialogs.spec.ts --project=chromium',
                    }
                ]
            }
        ),
        encoding='utf-8',
    )
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': True,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-PUBLISH-DIALOG',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'command': 'npx playwright test tests/e2e/course-dialogs.spec.ts --project=chromium',
                        'expected': 'CourseCard opens PublishTargetDialog and shows selected class count',
                        'prototype_conformance': ['v291-course-ops-prototype-contract'],
                        'prototype_surfaces': ['publish-target-dialog'],
                        'production_targets': ['component:OpenMAIC/components/course/PublishTargetDialog.tsx'],
                    },
                    {
                        'id': 'TC-PROTO-ASSIGN-MANAGE-DIALOG',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'command': 'npx playwright test tests/e2e/course-dialogs.spec.ts --project=chromium',
                        'expected': 'CourseCard opens AssignManageDialog and saves assignment count 1',
                        'prototype_conformance': ['v291-course-ops-prototype-contract'],
                        'prototype_surfaces': ['assignment-management-dialog'],
                        'production_targets': ['component:OpenMAIC/components/course/AssignManageDialog.tsx'],
                    },
                ],
            }
        ],
    }

    with pytest.raises(
        ValueError,
        match='surface assignment-management-dialog target component:OpenMAIC/components/course/AssignManageDialog.tsx via TC-PROTO-ASSIGN-MANAGE-DIALOG: missing',
    ):
        validate_final_prototype_conformance(
            state=state,
            artifacts_dir=artifacts_dir,
            requirements_path=requirements,
        )


def test_final_acceptance_blocks_passed_prototype_evidence_without_visual_screenshots(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 教师工作台必须符合原型合约。\n',
        encoding='utf-8',
    )
    _write_prototype_manifest_for_gate(requirements, ac='AC-21')
    artifacts_dir = tmp_path / 'artifacts'
    unit_dir = artifacts_dir / 'unit-01'
    unit_dir.mkdir(parents=True)
    command = 'npx playwright test tests/e2e/teacher-dashboard.spec.ts --project=chromium'
    (unit_dir / 'verification.json').write_text(
        json.dumps(
            {
                'evidence_rows': [
                    {
                        'unit_id': 'unit-01',
                        'test_case_id': 'TC-PROTO-VISUAL-MISSING',
                        'acceptance_criterion': 'AC-21',
                        'acceptance_obligations': [],
                        'layer': 'e2e',
                        'command': command,
                        'expected': 'dashboard keeps prototype region order and opens preview panel after clicking Preview',
                        'status': 'passed',
                        'result_index': 0,
                        'returncode': 0,
                        'artifact_refs': ['artifacts/unit-01/verification.json'],
                        'golden_path': True,
                        'environment_kind': 'local_real',
                        'real_entrypoint': '/dashboard/preview',
                        'uses_core_api_mock': False,
                        'mocked_routes': [],
                        'browser_console_errors': [],
                        'page_errors': [],
                        'request_failures': [],
                        'screenshot_refs': [],
                    }
                ]
            }
        ),
        encoding='utf-8',
    )
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': True,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-VISUAL-MISSING',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'command': command,
                        'expected': 'dashboard keeps prototype region order and opens preview panel after clicking Preview',
                        'prototype_conformance': ['requirements-prototype'],
                        'production_targets': ['/dashboard/preview'],
                        'user_steps': ['Open /dashboard/preview', 'Click Preview'],
                    }
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match='missing prototype screenshot'):
        validate_final_prototype_conformance(
            state=state,
            artifacts_dir=artifacts_dir,
            requirements_path=requirements,
        )


def test_final_acceptance_accepts_local_real_non_browser_prototype_conformance_evidence(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-42 [verification: integration]: controller workflow review artifact maps to module, artifact, state, and event targets.\n',
        encoding='utf-8',
    )
    _write_non_browser_surface_prototype_manifest_for_gate(requirements)
    artifacts_dir = tmp_path / 'artifacts'
    unit_dir = artifacts_dir / 'unit-01'
    unit_dir.mkdir(parents=True)
    command = 'bash scripts/verify/workflow-review.sh'
    visual_refs = _visual_evidence_plan(
        prototype='artifacts/prototype/workflow-review.png',
        production='artifacts/prototype/controller-surfaces.png',
        interaction='artifacts/prototype/tabs-after-click.png',
        entrypoint='controller module, artifact, state, and event surfaces',
    )
    (unit_dir / 'verification.json').write_text(
        json.dumps(
            {
                'evidence_rows': [
                    {
                        'unit_id': 'unit-01',
                        'test_case_id': 'TC-PROTO-WORKFLOW',
                        'acceptance_criterion': 'AC-42',
                        'layer': 'integration',
                        'command': command,
                        'expected': 'workflow review artifact maps to module, artifact, state, and event targets with tab interaction evidence',
                        'status': 'passed',
                        'returncode': 0,
                        'artifact_refs': ['artifacts/unit-01/verification.json'],
                        'environment_kind': 'local_real',
                        'real_entrypoint': 'controller module, artifact, state, and event surfaces',
                        'uses_core_api_mock': False,
                        'mocked_routes': [],
                        'browser_console_errors': [],
                        'page_errors': [],
                        'request_failures': [],
                        'visual_evidence_refs': visual_refs,
                    }
                ]
            }
        ),
        encoding='utf-8',
    )
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': True,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-WORKFLOW',
                        'acceptance_criterion': 'AC-42',
                        'layer': 'integration',
                        'environment_kind': 'local_real',
                        'command': command,
                        'expected': 'workflow review artifact maps to module, artifact, state, and event targets with tab interaction evidence',
                        'prototype_conformance': ['workflow-review'],
                        'prototype_surfaces': ['prompt-contract'],
                        'production_targets': [
                            'module:workflow_controller/prompts/requirements_package.py',
                            'artifact:.rrc-controller-*/artifacts/<role>/runs/<run-id>/',
                            'state:.rrc-controller-*/session.json',
                            'events:.rrc-controller-*/events.jsonl',
                        ],
                        'user_steps': ['Open workflow review artifact', 'Select Prompt Contract', 'Select Audit'],
                    }
                ],
            }
        ],
    }

    validate_final_prototype_conformance(
        state=state,
        artifacts_dir=artifacts_dir,
        requirements_path=requirements,
    )


def test_final_acceptance_still_requires_real_e2e_for_browser_route_prototype_target(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 教师工作台必须符合原型合约。\n',
        encoding='utf-8',
    )
    _write_prototype_manifest_for_gate(requirements, ac='AC-21')
    artifacts_dir = tmp_path / 'artifacts'
    unit_dir = artifacts_dir / 'unit-01'
    unit_dir.mkdir(parents=True)
    command = 'bash scripts/verify/teacher-dashboard-integration.sh'
    (unit_dir / 'verification.json').write_text(
        json.dumps(
            {
                'evidence_rows': [
                    {
                        'unit_id': 'unit-01',
                        'test_case_id': 'TC-PROTO-ROUTE-INTEGRATION',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'integration',
                        'command': command,
                        'expected': 'dashboard route preserves prototype region order and preview interaction',
                        'status': 'passed',
                        'returncode': 0,
                        'artifact_refs': ['artifacts/unit-01/verification.json'],
                        'environment_kind': 'local_real',
                        'real_entrypoint': '/dashboard/preview',
                        'uses_core_api_mock': False,
                        'mocked_routes': [],
                        'browser_console_errors': [],
                        'page_errors': [],
                        'request_failures': [],
                        'visual_evidence_refs': _visual_evidence_plan(),
                    }
                ]
            }
        ),
        encoding='utf-8',
    )
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': True,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-ROUTE-INTEGRATION',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'integration',
                        'environment_kind': 'local_real',
                        'command': command,
                        'expected': 'dashboard route preserves prototype region order and preview interaction',
                        'prototype_conformance': ['requirements-prototype'],
                        'production_targets': ['/dashboard/preview'],
                        'user_steps': ['Open /dashboard/preview', 'Click Preview'],
                    }
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match='not e2e evidence'):
        validate_final_prototype_conformance(
            state=state,
            artifacts_dir=artifacts_dir,
            requirements_path=requirements,
        )


def test_final_acceptance_blocks_explicit_screenshot_regression_without_result(tmp_path: Path) -> None:
    requirements = tmp_path / 'approvals' / 'requirements-and-acceptance.md'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-21 [verification: e2e]: 教师工作台必须使用截图回归符合原型合约。\n',
        encoding='utf-8',
    )
    manifest_path = _write_prototype_manifest_for_gate(requirements, ac='AC-21')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['prototypes'][0]['fidelity_required'] = 'screenshot_regression'
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    artifacts_dir = tmp_path / 'artifacts'
    unit_dir = artifacts_dir / 'unit-01'
    unit_dir.mkdir(parents=True)
    command = 'npx playwright test tests/e2e/teacher-dashboard.spec.ts --project=chromium'
    (unit_dir / 'verification.json').write_text(
        json.dumps(
            {
                'evidence_rows': [
                    {
                        'unit_id': 'unit-01',
                        'test_case_id': 'TC-PROTO-SCREENSHOT-REGRESSION',
                        'acceptance_criterion': 'AC-21',
                        'acceptance_obligations': [],
                        'layer': 'e2e',
                        'command': command,
                        'expected': 'dashboard keeps prototype region order and opens preview panel after clicking Preview',
                        'status': 'passed',
                        'result_index': 0,
                        'returncode': 0,
                        'artifact_refs': ['artifacts/unit-01/verification.json'],
                        'golden_path': True,
                        'environment_kind': 'local_real',
                        'real_entrypoint': '/dashboard/preview',
                        'uses_core_api_mock': False,
                        'mocked_routes': [],
                        'browser_console_errors': [],
                        'page_errors': [],
                        'request_failures': [],
                        'screenshot_refs': [],
                        'visual_evidence_refs': _visual_evidence_plan(),
                    }
                ]
            }
        ),
        encoding='utf-8',
    )
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': True,
                'test_cases': [
                    {
                        'id': 'TC-PROTO-SCREENSHOT-REGRESSION',
                        'acceptance_criterion': 'AC-21',
                        'layer': 'e2e',
                        'command': command,
                        'expected': 'dashboard keeps prototype region order and opens preview panel after clicking Preview',
                        'prototype_conformance': ['requirements-prototype'],
                        'production_targets': ['/dashboard/preview'],
                        'user_steps': ['Open /dashboard/preview', 'Click Preview'],
                    }
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match='missing screenshot regression result'):
        validate_final_prototype_conformance(
            state=state,
            artifacts_dir=artifacts_dir,
            requirements_path=requirements,
        )


def test_requirements_approval_requires_design_and_architecture_refs_for_each_ac(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: integration]: 六步 UX 清楚展示。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-001 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-1 | PD-1 |  | missing architecture |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
        ],
    }

    with pytest.raises(ValueError, match='AC-1.*design/architecture traceability'):
        validate_requirements_acceptance_quality(gate, state)


def test_requirements_approval_accepts_design_and_architecture_traceability(tmp_path: Path) -> None:
    gate = tmp_path / 'requirements-and-acceptance.md'
    gate.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: integration]: 六步 UX 清楚展示。\n\n'
        '## Requirements Traceability Matrix\n'
        '| AO | AC | Status | Verification Layer | Evidence/Reason |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| AO-001 | AC-1 | covered | integration | pytest tests/test_delivery.py -q |\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-1 | PD-AC1-six-step-flow | TA-AC1-state-model | runtime design and module boundary |\n',
        encoding='utf-8',
    )
    state = {
        'acceptanceObligations': [
            {'id': 'AO-001', 'title': '六步 UX 不清楚', 'priority': 'must', 'status': 'open'},
        ],
    }

    validate_requirements_acceptance_quality(gate, state)


def test_unit_plan_approval_requires_test_cases_to_preserve_design_architecture_refs(tmp_path: Path) -> None:
    requirements = tmp_path / 'requirements-and-acceptance.md'
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: integration]: 六步 UX 清楚展示。\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-1 | PD-AC1-six-step-flow | TA-AC1-state-model | runtime design and module boundary |\n',
        encoding='utf-8',
    )
    unit_plan = tmp_path / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n', encoding='utf-8')
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-1',
                        'acceptance_criterion': 'AC-1',
                        'layer': 'integration',
                        'command': 'pytest tests/test_delivery.py -q',
                        'expected': 'AO-001 works',
                    }
                ],
            }
        ]
    }

    with pytest.raises(ValueError, match='AC-1.*design/architecture traceability'):
        validate_unit_plan_design_architecture_traceability(requirements, unit_plan, state)


def test_unit_plan_approval_accepts_test_case_design_architecture_refs(tmp_path: Path) -> None:
    requirements = tmp_path / 'requirements-and-acceptance.md'
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: integration]: 六步 UX 清楚展示。\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| AC-1 | PD-AC1-six-step-flow | TA-AC1-state-model | runtime design and module boundary |\n',
        encoding='utf-8',
    )
    unit_plan = tmp_path / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n', encoding='utf-8')
    state = {
        'units': [
            {
                'id': 'unit-01',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-1',
                        'acceptance_criterion': 'AC-1',
                        'product_design_refs': ['PD-AC1-six-step-flow'],
                        'technical_architecture_refs': ['TA-AC1-state-model'],
                        'layer': 'integration',
                        'command': 'pytest tests/test_delivery.py -q',
                        'expected': 'AO-001 works',
                    }
                ],
            }
        ]
    }

    validate_unit_plan_design_architecture_traceability(requirements, unit_plan, state)


def test_unit_plan_approval_accepts_markdown_heading_trace_refs_from_requirements(tmp_path: Path) -> None:
    requirements = tmp_path / 'requirements-and-acceptance.md'
    requirements.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-1 [verification: functional]: 上游 HTTP 错误分类。\n\n'
        '## Design/Architecture Traceability Matrix\n'
        '| AC | Product Design Ref | Technical Architecture Ref | Notes |\n'
        '| --- | --- | --- | --- |\n'
        '| `AC-1` | `## 7. 产品设计概要` / `PDR-01 失败诊断卡片` | '
        '`## 8. 架构概要` / `TAR-01 诊断分类器模块边界`、`TAR-02 日志输入到诊断输出数据流` | '
        '覆盖上游 HTTP 错误诊断。 |\n',
        encoding='utf-8',
    )
    unit_plan = tmp_path / 'unit-plan.md'
    unit_plan.write_text('# Unit Plan\n', encoding='utf-8')
    state = {
        'units': [
            {
                'id': 'unit-v1-5-failure-diagnosis',
                'passes': False,
                'test_cases': [
                    {
                        'id': 'TC-FD-001',
                        'acceptance_criterion': 'AC-1',
                        'product_design_refs': ['## 7. 产品设计概要 / PDR-01 失败诊断卡片'],
                        'technical_architecture_refs': [
                            '## 8. 架构概要 / TAR-01 诊断分类器模块边界',
                            '## 8. 架构概要 / TAR-02 日志输入到诊断输出数据流',
                        ],
                        'layer': 'functional',
                        'command': 'go test ./internal/usagereport/requestlog -run TestDiagnoseFailureClassifiesFixtures -count=1',
                        'expected': 'diagnosis.code=upstream_http_error',
                    }
                ],
            }
        ]
    }

    validate_unit_plan_design_architecture_traceability(requirements, unit_plan, state)
