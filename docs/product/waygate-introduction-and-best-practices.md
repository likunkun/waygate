# Waygate Introduction and Best Practices

[中文](waygate-introduction-and-best-practices.zh-CN.md) | [README](../../README.md)

This document is the V0.6.0e introduction material for explaining Waygate to new collaborators. It is Markdown source material only; no `.pptx` file is generated in this version.

## The Problem Waygate Solves

AI coding agents can produce useful work quickly, but long chat-driven delivery often fails at process boundaries. Requirements drift, unit plans skip difficult acceptance paths, tests prove only static checks, and final answers describe completion without durable evidence.

Waygate adds a controller loop around AI coding work. The loop separates decisions from execution: humans approve requirements and final acceptance, agents draft and implement, and verifier evidence records what actually ran.

## Roles and Gates

- Requirements: the reviewed contract for scope, acceptance criteria, journeys, infrastructure facts, and non-goals.
- Unit Plan: the execution plan that maps each acceptance criterion to test cases, commands, evidence, and the current unit.
- Builder: the implementation role for the approved unit only.
- Refiner: the CodeSimplifier role that improves clarity and maintainability without changing scope.
- Reviewer: the review role that looks for defects, behavioral regressions, and missing tests.
- Verifier: the evidence role that runs planned commands and records structured results.
- Final Acceptance: the human-facing closure gate that reviews evidence, scope, and rework routing.

## Fact Sources

Waygate is useful because it treats files as facts, not chat memory:

- `session.json` is the controller state source.
- `events.jsonl` is the event history.
- `approvals/` contains human gate confirmation files.
- `artifacts/` contains prompts, runs, verifier output, reviewer output, refiner output, and related evidence.

Human-readable files such as `README.md`, `task_plan.md`, `progress.md`, and `findings.md` help collaborators understand the project, but controller closure depends on approved gates and verifier evidence.

## Recommended Workflow

1. Start from a clear target or Waygate Markdown spec.
2. Review Requirements before any implementation. Check scope, acceptance criteria, journeys, infrastructure facts, and non-goals.
3. Review Unit Plan before Builder runs. Check that test cases map to ACs, AOs, journeys, commands, and evidence.
4. Let Builder work only inside the current unit.
5. Use Refiner and Reviewer feedback as implementation-quality checks, not as approval substitutes.
6. Run Verifier commands and inspect evidence rows.
7. Use Final Acceptance to accept, reject, or route defects to the right upstream gate.

For UI/UX or Web targets, the Requirements review must include prototype evidence, clickable webpage prototype access, page states, core click paths, real implementation targets, and AC mapping. The current V0.6.0e unit is CLI/Markdown work and creates no business UI prototype.

## Common Misuse

- Treating a natural-language agent summary as proof. Use verifier evidence instead.
- Expanding the current unit because a later backlog item is nearby. Keep V0.6.1 and V0.6.2 work in future scope until explicitly approved.
- Letting static checks replace behavior tests. Static checks are useful, but they do not prove user journeys.
- Editing approved Requirements during implementation. Use a change request and return to the proper gate.
- Assuming installed tools are the tools being executed. Run `waygate doctor` and check PATH shadow warnings.

## Best Practices

- Keep each target small enough that acceptance criteria can be reviewed and verified.
- Prefer explicit commands over vague evidence descriptions.
- Keep secrets out of prompts, logs, docs, and artifacts.
- Use `waygate doctor` before diagnosing runner failures.
- Keep Claude Code, Codex, Plannotator, and agent skills as optional runtime dependencies unless the approved unit says otherwise.
- Package docs with the Debian build so installed users have the same operations and product guidance as source users.

## 10-12 Page PPT Outline

This is an outline for a future talk deck. V0.6.0e does not generate a PPT or `.pptx` deliverable.

1. Title: Waygate as a workflow control surface for AI coding delivery.
2. Problem: why long AI coding chats lose scope, evidence, and state.
3. Core idea: gates, units, evidence, and human approval.
4. Requirements gate: scope, ACs, journeys, infrastructure facts, non-goals.
5. Unit Plan gate: test cases, commands, layers, and traceability.
6. Builder, Refiner, Reviewer: separate implementation, simplification, and review responsibilities.
7. Verifier and Final Acceptance: evidence rows, scope audit, and rejection routing.
8. Fact sources: `session.json`, `events.jsonl`, `approvals/`, and `artifacts/`.
9. Recommended environment: Python, pytest, tmux runners, Plannotator port `20000`, skills, and Debian packaging.
10. Common failure modes and how Waygate prevents them.
11. Example walkthrough: from `waygate go V1.0` to final acceptance.
12. Adoption checklist: install, doctor, docs, runner choice, and review habits.
