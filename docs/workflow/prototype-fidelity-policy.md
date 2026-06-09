# Prototype Fidelity Policy

Waygate treats UI/Web prototypes as acceptance contracts when Requirements mark a prototype surface as required. Final Acceptance cannot rely only on route-loaded or text-visible E2E assertions for those surfaces.

## Fidelity Levels

| Level | Name | Required Evidence |
| --- | --- | --- |
| L1 | `visual_evidence` | Prototype screenshot, production screenshot, viewport, entrypoint, and action path. |
| L2 | `structural_interaction` | L1 plus assertions for layout/structure/order and real clicks; interactive surfaces also need an interaction screenshot and obstruction checks for fixed headers, badges, modals, drawers, and overlays. |
| L3 | `screenshot_regression` | L1/L2 plus a screenshot regression result with threshold or diff artifact. |
| L4 | `pixel_exact` | L1/L2 plus strict screenshot/pixel evidence for brand, logo, or fixed-size high-fidelity components. |

Default required UI/Web prototype surfaces use L1 + L2. Required browser-visible surfaces that are linked to an active E2E Journey, an E2E AC, or a golden-path prototype test default to L3 `screenshot_regression`; this includes route, page, dialog, drawer, panel, and form surfaces. L4 `pixel_exact` applies only when Requirements or the manifest explicitly declares it.

Every required `surface_contracts[]` row must be a user-task contract, not only a visual label. It must include `actor`, `task_start`, `main_business_object`, `success_endpoint`, `page_states`, `click_path`, AC mapping, Journey mapping when the Requirements define Journeys, and real `implementation_targets`.

## Unit Plan Contract

Prototype conformance test cases must include `prototype_conformance`, `prototype_surfaces` when applicable, `production_targets`, real `user_steps`, concrete visual/layout/interaction `expected` assertions, and a `visual_evidence_plan`.

The evidence plan must open the real production entrypoint and cover the manifest click path for the target surface. It must include:

- `prototype_screenshot`
- `production_screenshot`
- `viewport`
- `entrypoint`
- `action_path`
- `interaction_screenshot` for interactive surfaces
- screenshot regression or pixel tolerance fields for L3/L4

## Verifier Markers

Prototype conformance E2E commands should emit:

```text
PROTOTYPE_SCREENSHOT: <path>
PRODUCTION_SCREENSHOT: <path>
INTERACTION_SCREENSHOT: <path>
VISUAL_EVIDENCE: {"viewport":"desktop 1440x900","entrypoint":"/route","action_path":["Open /route","Click target"],"fidelity_level":"structural_interaction"}
```

The Verifier records these in `visual_evidence_refs` while preserving legacy `screenshot_refs`.

## Final Acceptance

Final Acceptance renders the Prototype Conformance Matrix and Visual Prototype Evidence sections and writes `artifacts/final-acceptance/prototype-conformance-matrix.json`. A required surface is blocked when visual evidence is missing, a key target is obstructed, or required L3/L4 fidelity lacks screenshot regression or pixel evidence.

The evidence layer requirement is target-aware:

- Browser production targets still require real E2E evidence. This includes `kind=route`, any target path that starts with `/`, and surface kinds `route`, `page`, `component`, `dialog`, `drawer`, `panel`, or `form`.
- Non-browser controller or workflow review targets with `kind=module`, `artifact`, `state`, or `events` and `surface kind=other` may use passed `integration` evidence from a non-mock environment such as `local_real`, as long as the row has no core API mock, no runtime errors, and complete visual evidence for the declared fidelity level.

Artifact-local prototype review evidence must not be upgraded or mislabeled as browser E2E. Browser surfaces are not relaxed by this exception.
