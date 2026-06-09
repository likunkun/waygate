# Changelog

All notable project changes should be recorded here.

## 0.6.2j

- Packaged the annotation Product Contract Traceability Audit enhancement as `0.6.2j`.
- Added advisory risk-only annotation coverage for product-contract fidelity, information degradation, product field mapping gaps, and out-of-scope boundary risks before human gates.
- Kept the annotation enhancement out of deterministic validators, state schema fields, CLI options, approval sources, and hard gates.

## 0.6.2i

- V0.6.2i is a prompt-only release for the staged Requirements prompt and documentation contract.
- Added prompt-only Requirements acceptance-first intake language: no-`--spec` sessions must first confirm current-version goal, non-goals, acceptance focus, success/failure evidence, and scope boundary before drafting or narrowing scope.
- Strengthened Product Design prompt contracts so each UI/Web/prototype surface is a 1:1 user-task prototype with actor, task start, click path, page states, main business object, success endpoint, AC/Journey mapping, and production target.
- Added Product Journey Contract handoff language for Unit Plan, Builder, Test Strategist, and Refiner prompts, including the `主业务对象血缘拆分矩阵` and explicit wording that fixture, engineering layer, screenshot, or prototype artifact cannot replace product journey closure.
- Updated formal workflow/architecture docs, README/USAGE, roadmap, registry, and package version metadata to `0.6.2i` without adding deterministic validators, state schema fields, CLI options, or hard gates.

## 0.6.2h

- Fixed Requirements Test Strategy 4.6 parsing so the validator consumes only the canonical fixed-column E2E matrix block and does not treat later subsection tables, such as 4.7 AC closure matrices, as 4.6 obligations.
- Added staged Requirements regression coverage for a valid 11-column 4.6 matrix followed by a 5-column 4.7 closure table containing the same E2E AC.
- Updated staged Requirements workflow and architecture docs, release notes, and package version metadata to `0.6.2h`.
- Follow-up: fixed current AC collection so source/provenance prose, source maps, conversion notes, `AC-SPEC-*` wildcard examples, `AC-SPEC-001 -> AC-V10-001` mappings, and source/imported/original AC columns do not create current-version AC obligations. Canonical current AC declarations with verification layers still count, including deliberately adopted external-looking IDs.

## 0.6.2g

- Added Product Design prompt branch handling for no-spec brainstorming in the same tmux conversation, supported-spec compatibility, and backend/API/CLI-only no-UI/no-prototype confirmation based on positive Scope evidence.
- Removed the annotation-specific tmux pane runtime. Annotation passes now always use the subprocess runtime; `WAYGATE_ANNOTATION_TMUX` is accepted as a deprecated no-op and no longer creates panes, run-local wrappers, run ids, or `done.json` files.
- Removed Claude Code as an annotation backend. Declared annotation backends are `opencode` and `codex`; persisted Waygate built-in Claude annotation configs migrate to the built-in OpenCode template. Claude Code remains available as a normal `tmux-claude` workflow runner.
- Hardened env key-only audit metadata so state, events, summaries, artifacts, and captured output record key names and omit env values, tokens, database URL values, passwords, secrets, `api_key` values, signatures, and proxy values.
- Added V0.6.2g script-entry verification under `scripts/verify/` and updated formal workflow, architecture, usage, release, and roadmap documentation while keeping V0.6.3 Strict Test Presence / Per-Role Runner Configuration as future scope.

## 0.6.2f

- Persist Plannotator approval notes from approved Requirements and Unit Plan gates as audit-only advisory context, then inject them into next-stage prompts under `Approval Notes Non-Contract Context`.
- Added human gate menu actions `i` and `m`: `i` creates a pending draft from review notes, while `m` adopts a human-edited gate body only when the body hash changed, a reason or notes exist, and deterministic validators pass.
- Converted Ctrl+C during automatic execution into an auditable `blockedContext.category=human_interrupt` state with best-effort tmux `C-c` delivery and recovery guidance.
- Split CLI review routes so `waygate approve --reason` uses guarded manual adoption and `waygate revise` without a reason returns to the current approval point, while checkpoint revise still requires `--reason`.
- Added V0.6.2f review bundle and prototype conformance evidence for approval notes, draft merge, manual adoption, interruption recovery, revise routes, legacy review compatibility, and real Waygate target mapping.
- Updated README/USAGE/CHANGELOG/ROADMAP, formal workflow/architecture docs, verification scripts, and package version metadata to `0.6.2f` while keeping V0.6.3 Strict Test Presence / Per-Role Runner Configuration as future scope.

