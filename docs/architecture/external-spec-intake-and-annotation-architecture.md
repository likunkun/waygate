# External Spec Intake And Annotation Architecture

This document records the V0.6.1 module boundaries for OpenSpec and Spec Kit intake, the V0.6.2e package-directory intake extension, role-based annotation config, prompt templates, runner selection, flexible verifier evidence, and the current subprocess-only annotation runtime.

Current note: annotation uses subprocess only. `WAYGATE_ANNOTATION_TMUX` is a deprecated no-op retained for old shell environments; it does not create an annotation pane. Persisted audit data remains env key-only.

## Module Boundaries

| Area | Modules | Responsibility |
| --- | --- | --- |
| Source classification | `workflow_controller/spec_sources.py` | Classify Waygate Markdown, OpenSpec/OpenAPI, `open-spec-package`, Spec Kit feature packages, unsupported, deferred, missing, unreadable, and invalid sources. |
| CLI flow | `workflow_controller/cli.py` | Route `init`, `start`, and `go --spec <path>` through the same intake contract. |
| Requirements context | `workflow_controller/requirements_dialogue_brief.py`, `workflow_controller/prompts/requirements.py`, `workflow_controller/steps/requirements.py` | Inject source metadata and conversion artifact paths into the Requirements Dialogue Brief and Requirements Draft prompt. |
| Annotation config and prompts | `workflow_controller/annotation_agents.py` | Normalize role-based annotation config, select backend family, render prompt templates, validate annotation artifacts, and reject approval-like payloads. |
| Gate orchestration | `workflow_controller/rrc_controller.py` | Enforce gate ordering before human review and run annotation or verification-assist passes. |
| Verifier runtime | `workflow_controller/rrc_real_runtime.py`, `workflow_controller/steps/builder.py` | Execute configured verification commands and map results into `verification.json` evidence rows. |
| Evidence validation | `workflow_controller/gates/validators/__init__.py` | Validate strict command rows and descriptive command rows without relaxing existing evidence schema checks. |
| Final display | `workflow_controller/gates/generators/__init__.py` | Render the Final Acceptance Evidence Matrix and Agent-Assisted Descriptive Evidence separately. |

## External Spec Intake Contract

OpenSpec, Open Spec package, and Spec Kit imports write conversion artifacts under the controller artifact tree. The contract keeps source metadata separate from approval state:

- source path and hash identify the imported input;
- `sourceType` distinguishes OpenSpec, Spec Kit, Waygate Markdown, unsupported, and deferred inputs;
- validation output records missing fields or unsupported structures;
- source maps link imported sections to normalized requirements, acceptance candidates, assumptions, non-goals, ACs, and Journey references.

Imported specs never approve Requirements. They only feed Requirements drafting and human review.

For `sourceType=open-spec-package`, `spec_sources.py` treats the directory as the source. The classifier requires `01-requirements.md` plus at least one supporting package document (`02-specification.md`, `03-technical-solution.md`, `04-storage-design.md`, or `08-stage-handoff.md`). The converter hashes directory contents, writes the directory path to `requirementsSpec.path`, records package entrypoints in `import-summary.json`, `source-map.json`, and `validation-report.json`, and extracts normalized requirements primarily from `01-requirements.md`.

For Spec Kit directories, arbitrary feature directory names are accepted only when `spec.md` has a same-directory companion such as `plan.md`, `tasks.md`, `research.md`, `data-model.md`, `quickstart.md`, or `contracts/`. Named legacy `spec-kit` / `specify` feature directories and `feature.specify.md` file imports remain compatible. `.specify` workspace/tool roots without a feature entrypoint are rejected with guidance to pass `specs/<feature>/` or a concrete `spec.md`.

## Role-Based Annotation Config

The role-based annotation config supports:

- `requirements_annotation`
- `unit_plan_annotation`
- `final_acceptance_verification_assist`

