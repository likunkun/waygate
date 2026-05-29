# External Spec Intake And Annotation Policy

This document records the V0.6.1 workflow rules for external spec intake, gate ordering, annotation agents, prompt contracts, and flexible evidence. It is a long-lived workflow policy; `.rrc-controller-*` artifacts remain audit evidence for individual runs.

## Scope

V0.6.1 keeps Waygate Markdown intake compatible while adding supported OpenSpec and Spec Kit import paths. Supported imports produce normalized requirements artifacts and source maps; unsupported, deferred, unreadable, missing, or invalid sources must fail clearly instead of being silently treated as Waygate Markdown.

The same policy also applies to the approval flow around imported specs:

- Requirements, Unit Plan, and Final Acceptance human approvals are the last step in their current phase.
- Controller preflight, schema validation, evidence checks, and enabled annotation passes run before a human review file is presented.
- Agent output can focus human review on risk, but it is never approval evidence by itself.

## External Spec Intake

OpenSpec and Spec Kit imports must produce auditable conversion artifacts before Requirements drafting uses them. The expected artifact set is:

- `import-summary.json`
- `normalized-requirements.json`
- `source-map.json`
- `validation-report.json`

Artifacts may record source paths, hashes, sourceType values, validation issues, and mapping references. They must not record token, password, secret, api_key, signature, database URL, or environment variable values.

## Gate Ordering

Every gate follows this ordering:

1. Generate or collect the candidate body and deterministic inputs.
2. Run controller preflight and schema validation.
3. Run evidence checks for phases that have verifier output.
4. Run the enabled annotation or verification-assist pass.
5. Present the human review file.
6. Accept or reject only through the controller human gate path and content hash.

If an annotation pass is enabled and fails, times out, writes an invalid artifact, or omits its artifact, the phase remains before human approval. The controller may expose a recoverable retry path, but it must not mark the gate approved.

Annotation execution is a controller-side subprocess. It does not appear in the tmux builder pane, drafter pane, or reviewer pane. Before a human gate, the controller pane prints compact Chinese lifecycle lines such as `标注 Agent 开始：角色=requirements_annotation 后端=codex 产物=<path>` and `标注 Agent 完成：角色=requirements_annotation 返回码=0 用时=<duration>`. On failure it prints `标注 Agent 失败：角色=requirements_annotation 错误=<summary> 产物=<path> 用时=<duration>`. The `标注 Agent` label is cyan, `开始` is yellow, `完成` is green, and `失败` is red when `--color always` is used or `--color auto` detects a TTY; `--color never` emits the same Chinese text without ANSI escapes. The controller continues to capture annotation stdout/stderr into the artifact path and events instead of streaming model diagnostics to the terminal. Human-visible controller output no longer uses the legacy bracketed English annotation prefix; structured event types such as `annotation_pass_started`, `annotation_pass_completed`, and `annotation_pass_failed` remain unchanged for audit and automation.

When the fresh artifact matches the current gate body and has `human_language = "zh-CN"`, Waygate writes a bounded annotation review block into the same approval Markdown that Plannotator opens, after `## Human Confirmation`. The block is delimited by `<!-- WAYGATE_ANNOTATION_REVIEW_BEGIN -->` and `<!-- WAYGATE_ANNOTATION_REVIEW_END -->` and headed `## Annotation Agent 风险批注`. It includes the artifact path, `generated_at`, gate hash, summary, issue count, and each issue's severity, category, location, AC/AO/Journey links, message, and evidence refs. Because the block is after the confirmation heading, `gate_body()` and the approval content hash remain stable. Re-entering the gate replaces the existing block instead of appending another copy; stale artifacts and non-Chinese artifacts remove any old review block and are not presented as current review context. The block must not contain the confirmation field names `Status:`, `Content hash:`, or `Confirmed by:`.

Some annotation backends wrap the whole JSON response inside the top-level `summary` string. Waygate normalizes this shape before review by parsing JSON embedded in `summary`, promoting nested `summary` and `issues[]` to the top-level artifact when the top-level `issues[]` is empty, and then counting the promoted issues for terminal output and the Markdown review block.

All human-facing annotation fields must be Simplified Chinese. The prompt requires Chinese `summary`, `issues[].message`, and `non_approval_statement`; taxonomy keys, AC/AO/Journey ids, commands, and file paths may remain in their original form. Normalized artifacts include `human_language = "zh-CN"`. If an annotation backend returns English-only human-facing notes, Waygate rejects that artifact instead of presenting it as current review context. Existing artifacts without the `human_language` marker are treated as stale and rerun before the human gate.

