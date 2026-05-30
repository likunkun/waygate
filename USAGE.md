# Waygate Usage

[中文](USAGE.zh-CN.md) | [README](README.md)

This document is the CLI-oriented guide for Waygate. For concepts, architecture, V0.6.1 external spec intake and annotation policy, V0.6.0m golden-path E2E preflight, V0.6.0j Requirements infrastructure follow-up, V0.6.0k UI/UX skill policy, and the V0.6.0i document lifecycle entry point, see [docs/README.md](docs/README.md), [docs/workflow.md](docs/workflow.md), [docs/workflow/external-spec-intake-and-annotation-policy.md](docs/workflow/external-spec-intake-and-annotation-policy.md), [docs/workflow/requirements-e2e-review-policy.md](docs/workflow/requirements-e2e-review-policy.md), [docs/workflow/ui-ux-skill-policy.md](docs/workflow/ui-ux-skill-policy.md), and [docs/architecture/external-spec-intake-and-annotation-architecture.md](docs/architecture/external-spec-intake-and-annotation-architecture.md).

For V0.6.0h environment preparation, see [docs/operations/recommended-environment.md](docs/operations/recommended-environment.md). For an introduction and best-practices walkthrough, see [docs/product/waygate-introduction-and-best-practices.md](docs/product/waygate-introduction-and-best-practices.md).

V0.6.0f tightens browser acceptance evidence: Playwright or browser tests that mock/stub core business APIs cannot be used as E2E, golden path, prototype conformance, or production-readiness evidence.

V0.6.0m moves golden-path E2E mistakes earlier: Unit Plan approval rejects `golden_path: true` cases that are not `layer=e2e`, lack a real entrypoint, use mock environments, omit concrete fixture/setup, or are absent from `verification_commands`. API-only or service-only E2E can use pytest/API/service commands and does not require browser fields.

V0.6.1 adds OpenSpec/OpenAPI and Spec Kit spec intake, non-approving annotation / verification-assist passes before human gates, and flexible verifier evidence rows with `human_review_required`.

## Prerequisites

Waygate itself is Python code packaged as a Debian package. Real agent execution depends on the runner you choose:

| Runner | Requirement |
| --- | --- |
| `subprocess` | A local command that can execute the agent task. |
| `tmux-claude` | `tmux` and a Claude Code pane, or permission to create one. |
| `tmux-codex` | `tmux` and an existing Codex pane. |
| `dry-run` | No real agent required; mock artifacts are generated. |

Build and install:

```bash
bash packaging/debian/build-deb.sh
sudo apt install ./dist/waygate_0.6.1a_all.deb
waygate --help
waygate doctor
waygate doctor --color auto
```

`waygate doctor` starts with `summary:`, `focus:`, and `action_required:` before the detailed checklist. The `focus:` layer groups the first things humans should look at, such as P1 tmux config fixes, install provenance warnings, environment risks, and skill gaps. Use `--color auto|always|never` to highlight status, P1 focus items, manual actions, and section headers; non-TTY output remains plain by default. It prints the active executable path, imported module path, module version, installed dpkg version, every `waygate` candidate in `PATH`, environment checks for Python, pytest, tmux, Claude Code, Codex, Plannotator, `dpkg-deb`, `tmux_config` checks for `~/.tmux.conf`, skill root scans, installed skills, README-aligned recommended workflow skill gaps, `claude_assets`, and the recommended Plannotator port. Waygate runners still need a usable `claude` or `codex` CLI command. If doctor reports a `~/.local/bin/waygate` shadow before `/usr/bin/waygate`, rename or remove the user-level wrapper and run `hash -r`.

Run from source:

```bash
python -m workflow_controller.cli --help
```

## Recommended Entry Point: `go`

Run Waygate from the target project root:

```bash
waygate go V1.0
```

`go` infers common defaults:

| Field | Default |
| --- | --- |
| `target` | The positional target, for example `V1.0`. |
| `workspace-dir` | Current directory, unless `--workspace-dir` or `--tmux-target` provides a better source. |
| `state-dir` | `<workspace-dir>/.rrc-controller-<target>`. |
| runner | In tmux without a target, Waygate creates a Claude pane. With `--tmux-target`, it detects Claude or Codex. |

Common examples:

```bash
# Create or resume a target session.
waygate go V1.0

# Use an existing tmux pane; Waygate detects Claude or Codex.
waygate go V1.0 --tmux-target 1.2

# Explicitly use an existing Codex pane. If no target is passed,
# Waygate searches the current tmux session for a matching Codex pane.
waygate go V1.0 --runner tmux-codex

# Run without tmux.
waygate go V1.0 --runner subprocess

# Simulate the workflow.
waygate go V1.0 --runner subprocess --dry-run --max-steps 20

# Run from outside the target project.
waygate go V1.0 --workspace-dir /path/to/target-project

# Start from a supported Waygate Markdown requirements spec.
waygate go V1.0 --spec ./requirements.md

# Enable non-approving Codex annotation agents for all review roles.
waygate go V0.6.1 --annotation-agent codex

# Enable only the Unit Plan annotation role.
waygate go V0.6.1 --annotation-agent unit-plan=codex
```

If a previous agent dispatch stopped with timeout, idle-without-DONE, or a still-running tmux shell tool without DONE, rerun `waygate go ...` with the same target or `--state-dir`. Waygate reads `recoverableAgentWait` from `session.json`, records an automatic resume event, and continues the same stage. Explicit `blocked` states are different: interactive `go`, `drive`, and `start` can open Blocked Assist for diagnosis, but only a human-selected route changes state. Use `unblock` after an external condition is fixed, or use `revise` / Final Acceptance rejection routing when the approved contract must change.

## Prototype Review Bundle

For UI/UX or Web-system requirements, the Requirements drafter must write `artifacts/requirements-draft/prototype-manifest.json`. Waygate validates it, copies local image/HTML prototypes into `artifacts/requirements-draft/prototypes/`, and renders `plannotator-review.md` plus `plannotator-review.html`. Plannotator annotates the approval file `approvals/requirements-and-acceptance.md`; the HTML bundle is exposed as an auxiliary rendered prototype preview URL during the current review session.

By default, Waygate binds review services on `0.0.0.0` and displays the Plannotator approval page and prototype preview URL with the machine's primary IP address. Plannotator uses port `20000`; the controller prototype preview server uses fixed port `20001` so operators can pre-approve ACLs. `--plannotator-port` changes the Plannotator port, `WAYGATE_PREVIEW_PORT` changes the controller preview port, `WAYGATE_DISPLAY_HOST` overrides the printed browser host, and `WAYGATE_PREVIEW_HOST` overrides the controller preview bind host. Waygate requests Plannotator remote access with `PLANNOTATOR_REMOTE=1`.

The manifest must map each prototype to real AC IDs and include page states plus click paths. URLs with sensitive query keys such as `token`, `password`, `secret`, `api_key`, or `signature` are rejected.

## Two-Step Mode

Use `init` when you want to inspect state before driving the workflow:

```bash
waygate init \
  --state-dir .rrc-controller-v1.0 \
  --workspace-dir . \
  --target V1.0 \
  --spec ./requirements.md \
  --runner tmux-claude \
  --tmux-target 1.2

waygate drive --state-dir .rrc-controller-v1.0
```

## Commands

### `init`

Create `session.json`, `approvals/`, `artifacts/`, and initial target state.

```bash
waygate init --target V1.0 --workspace-dir . --spec ./requirements.md
```

`--spec <path>` currently imports only a readable local Waygate Markdown spec file. Waygate stores path, SHA-256 hash, source type, and import time in `session.json`; it does not store the full spec text. OpenSpec and Spec Kit paths are detected as future external spec intake and rejected/deferred in this version.

