from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from workflow_controller.rrc_controller import RalphRefinerController
from workflow_controller.gates.parsers import approve_gate_file, write_gate_file
from workflow_controller.runners.base import DEFAULT_AGENT_TIMEOUT_SECONDS
from workflow_controller.rrc_real_runtime import (
    find_target_context_files,
    infer_execution_workspace,
    run_agent_for_current_step,
)
from workflow_controller.steps.builder import run_builder, run_verifier


ROOT = Path(__file__).resolve().parents[2]


def run_rrc(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
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


def test_init_from_ralph_plan_creates_state_for_next_uncompleted_step(tmp_path: Path) -> None:
    workspace = tmp_path / 'courses'
    ralph_dir = workspace / '.plan-ralph'
    plan_path = tmp_path / 'course-plan.md'
    _write(
        plan_path,
        """# Approved Plan

## Step 1-foundation
- Goal: Build the foundation
- Status: pending

### Scope
- Add database model

### Non-goals
- No UI

### Verification
- python -c "print('foundation ok')"

## Step 2-runtime
- Goal: Build the runtime
- Status: pending

### Scope
- Add runtime API

### Non-goals
- No admin page

### Verification
- python -c "print('runtime ok')"
""",
    )
    _write(
        ralph_dir / 'session.json',
        json.dumps(
            {
                'planPath': str(plan_path),
                'planHash': 'abc123',
                'completedStepIds': ['1-foundation'],
                'stepStatus': 'verified',
                'promptPath': str(ralph_dir / 'current-prompt.md'),
            }
        ),
    )

    state_dir = tmp_path / 'controller-state'
    result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--from-ralph',
        '--agent',
        'claude',
    )

    assert result.returncode == 0, result.stderr
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['workspacePath'] == str(workspace)
    assert state['promptPath'] == str(ralph_dir / 'current-prompt.md')
    assert state['agentCommand'] == 'claude'
    assert state['currentUnitId'] == '2-runtime'
    assert state['units'][0]['id'] == '1-foundation'
    assert state['units'][0]['passes'] is True
    assert state['units'][1]['id'] == '2-runtime'
    assert state['units'][1]['verification_commands'] == ['python -c "print(\'runtime ok\')"']


def test_init_from_ralph_plan_records_runner_backend_and_tmux_target(tmp_path: Path) -> None:
    workspace = tmp_path / 'courses'
    ralph_dir = workspace / '.plan-ralph'
    plan_path = tmp_path / 'course-plan.md'
    _write(
        plan_path,
        """# Approved Plan

## Step 1-runtime
- Goal: Build runtime
""",
    )
    _write(
        ralph_dir / 'session.json',
        json.dumps({'planPath': str(plan_path), 'promptPath': str(ralph_dir / 'current-prompt.md')}),
    )

    state_dir = tmp_path / 'controller-state'
    result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--from-ralph',
        '--runner',
        'tmux-claude',
        '--tmux-target',
        '1.2',
    )

    assert result.returncode == 0, result.stderr
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['agentRunner'] == 'tmux-claude'
    assert state['tmuxTarget'] == '1.2'


def test_init_with_unmatched_target_creates_target_acceptance_unit_and_prompt(tmp_path: Path) -> None:
    workspace = tmp_path / 'courses'
    ralph_dir = workspace / '.plan-ralph'
    plan_path = tmp_path / 'course-plan.md'
    _write(
        plan_path,
        """# Approved Plan

## Step 1-foundation
- Goal: Build the foundation
- Status: pending

### Verification
- python -c "print('foundation ok')"
""",
    )
    _write(workspace / 'task_plan.md', '# Target Plan\n\nV1.1 customer delivery/import acceptance.\n')
    _write(workspace / 'progress.md', '# Progress\n\nV1.0.5 accepted; V1.1 is next.\n')
    _write(
        ralph_dir / 'session.json',
        json.dumps(
            {
                'planPath': str(plan_path),
                'completedStepIds': ['1-foundation'],
                'promptPath': str(ralph_dir / 'current-prompt.md'),
            }
        ),
    )

    state_dir = tmp_path / 'controller-state'
    result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--from-ralph',
        '--agent',
        'claude',
        '--target',
        '1.1',
    )

    assert result.returncode == 0, result.stderr
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert state['currentUnitId'] == 'target-1-1'
    assert state['targetMatchedPlanStep'] is False
    assert str(workspace / 'task_plan.md') in state['targetContextFiles']

    prompt = Path(state['promptPath']).read_text(encoding='utf-8')
    assert 'Target acceptance: 1.1' in prompt
    assert 'V1.0.5 accepted; V1.1 is next.' in prompt


