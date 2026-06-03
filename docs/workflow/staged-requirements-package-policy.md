# Staged Requirements Package Policy

This document records the V0.6.2 workflow policy for Staged Requirements Package, including V0.6.2d unit continuity handoff hardening, the V0.6.2e requirements package directory intake extension, the V0.6.2f human review control handoff, and the V0.6.2g Product Design prompt contract. It reduces Requirements-stage overload by splitting the old single draft into focused checkpoints, while preserving one final human Requirements approval gate.

Current annotation note: annotation uses subprocess only. `WAYGATE_ANNOTATION_TMUX` is a deprecated no-op and does not create annotation panes. Persisted audit data remains env key-only.

`.rrc-controller-*` directories remain run audit evidence. Long-lived policy lives here and is registered from `docs/README.md`.

## Scope

V0.6.2 applies the staged flow to new V0.6.2 Requirements packages and compatible future targets that explicitly enable the package mode. Existing approved Requirements gates and legacy sessions already waiting at `WAITING_REQUIREMENTS_ACCEPTANCE` are not forced to migrate.

The staged package contains four checkpoint artifacts:

| Stage | Artifact Purpose |
| --- | --- |
| 需求范围检查点 (Requirements Scope Checkpoint) | Current-version goals, non-goals, users, target-product journeys, visible product surfaces, ACs, AO traceability, minimal context, risks, and later-version candidates. |
| 产品设计简报 (Product Design Brief) | Target product UX, prototype or review evidence, page/state/entrypoint review method, and product behavior implied by the approved scope. |
| 技术架构简报 (Technical Architecture Brief) | Target system interaction architecture, module boundaries, APIs, data flow, state write/readback behavior, runtime dependencies, and external integrations. |
| 需求测试策略简报 (Requirements Test Strategy Brief) | Strategy-level test layers, E2E review method when required, command intent, mock policy, risks, and verifier evidence shapes that Unit Plan must later turn into exact test cases and commands. |

Scope must stay focused. It must not ask the drafter to produce the complete product design, architecture, test strategy, or full `## 4.9 目标项目基础设施信息` inventory in the same checkpoint.

## No-Spec Scope Clarification

Staged Requirements inherit the legacy no-`--spec` first-turn clarification rule. When a target uses staged Requirements, has no supported `requirementsSpec`, has no `requirementsRevisionFeedback`, and the 需求范围检查点 artifact is not complete yet, the first Scope runner must ask the human one clarification question in the tmux agent pane before writing `artifacts/requirements-scope/requirements-scope.md`.

That question must confirm the current-version goal, explicit non-goals, acceptance focus, and the fact sources or documentation entry points to use. The agent must wait for the human answer, then read the project facts and write the Scope artifact. It must not immediately read project context and draft an artifact before the answer.

`--auto-approve` does not skip this clarification. It only affects later approval behavior after the required human clarification and checkpoint generation path have produced reviewable artifacts. If a supported spec exists, revision feedback already exists, or the Scope artifact is already complete, this first-turn clarification rule does not trigger for later checkpoint runs.

## Target Surface Classification

V0.6.2a adds `requirementsSurfaceClassification` to prevent staged checkpoints from designing Waygate/controller itself when Waygate is driving a target product. The classification is derived from `--spec`, target context, unit metadata, and human revision feedback. It records:

- `product_ui`: `required`, `not_required`, or `unknown`;
- `web_system`: `required`, `not_required`, or `unknown`;
- `prototype_required`: `required`, `not_required`, or `unknown`;
- `visible_surfaces`: detected entries such as product entrypoints, pages, dashboards, status review surfaces, detail pages, API/CLI review outputs, or consoles;
- `evidence_snippets`: short redacted snippets showing why the classification was made.

Default controller flags such as `currentUnitNeedsUiDesign=false` and `currentUnitIsWebSystem=false` are not evidence that the target product has no UI. They can only be recorded as ignored context. A `not_required` classification must cite an explicit backend/API/CLI-only basis.

If `product_ui`, `web_system`, or `prototype_required` is `required`, Requirements preflight still requires a valid prototype manifest when the target UI/Web/prototype contract is active. If the classification is `unknown`, the 需求范围检查点 or 产品设计简报 must explain the uncertainty or route back for clarification; it must not silently write “no UI”.

