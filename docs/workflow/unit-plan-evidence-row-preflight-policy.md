# Unit Plan Evidence Row Preflight Policy

This document records the workflow rule that closes the gap between Unit Plan test cases and Final Acceptance evidence rows. The rule applies before Unit Plan human review and again after Unit Plan approval.

## Exact Command And AC Closure Contract

Every automated test case in an unfinished unit must declare a `command` that exactly matches one entry in that unit's `verification_commands`.

Every executable command must be a script entrypoint under `scripts/verify/`. Inline shell, direct tool invocations, `bash -c` / `bash -lc`, `python -c`, pipes, chained commands, and ad hoc one-liners are not valid Unit Plan commands. Put the full verification logic into a script file and reference only the script entrypoint, for example:

```bash
bash scripts/verify/<case>.sh
sh scripts/verify/<case>.sh
python3 scripts/verify/<case>.py
python scripts/verify/<case>.py
./scripts/verify/<case>.sh
```

Waygate does not accept substring, fuzzy, or aggregate command coverage for this check. For example, this is invalid:

```json
{
  "test_cases": [
    {"id": "TC-1", "command": "python3 -m pytest tests/test_api.py::test_one -q"}
  ],
  "verification_commands": ["python3 -m pytest tests/test_api.py -q"]
}
```

The test case command must be listed exactly:

```json
{
  "test_cases": [
    {"id": "TC-1", "command": "python3 -m pytest tests/test_api.py::test_one -q"}
  ],
  "verification_commands": ["python3 -m pytest tests/test_api.py::test_one -q"]
}
```

This is intentionally stricter than verifier result matching. Unit Plan approval is where Waygate verifies that every future evidence row can be traced to an explicit planned command.

Waygate also checks approved Requirements AC ids before Unit Plan human review. Every approved AC id must have at least one planned final-valid evidence candidate:

- an exact `test_cases[].command` listed in `verification_commands[]`;
- or an explicit manual evidence case declared as manual layer or `evidence_type = "manual_evidence"` with concrete manual evidence.

If an AC has no such candidate, Unit Plan approval is blocked before the workflow reaches Builder or Final Acceptance.

## Assisted And Manual Evidence

`verification_assist` test cases may omit `command`. They must still satisfy the verification-assist contract: `description`, `expected`, and an enabled verification-assist backend.

`verification_assist` is auxiliary evidence and review context. It cannot statically satisfy approved AC closure by itself, because assisted output can produce `needs_human_review` evidence and Final Scope Audit does not count `needs_human_review` as AC coverage. If an approved AC is mapped only to `verification_assist`, Waygate blocks Unit Plan approval and asks for an exact command or explicit manual evidence case.

Manual evidence does not satisfy automated evidence-row preflight. If a functional, integration, E2E, prototype conformance, golden path, or other automated test case only names manual evidence, Waygate blocks Unit Plan approval until the case declares an exact command or explicitly uses `verification_assist`.

Pure manual review cases should declare a manual layer, such as `layer = "manual"`, or `evidence_type = "manual_evidence"`.

## Gate Ordering

The evidence-row and AC final-evidence-candidate preflights run in two places:

- after Unit Plan draft generation, before annotation and before human review;
- after Unit Plan human approval, before `unitPlanAccepted` is persisted and before the workflow advances.

The script-entry command policy runs in the same two places. Requirements draft confirmation does not parse or approve executable commands, because executable commands are introduced by Unit Plan `Controller State Patch` data.

This preserves the V0.6.1 approval-ordering rule: human approval is the last step in the phase, and deterministic validation is not deferred until Final Acceptance.

## Final Scope Audit Recovery

Final Scope Audit can still find missing AC evidence when a historical or legacy plan predates this rule, or when runtime evidence is `failed`, `missing`, `invalid`, `blocked`, or `needs_human_review`. If Waygate is blocked at `FINAL_WALKTHROUGH_PREPARE` because Final Scope Audit reports missing acceptance-criterion evidence rows, the recovery route is Unit Plan revision:

```bash
waygate revise --gate unit-plan --state-dir <state-dir> --reason "repair missing evidence rows"
```

This route preserves Requirements approval. The Unit Plan revision prompt includes the missing AC ids, the Final Scope Audit artifact paths, and a reminder to use exact `test_cases[].command` to `verification_commands[]` matches or explicit manual evidence for manual-only closure.

Requirements revision is only needed if the approved AC contract itself must change.
