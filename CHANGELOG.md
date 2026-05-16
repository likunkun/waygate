# Changelog

All notable project changes should be recorded here.

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
- Routed Requirements Plannotator review to the review bundle while keeping approval on `approvals/requirements-and-acceptance.md`.
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
