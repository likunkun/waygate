# Stop Guidance and Unblock Policy

Waygate must explain every stopped state with a reason, the next human action, and a copyable command. The first status line remains stable for scripts:

```text
currentStep=<step> status=<status> nextAction=<action> projectTargetVersion=<target>
```

Additional guidance is printed after that line by `status`, `run`, `drive`, `start`, and `go` when the workflow stops at a recoverable agent wait, human gate, blocked state, max-step/no-progress stop, or active state with no next action.

## Recoverable Wait Boundary

`recoverableAgentWait` is only for runner `timeout`, idle-without-DONE, or equivalent pending agent silence. It keeps approvals and artifacts intact and records why the current automatic loop stopped.

The next `waygate go --state-dir <state-dir>` invocation, or another execution command such as `run`, `drive`, or `start`, consumes `recoverableAgentWait`, appends an `agent_wait_auto_resumed` event, and lets the same stage compute its next action again.

Execution commands must not clear explicit `blocked` states. A blocked workflow still needs `waygate unblock` for environment/external dependency blockers or a formal `waygate revise` / Final Acceptance rejection route for contract changes.

## Blocked Boundary

Explicit agent or controller `blocked` means the workflow needs a reasoned route, not blind rerun.

- Environment or external dependency blockers include missing `PRODUCTION_WEB_BASE_URL`, `PRODUCTION_API_BASE_URL`, Docker, Compose, Playwright/browser runtime, ports, services, credentials, permissions, database/API access, or other external conditions.
- Unit Plan blockers mean approved planning, sequencing, verification commands, evidence policy, or execution constraints are not executable as written.
- Requirements blockers mean approved requirements, acceptance criteria, out-of-scope decisions, or journey contracts must change.
- Final Acceptance blocked route means the reviewer could not judge because environment, data, access, or evidence was unavailable.

## Unblock Boundary

`waygate unblock --state-dir <state-dir> --reason "<fixed condition>"` is allowed only after an environment or external dependency blocker has been fixed by a human. It is not an approval and it does not edit Requirements, Unit Plan, Final Acceptance gates, artifacts, or approval hashes.

On success, `unblock` clears `status=blocked`, clears `blockedReason` and `blockedContext`, preserves approvals, appends a `blocked_state_unblocked` audit event, and lets the current phase recompute `nextAction`.

If the blocker is a Unit Plan or Requirements contract problem, `unblock` refuses and prints the formal route:

```text
waygate revise --gate unit-plan --state-dir <state-dir> --reason "..."
waygate revise --gate requirements --state-dir <state-dir> --reason "..."
```

Final Acceptance non-environment rework remains controlled by the Final Acceptance rejection route.

## Builder Blocked Reconciliation

When Builder returns `status=blocked` in the runner result or DONE payload, Waygate persists the official controller state:

```text
status=blocked
currentStep=EXECUTE_UNIT
blockedReason=<DONE summary>
blockedContext.source=builder_agent
```

It also appends a `builder_agent_blocked` event and preserves existing approvals. If an older session is still `active` at a Builder-capable stage but `artifacts/<unit>/builder-summary.json` already shows Builder blocked, `status` and `get_status()` reconcile it into the same official blocked state.
