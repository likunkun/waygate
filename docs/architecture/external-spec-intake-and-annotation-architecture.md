# External Spec Intake And Annotation Architecture

This document records the V0.6.1 module boundaries for OpenSpec and Spec Kit intake, role-based annotation config, prompt templates, runner selection, and flexible verifier evidence.

## Module Boundaries

| Area | Modules | Responsibility |
| --- | --- | --- |
| Source classification | `workflow_controller/spec_sources.py` | Classify Waygate Markdown, OpenSpec, Spec Kit, unsupported, deferred, missing, unreadable, and invalid sources. |
| CLI flow | `workflow_controller/cli.py` | Route `init`, `start`, and `go --spec <path>` through the same intake contract. |
| Requirements context | `workflow_controller/requirements_dialogue_brief.py`, `workflow_controller/prompts/requirements.py`, `workflow_controller/steps/requirements.py` | Inject source metadata and conversion artifact paths into the Requirements Dialogue Brief and Requirements Draft prompt. |
| Annotation config and prompts | `workflow_controller/annotation_agents.py` | Normalize role-based annotation config, select backend family, render prompt templates, validate annotation artifacts, and reject approval-like payloads. |
| Gate orchestration | `workflow_controller/rrc_controller.py` | Enforce gate ordering before human review and run annotation or verification-assist passes. |
| Verifier runtime | `workflow_controller/rrc_real_runtime.py`, `workflow_controller/steps/builder.py` | Execute configured verification commands and map results into `verification.json` evidence rows. |
| Evidence validation | `workflow_controller/gates/validators/__init__.py` | Validate strict command rows and descriptive command rows without relaxing existing evidence schema checks. |
| Final display | `workflow_controller/gates/generators/__init__.py` | Render the Final Acceptance Evidence Matrix and Agent-Assisted Descriptive Evidence separately. |

## External Spec Intake Contract

OpenSpec and Spec Kit imports write conversion artifacts under the controller artifact tree. The contract keeps source metadata separate from approval state:

- source path and hash identify the imported input;
- `sourceType` distinguishes OpenSpec, Spec Kit, Waygate Markdown, unsupported, and deferred inputs;
- validation output records missing fields or unsupported structures;
- source maps link imported sections to normalized requirements, acceptance candidates, assumptions, non-goals, ACs, and Journey references.

Imported specs never approve Requirements. They only feed Requirements drafting and human review.

## Role-Based Annotation Config

The role-based annotation config supports:

- `requirements_annotation`
- `unit_plan_annotation`
- `final_acceptance_verification_assist`

Each role can select `claude-code`, `opencode`, or `codex` as a backend family. The normalized config records command, args, custom env key allowlist, timeout, artifact path, prompt template, and failure policy. At subprocess launch time, Waygate also inherits standard proxy keys present in the parent process (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, and lowercase variants). State and artifacts record env keys only, not values.

`annotation_agents.py` owns built-in backend templates and legacy migration. The Codex template is normalized away from the removed `--ask-for-approval never` flag. The Claude Code template includes `--bare` and `--no-session-persistence` so subprocess annotation runs do not inherit stale interactive thinking/session context; persisted sessions with the old built-in Claude args migrate during status/config normalization.

Backend unavailable behavior is explicit. The controller must report the selected backend or command as unavailable instead of silently falling back to another backend family.

## Prompt Template Registry

The prompt template registry is responsible for stable prompt contracts, stage-specific risk taxonomies, and template hashes. Prompts must include:

- stage and role;
- input refs and validator summary;
- AC/AO/Journey mapping;
- evidence refs and output artifact path;
- non-approval rules;
- environment availability checklist;
- output schema.

The templates are risk-only. They cannot ask an agent to approve a gate, change approval state, or rewrite deterministic verifier status.

The environment availability checklist is rendered by `workflow_controller/annotation_agents.py`. It directs Requirements and Unit Plan annotation agents to flag `production_readonly` plans that lack real external URL/API endpoint details, including `PRODUCTION_WEB_BASE_URL` and `PRODUCTION_API_BASE_URL`, and to call out missing Docker, Docker Compose, Playwright/browser, port, service, database, cache, and external API readiness. It also states that `verification_env` key names do not prove executable values or reachable environments.

## Verification Evidence Schema

`verification.json` keeps existing strict command row behavior and adds two explicit flexible evidence shapes. Strict command rows remain backwards compatible: old rows do not need agent-assisted fields and continue to be validated by the existing required evidence fields.

Descriptive command rows represent "a command still ran, but the row also carries human-review risk context." They add:

- `evidence_type: descriptive_command`
- `description`
- `agent_assisted_judgement`
- `risk_annotations`
- `structured_evidence_refs`
- `human_review_required`

Strict command rows and descriptive command rows both retain command, result_index, returncode, status, artifact refs, layer, environment, real entrypoint, and runtime error fields. Descriptive fields never override command exit code or deterministic policy status.

Agent-assisted test-case rows represent "no command ran; the Unit Plan explicitly opted this test case into verification assist." They add:

- `evidence_type: agent_assisted_case`
- `description`
- `status: passed|failed|blocked|needs_human_review`
- `agent_assisted_judgement`
- `risk_annotations`
- `structured_evidence_refs`
- `human_review_required`
- `assist_artifact_path`

The Unit Plan validator accepts `command` or `verification_assist`, but not both on the same test case. `verification_assist` must include `description` and `expected`, and it must resolve to an enabled agent config. By default, resolution reuses `final_acceptance_verification_assist`; a case-level `agent` can name a supported role or backend when the matching config exists.

The verifier runtime renders a verification-assist case prompt through `annotation_agents.py`, invokes the configured subprocess backend, normalizes the returned JSON artifact, and merges the result into `verification.json`. Runtime failures produce a blocked agent-assisted row and cannot override failed deterministic command rows.

## Final Acceptance Evidence Matrix

The Final Acceptance Evidence Matrix renders deterministic rows first. Agent-assisted descriptive rows are rendered in a separate Agent-Assisted Descriptive Evidence table. Commandless `agent_assisted_case` rows are rendered in a separate Agent-Assisted Verification Evidence table. This keeps passed, failed, missing, and invalid command evidence separate from human-review risk context and from opt-in agent-assisted verification evidence.

The renderer can display agent-assisted judgement, risks, structured evidence refs, and `human_review_required`, but it must not display these rows as auto approved.

## Completion Evidence

V0.6.1 completion evidence comes from:

- targeted pytest for spec intake, annotation config/prompts, flexible evidence, and docs;
- `git diff --check`;
- full `python3 -m pytest workflow_controller/tests -q`;
- optional Debian package evidence only when a later release request makes packaging required.
