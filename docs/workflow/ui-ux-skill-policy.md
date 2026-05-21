# UI/UX Skill Policy for V0.6.0k

This policy is the long-lived workflow rule for UI, Web, clickable prototype, prototype evidence, and production UI consistency work.

## Required Skill

- Use `ui-ux-pro-max` for UI/Web/prototype work.
- Requirements prompts, Unit Plan prompts, Builder prompts, and UI Design Brief artifacts must name `ui-ux-pro-max` explicitly when the work involves visible interfaces, browser routes, clickable prototypes, prototype evidence, or production UI consistency verification.
- `waygate doctor` reports `skill_recommendations.ui_ux_design` as `ok` only when `ui-ux-pro-max` is installed.

## `frontend-design` Boundary

- `frontend-design` can be used as an optional helper for new visual exploration or local visual polish.
- `frontend-design` cannot replace `ui-ux-pro-max` for existing product UI, prototype conformance, production UI consistency, or prototype fidelity work.
- When both skills are installed, doctor and prompt contracts prefer `ui-ux-pro-max`.

## Required UI Inventory

Before designing or validating a prototype, the agent must inventory the real UI sources that define product consistency:

- routes and real browser entry points;
- DOM/components and component ownership;
- existing page structure, navigation, dialogs, drawers, panels, forms, and selectors;
- screenshots, historical designs, product docs, or reference environments;
- interaction, accessibility, layout, and obstruction risks.

This inventory must happen before a new prototype design is proposed. A prototype based only on prose is not enough for existing-product consistency work.

## Verification Expectations

UI/Web/prototype test cases must preserve `ui-ux-pro-max` checks in the Unit Plan and Builder work:

- interaction behavior;
- accessibility and keyboard/focus behavior where applicable;
- layout, visual density, component order, and responsive constraints;
- obstruction checks for fixed headers, overlays, modals, drawers, badges, and loading masks;
- prototype and production screenshots when the prototype fidelity policy requires visual evidence.

`ui-ux-pro-max` works alongside the existing prototype fidelity policy in `docs/workflow/prototype-fidelity-policy.md`; it does not replace the L1-L4 evidence rules.

## Doctor Behavior

- Only `ui-ux-pro-max` installed: `ui_ux_design` is `ok`.
- Only `frontend-design` installed: `ui_ux_design` is `warning` with a manual action to install or use `ui-ux-pro-max`.
- Both installed: `ui_ux_design` is `ok matched=ui-ux-pro-max`.
