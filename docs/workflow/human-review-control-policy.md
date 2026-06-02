# Human Review Control Policy

This document records the V0.6.2f workflow policy for Waygate human review control. It is the long-lived policy counterpart to the V0.6.2f controller artifacts under `.rrc-controller-v0.6.2f/`.

## Scope

V0.6.2f covers Requirements and Unit Plan human gates, Plannotator approved payloads, terminal review menu actions, Ctrl+C recovery, and the review-bundle/prototype conformance surface for those controls.

The release does not change approved Requirements, acceptance criteria, Journey IDs, AO IDs, or Unit Plan test case contracts. It does not implement V0.6.3 Strict Test Presence, Test Case Contract v1, or Per-Role Runner Configuration.

## Contract Boundary

The contract truth for Requirements and Unit Plan remains the approved gate body plus the corresponding approval hash. Approval notes, Plannotator `annotations`, `feedback`, `reason`, AO-001 clarification text, review-bundle explanations, and screenshots are advisory context unless a human edits the gate body and the guarded approval path accepts that edited body.

When notes conflict with the approved body, the approved gate body wins. Notes are `non-contract context` and must not automatically create Acceptance Obligations, scope changes, Journey rows, test cases, verification commands, document deliverables, or final evidence rows.

## Approval Notes

When Plannotator returns `decision=approved` with `annotations`, `feedback`, or `reason`, Waygate stores those fields as approval audit context. The controller writes a gate-scoped artifact under `artifacts/approval-notes/` and records a lightweight `gateApprovalNotes.<gate>` index in `session.json` with the approved body hash and artifact path.

Next-stage prompts may render those notes only under `Approval Notes Non-Contract Context`. The context exists to help later agents understand reviewer concerns. It is not a source of AC, Journey, AO, or test case truth.

AO-001 is treated as a clarification boundary: the risk warning about notes and manual adoption explains existing V0.6.2f controls. It is not a new scope item and does not add acceptance criteria or Journey contracts.

## Human Gate Menu

Requirements and Unit Plan review menus keep the existing actions:

- `a`: approve the current gate body through the normal validator and approval hash path.
- `r`: regenerate or revise from human feedback.
- `v` / `p`: open or preview review surfaces when available.
- `q`: leave the gate pending.

V0.6.2f adds:

- `i`: prepare a draft body from approval notes or review feedback. The gate remains pending, and no approved hash is written.
- `m`: adopt the human-edited current body and continue only after all manual-adoption checks pass.

The `i` action is a drafting aid. It may write a draft artifact and update pending gate text, but it must not approve the gate or imply that notes became contract truth.

The `m` action is a controlled adoption path. It requires:

- the current body hash differs from the pending review baseline;
- a human reason or saved approval notes exist;
- the existing deterministic gate validator passes.

If any condition fails, the controller keeps the gate pending and records a structured rejection reason.

## CLI Routes

`waygate approve --reason` is the shorthand policy name for approve-with-reason manual adoption. `waygate approve --gate requirements --reason ...` and `waygate approve --gate unit-plan --reason ...` use the same guarded manual-adoption path as menu action `m`.

`waygate revise` without a reason returns to the existing approval point. It does not stale staged Requirements checkpoints and does not regenerate Requirements or Unit Plan artifacts.

`waygate revise --gate requirements --checkpoint ...` changes staged package routing and therefore requires `--reason`. Checkpoint revise without a reason is rejected.

## Human Interrupt

Ctrl+C during automatic execution is converted to an auditable blocked state:

- `status=blocked`;
- `blockedContext.category=human_interrupt`;
- interrupted step and action are recorded;
- tmux `send-keys C-c` is attempted when a target pane is known, and the actual result is recorded.

The recovery menu exposes normal controller routes such as continue/unblock, Unit Plan revise, Requirements revise, keep blocked, or quit. A human interrupt is not automatically a Requirements change and does not silently approve or reject any gate.

## Review Surface Evidence

The V0.6.2f review bundle and prototype surface must map review states to real Waygate targets:

- approval notes advisory context;
- AO-001 clarification;
- `i` draft merge pending state;
- `m` manual adoption guard;
- Ctrl+C `human_interrupt` recovery;
- revise route split;
- legacy review compatibility;
- review-bundle/prototype conformance.

Prototype-only screenshots are review aids, not sole acceptance evidence. AC-V062F-009 requires machine-checked conformance against real review bundle files, prototype manifest data, terminal menu targets, CLI route targets, state fields, artifacts, prompts, docs, and visual evidence markers.

## Compatibility

Existing approved gates and legacy Plannotator payloads without notes remain valid. Existing `a`, `r`, `v`, `p`, and `q` review actions keep their prior state transitions, approval hash semantics, preview behavior, and revision feedback routing.

Artifacts and events must not record token values, database URLs, proxy values, or other secret-like data.