### Annotation Agent Options

Annotation agents are disabled by default. Add them only when you want advisory risk notes before human review:

```bash
waygate go V0.6.1 --annotation-agent codex
waygate init --target V0.6.1 --annotation-agent unit-plan=codex
waygate drive --state-dir .rrc-controller-v0.6.1 --annotation-agent unit-plan=codex --annotation-agent-cmd unit-plan='python3 fake.py'
```

Supported role aliases are `requirements`, `unit-plan`, `final-acceptance`, and `all`. Supported backend names are `codex`, `claude-code` (or `claude`), and `opencode`. Use `--no-annotation-agent ROLE|all` to disable roles, `--annotation-agent-env-key ROLE=KEY` to inherit only named environment keys, `--annotation-agent-timeout ROLE=SECONDS`, and `--annotation-agent-failure-policy ROLE=block|warn`.

The built-in `--annotation-agent codex` configuration enables all three roles with `command=codex`, `args=["exec", "--sandbox", "workspace-write", "-o", "{artifact_path}", "..."]`, `timeout_seconds=7200`, `failure_policy=block`, and `prompt_template=risk-json-v1`. Annotation output is risk-only; it cannot approve, skip, modify, or bypass any Waygate gate. Legacy Waygate built-in Codex annotation args are normalized automatically; custom `--annotation-agent-cmd` commands are left unchanged.

Annotation agents run as controller-side subprocesses, not in the tmux builder pane. Before the human gate, the controller pane prints compact Chinese lifecycle lines such as `标注 Agent 开始：角色=requirements_annotation 后端=codex 产物=<path>`, `标注 Agent 完成：角色=requirements_annotation 返回码=0 用时=<duration>`, or `标注 Agent 失败：角色=requirements_annotation 错误=<summary> 产物=<path> 用时=<duration>`; `--color always` and TTY `--color auto` color the agent label and status, while `--color never` stays plain text. stdout/stderr stay captured in artifacts and events. Once a fresh annotation artifact matches the current gate body, the human gate menu shows the artifact path, issue count, and compact Chinese summary, and Plannotator review metadata records the same artifact reference. Human-facing annotation fields must be Simplified Chinese; English-only `summary` or issue messages are rejected instead of being shown as current annotations. Requirements revision reruns the Requirements annotation role, and each artifact records `gate_content_hash` plus `human_language=zh-CN` so stale annotation output from an older gate body or older prompt contract is not reused.

### `start`

Initialize if needed, then continuously drive the workflow.

```bash
waygate start --state-dir .rrc-controller-v1.0 --spec ./requirements.md
```

### `drive`

Continue an existing session until a human gate, terminal state, or step limit.

```bash
waygate drive --state-dir .rrc-controller-v1.0
```

### `run`

Advance the workflow once, or until terminal state with `--until-done`.

```bash
waygate run --state-dir .rrc-controller-v1.0
waygate run --state-dir .rrc-controller-v1.0 --until-done
```

### `status`

Print current workflow status.

```bash
waygate status --state-dir .rrc-controller-v1.0
```

### `doctor`

Print installation, PATH, environment, and skill checks. This command does not read controller state or controller artifacts.

```bash
waygate doctor
waygate doctor --color always
```

### `approve`

Approve a human gate after reviewing its Markdown file.

```bash
waygate approve --state-dir .rrc-controller-v1.0 --gate requirements
waygate approve --state-dir .rrc-controller-v1.0 --gate unit-plan
waygate approve --state-dir .rrc-controller-v1.0 --gate final-acceptance
```

Final acceptance approval is processed by the next `run`, `drive`, `start`, or `go` step. When a live tmux agent pane is configured, Waygate dispatches a final status-sync prompt before release so the agent can update `task_plan.md`, `progress.md`, and `findings.md`.

### `revise`

Ask the agent to revise a requirements or unit-plan gate after feedback is written.

