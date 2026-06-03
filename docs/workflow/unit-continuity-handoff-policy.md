# Unit Continuity Handoff Policy

This document records the V0.6.2d Unit Continuity Gate. It prevents multi-unit plans from relying on vague prerequisites such as "environment ready" and makes producer unit evidence a hard preflight for downstream Builder execution.

## Unit Plan Gate

Single-unit plans may omit handoff metadata. Multi-unit plans that declare `depends_on` or handoff metadata must include:

- `## 单元连贯性摘要`, explaining in human-readable Chinese what each upstream unit produces and how downstream units consume it.
- `## Handoff Matrix`, with upstream unit, downstream unit, produced artifacts/readiness, consumed inputs, evidence path, and failure route.
- Controller State Patch unit fields: `depends_on` and `handoff`.

The `handoff` object uses this minimal schema:

```json
{
  "human_summary": "unit-01 exports normalized catalog JSON for unit-02 importer tests",
  "produces": ["normalized catalog JSON"],
  "requires": [],
  "ready_checks": ["TC-U1-EXPORT"],
  "evidence_artifacts": ["export.json"]
}
```

Downstream units list upstream ids in `depends_on` and name the consumed inputs in `handoff.requires`. Each required input must match a produced output from at least one dependency, and each declared dependency must contribute at least one required input. This supports split handoffs, such as one upstream unit producing a schema while another produces seed fixtures for the same downstream unit. `ready_checks` must map to a test case id, test case command, expected assertion, or an exact `verification_commands[]` entry. `done_when` must describe observable completion, not a placeholder.

## Validator Rejections

The Unit Plan validator rejects:

- missing or unknown dependencies;
- circular dependencies;
- dependency participants missing `handoff`;
- vague summaries such as `environment ready`, `ready`, `done`, or `环境就绪`;
- downstream `requires[]` values not produced by dependencies;
- missing `ready_checks` or `evidence_artifacts` for planned producer/consumer units;
- ready checks that do not map to commands or test cases.

These checks run in the same Unit Plan preflight and approval revalidation path as the existing test case, command, E2E, Journey, and document deliverable validators.

## Runtime Evidence

When a unit declares handoff metadata, the Verifier writes:

```text
artifacts/<unit-id>/handoff-evidence.json
```

The file records `passed`, `human_summary`, `produces`, `requires`, `ready_checks`, resolved evidence artifacts, and structured issues. Missing declared artifacts or failed/unmapped ready checks make the producer unit verification fail.

Before Builder starts a downstream unit, the controller checks every `depends_on` unit for a passed `handoff-evidence.json`. Missing, invalid, failed, or mismatched handoff evidence blocks the downstream unit with:

```json
{
  "blockedContext": {
    "category": "unit_handoff"
  }
}
```

The blocked guidance explains in Chinese which upstream evidence is missing or failed. If the dependency contract is wrong, the recovery route is `waygate revise --gate unit-plan --reason ...`; if the upstream unit failed to produce evidence, rerun or repair the upstream unit so the verifier can produce a passed handoff artifact.