## 0.6.2e

- Added `open-spec-package` intake for Open Spec document package directories containing `01-requirements.md` plus at least one supporting package document.
- Extended Spec Kit feature package detection to arbitrary directory names when `spec.md` is accompanied by feature artifacts such as `plan.md`, `tasks.md`, or `contracts/`.
- Reject `.specify` workspace/tool roots and ordinary docs directories with guidance to pass `specs/<feature>/` or a concrete `spec.md`.
- Wrote conversion artifacts for package-directory imports, including package entrypoints in `import-summary.json`, `source-map.json`, and `validation-report.json`.
- Updated Requirements prompt/brief wording, README/USAGE, workflow/architecture docs, and package version metadata to `0.6.2e`.

## 0.6.2d

- Added a Unit Continuity Gate for multi-unit Unit Plans, including `单元连贯性摘要`, Handoff Matrix expectations, and structured `depends_on` / `handoff` metadata.
- Added Unit Plan validation for missing dependencies, circular dependencies, vague handoff summaries, unmatched downstream `requires[]`, and ready checks not mapped to commands or test cases.
- Made Verifier write `artifacts/<unit-id>/handoff-evidence.json` and fail producer verification when declared handoff artifacts or ready checks are missing.
- Block downstream Builder execution with `blockedContext.category=unit_handoff` when dependency handoff evidence is missing, failed, or mismatched.
- Documented the workflow policy in `docs/workflow/unit-continuity-handoff-policy.md` and updated package version metadata to `0.6.2d`.

## 0.6.2c

- Made the public staged Requirements checkpoint names Chinese-primary: 需求范围检查点, 产品设计简报, 技术架构简报, and 需求测试策略简报, while keeping internal stage keys unchanged.
- Updated final Requirements package assembly to show Chinese appendix titles and checkpoint names in the artifact hash table.
- Added `waygate revise --gate requirements --checkpoint ... --reason ...` for explicit rollback to a staged checkpoint, including Chinese aliases such as `产品设计`.
- Kept Unit Plan revision behavior unchanged and reject `--checkpoint` with `--gate unit-plan`.

## 0.6.2b

- Added Blocked Assist for controlled diagnosis of `status=blocked` workflows, with summary artifacts, human-confirmed `human_reason`, and explicit controller-selected recovery routes.
- Promoted the Requirements prototype preview from a temporary Plannotator-only server to a controller process-level preview service.
- Product Design checkpoints now generate the Plannotator review HTML/manifest after successful validation, using the Scope checkpoint as the requirements reference before the final approval gate exists.
- Reuse the same preview URL through Architecture, Test Strategy, final Requirements assembly, Requirements human review, and Plannotator-assisted review.
- Rebuild the review bundle after final Requirements assembly so the manifest records the real approval gate path while keeping the current preview port.
- Changed preview port binding to start from `WAYGATE_PREVIEW_PORT` or `20001` and increment when the port is occupied.
- Kept the preview server alive after Plannotator Close and added proxy-environment guidance for `NO_PROXY/no_proxy`.

## 0.6.2a

