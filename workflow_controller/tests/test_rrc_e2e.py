from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

from workflow_controller.rrc_human_gates import approve_gate_file


ROOT = Path(__file__).resolve().parents[2]


def run_rrc(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'workflow_controller.rrc_controller', *args],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def test_e2e_controller_runs_ralph_target_through_tmux_runner_and_verifier(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    subprocess.run(['git', 'init'], cwd=workspace, check=True, capture_output=True, text=True)

    plan_path = workspace / 'approved-plan.md'
    _write(
        plan_path,
        """# Approved Plan

## Step 1.1-delivery
- Goal: Complete V1.0 tmux runner delivery acceptance
- Status: pending

### Scope
- Produce a delivery artifact through the tmux runner

### Verification
- python -c "from pathlib import Path; assert Path('delivery.txt').read_text(encoding='utf-8') == 'ready\\n'; print('delivery verified')"
""",
    )
    ralph_dir = workspace / '.plan-ralph'
    prompt_path = ralph_dir / 'current-prompt.md'
    _write(prompt_path, 'Create delivery.txt with ready status.')
    _write(
        ralph_dir / 'session.json',
        json.dumps(
            {
                'planPath': str(plan_path),
                'completedStepIds': [],
                'promptPath': str(prompt_path),
            }
        ),
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
            "## 1. Requirements\\n- Delivery artifact is ready.\\n\\n"
            "## 2. User Journeys\\n- User verifies delivery.\\n\\n"
            "## 3. Acceptance Criteria\\n- Verification command passes.\\n\\n"
            "## 4. Test Strategy\\n- Run declared verification.\\n\\n"
            "## 5. Out of Scope\\n- Future units.\\n\\n"
            "## 6. Human Review Checklist\\n- [ ] Reviewed.\\n",
            encoding="utf-8",
        )
        Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
            json.dumps({"status": "done", "summary": "requirements generated"}),
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
                    "name": "Delivery artifact",
                    "passes": False,
                    "workflow_validation_level": "closure",
                    "scope": ["Produce delivery artifact."],
                    "verification_commands": [
                        "python -c \\"from pathlib import Path; assert Path('delivery.txt').read_text(encoding='utf-8') == 'ready\\\\n'; print('delivery verified')\\""
                    ],
                }
            ],
        }
        body_path.write_text(
            "# Unit Plan Confirmation\\n\\n"
            "## Objective Coverage Matrix\\n- Delivery objective -> 1.1-delivery.\\n\\n"
            "## Units\\n### 1.1-delivery - Delivery artifact\\n"
            "- Workflow validation level: `closure`\\n"
            "- Scope:\\n  - Produce delivery artifact.\\n"
            "- Verification commands:\\n  - declared verification command\\n\\n"
            "## Controller State Patch\\n\\n"
            "```json\\n"
            f"{json.dumps(state_patch)}\\n"
            "```\\n\\n"
            "## Human Review Checklist\\n- [ ] Reviewed.\\n",
            encoding="utf-8",
        )
        Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
            json.dumps({"status": "done", "summary": "unit plan generated"}),
            encoding="utf-8",
        )
        raise SystemExit(0)
    Path("delivery.txt").write_text("ready\\n", encoding="utf-8")
    Path(os.environ["RRC_RUN_DONE_FILE"]).write_text(
        json.dumps({"status": "done", "summary": "delivery artifact created"}),
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
        '--from-ralph',
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

    run_result = run_rrc('run', '--state-dir', str(state_dir), '--until-done', '--auto-approve')

    assert run_result.returncode == 0, run_result.stderr
    assert 'currentStep=WAITING_FINAL_ACCEPTANCE status=active' in run_result.stdout
    approve_gate_file(state_dir / 'approvals' / 'final-acceptance.md', actor='tester')

    final_result = run_rrc('run', '--state-dir', str(state_dir), '--until-done', '--auto-approve')

    assert final_result.returncode == 0, final_result.stderr
    assert 'currentStep=DONE status=done' in final_result.stdout
    assert (workspace / 'delivery.txt').read_text(encoding='utf-8') == 'ready\n'

    session = json.loads((state_dir / 'session.json').read_text(encoding='utf-8'))
    assert session['currentStep'] == 'DONE'
    assert session['status'] == 'done'
    assert session['agentRunner'] == 'tmux-claude'
    assert session['tmuxTarget'] == '1.2'

    unit_dir = state_dir / 'artifacts' / '1.1-delivery'
    builder = json.loads((unit_dir / 'builder-summary.json').read_text(encoding='utf-8'))
    assert builder['mode'] == 'tmux-claude'
    assert builder['runner_status'] == 'done'
    assert builder['done_payload']['summary'] == 'delivery artifact created'
    assert 'delivery.txt' in (unit_dir / 'changed-files.txt').read_text(encoding='utf-8')

    run_dir = Path(builder['runner_run_dir'])
    assert (run_dir / 'prompt.md').exists()
    assert (run_dir / 'events.log').exists()
    done_payload = json.loads((run_dir / 'done.json').read_text(encoding='utf-8'))
    assert done_payload['status'] == 'done'

    verification = json.loads((unit_dir / 'verification.json').read_text(encoding='utf-8'))
    assert verification['passed'] is True
    assert verification['results'][0]['returncode'] == 0
    assert 'delivery verified' in verification['results'][0]['stdout']
