from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

from workflow_controller.rrc_controller import RalphRefinerController
from workflow_controller.gates.parsers import (
    approve_gate_file,
    extract_unit_plan_state_patch,
    write_gate_file,
)
from workflow_controller.gates.generators import (
    ensure_final_acceptance_gate,
    render_requirements_gate_body,
    render_unit_plan_gate_body,
)
from workflow_controller.prompts.builder import _render_builder_execution_prompt
from workflow_controller.prompts.requirements import _render_requirements_draft_prompt
from workflow_controller.prompts.unit_plan import _render_unit_plan_draft_prompt
from workflow_controller.steps.builder import prepare_builder_prompt


ROOT = Path(__file__).resolve().parents[2]


def run_rrc(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'workflow_controller.rrc_controller', *args],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def _make_target_workspace(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / 'workspace'
    plan_path = workspace / 'approved-plan.md'
    _write(
        plan_path,
        """# Approved Plan

## Step 1.1-delivery
- Goal: Complete delivery acceptance

### Scope
- Produce delivery artifact

### Verification
- python -c "print('verified')"
""",
    )
    return workspace, plan_path


def test_unit_plan_prompt_allows_covered_legacy_units_outside_executable_units(tmp_path: Path) -> None:
    prompt = _render_unit_plan_draft_prompt(
        {
            'requestedOutcome': 'V2.2',
            'feasibleOutcome': 'V2.2',
            'currentUnitId': 'target-v2-2',
            'objectiveCoverage': [
                {'objective': 'Old objective', 'units': ['old-unit'], 'status': 'covered'},
                {'objective': 'New objective', 'units': ['new-unit'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'old-unit', 'name': 'Old unit', 'passes': True},
                {'id': 'target-v2-2', 'name': 'Target unit', 'passes': False},
            ],
        },
        tmp_path / 'requirements.md',
        tmp_path / 'unit-plan-body.md',
    )

    assert '已完成的既有 unit id 如果在 objectiveCoverage 中标记为 `covered`' in prompt
    assert '每个未完成的 `partial` objectiveCoverage unit id 都必须存在于 `units`' in prompt
    assert 'every objectiveCoverage unit id must exist in units' not in prompt


def test_unit_plan_prompt_defect_fix_mode_requires_bug_fix_units_without_requirement_changes(tmp_path: Path) -> None:
    requirements_path = tmp_path / 'requirements.md'
    requirements_path.write_text('# Requirements\n- Approved requirements remain valid.\n', encoding='utf-8')

    prompt = _render_unit_plan_draft_prompt(
        {
            'requestedOutcome': 'V2.2',
            'feasibleOutcome': 'V2.2',
            'currentUnitId': 'v2-2-u5-baidu-search',
            'unitPlanRevisionMode': 'defect_fix',
            'finalAcceptanceRejectionRoute': 'defect_fix',
            'unitPlanRevisionFeedback': 'Final acceptance defects: homepage logo is still text-only; workbench i18n is incomplete.',
            'objectiveCoverage': [
                {'objective': 'i18n coverage', 'units': ['v2-2-u1-i18n-fix'], 'status': 'covered'},
                {'objective': 'logo coverage', 'units': ['v2-2-u2-logo-real'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'v2-2-u1-i18n-fix', 'name': 'i18n', 'passes': True},
                {'id': 'v2-2-u2-logo-real', 'name': 'logo', 'passes': True},
            ],
        },
        requirements_path,
        tmp_path / 'unit-plan-body.md',
    )

    assert '最终验收缺陷修复模式' in prompt
    assert '生成一个或多个只聚焦最终验收缺陷的 bug-fix 单元' in prompt
    assert '不要修改已批准需求，也不要重新解释请求目标' in prompt
    assert '将受影响的已覆盖目标重新打开为 `partial`' in prompt
    assert 'Final acceptance defects: homepage logo is still text-only' in prompt


def test_requirements_and_unit_plan_prompts_include_acceptance_obligation_ledger(tmp_path: Path) -> None:
    requirements_path = tmp_path / 'requirements.md'
    requirements_path.write_text('# Requirements\n\n- AC-1 covers AO-001.\n', encoding='utf-8')
    state = {
        'requestedOutcome': 'V0.3.1',
        'feasibleOutcome': 'V0.3.1',
        'currentUnitId': 'unit-ao-ledger',
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
        ],
        'objectiveCoverage': [
            {'objective': 'AO coverage', 'units': ['unit-ao-ledger'], 'status': 'partial'},
        ],
        'units': [
            {'id': 'unit-ao-ledger', 'name': 'AO Ledger', 'passes': False},
        ],
    }

    requirements_prompt = _render_requirements_draft_prompt(state, tmp_path / 'requirements-body.md')
    unit_plan_prompt = _render_unit_plan_draft_prompt(state, requirements_path, tmp_path / 'unit-plan-body.md')

    assert '# Acceptance Obligation Ledger' in requirements_prompt
    assert 'AO-001: 六步 UX 不清楚' in requirements_prompt
    assert 'Every must AO must be covered by at least one Acceptance Criterion' in requirements_prompt
    assert '# Acceptance Obligation Ledger' in unit_plan_prompt
    assert 'Every must AO must appear in the Unit Plan coverage matrix' in unit_plan_prompt
    assert 'Do not collapse multiple AO items into one vague closure' in unit_plan_prompt



def test_unit_plan_prompt_requires_test_strategy_skill_and_test_case_matrix(tmp_path: Path) -> None:
    requirements_path = tmp_path / 'requirements.md'
    requirements_path.write_text(
        '# Requirements\n\n'
        '## 3. Acceptance Criteria\n'
        '- User can see the real logo on the homepage.\n',
        encoding='utf-8',
    )

    prompt = _render_unit_plan_draft_prompt(
        {
            'requestedOutcome': 'V2.2',
            'feasibleOutcome': 'V2.2',
            'currentUnitId': 'v2-2-u2-logo-real',
            'objectiveCoverage': [
                {'objective': 'logo coverage', 'units': ['v2-2-u2-logo-real'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'v2-2-u2-logo-real', 'name': 'logo', 'passes': False},
            ],
        },
        requirements_path,
        tmp_path / 'unit-plan-body.md',
    )

    assert '使用 `test-strategy` skill' in prompt
    assert '## 测试用例矩阵（Test Case Matrix）' in prompt
    assert 'Acceptance Criterion -> Test Case -> Journey -> Layer -> Command/Evidence -> Expected Result' in prompt
    assert 'JSON `test_cases[]` 中显式写 Journey 映射字段' in prompt
    assert '"test_cases"' in prompt


def test_prompt_contracts_require_ac_mapped_executable_e2e_assertions(tmp_path: Path) -> None:
    requirements_path = tmp_path / 'requirements.md'
    requirements_path.write_text(
        '# 需求与验收确认\n\n'
        '## 3. 验收标准\n'
        '- AC-01：用户导入课程包后，课程列表显示 3 门课程并按更新时间倒序排列。\n',
        encoding='utf-8',
    )
    state = {
        'task_id': 'course-import',
        'requestedOutcome': 'V2.8',
        'feasibleOutcome': 'V2.8',
        'currentUnitId': 'u-e2e-import',
        'workspacePath': str(tmp_path),
        'objectiveCoverage': [
            {'objective': 'AC-01 import course list', 'units': ['u-e2e-import'], 'status': 'partial'},
        ],
        'units': [
            {
                'id': 'u-e2e-import',
                'name': 'course import e2e',
                'passes': False,
                'workflow_validation_level': 'closure',
                'test_cases': [
                    {
                        'id': 'TC-AC-01-e2e',
                        'acceptance_criterion': 'AC-01',
                        'layer': 'e2e',
                        'fixture': 'tests/fixtures/course-import-ac-01.json',
                        'command': 'npx playwright test tests/e2e/ac-01.spec.ts',
                        'expected': '课程列表显示 3 门课程并按更新时间倒序排列',
                    },
                ],
                'verification_commands': ['npx playwright test tests/e2e/ac-01.spec.ts'],
            },
        ],
    }

    requirements_prompt = _render_requirements_draft_prompt(state, tmp_path / 'requirements-body.md')
    unit_plan_prompt = _render_unit_plan_draft_prompt(state, requirements_path, tmp_path / 'unit-plan-body.md')
    builder_prompt = _render_builder_execution_prompt(
        state=state,
        requirements_path=requirements_path,
        requirements_content=requirements_path.read_text(encoding='utf-8'),
        unit_plan_path=tmp_path / 'unit-plan.md',
        unit_plan_content='## 测试用例矩阵（Test Case Matrix）\n| AC-01 | TC-AC-01-e2e | e2e | npx playwright test tests/e2e/ac-01.spec.ts | 课程列表显示 3 门课程并按更新时间倒序排列 |\n',
        original_prompt_path=tmp_path / 'prompt.md',
        original_prompt='实现课程导入验收。',
        previous_failure_feedback='',
    )

    assert '每条验收标准必须有稳定 ID' in requirements_prompt
    assert '每条验收标准必须声明 verification layer' in requirements_prompt
    assert 'unit / functional / integration / e2e / manual' in requirements_prompt
    assert '## 4. 需求可追溯矩阵（Requirements Traceability Matrix）' in requirements_prompt
    assert '| AO | AC | Status | Verification Layer | Evidence/Reason |' in requirements_prompt
    assert 'covered/deferred/rejected/out_of_scope' in requirements_prompt
    assert '## 4.5 设计与架构可追溯矩阵（Design/Architecture Traceability Matrix）' in requirements_prompt
    assert '| AC | Product Design Ref | Technical Architecture Ref | Notes |' in requirements_prompt
    assert '## 4.7 Journey Acceptance Matrix' in requirements_prompt
    assert '| Journey | Title | Status | Steps | AC | Verification Layer | Verification Command | Test Case | Unit |' in requirements_prompt
    assert 'e2e 或 workflow_validation_level=closure' in requirements_prompt
    assert '至少一行 active Journey' in requirements_prompt
    assert '固定测试数据或 fixture' in requirements_prompt
    assert '可断言的期望值' in requirements_prompt
    assert '不能用截图或人工观察替代断言' in requirements_prompt
    assert 'Agent-side requirements clarification' in requirements_prompt
    assert '写正式 Requirements Gate 前，必须先提出简洁、集中的澄清问题' in requirements_prompt
    assert '当前 tmux agent pane' in requirements_prompt
    assert '等待用户回答期间不得写 `DONE_FILE`' in requirements_prompt
    assert '收到用户回答后，再继续生成 Requirements Gate' in requirements_prompt
    assert '用户回答后，将澄清结果写入本 Requirements Gate' in requirements_prompt
    assert '`acceptance_criterion`' in unit_plan_prompt
    assert '`fixture`' in unit_plan_prompt
    assert '`product_design_refs`' in unit_plan_prompt
    assert '`technical_architecture_refs`' in unit_plan_prompt
    assert '测试命令退出码为 0 且断言覆盖 AC' in unit_plan_prompt
    assert '对不适合 E2E 的 AC' in unit_plan_prompt
    requirements_body = render_requirements_gate_body(state)
    unit_plan_body = render_unit_plan_gate_body(state)

    assert 'command 指向的测试文件' in builder_prompt
    assert '覆盖了哪些 AC' in builder_prompt
    assert '不要伪造通过证据' in builder_prompt
    assert '稳定 AC ID' in requirements_body
    assert 'unit / functional / integration / e2e / manual' in requirements_body
    assert '需求可追溯矩阵' in requirements_body
    assert '设计与架构可追溯矩阵' in requirements_body
    assert 'Journey Acceptance Matrix' in requirements_body
    assert '| Journey | Title | Status | Steps | AC | Verification Layer | Verification Command | Test Case | Unit |' in requirements_body
    assert '已澄清事项、关键假设与待确认风险' in requirements_body
    assert '如 agent 在 tmux pane 中向用户提问' in requirements_body
    assert '每个 active must AO' in requirements_body
    assert '截图或人工观察不能替代断言' in requirements_body
    assert '| 验收标准 | 测试用例 | 层级 | 产品设计引用 | 技术架构引用 | 测试数据/Fixture | 命令/证据 | 预期结果 |' in unit_plan_body
    assert 'E2E/closure 测试用例包含 AC、fixture、可执行命令和具体断言' in unit_plan_body


def test_requirements_prompt_requires_clarification_before_gate(tmp_path: Path) -> None:
    state = {
        'requestedOutcome': 'V0.5.4',
        'feasibleOutcome': 'V0.5.4',
        'currentUnitId': 'target-v0-5-4',
        'objectiveCoverage': [
            {'objective': 'Complete V0.5.4 development acceptance', 'units': ['target-v0-5-4'], 'status': 'partial'},
        ],
        'units': [
            {
                'id': 'target-v0-5-4',
                'name': 'V0.5.4 development acceptance',
                'passes': False,
            },
        ],
    }

    prompt = _render_requirements_draft_prompt(state, tmp_path / 'requirements-body.md')

    assert '写正式 Requirements Gate 前，必须先提出简洁、集中的澄清问题' in prompt
    assert '等待用户回答期间不得写 `DONE_FILE`' in prompt
    assert '收到用户回答后，再继续生成 Requirements Gate' in prompt
    assert '第一条回复只能包含澄清问题' in prompt
    assert '不得先读取项目文件、检索代码、生成 Requirements 正文或写入 body_path' in prompt
    assert '「继续」' in prompt
    assert '不能视为有效澄清回答' in prompt
    assert '如果信息足够，直接生成 Requirements Gate' not in prompt
    assert '可用保守假设推进时必须推进' not in prompt
    assert prompt.index('Agent-side requirements clarification') < prompt.index('将 Markdown 正文写入这个精确文件')


def test_requirements_prompt_requires_clarification_results_in_section_4_8(tmp_path: Path) -> None:
    state = {
        'requestedOutcome': 'V0.5.4',
        'feasibleOutcome': 'V0.5.4',
        'currentUnitId': 'target-v0-5-4',
        'objectiveCoverage': [
            {'objective': 'Complete V0.5.4 development acceptance', 'units': ['target-v0-5-4'], 'status': 'partial'},
        ],
        'units': [
            {
                'id': 'target-v0-5-4',
                'name': 'V0.5.4 development acceptance',
                'passes': False,
            },
        ],
    }

    prompt = _render_requirements_draft_prompt(state, tmp_path / 'requirements-body.md')

    assert '## 4.8 已澄清事项、关键假设与待确认风险' in prompt
    assert '用户回答后，将澄清结果写入本 Requirements Gate 的 `## 4.8 已澄清事项、关键假设与待确认风险`' in prompt
    assert '同步反映到需求、范围外、验收标准和测试策略中' in prompt


def test_requirements_dialogue_brief_includes_spec_metadata(tmp_path: Path, monkeypatch) -> None:
    import workflow_controller.steps.requirements as requirements_step
    from workflow_controller.runners import RunnerConfig
    from workflow_controller.runners.base import RunnerResult
    from workflow_controller.steps.requirements import run_requirements_drafter

    spec_path = tmp_path / 'spec.md'
    spec_path.write_text('# Waygate Markdown spec\n\n- Import this spec.\n', encoding='utf-8')
    state = {
        'task_id': 'target-v0-5-6',
        'requestedOutcome': 'V0.5.6',
        'feasibleOutcome': 'V0.5.6',
        'currentUnitId': 'target-v0-5-6',
        'workspacePath': str(tmp_path),
        'agentRunner': 'tmux-claude',
        'agentCommand': 'claude',
        'tmuxTarget': '1.2',
        'requirementsSpec': {
            'path': str(spec_path),
            'hash': 'sha256:abc123',
            'sourceType': 'waygate-markdown',
            'importedAt': '2026-05-14T00:00:00+00:00',
        },
        'units': [{'id': 'target-v0-5-6', 'name': 'Spec intake', 'passes': False}],
    }
    approvals_dir = tmp_path / 'approvals'
    artifacts_dir = tmp_path / 'artifacts'

    def fake_make_runner(_state: dict) -> RunnerConfig:
        return RunnerConfig(backend='tmux-claude', agent_command='fake-claude', tmux_target='1.2')

    def fake_run_agent_backend(request):
        body_path = artifacts_dir / 'requirements-draft' / 'requirements-body.md'
        body_path.write_text('# 需求与验收确认\n\n## 1. 需求\n- Generated from spec.\n', encoding='utf-8')
        return RunnerResult(
            backend='tmux-claude',
            status='done',
            command=['fake-claude'],
            returncode=0,
            stdout='ok',
            stderr='',
            run_dir=artifacts_dir / 'requirements-draft' / 'run-1',
            prompt_path=request.prompt_path,
            done_payload={'status': 'done'},
            runner_metadata={'fake': True},
        )

    monkeypatch.setattr(requirements_step, 'make_runner', fake_make_runner)
    monkeypatch.setattr(requirements_step, 'run_agent_backend', fake_run_agent_backend)

    run_requirements_drafter(state, approvals_dir, artifacts_dir)

    brief = (artifacts_dir / 'requirements-dialogue-brief' / 'requirements-dialogue-brief.md').read_text(encoding='utf-8')
    prompt = (artifacts_dir / 'requirements-draft' / 'requirements-draft-prompt.md').read_text(encoding='utf-8')
    summary = json.loads((artifacts_dir / 'requirements-draft' / 'requirements-draft-summary.json').read_text(encoding='utf-8'))

    for content in (brief, prompt):
        assert str(spec_path) in content
        assert 'sha256:abc123' in content
        assert 'waygate-markdown' in content
        assert 'Read the Waygate Markdown spec file' in content
    assert summary['requirements_spec']['path'] == str(spec_path)
    assert summary['requirements_spec']['hash'] == 'sha256:abc123'
    assert summary['requirements_spec']['sourceType'] == 'waygate-markdown'


def test_requirements_prompt_with_spec_skips_mandatory_clarification_and_expands_matrices(tmp_path: Path) -> None:
    spec_path = tmp_path / 'spec.md'
    spec_path.write_text('# Spec\n\n## Requirements\n- Use spec facts.\n', encoding='utf-8')
    state = {
        'requestedOutcome': 'V0.5.6',
        'feasibleOutcome': 'V0.5.6',
        'currentUnitId': 'target-v0-5-6',
        'requirementsSpec': {
            'path': str(spec_path),
            'hash': 'sha256:abc123',
            'sourceType': 'waygate-markdown',
            'importedAt': '2026-05-14T00:00:00+00:00',
        },
        'units': [{'id': 'target-v0-5-6', 'name': 'Spec intake', 'passes': False}],
    }

    prompt = _render_requirements_draft_prompt(state, tmp_path / 'requirements-body.md')

    assert 'Read the Waygate Markdown spec file' in prompt
    assert str(spec_path) in prompt
    assert 'directly expand Requirements, AO, AC, Journey, Design/Architecture, and Test Strategy matrices' in prompt
    assert '## 4. 需求可追溯矩阵（Requirements Traceability Matrix）' in prompt
    assert '## 4.5 设计与架构可追溯矩阵（Design/Architecture Traceability Matrix）' in prompt
    assert '## 4.7 Journey Acceptance Matrix' in prompt
    assert '写正式 Requirements Gate 前，必须先提出简洁、集中的澄清问题' not in prompt
    assert '等待用户回答期间不得写 `DONE_FILE`' not in prompt


def test_requirements_prompt_without_spec_keeps_agent_side_clarification(tmp_path: Path) -> None:
    state = {
        'requestedOutcome': 'V0.5.6',
        'feasibleOutcome': 'V0.5.6',
        'currentUnitId': 'target-v0-5-6',
        'units': [{'id': 'target-v0-5-6', 'name': 'No spec path', 'passes': False}],
    }

    prompt = _render_requirements_draft_prompt(state, tmp_path / 'requirements-body.md')

    assert 'Agent-side requirements clarification' in prompt
    assert '写正式 Requirements Gate 前，必须先提出简洁、集中的澄清问题' in prompt
    assert '等待用户回答期间不得写 `DONE_FILE`' in prompt
    assert '收到用户回答后，再继续生成 Requirements Gate' in prompt
    assert '不得先读取项目文件、检索代码、生成 Requirements 正文或写入 body_path' in prompt
    assert '如果用户只回复「继续」' in prompt
    assert '必须继续追问或写 blocked DONE_FILE' in prompt
    assert '## 4.8 已澄清事项、关键假设与待确认风险' in prompt


def test_requirements_and_unit_plan_prompts_require_simplified_chinese(tmp_path: Path) -> None:
    state = {
        'requestedOutcome': '2.5',
        'feasibleOutcome': '2.5',
        'currentUnitId': 'target-2-5',
        'objectiveCoverage': [
            {'objective': '完成 2.5 验收', 'units': ['target-2-5'], 'status': 'partial'},
        ],
        'units': [
            {
                'id': 'target-2-5',
                'name': '2.5 验收',
                'passes': False,
                'verification_commands': ['pnpm exec tsc --noEmit'],
            },
        ],
    }
    requirements_path = tmp_path / 'requirements.md'
    requirements_path.write_text('# 需求与验收确认\n\n## 4. 测试策略（Test Strategy）\n- unit tests\n', encoding='utf-8')

    requirements_prompt = _render_requirements_draft_prompt(state, tmp_path / 'requirements-body.md')
    unit_plan_prompt = _render_unit_plan_draft_prompt(state, requirements_path, tmp_path / 'unit-plan-body.md')

    assert '使用简体中文' in requirements_prompt
    assert '# 需求与验收确认' in requirements_prompt
    assert '## 4. 需求可追溯矩阵（Requirements Traceability Matrix）' in requirements_prompt
    assert '## 5. 测试策略（Test Strategy）' in requirements_prompt
    assert '## 7. 产品设计概要' in requirements_prompt
    assert '## 8. 架构概要' in requirements_prompt
    assert '## 9. 人工审阅清单' in requirements_prompt
    assert '使用简体中文' in unit_plan_prompt
    assert '# 单元计划确认（Unit Plan Confirmation）' in unit_plan_prompt
    assert '## 测试用例矩阵（Test Case Matrix）' in unit_plan_prompt


def test_controller_generated_gate_bodies_are_chinese_first(tmp_path: Path) -> None:
    state = {
        'requestedOutcome': '2.5',
        'feasibleOutcome': '2.5',
        'currentUnitId': 'target-2-5',
        'currentStep': 'WAITING_FINAL_ACCEPTANCE',
        'status': 'active',
        'objectiveCoverage': [
            {'objective': '完成 2.5 验收', 'units': ['target-2-5'], 'status': 'covered'},
        ],
        'units': [
            {
                'id': 'target-2-5',
                'name': '2.5 验收',
                'passes': True,
                'done_when': ['验收证据完整'],
                'test_cases': [
                    {
                        'id': 'TC-AC-01-golden-path',
                        'acceptance_criterion': 'AC-01',
                        'layer': 'e2e',
                        'golden_path': True,
                        'fixture': 'tests/fixtures/ac-01.json',
                        'command': 'pnpm exec playwright test tests/e2e/ac-01.spec.ts',
                        'expected': '用户完成正常流程并看到结果 2.5',
                    }
                ],
                'verification_commands': ['DATABASE_URL=postgres://test pnpm exec playwright test tests/e2e/ac-01.spec.ts'],
            },
        ],
    }

    requirements_body = render_requirements_gate_body(state)
    unit_plan_body = render_unit_plan_gate_body(state)
    artifacts_dir = tmp_path / 'artifacts'
    unit_dir = artifacts_dir / 'target-2-5'
    unit_dir.mkdir(parents=True)
    (unit_dir / 'verification.json').write_text(
        json.dumps(
            {
                'passed': True,
                'results': [
                    {
                        'command': 'DATABASE_URL=postgres://test pnpm exec playwright test tests/e2e/ac-01.spec.ts',
                        'ok': True,
                        'returncode': 0,
                    }
                ],
            }
        ),
        encoding='utf-8',
    )
    final_path = ensure_final_acceptance_gate(state, tmp_path / 'approvals', artifacts_dir)
    final_body = final_path.read_text(encoding='utf-8')

    assert '# 需求与验收确认' in requirements_body
    assert '## 4. 需求可追溯矩阵（Requirements Traceability Matrix）' in requirements_body
    assert '## 5. 测试策略（Test Strategy）' in requirements_body
    assert '## 7. 产品设计概要' in requirements_body
    assert '## 8. 架构概要' in requirements_body
    assert '## 9. 人工审阅清单' in requirements_body
    assert '# 单元计划确认（Unit Plan Confirmation）' in unit_plan_body
    assert '## 附录 A：目标覆盖矩阵' in unit_plan_body
    assert '## Controller State Patch' in unit_plan_body
    assert '# 最终验收确认' in final_body
    assert '## 证据摘要' in final_body
    assert '## Golden Path 正常流程' in final_body
    assert 'TC-AC-01-golden-path' in final_body
    assert '`pnpm exec playwright test tests/e2e/ac-01.spec.ts` -> passed' in final_body
    assert '## 返工路由（Rejection Routing）' in final_body
    assert '需求变更:' in final_body


def _generate_requirements_gate(state_dir: Path) -> None:
    draft_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert draft_result.returncode == 0, draft_result.stderr
    assert 'currentStep=WAITING_REQUIREMENTS_ACCEPTANCE' in draft_result.stdout
    assert (state_dir / 'approvals' / 'requirements-and-acceptance.md').exists()


def test_target_init_requires_requirements_acceptance_gate(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    state_dir = tmp_path / '.rrc-controller'

    result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--runner',
        'subprocess',
        '--target',
        '1.1',
        '--force',
    )

    assert result.returncode == 0, result.stderr
    assert 'currentStep=REQUIREMENTS_DRAFT' in result.stdout
    assert 'nextAction=run_requirements_drafter' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['humanGatesRequired'] is True
    assert state['requirementsDraftGenerated'] is False
    assert state['requirementsAccepted'] is False
    assert not (state_dir / 'approvals' / 'requirements-and-acceptance.md').exists()


def test_auto_approve_does_not_skip_requirements_acceptance_gate(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    state_dir = tmp_path / '.rrc-controller'
    init_result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--runner',
        'subprocess',
        '--target',
        '1.1',
        '--auto-approve',
        '--force',
    )
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')

    assert result.returncode == 0, result.stderr
    assert 'currentStep=WAITING_REQUIREMENTS_ACCEPTANCE' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['requirementsAccepted'] is False


def test_tmux_claude_generates_requirements_gate_body(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    fake_tmux = tmp_path / 'tmux'
    _write(
        fake_tmux,
        """#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

if sys.argv[1:2] == ["paste-buffer"]:
    prompt = (Path(os.environ["RRC_RUN_DIR"]) / "prompt.md").read_text(encoding="utf-8")
    match = re.search(r"Write the Markdown body to this exact file:\\n(.+)", prompt)
    body_path = Path(match.group(1).strip())
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_text(
        "# Requirements & Acceptance Confirmation\\n\\n"
        "## 1. Requirements\\n- Generated by Claude from target context.\\n\\n"
        "## 2. User Journeys\\n- User completes delivery acceptance.\\n\\n"
        "## 3. Acceptance Criteria\\n- Delivery evidence is verified.\\n\\n"
        "## 4. Test Strategy\\n- Run the declared verification command.\\n\\n"
        "## 5. Out of Scope\\n- Future units.\\n\\n"
        "## 6. Human Review Checklist\\n- [ ] Draft reviewed.\\n",
        encoding="utf-8",
    )
    Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
        json.dumps({"status": "done", "summary": "requirements generated", "run_id": os.environ["RRC_RUN_ID"]}),
        encoding="utf-8",
    )
""",
    )
    fake_tmux.chmod(fake_tmux.stat().st_mode | stat.S_IXUSR)
    state_dir = tmp_path / '.rrc-controller'
    init_result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--target',
        '1.1',
        '--runner',
        'tmux-claude',
        '--tmux-target',
        '1.2',
        '--agent',
        str(fake_tmux),
        '--force',
    )
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')

    assert result.returncode == 0, result.stderr
    assert 'currentStep=WAITING_REQUIREMENTS_ACCEPTANCE' in result.stdout
    gate_content = (state_dir / 'approvals' / 'requirements-and-acceptance.md').read_text(encoding='utf-8')
    assert 'Generated by Claude from target context.' in gate_content
    assert 'Status: pending' in gate_content
    summary = json.loads((state_dir / 'artifacts' / 'requirements-draft' / 'requirements-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['mode'] == 'tmux-claude'


def test_revise_requirements_gate_reruns_tmux_drafter_with_human_feedback(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    fake_tmux = tmp_path / 'tmux'
    _write(
        fake_tmux,
        """#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

if sys.argv[1:2] == ["paste-buffer"]:
    prompt = (Path(os.environ["RRC_RUN_DIR"]) / "prompt.md").read_text(encoding="utf-8")
    match = re.search(r"Write the Markdown body to this exact file:\\n(.+)", prompt)
    if match:
        body_path = Path(match.group(1).strip())
        body_path.parent.mkdir(parents=True, exist_ok=True)
        if "please add retry path" in prompt:
            requirement = "Revised by Claude from human feedback."
            journey = "User retries after a temporary failure."
        else:
            requirement = "Initial Claude draft."
            journey = "User completes delivery acceptance."
        body_path.write_text(
            "# Requirements & Acceptance Confirmation\\n\\n"
            f"## 1. Requirements\\n- {requirement}\\n\\n"
            f"## 2. User Journeys\\n- {journey}\\n\\n"
            "## 3. Acceptance Criteria\\n- Delivery evidence is verified.\\n\\n"
            "## 4. Test Strategy\\n- Run the declared verification command.\\n\\n"
            "## 5. Out of Scope\\n- Future units.\\n\\n"
            "## 6. Product Design Summary\\n- Core flow is visible to reviewers.\\n\\n"
            "## 7. Architecture Summary\\n- Module boundaries and data flow are summarized.\\n\\n"
            "## 8. Human Review Checklist\\n- [ ] Draft reviewed.\\n",
            encoding="utf-8",
        )
        Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
            json.dumps({"status": "done", "summary": "requirements generated", "run_id": os.environ["RRC_RUN_ID"]}),
            encoding="utf-8",
        )
        raise SystemExit(0)
raise SystemExit(0)
""",
    )
    fake_tmux.chmod(fake_tmux.stat().st_mode | stat.S_IXUSR)
    state_dir = tmp_path / '.rrc-controller'
    init_result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--target',
        '1.1',
        '--runner',
        'tmux-claude',
        '--tmux-target',
        '1.2',
        '--agent',
        str(fake_tmux),
        '--force',
    )
    assert init_result.returncode == 0, init_result.stderr
    draft_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert draft_result.returncode == 0, draft_result.stderr

    gate_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    gate_path.write_text(
        gate_path.read_text(encoding='utf-8').replace(
            'Initial Claude draft.',
            'Initial Claude draft.\n\nReviewer note: please add retry path.',
        ),
        encoding='utf-8',
    )

    result = run_rrc('revise', '--state-dir', str(state_dir), '--gate', 'requirements')

    assert result.returncode == 0, result.stderr
    assert 'gate=requirements status=revised' in result.stdout
    gate_content = gate_path.read_text(encoding='utf-8')
    assert 'Revised by Claude from human feedback.' in gate_content
    assert 'User retries after a temporary failure.' in gate_content
    assert 'Status: pending' in gate_content
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert state['requirementsAccepted'] is False
    revision_path = state_dir / 'artifacts' / 'requirements-revisions' / 'revision-1.json'
    assert revision_path.exists()
    revision = json.loads(revision_path.read_text(encoding='utf-8'))
    assert revision['revision_count'] == 1
    assert revision['source_gate'] == 'requirements'
    assert revision['previous_gate_path'] == str(gate_path)
    assert revision['updated_gate_path'] == str(gate_path)
    assert 'please add retry path' in revision['feedback']
    assert revision['controller_validation_error'] is None
    assert len(revision['before_hash']) == 64
    assert len(revision['after_hash']) == 64
    assert revision['before_hash'] != revision['after_hash']
    assert revision['changed'] is True
    assert '- Revised by Claude from human feedback.' in revision['diff_summary']['added_lines']
    assert '- User retries after a temporary failure.' in revision['diff_summary']['added_lines']
    assert '- Initial Claude draft.' in revision['diff_summary']['removed_lines']
    assert 'Reviewer note: please add retry path.' in revision['diff_summary']['removed_lines']
    assert '## 1. Requirements' in revision['diff_summary']['changed_sections']
    assert '## 2. User Journeys' in revision['diff_summary']['changed_sections']

    index_path = state_dir / 'artifacts' / 'requirements-revisions' / 'requirements-revisions.md'
    index = index_path.read_text(encoding='utf-8')
    assert 'revision-1.json' in index
    assert 'changed: true' in index
    assert 'before:' in index
    assert 'after:' in index

    events = [
        json.loads(line)
        for line in (state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    revised_event = [event for event in events if event['type'] == 'requirements_draft_revised'][-1]
    assert revised_event['payload']['revision_artifact'] == str(revision_path)
    assert revised_event['payload']['change_request_id'] == 'CR-0001'

    change_requests_path = state_dir / 'change_requests.jsonl'
    change_requests = [
        json.loads(line)
        for line in change_requests_path.read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    assert len(change_requests) == 1
    change_request = change_requests[0]
    assert change_request['id'] == 'CR-0001'
    assert change_request['source'] == 'requirements_revision'
    assert change_request['source_gate'] == 'requirements'
    assert change_request['source_ref'] == 'requirements:revision-1'
    assert change_request['reason'].startswith('# Requirements & Acceptance Confirmation')
    assert 'please add retry path' in change_request['reason']
    assert change_request['status'] == 'pending_requirements_approval'
    assert change_request['approver'] is None
    assert change_request['revision_artifact'] == str(revision_path)
    assert change_request['previous_gate_path'] == str(gate_path)
    assert change_request['updated_gate_path'] == str(gate_path)
    assert len(change_request['before_hash']) == 64
    assert len(change_request['after_hash']) == 64
    assert change_request['changed'] is True
    assert change_request['impacted'] == {
        'acceptance_obligations': [],
        'acceptance_criteria': [],
        'test_cases': [],
        'journeys': [],
    }


def test_revise_requirements_gate_includes_plannotator_submitted_feedback(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    fake_tmux = tmp_path / 'tmux'
    _write(
        fake_tmux,
        """#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

if sys.argv[1:2] == ["paste-buffer"]:
    prompt = (Path(os.environ["RRC_RUN_DIR"]) / "prompt.md").read_text(encoding="utf-8")
    match = re.search(r"Write the Markdown body to this exact file:\\n(.+)", prompt)
    if match:
        body_path = Path(match.group(1).strip())
        body_path.parent.mkdir(parents=True, exist_ok=True)
        if "please remove the Baidu unit" in prompt:
            requirement = "Revised from local Plannotator feedback."
        else:
            requirement = "Initial Claude draft."
        body_path.write_text(
            "# Requirements & Acceptance Confirmation\\n\\n"
            f"## 1. Requirements\\n- {requirement}\\n\\n"
            "## 2. User Journeys\\n- User completes delivery acceptance.\\n\\n"
            "## 3. Acceptance Criteria\\n- Delivery evidence is verified.\\n\\n"
            "## 4. Test Strategy\\n- Run the declared verification command.\\n\\n"
            "## 5. Out of Scope\\n- Future units.\\n\\n"
            "## 6. Product Design Summary\\n- Core flow is visible to reviewers.\\n\\n"
            "## 7. Architecture Summary\\n- Module boundaries and data flow are summarized.\\n\\n"
            "## 8. Human Review Checklist\\n- [ ] Draft reviewed.\\n",
            encoding="utf-8",
        )
        Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
            json.dumps({"status": "done", "summary": "requirements generated", "run_id": os.environ["RRC_RUN_ID"]}),
            encoding="utf-8",
        )
        raise SystemExit(0)
raise SystemExit(0)
""",
    )
    fake_tmux.chmod(fake_tmux.stat().st_mode | stat.S_IXUSR)
    state_dir = tmp_path / '.rrc-controller'
    init_result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--target',
        '1.1',
        '--runner',
        'tmux-claude',
        '--tmux-target',
        '1.2',
        '--agent',
        str(fake_tmux),
        '--force',
    )
    assert init_result.returncode == 0, init_result.stderr
    draft_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert draft_result.returncode == 0, draft_result.stderr

    plannotator_dir = state_dir / 'plannotator'
    plannotator_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = plannotator_dir / 'requirements-last-review.stdout.log'
    stdout_path.write_text(
        json.dumps(
            {
                'decision': 'annotated',
                'feedback': '- please remove the Baidu unit before regenerating requirements.',
            }
        ),
        encoding='utf-8',
    )
    (plannotator_dir / 'requirements-last-review.json').write_text(
        json.dumps(
            {
                'gate': 'requirements',
                'gate_path': str(state_dir / 'approvals' / 'requirements-and-acceptance.md'),
                'stdout_path': str(stdout_path),
                'process_id': None,
            }
        ),
        encoding='utf-8',
    )

    result = run_rrc('revise', '--state-dir', str(state_dir), '--gate', 'requirements')

    assert result.returncode == 0, result.stderr
    gate_content = (state_dir / 'approvals' / 'requirements-and-acceptance.md').read_text(encoding='utf-8')
    assert 'Revised from local Plannotator feedback.' in gate_content
    assert not (plannotator_dir / 'requirements-last-review.json').exists()
    assert (plannotator_dir / 'requirements-last-review-used-1.json').exists()


def test_revise_requirements_gate_creates_distinct_obligations_from_plannotator_annotations(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    fake_tmux = tmp_path / 'tmux'
    _write(
        fake_tmux,
        """#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

if sys.argv[1:2] == ["paste-buffer"]:
    prompt = (Path(os.environ["RRC_RUN_DIR"]) / "prompt.md").read_text(encoding="utf-8")
    match = re.search(r"Write the Markdown body to this exact file:\\n(.+)", prompt)
    if match:
        body_path = Path(match.group(1).strip())
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_text(
            "# Requirements & Acceptance Confirmation\\n\\n"
            "## 1. Requirements\\n- Revised from annotation feedback.\\n\\n"
            "## 2. User Journeys\\n- User completes delivery acceptance.\\n\\n"
            "## 3. Acceptance Criteria\\n- Delivery evidence is verified.\\n\\n"
            "## 4. Test Strategy\\n- Run the declared verification command.\\n\\n"
            "## 5. Out of Scope\\n- Future units.\\n\\n"
            "## 6. Product Design Summary\\n- Core flow is visible to reviewers.\\n\\n"
            "## 7. Architecture Summary\\n- Module boundaries and data flow are summarized.\\n\\n"
            "## 8. Human Review Checklist\\n- [ ] Draft reviewed.\\n",
            encoding="utf-8",
        )
        Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
            json.dumps({"status": "done", "summary": "requirements generated", "run_id": os.environ["RRC_RUN_ID"]}),
            encoding="utf-8",
        )
        raise SystemExit(0)
raise SystemExit(0)
""",
    )
    fake_tmux.chmod(fake_tmux.stat().st_mode | stat.S_IXUSR)
    state_dir = tmp_path / '.rrc-controller'
    init_result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--target',
        '1.1',
        '--runner',
        'tmux-claude',
        '--tmux-target',
        '1.2',
        '--agent',
        str(fake_tmux),
        '--force',
    )
    assert init_result.returncode == 0, init_result.stderr
    draft_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert draft_result.returncode == 0, draft_result.stderr

    plannotator_dir = state_dir / 'plannotator'
    plannotator_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = plannotator_dir / 'requirements-last-review.stdout.log'
    stdout_path.write_text(
        json.dumps(
            {
                'decision': 'annotated',
                'annotations': [
                    {'quote': 'Step 5', 'comment': '模型选择不清楚'},
                    {'quote': 'Materials', 'comment': '15 个材料没有逐项证明'},
                ],
            }
        ),
        encoding='utf-8',
    )
    (plannotator_dir / 'requirements-last-review.json').write_text(
        json.dumps(
            {
                'gate': 'requirements',
                'gate_path': str(state_dir / 'approvals' / 'requirements-and-acceptance.md'),
                'stdout_path': str(stdout_path),
                'process_id': None,
            }
        ),
        encoding='utf-8',
    )

    result = run_rrc('revise', '--state-dir', str(state_dir), '--gate', 'requirements')

    assert result.returncode == 0, result.stderr
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    obligations = state['acceptanceObligations']
    assert [item['id'] for item in obligations] == ['AO-001', 'AO-002']
    assert [item['title'] for item in obligations] == ['模型选择不清楚', '15 个材料没有逐项证明']
    ledger = state_dir / 'artifacts' / 'acceptance-obligations' / 'acceptance-obligations.md'
    assert 'Quote: Step 5' in ledger.read_text(encoding='utf-8')


def test_revise_requirements_gate_uses_only_plannotator_feedback_for_obligations(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    fake_tmux = tmp_path / 'tmux'
    _write(
        fake_tmux,
        """#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

if sys.argv[1:2] == ["paste-buffer"]:
    prompt = (Path(os.environ["RRC_RUN_DIR"]) / "prompt.md").read_text(encoding="utf-8")
    match = re.search(r"Write the Markdown body to this exact file:\\n(.+)", prompt)
    if match:
        body_path = Path(match.group(1).strip())
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_text(
            "# Requirements & Acceptance Confirmation\\n\\n"
            "## 1. Requirements\\n- Generated requirement bullet.\\n\\n"
            "## 2. User Journeys\\n- Generated journey bullet.\\n\\n"
            "## 3. Acceptance Criteria\\n- AC-1 [verification: manual]: Generated AC.\\n\\n"
            "## 4. Requirements Traceability Matrix\\n"
            "| AO | AC | Status | Verification Layer | Evidence/Reason |\\n"
            "| --- | --- | --- | --- | --- |\\n\\n"
            "## 4.5 Design/Architecture Traceability Matrix\\n"
            "| AC | Product Design Ref | Technical Architecture Ref | Notes |\\n"
            "| --- | --- | --- | --- |\\n"
            "| AC-1 | Product design summary | Architecture summary | ok |\\n\\n"
            "## 5. Test Strategy\\n- Generated test strategy bullet.\\n",
            encoding="utf-8",
        )
        Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
            json.dumps({"status": "done", "summary": "requirements generated", "run_id": os.environ["RRC_RUN_ID"]}),
            encoding="utf-8",
        )
        raise SystemExit(0)
raise SystemExit(0)
""",
    )
    fake_tmux.chmod(fake_tmux.stat().st_mode | stat.S_IXUSR)
    state_dir = tmp_path / '.rrc-controller'
    init_result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--target',
        '1.1',
        '--runner',
        'tmux-claude',
        '--tmux-target',
        '1.2',
        '--agent',
        str(fake_tmux),
        '--force',
    )
    assert init_result.returncode == 0, init_result.stderr
    draft_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert draft_result.returncode == 0, draft_result.stderr

    plannotator_dir = state_dir / 'plannotator'
    plannotator_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = plannotator_dir / 'requirements-last-review.stdout.log'
    stdout_path.write_text(
        '# File Feedback\n'
        "I've reviewed this file and have 2 pieces of feedback:\n\n"
        '## 1. General feedback about the file\n'
        '> 这个需求就是瞎扯淡\n\n'
        '## 2. General feedback about the file\n'
        '> 这才是我要的需求：\n'
        '> - 默认只展示 changed / added / removed。\n',
        encoding='utf-8',
    )
    (plannotator_dir / 'requirements-last-review.json').write_text(
        json.dumps(
            {
                'gate': 'requirements',
                'gate_path': str(state_dir / 'approvals' / 'requirements-and-acceptance.md'),
                'stdout_path': str(stdout_path),
                'process_id': None,
            }
        ),
        encoding='utf-8',
    )

    result = run_rrc('revise', '--state-dir', str(state_dir), '--gate', 'requirements')

    assert result.returncode == 0, result.stderr
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    obligations = state['acceptanceObligations']
    assert [item['title'] for item in obligations] == [
        '这个需求就是瞎扯淡',
        '这才是我要的需求：',
    ]
    assert all('Generated requirement bullet' not in item['description'] for item in obligations)


def test_revise_requirements_gate_can_rewind_from_unit_plan_approval(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    state_dir = tmp_path / '.rrc-controller'
    init_result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--runner',
        'subprocess',
        '--target',
        '1.1',
        '--force',
    )
    assert init_result.returncode == 0, init_result.stderr
    _generate_requirements_gate(state_dir)
    approve_gate_file(state_dir / 'approvals' / 'requirements-and-acceptance.md', actor='tester')
    req_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert req_result.returncode == 0, req_result.stderr
    assert 'currentStep=UNIT_PLAN_DRAFT' in req_result.stdout
    unit_plan_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert unit_plan_result.returncode == 0, unit_plan_result.stderr
    assert 'currentStep=WAITING_UNIT_PLAN_APPROVAL' in unit_plan_result.stdout

    gate_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    gate_path.write_text(
        gate_path.read_text(encoding='utf-8').replace(
            'Requirements are accurate.',
            'Requirements need one more revision note.',
        ),
        encoding='utf-8',
    )

    result = run_rrc('revise', '--state-dir', str(state_dir), '--gate', 'requirements')

    assert result.returncode == 0, result.stderr
    assert 'gate=requirements status=revised' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert state['requirementsAccepted'] is False
    assert state['unitPlanAccepted'] is False


def test_revise_requirements_gate_can_rewind_from_plan_approved_with_reason(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'target-v1-8-1',
            'currentUnitId': 'unit-01',
            'currentStep': 'PLAN_APPROVED',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'V1.8.1',
            'feasibleOutcome': 'V1.8.1',
            'scopeApproved': True,
            'agentRunner': 'subprocess',
            'workspacePath': str(workspace),
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'requirementsAcceptedHash': 'sha256:req-approved',
            'requirementsAcceptedBy': 'human',
            'unitPlanAccepted': True,
            'unitPlanAcceptedHash': 'sha256:unit-approved',
            'unitPlanAcceptedBy': 'human',
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text(
        '# Requirements & Acceptance Confirmation\n\n'
        '- Must use the CLI Proxy Management API for disable/restore.\n',
        encoding='utf-8',
    )
    (approvals_dir / 'unit-plan.md').write_text(
        '# Unit Plan Confirmation\n\n'
        '- Keep the approved API-only proxy implementation plan.\n',
        encoding='utf-8',
    )
    reason = '允许保留副本 + 删除/创建作为 disable/restore 替代策略。'

    result = run_rrc(
        'revise',
        '--state-dir',
        str(state_dir),
        '--gate',
        'requirements',
        '--reason',
        reason,
    )

    assert result.returncode == 0, result.stderr
    assert 'gate=requirements status=revised' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    assert state['requirementsAccepted'] is False
    assert state['unitPlanAccepted'] is False
    assert 'requirementsAcceptedHash' not in state
    assert 'unitPlanAcceptedHash' not in state
    assert state['requirementsRevisionCount'] == 1
    assert not (approvals_dir / 'unit-plan.md').exists()
    revision = json.loads((state_dir / 'artifacts' / 'requirements-revisions' / 'revision-1.json').read_text(encoding='utf-8'))
    assert reason in revision['feedback']
    assert '这是 approved Requirements 后的需求变更，不是 Unit Plan 返工' in revision['feedback']
    change_request = json.loads((state_dir / 'change_requests.jsonl').read_text(encoding='utf-8').splitlines()[0])
    assert change_request['status'] == 'pending_requirements_approval'
    assert reason in change_request['reason']


def test_revise_requirements_gate_rejects_direct_final_acceptance_rewind(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_FINAL_ACCEPTANCE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'agentRunner': 'subprocess',
            'workspacePath': str(workspace),
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': True},
            ],
        },
        force=True,
    )
    approvals_dir = state_dir / 'approvals'
    approvals_dir.mkdir(parents=True, exist_ok=True)
    (approvals_dir / 'requirements-and-acceptance.md').write_text('# Requirements\n', encoding='utf-8')

    result = run_rrc(
        'revise',
        '--state-dir',
        str(state_dir),
        '--gate',
        'requirements',
        '--reason',
        'change requirements from final acceptance',
    )

    assert result.returncode != 0
    assert 'final acceptance rejection route' in result.stderr
    assert 'Traceback' not in result.stderr


def test_revise_unit_plan_gate_reruns_tmux_drafter_with_human_feedback(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    fake_tmux = tmp_path / 'tmux'
    _write(
        fake_tmux,
        """#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

if sys.argv[1:2] == ["paste-buffer"]:
    prompt = (Path(os.environ["RRC_RUN_DIR"]) / "prompt.md").read_text(encoding="utf-8")
    match = re.search(r"Write the Markdown body to this exact file:\\n(.+)", prompt)
    if not match:
        match = re.search(r"Write the Unit Plan Markdown body to this exact file:\\n(.+)", prompt)
    if match:
        body_path = Path(match.group(1).strip())
        body_path.parent.mkdir(parents=True, exist_ok=True)
        if "Unit Plan" in prompt:
            if "please split closure evidence" in prompt:
                unit_line = "Revised unit plan with separate closure evidence."
                unit_json = (
                    '{"currentUnitId":"target-1-1",'
                    '"objectiveCoverage":[{"objective":"Delivery objective","units":["target-1-1","target-1-1-e2e"],"status":"partial"}],'
                    '"units":[{"id":"target-1-1","name":"Implementation","passes":false},'
                    '{"id":"target-1-1-e2e","name":"Closure evidence","passes":false,"workflow_validation_level":"closure"}]}'
                )
            else:
                unit_line = "Initial unit plan."
                unit_json = (
                    '{"currentUnitId":"target-1-1",'
                    '"objectiveCoverage":[{"objective":"Delivery objective","units":["target-1-1"],"status":"partial"}],'
                    '"units":[{"id":"target-1-1","name":"Implementation","passes":false}]}'
                )
            body = (
                "# Unit Plan Confirmation\\n\\n"
                "## Objective Coverage Matrix\\n- Delivery objective mapped.\\n\\n"
                f"## Units\\n- {unit_line}\\n\\n"
                "## Controller State Patch\\n\\n"
                "```json\\n"
                f"{unit_json}\\n"
                "```\\n\\n"
                "## Human Review Checklist\\n- [ ] Unit plan reviewed.\\n"
            )
        else:
            body = (
                "# Requirements & Acceptance Confirmation\\n\\n"
                "## 1. Requirements\\n- Generated requirements.\\n\\n"
                "## 2. User Journeys\\n- Generated journey.\\n\\n"
                "## 3. Acceptance Criteria\\n- Generated acceptance.\\n\\n"
                "## 4. Test Strategy\\n- Generated tests.\\n\\n"
                "## 5. Out of Scope\\n- Future units.\\n\\n"
                "## 6. Product Design Summary\\n- Core flow is visible to reviewers.\\n\\n"
                "## 7. Architecture Summary\\n- Module boundaries and data flow are summarized.\\n\\n"
                "## 8. Human Review Checklist\\n- [ ] Requirements reviewed.\\n"
            )
        body_path.write_text(body, encoding="utf-8")
        Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
            json.dumps({"status": "done", "summary": "draft generated", "run_id": os.environ["RRC_RUN_ID"]}),
            encoding="utf-8",
        )
        raise SystemExit(0)
raise SystemExit(0)
""",
    )
    fake_tmux.chmod(fake_tmux.stat().st_mode | stat.S_IXUSR)
    state_dir = tmp_path / '.rrc-controller'
    init_result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--target',
        '1.1',
        '--runner',
        'tmux-claude',
        '--tmux-target',
        '1.2',
        '--agent',
        str(fake_tmux),
        '--force',
    )
    assert init_result.returncode == 0, init_result.stderr
    _generate_requirements_gate(state_dir)
    approve_gate_file(state_dir / 'approvals' / 'requirements-and-acceptance.md', actor='tester')
    req_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert req_result.returncode == 0, req_result.stderr
    unit_plan_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert unit_plan_result.returncode == 0, unit_plan_result.stderr

    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    gate_path.write_text(
        gate_path.read_text(encoding='utf-8').replace(
            'Initial unit plan.',
            'Initial unit plan.\n\nReviewer note: please split closure evidence.',
        ),
        encoding='utf-8',
    )

    result = run_rrc('revise', '--state-dir', str(state_dir), '--gate', 'unit-plan')

    assert result.returncode == 0, result.stderr
    assert 'gate=unit-plan status=revised' in result.stdout
    gate_content = gate_path.read_text(encoding='utf-8')
    assert 'Revised unit plan with separate closure evidence.' in gate_content
    assert 'target-1-1-e2e' in gate_content
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['unitPlanAccepted'] is False


def test_requirements_and_unit_plan_gates_must_be_approved_before_scope(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    state_dir = tmp_path / '.rrc-controller'
    init_result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--runner',
        'subprocess',
        '--target',
        '1.1',
        '--force',
    )
    assert init_result.returncode == 0, init_result.stderr

    _generate_requirements_gate(state_dir)
    approve_gate_file(state_dir / 'approvals' / 'requirements-and-acceptance.md', actor='tester')
    req_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert req_result.returncode == 0, req_result.stderr
    assert 'currentStep=UNIT_PLAN_DRAFT' in req_result.stdout

    unit_plan_draft_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert unit_plan_draft_result.returncode == 0, unit_plan_draft_result.stderr
    assert 'currentStep=WAITING_UNIT_PLAN_APPROVAL' in unit_plan_draft_result.stdout
    assert (state_dir / 'approvals' / 'unit-plan.md').exists()

    approve_gate_file(state_dir / 'approvals' / 'unit-plan.md', actor='tester')
    plan_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert plan_result.returncode == 0, plan_result.stderr
    assert 'currentStep=PLAN_CREATED' in plan_result.stdout
    assert 'nextAction=require_scope_approval' in plan_result.stdout


def test_unit_plan_approval_applies_controller_state_patch(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'old-unit',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Old objective', 'units': ['old-unit'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'old-unit', 'name': 'Old unit', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Objective Coverage Matrix
- Delivery objective -> unit-a, unit-b

## Units
### unit-a - Implementation

### unit-b - E2E closure

## Controller State Patch

```json
{
  "currentUnitId": "unit-a",
  "objectiveCoverage": [
    {
      "objective": "Delivery objective",
      "units": ["unit-a", "unit-b"],
      "status": "partial"
    }
  ],
  "units": [
    {
      "id": "unit-a",
      "name": "Implementation",
      "passes": false,
      "scope": ["Implement the delivery path"],
      "verification_commands": ["pytest tests/test_delivery.py -q"]
    },
    {
      "id": "unit-b",
      "name": "E2E closure",
      "passes": false,
      "workflow_validation_level": "closure",
      "test_cases": [
        {
          "id": "TC-delivery-golden-path",
          "acceptance_criterion": "Delivery objective",
          "layer": "e2e",
          "golden_path": true,
          "fixture": "tests/fixtures/delivery.json",
          "command": "pytest tests/e2e/test_delivery.py -q",
          "expected": "Delivery normal flow completes with confirmation"
        }
      ],
      "verification_commands": ["pytest tests/e2e/test_delivery.py -q"]
    }
  ]
}
```

## Human Review Checklist
- [ ] Reviewed.
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['currentStep'] == 'PLAN_CREATED'
    assert state['unitPlanAccepted'] is True
    assert state['currentUnitId'] == 'unit-a'
    assert [unit['id'] for unit in state['units']] == ['unit-a', 'unit-b']
    assert state['units'][0]['verification_commands'] == ['pytest tests/test_delivery.py -q']
    assert state['objectiveCoverage'] == [
        {'objective': 'Delivery objective', 'units': ['unit-a', 'unit-b'], 'status': 'partial'},
    ]


def test_unit_plan_patch_can_preserve_completed_existing_units_in_coverage(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'target-v2-1',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Old objective', 'units': ['old-unit'], 'status': 'covered'},
                {'objective': 'Target objective', 'units': ['target-v2-1'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'old-unit', 'name': 'Old unit', 'passes': True},
                {'id': 'target-v2-1', 'name': 'Target placeholder', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Controller State Patch

```json
{
  "currentUnitId": "unit-a",
  "objectiveCoverage": [
    {"objective": "Old objective", "units": ["old-unit"], "status": "covered"},
    {"objective": "Delivery objective", "units": ["unit-a"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-a",
      "name": "Implementation",
      "passes": false,
      "scope": ["Implement the delivery path"],
      "verification_commands": ["pytest tests/test_delivery.py -q"]
    }
  ]
}
```
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['currentStep'] == 'PLAN_CREATED'
    assert state['unitPlanAccepted'] is True
    assert state['currentUnitId'] == 'unit-a'
    assert [unit['id'] for unit in state['units']] == ['unit-a', 'old-unit']
    assert state['units'][1]['passes'] is True
    assert state['objectiveCoverage'] == [
        {'objective': 'Old objective', 'units': ['old-unit'], 'status': 'covered'},
        {'objective': 'Delivery objective', 'units': ['unit-a'], 'status': 'partial'},
    ]


def test_unit_plan_patch_allows_partial_rollup_to_reference_completed_existing_units(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'target-v2-2',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'V2.2',
            'feasibleOutcome': 'V2.2',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Completed objective', 'units': ['v2-2-u1'], 'status': 'covered'},
                {'objective': 'Target objective', 'units': ['target-v2-2'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'v2-2-u1', 'name': 'Completed unit', 'passes': True},
                {'id': 'target-v2-2', 'name': 'Target placeholder', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Controller State Patch

```json
{
  "currentUnitId": "v2-2-u2",
  "objectiveCoverage": [
    {"objective": "Completed objective", "units": ["v2-2-u1"], "status": "covered"},
    {"objective": "Complete V2.2", "units": ["v2-2-u1", "v2-2-u2"], "status": "partial"}
  ],
  "units": [
    {
      "id": "v2-2-u2",
      "name": "Remaining unit",
      "passes": false,
      "scope": ["Finish remaining work"],
      "verification_commands": ["pytest tests/test_remaining.py -q"]
    }
  ]
}
```
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['currentStep'] == 'PLAN_CREATED'
    assert state['unitPlanAccepted'] is True
    assert state['currentUnitId'] == 'v2-2-u2'
    assert [unit['id'] for unit in state['units']] == ['v2-2-u2', 'v2-2-u1']
    assert state['units'][1]['passes'] is True
    assert state['objectiveCoverage'] == [
        {'objective': 'Completed objective', 'units': ['v2-2-u1'], 'status': 'covered'},
        {'objective': 'Complete V2.2', 'units': ['v2-2-u1', 'v2-2-u2'], 'status': 'partial'},
    ]


def test_unit_plan_patch_rejects_partial_rollup_with_undeclared_unfinished_unit(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'target-v2-2',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'V2.2',
            'feasibleOutcome': 'V2.2',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Target objective', 'units': ['target-v2-2'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'target-v2-2', 'name': 'Target placeholder', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Controller State Patch

```json
{
  "currentUnitId": "v2-2-u2",
  "objectiveCoverage": [
    {"objective": "Complete V2.2", "units": ["target-v2-2", "v2-2-u2"], "status": "partial"}
  ],
  "units": [
    {
      "id": "v2-2-u2",
      "name": "Remaining unit",
      "passes": false,
      "scope": ["Finish remaining work"],
      "verification_commands": ["pytest tests/test_remaining.py -q"]
    }
  ]
}
```
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['unitPlanAccepted'] is False
    assert 'declare unfinished unit ids in units' in state['blockedReason']
    assert 'target-v2-2' in state['blockedReason']


def test_unit_plan_patch_can_reopen_covered_objective_with_defect_fix_unit(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'v2-2-u1-i18n-fix',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'V2.2',
            'feasibleOutcome': 'V2.2',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'i18n coverage', 'units': ['v2-2-u1-i18n-fix'], 'status': 'covered'},
            ],
            'units': [
                {'id': 'v2-2-u1-i18n-fix', 'name': 'i18n', 'passes': True},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Controller State Patch

```json
{
  "currentUnitId": "v2-2-fix-i18n-acceptance",
  "objectiveCoverage": [
    {
      "objective": "i18n coverage",
      "units": ["v2-2-u1-i18n-fix", "v2-2-fix-i18n-acceptance"],
      "status": "partial"
    }
  ],
  "units": [
    {
      "id": "v2-2-fix-i18n-acceptance",
      "name": "Final acceptance i18n defect fix",
      "passes": false,
      "scope": ["Fix final acceptance i18n gaps"],
      "verification_commands": ["pytest tests/test_i18n.py -q"]
    }
  ]
}
```
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['currentStep'] == 'PLAN_APPROVED'
    assert state['unitPlanAccepted'] is True
    assert [unit['id'] for unit in state['units']] == ['v2-2-fix-i18n-acceptance', 'v2-2-u1-i18n-fix']
    assert state['units'][0]['passes'] is False
    assert state['units'][1]['passes'] is True
    assert state['objectiveCoverage'] == [
        {
            'objective': 'i18n coverage',
            'units': ['v2-2-u1-i18n-fix', 'v2-2-fix-i18n-acceptance'],
            'status': 'partial',
        }
    ]


def test_unit_plan_approval_with_preapproved_scope_advances_to_builder_ready_state(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'v2-2-u4',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'V2.2',
            'feasibleOutcome': 'V2.2',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Completed objective', 'units': ['v2-2-u4'], 'status': 'covered'},
                {'objective': 'Remaining objective', 'units': ['target-v2-2'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'v2-2-u4', 'name': 'Completed unit', 'passes': True},
                {'id': 'target-v2-2', 'name': 'Target placeholder', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Controller State Patch

```json
{
  "currentUnitId": "v2-2-u5",
  "objectiveCoverage": [
    {"objective": "Completed objective", "units": ["v2-2-u4"], "status": "covered"},
    {"objective": "Remaining objective", "units": ["v2-2-u5"], "status": "partial"}
  ],
  "units": [
    {
      "id": "v2-2-u5",
      "name": "Remaining unit",
      "passes": false,
      "scope": ["Finish remaining work"],
      "verification_commands": ["pytest tests/test_remaining.py -q"]
    }
  ]
}
```
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['unitPlanAccepted'] is True
    assert state['currentStep'] == 'PLAN_APPROVED'
    assert state['lastVerifiedStep'] == 'PLAN_CREATED'
    assert state['nextAllowedActions'] == ['run_builder']


def test_status_repairs_preapproved_plan_created_state_to_builder_ready_state(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'v2-2-u5',
            'currentStep': 'PLAN_CREATED',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'V2.2',
            'feasibleOutcome': 'V2.2',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Remaining objective', 'units': ['v2-2-u5'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'v2-2-u5', 'name': 'Remaining unit', 'passes': False},
            ],
        },
        force=True,
    )

    state = controller.get_status()

    assert state['currentStep'] == 'PLAN_APPROVED'
    assert state['nextAction'] == 'run_builder'


def test_unit_plan_state_patch_accepts_chinese_heading() -> None:
    patch = extract_unit_plan_state_patch(
        """# 单元计划确认

## 控制器状态补丁

```json
{
  "currentUnitId": "unit-a",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-a"], "status": "partial"}
  ],
  "units": [
    {"id": "unit-a", "name": "Implementation", "passes": false}
  ]
}
```
"""
    )

    assert patch['currentUnitId'] == 'unit-a'
    assert patch['units'][0]['id'] == 'unit-a'


def test_unit_plan_approval_without_controller_state_patch_stays_waiting(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
            ],
        },
        force=True,
    )
    gate_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        gate_path,
        """# Unit Plan Confirmation

## Objective Coverage Matrix
- Delivery objective -> unit-01

## Units
### unit-01 - Delivery

## Human Review Checklist
- [ ] Reviewed.
""",
    )
    approve_gate_file(gate_path, actor='tester')

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['unitPlanAccepted'] is False
    assert 'Controller State Patch' in state['blockedReason']


def test_unit_plan_approval_enforces_required_test_strategy_layers(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-api',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-api'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-api', 'name': 'API delivery', 'passes': False},
            ],
        },
        force=True,
    )
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        """# Requirements & Acceptance Confirmation

## 1. Requirements
- Delivery works.

## 2. User Journeys
- User completes delivery.

## 3. Acceptance Criteria
- Delivery evidence exists.

## 4. Test Strategy
- Unit tests cover parser behavior.
- E2E tests cover browser delivery.

## 5. Out of Scope
- Future work.
""",
    )
    approve_gate_file(requirements_path, actor='tester')
    unit_plan_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        unit_plan_path,
        """# Unit Plan Confirmation

## Units
### unit-api - API delivery
- Verification commands:
  - `pytest tests/test_parser.py -q`

## Controller State Patch

```json
{
  "currentUnitId": "unit-api",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-api"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-api",
      "name": "API delivery",
      "passes": false,
      "verification_commands": ["pytest tests/test_parser.py -q"]
    }
  ]
}
```
""",
    )
    approve_gate_file(unit_plan_path, actor='tester')

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['unitPlanAccepted'] is False
    assert 'test strategy' in state['blockedReason']
    assert 'e2e' in state['blockedReason'].lower()


def test_unit_plan_approval_rejects_playwright_command_without_database_env(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-e2e',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-e2e'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-e2e', 'name': 'E2E delivery', 'passes': False},
            ],
        },
        force=True,
    )
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        """# Requirements & Acceptance Confirmation

## 4. Test Strategy
- Playwright E2E tests cover browser delivery.
""",
    )
    approve_gate_file(requirements_path, actor='tester')
    unit_plan_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        unit_plan_path,
        """# Unit Plan Confirmation

## Units
### unit-e2e - E2E delivery
- Verification commands:
  - `pnpm exec playwright test tests/e2e/delivery.spec.ts`

## Controller State Patch

```json
{
  "currentUnitId": "unit-e2e",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-e2e"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-e2e",
      "name": "E2E delivery",
      "passes": false,
      "verification_commands": ["pnpm exec playwright test tests/e2e/delivery.spec.ts"]
    }
  ]
}
```
""",
    )
    approve_gate_file(unit_plan_path, actor='tester')

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['unitPlanAccepted'] is False
    assert 'verification_env' in state['blockedReason']
    assert 'DATABASE_URL' in state['blockedReason']


def test_unit_plan_approval_rejects_closure_unit_without_golden_path(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-e2e',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-e2e'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-e2e', 'name': 'E2E delivery', 'passes': False},
            ],
        },
        force=True,
    )
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        """# Requirements & Acceptance Confirmation

## 3. Acceptance Criteria
- AC-01: User can complete the normal delivery flow.

## 4. Test Strategy
- Playwright E2E tests cover AC-01.
""",
    )
    approve_gate_file(requirements_path, actor='tester')
    unit_plan_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        unit_plan_path,
        """# Unit Plan Confirmation

## Controller State Patch

```json
{
  "currentUnitId": "unit-e2e",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-e2e"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-e2e",
      "name": "E2E delivery",
      "passes": false,
      "workflow_validation_level": "closure",
      "test_cases": [
        {
          "id": "TC-AC-01-e2e",
          "acceptance_criterion": "AC-01",
          "layer": "e2e",
          "fixture": "tests/fixtures/delivery.json",
          "command": "DATABASE_URL=file:test.db pnpm exec playwright test tests/e2e/delivery.spec.ts",
          "expected": "User completes normal delivery flow and sees confirmation #D-100"
        }
      ],
      "verification_commands": ["DATABASE_URL=file:test.db pnpm exec playwright test tests/e2e/delivery.spec.ts"]
    }
  ]
}
```
""",
    )
    approve_gate_file(unit_plan_path, actor='tester')

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['unitPlanAccepted'] is False
    assert 'golden_path' in state['blockedReason']
    assert 'unit-e2e' in state['blockedReason']



def test_unit_plan_approval_accepts_closure_unit_with_golden_path(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-e2e',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-e2e'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-e2e', 'name': 'E2E delivery', 'passes': False},
            ],
        },
        force=True,
    )
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        """# Requirements & Acceptance Confirmation

## 3. Acceptance Criteria
- AC-01: User can complete the normal delivery flow.

## 4. Test Strategy
- Playwright E2E tests cover AC-01.
""",
    )
    approve_gate_file(requirements_path, actor='tester')
    command = 'DATABASE_URL=file:test.db pnpm exec playwright test tests/e2e/delivery.spec.ts'
    unit_plan_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        unit_plan_path,
        '# Unit Plan Confirmation\n\n'
        '## Controller State Patch\n\n'
        '```json\n'
        + json.dumps(
            {
                'currentUnitId': 'unit-e2e',
                'objectiveCoverage': [
                    {'objective': 'Delivery objective', 'units': ['unit-e2e'], 'status': 'partial'}
                ],
                'units': [
                    {
                        'id': 'unit-e2e',
                        'name': 'E2E delivery',
                        'passes': False,
                        'workflow_validation_level': 'closure',
                        'test_cases': [
                            {
                                'id': 'TC-AC-01-golden-path',
                                'acceptance_criterion': 'AC-01',
                                'layer': 'e2e',
                                'golden_path': True,
                                'fixture': 'tests/fixtures/delivery.json',
                                'command': command,
                                'expected': 'User completes normal delivery flow and sees confirmation #D-100',
                            }
                        ],
                        'verification_commands': [command],
                    }
                ],
            }
        )
        + '\n```\n',
    )
    approve_gate_file(unit_plan_path, actor='tester')

    state = controller.run_once()

    assert state['unitPlanAccepted'] is True
    assert state['currentStep'] == 'PLAN_CREATED'