def test_target_acceptance_prompt_keeps_relevant_context_compact(tmp_path: Path) -> None:
    workspace = tmp_path / 'courses'
    ralph_dir = workspace / '.plan-ralph'
    plan_path = tmp_path / 'course-plan.md'
    _write(
        plan_path,
        """# Approved Plan

## Step 1-foundation
- Goal: Build the foundation

### Verification
- python -c "print('foundation ok')"
""",
    )
    irrelevant_lines = '\n'.join(f'IRRELEVANT-{index}' for index in range(300))
    _write(
        workspace / 'progress.md',
        f"""# Progress

{irrelevant_lines}

## Roadmap
- V1.1 customer delivery/import acceptance is next.
- Phase 7 批量 AI 课程包工厂 must produce customer delivery packages.
""",
    )
    _write(
        ralph_dir / 'session.json',
        json.dumps({'planPath': str(plan_path), 'completedStepIds': ['1-foundation']}),
    )

    state_dir = tmp_path / 'controller-state'
    result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--from-ralph',
        '--agent',
        'codex',
        '--target',
        '1.1',
    )

    assert result.returncode == 0, result.stderr
    state = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    prompt = Path(state['promptPath']).read_text(encoding='utf-8')
    assert 'V1.1 customer delivery/import acceptance is next.' in prompt
    assert 'Phase 7 批量 AI 课程包工厂' in prompt
    assert 'IRRELEVANT-0' not in prompt
    assert len(prompt) < 12000


