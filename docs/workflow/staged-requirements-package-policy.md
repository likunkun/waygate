# Staged Requirements Package Policy

This document records the V0.6.2 workflow policy for Staged Requirements Package. It reduces Requirements-stage overload by splitting the old single draft into focused checkpoints, while preserving one final human Requirements approval gate.

`.rrc-controller-*` directories remain run audit evidence. Long-lived policy lives here and is registered from `docs/README.md`.

## Scope

V0.6.2 applies the staged flow to new V0.6.2 Requirements packages and compatible future targets that explicitly enable the package mode. Existing approved Requirements gates and legacy sessions already waiting at `WAITING_REQUIREMENTS_ACCEPTANCE` are not forced to migrate.

The staged package contains four checkpoint artifacts:

| Stage | Artifact Purpose |
| --- | --- |
| Requirements Scope | Scope, non-goals, users or operators, journeys, ACs, AO traceability, minimal context, and risks. |
| Product Design Brief | User experience, review surface, human gate experience, and product behavior implied by the approved scope. |
| Technical Architecture Brief | Module boundaries, controller state, runner flow, gate assembly, validator behavior, and compatibility notes. |
| Requirements Test Strategy Brief | Test layers, focused suites, E2E review method when required, mock policy, and verifier evidence expectations. |

Scope must stay focused. It must not ask the drafter to produce the complete product design, architecture, test strategy, or full `## 4.9 目标项目基础设施信息` inventory in the same checkpoint.

## Checkpoint Contract

Every checkpoint writes a Markdown artifact and records metadata in `requirementsPackage.artifacts.<stage>`:

- `stage`
- `path`
- `hash`
- `status`

Downstream checkpoint prompts must read upstream artifact path/hash data instead of relying on recent conversation context. Product Design, Technical Architecture, and Requirements Test Strategy prompts must include the relevant upstream artifact path and hash so the next agent has a stable fact source.

The final package is assembled only after the four checkpoint artifacts are complete and their hashes still match the recorded state.

## Final Human Gate

V0.6.2 still presents one final human Requirements approval gate at `approvals/requirements-and-acceptance.md`.

The final gate must include:

- `## 审批摘要`
- `## Artifact Hashes`
- `## 附录 A：Requirements Scope Checkpoint`
- `## 附录 B：Product Design Brief`
- `## 附录 C：Technical Architecture Brief`
- `## 附录 D：Requirements Test Strategy Brief`

The hash table binds the approval file to the checkpoint artifacts. Missing appendices, missing hash rows, or hash mismatches are controller validation failures.

## Gate Ordering

Staged Requirements preserve the V0.6.1 human gate order:

1. Generate or reuse checkpoint artifacts.
2. Assemble the final Requirements gate.
3. Run deterministic controller preflight.
4. Run `requirements_annotation` when enabled.
5. Present the human Requirements approval gate.

Annotation remains non-approval review context. It cannot approve, skip, modify, or bypass a gate. Already approved legacy gates do not run retroactive annotation just because they lack a fresh staged package artifact.

## Infrastructure Responsibility

V0.6.2 moves detailed `## 4.9 目标项目基础设施信息` responsibility out of the final Requirements gate and into the Unit Plan `Infrastructure / Execution Context Matrix`.

The Requirements stage still carries enough context to decide scope, ACs, journeys, UI/E2E obligations, risk, and whether real E2E review is needed. The Unit Plan must then expand execution context into these seven categories:

- code repository
- runtime and deployment environment
- debugging and analysis methods
- reference environment
- documentation locations
- architecture, interaction logic, and interface notes
- dependency information

The `Requirements Test Strategy Brief` carries E2E method review before Unit Plan. The Unit Plan inherits that review and turns it into executable test cases, verification commands, fixtures, mock policy, and expected assertions.

## Unit Plan Handoff

When `requirementsPackage.version` is `v0.6.2-staged`, the Unit Plan prompt must list scope, product_design, architecture, and test_strategy artifact path/hash/status records. The prompt must require the Unit Plan to inherit:

- ACs and Journey coverage
- AO traceability
- Product Design obligations
- Technical Architecture obligations
- Requirements Test Strategy and E2E method
- UI/prototype obligations only when the upstream package explicitly declares them
- risk obligations and residual assumptions
- Infrastructure / Execution Context Matrix facts

Natural-language summaries are not sufficient as the handoff contract. The artifact path/hash/status records are the traceable source.

## Revision And Downstream Invalidation

Human revision or controller preflight failure uses downstream invalidation: only the affected stage and downstream stages become stale.

| Revision Source | Stale Stages |
| --- | --- |
| Scope | Scope, Product Design, Technical Architecture, Test Strategy, Final Gate |
| Product Design | Product Design, Technical Architecture, Test Strategy, Final Gate |
| Technical Architecture | Technical Architecture, Test Strategy, Final Gate |
| Test Strategy | Test Strategy, Final Gate |
| Final Gate assembly | Final Gate |

`waygate revise --gate requirements` in staged package mode rewinds to `REQUIREMENTS_SCOPE_DRAFT`, clears Requirements and Unit Plan approval state, preserves the revision feedback, and lets the controller regenerate only the necessary chain.

## Version Boundary

V0.6.2 delivers Staged Requirements Package. The original Strict Test Presence / TC1-TC7 scope is not part of V0.6.2 implementation. It is carried forward into V0.6.3 Strict Test Presence and Per-Role Runner Configuration.

V0.6.2 also does not add UI/prototype artifacts, Debian package installation, or role runner configuration changes unless a later unit explicitly requests them.

## Verification

The acceptance evidence for this policy is:

- docs registry and roadmap assertions for AC-15;
- focused staged package, human gate, validator, and annotation suites for AC-16;
- full `python3 -m pytest workflow_controller/tests -q`;
- `git diff --check`.
