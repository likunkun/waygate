# Requirements E2E Review Policy

This policy belongs to V0.6.3 Strict Test Presence after the original V0.6.2 scope was merged into V0.6.3. It was tightened in V0.6.0m for golden-path Unit Plan preflight. Under V0.6.2 Staged Requirements Package, the Requirements Test Strategy Brief is the checkpoint that carries this review before Unit Plan and implementation; the Unit Plan then inherits the method through its test cases and `Infrastructure / Execution Context Matrix`.

## Trigger

Requirements approval requires `## 4.6 E2E 测试方法与前置依赖矩阵（E2E Test Method & Prerequisite Matrix）` when any of these are true:

- an AC declares `verification: e2e`;
- an active Journey declares `Verification Layer = e2e`;
- Test Strategy explicitly requires Playwright, browser, API/service end-to-end, or E2E verification;
- a Web or UI contract requires real browser proof.

If text requires E2E but no AC or active Journey is mapped to E2E, the gate is invalid. The drafter must map the E2E review to a specific AC or Journey before approval.

Prototype-only artifact review does not by itself trigger 4.6 real E2E command validation. It is handled through the prototype manifest and Unit Plan prototype conformance contract unless the Requirements also require real browser or production E2E proof.

## Required Columns

The 4.6 matrix uses fixed columns:

| AC / Journey | E2E Method | Real Entrypoint | User Steps | Fixture / Test Data / Setup | Verification Command | Environment Kind | Required Env / Dependencies | Mock Policy | Expected Assertions | Human Review Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

Every active E2E Journey needs a row. An E2E AC needs its own row only when it is not already covered by a row for an active E2E Journey that maps to that AC.

The Journey table may use canonical headers or accepted aliases such as `Journey id`, `User steps`, and `Linked AC`. Support Journey layers such as `static`, `regression`, and `prerequisite` are valid for non-E2E journeys, but they do not create 4.6 E2E review obligations.

## Blocking Rules

Controller preflight blocks approval when 4.6 is missing, rows do not cover required AC/Journey IDs, fields are empty or placeholders, command intent is generic, entrypoints are not real runtime entrypoints, user/API/service steps or fixture/setup are vague, or expected assertions are weak.

`Verification Command` is a Requirements-stage command intent, command family, or runner intent. It must name enough tool/component/verification intent for Unit Plan to produce the exact command later, but it is not the final executable command. Values such as `pytest`, `playwright test`, `待 Unit Plan 补充`, or vague “test later” text are invalid.

`Environment Kind` must be `local_real` or `production_readonly`. `Mock Policy` must not allow core business API mocks/stubs. Screenshots and human observation may be supporting artifacts, but they cannot be the only assertion.

## Unit Plan Inheritance

Unit Plan must preserve the approved 4.6 method, real entrypoint, fixture/setup, command intent, environment kind, mock policy, and assertion intent, then turn them into concrete test cases, exact commands, fixture scripts, and evidence rows. Weakening those details requires a Requirements change request and a new Requirements approval.

In V0.6.2 staged mode, these details are inherited from the Requirements Test Strategy Brief and the final assembled Requirements package artifact hashes. The detailed project infrastructure inventory is no longer duplicated as a full Requirements `4.9` responsibility; it is expanded in the Unit Plan `Infrastructure / Execution Context Matrix`, where execution commands, local runtime, dependencies, documentation, and debugging facts are closer to the implementation plan.

For V0.6.0m, Unit Plan approval also blocks any `golden_path: true` test case unless it satisfies all of these conditions:

- `layer` is `e2e`;
- `environment_kind` is `local_real` or `production_readonly`;
- `entrypoint` or `real_entrypoint` names the real route, URL, CLI, API endpoint, or service endpoint;
- fixture/setup or test data is concrete;
- `command` is executable and appears in `verification_commands`;
- `expected` contains concrete machine-checkable assertions;
- core business API mocks/stubs are not used.

E2E does not mean browser-only. UI/Web golden paths normally use browser E2E, while API-only or service-only projects can use pytest/API/service E2E against real local services or read-only production endpoints.