Each role can select `opencode` or `codex` as a declared backend family. The normalized config records command, args, custom env key allowlist, timeout, artifact path, prompt template, and failure policy. At subprocess launch time, Waygate also inherits standard proxy keys present in the parent process (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, and lowercase variants). State and artifacts record env keys only, not values.

`annotation_agents.py` owns built-in backend templates and legacy migration. The Codex template is normalized away from the removed `--ask-for-approval never` flag. The OpenCode template is `opencode run <risk-only request>`. Persisted sessions with Waygate's old built-in Claude annotation config migrate to the OpenCode template. Custom commands are preserved, but a custom config must still declare `backend=opencode` or `backend=codex`; `backend=claude-code` is rejected. Claude Code remains available only through normal workflow runners such as `tmux-claude`.

Backend unavailable behavior is explicit. The controller must report the selected backend or command as unavailable instead of silently falling back to another backend family.

## Annotation Runtime

`annotation_agents.py` is the runtime boundary. `run_annotation_pass()` builds common prompt/artifact metadata, renders the prompt under `artifacts/annotation-prompts/`, and executes `_expanded_command(config, prompt_path)` through `subprocess.run()` in the workspace. The subprocess environment includes standard process keys, configured env key names that exist in the parent environment, default proxy keys that exist in the parent environment, `WAYGATE_ANNOTATION_ROLE`, `WAYGATE_ANNOTATION_STAGE`, `WAYGATE_ANNOTATION_PROMPT`, and `WAYGATE_ANNOTATION_ARTIFACT`.

The annotation runtime does not inspect `WAYGATE_ANNOTATION_TMUX`, `TMUX_PANE`, controller `tmuxTarget`, or the workflow runner family. Those values cannot select a different annotation runtime and cannot create panes. The removed annotation-specific tmux path no longer writes local wrapper scripts, dispatch files, annotation run ids, done files, temporary pane ids, tmux env keys, or fallback reasons. Normal workflow runners retain their own tmux behavior outside annotation.

Completion is valid only when the configured annotation artifact exists and passes normalization, language checks, gate hash binding, and non-approval validation. Runtime failure, timeout, missing artifact, or invalid risk artifact returns an annotation runtime failure. `rrc_controller.py` copies safe subprocess runtime metadata into `blockedContext` and `pendingAnnotationBeforeHumanGate` without mutating the main workflow runner configuration.

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

Every annotation prompt also renders a `Product Contract Traceability Audit` block. This is the module boundary for advisory risk-only 产品合同保真 review: `annotation_agents.py` renders the audit instructions and taxonomy, normalizes the returned risk keys, and records them in the annotation artifact; it does not add a deterministic validator, state schema field, CLI option, approval source, or hard gate.

The audit compares the product-contract chain from `Requirements/Product Design/Spec -> AC/Journey -> Unit Plan test case -> command/user_steps/expected -> Final Acceptance evidence`. It asks the backend to look for 信息衰减 across entry fields, selectors, 受控主体选择, user steps, main business object, success endpoint, error states, `request payload`, `response/readback`, DOM/API/DB evidence, screenshots, and `action path`.

The shared risk taxonomy includes `product_contract_gap`, `information_degradation`, `product_field_mapping_gap`, and `out_of_scope_boundary_risk`. Normalization preserves these categories in `risk_taxonomy` and in `issues[].category` when returned by a backend. Unknown categories still fall back to the role's safe default.

Default annotation evidence refs are assembled from stable text and JSON contract sources when they exist or when staged package state explicitly records them. Requirements annotation can reference Requirements Scope, Product Design, Test Strategy, `source-map.json`, `normalized-requirements.json`, and `prototype-manifest.json`. Unit Plan annotation can reference the Unit Plan body, approved Requirements, Product Design, Test Strategy, Journey contracts, and prototype manifest. Final Acceptance verification assist can reference approved Requirements, approved Unit Plan, `verification.json`, Final Scope Audit, and the Prototype Conformance Matrix. Missing optional refs are omitted to avoid legacy-session noise.

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
