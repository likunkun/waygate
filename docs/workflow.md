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
- assumptions and risks.

Before a human sees the gate, the controller can preflight it. Missing AC mapping, missing verification layers, and malformed traceability can route the draft back to the drafter automatically.

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

## Implementation Stage

The Builder receives a prompt file and works on one unit. A tmux or subprocess runner dispatches the prompt and waits for a completion signal.

The completion signal is not final proof. The controller still checks the run ID, artifacts, and later verifier evidence.

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

## Final Acceptance

Final Acceptance presents:

- target and objective coverage;
- evidence matrix;
- Journey matrix;
- scope audit;
- changed files;
- rejection routing.

The workflow reaches `DONE` only after this gate is approved.

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
