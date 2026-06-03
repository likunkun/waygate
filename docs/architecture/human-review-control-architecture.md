# Human Review Control Architecture

This document records the V0.6.2f module boundaries for approval notes, guarded manual adoption, Ctrl+C human interruption recovery, CLI route split, and review-bundle conformance evidence.

## Module Boundaries

| Area | Modules | Responsibility |
| --- | --- | --- |
| Approval notes | `workflow_controller/approval_notes.py` | Normalize Plannotator approved payload notes, write safe note artifacts, and render `Approval Notes Non-Contract Context`. |
| Controller gate orchestration | `workflow_controller/rrc_controller.py` | Own `approve_human_gate()`, human gate menu actions `i` and `m`, pending review baselines, draft merge state, manual adoption guard, events, and blocked recovery. |
| Prompt handoff | `workflow_controller/prompts/unit_plan.py`, `workflow_controller/prompts/builder.py` | Inject Requirements and Unit Plan approval notes into next-stage prompts as advisory context while stating that approved body wins conflicts. |
| CLI surface | `workflow_controller/cli.py`, `workflow_controller/rrc_controller.py` module CLI | Add `approve --reason`, split `revise` no-reason return-to-approval behavior from reasoned regeneration, and reject checkpoint revise without reason. |
| Gate contract | `workflow_controller/gates/parsers/__init__.py`, `workflow_controller/gates/validators/__init__.py` | Continue parsing body hashes and running deterministic validators before any approved hash is written. Notes never bypass these helpers. |
| Human interrupt | `workflow_controller/rrc_controller.py` | Catch `KeyboardInterrupt`, record `blockedContext.category=human_interrupt`, interrupted step/action, and tmux best-effort interruption result. |
| Review surface evidence | `workflow_controller/tests/v062f_review_surface_e2e.py`, `.rrc-controller-v0.6.2f/artifacts/requirements-draft/*` | Validate review-bundle/prototype openability, surface contracts, target mapping, structural interaction, and visual evidence markers. |

## State And Artifacts

Approval notes are stored as an artifact plus a state index:

```json
{
  "gateApprovalNotes": {
    "requirements": {
      "gate": "requirements",
      "source": "plannotator_approved",
      "approved_body_hash": "sha256 body hash",
      "artifact_path": ".rrc-controller-v0.6.2f/artifacts/approval-notes/requirements-<hash>.json",
      "contract_boundary": "non-contract context"
    }
  }
}
```

The artifact may contain `annotations`, `feedback`, and `reason`. The state index must stay small and must not store secret-like values. The `approved_body_hash` ties notes to the exact approved body but does not modify the body hash.

Draft merge state records pending-only output:

```json
{
  "gateDraftMerge": {
    "requirements": {
      "status": "drafted",
      "before_hash": "<hash before draft>",
      "after_hash": "<hash after draft>",
      "draft_body_path": ".rrc-controller-v0.6.2f/artifacts/gate-draft-merge/<run>/draft-body.md"
    }
  }
}
```

Manual adoption uses `pendingGateReview.baseline_body_hash` to prove a human-edited body changed. If the baseline is missing or unchanged, adoption is rejected and the gate remains pending.

Human interruption state records a real blocked category:

```json
{
  "status": "blocked",
  "blockedContext": {
    "category": "human_interrupt",
    "source": "keyboard_interrupt",
    "interrupted_step": "EXECUTE_UNIT",
    "interrupted_action": "run_builder",
    "tmux_interrupt": {
      "attempted": true,
      "returncode": 0
    }
  }
}
```

When no tmux target exists or `tmux send-keys` fails, the recorded result reflects that actual outcome. Recovery guidance cannot assume the agent stopped unless the recorded result supports it.

## Prompt Boundary

`render_approval_notes_context()` produces a bounded prompt block for later stages. Requirements approval notes are rendered for Unit Plan drafting. Requirements and Unit Plan notes are rendered for Builder execution.

The block must include the non-contract label and the body-wins rule. Prompt renderers must not feed approval notes into AC extraction, AO extraction, Journey parsing, Unit Plan test case derivation, or verifier evidence planning as authoritative truth.

## Approval Flow

The normal `a` approval path keeps the previous behavior: read the gate body, run deterministic validation, write the approved gate file/hash, and advance state.

The `i` draft path gathers approval notes or review feedback, writes a draft artifact, may update the pending gate body, and leaves the gate at the same human approval point. It must not set `requirementsAccepted=true`, `unitPlanAccepted=true`, or any approved hash.

The `m` path and `approve --reason` share the same guard:

1. Compute the current gate body hash.
2. Compare it to `pendingGateReview.baseline_body_hash`.
3. Confirm a human reason or saved approval notes exist.
4. Run the existing deterministic gate validator.
5. Only then call the approval write path.

Rejected cases write structured state/event data such as `manualGateAdoptionRejected` and leave approval status unchanged.

## Revise Flow

`revise_human_gate(require_reason_or_checkpoint=True)` distinguishes three routes:

- no reason and no checkpoint: return to the current approval point without staling checkpoints;
- reason present: route to the existing regeneration/revision logic;
- checkpoint present without reason: reject with an explicit checkpoint-without-reason error.

This split prevents accidental checkpoint invalidation while preserving auditable staged Requirements rollback when a reason is supplied.

## Events

V0.6.2f event names include:

- `gate_approval_notes_recorded`;
- `gate_draft_merge_created`;
- `manual_adoption_approved`;
- `manual_adoption_rejected`;
- `human_interrupt_recorded`;
- `human_gate_returned_to_approval_point`.

Events should record paths, hashes, gates, counts, categories, and reasons. They should not record environment variable values, tokens, database URLs, or long raw annotation payloads.

## Review-Bundle Conformance

The V0.6.2f E2E helper validates both the review bundle and the artifact-local prototype. The required surfaces are:

- `approval-notes-context-panel`;
- `human-gate-menu-actions`;
- `draft-merge-pending-state`;
- `manual-adoption-guard`;
- `human-interrupt-recovery-panel`;
- `revise-route-output`;
- `legacy-and-docs-review`;
- `review-bundle-prototype-conformance`.

The manifest target mapping must include review-bundle, prototype, manifest, terminal-menu, CLI, state, artifact, prompt, and docs targets. Screenshots are stored as visual evidence, while the pass condition comes from machine-checked DOM, manifest, and target-marker assertions.

## Compatibility

Legacy Plannotator approved payloads without notes still approve through the normal path. Existing review actions `a`, `r`, `v`, `p`, and `q` preserve their prior state transitions and approval hash semantics. V0.6.2f adds new state keys beside existing contract fields instead of migrating or rewriting historical approved gate bodies.
