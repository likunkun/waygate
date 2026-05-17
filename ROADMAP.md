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
- Route Requirements Plannotator review to the review bundle when it exists, while keeping `approvals/requirements-and-acceptance.md` as the approval gate and source of approval status.
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

### V0.6.1 - External Spec Intake

Goal: add explicit import paths for external spec ecosystems after Waygate Markdown intake is stable.

Planned work:

- Design import contracts for OpenSpec and Spec Kit.
- Add parsers, validation, and conversion artifacts for supported external formats.
- Preserve clear unsupported/deferred errors for formats that are detected but not enabled.

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
