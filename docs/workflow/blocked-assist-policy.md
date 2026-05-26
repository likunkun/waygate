# Blocked Assist Policy

Blocked Assist is an optional diagnostic layer for workflows that are already `status=blocked`. It helps the human inspect the blocker, but it does not approve, unblock, revise, reject, or mutate controller gates by itself.

Interactive `waygate drive`, `waygate start`, and `waygate go` show a blocked menu when they stop on `status=blocked`:

- start or continue a Blocked Assist dialogue;
- continue after a human says the external condition is fixed;
- route to Unit Plan rework;
- route to Requirements change;
- route through Final Acceptance rejection when applicable;
- keep the workflow blocked.

`waygate status` stays read-only. It may print guidance that Blocked Assist is available from interactive commands, but it does not open a menu.

## Assist Artifact

Each assist run writes a summary under:

```text
artifacts/blocked-assist/<run-id>/blocked-assist-summary.json
```

The controller stores a `blockedAssist` pointer in `session.json` with the assist status, run id, original blocked category and reason, summary path, and last recommended route. The summary includes:

- `diagnosed_category`
- `resolved_claim`
- `human_actions_taken`
- `recommended_route`
- `route_reason`
- `evidence_refs`
- `remaining_risks`
- `safe_to_continue_reason`

The prompt explicitly limits the agent to diagnosis, questions, troubleshooting suggestions, and summary writing. It must not edit Requirements, Unit Plan, Final Acceptance, approval files, source code, tests, or controller state.

## Human Reason

Any route that changes state requires a non-empty human-confirmed `human_reason`. Agent summary text can be used as a draft or context, but it is never the authoritative reason.

- Continue uses the existing unblock path and is allowed only for environment, external dependency, annotation runtime, or Final Acceptance blocked conditions.
- Unit Plan rework writes the human reason and optional assist summary path into `unitPlanRevisionFeedback` before regenerating the Unit Plan.
- Requirements change writes the human reason and optional assist summary path into `requirementsRevisionFeedback` and `change_requests.jsonl`.
- Final Acceptance routing writes the human reason and optional assist summary path into rejection feedback before applying the selected rejection route.
- Contract blockers cannot continue directly even if the assist summary claims they are resolved; they must route through Requirements, Unit Plan, or Final Acceptance.

The controller appends audit events for `blocked_assist_started`, `blocked_assist_completed`, `blocked_assist_failed`, `blocked_assist_reclassified`, and `blocked_assist_resolution_selected`.
