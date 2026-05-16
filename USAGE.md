# Waygate Usage

[中文](USAGE.zh-CN.md) | [README](README.md)

This document is the CLI-oriented guide for Waygate. For concepts and architecture, see [docs/workflow.md](docs/workflow.md) and [docs/architecture.md](docs/architecture.md).

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
sudo apt install ./dist/waygate_0.6.0b_all.deb
waygate --help
```

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
```

## Prototype Review Bundle

For UI/UX or Web-system requirements, the Requirements drafter must write `artifacts/requirements-draft/prototype-manifest.json`. Waygate validates it, copies local image/HTML prototypes into `artifacts/requirements-draft/prototypes/`, renders `plannotator-review.md`, and opens that review bundle in Plannotator. Approval status still belongs to `approvals/requirements-and-acceptance.md`.

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
