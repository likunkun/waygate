# Changelog

All notable project changes should be recorded here.

## 0.6.1a

- Added Blocked Assist for controlled diagnosis of `status=blocked` workflows, with summary artifacts, human-confirmed `human_reason`, and explicit controller-selected recovery routes.
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