def test_unit_plan_approval_rejects_static_only_verification_without_test_cases(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-static',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-static'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-static', 'name': 'Static-only delivery', 'passes': False},
            ],
        },
        force=True,
    )
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        """# Requirements & Acceptance Confirmation

## 3. Acceptance Criteria
- User can complete delivery.

## 4. Test Strategy
- Unit tests cover delivery behavior.
""",
    )
    approve_gate_file(requirements_path, actor='tester')
    unit_plan_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        unit_plan_path,
        """# Unit Plan Confirmation

## Units
### unit-static - Static-only delivery
- Verification commands:
  - `pnpm exec tsc --noEmit`

## Controller State Patch

```json
{
  "currentUnitId": "unit-static",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-static"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-static",
      "name": "Static-only delivery",
      "passes": false,
      "verification_commands": ["pnpm exec tsc --noEmit"]
    }
  ]
}
```
""",
    )
    approve_gate_file(unit_plan_path, actor='tester')

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_UNIT_PLAN_APPROVAL'
    assert state['unitPlanAccepted'] is False
    assert 'test case coverage' in state['blockedReason']
    assert 'unit-static' in state['blockedReason']


def test_unit_plan_approval_accepts_explicit_test_case_matrix_for_static_and_manual_evidence(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-logo',
            'currentStep': 'WAITING_UNIT_PLAN_APPROVAL',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': False,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': False,
            'unitPlanDraftGenerated': True,
            'objectiveCoverage': [
                {'objective': 'Logo objective', 'units': ['unit-logo'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-logo', 'name': 'Logo delivery', 'passes': False},
            ],
        },
        force=True,
    )
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_path,
        """# Requirements & Acceptance Confirmation

## 3. Acceptance Criteria
- Homepage shows the real logo image.

## 4. Test Strategy
- Manual visual acceptance covers homepage logo rendering.
""",
    )
    approve_gate_file(requirements_path, actor='tester')
    unit_plan_path = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        unit_plan_path,
        """# Unit Plan Confirmation

## Test Case Matrix

| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |
|---|---|---|---|---|
| Homepage shows the real logo image | logo-home-visible | manual visual | manual evidence: inspect homepage screenshot | logo is an image, not text |

## Controller State Patch

```json
{
  "currentUnitId": "unit-logo",
  "objectiveCoverage": [
    {"objective": "Logo objective", "units": ["unit-logo"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-logo",
      "name": "Logo delivery",
      "passes": false,
      "verification_commands": ["pnpm exec tsc --noEmit"],
      "test_cases": [
        {
          "id": "logo-home-visible",
          "acceptance_criterion": "Homepage shows the real logo image",
          "layer": "manual visual",
          "evidence": "Inspect homepage screenshot",
          "expected": "logo is an image, not text"
        }
      ]
    }
  ]
}
```
""",
    )
    approve_gate_file(unit_plan_path, actor='tester')

    state = controller.run_once()

    assert state['currentStep'] == 'PLAN_CREATED'
    assert state['unitPlanAccepted'] is True