When `prototype_required=required` or `web_system=required`, the 产品设计简报 prompt must require `artifacts/requirements-draft/prototype-manifest.json` and include the canonical top-level `{"prototypes": [...]}` schema skeleton. Local prototype paths are resolved relative to the manifest directory, so agents must generate or copy HTML/image/Markdown prototypes into `artifacts/requirements-draft/` and then reference an artifact-local path such as `prototypes/<prototype-id>/index.html`. Workspace-relative paths such as `docs/prototypes/...` are invalid unless the same file exists under `artifacts/requirements-draft/docs/prototypes/...`. Stage completion validates that the manifest exists and contains a clickable prototype access method, page states, click path, AC/Journey mapping, implementation targets, and surface contracts under `prototypes[]`. Manifest AC/Journey references and surface-contract AC references must already exist in 需求范围检查点; 产品设计简报 cannot invent new AC or Journey IDs. Flat top-level prototype keys such as `clickable_prototype_access_method`, `page_states`, or `click_path` are invalid as the final manifest shape. Missing or malformed manifest output is a 产品设计简报 stage problem and must be surfaced there, not deferred to the final Requirements preflight loop.

The final Requirements preflight accepts a manifest that passes `validate_prototype_review_manifest(..., require_clickable=True)` as clickable webpage prototype evidence. Product Design text can also satisfy the textual evidence check when it names an artifact-local clickable HTML path or URL, manifest path, page states, click path, and AC/Journey mapping. The manifest remains mandatory for active UI/Web/prototype contracts: missing files, missing page states, missing click path, missing AC mapping, unsupported prototype kind, or invalid surface contracts still block approval.

## Product Design Prompt Contract

V0.6.2g makes the Product Design checkpoint branch explicit instead of relying on historical prompt wording:

- No supported `requirementsSpec`: the Product Design prompt must require the `brainstorming` skill in the same tmux conversation, confirm one page, surface, or entrypoint at a time with the human, and write `product-design-brief.md` plus the required prototype manifest only after those confirmations.
- Supported `requirementsSpec`: the prompt stays on the compatibility path, preserving the staged artifact flow and not adding mandatory page-by-page brainstorming gates.
- Backend/API/CLI-only scope: the prompt asks once for explicit no-UI/no-prototype confirmation, cites positive Scope basis, and does not infer no-UI from default false controller flags.

This is a prompt contract, not a new deterministic transcript blocker. V0.6.2g does not add per-page controller gates, and it does not turn artifact-local prototype review into production browser route evidence. The subprocess-only annotation runtime, deprecated no-op `WAYGATE_ANNOTATION_TMUX`, supported `opencode` / `codex` annotation backends, and env key-only audit terms are handled by the annotation policy while Product Design remains focused on target-product review evidence.

V0.6.2b promotes the prototype review bundle from a temporary Plannotator helper to a controller process-level preview service. After 产品设计简报 validation succeeds, the controller generates `plannotator-review.html` and `prototype-review-manifest.json`, starts the preview server, and prints the prototype preview URL. Before final Requirements assembly exists, the bundle uses the 需求范围检查点 as the requirements reference. Final assembly regenerates the bundle with the real `approvals/requirements-and-acceptance.md` approval gate metadata, while the already-started preview server keeps the same port. Requirements Plannotator review reuses that server, Plannotator Close does not shut it down, and the controller closes it only when the process exits.

Preview port selection starts at `WAYGATE_PREVIEW_PORT` when set, otherwise `20001`. If the selected port is occupied, the controller increments until it finds a free port. The printed browser URL uses the display host from the existing preview host rules. When proxy environment variables are present, the controller may remind the operator to add that display host to `NO_PROXY/no_proxy` so local preview requests do not go through a proxy.

Every checkpoint now runs deterministic stage-output validation immediately after the artifact is produced:

- Scope rejects real E2E/browser review text unless it maps to `AC-... [verification: e2e]` or a Journey row with exact `Status=active` and `Verification Layer=e2e`. Values such as `是` or `real integration + DB assertion` are not canonical. Prototype-only artifact review is handled by Product Design manifest and Unit Plan prototype conformance, not by 4.6 real E2E command validation.
- Product Design rejects unknown AC/Journey references in its artifact and prototype manifest.
- Technical Architecture rejects unknown AC/Journey references and, when Scope declares E2E/browser handoff, must cite the Scope canonical e2e AC/Journey instead of only describing a natural-language strategy.
- Requirements Test Strategy rejects noncanonical E2E sections. If Scope or Test Strategy declares E2E/browser review, it must write fixed heading `## 4.6 E2E 测试方法与前置依赖矩阵（E2E Test Method & Prerequisite Matrix）`, use the fixed 11 columns, and cover every active e2e Journey plus any e2e AC not already covered by a mapped Journey row. `Environment Kind` is limited to `local_real` or `production_readonly`; `Real Entrypoint`, `User Steps`, and `Fixture / Test Data / Setup` must be concrete; core business API mocks/stubs are not allowed; expected assertions must be machine-checkable and screenshots cannot be the only assertion. `Verification Command` is a command intent, command family, or runner intent; exact commands belong in Unit Plan.

