# Recoverable Agent Timeout Policy

Waygate treats agent non-response as a recoverable wait when the runner reports `timeout` or `agent_idle_without_done`. This covers Requirements Draft, Unit Plan Draft, Builder, Refiner, Bug Fix Agent, and Final Acceptance Agent Sync dispatches.

Recoverable waits are not Requirements or Unit Plan contract failures. The controller keeps the workflow on the same stage, keeps `status=active`, clears `blockedReason`, records `recoverableAgentWait` in `session.json`, appends an `agent_wait_recoverable` event, and stops the automatic loop. Human approvals are not invalidated.

Use `waygate retry --state-dir <state-dir>` to clear `recoverableAgentWait` when the same stage should be attempted again. `retry` does not edit approvals, requirements, unit plans, or artifacts. For Requirements Draft, the next run may resume the existing pending run if its `done.json` and body arrive later; otherwise it dispatches according to the normal stage behavior.

If no `recoverableAgentWait` exists, `retry` must refuse. Explicit `blocked` states are handled by the stop guidance policy: fix environment/external dependencies and run `waygate unblock --state-dir <state-dir> --reason "<fixed condition>"`, or use the formal Requirements / Unit Plan / Final Acceptance rework route when the approved contract must change.

Do not use `waygate revise` for transient runner silence. `waygate revise` remains limited to Requirements and Unit Plan contract rework:

- Requirements revision changes approved requirements or acceptance criteria and invalidates downstream approval as needed.
- Unit Plan revision changes planning, sequencing, coverage, or test strategy inside approved requirements.
- Agent timeout, idle-without-DONE, or delayed user response is a recoverable wait unless the agent explicitly returns `blocked` or the controller hits a real validation, verifier, environment, repeated-failure, or final-acceptance blocked route.

Runner subprocess timeouts are normalized to `status=timeout` and `returncode=124` so controller stages can apply the same recoverable wait policy across subprocess, tmux Claude, and tmux Codex runners.