def test_final_acceptance_gate_summarizes_execution_evidence(tmp_path: Path) -> None:
    state = {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'currentStep': 'WAITING_FINAL_ACCEPTANCE',
        'status': 'active',
        'objectiveCoverage': [
            {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
        ],
    }
    artifacts_dir = tmp_path / 'artifacts'
    unit_dir = artifacts_dir / 'unit-01'
    unit_dir.mkdir(parents=True)
    (unit_dir / 'changed-files.txt').write_text('src/delivery.py\ntests/test_delivery.py\n', encoding='utf-8')
    (unit_dir / 'builder-summary.json').write_text(
        json.dumps({
            'runner_status': 'done',
            'done_payload': {'summary': 'Delivery implemented'},
            'changed_files': ['src/delivery.py', 'tests/test_delivery.py'],
        }),
        encoding='utf-8',
    )
    (unit_dir / 'review.json').write_text(
        json.dumps({'passed': True, 'issues': [], 'reviewer': 'real-runtime-reviewer'}),
        encoding='utf-8',
    )
    (unit_dir / 'verification.json').write_text(
        json.dumps({
            'passed': True,
            'commands': ['pytest tests/test_delivery.py -q'],
            'results': [
                {'command': 'pytest tests/test_delivery.py -q', 'returncode': 0, 'ok': True, 'stdout': '1 passed'}
            ],
        }),
        encoding='utf-8',
    )

    gate_path = ensure_final_acceptance_gate(state, tmp_path / 'approvals', artifacts_dir, force=True)

    content = gate_path.read_text(encoding='utf-8')
    assert '## 证据摘要' in content
    assert 'Delivery implemented' in content
    assert '`pytest tests/test_delivery.py -q` -> passed' in content
    assert '`src/delivery.py`' in content
    assert '评审：passed' in content
    assert '## 返工路由（Rejection Routing）' in content
    assert '- [ ] 需求变更:' in content
    assert '- [ ] 验收缺陷修复:' in content
    assert '- [ ] Unit Plan 修订:' in content
    assert '- [ ] 实现返工:' in content
    assert '- [ ] 阻塞:' in content


def test_final_acceptance_gate_renders_v035_evidence_matrix(tmp_path: Path) -> None:
    state = {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'currentStep': 'WAITING_FINAL_ACCEPTANCE',
        'status': 'active',
        'objectiveCoverage': [
            {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
        ],
    }
    artifacts_dir = tmp_path / 'artifacts'
    unit_dir = artifacts_dir / 'unit-01'
    unit_dir.mkdir(parents=True)
    (unit_dir / 'changed-files.txt').write_text('src/delivery.py\n', encoding='utf-8')
    (unit_dir / 'builder-summary.json').write_text(
        json.dumps({'runner_status': 'done', 'done_payload': {'summary': 'Delivery implemented'}}),
        encoding='utf-8',
    )
    (unit_dir / 'review.json').write_text(
        json.dumps({'passed': True, 'issues': [], 'reviewer': 'real-runtime-reviewer'}),
        encoding='utf-8',
    )
    (unit_dir / 'verification.json').write_text(
        json.dumps({
            'passed': True,
            'commands': ['pytest tests/test_delivery.py -q'],
            'evidence_schema_version': 'v0.3.5',
            'evidence_rows': [
                {
                    'unit_id': 'unit-01',
                    'test_case_id': 'TC-AC1-GOLDEN',
                    'acceptance_criterion': 'AC-1',
                    'acceptance_obligations': ['AO-001'],
                    'layer': 'e2e',
                    'command': 'pytest tests/test_delivery.py -q',
                    'manual_evidence': None,
                    'expected': 'delivery is visible with status complete',
                    'status': 'passed',
                    'result_index': 0,
                    'returncode': 0,
                    'artifact_refs': ['green-test.txt', 'verification.json'],
                    'golden_path': True,
                },
                {
                    'unit_id': 'unit-01',
                    'test_case_id': 'TC-AC2-MANUAL',
                    'acceptance_criterion': 'AC-2',
                    'acceptance_obligations': ['AO-002'],
                    'layer': 'manual',
                    'command': None,
                    'manual_evidence': 'approvals/unit-plan.md confirms manual acceptance',
                    'expected': 'manual acceptance is recorded',
                    'status': 'manual',
                    'result_index': None,
                    'returncode': None,
                    'artifact_refs': ['approvals/unit-plan.md'],
                    'golden_path': False,
                },
            ],
        }),
        encoding='utf-8',
    )

    gate_path = ensure_final_acceptance_gate(state, tmp_path / 'approvals', artifacts_dir, force=True)

    content = gate_path.read_text(encoding='utf-8')
    assert '## 验收证据矩阵（Final Acceptance Evidence Matrix）' in content
    assert '| AO | AC | Test Case | Layer | Status | Evidence | Expected | Artifacts | Golden Path |' in content
    assert '| AO-001 | AC-1 | TC-AC1-GOLDEN | e2e | passed | `pytest tests/test_delivery.py -q` | delivery is visible with status complete | green-test.txt, verification.json | yes |' in content
    assert '| AO-002 | AC-2 | TC-AC2-MANUAL | manual | manual | approvals/unit-plan.md confirms manual acceptance | manual acceptance is recorded | approvals/unit-plan.md | no |' in content
    assert '拒绝时请引用矩阵中的 AO、AC、Test Case 或 Evidence' in content


def test_final_acceptance_gate_renders_journey_matrix(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    journey_dir = artifacts_dir / 'journeys'
    journey_dir.mkdir(parents=True)
    journey_path = journey_dir / 'journeys.json'
    journey_path.write_text(
        json.dumps(
            {
                'version': 1,
                'journeys': [
                    {
                        'journey_id': 'J-001',
                        'title': 'Delivery happy path',
                        'status': 'active',
                        'linked_acceptance_criteria': ['AC-1'],
                    }
                ],
            }
        ),
        encoding='utf-8',
    )
    (journey_dir / 'journey-evidence.json').write_text(
        json.dumps(
            {
                'journey_evidence_rows': [
                    {
                        'journey_id': 'J-001',
                        'title': 'Delivery happy path',
                        'acceptance_criteria': ['AC-1'],
                        'unit_id': 'unit-01',
                        'test_case_id': 'TC-AC1-E2E',
                        'layer': 'e2e',
                        'command': 'pytest tests/e2e/test_delivery.py -q',
                        'status': 'passed',
                        'returncode': 0,
                        'expected': 'delivery confirmation is visible',
                        'artifact_refs': ['artifacts/unit-01/verification.json'],
                    }
                ],
            }
        ),
        encoding='utf-8',
    )
    unit_dir = artifacts_dir / 'unit-01'
    unit_dir.mkdir(parents=True)
    (unit_dir / 'changed-files.txt').write_text('src/delivery.py\n', encoding='utf-8')
    (unit_dir / 'builder-summary.json').write_text(json.dumps({'runner_status': 'done'}), encoding='utf-8')
    (unit_dir / 'review.json').write_text(json.dumps({'passed': True, 'issues': []}), encoding='utf-8')
    (unit_dir / 'verification.json').write_text(
        json.dumps({'passed': True, 'commands': [], 'evidence_rows': []}),
        encoding='utf-8',
    )
    state = {
        'task_id': 'delivery',
        'currentUnitId': 'unit-01',
        'currentStep': 'WAITING_FINAL_ACCEPTANCE',
        'status': 'active',
        'journeyContractPath': str(journey_path),
        'objectiveCoverage': [
            {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'covered'},
        ],
    }

    gate_path = ensure_final_acceptance_gate(state, tmp_path / 'approvals', artifacts_dir, force=True)

    content = gate_path.read_text(encoding='utf-8')
    assert '## Journey Matrix' in content
    assert '| Journey | AC | Unit | Test Case | Layer | Status | Command / Evidence | Expected | Artifacts |' in content
    assert '| J-001 Delivery happy path | AC-1 | unit-01 | TC-AC1-E2E | e2e | passed | `pytest tests/e2e/test_delivery.py -q` | delivery confirmation is visible | artifacts/unit-01/verification.json |' in content


def test_builder_prompt_includes_final_acceptance_defect_list_for_defect_fix_units(tmp_path: Path) -> None:
    approvals_dir = tmp_path / 'approvals'
    unit_dir = tmp_path / 'artifacts' / 'v2-2-fix-branding'
    original_prompt_path = tmp_path / 'current-prompt.md'
    original_prompt_path.write_text('Complete V2.2.', encoding='utf-8')
    requirements_path = approvals_dir / 'requirements-and-acceptance.md'
    unit_plan_path = approvals_dir / 'unit-plan.md'
    write_gate_file(requirements_path, '# Requirements & Acceptance Confirmation\n\nApproved requirements remain valid.\n')
    approve_gate_file(requirements_path, actor='tester')
    write_gate_file(
        unit_plan_path,
        '# Unit Plan Confirmation\n\n'
        '## Units\n'
        '### v2-2-fix-branding - Acceptance defect fix\n'
        '- Scope: fix final acceptance branding/i18n defects.\n',
    )
    approve_gate_file(unit_plan_path, actor='tester')
    state = {
        'task_id': 'delivery',
        'workspacePath': str(tmp_path),
        'promptPath': str(original_prompt_path),
        'currentUnitId': 'v2-2-fix-branding',
        'requestedOutcome': 'V2.2',
        'humanGatesRequired': True,
        'finalAcceptanceRejectionRoute': 'defect_fix',
        'finalAcceptanceRejectionFeedback': 'Homepage logo is still text-only; workbench i18n is incomplete.',
        'units': [
            {
                'id': 'v2-2-fix-branding',
                'name': 'Acceptance defect fix',
                'passes': False,
                'scope': ['Fix final acceptance branding/i18n defects'],
            }
        ],
        'objectiveCoverage': [
            {
                'objective': 'i18n and logo coverage',
                'units': ['v2-2-fix-branding'],
                'status': 'partial',
            }
        ],
    }

    prompt_path = prepare_builder_prompt(state, approvals_dir, unit_dir)

    assert prompt_path is not None
    prompt = prompt_path.read_text(encoding='utf-8')
    assert 'Final acceptance defect-fix feedback from the previous attempt' in prompt
    assert 'Homepage logo is still text-only' in prompt
    assert 'approved defect-fix unit' in prompt


def test_tmux_claude_generates_unit_plan_gate_body_after_requirements_approval(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    fake_tmux = tmp_path / 'tmux'
    _write(
        fake_tmux,
        """#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

if sys.argv[1:2] == ["paste-buffer"]:
    prompt = (Path(os.environ["RRC_RUN_DIR"]) / "prompt.md").read_text(encoding="utf-8")
    match = re.search(r"Write the Markdown body to this exact file:\\n(.+)", prompt)
    if not match:
        match = re.search(r"Write the Unit Plan Markdown body to this exact file:\\n(.+)", prompt)
    body_path = Path(match.group(1).strip())
    body_path.parent.mkdir(parents=True, exist_ok=True)
    if "Unit Plan" in prompt:
        body = (
            "# Unit Plan Confirmation\\n\\n"
            "## Objective Coverage Matrix\\n- Claude generated unit coverage.\\n\\n"
            "## Units\\n### target-1-1 - Claude generated unit\\n"
            "- Workflow validation level: `closure`\\n"
            "- Scope:\\n  - Implement target acceptance.\\n"
            "- Verification commands:\\n  - `python -c \\"print('verified')\\"`\\n\\n"
            "## Human Review Checklist\\n- [ ] Unit plan reviewed.\\n"
        )
    else:
        body = (
            "# Requirements & Acceptance Confirmation\\n\\n"
            "## 1. Requirements\\n- Generated requirements.\\n\\n"
            "## 2. User Journeys\\n- Generated journey.\\n\\n"
            "## 3. Acceptance Criteria\\n- Generated acceptance.\\n\\n"
            "## 4. Test Strategy\\n- Generated tests.\\n\\n"
            "## 5. Out of Scope\\n- Future units.\\n\\n"
            "## 6. Human Review Checklist\\n- [ ] Requirements reviewed.\\n"
        )
    body_path.write_text(body, encoding="utf-8")
    Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
        json.dumps({"status": "done", "summary": "draft generated", "run_id": os.environ["RRC_RUN_ID"]}),
        encoding="utf-8",
    )
""",
    )
    fake_tmux.chmod(fake_tmux.stat().st_mode | stat.S_IXUSR)
    state_dir = tmp_path / '.rrc-controller'
    init_result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--target',
        '1.1',
        '--runner',
        'tmux-claude',
        '--tmux-target',
        '1.2',
        '--agent',
        str(fake_tmux),
        '--force',
    )
    assert init_result.returncode == 0, init_result.stderr
    _generate_requirements_gate(state_dir)
    approve_gate_file(state_dir / 'approvals' / 'requirements-and-acceptance.md', actor='tester')

    result = run_rrc('run', '--state-dir', str(state_dir), '--until-done', '--auto-approve')

    assert result.returncode == 0, result.stderr
    assert 'currentStep=WAITING_UNIT_PLAN_APPROVAL' in result.stdout
    unit_plan_content = (state_dir / 'approvals' / 'unit-plan.md').read_text(encoding='utf-8')
    assert 'Claude generated unit coverage.' in unit_plan_content
    assert 'Status: pending' in unit_plan_content
    summary = json.loads((state_dir / 'artifacts' / 'unit-plan-draft' / 'unit-plan-draft-summary.json').read_text(encoding='utf-8'))
    assert summary['mode'] == 'tmux-claude'


def test_approve_command_updates_markdown_gate_hash(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    state_dir = tmp_path / '.rrc-controller'
    init_result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--runner',
        'subprocess',
        '--target',
        '1.1',
        '--force',
    )
    assert init_result.returncode == 0, init_result.stderr

    _generate_requirements_gate(state_dir)
    result = run_rrc(
        'approve',
        '--state-dir',
        str(state_dir),
        '--gate',
        'requirements',
        '--actor',
        'tester',
    )

    assert result.returncode == 0, result.stderr
    assert 'gate=requirements status=approved' in result.stdout
    gate_content = (state_dir / 'approvals' / 'requirements-and-acceptance.md').read_text(encoding='utf-8')
    assert 'Status: approved' in gate_content
    assert 'Confirmed by: tester' in gate_content
    assert 'Content hash: sha256:' in gate_content


def test_final_acceptance_approve_command_requires_final_waiting_step(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    state_dir = tmp_path / '.rrc-controller'
    init_result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--runner',
        'subprocess',
        '--target',
        '1.1',
        '--force',
    )
    assert init_result.returncode == 0, init_result.stderr

    result = run_rrc(
        'approve',
        '--state-dir',
        str(state_dir),
        '--gate',
        'final-acceptance',
        '--actor',
        'tester',
    )

    assert result.returncode != 0
    assert 'Final acceptance can only be approved at WAITING_FINAL_ACCEPTANCE' in result.stderr
    assert 'Traceback' not in result.stderr


def test_gate_approval_becomes_stale_when_content_changes(tmp_path: Path) -> None:
    workspace, _ = _make_target_workspace(tmp_path)
    state_dir = tmp_path / '.rrc-controller'
    init_result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--runner',
        'subprocess',
        '--target',
        '1.1',
        '--force',
    )
    assert init_result.returncode == 0, init_result.stderr
    _generate_requirements_gate(state_dir)
    gate_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    approve_gate_file(gate_path, actor='tester')
    gate_path.write_text(
        gate_path.read_text(encoding='utf-8').replace(
            '需求描述准确。',
            '需求描述已变更。',
        ),
        encoding='utf-8',
    )

    result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')

    assert result.returncode == 0, result.stderr
    assert 'currentStep=WAITING_REQUIREMENTS_ACCEPTANCE' in result.stdout
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['requirementsAccepted'] is False


def test_final_acceptance_gate_blocks_done_until_approved(tmp_path: Path) -> None:
    state_dir = tmp_path / '.rrc-controller'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'UNIT_COMPLETE',
            'lastVerifiedStep': 'VERIFY_UNIT',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'autoApprove': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'objectiveCoverage': [
                {'objective': 'Deliver usable workflow', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {'id': 'unit-01', 'passes': False},
            ],
        },
        force=True,
    )

    state = controller.run_once()

    assert state['currentStep'] == 'WAITING_FINAL_ACCEPTANCE'
    assert state['nextAllowedActions'] == ['check_final_acceptance']
    final_gate = state_dir / 'approvals' / 'final-acceptance.md'
    assert final_gate.exists()

    state = controller.run_once()
    assert state['currentStep'] == 'WAITING_FINAL_ACCEPTANCE'
    assert state['finalAcceptanceAccepted'] is False

    approve_gate_file(final_gate, actor='tester')
    state = controller.run_once()
    assert state['currentStep'] == 'RELEASE_GATE'
    assert state['nextAllowedActions'] == ['require_release_approval']

    state = controller.run_once()
    assert state['currentStep'] == 'DONE'
    assert state['status'] == 'done'
