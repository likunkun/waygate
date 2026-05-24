# Waygate Roadmap

[中文](ROADMAP.zh-CN.md) | [README](README.md)

This roadmap describes the direction of Waygate as an AI coding workflow control surface. Version numbers here are planning labels, not a promise of external release cadence.

## Completed Foundation

### V0.1 - Test Strategist

- Test Strategist runner configuration and role-specific environment handling.
- Prompt, schema, and artifact support for test strategy output.
- Controller orchestration with critical feedback routing.
- Review package integration with Unit Plan validation.

### V0.2 - Architecture Split

- Introduced layered package structure:
  - `state_machine/`
  - `gates/`
  - `runners/`
  - `prompts/`
  - `steps/`
- Preserved the internal `workflow_controller` Python package name for compatibility.

### V0.3 - Acceptance-Driven Loop

- Acceptance Obligation Ledger for human feedback and final acceptance issues.
- Requirements quality gate for AO-to-AC mapping and verification layers.
- Product design and technical architecture traceability.
- Verifier evidence schema with structured evidence rows.
- Final Acceptance Evidence Matrix.
- CodeSimplifier/Refiner integration before review and verification.

### V0.4 - Control Plane

- Project initialization guide generation through `AGENTS.md`.
- Requirements negotiation loop and controller-side preflight.
- Change Request Ledger.
- Independent Bug Fix Gate.
- Journey Acceptance Layer.
- Final Scope Audit.
- Requirements Dialogue Brief.

### V0.5 - Runner and Packaging Improvements

- tmux target detection for Claude and Codex panes.
- Automatic Claude pane creation when running in tmux.
- Explicit `tmux-codex` discovery for existing Codex panes.
- Approval-summary-first Markdown gates.
- Compact terminal output.
- Debian package build script and `waygate` command wrapper.

## Next Priorities

### V0.5.6 - Spec Intake & Dependency Documentation

Goal: make local requirements intake auditable before expanding into external spec ecosystems.

Planned work:

- Document local runtime, pytest, tmux, Claude/Codex runner, Plannotator, skills, and Debian packaging dependencies.
- Add `--spec <path>` for Waygate Markdown intake on `waygate init`, `waygate start`, and `waygate go`.
- Store only `requirementsSpec.path`, `requirementsSpec.hash`, `requirementsSpec.sourceType`, and `requirementsSpec.importedAt` in `session.json`.
- Inject spec metadata into the Requirements Dialogue Brief, Requirements Draft prompt, and draft summary artifact.
- Keep Requirements approval and controller quality preflight in place; `--spec` is not an approval bypass.

### V0.6.0 - Infrastructure Knowledge Base

Goal: document operational and infrastructure knowledge without mixing it into V0.5.6 spec intake.

Planned work:

- Create an operations knowledge base for local infrastructure assumptions, service dependencies, and troubleshooting.
- Separate environment/runbook facts from requirements and unit planning artifacts.
- Keep infrastructure docs out of V0.5.6 until this version is explicitly active.

### V0.6.0a - Prototype Review Bundle for Plannotator

Goal: make V0.6.0 prototype evidence directly reviewable in Plannotator before Requirements human confirmation.

Status: implemented in package `0.6.0a`.

Delivered work:

- Generate a structured prototype manifest under the Requirements draft artifacts with prototype id, type, path or URL, title, linked ACs, linked journeys, page state, click path, thumbnail or preview hint, and review guidance.
- Render a Requirements Plannotator review bundle that embeds or links generated prototype images, local HTML prototypes, external prototype URLs, and the AC/Journey mapping table.
- Keep `approvals/requirements-and-acceptance.md` as the approval gate and source of approval status while prototype review bundles provide auxiliary review context.
- Normalize local prototype asset paths into the controller artifact tree so Plannotator can open stable relative links instead of arbitrary agent-generated filesystem paths.
- Add Requirements preflight checks for missing prototype files, incomplete clickable prototype access method, missing page states, missing click path, missing AC mapping, unknown AC references, and sensitive URL query parameters.
- Keep approval semantics unchanged: Plannotator Approve still cannot bypass the Requirements quality gate.

### V0.6.0b - Prototype Conformance Gate

Goal: make Requirements-stage prototypes a production UI acceptance contract for Unit Plan, Verifier, and Final Acceptance, not just a clickable review artifact.

Status: implemented in package `0.6.0b`.