## Annotation Roles

Annotation configuration is role-based. V0.6.1 recognizes these roles:

| Role | Stage | Output Purpose |
| --- | --- | --- |
| `requirements_annotation` | Requirements | Mark high-risk claims, weak evidence, missing mappings, ambiguous acceptance items, infrastructure gaps, `production_readonly_gap`, `runtime_dependency_gap`, and unsupported spec risks. |
| `unit_plan_annotation` | Unit Plan | Mark weak assertions, fake fixtures, broad commands, missing commands, `production_readonly_gap`, `runtime_dependency_gap`, `verification_env_gap`, document gaps, mapping gaps, and descriptive item risks. |
| `final_acceptance_verification_assist` | Final Acceptance / verification-assist backend | Mark weak final evidence during Final Acceptance review, and serve as the default backend for explicit `verification_assist` test cases. |

Each enabled role can use a `claude-code`, `opencode`, or `codex` backend family. Configurable fields include `enabled`, `backend`, `command`, `args`, `env_keys`, `timeout_seconds`, `artifact_path`, `prompt_template`, and `failure_policy`.

Only environment variable keys may be written to state, events, logs, or artifacts. Environment variable values and other secret-like values must be redacted or rejected.

## CLI Enablement

Annotation roles are disabled by default. `init`, `start`, `go`, `drive`, and `run` can enable or update annotation config with these options:

```bash
waygate go V0.6.1 --annotation-agent codex
waygate go V0.6.1 --annotation-agent unit-plan=codex
waygate drive --state-dir .rrc-controller-v0.6.1 --annotation-agent unit-plan=codex --annotation-agent-cmd unit-plan='python3 fake.py'
```

`--annotation-agent BACKEND` enables the same backend for all roles. `--annotation-agent ROLE=BACKEND` enables one role and can be repeated. Role aliases are `requirements`, `unit-plan`, `final-acceptance`, and `all`; backend aliases are `codex`, `claude-code`, `claude`, and `opencode`.

`--no-annotation-agent ROLE|all` disables roles. `--annotation-agent-cmd ROLE='COMMAND ...'` replaces the command and args after `shlex.split`. `--annotation-agent-env-key ROLE=KEY` records only an env key allowlist, never the env value. `--annotation-agent-timeout ROLE=SECONDS` and `--annotation-agent-failure-policy ROLE=block|warn` override role runtime behavior.

The built-in `--annotation-agent codex` default enables `requirements_annotation`, `unit_plan_annotation`, and `final_acceptance_verification_assist` with `command = codex`, `args = ["exec", "--sandbox", "workspace-write", "-o", "{artifact_path}", "Read {prompt_path}. Output only the requested risk-only JSON annotation artifact. Do not approve, skip, modify, or bypass any Waygate gate."]`, `timeout_seconds = 7200`, `failure_policy = block`, and `prompt_template = risk-json-v1`. Existing sessions that contain Waygate's previous built-in Codex annotation args are normalized to this template at runtime; operator-supplied `--annotation-agent-cmd` commands are preserved.

The built-in `--annotation-agent claude-code` template uses `command = claude` with `args = ["--bare", "--no-session-persistence", "-p", "{request}", "--permission-mode", "bypassPermissions"]`. `--bare` and `--no-session-persistence` keep non-interactive annotation runs from inheriting an old Claude Code thinking/session context. Existing sessions that contain Waygate's previous built-in Claude Code annotation args without these two flags are normalized to the new template at runtime; custom command overrides are preserved.

Annotation runner failures are an `annotation runtime blocker`, not a Requirements, Unit Plan, or Final Acceptance contract failure. After fixing the backend CLI, credentials, permissions, or command compatibility, use `waygate unblock --state-dir <state-dir> --reason "<fixed annotation runtime condition>"` to rerun the pending annotation before the human gate. Do not revise Requirements only to recover from an annotation backend failure.

Annotation artifacts record the current gate body as `gate_content_hash`. A Requirements revision must rerun `requirements_annotation` before the revised Requirements human gate is presented. If the gate body changes after annotation, the previous artifact is stale and cannot be treated as current review context; Waygate reruns the enabled annotation role and writes a new artifact with the updated `gate_content_hash`.

## Prompt Contract

All annotation prompts use a shared non-approval prompt contract:

