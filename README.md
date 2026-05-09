# Waygate

[中文文档](README.zh-CN.md) | [Usage](USAGE.md) | [Architecture](docs/architecture.md) | [Workflow](docs/workflow.md) | [Roadmap](ROADMAP.md)

Waygate is a workflow control surface for AI coding delivery.

It is not another chat client and it is not a code generator. Waygate wraps AI coding work in a recoverable, auditable delivery loop: requirements, unit planning, implementation, refinement, review, verification, and final acceptance. The agent can draft and implement, but it cannot declare the work complete by itself.

## Why Waygate

Direct AI coding sessions often fail in predictable ways:

- scope drifts during a long conversation;
- a model says "done" without durable evidence;
- test results live only in chat history;
- interrupted tasks cannot be resumed reliably;
- final review issues have no clear route back to requirements, planning, implementation, or a bug-fix loop.

Waygate makes those transitions explicit. State is written to disk, human gates are Markdown files, verification evidence is structured, and failures route to the right stage instead of being hidden in a transcript.

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

## Installation

Build and install the Debian package:

```bash
bash packaging/debian/build-deb.sh
sudo apt install ./dist/waygate_0.5.3_all.deb
waygate --help
```

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