def test_target_context_files_ignore_global_claude_plans(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'fusion-soc-os'
    _write(workspace / 'task_plan.md', '# Fusion SOC OS Plan\n\nV0.5 acceptance.\n')
    home = tmp_path / 'home'
    _write(
        home / '.claude' / 'plans' / 'composed-sleeping-dolphin.md',
        '# OpenMAIC Plan\n\n客户交付 批量 AI 课程包工厂 course-mgmt-v1 OpenMAIC\n',
    )
    monkeypatch.setenv('HOME', str(home))

    context_files = find_target_context_files(workspace, target='V0.5')

    assert context_files == [workspace / 'task_plan.md']


def test_target_context_files_ignore_project_specific_nested_paths(tmp_path: Path) -> None:
    workspace = tmp_path / 'fusion-soc-os'
    _write(workspace / 'task_plan.md', '# Fusion SOC OS Plan\n')
    _write(workspace / 'OpenMAIC' / 'task_plan.md', '# Wrong nested project plan\n')
    _write(workspace / 'OpenMAIC' / '.worktrees' / 'course-mgmt-v1' / 'progress.md', '# Wrong worktree progress\n')

    context_files = find_target_context_files(workspace, target='V0.5')

    assert context_files == [workspace / 'task_plan.md']


def test_infer_execution_workspace_does_not_select_project_specific_nested_worktree(tmp_path: Path) -> None:
    workspace = tmp_path / 'fusion-soc-os'
    _write(workspace / 'package.json', '{}\n')
    _write(workspace / 'OpenMAIC' / '.worktrees' / 'course-mgmt-v1' / 'package.json', '{}\n')

    assert infer_execution_workspace(workspace) == workspace


def test_run_builder_executes_configured_agent_in_workspace_and_writes_real_artifacts(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    subprocess.run(['git', 'init'], cwd=workspace, check=True, capture_output=True, text=True)
    prompt_path = workspace / '.plan-ralph' / 'current-prompt.md'
    _write(prompt_path, 'Implement the current step.')

    agent = tmp_path / 'fake-claude'
    _write(
        agent,
        """#!/usr/bin/env python3
from pathlib import Path
Path("generated.txt").write_text("real change\\n", encoding="utf-8")
print("agent executed current step")
""",
    )
    agent.chmod(agent.stat().st_mode | stat.S_IXUSR)

    state = {
        'task_id': 'course-plan',
        'currentUnitId': '2-runtime',
        'workspacePath': str(workspace),
        'promptPath': str(prompt_path),
        'agentCommand': str(agent),
    }
    unit_dir = tmp_path / 'artifacts' / '2-runtime'

    result = run_builder(state, unit_dir, dry_run=False)

    assert result.summary == 'builder complete'
    assert (workspace / 'generated.txt').read_text(encoding='utf-8') == 'real change\n'
    summary = json.loads((unit_dir / 'builder-summary.json').read_text(encoding='utf-8'))
    assert summary['mode'] == 'claude-code'
    assert summary['exit_code'] == 0
    assert 'agent executed current step' in summary['stdout']
    assert (unit_dir / 'changed-files.txt').read_text(encoding='utf-8') == 'generated.txt\n'


def test_run_builder_supports_codex_exec_agent_command(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    subprocess.run(['git', 'init'], cwd=workspace, check=True, capture_output=True, text=True)
    prompt_path = workspace / '.plan-ralph' / 'current-prompt.md'
    _write(prompt_path, 'Implement the current step.')

    agent = tmp_path / 'fake-codex'
    _write(
        agent,
        """#!/usr/bin/env python3
import sys
from pathlib import Path
Path("codex-generated.txt").write_text("codex change\\n", encoding="utf-8")
print("ARGS=" + " ".join(sys.argv[1:]))
""",
    )
    agent.chmod(agent.stat().st_mode | stat.S_IXUSR)

    state = {
        'task_id': 'course-plan',
        'currentUnitId': 'target-1-1',
        'workspacePath': str(workspace),
        'promptPath': str(prompt_path),
        'agentCommand': str(agent),
    }
    unit_dir = tmp_path / 'artifacts' / 'target-1-1'

    result = run_builder(state, unit_dir, dry_run=False)

    assert result.summary == 'builder complete'
    summary = json.loads((unit_dir / 'builder-summary.json').read_text(encoding='utf-8'))
    assert summary['agent_command'][1:3] == [
        'exec',
        '--dangerously-bypass-approvals-and-sandbox',
    ]
    assert summary['agent_command'][-1] == '-'
    assert (unit_dir / 'changed-files.txt').read_text(encoding='utf-8') == 'codex-generated.txt\n'


def test_run_agent_for_current_step_uses_two_hour_default_timeout(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Inspect timeout.')
    captured: dict[str, int] = {}

    def fake_run_agent_backend(request):
        captured['timeout_seconds'] = request.timeout_seconds
        from workflow_controller.runners.base import RunnerResult
        return RunnerResult(
            backend='subprocess',
            status='done',
            command=['agent'],
            returncode=0,
            stdout='',
            stderr='',
            run_dir=tmp_path / 'run',
            prompt_path=prompt_path,
        )

    monkeypatch.setattr('workflow_controller.rrc_real_runtime.run_agent_backend', fake_run_agent_backend)

    run_agent_for_current_step(
        {'currentUnitId': 'unit-01', 'agentRunner': 'subprocess', 'agentCommand': 'agent'},
        workspace,
        prompt_path,
        artifact_dir=tmp_path / 'artifacts',
    )

    assert captured['timeout_seconds'] == DEFAULT_AGENT_TIMEOUT_SECONDS == 7200



def test_run_agent_for_current_step_uses_role_specific_runner_env_and_redacted_metadata(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv('HTTP_PROXY', raising=False)
    monkeypatch.delenv('HTTPS_PROXY', raising=False)
    monkeypatch.delenv('NO_PROXY', raising=False)
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    prompt_path = workspace / 'prompt.md'
    _write(prompt_path, 'Inspect role env.')
    fake_agent = tmp_path / 'fake-strategist'
    _write(
        fake_agent,
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
Path("role-env.json").write_text(json.dumps({
    "HTTP_PROXY": os.environ.get("HTTP_PROXY"),
    "SECRET_TOKEN": os.environ.get("SECRET_TOKEN"),
}), encoding="utf-8")
""",
    )
    fake_agent.chmod(fake_agent.stat().st_mode | stat.S_IXUSR)
    state = {
        'currentUnitId': 'unit-01',
        'agentRunner': 'tmux-claude',
        'agentCommand': 'claude',
        'roleRunners': {
            'test_strategist': {
                'runner': 'subprocess',
                'command': str(fake_agent),
                'env': {
                    'HTTP_PROXY': 'http://127.0.0.1:7890',
                    'SECRET_TOKEN': 'super-secret-token',
                },
            },
        },
    }

    result = run_agent_for_current_step(
        state,
        workspace,
        prompt_path,
        artifact_dir=tmp_path / 'artifacts',
        role='test_strategist',
    )

    assert result.status == 'done'
    assert result.runner_metadata == {
        'role': 'test_strategist',
        'backend': 'subprocess',
        'agent_command': str(fake_agent),
        'tmux_target': None,
        'env_keys': ['HTTP_PROXY', 'SECRET_TOKEN'],
    }
    assert json.loads((workspace / 'role-env.json').read_text(encoding='utf-8')) == {
        'HTTP_PROXY': 'http://127.0.0.1:7890',
        'SECRET_TOKEN': 'super-secret-token',
    }
    assert 'super-secret-token' not in json.dumps(result.runner_metadata)
    assert 'http://127.0.0.1:7890' not in json.dumps(result.runner_metadata)


def test_run_builder_uses_tmux_runner_when_configured(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    subprocess.run(['git', 'init'], cwd=workspace, check=True, capture_output=True, text=True)
    prompt_path = workspace / '.plan-ralph' / 'current-prompt.md'
    _write(prompt_path, 'Implement through tmux Claude Code.')

    fake_tmux = tmp_path / 'tmux'
    _write(
        fake_tmux,
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
if sys.argv[1:2] == ["paste-buffer"]:
    Path("tmux-builder-output.txt").write_text("tmux change\\n", encoding="utf-8")
    Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
        json.dumps({"status": "done", "summary": "builder done", "run_id": os.environ["RRC_RUN_ID"]}),
        encoding="utf-8",
    )
""",
    )
    fake_tmux.chmod(fake_tmux.stat().st_mode | stat.S_IXUSR)

    state = {
        'task_id': 'course-plan',
        'currentUnitId': 'target-1-1',
        'workspacePath': str(workspace),
        'promptPath': str(prompt_path),
        'agentRunner': 'tmux-claude',
        'agentCommand': str(fake_tmux),
        'tmuxTarget': '1.2',
        'agentTimeoutSeconds': 5,
    }
    unit_dir = tmp_path / 'artifacts' / 'target-1-1'

    result = run_builder(state, unit_dir, dry_run=False)

    assert result.summary == 'builder complete'
    assert (workspace / 'tmux-builder-output.txt').read_text(encoding='utf-8') == 'tmux change\n'
    summary = json.loads((unit_dir / 'builder-summary.json').read_text(encoding='utf-8'))
    assert summary['mode'] == 'tmux-claude'
    assert summary['runner_status'] == 'done'
    assert summary['done_payload']['summary'] == 'builder done'
    assert 'tmux-builder-output.txt' in (unit_dir / 'changed-files.txt').read_text(encoding='utf-8')


def test_controller_builder_prompt_includes_approved_requirements_and_unit_plan(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    subprocess.run(['git', 'init'], cwd=workspace, check=True, capture_output=True, text=True)
    prompt_path = workspace / '.plan-ralph' / 'current-prompt.md'
    _write(prompt_path, 'Original Ralph prompt only.')

    fake_tmux = tmp_path / 'tmux'
    _write(
        fake_tmux,
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

if sys.argv[1:2] == ["paste-buffer"]:
    prompt = (Path(os.environ["RRC_RUN_DIR"]) / "prompt.md").read_text(encoding="utf-8")
    if "REQ_TOKEN_APPROVED" not in prompt or "UNIT_TOKEN_APPROVED" not in prompt:
        print("approved gate content missing from builder prompt", file=sys.stderr)
        raise SystemExit(1)
    Path("builder-output.txt").write_text("built from approved gates\\n", encoding="utf-8")
    Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
        json.dumps({"status": "done", "summary": "builder used approved gates", "run_id": os.environ["RRC_RUN_ID"]}),
        encoding="utf-8",
    )
""",
    )
    fake_tmux.chmod(fake_tmux.stat().st_mode | stat.S_IXUSR)

    state_dir = tmp_path / 'controller-state'
    controller = RalphRefinerController(state_dir=state_dir, auto_approve=True)
    controller.init_state(
        {
            'task_id': 'delivery',
            'currentUnitId': 'unit-01',
            'currentStep': 'PLAN_APPROVED',
            'lastVerifiedStep': 'PLAN_CREATED',
            'status': 'active',
            'requestedOutcome': 'usable-system',
            'feasibleOutcome': 'usable-system',
            'scopeApproved': True,
            'humanGatesRequired': True,
            'requirementsAccepted': True,
            'unitPlanAccepted': True,
            'finalAcceptanceAccepted': False,
            'workspacePath': str(workspace),
            'executionWorkspacePath': str(workspace),
            'promptPath': str(prompt_path),
            'agentRunner': 'tmux-claude',
            'agentCommand': str(fake_tmux),
            'tmuxTarget': '1.2',
            'agentTimeoutSeconds': 5,
            'baselineChangedFiles': [],
            'objectiveCoverage': [
                {'objective': 'Delivery objective', 'units': ['unit-01'], 'status': 'partial'},
            ],
            'units': [
                {
                    'id': 'unit-01',
                    'name': 'Delivery',
                    'passes': False,
                    'verification_commands': ['python -c "print(1)"'],
                },
            ],
        },
        force=True,
    )
    requirements_gate = state_dir / 'approvals' / 'requirements-and-acceptance.md'
    write_gate_file(
        requirements_gate,
        '# Requirements & Acceptance Confirmation\n\n## 1. Requirements\n- REQ_TOKEN_APPROVED\n',
    )
    approve_gate_file(requirements_gate, actor='tester')
    unit_plan_gate = state_dir / 'approvals' / 'unit-plan.md'
    write_gate_file(
        unit_plan_gate,
        """# Unit Plan Confirmation

## Units
- UNIT_TOKEN_APPROVED

## Controller State Patch

```json
{
  "currentUnitId": "unit-01",
  "objectiveCoverage": [
    {"objective": "Delivery objective", "units": ["unit-01"], "status": "partial"}
  ],
  "units": [
    {
      "id": "unit-01",
      "name": "Delivery",
      "passes": false,
      "verification_commands": ["python -c \\"print(1)\\""]
    }
  ]
}
```
""",
    )
    approve_gate_file(unit_plan_gate, actor='tester')

    state = controller.run_once()

    assert state['currentStep'] == 'REFINE_UNIT'
    assert (workspace / 'builder-output.txt').read_text(encoding='utf-8') == 'built from approved gates\n'
    builder_prompt = Path(state['builderPromptPath']).read_text(encoding='utf-8')
    assert 'REQ_TOKEN_APPROVED' in builder_prompt
    assert 'UNIT_TOKEN_APPROVED' in builder_prompt
    assert state['promptPath'] == str(prompt_path)


def test_builder_failure_mentions_tmux_target_without_traceback(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    subprocess.run(['git', 'init'], cwd=workspace, check=True, capture_output=True, text=True)
    plan_path = workspace / 'plan.md'
    _write(
        plan_path,
        """# Approved Plan

## Step 1.1-delivery
- Goal: Delivery
""",
    )
    prompt_path = workspace / '.plan-ralph' / 'current-prompt.md'
    _write(prompt_path, 'Create delivery.')
    _write(
        workspace / '.plan-ralph' / 'session.json',
        json.dumps({'planPath': str(plan_path), 'promptPath': str(prompt_path)}),
    )

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
            "## 1. Requirements\\n- Delivery.\\n\\n"
            "## 2. User Journeys\\n- Delivery path.\\n\\n"
            "## 3. Acceptance Criteria\\n- Evidence exists.\\n\\n"
            "## 4. Test Strategy\\n- Run verification.\\n\\n"
            "## 5. Out of Scope\\n- Future units.\\n\\n"
            "## 6. Product Design Summary\\n- Core flow is visible to reviewers.\\n\\n"
            "## 7. Architecture Summary\\n- Module boundaries and data flow are summarized.\\n\\n"
            "## 8. Human Review Checklist\\n- [ ] Reviewed.\\n",
            encoding="utf-8",
        )
        Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
            json.dumps({"status": "done", "summary": "requirements generated", "run_id": os.environ["RRC_RUN_ID"]}),
            encoding="utf-8",
        )
        raise SystemExit(0)
    match = re.search(r"Write the Unit Plan Markdown body to this exact file:\\n(.+)", prompt)
    if match:
        body_path = Path(match.group(1).strip())
        body_path.parent.mkdir(parents=True, exist_ok=True)
        state_patch = {
            "currentUnitId": "1.1-delivery",
            "objectiveCoverage": [
                {"objective": "Delivery objective", "units": ["1.1-delivery"], "status": "partial"}
            ],
            "units": [
                {
                    "id": "1.1-delivery",
                    "name": "Delivery",
                    "passes": False,
                    "workflow_validation_level": "closure",
                    "scope": ["Delivery."],
                    "verification_commands": ["python -c \\"print('verified')\\""],
                    "test_cases": [
                        {
                            "id": "TC-delivery-golden-path",
                            "acceptance_criterion": "Delivery objective",
                            "layer": "e2e",
                            "golden_path": True,
                            "fixture": "Delivery fixture creates a normal delivery flow.",
                            "command": "python -c \\"print('verified')\\"",
                            "expected": "verification command prints verified for the normal delivery flow",
                        }
                    ],
                }
            ],
        }
        body_path.write_text(
            "# Unit Plan Confirmation\\n\\n"
            "## Objective Coverage Matrix\\n- Delivery objective -> 1.1-delivery.\\n\\n"
            "## Units\\n### 1.1-delivery - Delivery\\n"
            "- Workflow validation level: `closure`\\n"
            "- Scope:\\n  - Delivery.\\n"
            "- Verification commands:\\n  - declared verification command\\n\\n"
            "## Controller State Patch\\n\\n"
            "```json\\n"
            f"{json.dumps(state_patch)}\\n"
            "```\\n\\n"
            "## Human Review Checklist\\n- [ ] Reviewed.\\n",
            encoding="utf-8",
        )
        Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
            json.dumps({"status": "done", "summary": "unit plan generated", "run_id": os.environ["RRC_RUN_ID"]}),
            encoding="utf-8",
        )
        raise SystemExit(0)
    print("can't find pane: 2", file=sys.stderr)
    raise SystemExit(1)
raise SystemExit(0)
""",
    )
    fake_tmux.chmod(fake_tmux.stat().st_mode | stat.S_IXUSR)

    state_dir = tmp_path / 'controller-state'
    init_result = run_rrc(
        'init',
        '--state-dir',
        str(state_dir),
        '--workspace-dir',
        str(workspace),
        '--from-ralph',
        '--runner',
        'tmux-claude',
        '--tmux-target',
        '1.2',
        '--agent',
        str(fake_tmux),
    )
    assert init_result.returncode == 0, init_result.stderr

    draft_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert draft_result.returncode == 0, draft_result.stderr
    assert 'currentStep=WAITING_REQUIREMENTS_ACCEPTANCE' in draft_result.stdout

    approve_gate_file(state_dir / 'approvals' / 'requirements-and-acceptance.md', actor='tester')
    req_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert req_result.returncode == 0, req_result.stderr
    assert 'currentStep=UNIT_PLAN_DRAFT' in req_result.stdout

    unit_plan_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert unit_plan_result.returncode == 0, unit_plan_result.stderr
    assert 'currentStep=WAITING_UNIT_PLAN_APPROVAL' in unit_plan_result.stdout

    approve_gate_file(state_dir / 'approvals' / 'unit-plan.md', actor='tester')
    plan_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert plan_result.returncode == 0, plan_result.stderr
    assert 'currentStep=PLAN_CREATED' in plan_result.stdout

    approve_result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')
    assert approve_result.returncode == 0, approve_result.stderr
    assert 'currentStep=PLAN_APPROVED' in approve_result.stdout

    result = run_rrc('run', '--state-dir', str(state_dir), '--auto-approve')

    assert result.returncode != 0
    assert 'Builder agent failed' in result.stderr
    assert 'tmux target 1.2' in result.stderr
    assert 'Traceback' not in result.stderr


def test_run_verifier_executes_verification_commands_in_workspace_and_records_results(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state = {
        'currentUnitId': '2-runtime',
        'workspacePath': str(workspace),
        'units': [
            {
                'id': '2-runtime',
                'verification_commands': [
                    "python -c \"from pathlib import Path; Path('verified.txt').write_text('ok'); print('verified')\""
                ],
            }
        ],
    }
    unit_dir = tmp_path / 'artifacts' / '2-runtime'

    result = run_verifier(state, unit_dir, dry_run=False)

    assert result.summary == 'verification passed'
    assert (workspace / 'verified.txt').read_text(encoding='utf-8') == 'ok'
    verification = json.loads((unit_dir / 'verification.json').read_text(encoding='utf-8'))
    assert verification['passed'] is True
    assert verification['results'][0]['returncode'] == 0
    assert 'verified' in verification['results'][0]['stdout']


def test_run_verifier_supports_bash_source_in_approved_verification_command(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    activate = workspace / 'activate'
    activate.write_text('export RRC_SOURCE_SENTINEL=from-source\n', encoding='utf-8')
    command = "source ./activate && python -c \"import os; print(os.environ['RRC_SOURCE_SENTINEL'])\""
    state = {
        'currentUnitId': '2-runtime',
        'workspacePath': str(workspace),
        'units': [
            {
                'id': '2-runtime',
                'verification_commands': [command],
            }
        ],
    }
    unit_dir = tmp_path / 'artifacts' / '2-runtime'

    result = run_verifier(state, unit_dir, dry_run=False)

    assert result.summary == 'verification passed'
    verification = json.loads((unit_dir / 'verification.json').read_text(encoding='utf-8'))
    assert verification['passed'] is True
    assert verification['results'][0]['command'] == command
    assert verification['results'][0]['returncode'] == 0
    assert 'from-source' in verification['results'][0]['stdout']


def test_run_verifier_injects_unit_verification_env_without_inlining_it_in_command(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state = {
        'currentUnitId': '2-runtime',
        'workspacePath': str(workspace),
        'units': [
            {
                'id': '2-runtime',
                'verification_env': {
                    'DATABASE_URL': 'sqlite:///unit-test.db',
                },
                'verification_commands': [
                    "python -c \"import os; from pathlib import Path; "
                    "Path('database-url.txt').write_text(os.environ['DATABASE_URL'], encoding='utf-8'); "
                    "print(os.environ['DATABASE_URL'])\"",
                ],
            }
        ],
    }
    unit_dir = tmp_path / 'artifacts' / '2-runtime'

    result = run_verifier(state, unit_dir, dry_run=False)

    assert result.summary == 'verification passed'
    assert (workspace / 'database-url.txt').read_text(encoding='utf-8') == 'sqlite:///unit-test.db'
    verification = json.loads((unit_dir / 'verification.json').read_text(encoding='utf-8'))
    assert verification['passed'] is True
    assert verification['results'][0]['env_keys'] == ['DATABASE_URL']


def test_run_verifier_infers_database_url_for_legacy_playwright_session(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    (workspace / 'prisma').mkdir(parents=True)
    (workspace / 'prisma' / 'dev.db').write_text('', encoding='utf-8')
    state = {
        'currentUnitId': '2-runtime',
        'workspacePath': str(workspace),
        'units': [
            {
                'id': '2-runtime',
                'verification_commands': [
                    "python -c \"import os; from pathlib import Path; "
                    "Path('inferred-db-url.txt').write_text(os.environ['DATABASE_URL'], encoding='utf-8')\" "
                    "# playwright",
                ],
            }
        ],
    }
    unit_dir = tmp_path / 'artifacts' / '2-runtime'

    result = run_verifier(state, unit_dir, dry_run=False)

    expected = f"file:{workspace / 'prisma' / 'dev.db'}"
    assert result.summary == 'verification passed'
    assert state['verification_env']['DATABASE_URL'] == expected
    assert state['verification_env_inferred']['DATABASE_URL'] == expected
    assert (workspace / 'inferred-db-url.txt').read_text(encoding='utf-8') == expected
    verification = json.loads((unit_dir / 'verification.json').read_text(encoding='utf-8'))
    assert verification['results'][0]['env_keys'] == ['DATABASE_URL']


def test_run_verifier_emits_progress_events_on_verification_state_changes(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    state = {
        'currentUnitId': '2-runtime',
        'workspacePath': str(workspace),
        'units': [
            {
                'id': '2-runtime',
                'verification_commands': [
                    "python -c \"print('first')\"",
                    "python -c \"print('second')\"",
                ],
            }
        ],
    }
    unit_dir = tmp_path / 'artifacts' / '2-runtime'
    events: list[dict] = []

    result = run_verifier(state, unit_dir, dry_run=False, progress_callback=events.append)

    assert result.summary == 'verification passed'
    assert [event['event'] for event in events] == [
        'verification_started',
        'verification_command_started',
        'verification_command_finished',
        'verification_command_started',
        'verification_command_finished',
        'verification_finished',
    ]
    assert events[1]['index'] == 1
    assert events[1]['total'] == 2
    assert events[2]['returncode'] == 0
    assert events[-1]['passed'] is True