The 4.6 validator consumes only the canonical fixed-column E2E matrix block. A non-table line or a new noncanonical markdown table header resets the active 4.6 header, so later subsection tables such as `### 4.7 Scope AC Verification Layer Closure` are not inherited as 4.6 rows. Real rows inside the canonical 4.6 table remain strict; missing columns, placeholder command intent, fake entrypoints, vague steps, weak fixture/setup, mock core APIs, or weak assertions still block approval.

AC verification-layer facts are only read from canonical AC/layer tables, direct inline AC markers such as `AC-... [verification: e2e]`, or clear non-table layer buckets. Explanatory surface, coverage, or support tables may reference E2E ACs and integration/prerequisite ACs in the same note, but those references do not promote every referenced AC to E2E.

Source-provenance content is not a current-version AC obligation. This includes source map prose, conversion artifact notes, mapping text such as `AC-SPEC-001 -> AC-V10-001`, range notes such as `AC-SPEC-001 至 AC-SPEC-012`, wildcard examples such as `AC-SPEC-*`, and table columns such as `Source AC`, `Source AC / TC`, `Imported AC`, or `Original AC`. Those labels are ignored for missing-layer, current AC coverage, unknown-current-AC, and E2E obligation checks unless the same ID is declared in a canonical current AC column or AC line with an explicit verification layer. A supported external ID such as `AC-SPEC-001 [verification: integration]` still becomes a current AC when it is deliberately adopted in the canonical Acceptance Criteria section. AC and Journey ID parsing also rejects trailing-hyphen fragments such as `AC-V10-` so wildcard examples cannot become partial active IDs.

Requirements-stage AC layers include the behavioral layers `unit`, `functional`, `integration`, `e2e`, and `manual`, plus non-E2E support layers `static`, `regression`, and `prerequisite`. These support layers satisfy the Requirements obligation to classify the AC, but they do not trigger real E2E 4.6 strictness; Unit Plan still owns the exact executable command, test case, fixture initialization, and final evidence row.

Journey Acceptance Matrix parsing follows the same boundary. The preferred minimal header is `| Journey | Title | Status | Steps | AC | Verification Layer |`. The parser accepts rows without a `Title` column by using the Journey ID as the title, and it accepts equivalent headers such as `Journey id`, `User steps`, `Acceptance contract`, `Path / assertion focus`, and `Linked AC`. When an assembled final gate contains multiple compatible Journey-like tables for the same Journey ID, the parser merges them into one contract row and keeps the richest steps, AC, Unit, Test Case, and command data; conflicting status or verification layer values still block approval. A Journey-local marker such as `J-... [verification: manual]` applies only to that Journey reference and must not be spread to an AC mentioned later in the same prose line. `static`, `regression`, and `prerequisite` are valid non-E2E Journey layers for support/baseline/prerequisite journeys; only normalized `e2e` Journey rows trigger 4.6 real E2E coverage requirements.

Stage validation failures keep the workflow at the current checkpoint step and write a stage validation artifact. Before Requirements are human-approved, tmux-backed runners may automatically rework the failed checkpoint: the controller invalidates the failed stage and downstream artifacts, injects `Controller stage validation feedback` into `requirementsRevisionFeedback`, records `requirements_stage_auto_revision_requested`, and reruns the same stage action. The retry budget uses the same process-local consecutive semantic reason counter and `requirementsAutoRevisionMax` as Requirements auto-revision. Once that budget is exceeded, or when Requirements are already approved, the workflow hard-blocks with `requirements_stage_validation` guidance. The manual recovery remains `waygate unblock` for rerunning the same checkpoint, or `waygate revise --gate requirements --reason ...` when the error exposes an upstream AC, Journey, or Requirements contract conflict.

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
- `## 附录 A：需求范围检查点 (Requirements Scope Checkpoint)`
- `## 附录 B：产品设计简报 (Product Design Brief)`
- `## 附录 C：技术架构简报 (Technical Architecture Brief)`
- `## 附录 D：需求测试策略简报 (Requirements Test Strategy Brief)`

The hash table binds the approval file to the checkpoint artifacts and shows both the Chinese public checkpoint name and the stable English stage key. Missing appendices, missing hash rows, or hash mismatches are controller validation failures.

## Human Review Control Handoff

