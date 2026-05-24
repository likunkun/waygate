# Final Acceptance Guided Walkthrough Policy

Final Acceptance is a human gate after automated verifier evidence has already passed. Waygate prepares a guided walkthrough before generating the Final Acceptance gate so the reviewer sees the Agent-provided entrypoint, launch state, real system steps, expected observations, and an optional place to record human findings.

Waygate does not infer the true product entrypoint from package scripts, README files, or repository shape. The Unit Planner and Builder must provide the human-visible system walkthrough package; Waygate validates that package and renders it in Final Acceptance. Human approval is authoritative at the Final Acceptance gate once deterministic evidence checks have passed; an empty observation record is treated as review context risk, not an approval blocker.

## Unit Plan Contract

Closure, Web, and UI units must declare `final_acceptance_walkthrough.inspection` in the Controller State Patch.

Required inspection fields:

- `surface_kind`: one of `browser`, `api`, `cli`, or `artifact`.
- `entrypoint`: the URL, API endpoint, CLI command, or artifact path a human can open or run.
- `manual_steps`: real system operations the human performs. These cannot be only pytest, Playwright, golden path, or other automated verification commands.
- `expected_observations`: the page state, response, terminal output, log, status, or artifact content the human should see.

Closure units may also declare `final_acceptance_walkthrough.launch` in the Controller State Patch.

Allowed launch modes:

- `agent_start`: Waygate starts the declared command before the Final Acceptance gate is generated.
- `manual_only`: Waygate does not start a process; the gate shows manual launch instructions.
- `not_required`: no app launch is needed for the final walkthrough.

`agent_start` requires:

- `command`: complete startup command.
- At least one readiness hint: `ready_url`, `ready_command`, or `ready_output_contains`.
- Optional `cwd`, which must stay inside the workspace.
- Optional `env_keys`, with environment variable names only. Secret values must not be stored in Unit Plan state, artifacts, or logs.
- Optional `ready_timeout_seconds`, defaulting to 120 seconds.
- Optional `stop_command` for cleanup guidance.

`manual_only` requires `manual_launch_instructions`.

## Builder Confirmation

Builder must confirm the final human walkthrough entrypoint before DONE. If implementation changes the effective entrypoint from the Unit Plan, the Builder DONE payload should include:

```json
{
  "final_acceptance_walkthrough": {
    "inspection": {
      "surface_kind": "browser",
      "entrypoint": "http://127.0.0.1:5173/orders",
      "manual_steps": ["Open the orders page and create ORD-100"],
      "expected_observations": ["ORD-100 is visible with submitted status"],
      "reason": "Port 4173 was occupied; Vite selected 5173."
    }
  }
}
```

Final Acceptance prioritizes the Builder-confirmed inspection entrypoint. If Builder does not provide one, Waygate falls back to the Unit Plan inspection entrypoint.

## Prepare Phase

After verifier evidence passes and before the Final Acceptance gate is generated, Waygate enters `FINAL_WALKTHROUGH_PREPARE`.

For `agent_start`, Waygate runs the startup command, checks readiness, and writes `artifacts/<unit>/final-walkthrough-launch.json` plus a launch log. Startup failure does not approve or bypass Final Acceptance; the failure is shown in the gate so the reviewer can choose the correct rejection route.

For `manual_only` and `not_required`, Waygate writes an audit artifact without dispatching a launch command.

## Final Acceptance Gate

The gate includes:

- `## Agent 提供的人工走查入口`: surface kind, final entrypoint, manual steps, expected observations, and the reason for any Builder override.
- `## 人工系统观察记录（Review Notes）`: observed entrypoint, actual observation, data/account/fixture, and issues or evidence path. This section is blank by default and can be filled by the human reviewer for audit context.
- `## Golden Path 人工走查`: launch status, ready check, access URL or entrypoint, log artifact, stop command, fixture or test data, user steps, expected results, and reviewer checklist.

`waygate approve --gate final-acceptance` and Plannotator Approve both preserve the human decision. If the gate is approved without a filled observation record, Waygate still accepts the Final Acceptance gate after deterministic evidence, scope audit, journey, prototype, real E2E, document deliverable, and walkthrough-entrypoint checks have passed.

Automated verifier and golden path evidence remain required prerequisites before the gate is presented. They do not restrict a human reviewer from approving the final gate after reviewing the available evidence and risks.

The existing `## 修改清单` and Rejection Routing semantics remain unchanged.
