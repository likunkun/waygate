# Staged Requirements Package Architecture

This document records the V0.6.2 architecture boundaries for Staged Requirements Package, including the V0.6.2a target-product perspective patch, V0.6.2b persistent prototype preview patch, V0.6.2c Chinese checkpoint / targeted revise patch, V0.6.2d unit continuity handoff gate, V0.6.2e package-directory intake extension, V0.6.2f human review control handoff, and V0.6.2g Product Design prompt branching. It covers package helpers, target surface classification, checkpoint prompts, stage runner, controller orchestration, controller process-level prototype preview, final gate assembly, validators, Unit Plan prompt inheritance, unit handoff evidence, review-control prompt handoff, and revision routing.

Current annotation note: annotation uses subprocess only. `WAYGATE_ANNOTATION_TMUX` is a deprecated no-op and does not create annotation panes. Persisted audit data remains env key-only.

## Module Boundaries

| Area | Modules | Responsibility |
| --- | --- | --- |
| Package metadata | `workflow_controller/requirements_package.py` | Defines `REQUIREMENTS_PACKAGE_VERSION`, stage ordering, action maps, artifact filenames, hash helpers, artifact completeness checks, and downstream invalidation. |
| Target surface classification | `workflow_controller/requirements_surface.py` | Classifies target product surfaces from `--spec`, target context, current unit metadata, and human feedback into `product_ui`, `web_system`, `prototype_required`, `visible_surfaces`, and redacted evidence snippets. |
| Revision issue routing | `workflow_controller/requirements_revision_routing.py` | Classifies Requirements revision feedback into semantic issue codes, selects the staged checkpoint by upstream priority, and produces stable auto-revision semantic keys. |
| Prompt rendering | `workflow_controller/prompts/requirements_package.py` | Renders 需求范围检查点 (Requirements Scope Checkpoint), 产品设计简报 (Product Design Brief), 技术架构简报 (Technical Architecture Brief), and 需求测试策略简报 (Requirements Test Strategy Brief) prompts with upstream artifact path/hash inputs. |
| Stage execution | `workflow_controller/steps/requirements_package.py` | Runs one checkpoint, writes the prompt, calls the shared stage-output validator, writes summary JSON, and updates `requirementsPackage.artifacts`. |
| State routing | `workflow_controller/state_machine/actions.py` | Maps staged Requirements steps to `run_requirements_scope_drafter`, `run_requirements_product_design_brief`, `run_requirements_architecture_brief`, `run_requirements_test_strategy_brief`, and `assemble_requirements_package`. |
| Controller orchestration | `workflow_controller/rrc_controller.py` | Advances one checkpoint per `run_once()`, records `requirements_package_stage_generated`, auto-reworks unapproved stage-validation failures when allowed, records stage-validation blockers, assembles the final gate, runs preflight, preserves annotation ordering, and owns the process-level prototype preview server lifecycle. |
| Prototype preview | `workflow_controller/prototype_review.py`, `workflow_controller/rrc_controller.py` | Normalizes the Product Design prototype manifest into `plannotator-review.html` / `prototype-review-manifest.json`, starts preview from `WAYGATE_PREVIEW_PORT` or `20001` with incrementing fallback, uses Scope as the reference before final assembly, refreshes approval metadata after final assembly, and keeps the server alive until controller exit. |
| Gate generation | `workflow_controller/gates/generators/__init__.py` | Builds the final `requirements-and-acceptance.md` body from four checkpoint artifacts and records artifact hashes. |
| Gate validation | `workflow_controller/gates/validators/__init__.py` | Validates staged package consistency, stage outputs, hash rows, appendices, E2E/browser contracts, prototype manifest references, legacy 4.9 compatibility, and Unit Plan gate requirements. |
| Unit Plan handoff | `workflow_controller/prompts/unit_plan.py` | Injects staged package artifact path/hash/status metadata into the Unit Plan prompt and requires inherited AC, Journey, design, architecture, test strategy, E2E, UI, and risk obligations. |
| Unit continuity gate | `workflow_controller/unit_handoff.py`, `workflow_controller/gates/validators/__init__.py`, `workflow_controller/steps/builder.py`, `workflow_controller/rrc_controller.py` | Validates `depends_on` and `handoff` metadata, writes producer `handoff-evidence.json`, and blocks downstream Builder with `unit_handoff` when dependency evidence is missing or failed. |
| Human review control | `workflow_controller/approval_notes.py`, `workflow_controller/rrc_controller.py`, `workflow_controller/prompts/unit_plan.py`, `workflow_controller/prompts/builder.py`, `workflow_controller/cli.py` | Persists approval notes as non-contract audit context, renders `Approval Notes Non-Contract Context`, adds `i` draft merge and `m` guarded manual adoption, records `human_interrupt`, and splits `approve --reason` / `revise` CLI routes without changing the approved body/hash contract. |