- Added target surface classification for staged Requirements packages, recording target UI/Web/prototype needs, visible surfaces, and redacted evidence snippets from specs, target context, unit metadata, and feedback.
- Updated staged Scope, Product Design, Architecture, and Test Strategy prompts so they stay centered on the target product/system instead of Waygate/controller workflow.
- Preserved Requirements prototype hard gates for classified UI/Web targets, while allowing explicit backend/API/CLI-only targets to declare a no-UI basis.
- Added preflight rejection for non-Waygate target artifacts whose Product Design or Architecture primarily describes Waygate/controller internals.
- Improved staged revision routing so UI/prototype feedback returns to Product Design and interaction/API/data-flow feedback returns to Architecture.
- Routed combined AO mapping or E2E AC/Journey mapping blockers back to Scope before UI/prototype keywords, preventing prototype-related wording from looping through Product Design.
- Required Product Design checkpoints for classified prototype/Web targets to prompt for and stage-validate `artifacts/requirements-draft/prototype-manifest.json`.
- Clarified Product Design manifest local path semantics: local prototype paths must resolve from `artifacts/requirements-draft/`, with diagnostics showing the resolved path and guidance for workspace-relative `docs/prototypes/...` mistakes.

## 0.6.2

- Added the Staged Requirements Package flow: Requirements Scope, Product Design Brief, Technical Architecture Brief, and Requirements Test Strategy Brief now run as focused checkpoints before one final human Requirements approval gate.
- Added final package assembly with checkpoint artifact hashes and appendix content, plus staged package consistency validation.
- Moved detailed target infrastructure intake into the Unit Plan Infrastructure / Execution Context Matrix while keeping Requirements focused on minimal context.
- Added Unit Plan inheritance of staged artifact path, hash, and status metadata so scope, ACs, journeys, design, architecture, E2E, and risk obligations continue downstream.
- Added formal V0.6.2 workflow and architecture docs, and kept Strict Test Presence / Per-Role Runner Configuration in V0.6.3.

## 0.6.1

- Added supported OpenSpec/OpenAPI and Spec Kit intake paths with normalized requirements, source maps, validation reports, and clear unsupported/deferred errors.
- Added non-approving role-based annotation and verification-assist configuration for Requirements, Unit Plan, and Final Acceptance gates.
- Added `--annotation-agent` CLI options on `init`, `start`, `go`, `drive`, and `run` so operators can enable risk-only annotation agents without editing `session.json`.
- Added prompt contracts and prompt-template registry coverage for risk-only annotation artifacts.
- Added flexible verifier evidence rows so descriptive command evidence can record structured refs and `human_review_required` without overriding deterministic command status.
- Added formal V0.6.1 workflow and architecture docs, and packaged the new `docs/architecture/` subdirectory.

## 0.6.0m

- Added Unit Plan preflight for `golden_path: true`: golden-path test cases must be `layer=e2e`, use `local_real` or `production_readonly`, declare a real entrypoint, provide fixture/setup, run a concrete command listed in `verification_commands`, use strong expected assertions, and avoid core business API mocks/stubs.
- Required Requirements-declared E2E ACs and active E2E Journeys to map to `layer=e2e` Unit Plan test cases before Unit Plan approval.
- Clarified that E2E is not browser-only: API-only and service-only golden paths can use pytest/API/service E2E against real entrypoints.
- Rendered Golden Path as an explicit Unit Plan Test Case Matrix column alongside Layer, Environment, Real Entry, and Core API Mock.
- Updated Requirements/Unit Plan prompts, workflow docs, README/USAGE, and package version to `0.6.0m`.

## 0.6.0k

- Required `ui-ux-pro-max` in Requirements, Unit Plan, Builder, and UI Design Brief prompt contracts for UI/Web/prototype work.
- Clarified that `frontend-design` is optional for new visual exploration or local polish, but cannot replace existing product UI/prototype consistency work.
- Required real UI inventory before prototype design: routes, DOM/components, existing page structure, screenshots, historical design, or reference environments.
- Updated `waygate doctor` so `skill_recommendations.ui_ux_design` warns when only `frontend-design` is installed and prefers `ui-ux-pro-max` when both skills are present.
- Added and packaged `docs/workflow/ui-ux-skill-policy.md`.
- Printed the runtime version on startup: `init` and `run` emit `waygate <version>` as the first line, while `start`, `go`, and `drive` emit the same version line through the timestamped drive output channel.

## 0.6.0j

