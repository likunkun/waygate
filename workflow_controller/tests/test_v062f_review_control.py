from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

from workflow_controller.gates.parsers import check_gate_file, gate_body, hash_gate_body, write_gate_file
from workflow_controller.requirements_package import REQUIREMENTS_PACKAGE_VERSION, mark_stage_artifact
from workflow_controller.rrc_controller import RalphRefinerController
from workflow_controller.prompts.builder import _render_builder_execution_prompt
from workflow_controller.prompts.unit_plan import _render_unit_plan_draft_prompt


ROOT = Path(__file__).resolve().parents[2]


def run_waygate(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'workflow_controller.rrc_controller', *args],
        cwd=str(cwd or ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def _requirements_body() -> str:
    return """# 需求与验收确认

## 3. 验收标准
- AC-1 [verification: integration]: Approval notes remain advisory context.

## Requirements Traceability Matrix
| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| 无 active must AO | AC-1 | covered | integration | bash scripts/verify/v062f-approval-notes.sh |

## 4.5 设计与架构可追溯矩阵（Design/Architecture Traceability Matrix）
| AC | Product Design Ref | Technical Architecture Ref | Notes |
| --- | --- | --- | --- |
| AC-1 | approval notes panel | approval notes persistence | Notes are advisory only. |

## 4.7 Journey Acceptance Matrix
| Journey | Title | Status | Steps | AC | Verification Layer |
| --- | --- | --- | --- | --- | --- |

## 4.9 目标项目基础设施信息
- 代码仓库：测试目标主仓库、workspace、docs、artifacts 和 state-dir 边界已确认。
- 项目部署运行时环境：本地 pytest/subprocess runtime、tmux runner 前置条件和验证命令运行环境已确认。
- 调试分析方法：查看 session.json、events.jsonl、runner stdout/stderr、verification artifacts 和 pytest 输出。
- 参考环境：当前测试 workspace 和历史 controller fixture 作为参考环境，不混同部署环境。
- 文档地址：正式维护文档：`docs/README.md` 作为入口，README/USAGE/ROADMAP 作为项目说明；Controller 过程证据：`.rrc-controller-test/artifacts` 只作审计；外部 Agent / 人工沟通生成文档：未发现；外部 wiki / 设计稿 / API 文档：不涉及，因为该测试目标无外部资料；缺失但需要沉淀的文档：未发现。
- 架构/交互逻辑/接口说明：controller state、human gate、runner dispatch、approval CLI 和 artifact 接口已记录。
- 依赖信息：Python、pytest、tmux fake runner、dpkg tooling 和 shell runtime 依赖已记录。
"""


def _unit_plan_body(command: str = 'bash scripts/verify/v062f-approval-notes.sh') -> str:
    return f"""# Unit Plan Confirmation

## Test Case Matrix
| Acceptance Criterion | Test Case | Layer | Command/Evidence | Expected Result |
| --- | --- | --- | --- | --- |
| AC-1 | TC-1 | integration | {command} | notes remain advisory |

## Document Deliverables Matrix
| Document / Registry | Action | Required For Acceptance | Owner | Reason |
| --- | --- | --- | --- | --- |
| 不需要正式文档变更 | none | false | builder | focused controller test fixture only |

## Controller State Patch

```json
{{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {{"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}}
  ],
  "units": [
    {{
      "id": "unit-01",
      "name": "Delivery",
      "passes": false,
      "test_cases": [
        {{
          "id": "TC-1",
          "acceptance_criterion": "AC-1",
          "layer": "integration",
          "environment_kind": "local_real",
          "entrypoint": "approval notes prompt renderer",
          "allows_mock": false,
          "mocked_routes": [],
          "uses_core_api_mock": false,
          "product_design_refs": ["approval notes panel"],
          "technical_architecture_refs": ["approval notes persistence"],
          "command": "{command}",
          "expected": "notes remain advisory"
        }}
      ],
      "verification_commands": ["{command}"]
    }}
  ]
}}
```
"""


def _base_state(tmp_path: Path, *, step: str = 'WAITING_REQUIREMENTS_ACCEPTANCE') -> dict[str, Any]:
    return {
        'task_id': 'target-v0-6-2f',
        'currentUnitId': 'unit-01',
        'currentStep': step,
        'lastVerifiedStep': 'PLAN_CREATED',
        'status': 'active',
        'requestedOutcome': 'V0.6.2f',
        'feasibleOutcome': 'V0.6.2f',
        'humanGatesRequired': True,
        'scopeApproved': True,
        'requirementsAccepted': step != 'WAITING_REQUIREMENTS_ACCEPTANCE',
        'requirementsDraftGenerated': True,
        'unitPlanAccepted': False,
        'unitPlanDraftGenerated': step == 'WAITING_UNIT_PLAN_APPROVAL',
        'workspacePath': str(tmp_path),
        'executionWorkspacePath': str(tmp_path),
        'promptPath': str(tmp_path / 'original-prompt.md'),
        'objectiveCoverage': [
            {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
        ],
        'units': [
            {'id': 'unit-01', 'name': 'Delivery', 'passes': False},
        ],
    }


def _controller_with_requirements_gate(tmp_path: Path, *, step: str = 'WAITING_REQUIREMENTS_ACCEPTANCE') -> RalphRefinerController:
    state_dir = tmp_path / 'state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    state = _base_state(tmp_path, step=step)
    controller.init_state(state, force=True)
    _write(tmp_path / 'original-prompt.md', '# Original prompt\n')
    write_gate_file(state_dir / 'approvals' / 'requirements-and-acceptance.md', _requirements_body())
    return controller


def test_v062f_approval_notes_persist_and_render_as_non_contract_context(tmp_path: Path) -> None:
    controller = _controller_with_requirements_gate(tmp_path)
    requirements_path = controller.state_dir / 'approvals' / 'requirements-and-acceptance.md'
    notes = {
        'status': 'approved',
        'annotations': [{'quote': 'AC-1', 'comment': 'Clarify AO-001 without scope expansion'}],
        'feedback': 'Please keep AO-001 as clarification only.',
        'reason': 'human approved with advisory notes',
    }

    controller.approve_human_gate('requirements', actor='tester', approval_notes=notes)

    state = json.loads((controller.state_dir / 'session.json').read_text(encoding='utf-8'))
    stored = state['gateApprovalNotes']['requirements']
    assert stored['gate'] == 'requirements'
    assert stored['source'] == 'plannotator_approved'
    assert stored['approved_body_hash'] == hash_gate_body(gate_body(requirements_path.read_text(encoding='utf-8')))
    artifact_path = Path(stored['artifact_path'])
    assert artifact_path.exists()
    artifact = json.loads(artifact_path.read_text(encoding='utf-8'))
    assert artifact['reason'] == 'human approved with advisory notes'
    assert artifact['annotations'][0]['comment'] == 'Clarify AO-001 without scope expansion'

    prompt = _render_unit_plan_draft_prompt(
        state,
        requirements_path,
        controller.artifacts_dir / 'unit-plan-draft' / 'unit-plan-body.md',
    )
    assert 'Approval Notes Non-Contract Context' in prompt
    assert 'non-contract context' in prompt
    assert 'approved gate body wins' in prompt
    assert 'human approved with advisory notes' in prompt
    assert 'Clarify AO-001 without scope expansion' in prompt
    assert state.get('acceptanceObligations') in (None, [])


def test_v062f_unit_plan_approval_notes_reach_builder_prompt_without_contract_promotion(tmp_path: Path) -> None:
    controller = _controller_with_requirements_gate(tmp_path, step='WAITING_UNIT_PLAN_APPROVAL')
    state_dir = controller.state_dir
    requirements_path = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(state_dir / 'approvals' / 'unit-plan.md', _unit_plan_body())
    from workflow_controller.gates.parsers import approve_gate_file

    approve_gate_file(requirements_path, actor='tester')
    notes = {
        'status': 'approved',
        'feedback': 'Builder should know the reviewer concern, but not treat it as a new test case.',
        'reason': 'unit plan approved with advisory context',
    }

    controller.approve_human_gate('unit-plan', actor='tester', approval_notes=notes)

    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    unit_plan_path = state_dir / 'approvals' / 'unit-plan.md'
    prompt = _render_builder_execution_prompt(
        state=state,
        requirements_path=requirements_path,
        requirements_content=requirements_path.read_text(encoding='utf-8'),
        unit_plan_path=unit_plan_path,
        unit_plan_content=unit_plan_path.read_text(encoding='utf-8'),
        original_prompt_path=tmp_path / 'original-prompt.md',
        original_prompt='# Original prompt\n',
        previous_failure_feedback='',
    )
    assert 'Approval Notes Non-Contract Context' in prompt
    assert 'unit plan approved with advisory context' in prompt
    assert 'not treat it as a new test case' in prompt
    assert 'approved gate body wins' in prompt


def test_v062f_i_draft_merge_writes_draft_artifact_and_keeps_gate_pending(tmp_path: Path) -> None:
    controller = _controller_with_requirements_gate(tmp_path)
    state = controller.store.load_state()
    state['gateApprovalNotes'] = {
        'requirements': {
            'approved_body_hash': 'previous',
            'reason': 'merge annotation into a draft only',
            'annotations': [{'comment': 'add reviewer callout'}],
        }
    }
    controller.store.save_state(state)
    outputs: list[str] = []
    choices = iter(['i', 'q'])

    controller.drive(
        max_steps=1,
        input_func=lambda _prompt: next(choices),
        output_func=outputs.append,
        timestamp_output=False,
        print_agent_target=False,
    )

    refreshed = json.loads((controller.state_dir / 'session.json').read_text(encoding='utf-8'))
    merge = refreshed['gateDraftMerge']['requirements']
    assert Path(merge['draft_body_path']).exists()
    assert len(merge['before_hash']) == 64
    assert len(merge['after_hash']) == 64
    assert check_gate_file(controller.state_dir / 'approvals' / 'requirements-and-acceptance.md').approved is False
    assert any('仍停在人工确认点' in line or 'gate remains pending' in line for line in outputs)


def test_v062f_manual_adoption_requires_changed_hash_reason_or_notes_and_validator_pass(tmp_path: Path) -> None:
    controller = _controller_with_requirements_gate(tmp_path)
    state = controller.store.load_state()
    gate_path = controller.state_dir / 'approvals' / 'requirements-and-acceptance.md'
    controller._ensure_pending_gate_review_baseline(state, 'requirements', gate_path)
    controller.store.save_state(state)

    with pytest.raises(ValueError, match='manual adoption rejected: body hash unchanged'):
        controller.approve_human_gate('requirements', actor='tester', reason='manual edit', manual_adoption=True)
    assert check_gate_file(gate_path).approved is False

    edited_body = gate_body(gate_path.read_text(encoding='utf-8')).rstrip() + '\n\n## Manual Clarification\n- Reviewer edited wording only.\n'
    write_gate_file(gate_path, edited_body)
    with pytest.raises(ValueError, match='manual adoption rejected: missing human reason or approval notes'):
        controller.approve_human_gate('requirements', actor='tester', manual_adoption=True)
    assert check_gate_file(gate_path).approved is False

    controller.approve_human_gate('requirements', actor='tester', reason='manual reviewer edit', manual_adoption=True)
    gate = check_gate_file(gate_path)
    assert gate.approved is True
    refreshed = json.loads((controller.state_dir / 'session.json').read_text(encoding='utf-8'))
    adoption = refreshed['manualGateAdoption']['requirements']
    assert adoption['before_hash'] != adoption['after_hash']
    assert adoption['reason'] == 'manual reviewer edit'
    assert adoption['validator'] == 'passed'


def test_v062f_drive_keyboard_interrupt_records_human_interrupt_and_tmux_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller_with_requirements_gate(tmp_path, step='EXECUTE_UNIT')
    state = controller.store.load_state()
    state.update({
        'requirementsAccepted': True,
        'unitPlanAccepted': True,
        'currentStep': 'EXECUTE_UNIT',
        'tmuxTarget': '9.1',
        'agentCommand': 'tmux',
    })
    controller.store.save_state(state)
    sent_commands: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        sent_commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout='', stderr='')

    def interrupting_run_once(*_: Any, **__: Any) -> dict[str, Any]:
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, 'run', fake_run)
    monkeypatch.setattr(controller, 'run_once', interrupting_run_once)
    outputs: list[str] = []
    choices = iter(['q'])

    result = controller.drive(
        input_func=lambda _prompt: next(choices),
        output_func=outputs.append,
        timestamp_output=False,
        print_agent_target=False,
    )

    assert result['status'] == 'blocked'
    context = result['blockedContext']
    assert context['category'] == 'human_interrupt'
    assert context['interrupted_step'] == 'EXECUTE_UNIT'
    assert context['interrupted_action'] == 'run_builder'
    assert context['tmux_interruption']['status'] == 'sent'
    assert any(command[-3:] == ['send-keys', '-t', '9.1'] or 'send-keys' in command for command in sent_commands)
    menu_text = '\n'.join(outputs)
    for token in ['    c  ', '    u  ', '    r  ', '    k  ', '    q  ']:
        assert token in menu_text
    events = [
        json.loads(line)
        for line in (controller.state_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    assert any(event['type'] == 'human_interrupt_recorded' for event in events)


def _staged_state(tmp_path: Path) -> tuple[RalphRefinerController, dict[str, Any]]:
    controller = _controller_with_requirements_gate(tmp_path, step='WAITING_UNIT_PLAN_APPROVAL')
    state = controller.store.load_state()
    artifacts: dict[str, dict[str, str]] = {}
    state.update({
        'requirementsAccepted': True,
        'requirementsPackage': {'version': REQUIREMENTS_PACKAGE_VERSION, 'artifacts': artifacts},
        'stagedRequirementsEnabled': True,
    })
    for stage in ['scope', 'product_design', 'architecture', 'test_strategy']:
        path = tmp_path / f'{stage}.md'
        _write(path, f'# {stage}\n')
        artifacts[stage] = mark_stage_artifact(state, stage, path)
    mark_stage_artifact(state, 'final_gate', controller.state_dir / 'approvals' / 'requirements-and-acceptance.md')
    write_gate_file(controller.state_dir / 'approvals' / 'unit-plan.md', _unit_plan_body('bash scripts/verify/v062f-revise-routes.sh'))
    controller.store.save_state(state)
    return controller, state


def test_v062f_cli_revise_without_reason_returns_to_approval_point_without_staling(tmp_path: Path) -> None:
    controller, before = _staged_state(tmp_path)
    before_statuses = {
        stage: record['status']
        for stage, record in before['requirementsPackage']['artifacts'].items()
    }

    result = run_waygate('revise', '--state-dir', str(controller.state_dir), '--gate', 'requirements')

    assert result.returncode == 0, result.stderr
    assert 'status=pending-approval' in result.stdout
    state = json.loads((controller.state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentStep'] == 'WAITING_REQUIREMENTS_ACCEPTANCE'
    after_statuses = {
        stage: record['status']
        for stage, record in state['requirementsPackage']['artifacts'].items()
    }
    assert after_statuses == before_statuses
    assert 'requirementsRevisionCount' not in state


def test_v062f_cli_revise_checkpoint_without_reason_is_rejected(tmp_path: Path) -> None:
    controller, _ = _staged_state(tmp_path)

    result = run_waygate(
        'revise',
        '--state-dir',
        str(controller.state_dir),
        '--gate',
        'requirements',
        '--checkpoint',
        'product-design',
    )

    assert result.returncode != 0
    assert 'requires --reason when --checkpoint is used' in result.stderr


def test_v062f_legacy_review_actions_remain_visible_with_i_and_m(tmp_path: Path) -> None:
    controller = _controller_with_requirements_gate(tmp_path)
    outputs: list[str] = []
    choices = iter(['p', 'q'])

    controller.drive(
        max_steps=1,
        input_func=lambda _prompt: next(choices),
        output_func=outputs.append,
        timestamp_output=False,
        print_agent_target=False,
    )

    menu = '\n'.join(outputs)
    for line in [
        '    v  使用 Plannotator 辅助审阅',
        '    a  确认通过并继续',
        '    r  我已写批注，让 Claude 重新生成',
        '    p  打印文件路径',
        '    q  退出',
        '    i  根据批注整理正文草案',
        '    m  采纳我已修改的正文并继续',
    ]:
        assert line in menu
