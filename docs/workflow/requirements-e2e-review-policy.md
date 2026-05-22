# Requirements E2E Review Policy

This policy belongs to V0.6.2 Strict Test Presence. It moves real E2E/browser acceptance review into the Requirements gate so humans approve the method before Unit Plan and implementation.

## Trigger

Requirements approval requires `## 4.6 E2E 测试方法与前置依赖矩阵（E2E Test Method & Prerequisite Matrix）` when any of these are true:

- an AC declares `verification: e2e`;
- an active Journey declares `Verification Layer = e2e`;
- Test Strategy explicitly requires Playwright, browser, end-to-end, or E2E verification;
- a Web, prototype, or UI contract requires real browser proof.

If text requires E2E but no AC or active Journey is mapped to E2E, the gate is invalid. The drafter must map the E2E review to a specific AC or Journey before approval.

## Required Columns

The 4.6 matrix uses fixed columns:

| AC / Journey | E2E Method | Real Entrypoint | User Steps | Fixture / Test Data / Setup | Verification Command | Environment Kind | Required Env / Dependencies | Mock Policy | Expected Assertions | Human Review Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

Every E2E AC and every active E2E Journey needs a row. A row may cover both when `AC / Journey` lists both IDs.

## Blocking Rules

Controller preflight blocks approval when 4.6 is missing, rows do not cover required AC/Journey IDs, fields are empty or placeholders, commands are generic, entrypoints are not real runtime entrypoints, user steps or fixture/setup are vague, or expected assertions are weak.

`Environment Kind` must be `local_real` or `production_readonly`. `Mock Policy` must not allow core business API mocks/stubs. Screenshots and human observation may be supporting artifacts, but they cannot be the only assertion.

## Unit Plan Inheritance

Unit Plan must preserve the approved 4.6 method, real entrypoint, fixture/setup, command dependencies, environment kind, mock policy, and assertion intent. Weakening those details requires a Requirements change request and a new Requirements approval.