- Updated no-`--spec` Requirements prompting so the first response still asks only a clarification question, then reads project context after a concrete answer, audits `## 4.9` infrastructure gaps, and follows up in the same tmux pane when facts are still missing.
- Required agent-side non-destructive validation for user-supplied infrastructure facts, with unverifiable external/private systems recorded as user-provided and not directly verified.
- Tightened Requirements preflight so vague or unsupported missing infrastructure facts are rejected unless they include checked sources, a 4.8 user-confirmation record, or a specific not-applicable reason.
- Required `## 4.8` traceability when `## 4.9` claims infrastructure facts are user-confirmed or verified.
- Fixed Plannotator and prototype preview access lines so services can still bind on `0.0.0.0`, while printed browser URLs use the machine's primary IP address or `WAYGATE_DISPLAY_HOST`.
- Switched Plannotator remote access setup to `PLANNOTATOR_REMOTE=1`, and made the controller prototype preview server use fixed port `20001` by default.

## 0.6.0i

- Added `docs/README.md` as the generated and packaged documentation entry point and lightweight registry.
- Updated generated `AGENTS.md` guidance to read `docs/README.md`, separate formal docs from process state, and treat `.rrc-controller-*` as audit evidence rather than long-term documentation.
- Changed Requirements infrastructure intake so document sources are inventoried as formal docs, controller evidence, external agent/human docs, external wiki/design/API docs, and missing docs to be preserved.
- Added Unit Plan Document Deliverables Matrix prompting and validation for long-lived product, architecture, workflow, operations, evidence, and document lifecycle changes.
- Added Final Acceptance document deliverable status rendering and blocking only for deliverables marked `Required For Acceptance = true`.

## 0.6.0h

- Added a `tmux_config` section to `waygate doctor` for the recommended `~/.tmux.conf` settings: `mouse on`, `history-limit 100000`, `@scroll-speed 5`, and `@copy-mode-vi 'on'`.
- Made tmux config diagnostics read-only: warnings include expected/actual values and manual actions, but Waygate does not edit or reload tmux config.
- Reworked doctor output to put `summary:`, `focus:`, and `action_required:` before detailed provenance, PATH, environment, skill, and Claude asset sections.
- Added `waygate doctor --color auto|always|never` to highlight status, P1 focus items, manual actions, and section headers for human scanning while preserving plain non-TTY output by default.
- Kept detailed doctor sections stable for troubleshooting while promoting PATH shadow, version mismatch, missing tools, missing skills, and tmux config actions to the top.
- Updated README, USAGE, roadmap, recommended-environment docs, and package version to `0.6.0h`.

## 0.6.0g

- Extended `waygate doctor` with a `claude_assets` section for `~/.claude/commands`, `agents`, `rules`, and `plugins`, reporting only path, status, and count.
- Aligned `skill_recommendations` with the README baseline at that time, including code review, plan execution, webapp testing, and UI-heavy requirements. V0.6.0k later made `ui-ux-pro-max` the required UI/Web/prototype skill.
- Made the controller prototype preview server bind on `0.0.0.0` by default for remote reachability.
- Requested Plannotator remote access with `PLANNOTATOR_REMOTE=1` instead of controlling the bind host.
- Documented remote review host behavior; current browser URLs are printed with the machine's primary IP address.

## 0.6.0f

- Added real E2E evidence policy gates for Unit Plan approval: mocked/stubbed core API browser tests cannot satisfy E2E, golden path, prototype conformance, Journey closure, or Web-system acceptance evidence.
- Extended verifier evidence rows with environment kind, real entrypoint, core API mock status, mocked routes, browser runtime errors, request failures, and screenshot references.
- Marked mocked browser E2E evidence as `invalid` even when the command exits successfully, and failed real E2E evidence when console/page/request runtime errors are recorded.
- Expanded Final Acceptance and Prototype Conformance matrices with environment, mock, and runtime-error columns, and blocked prototype/golden-path acceptance on non-real E2E evidence.
- Kept remote/production checks explicit through `environment_kind=production_readonly` when requirements or feedback demand read-only production verification.

## 0.6.0e