Delivered work:

- Require prototype manifest entries used as UI/Web contracts to map to real implementation targets through `implementation_targets` with compatible aliases `production_targets` and `real_targets`.
- Require multi-surface UI/Web prototypes to declare `surface_contracts` for each required route, page, component, dialog, drawer, panel, form, selector, management surface, and real entry point.
- Detect prototype obligations from Requirements text even when state flags such as `currentUnitNeedsUiDesign` are not set, while preserving controller policy-work exceptions.
- Block Unit Plan approval when prototype conformance tests only exercise static prototype artifacts instead of real production routes/pages.
- Require prototype conformance test cases to declare `prototype_conformance`, `prototype_surfaces` when applicable, `production_targets`, executable commands, concrete expected assertions, real-entry `user_steps`, and E2E layer for browser routes and surfaces.
- Render a Final Acceptance `Prototype Conformance Matrix` with Surface and Entry Point columns, and block final approval when required prototype-to-production evidence is missing or not passed.
- Preserve `currentUnitIsWebSystem` in Controller State Patch alongside `currentUnitNeedsUiDesign`.

### V0.6.0c - Target Infrastructure Intake and Install Diagnostics

Goal: make infrastructure intake mandatory for every target project and make installed `waygate` command provenance auditable.

Delivered work:

- Apply target-project infrastructure intake to every Requirements draft, not only V0.6.0 controller policy work.
- Require fixed Requirements section `## 4.9 目标项目基础设施信息` with repository, runtime, debugging, reference environment, documentation, architecture/interaction/interface, and dependency facts.
- Block Requirements approval when section 4.9 is missing, a category is missing, or category content is empty/placeholder.
- Keep Debian package version, package module `__version__`, and `waygate --version` aligned.
- Add `waygate doctor` and Debian post-install shadow warnings for user-level wrappers such as `~/.local/bin/waygate`.

### V0.6.0d - Requirements Plannotator Approval Source Correction

Goal: keep Requirements approval anchored to the approval Markdown while preserving rendered prototype preview help.

Delivered work:

- Make Requirements Plannotator annotate `approvals/requirements-and-acceptance.md` even when `plannotator-review.html` and `prototype-review-manifest.json` exist.
- Continue starting the controller preview server for `plannotator-review.html` during Requirements review and print the auxiliary preview URL separately from the Plannotator approval URL.
- Record approval file, auxiliary preview file, manifest path, and temporary preview URL in Plannotator review metadata without injecting temporary localhost URLs into the approval file.

### V0.6.0e - Environment Diagnostics and Introduction Materials

Goal: make the recommended local environment and Waygate introduction materials easy to inspect from source and installed packages.

Delivered work:

- Extend `waygate doctor` with `environment_checks` for Python executable/version, `pytest`, `tmux`, tmux session state, Claude Code, Codex, Plannotator, `dpkg-deb`, and recommended Plannotator port `20000`.
- Extend `waygate doctor` with common agent skill root scans, installed skill reporting, recommended workflow skill gap warnings, and optional `WAYGATE_SKILL_ROOTS`.
- Keep Claude Code, Codex, and Plannotator optional: missing tools produce warning/manual action output without failing `doctor`.
- Add bilingual recommended-environment docs under `docs/operations/`, including `docs/operations/recommended-environment.md`.
- Add bilingual Waygate introduction and best-practices docs under `docs/product/`, including a 10-12 page PPT outline without generating a `.pptx`.
- Package the new product and operations docs under `/usr/share/doc/waygate/docs/`.
- Keep V0.6.1 External Spec Intake and V0.6.2 Strict Test Presence as future planned scope, not V0.6.0e delivery.

### V0.6.0f - Real E2E Evidence Gate

Goal: prevent mocked/stubbed browser tests from being accepted as real E2E, golden path, prototype conformance, or production-consistency evidence.

Delivered work:

- Add Unit Plan validation that blocks E2E, golden path, prototype conformance, Journey closure, and Web-system acceptance test cases when their browser scripts mock or stub core business API routes such as `**/api/...`.
- Standardize test case metadata around `environment_kind`, `entrypoint` / `real_entrypoint`, `allows_mock`, and `mocked_routes`, with mocks limited to non-E2E component/contract/visual auxiliary tests.
- Extend verifier evidence rows with environment kind, real entrypoint, core API mock status, mocked routes, browser console errors, page errors, request failures, and screenshot references.
- Classify successful mocked browser E2E commands as invalid evidence and fail real E2E evidence when browser runtime errors are recorded.
- Expand Final Acceptance and Prototype Conformance matrices so environment, mock status, and runtime errors are visible, and require real E2E evidence for prototype and golden path acceptance.
- Require explicit `production_readonly` evidence when Requirements or feedback demand remote logs, production pages, or post-deploy verification.