## State Shape

Staged package state lives under `requirementsPackage`:

```json
{
  "version": "v0.6.2-staged",
  "artifacts": {
    "scope": {
      "stage": "scope",
      "path": ".../requirements-scope.md",
      "hash": "sha256:...",
      "status": "complete"
    }
  }
}
```

The status field is the controller-visible state of each artifact. `complete` records a usable artifact whose current file hash matches state. `stale` records revision or validation invalidation and prevents final package completion.

V0.6.2a also stores `requirementsSurfaceClassification` when staged Requirements, `--spec`, or target initialization are active:

```json
{
  "requirementsSurfaceClassification": {
    "product_ui": "required",
    "web_system": "required",
    "prototype_required": "required",
    "visible_surfaces": ["课程生产中心入口", "状态回看页面或 API", "课程草稿详情"],
    "evidence_snippets": ["requirementsSpec.path: ..."]
  }
}
```

The three classification fields use `required`, `not_required`, or `unknown`. Default false state flags are only recorded as ignored snippets and cannot prove that UI or prototypes are unnecessary.

## Flow

The staged flow uses these controller steps:

1. `REQUIREMENTS_SCOPE_DRAFT`
2. `REQUIREMENTS_PRODUCT_DESIGN_BRIEF`
3. `REQUIREMENTS_TECH_ARCH_BRIEF`
4. `REQUIREMENTS_TEST_STRATEGY_BRIEF`
5. `REQUIREMENTS_PACKAGE_ASSEMBLE`
6. `WAITING_REQUIREMENTS_ACCEPTANCE`

Each checkpoint runner writes an artifact under the controller artifact tree and updates the state record through the package helper. The controller advances only one step per `run_once()` so timeout, retry, and review evidence stay scoped to the current checkpoint.

Before staged checkpoint prompts run, the controller refreshes `requirementsSurfaceClassification`. Prompt rendering then injects both the surface classification and the spec/conversion artifact references so Scope, Product Design, Architecture, and Test Strategy stay anchored to the target product/system.

## Product Design Prompt Branching

`workflow_controller/prompts/requirements_package.py` owns the V0.6.2g `product_design_prompt_contract(state)` helper. The helper classifies a Product Design run into no-spec, supported-spec, or backend/API/CLI-only no-UI branches from state and Scope basis, then `render_product_design_prompt()` prepends the matching branch rules.

The no-spec branch is intentionally prompt-level: it requires same-conversation brainstorming and one surface at a time confirmation before writing Product Design artifacts. It does not add a deterministic transcript parser, controller blocker, or per-page gate. The supported-spec branch keeps the existing staged artifact path/hash flow. The backend/API/CLI-only branch uses positive Scope evidence and asks for a single explicit no-UI/no-prototype confirmation instead of relying on default false flags. Annotation runtime architecture for subprocess-only execution, deprecated no-op `WAYGATE_ANNOTATION_TMUX`, legacy Claude annotation migration to OpenCode, and env key-only metadata is documented in the external spec annotation architecture.

## Final Gate Assembly

Final assembly reads the four checkpoint artifacts, recalculates their hashes, compares them with state, and renders one approval gate. The gate contains an artifact hash table and appendices for the four checkpoint bodies.

`validate_staged_requirements_package_consistency` checks that:

- all required appendices are present;
- every checkpoint has a hash row;
- file hashes match the recorded state;
- obvious AC, Journey, or AO conflicts between checkpoint artifacts are rejected.

In staged package mode, Requirements validation no longer requires the legacy full `## 4.9 目标项目基础设施信息` section in the final gate. Legacy state keeps the existing 4.9 requirement.

V0.6.2a adds target-perspective validation for non-Waygate target projects. Product Design and Technical Architecture artifacts are rejected when they primarily describe Waygate/controller staged package operation, controller orchestration, runner contracts, checkpoint transitions, or artifact hash mechanics instead of target product UX and target system architecture.

When the surface classification is `required`, existing prototype manifest and clickable Web prototype gates still apply. When it is `unknown`, Requirements must explain the uncertainty or route back to Scope/Product Design. A `not_required` result requires explicit backend/API/CLI-only evidence.