- Extended `waygate doctor` with `environment_checks` for Python, pytest, tmux, tmux session, Claude Code, Codex, Plannotator, `dpkg-deb`, and recommended Plannotator port `20000`.
- Extended `waygate doctor` with common agent skill root scans, installed skill reporting, recommended workflow skill gap warnings, and optional `WAYGATE_SKILL_ROOTS`.
- Kept Claude Code, Codex, and Plannotator optional by reporting warning/manual action entries without failing `doctor`.
- Added bilingual recommended-environment docs under `docs/operations/` and Waygate introduction/best-practices docs under `docs/product/`, including a PPT outline without generating `.pptx`.
- Updated README, USAGE, ROADMAP, and package docs links for V0.6.0e while keeping V0.6.1 and V0.6.2 as future scope.
- Packaged the new product and operations docs under `/usr/share/doc/waygate/docs/` and aligned the package version with `workflow_controller.__version__`.

## 0.6.0d

- Restored `approvals/requirements-and-acceptance.md` as the Requirements Plannotator approval target even when a prototype review bundle exists.
- Kept `plannotator-review.html` as an auxiliary rendered prototype preview served by the controller preview server.
- Recorded approval file, auxiliary preview file, manifest path, and temporary preview URL in Plannotator review metadata without writing temporary localhost URLs into the approval file.

## 0.6.0c

- Made target-project infrastructure intake apply to every Requirements draft, with fixed section `## 4.9 目标项目基础设施信息`.
- Added Requirements preflight validation for missing, incomplete, or placeholder infrastructure categories.
- Added `waygate doctor` to report executable path, module path/version, dpkg version, PATH candidates, and command shadow warnings.
- Hardened Debian packaging so the control `Version`, package module `__version__`, and `waygate --version` stay aligned.
- Added Debian post-install warnings for user-level `waygate` wrappers such as `~/.local/bin/waygate` without deleting user files.

## 0.6.0b

- Added prototype-to-production conformance gating for Requirements, Unit Plan, and Final Acceptance.
- Required prototype manifests to map each UI/Web prototype to real implementation targets through `implementation_targets` or compatible aliases.
- Extended conformance from whole-prototype targets to required `surface_contracts`, including dialogs, drawers, panels, selectors, management surfaces, and real entry points.
- Added Unit Plan validation for real route/page conformance tests with concrete assertions.
- Added the Final Acceptance `Prototype Conformance Matrix` and blocking validation for missing or failed conformance evidence.
- Preserved `currentUnitIsWebSystem` in Controller State Patch.

## 0.6.0a

- Added Requirements prototype review bundles for Plannotator.
- Added `prototype-manifest.json` validation, normalized review manifests, copied local prototype assets, and read-only localhost preview links.
- Kept approval on `approvals/requirements-and-acceptance.md`; newer releases use the rendered prototype HTML only as an auxiliary preview.
- Hardened UI/UX and Web prototype preflight for missing files, unknown ACs, missing page states/click paths/AC mappings, and sensitive URL query parameters.

## 0.6.0

- Added `__version__` to the Python package and `--version` flag to the CLI.
- Cleaned up roadmap version numbering: next priorities now start at V0.6.0.
- Prepared GitHub-facing English and Chinese documentation.
- Added community files for contribution, security, issues, and pull requests.
- Kept Requirements controller preflight in front of human confirmation after draft revisions.

## 0.5.4

- Added mandatory Requirements clarification before writing the Requirements Gate, with clarified answers recorded in section 4.8.
- Added human-review tmux reminders for Requirements, Unit Plan, Final Acceptance, and Bug Fix gates without submitting input or advancing workflow state.
- Cleared tmux agent input before normal dispatch by default, with `WAYGATE_TMUX_CLEAR_INPUT_BEFORE_DISPATCH=0` as the opt-out.
- Showed the current project target version separately from the Waygate package version.
- Added version-planning source-of-truth rules to project agent guides.

## 0.5.3

- Added Waygate Debian packaging and `/usr/bin/waygate` wrapper.
- Improved compact terminal output and approval-gate status reporting.
- Added tmux runner reliability fixes, including Codex pane discovery and Claude pane command defaults.
- Improved Requirements and Unit Plan validation around AO, traceability, and Journey mapping.

## Earlier Work

Earlier development history is preserved in `progress.md`, `findings.md`, and `task_plan.md`. Those files are maintainer history, not required user documentation.
