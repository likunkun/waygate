# Waygate Workflow

[中文](workflow.zh-CN.md) | [README](../README.md)

Waygate turns an AI coding target into a staged delivery loop. The controller drives the loop and stops at human gates when review is required.

## High-Level Flow

```text
Requirements Draft
  -> Requirements Gate
  -> Unit Plan Draft
  -> Unit Plan Gate
  -> Builder
  -> CodeSimplifier / Refiner
  -> Reviewer
  -> Verifier
  -> Final Acceptance Gate
  -> Agent Status Sync
  -> Done
```

If final acceptance identifies a defect within approved scope:

```text
Final Acceptance rejection
  -> Bug Fix Gate
  -> Bug Fix Agent
  -> Regression Verifier
  -> Final Acceptance Gate
```

## Requirements Stage

The requirements drafter creates a Markdown gate with:

- product goal and scope;
- acceptance criteria;
- verification layers;
- Journey definitions when cross-step behavior matters;
- design and architecture traceability;
- target-project infrastructure facts in `## 4.9`;
- assumptions and risks.

When no supported `--spec` is provided, the first drafter response is still a direct clarification question in the tmux pane. After a concrete user answer, the drafter reads project context and audits the seven infrastructure categories: repository, runtime, debugging, reference environment, documentation, architecture/interaction/interface, and dependencies. If facts are still missing, it keeps asking the user directly.

User-supplied infrastructure facts are not accepted as verified by default. The drafter should check them through non-destructive sources such as the local repository, configuration files, README/USAGE, docs, state-dir artifacts, package manifests, test commands, or existing verification output. External systems, production environments, private wiki/API sources, and other inaccessible facts must be marked as user-provided and not directly verified. Section `## 4.8` records questions, answers, verification methods, conclusions, and residual risks; section `## 4.9` records each infrastructure fact's source and verification status.

Before a human sees the gate, the controller can preflight it. Missing AC mapping, missing verification layers, and malformed traceability can route the draft back to the drafter automatically.
The preflight also rejects vague infrastructure placeholders such as `暂无` or `不清楚`, unsupported `未发现` / `没有` claims, and 4.9 statements that claim `用户确认` or `已验证` without corresponding 4.8 traceability.

UI, Web, clickable prototype, prototype evidence, and production UI consistency work must use `ui-ux-pro-max`. `frontend-design` can assist new visual exploration or local polish, but cannot replace `ui-ux-pro-max` for existing product UI/prototype consistency. The full V0.6.0k policy is registered in [docs/workflow/ui-ux-skill-policy.md](workflow/ui-ux-skill-policy.md).

## Unit Plan Stage

The Unit Plan defines what the implementation agent may do. It should include:

- objective coverage;
- execution units;
- `workflow_validation_level`;
- test cases;
- Journey mapping;
- verification commands;
- a `Controller State Patch` JSON block.

The controller validates the plan before approval. Invalid plans are not marked approved.
When Unit Plan preflight routes a draft back automatically, `unitPlanAutoRevisionMax` limits consecutive revisions for the same normalized invalid reason. A different invalid reason is treated as progress and resets the consecutive counter; request events record both the current-reason `attempt` and the cumulative `total_attempt`.

## Implementation Stage

The Builder receives a prompt file and works on one unit. A tmux or subprocess runner dispatches the prompt and waits for a completion signal.

The completion signal is not final proof. The controller still checks the run ID, artifacts, and later verifier evidence.

If the previous controller Verifier failed a specific command, the next Builder prompt includes a `Controller Verification Failure Protocol`. Builder must first rerun that exact command from the controller cwd, using the same command text rather than a filtered or adjacent command. Before DONE, the Builder must record `done_payload.controller_failure_resolution` with the failed command, reproduction result, root cause or mismatch analysis, fix summary, rerun exit code, and full approved verification run. Missing or mismatched resolution evidence blocks the workflow before Refiner; the controller Verifier remains the final source of truth.

## Refinement and Review

After Builder completes:

1. CodeSimplifier/Refiner can request cleanup or return an OK/skipped result.
2. Reviewer checks for risks, missing tests, and obvious regressions.
3. Reviewer issues route back to Builder or block the workflow.

## Verification

The Verifier runs the commands listed for the unit and writes `verification.json`. Evidence rows connect command results back to:

- unit IDs;
- test case IDs;
- acceptance criteria;
- acceptance obligations;
- journeys;
- artifact references.

Malformed evidence is treated as verification failure.

For required UI/Web prototype surfaces, verifier evidence must also include `visual_evidence_refs`. Prototype conformance commands emit `PROTOTYPE_SCREENSHOT`, `PRODUCTION_SCREENSHOT`, optional `INTERACTION_SCREENSHOT`, and `VISUAL_EVIDENCE` markers so Final Acceptance can compare the approved prototype with the production UI instead of accepting route/text assertions alone.

Repeated verifier failures use a stable fingerprint based on stage, issue type, command, return code, and stable failure features such as Playwright test titles or error classes. Volatile stdout/stderr tails remain visible in summaries and artifacts, but they do not by themselves make the same failure look new.

## Final Acceptance

Final Acceptance presents:

- target and objective coverage;
- evidence matrix;
- prototype conformance and visual prototype evidence when required UI/Web surfaces exist;
- Journey matrix;
- scope audit;
- changed files;
- rejection routing.

When a live tmux agent pane is configured, approval first triggers an Agent Status Sync step. That prompt tells the agent final acceptance has been approved and asks it to update status documents such as `task_plan.md`, `progress.md`, and `findings.md` before release.

The workflow reaches `DONE` only after final acceptance is approved and any required status sync has completed.

## Rejection Routing

A final acceptance rejection should choose the narrowest correct route:

| Route | Use when |
| --- | --- |
| `requirements` | The accepted requirements are wrong or incomplete. |
| `unit_plan` | The plan misses coverage, sequencing, test cases, or Journey mapping. |
| `implementation` | The unit plan is valid, but implementation is incomplete or wrong. |
| `defect_fix` | A bug exists within approved scope and needs a focused fix. |
| `blocked` | The workflow cannot continue without external input. |

## Human Responsibilities

Waygate does not remove human judgment. It concentrates human review at the points where it matters:

- confirm that requirements match intent;
- confirm that unit plans have enough evidence coverage;
- confirm that final evidence is credible;
- route failures honestly.

## Artifacts to Inspect

| Artifact | Why it matters |
| --- | --- |
| `approvals/requirements-and-acceptance.md` | Approved requirements and acceptance criteria. |
| `approvals/unit-plan.md` | Approved unit breakdown and test matrix. |
| `artifacts/*/prompt.md` | Exact agent task prompt. |
| `artifacts/*/done.json` | Agent completion signal with run ID. |
| `artifacts/*/verification.json` | Verifier evidence and command results. |
| `approvals/final-acceptance.md` | Final approval gate and evidence matrix. |