V0.6.2f keeps the staged Requirements approval contract unchanged while adding review-control evidence around it. The only contract truth remains the approved gate body plus valid approval hash. Plannotator `decision=approved` payload fields such as `annotations`, `feedback`, and `reason` are saved as approval notes and rendered later only as `Approval Notes Non-Contract Context`; they do not create Acceptance Obligations, scope changes, Journey rows, test cases, or approved body edits.

The Requirements and Unit Plan human gate menu includes `i` and `m` in addition to the legacy `a`, `r`, `v`, `p`, and `q` actions. `i` asks the controller to prepare a revised draft from approval notes or review feedback and keeps the gate pending. `m` adopts a human-edited body only when the current body hash differs from the pending review baseline, a human reason or saved approval notes exist, and the existing deterministic validator passes. Rejected `m` attempts keep the gate pending and record structured rejection reasons.

Ctrl+C during automatic execution is not treated as a Requirements change. The controller records `status=blocked`, `blockedContext.category=human_interrupt`, the interrupted step/action, and the best-effort tmux `C-c` result, then shows recovery routes. Operators may choose a normal recovery route such as continue/unblock, Unit Plan revise, Requirements revise, keep blocked, or quit according to the blocked guidance.

CLI routes follow the same policy. `waygate approve --gate requirements --reason ...` and `waygate approve --gate unit-plan --reason ...` use the guarded manual-adoption path. `waygate revise` without a reason returns to the current approval point without staling staged checkpoints or regenerating artifacts. `waygate revise --gate requirements --checkpoint ...` still requires `--reason`, because checkpoint rollback changes staged package state.

The detailed V0.6.2f review-control policy lives in `docs/workflow/human-review-control-policy.md`.

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

The 需求测试策略简报 (`Requirements Test Strategy Brief`) carries E2E method review before Unit Plan. The Unit Plan inherits that review and turns it into executable test cases, exact verification commands, fixtures, mock policy, and expected assertions.

The Test Strategy checkpoint remains strategy-level. It should describe risk, verification layers, evidence shapes, and handoff expectations, while exact test cases, concrete commands, fixture scripts, and final assertions are owned by Unit Plan.

The final Requirements gate still runs the full `validate_requirements_acceptance_quality()` chain after assembly. The stage checks are earlier deterministic blockers, not a replacement for final preflight.

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

V0.6.2d adds a hard Unit Continuity Gate for multi-unit plans. Any unit that declares `depends_on`, or participates in handoff metadata, must declare structured `handoff` data in Controller State Patch: `human_summary`, `produces`, `requires`, `ready_checks`, and `evidence_artifacts`. The Unit Plan body must include `## 单元连贯性摘要` and `## Handoff Matrix` so human reviewers can see upstream unit, downstream unit, produced artifacts/readiness, consumed inputs, evidence path, and failure route. The validator rejects vague summaries such as `environment ready`, missing dependencies, circular dependencies, unmatched `requires[]`, dependencies that contribute no required input, and ready checks that do not map to commands or test cases. When a downstream unit depends on multiple upstream units, different dependencies may satisfy different `requires[]` entries.

Producer unit verification writes `artifacts/<unit-id>/handoff-evidence.json`. Missing declared evidence artifacts or failed ready checks make producer verification fail. Before Builder starts a downstream unit, the controller checks every dependency's handoff evidence and blocks with `blockedContext.category=unit_handoff` when the upstream evidence is missing, invalid, failed, or does not produce the downstream required input. The detailed policy lives in `docs/workflow/unit-continuity-handoff-policy.md`.

Unit Plan has no staged checkpoint sequence. Its deterministic gate is the same validator chain in draft preflight and approval revalidation: state patch, test strategy, test case coverage, AO/AC traceability, prototype conformance, document deliverables, infrastructure matrix, verification environment, verification-assist contract, evidence-row preflight, final evidence candidates, golden path, real E2E policy, Journey enrichment, and final walkthrough. A draft that fails this chain must not run annotation or enter human approval, and a human-approved gate is revalidated through the same helper before state advances.

## Revision And Downstream Invalidation

Human revision or controller preflight failure uses downstream invalidation: only the affected stage and downstream stages become stale.

| Revision Source | Stale Stages |
| --- | --- |
| Scope | Scope, Product Design, Technical Architecture, Test Strategy, Final Gate |
| Product Design | Product Design, Technical Architecture, Test Strategy, Final Gate |
| Technical Architecture | Technical Architecture, Test Strategy, Final Gate |
| Test Strategy | Test Strategy, Final Gate |
| Final Gate assembly | Final Gate |

`waygate revise --gate requirements` in staged package mode clears Requirements and Unit Plan approval state, preserves revision feedback, and routes to the affected checkpoint through semantic issue classification. Operators can also target the checkpoint directly:

```bash
waygate revise --gate requirements --checkpoint product-design --reason "补产品原型和页面状态"
```

`--checkpoint` accepts `scope`, `product-design`, `architecture`, `test-strategy`, and Chinese aliases such as `需求范围`, `产品设计`, `技术架构`, and `测试策略`. It only applies to `--gate requirements`; Unit Plan revision keeps the existing `waygate revise --gate unit-plan --reason ...` behavior. If no checkpoint is supplied, `--reason` is semantically routed as before. In non-interactive shells, Requirements revise must provide a reason or explicit checkpoint so the rollback is auditable.

Surface/prototype/UI feedback such as “产品原型呢”, a missing prototype manifest, missing page states, missing click path, or missing prototype access method routes to 产品设计简报. Interaction architecture, API, data-flow, state-write/readback, module-boundary, runtime, or external-system feedback routes to 技术架构简报. Test-method quality feedback such as mock policy, `environment_kind`, E2E method, fixture/setup, verification layer, 4.6 matrix shape, or expected assertions routes to 需求测试策略简报. Broader scope, current-version boundary, visible-surface classification, unknown AC/Journey references, AO traceability, or unclear feedback routes to 需求范围检查点.

Controller preflight reasons that include missing AO requirements mapping, missing AO coverage, a required Journey contract with no active Journey rows, E2E review not mapped to an active E2E AC/Journey, unknown acceptance criteria, unknown Journey references, conflicting AC verification layers, conflicting Journey status, or inconsistent `requirementsSurfaceClassification` are Scope blockers. They route to `REQUIREMENTS_SCOPE_DRAFT` even if the same combined reason also mentions prototype manifest, Web, page states, or UI evidence. Pure prototype access or “how do I review the UI” feedback still routes to Product Design. For controller-validation-only auto-rework, routing uses the controller validation error as the primary source instead of the full old Requirements gate body; the event `requirements_staged_revision_routed` records `reason_key`, `routing_source`, and `routing_reason` for audit.

Requirements auto-revision uses the same semantic issue key for its retry budget, but the budget is process-local to one `waygate go`. The controller keeps the last reason key, consecutive attempt count, and total requested attempts in the active `RalphRefinerController` instance only. It does not read or write `requirementsAutoRevisionLastReasonKey`, `requirementsAutoRevisionConsecutiveCount`, or `requirementsAutoRevisionTotalCount` in `session.json`; later state saves remove those legacy fields if an older session contains them. Events still record `attempt` and `total_attempt` for audit history, but event history and legacy session fields do not control a later run. A process exit, explicit human Requirements revise, or next `waygate go` starts with a fresh budget. Within one controller process, when an unapproved final Requirements preflight reason exceeds `requirementsAutoRevisionMax`, the workflow hard-blocks with `blockedContext.category=requirements_contract`; recovery is `waygate revise --gate requirements --reason "..."`, not `retry` or ordinary `unblock`.

For staged checkpoint validation blockers, `waygate unblock` preserves the controller stage-validation reason into `requirementsRevisionFeedback` before clearing the blocker. Auto-rework uses the same feedback format before a hard block is reached. The next checkpoint prompt therefore sees the exact validator failure instead of regenerating the same artifact from ordinary upstream context alone.

For non-Waygate target projects, Product Design and Technical Architecture are invalid if they primarily describe Waygate/controller staged package operation, controller orchestration, runner contracts, checkpoint state transitions, or artifact hash flows instead of target product UX and target system architecture.

## Version Boundary

V0.6.2 delivers Staged Requirements Package. The original Strict Test Presence / TC1-TC7 scope is not part of V0.6.2 implementation. It is carried forward into V0.6.3 Strict Test Presence and Per-Role Runner Configuration.

V0.6.2f adds approval notes, guarded manual adoption, human interruption recovery, and review-surface conformance evidence for the Waygate review control surface. It does not implement V0.6.3 Strict Test Presence, Test Case Contract v1, or Per-Role Runner Configuration.

V0.6.2g adds Product Design prompt branch behavior. Annotation remains subprocess-only; the removed annotation tmux runtime does not change annotation approval authority, and ordinary `tmux-claude` / `tmux-codex` workflow runners remain available.

V0.6.2 also does not add unrelated UI/prototype artifacts, Debian package installation behavior, or role runner configuration changes unless a later unit explicitly requests them.

## Verification

The acceptance evidence for this policy is:

- docs registry and roadmap assertions for AC-15;
- focused staged package, human gate, validator, and annotation suites for AC-16;
- full `python3 -m pytest workflow_controller/tests -q`;
- `git diff --check`.