### V0.6.0g - Doctor Coverage and Remote Review Reachability

Goal: close V0.6.0f documentation gaps while making environment diagnostics and Plannotator prototype review more useful from remote browsers.

Delivered work:

- Record V0.6.0f as delivered in human-readable project records without manually changing the historical `.rrc-controller-v0.6.0f/session.json` to `DONE`.
- Extend `waygate doctor` with `claude_assets` checks for `~/.claude/commands`, `~/.claude/agents`, `~/.claude/rules`, and `~/.claude/plugins`; output is limited to path, status, and count.
- Align recommended skill warnings with the README baseline at that time, including persistent planning, startup, brainstorming, writing plans, TDD, debugging, test strategy, refiner, verification, code review, plan execution, webapp/browser verification, and UI-heavy skill coverage. V0.6.0k later made `ui-ux-pro-max` the required UI/Web/prototype skill.
- Bind the controller prototype preview server on `0.0.0.0` by default, while printing browser URLs with the machine's primary IP address; `WAYGATE_PREVIEW_HOST` overrides preview bind host and `WAYGATE_DISPLAY_HOST` overrides the printed browser host.
- Request Plannotator remote access with `PLANNOTATOR_REMOTE=1`, while printing the approval URL with the machine's primary IP address.
- Document that `0.0.0.0` is a listening address, not a browser target, and use fixed controller prototype preview port `20001` for ACL planning.

### V0.6.0h - tmux Recommended Config and Doctor Information Hierarchy

Goal: make the recommended tmux workstation setup visible in `waygate doctor` while making manual actions easier to scan.

Delivered work:

- Add `tmux_config` checks for `~/.tmux.conf`, covering `mouse on`, `history-limit 100000`, `@scroll-speed 5`, and `@copy-mode-vi 'on'`.
- Parse `set -g key value` and `set-option -g key value`, including simple quoted values, while reporting only recommended keys and never printing unrelated config lines.
- Keep `doctor` read-only: missing or mismatched tmux config produces warnings and manual actions, but Waygate does not edit or reload tmux config.
- Reorder doctor output with top-level `summary:`, `focus:`, and `action_required:` sections before detailed provenance and environment sections.
- Add `waygate doctor --color auto|always|never` so TTY users can see status, P1 focus items, manual actions, and section headers in color while non-TTY output remains plain by default.
- Preserve existing detailed sections, including `environment_checks`, `skill_recommendations`, and `claude_assets`, for troubleshooting continuity.

### V0.6.0i - Documentation Lifecycle

Goal: make formal documentation discoverable and make document updates auditable without turning every historical gap into a blocking acceptance issue.

Delivered work:

- Generate `docs/README.md` during `waygate init/start` as the documentation entry point and lightweight registry, while preserving existing user files through `.generated` drafts.
- Update generated `AGENTS.md` guidance so agents read `docs/README.md`, distinguish formal docs from process state, and treat `.rrc-controller-*` as audit evidence.
- Structure Requirements `文档地址` intake around formal docs, controller evidence, external Agent / human communication docs, external wiki/design/API docs, and missing docs to preserve.
- Add Unit Plan Document Deliverables Matrix prompting and validation for long-lived product, architecture, workflow, operations, evidence policy, and document lifecycle changes.
- Render Final Acceptance document deliverable status and block only deliverables marked `Required For Acceptance = true`.

### V0.6.0j - Requirements Infrastructure Follow-up and Validation

Goal: keep no-`--spec` Requirements intake conversational while preventing unverified infrastructure facts from being copied into approval gates.

Delivered work:

- Keep the first no-`--spec` Requirements drafter reply limited to a clarification question, then require project-context reading after the user gives a concrete answer.
- Require the drafter to audit all seven `## 4.9 目标项目基础设施信息` categories after first clarification and continue asking the user in the tmux pane when infrastructure facts are still missing.
- Require non-destructive verification for user-supplied repository, runtime, debugging, reference environment, documentation, interface, and dependency facts.
- Mark inaccessible external systems, production environments, private wiki/API sources, or other unverifiable facts as user-provided and not directly verified, without inventing evidence.
- Record infrastructure questions, answers, verification methods, conclusions, and residual risks in `## 4.8`, and record source plus verification status for each 4.9 category.
- Strengthen Requirements preflight for missing/none/not-applicable claims and require a matching 4.8 record when 4.9 claims a fact is user-confirmed or verified.

### V0.6.0k - UI/UX Skill Policy

Goal: make UI, Web, clickable prototype, prototype evidence, and production UI consistency work use the correct specialist skill.

Delivered work:

- Require Requirements, Unit Plan, Builder, and UI Design Brief prompt contracts to name `ui-ux-pro-max` for UI/Web/prototype work.
- Clarify that `frontend-design` can help with new visual exploration or local polish, but cannot replace `ui-ux-pro-max` for existing product UI/prototype consistency.
- Require real UI inventory before prototype design: routes, DOM/components, existing page structure, screenshots, historical design, or reference environments.
- Update `waygate doctor` so `skill_recommendations.ui_ux_design` requires `ui-ux-pro-max`, warns when only `frontend-design` is installed, and prefers `ui-ux-pro-max` when both are installed.
- Document the policy under `docs/workflow/ui-ux-skill-policy.md` and package it with the Debian docs.

### V0.6.0m - Golden Path E2E Preflight

Goal: catch non-real golden-path evidence during Unit Plan approval instead of waiting for Final Acceptance.

Delivered work:

- Block `golden_path: true` Unit Plan test cases unless they are `layer=e2e`, use `local_real` or `production_readonly`, declare a real entrypoint, include fixture/setup, run a concrete command listed in `verification_commands`, use strong expected assertions, and avoid core business API mocks/stubs.
- Require Requirements-declared E2E ACs and active E2E Journeys to have matching `layer=e2e` Unit Plan test cases.
- Keep API-only and service-only golden paths valid as pytest/API/service E2E against real entrypoints; browser fields are not required for non-UI systems.
- Render Golden Path explicitly in the Unit Plan Test Case Matrix together with Layer, Environment, Real Entry, and Core API Mock.
- Preserve Final Acceptance real E2E evidence checks as the last line of defense for non-E2E golden evidence, missing real entrypoints, mock core APIs, non-real environments, and runtime errors.

### V0.6.1 - External Spec Intake

Goal: add explicit import paths for external spec ecosystems after Waygate Markdown intake is stable, while closing the approval-ordering, annotation, prompt contract, and flexible evidence gaps required for controller acceptance.

Status: final acceptance approved on 2026-05-23.

Delivered work:

- Design import contracts for OpenSpec and Spec Kit.
- Add parsers, validation, and conversion artifacts for supported external formats.
- Preserve clear unsupported/deferred errors for formats that are detected but not enabled.
- Enforce gate ordering so human approval is the last step in each current phase; controller preflight, schema validation, evidence checks, and annotation passes must finish before a human review file is presented.
- Add role-based annotation and verification-assist configuration for `requirements_annotation`, `unit_plan_annotation`, and `final_acceptance_verification_assist`.
- Support `claude-code`, `opencode`, and `codex` backend families through configurable command, args, env key allowlist, timeout, artifact path, prompt template, and failure policy fields.
- Define a shared non-approval prompt contract plus stage-specific Requirements, Unit Plan, and Final Acceptance templates for risk-only annotation artifacts.
- Allow verification JSON to include strict command-only checks, `descriptive_command` rows where a command still runs and Agent judgement only adds review context, and opt-in `agent_assisted_case` rows where a test case declares `verification_assist` instead of `command`; assisted rows must record structured evidence, `human_review_required`, and an assist artifact path.
- Preserve approval semantics: annotation agents and agent-assisted verification may focus human review on risks, but they cannot approve, skip, or bypass controller gates.
- Document the long-lived workflow rules in `docs/workflow/external-spec-intake-and-annotation-policy.md` and the module boundaries in `docs/architecture/external-spec-intake-and-annotation-architecture.md`.

### V0.6.2 - Strict Test Presence

Goal: prevent non-manual acceptance criteria from passing without executable test cases or explicit evidence.

Planned work:

- Bring Test Strategist forward into the requirements phase.
- Require executable test cases for non-manual ACs.
- Require concrete fixture/setup, command, and expected assertion in Unit Plan test cases.
- Ensure verifier and final acceptance evidence rows map back to test case IDs.

Test case contract hardening sequence:

- TC1 - Test Case Contract v1: define a stable Unit Plan `test_cases[]` contract with `acceptance_criteria[]`, `covers_obligations[]`, `covers_journeys[]`, `layer`, `path_type`, `golden_path`, `setup[]`, `entrypoint`, optional `cleanup[]`, `command_id`, `manual_evidence`, and `assertions[]`.
- TC2 - Source of truth cleanup: make `test_cases[]` in the Controller State Patch the authoritative source; render the Markdown Test Case Matrix from that structured data instead of treating prose and JSON as separate facts.
- TC3 - Backward compatibility and migration: continue reading older fields such as `acceptance_criterion`, `fixture`, `command`, `evidence`, `expected`, `journey_refs`, and `journeyRefs`, but normalize them into the v1 contract and surface migration warnings.
- TC4 - Strict Unit Plan preflight: block missing or unknown AC/AO/Journey references, unresolved `command_id`, static-only behavior coverage, weak assertions, missing E2E `user_steps`, missing setup/entrypoint, and manual evidence masquerading as automated proof.
- TC5 - Pre-human Test Case Review Agent: before Unit Plan human confirmation, run a non-approving reviewer that annotates shallow assertions, fake fixtures, over-broad commands, happy-path-only E2E coverage, AO name-only coverage, and test cases that do not prove their mapped AC.
- TC6 - Verifier evidence alignment: emit one evidence row per planned test case, include command IDs and structured assertions, mark unexecuted planned test cases as `missing`, and keep manual evidence separate from automated `passed` results.
- TC7 - Final Acceptance matrix upgrade: show the full chain from Requirement / Use Case / Journey / AC / AO to Test Case and Evidence so humans review traceable proof instead of agent summaries.

### V0.6.3 - Per-Role Runner Configuration

Goal: make Builder, Refiner, Reviewer, Verifier, and Bug Fix Agent independently configurable.

Planned work:

- Add role-specific runner, command, env, and timeout configuration.
- Normalize role metadata in artifacts.
- Keep secret values out of logs and artifacts.

### V0.6.4 - OpenCode Runner

Goal: provide a first-class OpenCode runner implementation.

Planned work:

- Implement runner invocation and completion signaling.
- Align metadata and artifacts with existing runner contracts.
- Add regression coverage for dispatch, completion, and failure modes.

### V0.6.5 - Task Workspace and Branch Isolation

Goal: reduce cross-task mutation and stale state pollution.

Planned work:

- Allow each unit to run in an isolated workspace or branch.
- Produce patch/checkpoint artifacts per unit.
- Keep state transitions tied to the isolated execution context.

### V0.6.6 - File and Tool Policy

Goal: move role restrictions from prompts toward enforceable policy.

Planned work:

- Limit writable paths by role.
- Restrict approved requirements and acceptance files during implementation.
- Record policy decisions in artifacts.

### V0.6.7 - Clean Verification

Goal: make verifier results less dependent on local leftovers.

Planned work:

- Support clean checkout or clean environment verification.
- Separate local preflight from authoritative verification evidence.
- Capture reproducible verifier context.

## Longer-Term Direction

### V0.7 - Recovery and Observability

- Checkpoint and time-travel support.
- Unified trace IDs across runs, units, AOs, ACs, journeys, evidence, and logs.
- Standardized evidence types such as screenshots, traces, API responses, coverage, and database checks.
- Failure taxonomy for requirements, test gaps, environment issues, implementation bugs, runner failures, and permission blocks.
- Automatic context repair based on failure classification.

### V0.8 - Structured Contracts and CI Authority

- Promote `requirements.json`, `acceptance.json`, `tasks.json`, and `journeys.json` to first-class contracts.
- Keep Markdown as a review view instead of the only source of structured data.
- Integrate CI as the final verification authority.
- Add lifecycle hooks such as before-tool-use, before-file-write, before-mark-done, and after-commit.

## Non-Goals for the Current Line

- Waygate is not a hosted SaaS service.
- Waygate does not replace code review by humans.
- Waygate does not guarantee correctness without meaningful tests and acceptance criteria.
- Waygate does not yet provide a full sandbox or policy engine for all roles.