Product Design now owns the first manifest contract check for `prototype_required=required` or `web_system=required`. `workflow_controller/prompts/requirements_package.py` tells the Product Design agent to write `artifacts/requirements-draft/prototype-manifest.json` using the canonical top-level `prototypes[]` schema, and to keep local prototype paths artifact-local relative to that manifest directory. `validate_staged_requirements_stage_output()` validates that local HTML/image/Markdown paths resolve from `artifacts/requirements-draft/`, reports the resolved path when a file is missing, and treats workspace-relative `docs/prototypes/...` as invalid unless that path exists under the artifact tree. The same stage validation checks that the manifest has a prototype access method, page states, click path, AC/Journey mapping, implementation targets, and surface contracts before marking Product Design complete. Manifest and surface-contract AC/Journey references must exist in Scope.

Final Requirements validation reuses the same manifest validator. A manifest that passes with `require_clickable=True` counts as clickable webpage prototype evidence, so valid Product Design artifacts are not rejected merely because the final gate text lacks a duplicate prose paragraph. The textual evidence fallback still recognizes artifact-local clickable HTML or URL evidence when Product Design names the manifest path, page states, click path, and AC/Journey mapping, but manifest schema and file checks remain strict.

The shared stage-output validator also runs these earlier checks:

- Scope stage real E2E/browser review text must resolve to a canonical e2e AC or active e2e Journey; prototype-only artifact review is validated through prototype manifest and later prototype conformance.
- Product Design and Technical Architecture cannot reference AC/Journey IDs missing from Scope.
- Technical Architecture must cite Scope canonical e2e AC/Journey IDs when it inherits E2E/browser handoff.
- Requirements Test Strategy must use the fixed `## 4.6 E2E 测试方法与前置依赖矩阵（E2E Test Method & Prerequisite Matrix）` heading and 11-column matrix when E2E/browser review is declared or inherited. The matrix accepts only `local_real` or `production_readonly` environments, requires real entrypoints, concrete user/API/service steps, fixed fixture/setup, no core business API mocks/stubs, and machine-checkable assertions. The matrix records command intent; Unit Plan owns exact commands and evidence rows.

`workflow_controller/gates/validators/__init__.py` treats the Requirements 4.6 table as a canonical fixed-column table block, not as every table nested under the 4.6 markdown section. The row collector resets its active 4.6 header at non-table boundaries and at noncanonical table headers, preventing later subsection tables such as 4.7 AC closure matrices from becoming synthetic 4.6 obligations while preserving strict checks for malformed rows inside the true 4.6 matrix.

`workflow_controller/gates/validators/__init__.py` parses AC verification layers from explicit facts only: canonical AC/layer table columns, direct inline AC markers, or clear non-table layer buckets. Mixed explanatory tables such as visible-surface maps or supporting-coverage maps may mention direct E2E ACs together with integration/prerequisite ACs, but the parser does not spread the E2E marker to every AC in the same note. Current AC collection strips source/provenance material from obligation discovery: source map prose, conversion artifact notes, `AC-SPEC-001 -> AC-V10-001` mapping lines, `AC-SPEC-001 至 AC-SPEC-012` range explanations, wildcard examples, and table columns such as `Source AC`, `Source AC / TC`, `Imported AC`, and `Original AC` are ignored. Canonical current AC declarations still count, even when the adopted current ID is an external-looking ID such as `AC-SPEC-001 [verification: integration]`. Shared ID tokenization rejects wildcard fragments and trailing-hyphen partial IDs before validators see them.

The parser accepts Requirements-stage support layers `static`, `regression`, and `prerequisite` alongside behavioral layers `unit`, `functional`, `integration`, `e2e`, and `manual`. Only normalized `e2e` facts feed the real E2E review matrix and Unit Plan real-E2E mapping checks; support layers are treated as non-E2E classifications for Requirements completeness.

`workflow_controller/journeys.py` uses the same support-layer contract for Journey Acceptance Matrix rows. It accepts canonical headers plus common aliases such as `Journey id`, `User steps`, `Acceptance contract`, `Path / assertion focus`, and `Linked AC`, falls back to the Journey ID when no `Title` column is present, normalizes Journey layers, and treats `static`, `regression`, and `prerequisite` as valid non-E2E active Journey layers. Because final staged gates may include Scope and Test Strategy Journey tables for the same business path, compatible duplicate rows are merged by Journey ID, while status or verification-layer conflicts remain validation errors. `workflow_controller/gates/validators/__init__.py` uses the same header aliases when collecting active e2e Journeys for Requirements 4.6 coverage, so header wording does not force valid Scope artifacts into unnecessary rewrites. Journey-local inline markers are not treated as AC layer facts for other AC IDs on the same prose line.

