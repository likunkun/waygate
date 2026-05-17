# Waygate

[中文文档](README.zh-CN.md) | [Usage](USAGE.md) | [Architecture](docs/architecture.md) | [Workflow](docs/workflow.md) | [Roadmap](ROADMAP.md)

Waygate is a workflow control surface for AI coding delivery.

It is not another chat client and it is not a code generator. Waygate wraps AI coding work in a recoverable, auditable delivery loop: requirements, unit planning, implementation, refinement, review, verification, and final acceptance. The agent can draft and implement, but it cannot declare the work complete by itself.

## Why Waygate

Direct AI coding sessions often fail in predictable ways:

- The AI takes shortcuts: it implements the easy slice and quietly leaves the rest undone.
- It builds functions, but not the real user scenarios, journeys, edge cases, or acceptance paths.
- Humans stay trapped in the loop, repeatedly typing "continue" because the process has no durable next step.
- The final result looks different from the expectation, and there is no clear record of when the drift happened.
- Across multiple projects, conversations, panes, and agents, the human operator gets pulled into context management instead of product judgment.

Waygate exists to make AI coding work behave like a controlled delivery workflow instead of a long chat. It turns "please build this" into explicit gates: requirements, unit planning, implementation, refinement, review, verification, and final acceptance. Each gate writes durable files, every acceptance criterion is tied to evidence, and failures route back to the right stage instead of being buried in a transcript.

The point is not to remove the human. The point is to move human attention to the decisions that matter: approving requirements, checking scope, accepting evidence, and choosing the right rework route. Waygate handles the repetitive controller work, keeps state on disk, and makes it harder for an agent to skip work while still claiming success.

## Current Capabilities

| Area | What Waygate provides |
| --- | --- |
| Recoverable workflow | `session.json`, `events.jsonl`, approvals, and artifacts form the source of truth. |
| Requirements gates | Human-readable requirements and acceptance criteria with traceability checks. |
| Unit planning gates | Unit plans must map objectives, acceptance criteria, test cases, journeys, and verification commands. |
| Runner support | Subprocess, `tmux-claude`, and `tmux-codex` runners. Existing tmux panes can be detected automatically. |
| Refinement and review | Builder output can pass through CodeSimplifier/Refiner and Reviewer roles before verification. |
| Verification evidence | Verifier output includes structured evidence rows for ACs, test cases, commands, and artifacts. |
| Final acceptance | Final approval is a gate with evidence, journey coverage, scope audit, and rejection routing. |
| Bug-fix loop | Final acceptance defects can enter a dedicated bug-fix gate without rewriting requirements. |
| Debian package | `packaging/debian/build-deb.sh` builds a `waygate` command package. |

## Local Dependencies

Waygate runs as Python 3 code. Local development and verification use `python -m pytest workflow_controller/tests -q`, so `pytest` must be available in the Python environment.

Real agent execution depends on the selected runner:

- `tmux-claude` requires `tmux` and Claude Code. Waygate can create a Claude Code pane in tmux when no pane is provided.
- `tmux-codex` requires `tmux` and an existing Codex pane. Waygate can discover a matching Codex pane in the current tmux session.
- Plannotator is optional but recommended for browser-assisted human gate review; configure it with `--plannotator-command` and `--plannotator-port`.
- Project-specific agent skills are loaded by the agent runtime, not by the Debian package; keep required skills installed in the agent environment.
- Debian package builds require standard shell tools and `dpkg-deb`.

Waygate Markdown spec intake is available through `--spec <path>` on `init`, `start`, and `go`. In V0.5.6 this supports local Waygate Markdown spec files only; detected external formats are deferred rather than imported silently.

## Skills Used by Waygate Agents

Waygate does not install agent skills into Claude Code, Codex, or other agent runtimes. It assumes the selected agent environment already has the skills needed by the task. The controller makes the workflow auditable; skills make each agent role better at its specialized work.

The `test-strategy` skill is a less-common external skill, not something installed by the Waygate Debian package. Install it in each agent runtime environment that will need it:

```bash
npx skills add AbsolutelySkilled/AbsolutelySkilled --skill test-strategy
```

Recommended baseline skills:

| Skill | Stage | Why it matters |
| --- | --- | --- |
| `planning-with-files` | Project setup, long-running work, recovery after `/clear` | Maintains `task_plan.md`, `progress.md`, and `findings.md` as persistent project memory so multi-step work does not depend on a single chat context. |
| `superpowers:using-superpowers` | Agent startup | Forces the agent to check applicable skills before acting, reducing unstructured improvisation. |
| `superpowers:brainstorming` | Requirements discovery and scope shaping | Helps turn vague goals into explicit requirements before implementation begins. |
| `superpowers:writing-plans` | Unit Plan / implementation planning | Produces task-by-task implementation plans after requirements are clear. |
| `superpowers:test-driven-development` | Builder and bug-fix work | Keeps behavior changes anchored in failing tests before implementation. |
| `superpowers:systematic-debugging` | Failures, verifier issues, runner problems | Requires root-cause investigation before fixes, which is important when controller, runner, and agent state interact. |
| `test-strategy` or `testing-strategy` | Requirements and Unit Plan test matrix | Helps define meaningful verification layers instead of relying on lint or typecheck alone. |
| `code-simplifier` | Refiner stage after Builder | Reviews recent implementation for clarity and maintainability while preserving behavior. |
| `superpowers:verification-before-completion` | Before DONE, review, release, or final acceptance | Prevents success claims without fresh evidence. |
| `superpowers:requesting-code-review` and `superpowers:receiving-code-review` | Reviewer and rework loops | Keeps review findings concrete and prevents blind acceptance of weak feedback. |
| `superpowers:executing-plans` or `superpowers:subagent-driven-development` | Executing approved multi-step plans | Runs a written plan task by task, with checkpoints and review boundaries. |
| `webapp-testing` | Browser-visible UI or workflow verification | Uses Playwright-style checks and screenshots when user-facing browser behavior must be verified. |
| `frontend-design` or `ui-ux-pro-max` | UI-heavy requirements | Guides interface design, interaction states, layout, and accessibility when the target includes frontend work. |
| `pdf`, `docx`, `pptx` | Document-specific tasks | Used only when the project requirements involve those file types. |

