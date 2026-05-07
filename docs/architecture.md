# Waygate Architecture

[中文](architecture.zh-CN.md) | [README](../README.md)

Waygate is organized around a simple boundary: agents produce work, while the controller owns workflow state, gates, routing, and completion evidence.

## Core Principles

1. **State is the source of truth.** Chat summaries are not completion evidence.
2. **Humans approve gates.** Requirements, Unit Plan, Bug Fix, and Final Acceptance are Markdown review points.
3. **Implementation is unit-scoped.** The controller advances one unit at a time.
4. **Evidence is structured.** Verifier results are mapped back to acceptance criteria and test cases.
5. **Failures route intentionally.** A defect can route to requirements, unit planning, implementation, bug-fix, or blocked state.

## Package Layout

```text
workflow_controller/
  cli.py
  rrc_controller.py
  acceptance_obligations.py
  journeys.py
  requirements_dialogue_brief.py
  scope_audit.py

  gates/
    generators/
    parsers/
    validators/

  prompts/
    requirements.py
    unit_plan.py
    builder.py
    bug_fix.py

  runners/
    base.py
    codex.py
    tmux_claude.py
    opencode.py

  state_machine/
    actions.py
    store.py
    transitions.py

  steps/
    requirements.py
    unit_plan.py
    builder.py
    bug_fix.py

  tests/
```

## Runtime State

Each target has a state directory, usually:

```text
<target-project>/.rrc-controller-v1.0/
```

Important files:

| Path | Purpose |
| --- | --- |
| `session.json` | Current workflow state. |
| `events.jsonl` | Append-only event history. |
| `change_requests.jsonl` | Requirements and acceptance change ledger. |
| `approvals/*.md` | Human gate review files. |
| `artifacts/` | Prompts, runner outputs, verification evidence, audits. |

State directories are local run data and should not be committed.

## Controller Layer

`rrc_controller.py` is the orchestration layer. It coordinates:

- initialization and existing-session compatibility checks;
- state transitions and next allowed actions;
- human gate generation, approval, rejection, and revision;
- runner selection and tmux target resolution;
- builder, refiner, reviewer, verifier, and final acceptance routing;
- scope audit and evidence validation.

The controller intentionally remains the completion authority. Agent output can request completion by writing a `done.json`, but the controller still validates run IDs, reviewer/verifier artifacts, gate state, and evidence.

## Gate Layer

The gate package is split into:

| Layer | Responsibility |
| --- | --- |
| `generators` | Render human-readable Markdown gates. |
| `parsers` | Parse confirmations, state patches, and reviewer input. |
| `validators` | Enforce traceability, test presence, Journey mapping, and gate quality. |

Markdown is the human review view. The roadmap moves toward first-class structured contracts while keeping Markdown as a review surface.

## Runner Layer

Runners execute agent work and return metadata plus artifacts.

Current runner families:

- `subprocess`: run a local command.
- `tmux-claude`: dispatch prompts into a Claude Code tmux pane.
- `tmux-codex`: dispatch prompts into a Codex tmux pane.
- `opencode`: placeholder for a future first-class runner.

tmux runners use prompt files and `DONE_FILE` JSON completion signals. The controller validates `run_id` to avoid stale completion signals from previous runs.

## Evidence Layer

Verifier output is stored as `verification.json`. Modern verifier artifacts include:

- schema version;
- command results;
- evidence rows;
- acceptance criterion IDs;
- test case IDs;
- journey IDs where applicable;
- artifact references.

Final acceptance uses this evidence to render matrices rather than relying on a free-form summary.

## Human Review Model

Waygate has four major human gates:

| Gate | Purpose |
| --- | --- |
| Requirements | Confirm scope, acceptance criteria, design/architecture references, and journeys. |
| Unit Plan | Confirm unit breakdown, test cases, verification commands, and state patch. |
| Bug Fix | Confirm defect scope, expected behavior, actual behavior, root cause, and regression evidence. |
| Final Acceptance | Confirm evidence, Journey coverage, scope audit, and rejection route. |

Plannotator can be used as a browser-assisted review surface, but the canonical gate files remain in `approvals/`.

## Security and Data Handling

Waygate records environment variable keys where needed for reproducibility, but should not record secret values in artifacts. Runner stdout/stderr redaction and metadata rules are part of the current implementation, and stronger file/tool policy is planned.

Do not publish local state directories. They can contain project-specific prompts, generated artifacts, and review context.