If stage validation fails before Requirements are approved and the runner supports automatic dispatch, `workflow_controller/rrc_controller.py` writes the same stage validation JSON artifact, marks the failed stage and downstream stages stale, injects `_requirements_stage_validation_feedback()` into `requirementsRevisionFeedback`, records `requirements_stage_auto_revision_requested`, and leaves `currentStep` on the same checkpoint with the same next action. The retry budget reuses the in-process Requirements auto-revision semantic counter and `requirementsAutoRevisionMax`; exceeding it records `requirements_stage_auto_revision_blocked` and enters the normal `requirements_stage_validation` hard block. If Requirements are already approved, stage validation does not auto-change the contract and blocks immediately. `unblock_blocked_workflow()` captures the stage-validation reason as `requirementsRevisionFeedback` before clearing the blocker, so the next checkpoint prompt receives the controller failure directly. When the same blocker reveals an upstream AC, Journey, or Requirements contract conflict, `_revise_requirements_gate()` also permits `waygate revise --gate requirements` from the staged checkpoint blocker and routes through semantic stage selection. The final Requirements preflight still performs the complete Requirements quality validation after assembly.

## Unit Plan Prompt And Validator

The Unit Plan prompt consumes the final Requirements gate plus `requirementsPackage` metadata. In staged mode it must render artifact path/hash/status records for:

- scope
- product_design
- architecture
- test_strategy

The Unit Plan prompt requires inherited AC, Journey, Product Design, Technical Architecture, Test Strategy, E2E method, UI obligations when explicitly declared, risk obligations, and document deliverables.

The Unit Plan validator requires an `Infrastructure / Execution Context Matrix` that covers repository, runtime, debugging, reference environment, documentation, architecture/interface, and dependency facts. This is the architecture endpoint for the V0.6.2 shift away from overloading Requirements `4.9`.

V0.6.2d extends the same validator chain with unit continuity checks. `validate_unit_plan_handoff_continuity()` reads the Controller State Patch after it is applied, checks dependency existence and cycles, validates producer/consumer handoff matching, rejects vague summaries, and requires ready checks to map to commands or test cases. `workflow_controller/unit_handoff.py` centralizes field aliases and evidence helpers so validator, verifier, and Builder preflight share the same interpretation.

`run_verifier()` writes `handoff-evidence.json` for producer units that declare handoff metadata. The artifact records pass/fail state, produced outputs, consumed inputs, ready checks, resolved evidence artifacts, and structured issues. `RalphRefinerController` checks dependency handoff evidence before `prepare_builder_prompt()` and `run_builder()`; failed or missing evidence sets `status=blocked`, `currentStep=EXECUTE_UNIT`, and `blockedContext.category=unit_handoff`.

`RalphRefinerController._apply_and_validate_unit_plan_gate()` is the single Unit Plan gate helper. The drafter path applies it before annotation or human review, and the approval path applies it again after human approval. This keeps infrastructure matrix, final evidence candidates, golden path, real E2E, Journey, prototype, AO, AC, and walkthrough validation from diverging between preflight and approval revalidation.

## Human Review Control Architecture

V0.6.2f adds review-control state and artifacts beside the staged package state. `workflow_controller/approval_notes.py` owns normalization and rendering of approval notes. `RalphRefinerController.approve_human_gate()` accepts optional `approval_notes`, writes `.rrc-controller-*/artifacts/approval-notes/<gate>-<hash>.json`, and stores a lightweight `gateApprovalNotes.<gate>` index with the approved body hash. That hash is the boundary: notes are advisory and cannot update `requirementsAcceptedHash`, `unitPlanAcceptedHash`, AC extraction, Journey extraction, AO ledgers, or test case matrices.

Prompt handoff reads `gateApprovalNotes` through `render_approval_notes_context()`. Requirements notes are rendered into the Unit Plan draft prompt, and Requirements plus Unit Plan notes are rendered into the Builder prompt under `Approval Notes Non-Contract Context`. Each block states that the approved gate body wins conflicts.

The `i` review action records `gateDraftMerge.<gate>` with before/after hashes and a draft artifact path under `artifacts/gate-draft-merge/`. It keeps the gate pending and does not call the approval write path. The `m` action and `waygate approve --reason` share the guarded manual-adoption validator: current gate body hash must differ from `pendingGateReview.baseline_body_hash`, a reason or approval notes must exist, and the same deterministic gate validators must pass before the controller writes an approved hash.

