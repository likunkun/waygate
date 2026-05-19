# Recommended Environment

[中文](recommended-environment.zh-CN.md) | [README](../../README.md)

This guide describes the local environment recommended for Waygate V0.6.0h. It is operational guidance for preparing a workstation or CI-like package verification host; it is not a new requirement intake format.

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

## Recommended tmux config

For long-running agent panes, use a tmux config that keeps mouse scrolling, a large history buffer, and stable copy-mode defaults:

```tmux
set -g mouse on
set -g @scroll-speed 5
set -g history-limit 100000
set -g @copy-mode-vi 'on'
```

`waygate doctor` checks only `~/.tmux.conf` and reports the result under `tmux_config`. It accepts `set -g key value` and `set-option -g key value`, handles simple quoted values such as `@copy-mode-vi 'on'`, and treats the last valid setting for a key as active. When a recommended setting is missing or different, doctor reports `status=warning`, the expected and actual value, and a manual action. It never edits `~/.tmux.conf` and never reloads tmux for you.

The top of the doctor report is summary-first and focus-first. Use `waygate doctor --color auto|always|never` to highlight status, P1 focus items, manual actions, and section headers for human scanning; non-TTY output stays plain by default.

```text
summary:
- overall: status=warning warnings=<n> manual_actions=<n>
focus:
- [P1] tmux_config: 4 warning(s); update ~/.tmux.conf and reload tmux config.
action_required:
- tmux_config.mouse: Add `set -g mouse on` to ~/.tmux.conf and reload tmux config.
```

## Human Review

Plannotator is optional but recommended for browser-assisted review of Requirements, Unit Plan, and Final Acceptance gates. The recommended Plannotator port is `20000`.

Typical review setup:

```bash
waygate go V1.0 --plannotator-port 20000
```

Requirements approval remains anchored to `approvals/requirements-and-acceptance.md`. Prototype review HTML, when present for UI/Web work, is an auxiliary review view and not the approval source.

Waygate displays Plannotator and prototype preview URLs with `0.0.0.0` by default so remote reviewers can identify that the service is listening beyond loopback. Remote browsers usually need to replace `0.0.0.0` with the IP or hostname of the machine running Waygate. `WAYGATE_PREVIEW_HOST` overrides the controller prototype preview host. Waygate also passes `PLANNOTATOR_HOST=0.0.0.0` to Plannotator by default; whether that changes Plannotator's own bind address depends on the installed Plannotator binary.

## Agent Skills

Waygate does not install agent skills. Skills belong to the selected agent runtime, such as Claude Code or Codex. Install required skills in each runtime that will execute Waygate roles.

`waygate doctor` scans common local skill roots:

- `~/.agents/skills`
- `~/.codex/skills`
- `~/.codex/superpowers/skills`
- `~/.config/opencode/skills`

It reports readable `SKILL.md` files and warns when recommended workflow skills are missing. The recommendation groups are aligned with the README baseline: `planning-with-files`, startup skill checks, brainstorming, writing plans, TDD, systematic debugging, `test-strategy` / `testing-strategy`, `code-simplifier`, verification-before-completion, code review, plan execution, `webapp-testing`, and `frontend-design` / `ui-ux-pro-max` for UI-heavy work. These warnings are advisory; controller state and gate artifacts remain the facts for workflow completion.

`waygate doctor` also reports `claude_assets` for `~/.claude/commands`, `~/.claude/agents`, `~/.claude/rules`, and `~/.claude/plugins`. It reports only path, status, and count; it does not read cache, file-history, secrets, tokens, or environment variable values.

Recommended skill boundary:

- Keep workflow skills such as planning, TDD, debugging, testing strategy, verification, code simplification, code review, webapp testing, and UI/UX design support in the agent environment.
- Do not assume the Debian package installs or upgrades those skills.
- Treat skills as role enablement, while `session.json`, `events.jsonl`, `approvals/`, and `artifacts/` remain the workflow facts.

## Debian Packaging

Package builds require shell tools and `dpkg-deb`:

```bash
bash packaging/debian/build-deb.sh
```

The generated package installs the `waygate` wrapper under `/usr/bin/waygate`, the Python package under `/usr/lib/waygate`, and user documentation under `/usr/share/doc/waygate`.

V0.6.0h also installs:

- `/usr/share/doc/waygate/docs/operations/recommended-environment.md`
- `/usr/share/doc/waygate/docs/operations/recommended-environment.zh-CN.md`
- `/usr/share/doc/waygate/docs/product/waygate-introduction-and-best-practices.md`
- `/usr/share/doc/waygate/docs/product/waygate-introduction-and-best-practices.zh-CN.md`

## PATH Shadow Handling

A user-level wrapper such as `~/.local/bin/waygate` can appear before `/usr/bin/waygate` in `PATH`. That is a PATH shadow situation: the shell may run an older wrapper while the Debian package is installed correctly.

Use:

```bash
waygate doctor
waygate doctor --color auto
```

If the report shows PATH shadow, rename or remove the user-level wrapper after confirming the desired install, then run:

```bash
hash -r
```

The Debian post-install script warns about PATH shadow but does not delete user files.
