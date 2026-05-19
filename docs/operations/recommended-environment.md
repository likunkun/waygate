# Recommended Environment

[中文](recommended-environment.zh-CN.md) | [README](../../README.md)

This guide describes the local environment recommended for Waygate V0.6.0e. It is operational guidance for preparing a workstation or CI-like package verification host; it is not a new requirement intake format.

## Runtime

- Recommended Python versions: Python 3.11 or Python 3.12.
- Minimum compatibility target: Python 3.10.
- Standard full verification command:

```bash
python3 -m pytest workflow_controller/tests -q
```

Use the same Python environment for source execution and tests when possible. If a virtual environment is used, activate it before running Waygate or pytest so the imported `workflow_controller` package and command-line tools are consistent.

## Runner Tools

Waygate can run without a tmux agent pane by using the `subprocess` runner, but the normal interactive workflow depends on tmux-based runners:

- `tmux-claude` needs `tmux` and Claude Code. Waygate may create a Claude Code pane when it is launched inside tmux and no pane is provided.
- `tmux-codex` needs `tmux` and an existing Codex pane. Waygate can discover a matching Codex pane in the current tmux session.
- `waygate doctor` reports both the `tmux` command and whether the current shell is inside a tmux session.

Claude Code, Codex, and Plannotator are optional runtime tools, not Debian package dependencies. Missing optional tools should produce warning/manual action entries in `waygate doctor`, not a failed doctor command.

## Human Review

Plannotator is optional but recommended for browser-assisted review of Requirements, Unit Plan, and Final Acceptance gates. The recommended Plannotator port is `20000`.

Typical review setup:

```bash
waygate go V1.0 --plannotator-port 20000
```

Requirements approval remains anchored to `approvals/requirements-and-acceptance.md`. Prototype review HTML, when present for UI/Web work, is an auxiliary review view and not the approval source.

## Agent Skills

Waygate does not install agent skills. Skills belong to the selected agent runtime, such as Claude Code or Codex. Install required skills in each runtime that will execute Waygate roles.

`waygate doctor` scans common local skill roots:

- `~/.agents/skills`
- `~/.codex/skills`
- `~/.codex/superpowers/skills`
- `~/.config/opencode/skills`

It reports readable `SKILL.md` files and warns when recommended workflow skills such as planning, brainstorming, TDD, systematic debugging, test strategy, code simplification, or verification-before-completion are missing. These warnings are advisory; controller state and gate artifacts remain the facts for workflow completion.

Recommended skill boundary:

- Keep workflow skills such as planning, TDD, debugging, testing strategy, verification, and code simplification in the agent environment.
- Do not assume the Debian package installs or upgrades those skills.
- Treat skills as role enablement, while `session.json`, `events.jsonl`, `approvals/`, and `artifacts/` remain the workflow facts.

## Debian Packaging

Package builds require shell tools and `dpkg-deb`:

```bash
bash packaging/debian/build-deb.sh
```

The generated package installs the `waygate` wrapper under `/usr/bin/waygate`, the Python package under `/usr/lib/waygate`, and user documentation under `/usr/share/doc/waygate`.

V0.6.0e also installs:

- `/usr/share/doc/waygate/docs/operations/recommended-environment.md`
- `/usr/share/doc/waygate/docs/operations/recommended-environment.zh-CN.md`
- `/usr/share/doc/waygate/docs/product/waygate-introduction-and-best-practices.md`
- `/usr/share/doc/waygate/docs/product/waygate-introduction-and-best-practices.zh-CN.md`

## PATH Shadow Handling

A user-level wrapper such as `~/.local/bin/waygate` can appear before `/usr/bin/waygate` in `PATH`. That is a PATH shadow situation: the shell may run an older wrapper while the Debian package is installed correctly.

Use:

```bash
waygate doctor
```

If the report shows PATH shadow, rename or remove the user-level wrapper after confirming the desired install, then run:

```bash
hash -r
```

The Debian post-install script warns about PATH shadow but does not delete user files.