Typical mapping:

```text
Requirements Draft        -> brainstorming, planning-with-files
Requirements Gate         -> test-strategy/testing-strategy when ACs need test design
Unit Plan                 -> writing-plans, test-strategy/testing-strategy
Builder                   -> test-driven-development, systematic-debugging when failures appear
Refiner                   -> code-simplifier
Reviewer                  -> requesting-code-review / receiving-code-review
Verifier                  -> verification-before-completion, webapp-testing for browser flows
Final Acceptance / Rework -> systematic-debugging, executing-plans or subagent-driven-development
Long sessions             -> planning-with-files throughout
```

## Installation

Build and install the Debian package:

```bash
bash packaging/debian/build-deb.sh
sudo apt install ./dist/waygate_*_all.deb
waygate --help
waygate doctor
```

If `waygate doctor` reports a user-level wrapper such as `~/.local/bin/waygate` before `/usr/bin/waygate`, rename or remove the user-level wrapper and run `hash -r`. The Debian package warns about this shadowing but does not delete user files.

For local development, run from the source tree:

```bash
cd /path/to/workflow-controller
python -m workflow_controller.cli --help
```

The project test environment used during development is:

```bash
python -m pytest workflow_controller/tests -q
```

## Quick Start

Run Waygate from the target project root:

```bash
waygate go V1.0
```

This creates or resumes:

```text
<target-project>/.rrc-controller-v1.0/
```

In a tmux session, Waygate can create or detect an agent pane. If you already have a Codex or Claude pane, pass it explicitly:

```bash
waygate go V1.0 --tmux-target 1.2
```

To force local subprocess execution:

```bash
waygate go V1.0 --runner subprocess
```

To exercise the workflow without calling a real agent:

```bash
waygate go V1.0 --runner subprocess --dry-run --max-steps 20
```

See [USAGE.md](USAGE.md) for the complete CLI guide.

## Workflow

```text
Requirements Draft
  -> Requirements Gate
  -> Unit Plan
  -> Unit Plan Gate
  -> Builder
  -> CodeSimplifier / Refiner
  -> Reviewer
  -> Verifier
  -> Final Acceptance Gate
  -> Agent Status Sync
  -> Done
```

Defects found at final acceptance can route into:

```text
Bug Fix Gate
  -> Bug Fix Agent
  -> Regression Verifier
  -> Final Acceptance Gate
```

Read the detailed workflow in [docs/workflow.md](docs/workflow.md).

## Repository Layout

```text
workflow_controller/
  cli.py                     # CLI entry point
  rrc_controller.py          # Main orchestration layer
  gates/                     # Gate generators, parsers, validators
  prompts/                   # Role prompt builders
  runners/                   # Subprocess and tmux runners
  state_machine/             # State storage and transitions
  steps/                     # Workflow step implementations
  tests/                     # Pytest suite

packaging/debian/            # Debian package builder
docs/                        # Architecture and workflow documentation
```

## Documentation

| Document | English | Chinese |
| --- | --- | --- |
| README | [README.md](README.md) | [README.zh-CN.md](README.zh-CN.md) |
| CLI usage | [USAGE.md](USAGE.md) | [USAGE.zh-CN.md](USAGE.zh-CN.md) |
| Architecture | [docs/architecture.md](docs/architecture.md) | [docs/architecture.zh-CN.md](docs/architecture.zh-CN.md) |
| Workflow | [docs/workflow.md](docs/workflow.md) | [docs/workflow.zh-CN.md](docs/workflow.zh-CN.md) |
| Roadmap | [ROADMAP.md](ROADMAP.md) | [ROADMAP.zh-CN.md](ROADMAP.zh-CN.md) |

`task_plan.md`, `progress.md`, and `findings.md` are development history files for this repository. They are useful for maintainers, but they are not required to use Waygate.

## Project Status

Waygate is actively evolving. The current implementation is suitable for controlled local workflows where you want durable state, gate documents, and verification artifacts around AI coding tasks. It is not yet a hosted service and does not yet enforce sandboxed per-role write policies.

See [ROADMAP.md](ROADMAP.md) for planned execution isolation, clean verification, structured contracts, and CI integration.

## Contributing

Issues and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before sending changes.

## License

Waygate is released under the [MIT License](LICENSE).
