# Staged Requirements Package Architecture

This document records the V0.6.2 architecture boundaries for Staged Requirements Package. It covers the helper module, checkpoint prompts, stage runner, controller orchestration, final gate assembly, validators, Unit Plan prompt inheritance, and revision routing.

## Module Boundaries

| Area | Modules | Responsibility |
| --- | --- | --- |
| Package metadata | `workflow_controller/requirements_package.py` | Defines `REQUIREMENTS_PACKAGE_VERSION`, stage ordering, action maps, artifact filenames, hash helpers, artifact completeness checks, and downstream invalidation. |
| Prompt rendering | `workflow_controller/prompts/requirements_package.py` | Renders Requirements Scope, Product Design Brief, Technical Architecture Brief, and Requirements Test Strategy Brief prompts with upstream artifact path/hash inputs. |
| Stage execution | `workflow_controller/steps/requirements_package.py` | Runs one checkpoint, writes the prompt, stage artifact, summary JSON, and updates `requirementsPackage.artifacts`. |
| State routing | `workflow_controller/state_machine/actions.py` | Maps staged Requirements steps to `run_requirements_scope_drafter`, `run_requirements_product_design_brief`, `run_requirements_architecture_brief`, `run_requirements_test_strategy_brief`, and `assemble_requirements_package`. |
| Controller orchestration | `workflow_controller/rrc_controller.py` | Advances one checkpoint per `run_once()`, records `requirements_package_stage_generated`, assembles the final gate, runs preflight, and preserves annotation ordering. |
| Gate generation | `workflow_controller/gates/generators/__init__.py` | Builds the final `requirements-and-acceptance.md` body from four checkpoint artifacts and records artifact hashes. |
| Gate validation | `workflow_controller/gates/validators/__init__.py` | Validates staged package consistency, hash rows, appendices, legacy 4.9 compatibility, and Unit Plan infrastructure matrix requirements. |
| Unit Plan handoff | `workflow_controller/prompts/unit_plan.py` | Injects staged package artifact path/hash/status metadata into the Unit Plan prompt and requires inherited AC, Journey, design, architecture, test strategy, E2E, UI, and risk obligations. |

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

## Flow

The staged flow uses these controller steps:

1. `REQUIREMENTS_SCOPE_DRAFT`
2. `REQUIREMENTS_PRODUCT_DESIGN_BRIEF`
3. `REQUIREMENTS_TECH_ARCH_BRIEF`
4. `REQUIREMENTS_TEST_STRATEGY_BRIEF`
5. `REQUIREMENTS_PACKAGE_ASSEMBLE`
6. `WAITING_REQUIREMENTS_ACCEPTANCE`

Each checkpoint runner writes an artifact under the controller artifact tree and updates the state record through the package helper. The controller advances only one step per `run_once()` so timeout, retry, and review evidence stay scoped to the current checkpoint.

## Final Gate Assembly

Final assembly reads the four checkpoint artifacts, recalculates their hashes, compares them with state, and renders one approval gate. The gate contains an artifact hash table and appendices for the four checkpoint bodies.

`validate_staged_requirements_package_consistency` checks that:

- all required appendices are present;
- every checkpoint has a hash row;
- file hashes match the recorded state;
- obvious AC, Journey, or AO conflicts between checkpoint artifacts are rejected.

In staged package mode, Requirements validation no longer requires the legacy full `## 4.9 目标项目基础设施信息` section in the final gate. Legacy state keeps the existing 4.9 requirement.

## Unit Plan Prompt And Validator

The Unit Plan prompt consumes the final Requirements gate plus `requirementsPackage` metadata. In staged mode it must render artifact path/hash/status records for:

- scope
- product_design
- architecture
- test_strategy

The Unit Plan prompt requires inherited AC, Journey, Product Design, Technical Architecture, Test Strategy, E2E method, UI obligations when explicitly declared, risk obligations, and document deliverables.

The Unit Plan validator requires an `Infrastructure / Execution Context Matrix` that covers repository, runtime, debugging, reference environment, documentation, architecture/interface, and dependency facts. This is the architecture endpoint for the V0.6.2 shift away from overloading Requirements `4.9`.

## Revision Routing

Requirements revision in staged mode clears Requirements and Unit Plan approval state, records feedback, marks scope and downstream stages stale, and routes back to `REQUIREMENTS_SCOPE_DRAFT`.

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