Ctrl+C handling is implemented at the controller loop boundary. The controller catches `KeyboardInterrupt`, records `status=blocked`, `blockedContext.category=human_interrupt`, interrupted step/action, occurred timestamp, and a best-effort tmux `send-keys C-c` result when a target pane is known. The recovery guidance treats `human_interrupt` as an auditable blocked category, not as a hidden agent failure.

The dedicated architecture details live in `docs/architecture/human-review-control-architecture.md`.

## Revision Routing

Requirements revision in staged mode clears Requirements and Unit Plan approval state, records feedback, marks the affected stage and downstream stages stale, and routes to that stage through `requirements_revision_routing.py`:

- Scope issues have highest priority and include AO mapping gaps, required Journey contracts with no active Journey rows, E2E review rows not mapped to an E2E AC or active Journey, unknown AC/Journey references, conflicting AC verification layers, conflicting Journey status, and target surface classification inconsistencies.
- Product Design issues include pure prototype manifest, prototype path, page state, click path, access-method, UI, and product-review feedback.
- Architecture issues include target API, data-flow, state write/readback, runtime interaction, module-boundary, and external-system gaps.
- Test Strategy issues include mock policy, `environment_kind`, E2E method, fixture/setup, verification layer, 4.6 matrix shape, evidence shape, and expected assertion quality.

Combined preflight reasons are checked in upstream order: Scope, Product Design, Architecture, then Test Strategy. Missing Acceptance Obligation requirements mapping, missing AO coverage, unknown acceptance criteria, unknown Journey references, conflicting AC verification layers, conflicting Journey status, and E2E review that is not mapped to an active E2E AC/Journey route to `REQUIREMENTS_SCOPE_DRAFT` even when the same reason also mentions `prototype-manifest.json`, Web, page states, verification layer, or click path.

V0.6.2c adds an explicit Requirements checkpoint revise CLI route for the same staged rollback primitive. `waygate revise --gate requirements --checkpoint product-design --reason "..."` normalizes CLI names and Chinese aliases to the stable internal stage key, writes the checkpoint and human reason into `requirementsRevisionFeedback`, clears Requirements and Unit Plan approvals, deletes the current Unit Plan gate, marks the selected checkpoint and downstream artifacts stale, and records `requirements_staged_revision_routed` with `gate`, `checkpoint`, `checkpoint_label`, `reason`, `reason_key`, and `routing_source`. `--checkpoint` is rejected for `--gate unit-plan`.

For controller-validation-only auto-rework, `_revise_requirements_gate()` routes from the controller validation error rather than the full old gate body. This prevents stale Scope/E2E text in the previous assembled gate from stealing a pure Product Design issue such as missing clickable prototype page states or click path. The routed event records `reason_key`, `routing_source`, and `routing_reason`, and the prompt feedback is reduced to the original controller reason, routed stage, missing fields, and an expected output example.

The auto-revision budget also uses semantic keys from the routing module. `RalphRefinerController._auto_revise_invalid_requirements_draft()` tracks the last Requirements semantic reason key, consecutive attempt count, and total requested attempts in controller instance memory for the current `waygate go`. It intentionally does not use `session.json` fields such as `requirementsAutoRevisionLastReasonKey`, `requirementsAutoRevisionConsecutiveCount`, or `requirementsAutoRevisionTotalCount` as control-flow input, and `_save_state()` strips those legacy fields on later writes. Within one controller process, once a semantic issue exceeds `requirementsAutoRevisionMax`, the controller blocks at `WAITING_REQUIREMENTS_ACCEPTANCE` with `blockedContext.category=requirements_contract` instead of rerouting the same issue through another checkpoint cycle. A later process, a human Requirements revise, or the next `waygate go` starts that budget from zero.

Stage-specific controller validation failures use the same invalidation helper with a narrower starting stage. This keeps stable upstream checkpoint artifacts intact and avoids unnecessary regeneration.

## Compatibility And Safety

Legacy approved gates and sessions already waiting for Requirements acceptance are not force-migrated. The staged mode switch is explicit through `requirementsPackage.version == "v0.6.2-staged"` or the staged flow state.

Artifacts and logs record paths, hashes, statuses, and safe summaries only. Environment variable values, tokens, database URLs, and other secret-like values must not be written to package artifacts, events, or validation errors.

## Verification Surface

The regression surface includes:

- package helper unit tests;
- state machine action tests;
- prompt renderer tests;
- stage runner artifact and summary tests;
- controller `run_once()` checkpoint flow tests;
- final package assembly and validator tests;
- Unit Plan prompt and infrastructure matrix tests;
- annotation ordering tests;
- docs registry and roadmap tests;
- full `workflow_controller/tests` regression.