- `Role`: non-approval Waygate risk annotation agent.
- `Inputs`: gate path, `gate_content_hash`, validator summary, state refs, artifact refs, AC/AO/Journey mapping, and output path.
- `Rules`: mark risks only, do not approve, do not modify gates, do not infer unavailable facts, do not reveal secrets, and do not change deterministic verifier status.
- `Output`: write a structured JSON or Markdown artifact to the configured artifact path.
- `Schema`: include stage, role, backend, prompt_template_hash, gate_content_hash, issues, summary, and a non-approval statement.

Stage-specific templates add focused risk categories for Requirements, Unit Plan, and Final Acceptance. The templates must not include approval instructions, status mutation instructions, or gate-bypass language.

## Environment Availability Annotation

Requirements and Unit Plan annotation prompts must explicitly ask the annotation agent to review external runtime availability before the human gate. This is advisory risk context only; it does not approve, reject, or bypass the gate.

For Requirements, annotation agents should flag unclear external access whenever Requirements request remote logs, post-deploy verification, a production page, a production environment, or `production_readonly` evidence. Missing real external access details such as `PRODUCTION_WEB_BASE_URL` or `PRODUCTION_API_BASE_URL` should be marked as `production_readonly_gap`.

For Unit Plans, annotation agents should inspect every `production_readonly` test case and verification command for real production URLs or API endpoints, declared fixture/setup, command working directory, and reachable runtime assumptions. Docker, Docker Compose, Playwright/browser installation, required ports, service dependencies, databases, caches, and external APIs should be called out when the plan only assumes them.

`verification_env` remains a key-name declaration. `verification_env` key names do not prove executable values, deployed services, reachable production environments, or port availability. When a plan only declares env keys but no executable environment or deferred/manual blocker, the annotation artifact should mark the risk as `verification_env_gap` or `runtime_dependency_gap`.

## Non-Approval Semantics

Annotation artifacts cannot set approval fields such as `requirementsAccepted`, `unitPlanAccepted`, or `finalAcceptanceAccepted`. They cannot write `Status: approved`, skip a gate, bypass controller validation, or replace the human confirmation hash.

Approval remains anchored to:

- the human gate file;
- the controller transition;
- the content hash;
- deterministic verifier evidence where applicable.

## Flexible Evidence

`verification.json` can contain strict command rows, descriptive command rows, and explicit agent-assisted test-case rows.

Strict command rows remain deterministic. Their status follows command exit code, assertions, and controller evidence policy.

Descriptive command rows use `evidence_type: descriptive_command`. They still bind to and execute a command, but they also record:

- `description`
- `agent_assisted_judgement`
- `risk_annotations`
- `structured_evidence_refs`
- `human_review_required`

Descriptive rows cannot override a command exit code, hide failed deterministic assertions, or become automatic approval.

Agent-assisted test-case rows use `evidence_type: agent_assisted_case`. They are opt-in at the Unit Plan test-case level through `verification_assist` and do not require or execute `command`. They are intended for verification items where a shell command is not robust enough, such as hostile browser E2E environments, unstable manual entrypoints, or API/service checks that need observation rather than deterministic automation.

A `verification_assist` test case must declare:

- `description`
- `expected`
- optional `agent`
- optional `evidence_required`
- optional `human_review_required`, defaulting to `true`

The controller resolves `agent` to a configured verification-assist backend, defaulting to the existing `final_acceptance_verification_assist` role configuration. If no enabled backend can be resolved, the Unit Plan or Verifier blocks the case instead of silently falling back to a command.

Agent-assisted rows record:

- `evidence_type: agent_assisted_case`
- `status: passed|failed|blocked|needs_human_review`
- `agent_assisted_judgement`
- `risk_annotations`
- `structured_evidence_refs`
- `human_review_required`
- `assist_artifact_path`

`human_review_required` means the evidence must still be reviewed by the human gate. The assist artifact is controller evidence for one test case; it is not an annotation approval, not a gate approval, and cannot overwrite command verifier failures.

Final Acceptance must render deterministic evidence separately from Agent-Assisted Descriptive Evidence and Agent-Assisted Verification Evidence so humans can see which claims are command-proven and which claims rely on agent-assisted observation.

## Final Acceptance

Final Acceptance consumes verifier output, scope audit, Journey evidence, document deliverable status, and optional verification-assist artifacts before human review. The Final Acceptance Evidence Matrix must show deterministic passed, failed, missing, and invalid rows separately from Agent-Assisted Descriptive Evidence and Agent-Assisted Verification Evidence.

Agent-assisted judgement is risk context only and never approval.