```bash
waygate revise --state-dir .rrc-controller-v1.0 --gate unit-plan
```

For blocked recovery, the interactive menu requires a non-empty human reason before routing to Unit Plan or Requirements rework. The Blocked Assist summary is context only; it is not a substitute for the human reason.

### `reject`

Reject final acceptance and route feedback to the right stage.

```bash
waygate reject --state-dir .rrc-controller-v1.0
```

### `migrate`

Upgrade older gate files to the current format.

```bash
waygate migrate --state-dir .rrc-controller-v1.0
```

## Important Options

| Option | Meaning |
| --- | --- |
| `--state-dir` | Controller state directory. |
| `--workspace-dir` | Target project directory. |
| `--target` / positional target | Acceptance target label. |
| `--runner` | `subprocess`, `tmux-claude`, or `tmux-codex`. |
| `--tmux-target` | Existing tmux pane target such as `1.2` or `%43`. |
| `--agent` | Agent command used by the runner. |
| `--dry-run` | Generate mock artifacts instead of calling a real agent. |
| `--max-steps` | Stop after a bounded number of automatic steps. |
| `--auto-approve` | Auto-generate low-risk approval artifacts in tests or controlled runs. |
| `--annotation-agent BACKEND` | Enable the same non-approving annotation backend for all roles. |
| `--annotation-agent ROLE=BACKEND` | Enable one annotation role; repeat for multiple roles. |
| `--no-annotation-agent ROLE|all` | Disable one annotation role or all roles. |
| `--annotation-agent-cmd ROLE='COMMAND ...'` | Override the full annotation command line, parsed with `shlex.split`. |
| `--annotation-agent-env-key ROLE=KEY` | Inherit only this env key name for the role; secret values are not stored. |
| `--annotation-agent-timeout ROLE=SECONDS` | Override role timeout. |
| `--annotation-agent-failure-policy ROLE=block|warn` | Choose whether annotation failures block the human gate or write warning evidence. |
| `--verbose` | Print detailed per-step output. |
| `--color auto|always|never` | Control compact output highlighting. |

## tmux Runner Notes

When `--tmux-target` is provided, Waygate probes the pane command, title, process tree, and visible output to detect Claude or Codex.

When `--runner tmux-codex` is provided without `--tmux-target`, Waygate searches the current tmux session for an existing Codex pane. It prefers a pane whose current path matches the target workspace. It does not auto-create Codex panes.

When Waygate auto-creates a Claude pane, the default command is:

```bash
claude --permission-mode bypassPermissions
```

Override it with:

```bash
export WAYGATE_AUTO_CLAUDE_PERMISSION_MODE=acceptEdits
export WAYGATE_AUTO_CLAUDE_COMMAND='claude --permission-mode dontAsk --model sonnet'
```

## State Directory

A session directory looks like this:

```text
.rrc-controller-v1.0/
  session.json
  events.jsonl
  change_requests.jsonl
  approvals/
    requirements-and-acceptance.md
    unit-plan.md
    final-acceptance.md
  artifacts/
    requirements-draft/
    unit-plan-draft/
    <unit-id>/
```

Do not commit `.rrc-controller-*` directories. They contain local run state and may include project-specific artifacts.

## Testing

Run the full test suite:

```bash
python -m pytest workflow_controller/tests -q
```

Run packaging verification:

```bash
python -m pytest workflow_controller/tests/test_packaging.py -q
```

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `requires --tmux-target` | You are outside tmux or no matching Codex pane was found. Pass `--tmux-target`. |
| Gate keeps returning for revision | Read the controller validation artifact under `artifacts/*/controller-validation-error.json`. |
| Verifier fails repeatedly | Inspect `verification.json` and the failed command output. |
| Agent writes `done.json` too early | Use tmux runner metadata and events to check post-done busy state. |
| Unexpected target state | Confirm `--workspace-dir`, `--state-dir`, and existing `session.json` match. |
