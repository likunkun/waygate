# 进度日志

## 会话：2026-06-09

### Annotation Agent 产品合同保真审查增强
- **状态：** implementation verified; focused annotation/docs suites and full regression passed.
- 修复：annotation prompt 增加 `Product Contract Traceability Audit` section，要求人工 gate 前辅助审查当前版本产品合同是否完整、无歧义，并检查从 Requirements/Product Design/Spec 到 AC/Journey、Unit Plan test case、command/user_steps/expected 和 Final Acceptance evidence 的信息衰减。
- 修复：annotation risk taxonomy 新增 `product_contract_gap`、`information_degradation`、`product_field_mapping_gap`、`out_of_scope_boundary_risk`，并保持 `ambiguous_acceptance` 作为验收语言歧义分类；normalizer 会保留新增 category，不降级为 `weak_evidence`。
- 修复：默认 annotation evidence refs 改为只注入存在或 state 明确记录的稳定文本/JSON 合同源，覆盖 Requirements Scope、Product Design、Test Strategy、source-map、normalized requirements、prototype manifest、approved Requirements/Unit Plan、verification.json、Final Scope Audit 和 Prototype Conformance Matrix，避免 legacy session 噪音。
- 文档：同步正式 workflow / architecture annotation 文档和 `docs/README.md` registry，明确该审查是 advisory risk-only，不是完整性证明、审批来源、deterministic validator、state schema、CLI 或 hard gate。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q -k 'product_contract or default_annotation_evidence_refs or traceability_audit'` -> 3 failed，分别复现缺 prompt section、缺 taxonomy 和 legacy default refs。
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_docs.py -q -k 'product_contract_traceability_audit'` -> 1 failed，复现正式文档缺说明。
  - GREEN: `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q -k 'product_contract or default_annotation_evidence_refs or traceability_audit'` -> `3 passed, 55 deselected`。
  - GREEN: `python3 -m pytest workflow_controller/tests/test_v061_docs.py -q -k 'product_contract_traceability_audit'` -> `1 passed, 8 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q` -> `58 passed`。
  - `python3 -m pytest workflow_controller/tests/test_v061_docs.py -q` -> `9 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `897 passed in 83.60s`。
  - `git diff --check` -> passed。

### V0.6.2j 版本号与 Debian 打包
- **状态：** package built and verified.
- 修复：`workflow_controller.__version__` 更新为 `0.6.2j`；同步 `USAGE.md` / `USAGE.zh-CN.md` 安装示例、packaging 测试期望和双语 CHANGELOG 顶部记录。
- 打包：`bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2j_all.deb`。
- 验证：
  - `python3 -m pytest workflow_controller/tests/test_packaging.py workflow_controller/tests/test_v061_docs.py -q` -> `13 passed`。
  - `python3 -m workflow_controller.cli --version` -> `waygate 0.6.2j`。
  - `dpkg-deb --field dist/waygate_0.6.2j_all.deb Package Version Architecture Depends` -> `waygate / 0.6.2j / all / python3`。
  - 解包后 `WAYGATE_LIB_DIR=/tmp/waygate-0.6.2j-check/usr/lib/waygate /tmp/waygate-0.6.2j-check/usr/bin/waygate --version` -> `waygate 0.6.2j`。
  - `python3 -m pytest workflow_controller/tests -q` -> `897 passed in 83.84s`。
  - `git diff --check` -> passed。

## 会话：2026-06-08

### V2.3 Document Deliverables 多路径解析与 7 号窗口恢复
- **状态：** controller fix verified; live V2.3 blocker cleared with patched source; Debian package rebuilt as `dist/waygate_0.6.2i_all.deb`.
- 现场现象：tmux 7 号窗口 `/home/lichangkun/code/proxy-collector/.rrc-controller-v2.3/session.json` 在 verifier 13/13 通过后先停在 `FINAL_WALKTHROUGH_PREPARE status=blocked`，报 required document deliverable missing：`05-development-plan.md` 与 `06-test-cases.md` 被拼成一个目标路径；随后 agent 手工拆分已批准 `approvals/unit-plan.md`，触发 `journey acceptance is incomplete: unit plan gate hash in journey contract is stale`。
- 根因：Document Deliverables Matrix parser 只把 `Target Path` cell 清理成一个字符串并直接做 `Path.exists()`；同一 cell 中两个 backticked docs path 由中文“与”连接时没有展开成两个 deliverable。后续 stale-hash blocker 是 approved gate body 被手工修改后的预期保护，不是新的业务实现失败。
- 修复：`parse_document_deliverables()` 对同一 Target Path cell 中多个 path-like backtick span 展开为多条 deliverable row；no-formal-doc-change 行保持原样。新增回归测试覆盖一个 required row 同时声明 `05-development-plan.md` 与 `06-test-cases.md` 的 final acceptance 通过场景。
- 现场恢复：将 live `approvals/unit-plan.md` 恢复到审批 hash `60033c9e004b38f28d5dc4d7f445f905c3aed4f6a0c3c91639a0d2773ad54317` 对应的原始正文；使用 patched source 执行 `status`，controller 通过 `final_acceptance_gate_invalid_blocker_cleared` 事件清除 blocker，当前 `status=active`、`nextAction=prepare_final_walkthrough`。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py::test_final_acceptance_accepts_multiple_backticked_required_document_paths_in_one_cell -q` -> failed，报两个 docs path 被当作一个 missing path。
  - GREEN: 同一命令 -> `1 passed`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q -k 'document_deliverable or deliverables'` -> `5 passed, 104 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `109 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `892 passed in 86.57s`。
  - `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2i_all.deb`；`dpkg-deb --field` -> `Package: waygate`, `Version: 0.6.2i`, `Architecture: all`。

### Existing Session `go --spec` Open Spec package hash drift 修复
- **状态：** implementation verified; live V2.3 now reaches Final Acceptance human gate with patched source.
- 现场现象：7 号窗口继续运行 `waygate go V2.3 --spec docs/open-spec/v2.3-ip-key-ops/ ...` 时，报 `Existing session does not match start arguments`；错误中 existing path 和 incoming `--spec` path 相同，但仍拒绝接续。
- 根因：`same_requirements_spec()` 同时比较 path、sourceType 和 hash。Open Spec package 是目录 intake，实施阶段会更新同目录内的 05/06 进度与测试文档，导致当前目录 hash 与 session 初始化时的 `requirementsSpec.hash` 不同。该 hash 是 intake snapshot，不应作为已有 session 的接续兼容条件。
- 修复：已有 session 的 `--spec` 兼容判断只要求 path 与 sourceType 一致，保留 session 中的原始 hash，不在接续时静默覆盖。不同 spec path 仍会拒绝并要求 `--force`。
- 现场验证：
  - patched source 下 `go V2.3 --tmux-target 7.0 --annotation-agent opencode --auto-approve --spec docs/open-spec/v2.3-ip-key-ops/ --max-steps 0` 成功接续，并显示 Final Acceptance 人工 gate。
  - 7.1 pane 已更新状态：`currentStep=WAITING_FINAL_ACCEPTANCE status=active nextAction=check_final_acceptance`。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_spec_intake.py::test_go_accepts_existing_session_same_spec_path_after_open_spec_package_hash_changes -q` -> failed，复现 path 相同但 hash drift 导致 start 参数不匹配。
  - GREEN: 同一命令 -> `1 passed`。
  - `python3 -m pytest workflow_controller/tests/test_v061_spec_intake.py -q` -> `12 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `893 passed in 85.51s`。

### Final Acceptance prototype / real E2E evidence alias follow-up
- **状态：** implementation verified; live V0.6 state revalidated with patched source; Debian package rebuilt but not installed because passwordless sudo is unavailable in this shell.
- 现场现象：安装上一轮 Final Scope Audit 修复后，tmux 2 号窗口不再报 AC/AO coverage 缺失，但停在 `FINAL_WALKTHROUGH_PREPARE status=blocked`，报 `prototype conformance is incomplete ... missing`；源码修复 prototype conformance 后又暴露 `real E2E evidence is incomplete: golden_path unknown-test: not e2e evidence`。
- 根因：V0.6 verifier evidence rows 使用 `test_case` 标识测试用例、使用 `visual_evidence` 保存视觉证据，并把 `action_path` 放在 `screenshot_regression_result` / `screenshot_regression` 内层；Final Acceptance prototype conformance 只匹配 `test_case_id`、只读取 `visual_evidence_refs` 顶层字段。Final real E2E gate 直接检查 raw evidence row，没有按 `test_case` / command 找回 Unit Plan test case 的 `layer=e2e` 和 `entrypoint` 默认值，导致 passed golden path 被误报为 `unknown-test: not e2e evidence`。
- 修复：prototype conformance evidence matching 接受 `test_case` / `testCase` / `case_id` 等别名，视觉证据统一走 `visual_evidence_refs_from_result()`；视觉证据归一化读取截图回归结果内层的 `action_path`、`entrypoint`、`fidelity_level`、`pixel_tolerance` 和 `compared_screenshots`。Final real E2E gate 会按 evidence test-case alias 或 command 找到 Unit Plan case，并补齐 `layer`、`environment_kind`、`real_entrypoint`、mock 和 runtime 默认字段后再执行原有硬校验。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py::test_final_acceptance_accepts_verifier_test_case_and_visual_evidence_aliases -q` -> failed，先报 `missing`，补 test-case alias 后报 `missing action path`。
  - GREEN: 同一命令 -> `1 passed`。
  - RED: `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py::test_final_real_e2e_accepts_verifier_test_case_alias_with_unit_plan_defaults -q` -> failed，报 `golden_path unknown-test: not e2e evidence`。
  - GREEN: 同一命令 -> `1 passed`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q -k 'final_real_e2e or prototype_conformance or visual_evidence'` -> `6 passed, 102 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'final_acceptance_gate_invalid or prototype_conformance'` -> `2 passed, 246 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py -q -k 'prototype_conformance'` -> `2 passed, 74 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_real_runtime.py -q -k 'visual_evidence'` -> `2 passed, 24 deselected`。
  - `python3 -m pytest workflow_controller/tests -q` -> `890 passed, 1 skipped in 86.34s`。
  - `git diff --check` -> passed。
  - patched source revalidation: `PYTHONPATH=/home/lichangkun/works/ai-works/worktrees/workflow-controller python3 -m workflow_controller.rrc_controller status --state-dir /home/lichangkun/code/classroom/.rrc-controller-v0.6` -> `currentStep=FINAL_WALKTHROUGH_PREPARE status=active nextAction=prepare_final_walkthrough projectTargetVersion=V0.6`。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2i_all.deb`；`dpkg-deb --field` -> `0.6.2i`。

### Final Scope Audit evidence alias 修复
- **状态：** implementation verified; live V0.6 blocker validated on temp state copy.
- 现场现象：tmux 2 号窗口的 `/home/lichangkun/code/classroom/.rrc-controller-v0.6/session.json` 停在 `FINAL_WALKTHROUGH_PREPARE status=blocked`，报 `AO-001` 和 `AC-V06-001` 至 `AC-V06-010` 缺少 passed evidence row。
- 根因：V0.6 identity unit 的 `verification.json` 已 `status=passed`、`final_acceptance_can_proceed=true`、18/18 evidence passed，并用 `acceptance_criteria[]` / `obligations[]` 记录 AC/AO 覆盖；`scope_audit.py` 只读取旧字段 `acceptance_criterion` / `acceptance_obligations`，导致 Final Scope Audit 漏认新版数组字段。
- 修复：Final Scope Audit evidence coverage 增加字段别名识别：AC 读取 `acceptance_criterion`、`acceptance_criteria`、`acceptance_criterion_ids`、`acceptance_criteria_ids`；AO 读取 `acceptance_obligations`、`acceptance_obligation_ids`、`obligations`、`obligation_ids`、`covers_obligations`。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_scope_audit.py::test_scope_audit_accepts_verifier_array_aliases_for_ac_and_ao_coverage -q` -> failed，`ao_coverage.covered_ids == []`。
  - GREEN: 同一命令 -> `1 passed`。
  - `python3 -m pytest workflow_controller/tests/test_scope_audit.py -q` -> `9 passed`。
  - `python3 -m pytest workflow_controller/tests/test_scope_audit.py workflow_controller/tests/test_rrc_controller.py -q -k 'final_scope_audit or scope_audit'` -> `11 passed, 246 deselected`。
  - 临时复制 `/home/lichangkun/code/classroom/.rrc-controller-v0.6` 后用源码重算 Final Scope Audit -> valid；AO `2/2`、AC `11/11`、Journey `6/6`，blockers `[]`。
  - `python3 -m pytest workflow_controller/tests -q` -> `888 passed, 1 skipped in 85.04s`。
  - `git diff --check` -> passed。

## 会话：2026-06-07

### Prototype Surface Coverage / Fidelity Gate 硬化
- **状态：** implementation in progress; focused prototype/controller regression passed.
- 修复：Product Design / assembled Requirements 对 required UI/Web prototype 增加 surface coverage gate；Product Design 声明的 required visible surface 必须出现在 `prototype-manifest.json` 的 `surface_contracts[]`。
- 修复：required surface contract 现在要求 `actor`、`task_start`、`main_business_object`、`success_endpoint`、`page_states`、`click_path`、AC 映射、存在 Journey 时的 Journey 映射，以及真实 `implementation_targets`。
- 修复：关联 E2E AC / active E2E Journey / golden-path 候选的浏览器可见 route/page/dialog/drawer/panel/form surface 默认 fidelity 提升为 `screenshot_regression`；普通 required UI surface 仍保持 `structural_interaction`，`pixel_exact` 仍需显式声明。
- 修复：Unit Plan prototype conformance 的 `visual_evidence_plan.entrypoint/action_path` 必须覆盖 manifest target surface 的真实生产入口和 click path；Final Acceptance matrix 增加 screenshot regression / diff artifact 字段，并写 `artifacts/final-acceptance/prototype-conformance-matrix.json`。
- 文档/Prompt：同步 `docs/workflow/prototype-fidelity-policy.md`、`docs/README.md`、Requirements / Product Design / Unit Plan prompt guidance。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py workflow_controller/tests/test_requirements_staged_package.py -q -k 'critical_surface_screenshot_regression or visual_entrypoint_that_does_not_cover or default_critical_surface_without_screenshot_regression or required_surface_without_user_task_contract or declared_visible_surface_missing_from_manifest'` -> 修复前 5 failed。
  - GREEN: 同一命令 -> `5 passed, 213 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py::test_final_acceptance_gate_renders_prototype_conformance_matrix -q` -> `1 passed`。
  - `python3 -m pytest workflow_controller/tests/test_prototype_review.py workflow_controller/tests/test_acceptance_obligations.py workflow_controller/tests/test_requirements_staged_package.py workflow_controller/tests/test_rrc_human_gates.py -q -k 'prototype or surface or visual or fidelity'` -> `59 passed, 249 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_status_clears_stale_final_acceptance_gate_invalid_blocker_after_revalidation -q` -> `1 passed`。
  - `python3 -m pytest workflow_controller/tests/test_prototype_review.py workflow_controller/tests/test_acceptance_obligations.py workflow_controller/tests/test_requirements_staged_package.py workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/test_rrc_controller.py -q` -> `556 passed in 46.73s`。
  - 标准命令 `python -m pytest workflow_controller/tests -q` 无法执行：当前 shell 中 `python` 命令不存在。
  - Fresh after final renderer cleanup: `python3 -m pytest workflow_controller/tests -q` -> `888 passed in 87.48s`。

## 会话：2026-06-04

### V0.6.2i Prompt 与文档合同
- **状态：** implementation verified; pre-commit focused/full regression passed; Debian package built as `0.6.2i`.
- 范围：本版是 Prompt+文档版本，不新增 deterministic validator、state schema、CLI 参数、manifest 必填字段或 hard gate。
- 修复：legacy Requirements 与 staged Scope prompt 的无 `--spec` intake 改为验收前置，先确认当前版本目标、非目标、验收重点、成功/失败证据和范围边界，避免 agent 在用户回答前直接缩小当前版本范围。
- 修复：Product Design prompt 增加 1:1 用户任务原型合同，每个 prototype/surface 必须对应真实用户任务，写明 actor、任务起点、点击路径、页面状态、主业务对象、成功终点、AC/Journey 映射和 production target；明确 prototype artifact 不能替代产品旅程闭环。
- 修复：Unit Plan、Builder、Test Strategist、Refiner prompt 继承 Product Journey Contract，并要求 Unit Plan 写 `主业务对象血缘拆分矩阵`；fixture、工程层、截图或 prototype artifact 只能作为辅助证据，不能替代真实用户任务闭环。
- 补充修复：Test Strategy stage validation 组合 Scope 合同时忽略 Scope 中陈旧的 4.6 E2E matrix，避免旧截图/人工观察类 4.6 行覆盖当前 Test Strategy 的有效 4.6；这是既有 validator 边界修复，不新增 hard gate。
- 文档/版本：同步 `docs/workflow/staged-requirements-package-policy.md`、`docs/architecture/staged-requirements-package-architecture.md`、`docs/README.md`、README/USAGE、ROADMAP/CHANGELOG、findings/task_plan 和 package version metadata 到 `0.6.2i`。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/test_rrc_refiner.py workflow_controller/tests/test_v061_docs.py workflow_controller/tests/test_packaging.py -q -k 'v062i or version_flag or scope_prompt_without_spec or product_design_prompt_requires_manifest_contract_for_required_prototype or product_design_prompt_no_spec_requires_brainstorming_and_one_surface_at_a_time or prompt_contracts_require_ac_mapped_executable_e2e_assertions or run_refiner_enabled_invokes_refiner_runner_and_uses_agent_result'` -> 修复前 7 failed。
  - GREEN: 同一命令 -> `7 passed, 196 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `108 passed`。
  - `python3 -m pytest workflow_controller/tests/test_v061_docs.py workflow_controller/tests/test_packaging.py -q` -> `12 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `879 passed, 1 skipped in 111.44s`。
  - Pre-commit fresh: `python3 -m pytest workflow_controller/tests -q` -> `881 passed in 95.19s`。
  - Pre-commit fresh: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `109 passed`。
  - Pre-commit fresh: `python3 -m pytest workflow_controller/tests/test_v061_docs.py workflow_controller/tests/test_packaging.py -q` -> `12 passed`。
  - Pre-commit fresh: `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2i_all.deb`。
  - `dpkg-deb --field dist/waygate_0.6.2i_all.deb Version` -> `0.6.2i`。

## 会话：2026-06-03

### Requirements AC-SPEC provenance prose parser / V0.6.2h follow-up
- **状态：** implementation verified; focused/full regression passed; Debian package rebuilt as `0.6.2h`.
- 根因：`_requirements_current_ac_ids_in_text()` 已忽略 `Source AC` / `Source AC / TC` 表格列，但仍把 source map prose、conversion note、`AC-SPEC-001 -> AC-V10-001`、`AC-SPEC-001 至 AC-SPEC-012` 等 provenance 文本当作当前版本 AC obligation，导致 final Requirements gate 误报 `AC-SPEC-001 missing verification layer` / `AC-SPEC-012 missing verification layer`。
- 修复：当前 AC 收集增加 source/provenance section 与 line 边界，并扩展 source-like 表头识别到 `Imported AC` / `Original AC`；provenance prose、mapping note、wildcard example 和 source/imported/original columns 不参与当前 AC obligation 收集。canonical Acceptance Criteria 中显式声明 `AC-SPEC-001 [verification: integration]` 仍作为当前 AC 处理；`_requirements_ac_layer_pairs()`、4.6 E2E quality checks 和 Journey/AC coverage 规则不放宽。
- 文档/版本：同步 staged Requirements workflow / architecture docs、docs registry、CHANGELOG、findings 和 task_plan；版本保持 `0.6.2h`，未引入后续 patch 版本号。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'ac_spec_mapping_prose or provenance_prose or imported_original_ac_columns or canonical_ac_spec'` -> 修复前 3 failed，其中 final gate 用例报 `AC-SPEC-001 missing verification layer, AC-SPEC-012 missing verification layer`。
  - GREEN: 同一命令 -> `4 passed, 104 deselected`。
  - Focused: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'source_ac or wildcard or ac_spec or provenance or verification_layer or e2e_review or 4_6'` -> `11 passed, 97 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'requirements_auto_revision or staged'` -> `4 passed, 243 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `108 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `878 passed, 1 skipped in 82.95s`。
  - `git diff --check` -> passed。
  - `rg -n "0\.6\.2i" .` -> no matches.
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2h_all.deb`。
  - `dpkg-deb --field dist/waygate_0.6.2h_all.deb Version` -> `0.6.2h`。

### Requirements 4.6 parser boundary / V0.6.2h
- **状态：** implementation verified; focused/full regression passed; Debian package built as `0.6.2h`.
- 根因：`_requirements_e2e_review_rows()` 在同一 markdown section 内复用最近一次 4.6 header；当有效 11 列 `## 4.6` E2E matrix 后面出现 `### 4.7 Scope AC Verification Layer Closure` 的 5 列表时，后续 `AC-V10-010` closure row 会继承旧 4.6 header，被误判为 `Requirements 4.6 Verification Command is empty or placeholder` 等缺列问题。
- 修复：4.6 row collector 现在只消费 canonical 固定列 E2E matrix block；遇到非表格行或非 canonical markdown table header 会重置 active 4.6 header。真实 4.6 table 内的 row quality checks 不放宽，仍校验 command intent、real entrypoint、user steps、fixture/setup、environment kind、mock policy 和 expected assertions。
- 文档/版本：同步 staged Requirements workflow / architecture docs、docs registry、findings、task_plan、README/USAGE、CHANGELOG/ROADMAP，并把 package version metadata 更新为 `0.6.2h`。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py::test_test_strategy_stage_validation_ignores_non_4_6_tables_under_4_6_subsections -q` -> 修复前 failed，报 `AC-V10-010 Requirements 4.6 Verification Command is empty or placeholder`。
  - GREEN: 同一命令 -> `1 passed`。
  - Focused: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'source_ac or wildcard or conflicting_ac_layer or journey_verification or e2e_review or 4_6'` -> `10 passed, 94 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `104 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'requirements_auto_revision or staged'` -> `4 passed, 243 deselected`。
  - `python3 -m pytest workflow_controller/tests -q` -> `875 passed in 84.38s`。
  - `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2h_all.deb`。
  - `dpkg-deb --field dist/waygate_0.6.2h_all.deb Version` -> `0.6.2h`。

### Controller Requirements source-label parser 与 AC/Journey routing 修复
- **状态：** implementation verified; focused/full regression passed.
- 根因：Requirements ID parser 会把 `AC-V10-*` 误截成 `AC-V10-`；staged Requirements final preflight 又把 `Source AC` / `Source AC / TC` provenance 列里的 source label 当作当前版本 AC obligations，导致 `AC-SPEC-*` / `AC-SPEC-001 missing verification layer`。同一 prose line 中 `J-... [verification: manual]` 也会被行级 fallback 扩散到同一行提到的 AC，制造虚假的 AC layer conflict；该 conflict reason 又因 `verification layer` 关键词误路由到 Test Strategy。
- 修复：AC/Journey ID tokenization 增加 suffix boundary，并要求 body 不能以短横线结尾；Requirements validator 收集当前 AC 时忽略 `Source AC` / `Source AC / TC` provenance 列；AC layer fallback 遇到 Journey-local inline verification marker 时不再给同一行 AC 赋层；`staged requirements package conflicting AC verification layers ...` 归类为 Scope AC/Journey contract conflict，semantic key 为 `scope:ac_verification_layer_conflict`。
- 文档：同步 staged Requirements workflow / architecture 文档，记录 source provenance、wildcard example、Journey-local marker 和 Scope routing 边界；同步 `findings.md` 与 `task_plan.md`。
- 验证：
  - RED/GREEN: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'source_ac or wildcard or conflicting_ac_layer or journey_verification'` -> 修复前 4 failed，修复后 `4 passed, 99 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'requirements_auto_revision or staged'` -> `4 passed, 243 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `103 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `874 passed in 81.86s`。
  - `git diff --check` -> passed。

## 会话：2026-06-02

### Annotation Agent subprocess-only 与 Claude annotation backend 移除
- **状态：** implementation verified; focused scripts and full regression passed.
- 根因：V0.6.2g annotation tmux runtime 扩大了 annotation execution surface；当前策略改为移除 annotation 专用 tmux runtime，避免 annotation 创建临时 pane、wrapper、run id 或 `done.json`。
- 修复：annotation runtime 始终使用 subprocess。`WAYGATE_ANNOTATION_TMUX`、继承的 `TMUX_PANE` 和 state 中的 tmux runner 信息只作为兼容旧环境的无效上下文被忽略，不创建 pane、不调用 `split-window` / `set-buffer` / `paste-buffer` / `send-keys` / `kill-pane`。
- 修复：声明式 annotation backend 仅支持 `opencode` 和 `codex`；`claude` / `claude-code` 被拒绝。已有 session 中 Waygate 内置 `backend=claude-code command=claude` annotation 配置迁移为内置 OpenCode 模板；自定义 command 保留，但声明 backend 仍必须是 `opencode` 或 `codex`。
- 文档：同步 README/USAGE、CHANGELOG/ROADMAP、正式 annotation workflow/architecture 文档、staged Requirements 文档、docs registry、task_plan/findings 和 V0.6.2g verification script 术语。
- 验证：
  - `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q` -> `55 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'annotation or final_acceptance or blocked'` -> `45 passed, 202 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_v061_docs.py workflow_controller/tests/test_packaging.py -q` -> `11 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `869 passed, 1 skipped in 83.18s`。
  - `bash scripts/verify/v062g-annotation-tmux-runtime.sh` -> `4 passed` + `18 passed`。
  - `bash scripts/verify/v062g-annotation-fallback-env.sh` -> `6 passed`。
  - `bash scripts/verify/v062g-product-design-prompt.sh` -> `5 passed`。
  - `bash scripts/verify/v062g-prototype-and-docs.sh` -> passed and refreshed V0.6.2g visual marker artifacts。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2g_all.deb`；`dpkg-deb --field` 和解包后 `waygate --version` 均为 `0.6.2g`。

### Final Acceptance 非浏览器 Prototype Conformance 误判修复
- **状态：** implementation verified; focused/full regression passed; live V0.6.2g blocker cleared.
- 根因：Final Acceptance prototype conformance matrix 对所有 production targets 无条件调用 real E2E evidence 校验，导致 `module/artifact/state/events` + `surface kind=other` 的 artifact-local workflow review evidence 即使 `integration/local_real` passed 且有完整 `visual_evidence_refs`，仍被误判为 `not e2e evidence`。
- 修复：Final Acceptance evidence 判定改为 target-aware；浏览器 route/path `/...` 和 `route/page/component/dialog/drawer/panel/form` surface 继续要求 real E2E，非浏览器 `module/artifact/state/events` + `other` surface 接受 passed non-mock local evidence，并保持视觉证据、runtime errors 和 core API mock 阻断规则。
- 修复：`get_status()` 对 `status=blocked` 且 `blockedReason` 以 `final acceptance gate invalid:` 开头、当前位置为 `FINAL_WALKTHROUGH_PREPARE` 的 deterministic blocker 重新计算 Final Acceptance preflight；新规则下通过时清除 blocker 并恢复 `status=active`，不手改 live `session.json`。
- 文档：同步 `docs/workflow/prototype-fidelity-policy.md`，明确 Final Acceptance 的 prototype conformance E2E 要求按 target 类型区分，浏览器 surface 不放宽。
- 验证：
  - RED/GREEN: `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q -k 'non_browser_prototype_conformance or browser_route_prototype_target'` -> `2 passed` after fix，修复前非浏览器用例失败为 `not e2e evidence`。
  - RED/GREEN: `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'stale_final_acceptance_gate_invalid_blocker'` -> `1 passed` after fix，修复前 state 保持 `blocked`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q -k 'prototype_conformance or visual'` -> `6 passed, 97 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py -q -k 'prototype_conformance'` -> `2 passed, 74 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'final_acceptance or blocked'` -> `44 passed, 203 deselected`。
  - 标准命令 `python -m pytest workflow_controller/tests -q` 无法执行：当前 shell 中 `python` 命令不存在。
  - `python3 -m pytest workflow_controller/tests -q` -> `868 passed, 1 skipped in 84.99s`。
  - `waygate status --state-dir .rrc-controller-v0.6.2g` -> `currentStep=FINAL_WALKTHROUGH_PREPARE status=active nextAction=prepare_final_walkthrough projectTargetVersion=V0.6.2g`；live events 记录 `final_acceptance_gate_invalid_blocker_cleared`，不再有 `not e2e evidence` blocker。
- 补充：`scripts/verify/v062g-annotation-tmux-runtime.sh` 保留历史脚本名，但当前职责改为验证 annotation 专用 tmux runtime 已移除，设置旧环境变量或处于 tmux 环境也仍走 subprocess。
- 验证：`bash scripts/verify/v062g-annotation-tmux-runtime.sh` -> `4 passed` + `18 passed`。

### V0.6.2g Product Design Prompt Contract and annotation subprocess baseline
- **状态：** implementation verified; annotation pane runtime removed in follow-up.
- 已实现 Product Design prompt 三分支：无 supported spec 时要求 same tmux conversation brainstorming 与逐页/逐入口确认；supported spec 会话保持 staged artifact compatibility；backend/API/CLI-only scope 只基于正向 no-UI/no-prototype 依据做一次确认。
- Annotation runtime 基线改为 subprocess-only；旧 tmux 环境变量和 tmux-backed state 不再影响 annotation 执行。pytest helper 仍默认移除继承的 `TMUX` / `TMUX_PANE`，避免 contract-mock 测试误受开发者 shell 环境影响。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'rrc_subprocess_env_strips_inherited_tmux_context'` -> `1 passed`。
  - `bash scripts/verify/v062g-annotation-tmux-runtime.sh` -> `4 passed` + `18 passed`。
  - `bash scripts/verify/v062g-annotation-fallback-env.sh` -> `6 passed`。

### V0.6.2f Final Acceptance 终验同步
- **状态：** Final Acceptance approved; human-readable status synced.
- Controller state `.rrc-controller-v0.6.2f/session.json` 显示 `finalAcceptanceAccepted=true`、确认人为 `human`，目标 `Complete V0.6.2f development acceptance using current planning progress` 已 `covered`，单元 `target-v0-6-2f` 已 `passes=true`。
- Final Acceptance evidence matrix 中 AC-V062F-001 至 AC-V062F-009 均 passed；Final Scope Audit 显示 AC coverage `9/9`、Journey coverage `7/7`、AO coverage `1/1`、unexplained changed files `0`。
- 必需文档 deliverables 均为 present，`docs/README.md` 已登记 V0.6.2f workflow / architecture 文档；本同步更新了 `ROADMAP.md`、`ROADMAP.zh-CN.md`、`task_plan.md` 和 `progress.md`。
- 未发现需要新增到 `findings.md` 的 workflow decision、defect 或 risk；除本轮 `DONE_FILE` 外，本次只写 final sync summary artifact。

### V0.6.2e `--spec` 文档包目录 intake
- **状态：** implementation verified; focused/full regression passed; Debian package rebuilt as `0.6.2e`.
- 修复：`--spec` 现在可导入 Open Spec 文档包目录，要求 `01-requirements.md` 且至少包含 `02-specification.md`、`03-technical-solution.md`、`04-storage-design.md` 或 `08-stage-handoff.md` 之一；`requirementsSpec.path` 保存目录路径，hash 覆盖目录内容。
- 修复：新增 `sourceType=open-spec-package` conversion artifacts：`import-summary.json`、`normalized-requirements.json`、`source-map.json`、`validation-report.json`，并记录 package entrypoints；artifact 输出会脱敏 token / database URL 等敏感值。
- 修复：Spec Kit feature package 支持任意目录名，只要 `spec.md` 同目录存在 `plan.md`、`tasks.md`、`research.md`、`data-model.md`、`quickstart.md` 或 `contracts/`；保留 legacy `spec-kit` / `specify` 目录和 `feature.specify.md` 文件兼容。
- 修复：`.specify` workspace/tool root 和普通 docs 目录不会被误判为需求源；错误提示要求传入 `specs/<feature>/` 或具体 `spec.md`。
- 文档/版本：同步 README/USAGE/CHANGELOG/ROADMAP、external spec intake workflow/architecture docs、Requirements prompt/brief 文案和 package version 到 `0.6.2e`。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_spec_intake.py -q -k 'v062e'` -> 新增用例按预期失败。
  - GREEN: `python3 -m pytest workflow_controller/tests/test_v061_spec_intake.py -q` -> `11 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'spec or requirementsSpec'` -> `6 passed, 239 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_packaging.py workflow_controller/tests/test_v061_docs.py -q` -> `10 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `838 passed, 1 skipped in 82.88s`。
  - `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2e_all.deb`；`dpkg-deb --field` 和解包后 `waygate --version` 均为 `0.6.2e`。

## 会话：2026-06-01

### Verifier 环境占位值与重复失败保护修复
- **状态：** implementation verified; focused/full regression passed.
- 根因：`verification_env` 把 `required key name only`、`<...>` 等 key-only 说明当作真实值覆盖父进程环境；同时 `REFINE_UNIT` / `REVIEW_UNIT` 成功后全局清理 `lastFailure`，导致同一 `VERIFY_UNIT` failure fingerprint 经过 Builder/Refiner/Reviewer 后丢失计数。
- 修复：Verifier runtime 跳过 key-only 占位 value；父进程存在同名真实环境变量时使用父环境值，否则不注入，保留脚本自身 `.env` / 默认加载逻辑。`env_keys` 作为只声明变量名的合同，不记录 value。
- 修复：Unit Plan validator 拒绝 `verification_env` 中的 key-only prose / `<...>` 占位 value，支持 state/unit 级 `env_keys`，并拒绝 `env_keys` 中包含 `=`、URL 或其他非变量名条目；Unit Plan prompt 同步说明 `verification_env` 与 `env_keys` 边界。
- 修复：新增 stage-aware `lastFailure` 清理；Refiner/Reviewer 成功只清同 stage failure，`VERIFY_UNIT` failure 会保留到下一次 verifier 通过或相同 fingerprint 再次触发 repeated failure block。
- 打包：`bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2d_all.deb`；`dpkg-deb --field` 与解包后的 `waygate --version` 均确认为 `0.6.2d`。
- 验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_real_runtime.py -q` -> `26 passed in 5.63s`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'repeated_verification_failure or lastFailure or verifier'` -> `8 passed, 237 deselected`。
  - `python3 -m pytest workflow_controller/tests/gates/test_gates_structure.py -q` -> `22 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `830 passed in 82.74s`。
  - `git diff --check` -> passed。

### Staged Requirements 无 spec Scope 首轮澄清修复
- **状态：** implementation verified; focused/full regression passed.
- 根因：legacy `REQUIREMENTS_DRAFT` 已对无 `--spec` 首轮关闭 idle monitor 并要求先问人工，但 V0.6.2 staged 默认入口 `REQUIREMENTS_SCOPE_DRAFT` 只注入 Scope 生成要求，没有强制先问人工确认版本目标、非目标、验收重点和事实来源。
- 修复：新增 staged Scope 首轮澄清判定：无 supported `requirementsSpec`、无 `requirementsRevisionFeedback`、Scope artifact 尚未 complete 时，Scope prompt 明确要求先在 tmux agent pane 提 1 个需求澄清问题，等待人工回答后再读项目上下文并写 `requirements-scope.md`；`--auto-approve` 不跳过该步骤。
- 修复：tmux-backed no-spec Scope 首轮 runner request 使用 `idle_monitor_enabled=False`，timeout 仍为 `DEFAULT_AGENT_TIMEOUT_SECONDS=7200`；有 spec、已有 revision feedback、或 Scope 已完成后的后续 run 保持默认 idle monitor。
- 文档：同步 `docs/workflow/staged-requirements-package-policy.md`，记录 no-spec Scope clarification 与 auto-approve 边界。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'scope_prompt_without_spec or scope_prompt_with_spec or scope_stage_without_spec or scope_stage_with_spec'` -> 新增用例按预期失败。
  - GREEN: 同一命令 -> `4 passed, 81 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'scope_prompt_without_spec or scope_stage_without_spec or scope_stage_with_spec'` -> `3 passed, 82 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'requirements_draft_uses_two_hour_timeout_by_default or requirements_draft_with_spec_keeps_idle_monitor_enabled'` -> `2 passed, 241 deselected`。
  - `python3 -m pytest workflow_controller/tests -q` -> `822 passed, 1 skipped in 82.46s`。
  - `git diff --check` -> passed。

## 会话：2026-05-31

### stale Builder blocked artifact 恢复修复
- **状态：** implementation verified; live Classroom V0.4 recovered and advanced through normal controller route.
- 根因：Unit Plan 重新批准后，controller 仍会把旧 `artifacts/<unit>/builder-summary.json` 的 `blocked` 结果重新解释成当前官方 blocked；旧 artifact 没有与最新 Unit Plan approval 建立 freshness 边界。
- 修复：Unit Plan approval 成功时记录 `unitPlanAcceptedAt`；旧 session 若只有 `unitPlanAcceptedHash`，在 gate approved 且 hash 匹配时用 `approvals/unit-plan.md` mtime 作为 cutoff。Builder summary mtime 早于 cutoff 时视为 stale audit artifact，不再阻塞。
- 修复：Builder blocked context 可按 unit 读取；Unit Plan approval 扫描 approved plan 的所有 `units[].id` 与 `currentUnitId`，把已有 blocked summaries 写入 `ignoredBuilderBlockedContexts`，避免非当前 unit 的旧 blocker 在切换单元后复活。
- 修复：`get_status()` 会自动清理已处于 `status=blocked` 的 stale `blockedContext.source=builder_agent`，恢复 `status=active` / `currentStep=EXECUTE_UNIT`，并追加 `stale_builder_agent_blocked_context_cleared` event；不删除历史 `builder-summary.json`。
- 已完成验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'builder_summary_blocked or builder_agent_blocked or unit_plan_approval_ignores'` -> 新增/更新用例按预期失败。
  - GREEN: 同一命令 -> `5 passed, 237 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'builder_agent_blocked or stale_builder or unit_plan_approval_ignores_previous_builder_blocked_artifact or unblock_rejects_unit_plan_contract'` -> `4 passed, 238 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_builder.py::test_prepare_builder_prompt_ignores_controller_failure_from_other_unit workflow_controller/tests/test_rrc_controller.py::test_builder_done_ignores_verifier_failure_from_other_unit -q` -> `2 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `817 passed in 82.90s`。
  - `git diff --check` -> passed。
- Live recovery:
  - `python3 -m workflow_controller.rrc_controller status --state-dir /home/lichangkun/code/classroom/.rrc-controller-v0.4` -> `currentStep=EXECUTE_UNIT status=active nextAction=run_builder projectTargetVersion=V0.4`，并写入 `stale_builder_agent_blocked_context_cleared`。
  - `python3 -m workflow_controller.rrc_controller go --state-dir /home/lichangkun/code/classroom/.rrc-controller-v0.4 --max-steps 1` 正常派发 Builder，不手改 live `session.json`、不删除 artifact；Builder 完成后 controller 前进到 `currentStep=REFINE_UNIT status=active nextAction=run_refiner`，因 `--max-steps 1` 停止。

### V0.6.2d Unit Continuity Gate
- **状态：** implementation verified; focused/full regression passed.
- 新增 Unit Plan handoff 连贯性 validator：多单元依赖必须声明 `depends_on` 与 `handoff`，拒绝缺失依赖、循环依赖、模糊 `human_summary`、下游 `requires[]` 无上游 `produces[]` 匹配、ready checks 未映射到命令/测试用例。
- 修正多上游依赖匹配：下游 `requires[]` 可由不同 upstream 分别满足，但每个 required input 至少要有一个 producer，且每个声明依赖至少贡献一个 required input。
- Unit Plan approval Markdown 也会校验多单元 handoff 的 `## 单元连贯性摘要` 和 `## Handoff Matrix` 人工审阅段落，避免只剩结构化 JSON 而缺少人工可读交接说明。
- 新增 Verifier producer handoff evidence：声明 handoff 的 unit 会写 `artifacts/<unit-id>/handoff-evidence.json`；声明的 evidence artifact 缺失或 ready check 未通过时 producer verification 失败。
- 新增 downstream Builder preflight：依赖单元 handoff evidence 缺失、无效、failed 或无法满足下游 `requires[]` 时，以 `blockedContext.category=unit_handoff` 阻塞，并给出中文恢复 guidance。
- Prompt / docs：Unit Plan prompt 增加 `单元连贯性摘要`、`Handoff Matrix` 和 Controller State Patch JSON 字段；Builder prompt 说明上游 handoff 证据边界；新增 `docs/workflow/unit-continuity-handoff-policy.md` 并登记到 `docs/README.md`。
- 版本记录：更新 package version metadata 至 `0.6.2d`，同步 ROADMAP / CHANGELOG / README / USAGE。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_unit_plan_continuity.py -q` -> `12 passed`。
  - `python3 -m pytest workflow_controller/tests/test_unit_plan_continuity.py workflow_controller/tests/test_unit_plan_command_policy.py -q` -> `21 passed`。
  - `python3 -m pytest workflow_controller/tests/test_unit_plan_command_policy.py -q` -> `9 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_verifier.py -q` -> `7 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_builder.py -q` -> `6 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'unit_plan_gate_invalid or run_builder or blocked_guidance or builder_agent_blocked or unit_plan_approval'` -> `18 passed, 221 deselected`。
  - 标准命令 `python -m pytest workflow_controller/tests -q` 无法执行：当前 shell 中 `python` 命令不存在。
  - `python3 -m pytest workflow_controller/tests -q` -> `813 passed in 82.23s`。
  - `python3 -m pytest workflow_controller/tests/test_v061_docs.py -q` -> `6 passed`。
  - `python3 -m pytest workflow_controller/tests/test_packaging.py -q` -> `4 passed`。
  - `python3 -m py_compile workflow_controller/unit_handoff.py workflow_controller/gates/validators/__init__.py workflow_controller/steps/builder.py workflow_controller/rrc_controller.py workflow_controller/prompts/unit_plan.py workflow_controller/prompts/builder.py` -> passed。
  - `git diff --check` -> passed。

### tmux 2 号窗口 blocked 诊断与跨单元 lastFailure 修复
- **状态：** implementation in progress; focused RED/GREEN passed.
- 现场现象：`/home/lichangkun/code/classroom/.rrc-controller-v0.4/session.json` 当前为 `status=blocked`、`currentUnitId=target-v0-4-prereq-env-fixture`、`blockedReason=Exact historical failed command...`；tmux 2 号 controller pane 显示 `category=unit_plan_contract`，选择 `c` 被拒绝是当前 blocked policy 的预期行为。
- 根因：Builder prompt 把旧单元 `target-v0-4-openmaic-course-draft` 的 verifier failed command 注入到当前 prerequisite unit；`lastFailure` 已有 `unit_id`，但 prompt 渲染和 Builder completion 的 controller failure resolution gate 没有按当前 unit 过滤。
- 修复：新增 `_current_unit_last_failure()`，Builder prompt、Builder failure-resolution gate 和紧凑失败摘要只使用当前 `currentUnitId` 对应的 `lastFailure`；旧 session 无 `unit_id` 的 lastFailure 保持兼容。
- 已完成 focused RED/GREEN：
  - `python3 -m pytest workflow_controller/tests/test_rrc_builder.py::test_prepare_builder_prompt_ignores_controller_failure_from_other_unit -q` -> failed before fix, passed after fix。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_builder_done_ignores_verifier_failure_from_other_unit -q` -> failed before fix, passed after fix。
  - `python3 -m pytest workflow_controller/tests/test_rrc_builder.py -q -k 'controller_verification_failure_protocol or previous_verification_failure_feedback or other_unit'` -> `3 passed, 4 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'builder_done_after_verifier_failure or ignores_verifier_failure_from_other_unit'` -> `4 passed, 236 deselected`。
  - `python3 -m py_compile workflow_controller/steps/_common.py workflow_controller/prompts/builder.py workflow_controller/rrc_controller.py` -> passed。
  - 标准命令 `python -m pytest workflow_controller/tests -q` 无法执行：当前 shell 中 `python` 命令不存在。
  - `python3 -m pytest workflow_controller/tests -q` -> `815 passed in 85.45s`。

## 会话：2026-05-30

### Annotation Agent 默认代理环境透传
- **状态：** implementation verified; focused/full regression passed.
- 修复：Annotation Agent subprocess 默认继承父 `waygate` 进程中已存在的标准代理 key：`HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`、`NO_PROXY` 及小写形式；不需要再通过 `--annotation-agent-env-key` 传代理。
- 修复：runner metadata、event、annotation artifact 和 verification-assist artifact 只记录 effective `env_keys`，不记录代理 URL 或其他 env value；stdout/stderr 和 agent 输出中的 inherited env values 继续写入 artifact 前脱敏。
- 文档：同步 `USAGE.md` / `USAGE.zh-CN.md` 和 external spec annotation workflow / architecture 文档，明确 `--annotation-agent-env-key` 只用于额外非代理变量，annotation runtime blocker 修复后从已有代理环境的 shell 重新运行或 unblock。
- 验证：
  - RED：新增 focused tests 初始失败，复现默认代理 env 未传给 annotation subprocess，以及代理值未进入 effective metadata 的旧行为。
  - GREEN：`python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q` -> `48 passed`。
  - GREEN：`python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'annotation or blocked'` -> `23 passed, 216 deselected`。
  - GREEN：`python3 -m pytest workflow_controller/tests -q` -> `798 passed in 78.33s`。
  - `git diff --check -- workflow_controller/annotation_agents.py workflow_controller/tests/test_v061_annotation_agents.py USAGE.md USAGE.zh-CN.md docs/workflow/external-spec-intake-and-annotation-policy.md docs/architecture/external-spec-intake-and-annotation-architecture.md` -> passed。

### V0.6.2c 中文 Checkpoint 命名与定点 Revise
- **状态：** implementation verified; focused/full regression passed; package version updated to `0.6.2c`.
- 修复：staged Requirements 用户可见 checkpoint 名称改为中文主名：需求范围检查点、产品设计简报、技术架构简报、需求测试策略简报；内部 `scope` / `product_design` / `architecture` / `test_strategy` state key、artifact key 和 state-machine step 保持英文不迁移。
- 修复：final Requirements gate 的 appendix title 和 hash table 展示中文 checkpoint 名称，同时保留稳定 stage key 与英文别名；prompt、compact action/status 和 stage-validation guidance 使用中文 checkpoint 名称。
- 修复：`waygate revise --gate requirements --checkpoint scope|product-design|architecture|test-strategy --reason ...` 支持定点回撤；接受 `需求范围`、`产品设计`、`技术架构`、`测试策略` 等中文别名；`--gate unit-plan --checkpoint ...` 会被拒绝。
- 修复：显式 checkpoint revise 会写入 checkpoint / human reason 到 `requirementsRevisionFeedback`，清除 Requirements 与 Unit Plan approval，删除当前 Unit Plan gate，将指定 checkpoint 及下游 artifacts 标记 stale，并在 `requirements_staged_revision_routed` event 记录 gate、checkpoint、reason 和 routing source。
- 文档：同步 `docs/README.md`、staged requirements workflow / architecture docs、README/USAGE、CHANGELOG 和 ROADMAP / ROADMAP.zh-CN。
- 验证：
  - RED：新增 focused tests 初始失败，覆盖缺少 checkpoint normalizer、CLI `--checkpoint`、explicit checkpoint API 和非 TTY staged Requirements revise guard。
  - GREEN：`python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `81 passed`。
  - GREEN：`python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'revise or staged or checkpoint'` -> `20 passed, 219 deselected`。
  - GREEN：`python3 -m pytest workflow_controller/tests/test_v061_docs.py workflow_controller/tests/test_packaging.py -q -k 'staged_requirements or package_version or version'` -> `4 passed, 6 deselected`。
  - GREEN：`python3 -m pytest workflow_controller/tests -q` -> `795 passed in 79.50s`。

### tmux Claude 后台 shell 超时语义修正
- **状态：** implementation verified; focused regression passed.
- 复现路径：`16:0.1` Claude pane 显示 `1 shell` / `1 shell still running`，但 controller 在 Requirements Draft 等待上限到达后写入 `status=timeout` 和“pane output stopped changing”文案。
- 根因：`workflow_controller/runners/tmux_claude.py` 的 idle monitor 已用 `_tmux_pane_tail_shows_running_shell()` 避免 `agent_idle_without_done`，但最终 deadline 分支没有复用该判断，仍无条件返回 `timeout`。
- 已修复：deadline 到达时若 pane tail 仍显示 shell 工具运行，runner 返回 `agent_shell_running_without_done`，记录同名 event，并写明这是 active shell pending 而不是 idle/no-response timeout。
- 已按现场调试结论去除额外 timeout 证据落盘，不再生成 `timeout-decision.json` 或 `requirements-resume-timeout-decision.json`。
- 已同步 recoverable wait 状态集合、Requirements pending draft 状态集合、stop guidance 和正式 workflow / usage 文档。
- 已完成验证：
  - `.venv312/bin/python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q -k 'shell_tool_tail_is_not_idle_without_done or idle_without_done or timeout or idle_monitor or nudge'` -> `9 passed, 30 deselected`
  - `.venv312/bin/python -m pytest workflow_controller/tests/test_rrc_agent_runners.py workflow_controller/tests/test_rrc_controller.py -q -k 'shell_tool_tail_is_not_idle_without_done or recoverable_agent_wait or requirements_draft_timeout or builder_timeout or unit_plan_draft_timeout or stop_guidance'` -> `10 passed, 253 deselected`
  - `.venv312/bin/python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q -k 'timeout or idle_without_done or shell_tool_tail_is_not_idle_without_done or nudge'` -> `9 passed, 30 deselected`
  - `.venv312/bin/python -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'requirements_draft_timeout or recoverable_agent_wait or stop_guidance'` -> `7 passed, 217 deselected`

## 会话：2026-05-29

### V0.6.2b Product Design 后常驻原型预览
- **状态：** implementation verified; focused/full regression passed; Debian package rebuilt as `0.6.2b`.
- 修复：Product Design checkpoint 校验通过后立即生成 `plannotator-review.html` / `prototype-review-manifest.json`，并启动随当前 controller 进程常驻的 prototype preview server；final Requirements gate 尚未装配时使用 Scope checkpoint 作为 requirements reference。
- 修复：final Requirements assembly 后重新生成 review bundle，补齐真实 `approval_gate_path`，并复用已启动 preview server 的当前端口；Requirements gate 选择 `v` 时复用该服务，Plannotator Close 后不再关闭预览服务。
- 修复：preview server 端口从 `WAYGATE_PREVIEW_PORT` 或默认 `20001` 起步，端口被占用时递增；代理环境下提示将 display host 加入 `NO_PROXY/no_proxy`。
- 验证：
  - RED/GREEN: 新增 focused tests 覆盖 Scope reference bundle、默认端口占用递增、env port 占用递增、Product Design 后启动常驻预览、final assembly 复用端口并刷新 approval metadata、Plannotator Close 后 preview server 仍存活。
  - `python3 -m pytest workflow_controller/tests/test_prototype_review.py -q` -> `14 passed`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'prototype or product_design or staged'` -> `79 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'prototype_review or plannotator or staged'` -> `15 passed, 209 deselected`。
  - `python3 -m pytest workflow_controller/tests -q` -> `758 passed in 79.72s`。
  - `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2b_all.deb`。

## 会话：2026-05-28

### Unit Plan 命令脚本入口限制
- **状态：** implementation verified on source branch; Python 3.12 full regression passed; current V0.6.2c cherry-pick will be verified in this branch.
- 用户决策：不再兼容 Unit Plan Markdown 表格中的管道符解析；所有可执行验证命令都必须先写入 `scripts/verify/` 下的脚本文件，再通过脚本入口执行。
- 已新增 Unit Plan command policy validator，检查 `verification_commands[]` 与 test case `command`，只接受脚本入口形态：`bash scripts/verify/<case>.sh`、`sh scripts/verify/<case>.sh`、`python3 scripts/verify/<case>.py`、`python scripts/verify/<case>.py`、`./scripts/verify/<case>.sh` 或 `./scripts/verify/<case>.py`。
- 后续澄清：脚本入口策略不限制为 bash；Python 脚本入口同样是有效命令。Unit Plan 仍不接受直接 `pytest`、`python -c`、管道或内联 shell。
- 已接入 Unit Plan 人工确认前 preflight 与 Unit Plan approval 后持久化前校验；Requirements 确认阶段不解析命令，因为可执行命令来自 Unit Plan `Controller State Patch`。
- 已同步 `docs/workflow/unit-plan-evidence-row-preflight-policy.md` 与 `docs/README.md`。
- 源分支验证：
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest workflow_controller/tests/test_unit_plan_command_policy.py -q` -> `7 passed`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest workflow_controller/tests/test_unit_plan_command_policy.py workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/test_rrc_e2e.py workflow_controller/tests/test_rrc_real_runtime.py workflow_controller/tests/test_v061_annotation_agents.py -q` -> `143 passed`
  - 沙箱外 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest workflow_controller/tests --ignore=workflow_controller/tests/test_rrc_controller.py -q` -> `443 passed`
  - `python3 -m py_compile ...` 修改过的 Python 文件 -> passed
  - 标准 `python -m pytest workflow_controller/tests -q` 在源环境失败：`python` 命令不存在。
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest workflow_controller/tests -q` 在源环境失败于既有 Python 3.10 f-string backslash 兼容问题。
  - `.venv312/bin/python -m pytest workflow_controller/tests -q` -> `670 passed in 119.00s`。

### 7号窗口 Requirements Auto-Rework 后续整改
- **状态：** implementation verified; focused/full regression passed; package rebuilt; user-level `waygate` synced; live V2.1 recovered to Requirements human gate.
- 修复：Journey contract parser 接受无 `Title` 列的 Journey 表，并以 Journey ID 作为 title 兜底；新增 `Acceptance contract`、`Path / assertion focus` 等 steps 表头别名；assembled final gate 中同一 Journey ID 的兼容重复表行会合并为一条合同记录，优先保留更完整 steps、AC、Unit、Test Case 和 command 信息。
- 修复：Scope / Test Strategy staged prompts 和 controller validation feedback 明确最小可解析 Journey 表头 `Journey / Title / Status / Steps / AC / Verification Layer`；`journey contract required...` 语义路由到 Scope，reason key 为 `scope:journey_contract_required`。
- 修复：内置 `claude-code` annotation args 改为 `--bare --no-session-persistence -p ... --permission-mode bypassPermissions`，并迁移已有 session 中旧 built-in Claude Code args；annotation runtime unblock 继续只重跑 pending annotation，不触发 Requirements rewrite。
- 文档：同步 staged Requirements workflow / architecture 和 external spec annotation workflow / architecture，记录 Journey 表头兼容、Scope 路由边界和 Claude Code annotation runtime 参数。
- 验证：
  - RED: 新增 focused tests 初始失败，覆盖无 Title Journey 表、contract/focus steps 表头、Journey required 路由、canonical prompt/feedback、Claude Code 默认参数和 legacy migration。
  - RED/GREEN: `test_journey_contract_merges_compatible_duplicate_rows_from_assembled_gate` 复现 live V2.1 assembled gate 中 Scope / canonical / Test Strategy 多张 Journey 表导致 duplicate/missing steps 的误判，并验证合并后 `journeys.json` 不写 `_merge_conflicts` 私有字段。
  - GREEN: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'contract_steps or journey_contract_required_reason or staged_prompts_anchor'` -> `3 passed, 72 deselected`。
  - GREEN: `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q -k 'builtin_annotation_backend_templates or legacy_builtin_claude_code or unblock_reruns_legacy_blocked'` -> `4 passed, 41 deselected`。
  - live V2.1 diagnostic against `/home/lichangkun/code/proxy-collector/.rrc-controller-v2.1/approvals/requirements-and-acceptance.md` -> 10 unique active Journey rows, all with steps and valid `e2e` layer.
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'journey or prototype or auto_revision or product_design'` -> `32 passed, 44 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'journey_contract or requirements_auto_revision or annotation_runtime'` -> `9 passed, 213 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q -k 'claude or annotation_agent or unblock'` -> `45 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `750 passed in 79.48s`。
  - `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2a_all.deb`。
  - `command -v waygate && waygate --version` -> `/home/lichangkun/.local/bin/waygate`, `waygate 0.6.2a`；user-level wrapper points `WAYGATE_LIB_DIR` at this worktree. `waygate doctor` reports this intended PATH shadow as a warning because `/usr/bin/waygate` still exists.
  - Extracted `dist/waygate_0.6.2a_all.deb` and verified packaged code contains `--no-session-persistence`, `path / assertion focus`, `journey_contract_required`, and Journey feedback fields.
- Live V2.1 recovery:
  - Deterministic final Requirements preflight now passes; live diagnostic against `approvals/requirements-and-acceptance.md` extracts 10 unique active Journey rows with valid steps/layers.
  - Normal `waygate drive --max-steps 1` advanced Product Design, Architecture, Test Strategy, and final assembly without manual `session.json` edits.
  - Claude Code 2.1.152 still returned `API Error: 400 The content[].thinking in the thinking mode must be passed back to the API` for the full annotation prompt even with `--bare --no-session-persistence`; live recovery used the documented backend override path: `waygate unblock ...` then `waygate run --annotation-agent requirements=codex`.
  - `requirements_annotation` completed with backend `codex`, `requirements-annotations.json` status `completed`, 8 risk items, gate hash `sha256:186864312a6ab6e706c88e15879d6b50fdd211cb3fbca93edfcb5ab38d9f17af`; approval file now contains `## Annotation Agent 风险批注`.
  - Final live state: `status=active`, `currentStep=WAITING_REQUIREMENTS_ACCEPTANCE`, `blockedReason=None`, `pendingAnnotationBeforeHumanGate=None`, `nextAction=check_requirements_acceptance`.

### Controller Requirements Auto-Rework 整改
- **状态：** implementation verified; focused/full regression passed; package rebuilt; user-level `waygate` synced.
- 修复：staged Requirements final preflight 的 controller-validation-only 自动打回现在以 controller validation error 作为路由主依据，不再让旧 final gate 正文里的 Scope/E2E 文本抢走 Product Design 问题；`requirements_staged_revision_routed` event 记录 `reason_key`、`routing_source` 和 `routing_reason`。
- 修复：controller validation feedback 写入短而精确的 `requirementsRevisionFeedback`，包含原始 reason、归属 stage、reason key、缺失字段和期望输出示例，避免把完整旧 Requirements gate 当作路由依据。
- 修复：final Requirements preflight 接受通过 `validate_prototype_review_manifest(..., require_clickable=True)` 的 manifest 作为 clickable webpage prototype evidence；Product Design 文本中的 artifact-local clickable HTML、manifest path、page states、click path 和 AC/Journey mapping 也会被识别为文本证据；manifest 缺文件、缺字段、unsupported kind 等严格规则保持阻断。
- 修复：未批准 Requirements 的同类 final preflight 内容失败超过 `requirementsAutoRevisionMax` 后进入 `blockedContext.category=requirements_contract`，guidance 走 `waygate revise --gate requirements --reason ...`，不允许用普通 `retry` / `unblock` 清除。
- 文档：同步 `docs/workflow/staged-requirements-package-policy.md` 和 `docs/architecture/staged-requirements-package-architecture.md`，记录 controller-validation routing source、clickable manifest evidence 和 hard-block category 边界。
- 验证：
  - RED: 新增 focused tests 初始 `4 failed`，分别复现 valid clickable manifest 被忽略、artifact-local Product Design 文本不被识别、Product Design controller reason 被旧 Scope/E2E gate 文本误路由、同类 Requirements preflight 超预算缺 `requirements_contract` blocked context。
  - GREEN: 同一 focused tests -> `4 passed`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'prototype or stage_validation or auto_revision or product_design'` -> `37 passed, 36 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'requirements_auto_revision or stage_validation'` -> `3 passed, 219 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `73 passed`。
  - `python3 -m pytest workflow_controller/tests/test_prototype_review.py -q` -> `11 passed`。
  - `python3 -m pytest workflow_controller/tests/test_v061_docs.py workflow_controller/tests/test_packaging.py -q -k 'docs or package_version or staged_requirements'` -> `7 passed, 3 deselected`。
  - `python3 -m pytest workflow_controller/tests -q` -> `745 passed in 78.15s`。
  - `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2a_all.deb`。
  - `which waygate && waygate --version` -> `/home/lichangkun/.local/bin/waygate`, `waygate 0.6.2a`；user-level wrapper points `WAYGATE_LIB_DIR` at this worktree because system `/usr/lib/waygate` could not be updated without sudo.
  - Extracted `dist/waygate_0.6.2a_all.deb` and verified packaged code/docs contain `routing_source`, `Original reason:`, `artifact-local clickable html`, and `blockedContext.category=requirements_contract` policy text.

### Staged Test Strategy auto-rework 整改
- **状态：** implementation verified; focused/full regression passed.
- 修复：Requirements Test Strategy Brief prompt 明确 `Environment Kind` 只能是 `local_real` / `production_readonly`，并补齐真实入口、具体 user/API/service steps、fixture/setup、核心业务 API 不得 mock/stub、machine-checkable assertions 和截图不能作为唯一断言的 validator 级合同。
- 修复：未批准 Requirements 的 staged checkpoint validation failure 不再立即 hard block；tmux-backed runner 会自动打回同一 checkpoint，写入 `Controller stage validation feedback` 到 `requirementsRevisionFeedback`，失效当前 stage 及下游 artifact，并记录 `requirements_stage_auto_revision_requested`。连续同类原因超过 `requirementsAutoRevisionMax` 后才进入 `requirements_stage_validation` blocked；已批准 Requirements 仍直接 hard block，不自动改合同。
- 文档：同步 `docs/workflow/staged-requirements-package-policy.md` 和 `docs/architecture/staged-requirements-package-architecture.md`，记录 stage validation auto-rework、预算边界和 Test Strategy 4.6 prompt/validator 对齐。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'validator_level_4_6_contract or stage_validation_failure_auto_reworks or stage_validation_auto_rework_blocks or stage_validation_does_not_auto_rework'` -> `3 failed, 1 passed`，分别复现 prompt 缺 validator 级要求、stage validation 直接 blocked。
  - GREEN: 同一命令 -> `4 passed, 66 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'test_strategy_prompt or stage_validation or auto_revision'` -> `25 passed, 45 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'requirements_auto_revision or stage_validation'` -> `3 passed, 219 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `89 passed`。
  - `python3 -m pytest workflow_controller/tests/test_v061_docs.py workflow_controller/tests/test_packaging.py -q -k 'docs or package_version or staged_requirements'` -> `7 passed, 3 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_claude_runner_fails_fast_when_pane_returns_idle_after_dispatch -q` -> `1 passed in 1.20s`（复核一次 full run 中的非复现 tmux idle timing failure）。
  - `python3 -m pytest workflow_controller/tests -q` -> `742 passed in 78.87s`。
  - `git diff --check` -> passed。

### Waygate Block / 返工边界补充
- **状态：** implementation verified; focused/full regression passed.
- 修复：annotation artifact normalizer 会解析包在 `summary` 字符串中的 JSON，并把嵌套 `summary` / `issues[]` 提升到顶层，保证终端风险数量、Plannotator review block 和 artifact `issues[]` 一致。
- 修复：Final Scope Audit AO coverage 增加 `coverage_status=covered|uncovered` 和 `ledger_status`，Markdown 使用 coverage status 表达证据覆盖，避免 `AO.status=open` 被误读为未覆盖。
- 修复：blocked guidance 输出 `类别`，长 `blocker(s)` 列表只展示前 3 条并指向完整 artifact；恢复命令继续按 category 路由到 `unblock`、`revise --gate unit-plan`、`revise --gate requirements` 或 Final Acceptance rejection route。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py::test_annotation_artifact_promotes_json_embedded_in_summary -q` -> failed，`summary` JSON 未提升。
  - RED: `python3 -m pytest workflow_controller/tests/test_scope_audit.py::test_scope_audit_records_coverage_status_separately_from_ledger_status -q` -> failed，缺少 `ledger_status` / `coverage_status`。
  - RED: `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_blocked_guidance_shows_category_and_compacts_long_blocker_lists -q` -> failed，guidance 未显示 category。
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py::test_annotation_nonapproval_rejects_approval_fields_embedded_in_summary_json -q` -> failed，`summary` JSON 中的 approval-like field 未被拒绝。
  - GREEN: 上述 4 条测试均通过。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'final_acceptance_rejection or generated_final_rejection or annotation or scope_audit'` -> `7 passed, 215 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `89 passed`。
  - `python3 -m pytest workflow_controller/tests/test_scope_audit.py -q` -> `8 passed`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `66 passed`。
  - `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q` -> `43 passed`。
  - `python3 -m pytest workflow_controller/tests/test_v061_docs.py workflow_controller/tests/test_packaging.py -q -k 'docs or package_version'` -> `7 passed, 3 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_codex_retries_submit_when_agent_is_not_working_after_submit -q` -> `1 passed`（复核一次 full run 中的非复现 tmux-codex runner sleep 计数失败）。
  - `python3 -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `41 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `738 passed in 77.63s`。
  - `git diff --check` -> passed。

## 会话：2026-05-27

### Final Acceptance rejection AO 污染修复与 Classroom V0.4 恢复
- **状态：** implementation verified; live Classroom V0.4 recovered to `WAITING_FINAL_ACCEPTANCE`.
- 根因：Final Acceptance rejection 路径曾把完整生成式 final gate 正文作为 `final_acceptance_rejection` feedback 写入 Acceptance Obligation Ledger。用户只选择 rejection route、未写具体返工说明时，证据摘要、文件列表、Final Scope Audit、Journey Matrix、人工走查步骤和默认提示语被拆成 AO-008..AO-089，导致下一轮 Final Scope Audit 误报大量 active must AO 缺 evidence row。
- 修复：Final Acceptance rejection 只把人工提交的 Plannotator feedback、`## 修改清单` 和非默认 `## 返工说明` 转成 AO；默认说明文字不再生成 AO。新增 legacy cleanup，将旧版本生成式 final gate 内容类 AO 自动标记为 `out_of_scope`，保留审计记录但不再作为 active must AO；若当前 blocker 仅由这些生成式 AO 触发，controller 会重新跑 Final Scope Audit 并清除 blocker。
- Live V0.4：通过 2 号 tmux controller pane 使用本 worktree `WAYGATE_LIB_DIR` 重新 `waygate go`；状态从 `blocked / FINAL_WALKTHROUGH_PREPARE` 恢复到 `active / WAITING_FINAL_ACCEPTANCE`，`blockedReason=None`，`final_acceptance_rejection` open AO 为 0，旧生成式 final rejection AO 关闭 82 条。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'final_acceptance_rejection_ignores_default_rejection_notes_instruction or status_closes_legacy_generated_final_rejection_obligations'` -> failed，默认 `返工说明` 提示语被写成 AO，旧生成式 final gate AO 仍 active。
  - GREEN: 同一命令 -> `2 passed, 219 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'final_acceptance_rejection or generated_final_rejection or acceptance_obligation'` -> `8 passed, 213 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `89 passed`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `66 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `734 passed in 75.32s`。
  - `git diff --check` -> passed。
  - `python3 -m py_compile workflow_controller/acceptance_obligations.py workflow_controller/rrc_controller.py workflow_controller/tests/test_rrc_controller.py` -> passed。

### Unit Plan annotation 中断后的草案恢复修复
- **状态：** implementation verified; live Classroom V0.4 pending recovery ready via fixed controller.
- 根因：Unit Plan draft 已生成、`approvals/unit-plan.md` 已通过 controller preflight 后，controller 在进入 `unit_plan_annotation` 前没有先保存 `currentStep=WAITING_UNIT_PLAN_APPROVAL` / `unitPlanDraftGenerated=true`。人工中断 annotation 后，`session.json` 仍停在 `UNIT_PLAN_DRAFT`，下次 `go` 会重派 Unit Plan drafter；drafter 启动时删除旧 `unit-plan-body.md`，若重复派发没有重新写 body，就报 `Unit plan drafter did not write .../unit-plan-body.md`。
- 修复：`run_unit_plan_drafter` action 在重派 drafter 前先检查已有 `approvals/unit-plan.md`；若 gate 存在、比 Requirements gate 新、无 Unit Plan revision feedback、且通过同一套 Unit Plan validator，则恢复 `artifacts/unit-plan-draft/unit-plan-body.md` / `unit-plan-draft-summary.json` 并继续进入 Unit Plan human gate，不再重派 drafter。Unit Plan preflight 通过后、annotation 运行前先保存 pending human-gate state 和 `pendingAnnotationBeforeHumanGate`，后续中断重启会接回 gate 并重跑/跳过 annotation，而不是回到草案生成。
- Live V0.4：当前 live state 仍是 `UNIT_PLAN_DRAFT` / `unitPlanDraftGenerated=false`，但已有有效 `approvals/unit-plan.md` 和 `unit_plan_gate_preflight_completed` 历史；使用本 worktree `WAYGATE_LIB_DIR` 重启应走恢复路径，不手改 `session.json`。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py::test_unit_plan_draft_reuses_valid_gate_after_annotation_interruption -q` -> failed，旧逻辑错误调用 Unit Plan drafter。
  - GREEN: 同一测试 -> `1 passed`。
  - `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q` -> `41 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'unit_plan_draft or unit_plan_gate_preflight or unit_plan_approval or annotation'` -> `23 passed, 195 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `66 passed`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `89 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `730 passed in 74.34s`。
  - `git diff --check` -> passed。
  - `python3 -m py_compile workflow_controller/rrc_controller.py workflow_controller/annotation_agents.py workflow_controller/tests/test_v061_annotation_agents.py` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2a_all.deb`。

### Annotation timeout bytes 输出序列化修复
- **状态：** implementation verified; live Classroom V0.4 Requirements gate recovered past annotation timeout warning and advanced to Unit Plan draft.
- 根因：`subprocess.TimeoutExpired.output` / `stderr` 在 Python 3.12 中即使 `text=True` 也可能保持为 `bytes`；annotation timeout warn 路径把这些 bytes 直接写入 failure artifact，`json.dumps()` 因 `Object of type bytes is not JSON serializable` 崩溃，导致已通过 deterministic Requirements preflight 的 live gate 被 runner 运行时问题挡住。
- 修复：`workflow_controller/annotation_agents.py` 的 `_redact_text()` 统一接受 `str | bytes | None`，先把 bytes 按 replacement error handling 解码为字符串，再做 secret redaction；annotation 和 verification-assist timeout/failure 路径共享该归一化。
- Live V0.4：使用本 worktree 代码重启 2.0，`requirements_gate_preflight_completed` 继续通过；Requirements annotation 5s timeout 按 `failure_policy=warn` 写入 warning artifact；随后通过 controller 人工 gate approve 路径进入 `UNIT_PLAN_DRAFT`，未手改 `.rrc-controller-v0.4/session.json`。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py::test_annotation_config_safety_rejects_invalid_backend_unavailable_timeout_and_redacts_env_values -q` -> failed，复现 `Object of type bytes is not JSON serializable`。
  - GREEN: 同一测试 -> `1 passed`。
  - `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q -k 'timeout or annotation_config_safety or failure_policy or requirements_gate_preflight_completed'` -> `5 passed, 35 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q` -> `40 passed`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `66 passed`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `89 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `729 passed in 75.35s`。
  - `git diff --check` -> passed。
  - `python3 -m py_compile workflow_controller/annotation_agents.py workflow_controller/journeys.py workflow_controller/gates/validators/__init__.py workflow_controller/gates/generators/__init__.py workflow_controller/scope_audit.py` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2a_all.deb`。
  - `sudo -n dpkg -i dist/waygate_0.6.2a_all.deb` -> failed，原因是 sudo 需要密码；live 运行继续通过 `WAYGATE_LIB_DIR` 使用本 worktree 修复代码。

### Requirements Journey 表头与 support layer 解析修复
- **状态：** implementation in progress; focused RED/GREEN passed; live Classroom V0.4 Journey contract diagnostic now recognizes `User steps` and `regression` Journey layer.
- 根因：Journey contract parser 只接受 `Steps` 表头和 `functional/integration/e2e/manual` Journey layer；Classroom V0.4 Scope 使用合法的 `Journey id`、`User steps`、`Linked AC` 表头和 `J-V04-006 Verification Layer=regression`，因此 final Requirements preflight 误报所有 Journey missing steps，并误报 J-V04-006 missing valid verification layer。
- 修复：`workflow_controller/journeys.py` 接受 `User steps`、`Journey id`、`Linked AC` 等常见 Journey 表头别名，Journey layer 归一化为 behavioral + support layer；`workflow_controller/gates/validators/__init__.py` 在收集 active e2e Journey 做 4.6 覆盖时也接受同一类表头别名。`static/regression/prerequisite` Journey 是合法非 E2E support layer，只有 `e2e` 触发 4.6 real E2E strictness。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'user_steps_and_support_layers or journey_header_aliases'` -> failed，分别误报 `missing steps / missing valid verification layer` 和 E2E Journey 未映射。
  - GREEN: 同一命令 -> `2 passed, 63 deselected`。
  - live Classroom V0.4 diagnostic -> `J-V04-001..005` steps recognized，`J-V04-006 layer=regression`，`journey contract ok`。

### Requirements support layer 解析修复
- **状态：** implementation verified; focused/full regression passed; live Classroom V0.4 Scope artifact parser diagnostic now recognizes support layers.
- 根因：Requirements AC layer parser 只接受 `unit`、`functional`、`integration`、`e2e`、`manual` 五类，导致 Classroom V0.4 Scope 中合法的 `static`、`regression`、`prerequisite` 被当作 missing verification layer。现场表现为 final Requirements preflight 报 `AC-V04-008` 至 `AC-V04-013 missing verification layer`。
- 修复：`_normalize_requirements_verification_layer()` 和 direct inline / leading layer / structured marker regex 接受 Requirements-stage support layers：`static`、`regression`、`prerequisite`（含中文静态、回归、前置）。这些 layer 满足 Requirements 分类完整性，但仍作为非 E2E 处理；只有 `e2e` 触发 4.6 real E2E strictness。
- Prompt / docs：legacy Requirements gate template、Requirements prompt、staged Scope prompt、staged workflow / architecture 文档均同步说明行为验证层与 Requirements 辅助层边界，避免后续 agent 为过 gate 把支撑 AC 硬改成 `integration` 或 `e2e`。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py::test_staged_requirements_preflight_accepts_static_regression_and_prerequisite_layers -q` -> failed，误报 `AC-V04-008`、`AC-V04-009`、`AC-V04-010`、`AC-V04-011`、`AC-V04-013 missing verification layer`。
  - GREEN: 同一测试 -> `1 passed`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'static_regression_and_prerequisite or does_not_promote_prerequisite or explanatory_table or explicit_verification_tag'` -> `4 passed, 59 deselected`。
  - live Classroom V0.4 Scope diagnostic -> `AC-V04-008/009/010/012 static`，`AC-V04-011 regression`，`AC-V04-013 prerequisite`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `63 passed`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `89 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `726 passed in 74.81s`。

### Requirements explanatory table AC layer 解析修复
- **状态：** implementation verified; focused regressions passed; live Classroom V0.4 final gate AC layer conflict no longer reproduces with fixed parser.
- 根因：上一轮 AC/layer 列感知修复只覆盖了带 `AC id` + `verification layer` 表头的正式表格；普通说明表仍会对单元格执行“发现一个 `[verification: e2e]` 就把该单元格所有 AC 都标成 e2e”的回退逻辑。Classroom V0.4 的 visible-surface / API visible output 说明表在同一说明单元格里写 direct e2e AC 和 integration AC，导致 `AC-V04-003` 至 `AC-V04-007` 被误报为 `['e2e', 'integration']`。
- 修复：无正式 AC/layer 表头的 Markdown 表格只接受 direct inline AC marker（例如 `AC-... [verification: e2e]`）对应的同一个 AC，不再把 layer marker 扩散到同一单元格或整行里的其他 AC。非表格行也优先按 direct inline marker 配对；多 AC 的行级 layer 只在明确 layer bucket 行首时才扩散。
- 文档：同步 `docs/workflow/staged-requirements-package-policy.md` 和 `docs/architecture/staged-requirements-package-architecture.md`，明确 explanatory surface / coverage / support tables 不创建跨 AC layer facts。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py::test_package_consistency_does_not_promote_explanatory_table_references_to_e2e -q` -> failed，误报 `AC-09: ['e2e', 'integration']`。
  - GREEN: 同一测试 -> `1 passed`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'does_not_promote_prerequisite or explanatory_table or explicit_verification_tag'` -> `3 passed, 59 deselected`。
  - live Classroom V0.4 final gate parser diagnostic against `/home/lichangkun/code/classroom/.rrc-controller-v0.4/approvals/requirements-and-acceptance.md` -> `no conflicts`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `62 passed`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `89 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `725 passed in 74.95s`。
  - `git diff --check` -> passed。
  - `python3 -m pytest workflow_controller/tests/test_v061_docs.py workflow_controller/tests/test_packaging.py -q -k 'docs or package_version'` -> `7 passed, 3 deselected`。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2a_all.deb`。
  - `dpkg-deb --field dist/waygate_0.6.2a_all.deb Package Version Architecture Depends` -> `waygate / 0.6.2a / all / python3`。

### Requirements AC 表格 verification layer 解析修复
- **状态：** implementation verified; focused regressions passed; live Classroom V0.4 Test Strategy artifact passes fixed stage validation.
- 根因：`AC` 表格行按整行解析 verification marker；当 `AC-V04-013` 自身 `verification layer=prerequisite`，但 expected/setup 单元格引用 `AC-V04-001 [verification: e2e]` / `AC-V04-002 [verification: e2e]` 时，validator 会把该 prerequisite 行误判为 e2e，并要求 `AC-V04-013` 也写 4.6 E2E row。
- 修复：AC/layer 解析改为 Markdown 表格列感知；带 `AC id` + `verification layer` 的表格只用 AC 单元格和 layer 单元格建立映射，其他说明单元格里的 AC 引用不再提升当前行 AC 的 layer。非表格和无 layer 表格继续支持 cell-local `[verification: ...]` 标记。
- Live V0.4：`AC-V04-013` 不再进入 e2e AC 集合；当前 Test Strategy 只需要 `AC-V04-001`、`AC-V04-002`、`AC-V04-014` / `J-V04-001`、`J-V04-002`、`J-V04-005` 的 4.6 row。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py::test_test_strategy_stage_validation_does_not_promote_prerequisite_row_references_to_e2e -q` -> failed，误报 `AC-V04-013 missing Requirements 4.6 E2E review matrix row`。
  - GREEN: 同一测试 -> `1 passed`。
  - `PYTHONPATH=/home/lichangkun/works/ai-works/worktrees/workflow-controller-v0.6.2 python3 - <<'PY' ... validate_staged_requirements_stage_output(...) ... PY` against `/home/lichangkun/code/classroom/.rrc-controller-v0.4` -> `stage validation ok`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `61 passed`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `89 passed`。

### Staged Requirements explicit verification tag parser 修复
- **状态：** implementation verified; focused/full regression passed.
- 根因：staged Requirements final preflight 的 conflicting AC layer 检查只处理含 `[verification: ...]` 的行，但 `_requirements_verification_layer_from_line()` 对 Markdown 表格先按自然语言 cell alias 取 layer；当同一行在说明列写 `service/API E2E`、而 AC cell 明确写 `AC-V04-001 [verification: e2e]` 时，`API` 会先被归一成 `functional`，导致同一 AC 被误报为 `['e2e', 'functional']`。
- 修复：verification layer 解析现在优先读取显式结构化标记（`verification layer=...`、中文验证层、`[verification: ...]`、`(e2e)`），再回退到表格 cell / 行首自然语言 alias；显式 AC layer 不再被 API/browser 等说明文字覆盖。
- 现场影响：Classroom V0.4 final Requirements preflight 中 `AC-V04-001`、`AC-V04-002`、`AC-V04-014` 的误报属于工具侧解析问题，不应要求删除真实 API/service E2E 说明。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py::test_package_consistency_prefers_explicit_verification_tag_over_api_text -q` -> failed，误报 `AC-08: ['e2e', 'functional']`。
  - GREEN: 同一测试 -> `1 passed`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `60 passed`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `89 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `723 passed in 82.27s`。
  - `git diff --check` -> passed。

### Staged Requirements stage-validation recovery 修复
- **状态：** implementation verified; focused/full regression passed.
- 根因：stage validation blocker 只允许解除阻塞重跑当前 checkpoint，且 unblock 后没有把上一轮 validator error 明确注入下一次 staged prompt；当真实问题是 AC/Journey/Requirements 合同需要上游 Scope 修订时，`waygate revise --gate requirements` 又会被当前阶段限制拒绝，导致用户只能手工改 artifact 或重建 state。
- 修复：`requirements_stage_validation` blocker 现在在 `unblock` 时把 controller stage-validation feedback 写入 `requirementsRevisionFeedback`，下一次 checkpoint prompt 会看到具体 validator error；同类 blocker 下也允许 `waygate revise --gate requirements --reason ...`，并用 semantic routing 把 AC/Journey contract change 回到 Scope。终端 guidance 改为默认 unblock 重跑，合同变更时走 Requirements revise。
- 文档：同步 staged Requirements workflow / architecture 文档，明确 stage validation 的两条恢复路径和 unblock feedback 注入行为。
- 验证：
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'stage_validation_unblock_injects or revision_allowed_from_staged_stage_validation_blocker'` -> `2 passed`。
  - `python3 -m py_compile workflow_controller/rrc_controller.py workflow_controller/requirements_revision_routing.py` -> passed。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `59 passed`。
  - `python3 -m pytest workflow_controller/tests/test_v061_docs.py workflow_controller/tests/test_packaging.py -q -k 'docs or package_version or staged_requirements'` -> `7 passed, 3 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py -q -k 'unblock or revise_requirements or requirements_stage_validation or staged'` -> `18 passed`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `89 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `722 passed in 75.12s`。
  - `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2a_all.deb`。
  - `dpkg-deb --field dist/waygate_0.6.2a_all.deb Package Version Architecture Depends` -> `waygate / 0.6.2a / all / python3`。
  - `sudo -n dpkg -i dist/waygate_0.6.2a_all.deb` -> failed，原因是 sudo 需要密码；系统 `/usr/bin/waygate` 未由本轮安装替换。

### Requirements 4.6 / Unit Plan 职责边界修复
- **状态：** implementation verified; focused/full regression passed; Debian package rebuilt.
- 根因：V0.6.2 staged Requirements 把 Unit Plan 的 exact command / test case / fixture script 职责提前压到 Requirements Test Strategy 4.6，导致只写 command intent 的合法 Test Strategy 被拦截；同时 4.6 row 覆盖要求把 e2e AC 与 active e2e Journey 重复计算，prototype-only artifact review 也可能被误吸进 real E2E command strictness。
- 修复：4.6 `Verification Command` 改为校验非占位 command intent / command family / runner intent，继续拒绝空值、`待 Unit Plan 补充`、`pytest`、`playwright test` 和无工具/组件/验证意图的“后续测试验证”；错误文案改为 exact command 属于 Unit Plan。
- 覆盖语义：active e2e Journey 仍必须有 4.6 row；该 Journey row 映射的 e2e AC 不再强制重复独立 row；未被 Journey row 覆盖的 e2e AC 仍需独立 row。
- prototype 边界：prototype-only artifact review 不再触发 real E2E 4.6 command strictness；它继续通过 Product Design prototype manifest 和 Unit Plan prototype conformance 合同承接。
- Prompt / docs：Requirements Test Strategy prompt、legacy Requirements prompt、Unit Plan handoff prompt、正式 workflow / architecture 文档已同步，明确 4.6 写命令意图，exact command / test case / fixture 初始化脚本 / evidence row 归 Unit Plan。
- 验证：
  - RED: 新增 focused tests 初始失败，表现为 command intent 被拒绝、e2e AC 被要求重复 row、prototype-only review 被当作 E2E 映射缺口、错误文案仍是 concrete executable command。
  - GREEN: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'command_intent or journey_row_covers or prototype_only_review or staged_prompts_anchor'` -> `4 passed, 53 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q -k 'command_intent or placeholder_or_generic_command_intent'` -> `4 passed, 85 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `57 passed`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `89 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py -q -k 'requirements_prompt_includes_acceptance_quality_contracts or 4_6 or e2e'` -> `2 passed, 73 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_v061_docs.py -q` -> `6 passed`。
  - `python3 -m pytest workflow_controller/tests/test_packaging.py -q -k 'docs or package_version'` -> `1 passed, 3 deselected`。
  - `python3 -m pytest workflow_controller/tests -q` -> `720 passed in 74.86s`。
  - `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2a_all.deb`。
  - `dpkg-deb --field dist/waygate_0.6.2a_all.deb Package Version Architecture Depends` -> `waygate / 0.6.2a / all / python3`。

### Requirements staged checkpoint validation 前移
- **状态：** implementation verified; focused/full regression passed; Debian package rebuilt.
- 根因：final Requirements gate 的 `validate_requirements_acceptance_quality()` 已能拒绝非 canonical E2E/browser 映射，但 Scope、Product Design、Architecture、Test Strategy 四个 staged checkpoint 生成后没有统一 deterministic stage-output validation，导致 `Status=是`、`Verification Layer=real integration + DB assertion`、非固定 `## 4.6` E2E 表和未知 AC/Journey 引用会拖到 final gate 才暴露。
- 修复：新增 `validate_staged_requirements_stage_output()` 并接入 `run_requirements_package_stage()`；Scope 立即拒绝未映射到 canonical e2e AC / active e2e Journey 的 E2E/browser/prototype review；Product Design manifest 和 surface contracts 必须引用 Scope 已定义 AC/Journey；Architecture 不得引用未知 ID，继承 E2E/browser/prototype handoff 时必须引用 Scope canonical e2e ID；Test Strategy 必须使用固定 `## 4.6 E2E 测试方法与前置依赖矩阵（E2E Test Method & Prerequisite Matrix）` 和固定 11 列覆盖所有 e2e AC / active e2e Journey。
- Prompt / feedback：Scope prompt 增加 exact `Status=active` / `Verification Layer=e2e` 示例；Test Strategy prompt 增加固定 4.6 表头和 11 列要求；staged prompt 会注入 controller revision feedback，并对 E2E/browser blockers 附带 canonical 示例，避免 agent 继续产出人类可读但机器不认的表。
- Unit Plan：确认 draft preflight 和 human approval revalidation 继续共用 `_apply_and_validate_unit_plan_gate()`；补回归证明无效 Unit Plan draft 不会进入 annotation 或人工 gate。
- 已完成 focused 验证：
  - RED: 新增 staged validation tests 初始因缺少 `validate_staged_requirements_stage_output` import 失败。
  - GREEN: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py workflow_controller/tests/test_v061_annotation_agents.py -q -k 'stage_validation or e2e_mapping_blocker or auto_revision_routes_declares or unit_plan_draft_preflight_blocks_annotation'` -> `11 passed, 83 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `54 passed`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_v061_annotation_agents.py -q -k 'stage_validation or e2e or unit_plan_approval or requirements_auto_revision or staged or unit_plan_draft_preflight_blocks_annotation'` -> `75 passed, 237 deselected`。
- 回归验证：
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py workflow_controller/tests/test_rrc_controller.py -q -k 'stage_validation or e2e or unit_plan_approval or requirements_auto_revision or staged'` -> `73 passed, 199 deselected`。
  - `python3 -m pytest workflow_controller/tests -q` -> `713 passed in 81.44s`。
  - `python3 -m pytest workflow_controller/tests/test_v061_docs.py -q` -> `6 passed`。
  - `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2a_all.deb`。

### Requirements auto-revision counter persistence rollback
- **状态：** implementation verified; focused/full regression passed; Debian package rebuilt.
- 根因：上一轮把 `requirementsAutoRevisionLastReasonKey`、`requirementsAutoRevisionConsecutiveCount` 和 `requirementsAutoRevisionTotalCount` 持久化到 `session.json` 后，旧 controller 进程留下的计数会污染下一次 `waygate go`。当旧 state 中同一 semantic reason 已达到上限时，新一轮 Requirements preflight 会一次就进入 `blocked`，而不是先给新的 Requirements revise/go 完整自动打回预算。
- 修复：Requirements 自动打回计数改为 `RalphRefinerController` 实例内临时状态；`_auto_revise_invalid_requirements_draft()` 不再从 `session.json` 读取或写回三项计数字段；`_save_state()` 会清理旧 session 中残留的三项字段；人工 `waygate revise --gate requirements` 会重置进程内计数；事件仍记录 `attempt` / `total_attempt` 作为审计历史。
- 保留边界：同一 controller 进程 / 单次 `waygate go` 内，同一 semantic key 连续超过 `requirementsAutoRevisionMax` 仍会 block；已经 `blocked` 的 workflow 不会被直接 `go` 自动清除，仍需要显式 `revise`、`unblock` 或既有恢复动作。
- 未修改 live `.rrc-controller-*` state；本 worktree 当前没有 `.rrc-controller-*` state-dir。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'auto_revision'` -> `3 failed, 3 passed`，旧实现表现为读取旧计数直接 block、session 继续保留计数字段、人工 revise 后旧字段仍存在。
  - GREEN: 同一 auto-revision focused subset -> `6 passed, 39 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py workflow_controller/tests/test_rrc_controller.py -q -k 'requirements_auto_revision or staged'` -> `49 passed, 214 deselected`。
  - `python3 -m pytest workflow_controller/tests -q` -> `703 passed in 81.35s`。
  - `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2a_all.deb`。

### Requirements versioned ID parser / false-flag no-UI regression
- **状态：** implementation verified; focused/full regression passed; Debian package rebuilt; classroom Requirements recovery rerun reached a real content blocker.
- 根因：多个 Requirements / prototype / Journey / evidence validator 仍使用旧的 numeric-only `AC-\d+` / `J-\d+` 提取规则，导致 `AC-V04-001` / `J-V04-001` 这类版本化 ID 被当作 unknown 或 unmapped；同时 false-flag no-UI detector 把“不能把 false flag 当作不需要 UI/原型的证据”这类拒绝语句误判成 no-UI basis。
- 修复：新增共享 `workflow_controller/requirements_ids.py`，统一提取支持字母、数字、下划线和短横线的 AC/Journey ID，并过滤 `AC-ID` 等占位符；prototype manifest、Requirements validator、Journey、evidence policy 和 controller change-request impact 均改用或对齐该规则；`requirements_surface_uses_false_flag_as_no_ui_basis()` 在文本明确否定 false flag 可作为 no-UI 依据时不再误报。
- Classroom V0.4：已使用本 worktree 代码重新走 Requirements staged revise/go；当前 `.rrc-controller-v0.4/session.json` 仍为 `status=blocked` / `currentStep=WAITING_REQUIREMENTS_ACCEPTANCE`，但旧误报已消失。剩余 blocker 是真实内容缺口：Requirements 声明 E2E/browser review，但没有 `layer=e2e` AC 或 active Journey，且没有 fixed-column `## 4.6` E2E matrix rows。诊断结果：`e2e_ac_ids=[]`、`e2e_journey_ids=[]`、`explicit_e2e=True`、`4.6_rows=0`。
- 系统安装未完成：`sudo -n dpkg -i dist/waygate_0.6.2a_all.deb` 返回 `sudo: a password is required`。当前 `/usr/bin/waygate --version` 显示 `waygate 0.6.2a`，但本轮无法替换系统包；package artifact 已重新生成。
- 验证：
  - `python3 -m pytest workflow_controller/tests/test_prototype_review.py workflow_controller/tests/test_requirements_staged_package.py -q` -> `54 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `701 passed in 80.79s`
  - `git diff --check` -> passed
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2a_all.deb`
  - `dpkg-deb --field dist/waygate_0.6.2a_all.deb Package Version Architecture Depends` -> `waygate / 0.6.2a / all / python3`
  - `dpkg-deb --contents dist/waygate_0.6.2a_all.deb | rg 'requirements_ids\.py|requirements_revision_routing\.py|requirements_surface\.py'` -> required modules included

### Waygate blocked state human gate control-flow regression
- **状态：** implementation verified; focused/full regression passed; Debian package rebuilt.
- 根因：`drive()` 在 Requirements / Unit Plan 自动打回后没有立即尊重 `blocked/done/failed` terminal state；当 `_auto_revise_invalid_requirements_draft()` 达到上限并写入 `status=blocked` 时，后续 `_pending_gate_info()` 仍按 `currentStep=WAITING_REQUIREMENTS_ACCEPTANCE` 生成人工 gate，`_handle_drive_gate()` 随后发送 tmux “进入人工评审”提醒并展示误导性的 `[人工确认] 需求与验收` 菜单。
- 修复：新增 terminal status 集合并让 `drive()` 在自动打回后立即停止到 terminal guidance；`_pending_gate_info()` 对 `blocked/done/failed` 返回 `None`；`_handle_drive_gate()` 和 `_send_human_review_tmux_reminder()` 在发送提醒或展示菜单前重新读取/检查 terminal state；Requirements / Unit Plan gate validation refresh 不再覆盖 terminal blocked reason。
- 已保留 annotation 语义：invalid deterministic preflight blocked 后不运行 annotation；只有 preflight 通过、进入真实人工 gate 前才运行 annotation。
- 未修改 classroom live state，未手改 `.rrc-controller-v0.4/session.json`，未执行 live recovery。
- 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py::test_drive_staged_requirements_auto_revision_blocked_stops_without_human_gate_or_annotation -q` -> failed，表现为输出包含 `[人工确认] 需求与验收`。
  - GREEN: 同一测试 -> `1 passed`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'auto_revision or drive or blocked'` -> `4 passed, 37 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'requirements_auto_revision or staged or annotation'` -> `5 passed, 213 deselected`。
  - `python3 -m pytest workflow_controller/tests -q` -> `698 passed in 79.75s`。
  - `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2a_all.deb`。
  - `dpkg-deb --field dist/waygate_0.6.2a_all.deb Package Version Architecture Depends` -> `waygate / 0.6.2a / all / python3`。

### Staged Requirements semantic routing / auto-revision persistence
- **状态：** implementation verified; focused/full regression passed; Debian package rebuilt.
- 根因：staged Requirements revision routing 仍以自然语言 reason 的关键词顺序决定 checkpoint；真实 validator 文案 `does not map it to an e2e AC or active e2e Journey` 未被识别为 Scope blocker，随后被同一 reason 中的 prototype/Web/page states 关键词路由到 Product Design。Test-method quality reason 中的 `core API stubs` 也可能因 `API` 被误吸到 Architecture。
- 另一个根因：`_auto_revise_invalid_requirements_draft()` 的 consecutive/total attempt 计数是函数局部变量；staged route 返回后下一轮 `go` 会从 1 重新计数，导致同一 semantic issue 跨 checkpoint cycle 无限打回。
- 已新增 `workflow_controller/requirements_revision_routing.py`，用 `RequirementsRevisionIssue`、`classify_requirements_revision_reason()`、`select_requirements_revision_stage()` 和 `requirements_auto_revision_semantic_key()` 统一分类与 key 生成；路由优先级固定为 `scope > product_design > architecture > test_strategy`。
- 已让 `_staged_requirements_revision_stage_from_feedback()` 调用语义路由，并让 Requirements auto-revision 把 `requirementsAutoRevisionLastReasonKey`、`requirementsAutoRevisionConsecutiveCount`、`requirementsAutoRevisionTotalCount` 写入 `session.json`；同一 semantic key 超过 `requirementsAutoRevisionMax` 时 block，preflight 通过后清理这些内部字段。
- 已同步 `docs/workflow/staged-requirements-package-policy.md`、`docs/architecture/staged-requirements-package-architecture.md` 和 `findings.md` 的路由/计数边界。
- 已完成 RED/GREEN focused 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'live_e2e_mapping_reason or unknown_ac_prototype_reason or test_method_quality or persists_semantic_attempts'` -> `4 failed`，分别表现为 Scope blocker 被路由到 Product Design、test-method quality 被路由到 Architecture、staged cycle 计数未持久化。
  - RED: `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'requirements_auto_revision_state_clears_after_valid_preflight'` -> `1 failed`，preflight 通过后旧 auto-revision state 未清理。
  - GREEN: staged focused -> `4 passed, 36 deselected`；controller clear-state focused -> `1 passed, 217 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'revision or auto_revision or routing'` -> `10 passed, 30 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'requirements_auto_revision or staged'` -> `4 passed, 214 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `40 passed`。
- 回归验证：
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py workflow_controller/tests/test_v061_docs.py -q` -> `46 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `697 passed in 79.36s`。
  - `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2a_all.deb`。
  - `dpkg-deb --field dist/waygate_0.6.2a_all.deb Package Version Architecture Depends` -> `waygate / 0.6.2a / all / python3`。

## 会话：2026-05-26

### Blocked Assist 对话恢复层
- **状态：** implementation verified on source branch; ported into current V0.6.2b branch with package version preserved.
- 已为显式 `status=blocked` 增加交互式 Blocked Assist 菜单，仅接入 `drive/start/go` 的共享 `drive()` 路径；`status` 仍只读，只提示可用诊断入口。
- Assist agent 只能诊断、提问、建议 route 并写 `artifacts/blocked-assist/<run-id>/blocked-assist-summary.json`；controller 在 `session.json` 记录 `blockedAssist` 指针，并记录 `blocked_assist_started/completed/failed/reclassified/resolution_selected` 事件。
- 已实现人工原因边界：continue、Unit Plan 返工、Requirements 变更和 Final Acceptance route 都需要非空 `human_reason`；Agent summary 只作为上下文，不能自动解除阻塞。
- continue 继续复用既有 `unblock_blocked_workflow()`，仅允许 environment / external dependency / annotation runtime / final acceptance blocked；Unit Plan 和 Requirements 合同类 blocked 必须走正式返工路线。
- 正式 workflow 文档与 USAGE 已同步：`docs/workflow/blocked-assist-policy.md`、`docs/workflow/stop-guidance-and-unblock-policy.md`、`docs/workflow.md`、`docs/workflow.zh-CN.md`、`USAGE.md`、`USAGE.zh-CN.md` 和 `docs/README.md`。
- 当前分支解决冲突时保留 `workflow_controller.__version__ = "0.6.2b"`、双语安装示例、双语 CHANGELOG 和 ROADMAP / task plan 的 V0.6.2b 记录。
- 历史验证：
  - `python3 -m pytest workflow_controller/tests/test_packaging.py -q` -> `4 passed`
  - `git diff --check` -> passed
  - 包内容包含 `workflow_controller/rrc_controller.py`、`docs/workflow/blocked-assist-policy.md` 和 `USAGE.md`
  - `python -m pytest workflow_controller/tests -q` -> failed because this shell has no `python` executable (`zsh:1: command not found: python`); `python3` is the verified interpreter.
  - `python3 -m pytest workflow_controller/tests -q` -> `659 passed`

### Recoverable wait 恢复入口收敛到 go/run/drive/start
- **状态：** implementation verified; full regression passed.
- 用户决策：不再保留用户可见 `waygate retry`；timeout/idle 后退出即可，下一次 `go` 或其他执行命令读取 `session.json` 继续同一阶段。
- 已实现 `recoverableAgentWait` 自动消费：`run_once`、`run_until_done`、`drive/start/go` 在进入执行时读取 active recoverable wait，记录 `agent_wait_auto_resumed`，清除等待标记，保留 Requirements / Unit Plan approval hash 和 artifacts，并继续当前 stage。
- 显式 `blocked` 边界保持独立：即使旧 state 同时残留 `recoverableAgentWait`，`run`、`run --until-done` 和 `go` 也不会清除 blocked；guidance 优先显示 `unblock` / `revise`，不会误提示已恢复 timeout/idle。环境类 `unblock` 成功后会清理 stale wait。
- 已移除 `workflow_controller.cli` 和 legacy `workflow_controller.rrc_controller` CLI 中的 `retry` 子命令；`waygate retry --help` 现在由 argparse 返回 invalid choice。
- 正式文档与使用说明已同步：`docs/workflow/recoverable-agent-timeout-policy.md`、`docs/workflow/stop-guidance-and-unblock-policy.md`、`docs/workflow.md`、`docs/workflow.zh-CN.md`、`USAGE.md`、`USAGE.zh-CN.md` 和 `docs/README.md`。
- 历史验证：focused controller / annotation / packaging checks、`git diff --check` 和当时全量 `workflow_controller/tests` 通过。

### Auto-created Claude pane staged Requirements 首次派发修复
- **状态：** implementation verified; focused/full regression passed; Debian package rebuilt.
- 现场 7 号窗口证据：auto-created Claude pane 首次 Requirements dispatch 前 controller 发送清输入序列；`C-c` 已成功作用于刚创建的 Claude pane，随后 `C-u` 返回 `can't find pane`，说明清输入阶段可能让新建 pane 退出或失效。
- 根因：旧修复只在 `currentStep=REQUIREMENTS_DRAFT` 且 `requirementsDraftGenerated=false` 时注入 `WAYGATE_TMUX_CLEAR_INPUT_BEFORE_DISPATCH=0`；V0.6.2 staged Requirements 新默认入口是 `REQUIREMENTS_SCOPE_DRAFT`，scope artifact 尚未完成时也属于首次 Requirements dispatch，但未命中保护。
- 修复：`make_runner()` 仅对 `tmux-claude` 且 `tmuxTargetResolution.source=auto-created` 的首次 Requirements dispatch 注入 `WAYGATE_TMUX_CLEAR_INPUT_BEFORE_DISPATCH=0`、`RRC_TMUX_CLAUDE_SUBMIT_DELAY_SECONDS=2.0` 和 `WAYGATE_TMUX_CLAUDE_SUBMIT_WATCHDOG=1`；legacy `REQUIREMENTS_DRAFT` 保持兼容，staged `REQUIREMENTS_SCOPE_DRAFT` 在 `requirementsPackage.artifacts.scope.status` 未 complete 时覆盖，scope complete 后恢复默认清输入。
- 未修改 proxy-collector live state，未删除 state-dir；controller 既有 stale auto-created pane 重建逻辑保持不变，本轮只补 runner env 条件。
- 已完成 RED/GREEN focused 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q -k 'make_runner_disables_initial_clear_for_auto_created_staged_scope_pane or make_runner_keeps_clear_for_completed_staged_scope_artifact or make_runner_does_not_disable_initial_clear_for_tmux_codex or make_runner_disables_initial_clear_for_auto_created_requirements_pane'` -> `1 failed, 3 passed`，staged Scope 未注入 clear-disable env。
  - RED: `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_rrc_go_recreated_staged_scope_pane_dispatch_disables_initial_clear -q` -> failed，recreated staged Scope dispatch 的 fake tmux env 中缺少 clear-disable/watchdog，且 delay 被外部测试 env 保持为 `0`。
  - GREEN: runner focused -> `4 passed, 37 deselected`。
  - GREEN: controller staged stale-pane dispatch focused -> `1 passed`。
- 回归验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `41 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'tmux or staged or requirements'` -> `57 passed, 160 deselected`。
  - `python3 -m pytest workflow_controller/tests -q` -> `692 passed in 78.87s`。
  - `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2a_all.deb`。

### Staged Requirements preflight route / Product Design manifest loop fix
- **状态：** implementation verified; focused/full regression passed; Debian package rebuilt.
- 根因：staged Requirements revision routing 先匹配 prototype/UI 关键词，导致同时包含 AO mapping、E2E AC/Journey mapping 和 prototype manifest 的 combined preflight reason 被错路由到 Product Design；同时 Product Design checkpoint 只在 prompt 中泛化描述原型证据，没有给出 canonical `prototypes[]` manifest schema，stage validation failure 也没有写成清晰的 blocked recovery state。
- 已修复路由优先级：missing Acceptance Obligation requirements mapping、missing AO coverage、E2E review 未映射到 active E2E AC/Journey 时优先回 `REQUIREMENTS_SCOPE_DRAFT`；纯 prototype/UI/“怎么看”反馈仍回 `REQUIREMENTS_PRODUCT_DESIGN_BRIEF`。
- 已强化 Product Design checkpoint 合同：当 `requirementsSurfaceClassification.prototype_required=required` 或 `web_system=required` 时，prompt 明确要求写 `artifacts/requirements-draft/prototype-manifest.json`，并内嵌 canonical 顶层 `prototypes[]` JSON skeleton；stage 完成前校验 manifest 存在且包含可访问原型、page states、click path、AC/Journey mapping、implementation targets 和 surface contracts。
- 现场 2 号窗口暴露后续 path locality 缺口：agent 写出 canonical `prototypes[]` 后仍使用 workspace-relative `docs/prototypes/customer-course-production.html`，而 stage validator 按 manifest 所在的 `artifacts/requirements-draft/` 目录解析路径；已补 prompt 明确本地原型必须生成/复制到 artifact tree 并写 artifact-local 相对路径，validator 缺文件时输出 resolved path 和 `docs/prototypes/...` 专项 guidance。
- 已拒绝扁平 manifest：顶层 `clickable_prototype_access_method` / `page_states` / `click_path` / `implementation_targets` / `surface_contracts` 不再被接受为最终 shape，错误会明确提示缺少 `prototypes[]`。
- 已补 stage validation recovery：Product Design stage validation failure 会保持 `currentStep=REQUIREMENTS_PRODUCT_DESIGN_BRIEF`，写入 `blockedReason`、`blockedContext.category=requirements_stage_validation` 和 stage validation artifact；终端 guidance 指向重新运行 Product Design checkpoint，不引导 `waygate revise --gate requirements`。
- 未操作 classroom live state，未停止 2.0，未修改 `.rrc-controller-v0.4/session.json`，未删除 state-dir，未执行恢复命令。
- 新包已构建但未安装到 `/usr/lib/waygate`：`sudo -n dpkg -i dist/waygate_0.6.2a_all.deb` 返回 `sudo: a password is required`；因此没有用旧 `/usr/bin/waygate` 执行 classroom recovery。
- 验证：
  - RED: 新增 combined AO/E2E/prototype routing 和 Product Design manifest prompt/stage tests 初始失败，表现为错路由到 Product Design、prompt 缺 manifest path、stage 缺失 manifest 未报错。
  - RED: 新增 canonical `prototypes[]` prompt、flat manifest rejection、Product Design stage validation recovery tests 初始失败，表现为 prompt 缺 schema skeleton、扁平 manifest 报错不清晰、`run_once()` 抛出 `ValueError`。
  - GREEN: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'canonical_manifest_schema_skeleton or flat_manifest or stage_validation_failure_records_recovery_state'` -> `3 passed, 30 deselected`。
  - RED/GREEN: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'artifact_local or workspace_relative_manifest_path or accepts_docs_path'` -> RED `2 failed, 1 passed`，GREEN `3 passed, 33 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `33 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'requirements or staged'` -> `33 passed, 183 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_v061_docs.py workflow_controller/tests/test_packaging.py -q` -> `10 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `685 passed in 80.08s`。
  - `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2a_all.deb`。
  - `dpkg-deb --field dist/waygate_0.6.2a_all.deb Package Version Architecture Depends` -> `waygate / 0.6.2a / all / python3`。
  - `sudo -n dpkg -i dist/waygate_0.6.2a_all.deb` -> failed，原因是 sudo 需要密码；live recovery 未执行。

### V0.6.2a Staged Requirements 目标产品视角修复
- **状态：** implementation verified; focused/full regression passed.
- 根因：V0.6.2 staged checkpoint prompt 和 preflight 仍容易把 Product Design / Architecture 带回 Waygate/controller 自身流程；同时默认 `currentUnitNeedsUiDesign=false` / `currentUnitIsWebSystem=false` 会掩盖 spec 中的目标产品入口、状态回看和详情页等可见表面。
- 已新增 `workflow_controller/requirements_surface.py`，从 `--spec`、目标上下文、unit metadata 和人工反馈生成 `requirementsSurfaceClassification`，记录 `product_ui`、`web_system`、`prototype_required`、`visible_surfaces` 和脱敏 `evidence_snippets`；默认 false 只作为 ignored context。
- 已更新 staged Scope / Product Design / Architecture / Test Strategy prompt：Scope 必须列当前版本目标、非目标、旅程、可见产品表面和后续候选；Product Design 围绕目标产品 UX / 原型 / 审阅入口；Architecture 围绕目标系统交互架构、API、数据流和运行边界；Test Strategy 保持策略层，不提前写 Unit Plan exact commands。
- 已强化 Requirements preflight：UI/Web/prototype classified required 时继续要求 prototype manifest；unknown classification 必须解释；非 Waygate 目标中 Product Design / Architecture 描述 controller 流程会被判 invalid。
- 已改善 staged revision route：产品原型/UI/“怎么看”反馈回 Product Design，架构交互/API/数据流反馈回 Architecture，测试策略反馈回 Test Strategy；prototype manifest 自动返工不再强制回 Scope。
- 已同步正式 workflow / architecture docs、ROADMAP / ROADMAP.zh-CN、CHANGELOG / CHANGELOG.zh-CN、README / README.zh-CN、USAGE / USAGE.zh-CN 和版本号 `0.6.2a`。
- 验证：
  - RED: 新增 staged Requirements target-surface tests 初始因 `workflow_controller.requirements_surface` 缺失失败；后续暴露 no-UI basis、revision route 和 legacy generic “browser-visible when UI is touched” 误判问题。
  - GREEN: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `26 passed`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py workflow_controller/tests/test_v061_docs.py workflow_controller/tests/test_packaging.py -q` -> `36 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/test_rrc_e2e.py workflow_controller/tests/test_rrc_real_runtime.py -q -k 'requirements or staged or target_init or unit_plan_approval or go_dry_run_target'` -> `87 passed, 227 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py workflow_controller/tests/test_v061_docs.py workflow_controller/tests/test_requirements_staged_package.py -q` -> `117 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `676 passed in 80.29s`。
  - `git diff --check` -> passed。
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.2a_all.deb`。
  - `dpkg-deb --field dist/waygate_0.6.2a_all.deb Package Version Architecture Depends` -> `waygate / 0.6.2a / all / python3`。

## 会话：2026-05-25

### Staged Requirements 自动打回后重新派发 Scope checkpoint
- **状态：** implementation verified; focused/full regression passed.
- 根因：final Requirements gate 预检失败后，staged package revision 已经把 artifact package 标记 stale 并把 state 路由回 `REQUIREMENTS_SCOPE_DRAFT`，但 `_auto_revise_invalid_requirements_draft()` 继续用旧 final gate 做同一轮预检，导致重复打回、blocked，`drive()` 还可能展示旧 final gate 的人工确认菜单。
- 修复：`_auto_revise_invalid_requirements_draft()` 在 `_revise_requirements_gate(controller_validation_only=True)` 后重新读取 state；如果当前是 `v0.6.2-staged` package 且已离开 `WAITING_REQUIREMENTS_ACCEPTANCE`，立即返回该 state，让下一轮由 `run_requirements_scope_drafter` 重新派发 agent 任务。
- 新增回归覆盖 staged auto-revision loop 和 `drive()` stale final gate 菜单；legacy Requirements auto-revision 连续同因预算行为保持不变。
- 验证：
  - RED: 新增 staged auto-revision / drive 回归初始失败，分别表现为 state 进入 `blocked` 和输出 `[人工确认] 需求与验收`。
  - GREEN: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q -k 'staged_requirements_auto_revision_returns_after_routing_to_scope or drive_staged_requirements_auto_revision'` -> `2 passed`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py -q` -> `19 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'requirements_auto_revision or staged'` -> `2 passed, 214 deselected`。
  - `git diff --check` -> passed。
  - `python3 -m pytest workflow_controller/tests -q` -> `669 passed in 78.29s`。

### Requirements staged 默认入口与 Unit Plan 批准校验一致性修复
- **状态：** implementation verified; focused/full regression passed; live V0.4 rerun reached staged checkpoints.
- 根因：`init_state()` 的 target 初始化分支仍把新 session 设为 legacy `REQUIREMENTS_DRAFT -> run_requirements_drafter`；同时 `check_unit_plan_approval` 的人工批准路径手写 validator 列表，漏掉了已经接入 preflight 的 `Infrastructure / Execution Context Matrix` 和 final evidence candidate 校验。
- 已修复 target 初始化默认入口：新建 target session 现在从 `REQUIREMENTS_SCOPE_DRAFT` / `run_requirements_scope_drafter` 开始，设置 `stagedRequirementsEnabled=true`，并初始化 `requirementsPackage.version=v0.6.2-staged` 空 artifact package。
- 已将 Unit Plan preflight 和 approved gate 路径收敛到同一个 `_apply_and_validate_unit_plan_gate()`，保证 state patch 后的 test strategy / coverage / AO / traceability / prototype / docs / infrastructure / env / assist / evidence / final candidate / golden path / real E2E / journey / walkthrough 校验顺序一致。
- Staged Unit Plan 本地模板现在在 staged Requirements state 下生成 `Infrastructure / Execution Context Matrix`，避免 dry-run/local-template gate 与批准校验合同不一致。
- 已完成 RED/GREEN 与回归验证：
  - RED: 新增 target init、`go --dry-run --max-steps 1`、Unit Plan approved assist-only、Unit Plan approved 缺 infrastructure matrix 回归，初始均按预期失败。
  - GREEN: `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_init_with_target_and_workspace_without_ralph_creates_target_acceptance_state workflow_controller/tests/test_rrc_human_gates.py::test_target_init_requires_requirements_acceptance_gate workflow_controller/tests/test_rrc_controller.py::test_rrc_go_dry_run_target_starts_with_requirements_scope_checkpoint workflow_controller/tests/test_rrc_controller.py::test_unit_plan_approval_rejects_assist_only_candidate_after_human_approval workflow_controller/tests/test_rrc_controller.py::test_unit_plan_approval_rejects_missing_infrastructure_matrix_after_human_approval -q` -> `5 passed`。
  - `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py -q` -> `307 passed`。
  - `git diff --check` -> passed。
  - `python3 -m pytest workflow_controller/tests -q` -> `667 passed in 81.43s`。
- Live V0.4：旧 `/home/lichangkun/code/classroom/.rrc-controller-v0.4` 已备份为 `.rrc-controller-v0.4.legacy-requirements-20260525T213923`；一次 auto-created Claude pane 失败状态已备份为 `.rrc-controller-v0.4.failed-autoclaude-20260525T214256`；随后使用本 worktree 代码和显式 `tmux-codex` target `2.0` 重新运行 V0.4。
- Live V0.4 证据：新 session 从 `Requirements Scope checkpoint` 开始，生成了 scope / product design / architecture / test strategy 四个 checkpoint，并装配了含 artifact hash rows 的 final Requirements gate。当前目标 Requirements 内容仍未通过 controller preflight，原因是 E2E/browser review 未映射到 e2e AC 或 active Journey，且 UI/Web/prototype 合同触发了 prototype manifest 要求；controller 已按 staged revision route 回到 `REQUIREMENTS_SCOPE_DRAFT`，无后台 Waygate 进程在写该 state-dir。

### V0.6.2 Final Acceptance 终验同步
- **状态：** Final Acceptance approved; human-readable status synced.
- Controller state `.rrc-controller-v0.6.2/session.json` 显示 `finalAcceptanceAccepted=true`、确认人为 `human`，目标 `Complete V0.6.2 development acceptance using current planning progress` 已 `covered`，四个 V0.6.2 units 均 `passes=true`。
- 同步 `ROADMAP.md`、`ROADMAP.zh-CN.md` 和 `task_plan.md` 的 V0.6.2 状态；`docs/README.md` 已登记 required staged Requirements workflow / architecture 文档，本同步未修改 docs registry。
- 未发现需要新增到 `findings.md` 的 workflow decision、defect 或 risk；除本轮 `DONE_FILE` 外，本次只写 final sync summary artifact。

### Unit Plan Evidence Closure Gap
- **状态：** implementation verified; full regression passed; classroom V0.3 evidence artifact regenerated.
- 根因：既有 Unit Plan evidence-row preflight 只检查 automated test case 的 exact command，且显式跳过 `verification_assist`；它没有检查每个 approved Requirements AC 是否至少有一个 Final Scope Audit 可计数的 planned evidence candidate，导致 AC 可能只靠 `verification_assist` / `needs_human_review` 到终验才暴露缺口。
- 已新增 controller 回归：approved AC 仅由 `verification_assist` 覆盖时 Unit Plan preflight 阻断；approved AC 由 exact command 覆盖时通过；approved AC 由 explicit manual evidence 覆盖时通过；Final Scope Audit 继续拒绝 `needs_human_review` 作为 AC coverage。
- 已实现 `validate_unit_plan_final_evidence_candidates()` 并接入 Unit Plan gate validation；已更新 `docs/workflow/unit-plan-evidence-row-preflight-policy.md`。
- 已完成 focused 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'approved_ac_covered_only_by_verification_assist or approved_ac_with_exact_command_candidate or approved_ac_with_explicit_manual_evidence'` -> `1 failed, 2 passed`，失败点为 assist-only AC 未设置 `blockedReason`。
  - GREEN: 同一 controller focused 范围 -> `3 passed`；`python3 -m pytest workflow_controller/tests/test_scope_audit.py -q -k 'needs_human_review'` -> `1 passed`。
  - RED/GREEN: `python3 -m pytest workflow_controller/tests/test_rrc_verifier.py -q -k 'manual_evidence_alias'` -> RED `1 failed`，GREEN `1 passed`，确保 Unit Plan `manual_evidence` alias 能进入 verifier row。
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py workflow_controller/tests/test_v061_flexible_evidence.py workflow_controller/tests/test_scope_audit.py -q` -> `93 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'unit_plan or final_scope_audit or verification_assist'` -> 初次发现测试 fixture 对 AC-2 缺 evidence candidate；修正 fixture 后 -> `48 passed, 164 deselected`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_verifier.py -q` -> `7 passed`。
  - `python3 -m pytest workflow_controller/tests -q` -> `635 passed in 77.35s`。
  - `git diff --check` -> passed。
  - `python -m pytest workflow_controller/tests -q` -> failed because this shell has no `python` executable (`zsh:1: command not found: python`); `python3` is the verified interpreter.
- Classroom V0.3 修订：
  - Added deterministic Go test `TestV03CapabilityErrorRetryIdempotencyEvidence` in `/home/lichangkun/code/classroom/services/api/v03_contract_test.go`.
  - Updated `.rrc-controller-v0.3/approvals/unit-plan.md` and `.rrc-controller-v0.3/session.json` so `TC-V03-AC05-AC08-ERROR-RETRY-IDEMPOTENCY-EVIDENCE` uses exact command `cd services/api && sh -c 'test -n "$DATABASE_URL" && go test ./... -run TestV03CapabilityErrorRetryIdempotencyEvidence'`, no `verification_assist`.
  - Verified exact command against `classroom_v03_test`; regenerated `.rrc-controller-v0.3/artifacts/target-v0-3/verification.json` and `.rrc-controller-v0.3/artifacts/final-scope-audit/scope-audit.json`; Final Scope Audit now reports AC coverage `13/13`, uncovered `[]`, issues `[]`.

## 会话：2026-05-24

### V0.6.2 Staged Requirements Package 文档登记与回归
- **状态：** implementation verified; focused and full regression passed.
- 完成 U4 文档交付：新增 `docs/workflow/staged-requirements-package-policy.md` 和 `docs/architecture/staged-requirements-package-architecture.md`，并在 `docs/README.md` 登记；同步 `requirements-e2e-review-policy.md` 中 V0.6.2 Test Strategy Brief / Unit Plan 继承边界。
- 同步版本边界：`ROADMAP.md` / `ROADMAP.zh-CN.md` 记录 V0.6.2 为 Staged Requirements Package，原 Strict Test Presence / TC1-TC7 并入 V0.6.3 Strict Test Presence / Per-Role Runner Configuration；`task_plan.md` 同步当前阶段记录。
- Focused regression 暴露并修复 annotation command placeholder 问题：`_expanded_command()` 原先对整段 args 使用 `str.format()`，会把 fake annotation JSON/Python 字典里的普通 `{...}` 误识别为占位符；现改为只替换 Waygate 已知 `{role}`、`{stage}`、`{prompt_path}`、`{artifact_path}` token，并把 staged requirements annotation fixture 的 `summary` 改为简体中文以符合既有 annotation artifact 合同。
- 未发现需要沉淀到 `findings.md` 的新增长期决策；本轮根因和验证证据记录在本进度项。
- 已完成 RED/GREEN 与回归验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_docs.py workflow_controller/tests/test_requirements_staged_package.py -q -k 'staged_requirements_docs or roadmap'` -> failed on missing `docs/workflow/staged-requirements-package-policy.md`
  - GREEN: 同一命令 -> `2 passed, 20 deselected`
  - Focused regression first run -> failed in `test_staged_requirements_final_assembly_run_once_preflights_before_annotation` on annotation arg placeholder expansion, then on non-Chinese `summary`
  - GREEN: `python3 -m pytest workflow_controller/tests/test_requirements_staged_package.py workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/test_acceptance_obligations.py workflow_controller/tests/test_v061_annotation_agents.py -q` -> `211 passed in 29.46s`
  - `python3 -m pytest workflow_controller/tests -q` -> `649 passed in 76.77s`
  - `git diff --check` -> passed

### Final Acceptance 人工批准不再被观察记录阻断
- **状态：** implementation verified; full regression passed.
- 现场 2 号窗口 V0.2 复现：Plannotator 已返回 `{"decision":"approved"}`，但 controller 在人工批准后因为 `人工系统观察记录（Required）` 的 `Issues or evidence path` 为空阻断最终验收。
- 根因：Final Acceptance gate 展示前已完成 deterministic evidence / scope / journey / prototype / real E2E / document deliverable / walkthrough entrypoint 预检，但批准路径仍额外调用 `validate_final_acceptance_manual_observation_record()`，把审阅记录字段当成硬门槛。
- 修复方向：最终验收人工批准优先；观察记录保留为审阅上下文和风险提示，不再限制人工批准。终验 gate 校验默认也不要求人工观察记录，避免未来新增调用遗漏显式 `False` 又重新限制人工。现场 V0.2 已用修复后的 controller 写回 Final Acceptance approval，并完成批准后的 agent sync，当前进入 `RELEASE_GATE`。
- 已完成 RED/GREEN focused 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_final_walkthrough.py::test_final_acceptance_approval_allows_empty_manual_observation_record -q` -> failed on `人工系统观察记录（Required） is incomplete`
  - GREEN: 同一命令 -> `1 passed`
  - `python3 -m pytest workflow_controller/tests/test_final_walkthrough.py -q` -> `21 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/test_rrc_controller.py -q -k 'final_acceptance or final_walkthrough or plannotator'` -> `39 passed, 238 deselected`
  - `python3 -m pytest workflow_controller/tests/test_v061_docs.py -q` -> `4 passed`
  - `git diff --check` -> passed
  - `WAYGATE_PREVIEW_PORT=0 python3 -m pytest workflow_controller/tests -q` -> `621 passed in 77.53s`

### Annotation Agent 人工 Gate 顺序修复
- **状态：** implementation verified; full regression passed.
- 修复 Unit Plan 修订路径：新 gate 通过 controller preflight 后会先记录 `unit_plan_gate_preflight_completed` 并执行 fresh `unit_plan_annotation`，再返回人工确认；无效 Unit Plan 不运行 annotation。
- 修复 Requirements / Unit Plan / Final Acceptance approval check 顺序：已 approved gate 先走 deterministic validation 和状态推进，不再在人工确认之后补跑 annotation；pending/stale gate 仍会在人工 review 前确保 annotation fresh。
- 已完成 RED/GREEN 定向验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q -k 'revise_unit_plan_gate_runs_annotation_before_returning_to_human_gate or approved_human_gate_does_not_start_annotation_after_approval'` -> initially `4 failed`
  - GREEN: 同一命令 -> `4 passed, 33 deselected`
- 已完成回归验证：
  - `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q` -> `37 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'annotation or plannotator or unit_plan or final_acceptance'` -> `66 passed, 139 deselected`
  - `WAYGATE_PREVIEW_PORT=0 python3 -m pytest workflow_controller/tests -q` -> `619 passed in 75.99s`

### Verification-Assist Agent 语义修正
- **状态：** implementation verified; full regression passed.
- V0.6.1 flexible evidence 现在区分两类：`descriptive_command` 仍执行命令，Agent 判断只作为人工 review context；`agent_assisted_case` 由 test case 显式声明 `verification_assist`，不执行命令，由 configured verification-assist backend 产出结构化 case artifact。
- Unit Plan validator 新增 `verification_assist` 合同校验：同一 test case 不能同时声明 `command` 和 `verification_assist`；`verification_assist.description` 与 `verification_assist.expected` 必填；必须解析到已启用的 Agent 配置，默认复用 `final_acceptance_verification_assist`。
- Verifier runtime 对 command cases 保持原路径；对 `verification_assist` cases 渲染专用 prompt、调用 configured subprocess backend、规范化 assist artifact，并在 `verification.json` 写入 `evidence_type=agent_assisted_case`、`status`、`agent_assisted_judgement`、`risk_annotations`、`structured_evidence_refs`、`human_review_required` 和 `assist_artifact_path`。
- Final Acceptance Evidence Matrix 现在将 deterministic rows、Agent-Assisted Descriptive Evidence 和 Agent-Assisted Verification Evidence 分开展示；辅助验证 evidence 仍不是 approval。
- 已完成 focused 验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_flexible_evidence.py -q` -> initially failed on missing validator import.
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_flexible_evidence.py -q -k golden_path_allows_verification_assist` -> initially failed on golden path command requirement.
  - GREEN: `python3 -m pytest workflow_controller/tests/test_v061_flexible_evidence.py -q` -> `5 passed`
  - `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q` -> `33 passed`
  - `python3 -m pytest workflow_controller/tests/test_v061_docs.py -q` -> `4 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'verification_assist or annotation or final_acceptance'` -> `17 passed, 188 deselected`
  - `WAYGATE_PREVIEW_PORT=0 python3 -m pytest workflow_controller/tests -q` -> `615 passed in 77.11s`
  - `git diff --check` -> passed

### Annotation Agent Approval Markdown Review Block
- **状态：** implementation verified; full regression passed.
- Fresh `human_language=zh-CN` annotation artifact 现在会在人工 gate 展示前写入同一个 approval Markdown 文件，块边界为 `<!-- WAYGATE_ANNOTATION_REVIEW_BEGIN -->` / `<!-- WAYGATE_ANNOTATION_REVIEW_END -->`，标题为 `## Annotation Agent 风险批注`。
- 批注块位于 `## Human Confirmation` 之后，展示 artifact 路径、`generated_at`、gate hash、summary、issue count 和逐条 issue 的 severity/category/location/AC/AO/Journey/message/evidence refs；`gate_body()` 和 approval content hash 保持不变。
- 重复进入 gate 会替换旧块；stale artifact 或非 `zh-CN` artifact 不写入审批 Markdown，并会移除旧块，避免 Plannotator 展示过期批注。
- 已完成 RED/GREEN 定向验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q -k 'review_block'` -> `4 failed`
  - GREEN: 同一命令 -> `4 passed`
- 已完成回归验证：
  - `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q` -> `33 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'annotation or requirements or plannotator'` -> `40 passed, 165 deselected`
  - `WAYGATE_PREVIEW_PORT=0 python3 -m pytest workflow_controller/tests -q` -> `612 passed in 77.52s`
  - `git diff --check` -> passed

### Annotation Agent Visibility and Freshness Fix
- **状态：** implementation verified; full regression passed.
- Annotation pass 现在在 controller pane 输出紧凑生命周期行：`[annotation] started ...`、`[annotation] completed ...` 或 `[annotation] failed ...`；模型 stdout/stderr 仍通过 `capture_output=True` 捕获，不直接刷终端。
- Annotation prompt、event 和 artifact 现在记录当前 gate body 的 `gate_content_hash`；人工 gate 检查会在 artifact 缺失或 hash 不匹配时重新运行对应 annotation role，避免复用旧 gate 的风险标注。
- Annotation artifact 现在必须声明 `human_language=zh-CN`，且 `summary`、`issues[].message`、`non_approval_statement` 等人类可见批注字段必须是简体中文；英文-only artifact 会被拒绝，旧 artifact 因缺少语言标记会重新运行。
- 人工 gate 菜单显示当前 fresh annotation artifact 路径、风险数量和中文摘要；Plannotator review metadata / event 也记录同一 annotation artifact 引用。后续 Approval Markdown Review Block 修复已改为把批注块写入 `## Human Confirmation` 之后，仍不改变 gate hash。
- Requirements 人工 `r` 修订路径在新 gate 生成、preflight 通过后重新运行 `requirements_annotation`；annotation 失败会进入 `annotation_runtime` blocked，并保留 `pendingAnnotationBeforeHumanGate` 供 `unblock` 后恢复。
- 正式 workflow 文档和 CLI 使用说明已补充：annotation agent 是 controller-side subprocess，不会显示在 tmux builder pane；人工 gate 前只显示 compact status；Requirements revision 必须生成 fresh annotation artifact。
- 已完成 RED/GREEN 定向验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q -k 'compact_lifecycle or stale_gate_reruns or revised_gate_hash or annotation_failure_blocks_annotation_runtime'` -> `4 failed`
  - GREEN: 同一命令 -> `4 passed`
  - GREEN: `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q` -> `26 passed`
  - RED/GREEN: `python3 -m pytest workflow_controller/tests/test_v061_docs.py -q -k visibility_and_revision_freshness` -> RED `1 failed`，GREEN `1 passed`
- 已完成回归验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'annotation or requirements'` -> `31 passed, 174 deselected`
  - `python3 -m pytest workflow_controller/tests/test_v061_docs.py -q` -> `4 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `605 passed in 76.61s`
  - `git diff --check` -> passed
- 用户要求打包后，已生成 `dist/waygate_0.6.1_all.deb`；打包验证：
  - `python3 -m pytest workflow_controller/tests/test_packaging.py -q` -> `4 passed`
  - `git diff --check` -> passed
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.1_all.deb`
  - `dpkg-deb --field dist/waygate_0.6.1_all.deb Package Version Architecture Depends` -> `waygate / 0.6.1 / all / python3`
  - 解包后 `waygate --version` -> `waygate 0.6.1`
  - 包内容包含 `workflow_controller/annotation_agents.py`、`docs/workflow/external-spec-intake-and-annotation-policy.md` 和 `docs/architecture/external-spec-intake-and-annotation-architecture.md`

### Annotation Agent CLI Compatibility Formal Fix
- **状态：** implementation verified; full regression passed; live V0.2 recovery verified.
- 内置 `--annotation-agent codex` 模板已改为当前 Codex CLI 支持的 `codex exec --sandbox workspace-write -o {artifact_path} ...`，不再生成 `--ask-for-approval never`。
- 旧 session 中精确匹配 Waygate 旧内置 Codex annotation args 的配置会在 runtime/config normalize 路径自动归一化；用户通过 `--annotation-agent-cmd` 自定义的命令保持原样。
- Annotation runner 失败现在归类为 `annotation_runtime` blocker，并通过 `unblock` 恢复 pending annotation 后再进入人工 gate，不再误导为 Requirements contract revise。
- 正式文档 `docs/workflow/external-spec-intake-and-annotation-policy.md`、`USAGE.md`、`USAGE.zh-CN.md` 已同步；`findings.md` 记录“CLI annotation 后端兼容性不是 gate 合同失败”的决策。
- CLI 兼容性检查：
  - `claude --version` -> `2.1.150 (Claude Code)`；`claude --help` 包含 `-p` 和 `--permission-mode bypassPermissions`。
  - `codex --version` -> `codex-cli 0.133.0`；`codex exec --help` 包含 `--sandbox` 和 `-o, --output-last-message`，未包含旧 `--ask-for-approval`。
  - `opencode --version` -> `1.15.10`；`opencode run --help` 可用。
- 真实 smoke：
  - Codex：临时目录 `/tmp/waygate-codex-smoke.TzSkRR` 写出合法 JSON artifact；命令兼容，过程中本机 Codex auth refresh 有 401/expired token 日志但命令 returncode 为 0。
  - OpenCode：临时目录 `/tmp/waygate-opencode-smoke.pvBHSK` 写出合法 JSON artifact。
  - Claude Code：临时目录 `/tmp/waygate-claude-smoke.jqtY4W` 的 artifact 写入 smoke 在 180s 超时，未生成 artifact；记录为本机 Claude backend/runtime smoke blocker，CLI help 本身可用。
- Live 验收：`/home/lichangkun/code/classroom/.rrc-controller-v0.2` 旧 state 已归一化三类 annotation args，`unblock` 后重新执行 Requirements annotation；最新 events 记录 `annotation_pass_completed`，未再出现 `unexpected argument '--ask-for-approval'`，当前停在真实 Requirements 人工 gate：`currentStep=WAITING_REQUIREMENTS_ACCEPTANCE`、`status=active`、`nextAction=check_requirements_acceptance`。
- 已完成验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py -q -k 'codex_enables_all_roles_with_safe_defaults or builtin_annotation_backend_templates or legacy_builtin_codex_annotation_args_normalize or custom_annotation_agent_cmd_with_legacy_like_args_is_preserved or unblock_reruns_pending_requirements_annotation'` -> `4 failed, 1 passed`
  - RED: `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'annotation_runtime_blocker_guidance'` -> `1 failed`
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_docs.py -q -k 'annotation_policy_docs_use_current_codex_cli_contract'` -> `1 failed`
  - GREEN: `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py workflow_controller/tests/test_v061_docs.py -q` -> `25 passed`
  - GREEN: `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'annotation or unblock or stop_guidance'` -> `7 passed, 198 deselected`
  - `python3 -m pytest workflow_controller/tests -q` -> `600 passed in 76.83s`
  - `git diff --check` -> passed
  - `python -m pytest workflow_controller/tests -q` -> failed because this shell has no `python` executable (`zsh:1: command not found: python`); `python3` is the verified interpreter.

### Agent 提供终验走查包与人工观察记录审阅上下文
- **状态：** implementation verified; full regression passed.
- Unit Plan `final_acceptance_walkthrough` 现在区分 `inspection` 和 `launch`：closure/Web/UI unit 必须声明人工可见系统入口，包含 `surface_kind`、`entrypoint`、`manual_steps` 和 `expected_observations`；`manual_steps` 不能只写 pytest、Playwright、golden path 或其他测试命令。
- Builder 可在 DONE payload 中通过 `final_acceptance_walkthrough.inspection` 覆盖 Unit Plan 入口；Final Acceptance gate 优先展示 Builder 确认过的最终入口和原因。
- Final Acceptance gate 新增 `## Agent 提供的人工走查入口` 与 `## 人工系统观察记录（Review Notes）`；人工记录包含 observed entrypoint、actual observation、data/account/fixture 和 issues/evidence path，作为审阅上下文和审计补充。
- `waygate approve --gate final-acceptance` 与 Plannotator Approve 共享同一校验路径；当前语义下人工批准优先，空观察记录不再阻断 Final Acceptance。
- 正式 workflow 文档 `docs/workflow/final-acceptance-guided-walkthrough-policy.md` 已同步；`findings.md` 记录“Plannotator 文档审批不等于系统终验”的决策。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_final_walkthrough.py -q` -> `21 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/test_rrc_controller.py -q -k 'final_acceptance or final_walkthrough or plannotator'` -> `39 passed, 237 deselected`
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `72 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `204 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `593 passed in 75.67s`
  - `git diff --check` -> passed

## 会话：2026-05-23

### Builder blocked artifact 复阻塞修复
- **状态：** implementation verified; packaged.
- 现场 2 号窗口 V0.1 workflow 已确认 Unit Plan 中 `PRODUCTION_WEB_BASE_URL` / `PRODUCTION_API_BASE_URL` 已改为 localhost 默认值，但 `artifacts/target-v0-1/builder-summary.json` 仍保留旧 run `target-v0-1-20260523T111412138716Z` 的 `status=blocked`。
- 根因是 controller 在 `get_status()` / `run_once()` 中会把同一个旧 Builder blocked artifact 反复 reconciliation 回官方 blocked state；`waygate unblock` 或重新批准 Unit Plan 后，还没进入新 Builder run 就被旧 run_id 复阻塞。
- 修复：`unblock` 和 Unit Plan approval 会记录已处理的 builder blocked context key；同一个旧 artifact 不再复阻塞，新 Builder run 若再次 blocked 会用新的 run_id 正常进入 blocked。
- 已完成 RED/GREEN 定向验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'unblock_ignores_same_builder_blocked_artifact or unit_plan_approval_ignores_previous_builder_blocked_artifact'` -> `2 failed`
  - GREEN: 同一命令 -> `2 passed`
- 已完成回归与打包验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'blocked_guidance or stop_guidance or drive or unblock or builder_agent_blocked or unit_plan_approval_ignores_previous_builder_blocked_artifact'` -> `46 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `585 passed in 74.84s`
  - `git diff --check` -> passed
  - `python3 -m pytest workflow_controller/tests/test_packaging.py -q` -> `4 passed`
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.1_all.deb`
  - 解包后 `waygate --version` -> `waygate 0.6.1`

### Waygate 停止状态原因化引导
- **状态：** implementation verified; full regression passed.
- `status`、`run`、`drive/start/go` 现在在 recoverable wait、human gate、blocked、max steps、no progress 和 no next action 停止点追加原因、下一步和可复制命令；`status` 第一行仍保持 `currentStep/status/nextAction/projectTargetVersion` 兼容输出。
- `retry` 边界收紧为只处理 `recoverableAgentWait` 的 timeout/idle；显式 `blocked` 会提示运行 `waygate status --state-dir <dir>` 查看 route guidance。
- 新增 `waygate unblock --state-dir <dir> --reason "<fixed condition>"`，只允许环境/外部依赖类 blocked 在人工修复后继续同一阶段；保留 approvals/gates/artifacts，记录 `blocked_state_unblocked` event。
- Builder 显式 `blocked` 现在会持久化为官方 controller blocked state：`status=blocked`、`currentStep=EXECUTE_UNIT`、`blockedReason=<DONE summary>`、`blockedContext.source=builder_agent`，并记录 `builder_agent_blocked` event；旧 active state 若已有 `builder-summary.json` blocked，会在 `status/get_status()` reconciliation 中恢复。
- 正式 workflow 文档新增 `docs/workflow/stop-guidance-and-unblock-policy.md`，并更新 `docs/workflow/recoverable-agent-timeout-policy.md` 与 `docs/README.md` 登记。
- 已完成 RED/GREEN 定向验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q -k 'status_prints_recoverable_wait_guidance or retry_refuses_explicit_blocked_state or unblock_requires_reason or unblock_allows_environment_blocked_state or unblock_rejects_unit_plan_contract_blocked_state or builder_agent_blocked_persists_official_controller_blocked_state or status_reconciles_legacy_builder_summary_blocked'` -> `7 failed`
  - GREEN: 同一范围 + drive timestamp/gate regression -> `9 passed`
- 已完成回归验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_builder.py workflow_controller/tests/test_packaging.py -q` -> `208 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/test_v061_docs.py -q` -> `74 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `579 passed in 74.63s`
  - `git diff --check` -> passed

### Annotation Agent 环境可用性风险标注
- **状态：** implementation verified; full regression passed.
- Requirements / Unit Plan annotation prompt 现在明确要求在人工 gate 前标注外部运行环境可用性风险，但仍保持 risk-only、non-approval 语义。
- 新增风险 taxonomy：Requirements 支持 `production_readonly_gap` / `runtime_dependency_gap`；Unit Plan 支持 `production_readonly_gap` / `runtime_dependency_gap` / `verification_env_gap`。
- 标注 prompt 会提醒 agent 检查 `production_readonly` 是否缺真实外部入口，例如 `PRODUCTION_WEB_BASE_URL` / `PRODUCTION_API_BASE_URL`，并检查 Docker、Docker Compose、Playwright/browser、端口、服务依赖、数据库、缓存和外部 API 是否只是被假设存在。
- `verification_env` 被明确为 key-name declaration；仅声明 env key 不证明存在可执行 value、已部署服务、可达生产环境或端口可用。
- 正式 workflow 文档 `docs/workflow/external-spec-intake-and-annotation-policy.md` 与架构文档 `docs/architecture/external-spec-intake-and-annotation-architecture.md` 已同步。
- 已完成 RED/GREEN 定向验证：
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py::test_requirements_and_unit_plan_annotation_prompts_flag_environment_availability_risks -q` -> failed on missing `production_readonly`.
  - GREEN: 同一命令 -> `1 passed`。
  - RED: `python3 -m pytest workflow_controller/tests/test_v061_docs.py::test_v061_required_formal_docs_and_registry_exist -q` -> failed on missing `production_readonly_gap` docs.
  - GREEN: 同一命令 -> `1 passed`。
- 已完成 focused regression：
  - `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py workflow_controller/tests/test_v061_docs.py -q` -> `19 passed`
- 标准验证命令环境差异：
  - `python -m pytest workflow_controller/tests -q` -> failed because this shell has no `python` executable (`zsh:1: command not found: python`).
  - `python3 -m pytest workflow_controller/tests -q` -> `572 passed in 75.01s`
- 用户要求打包后，已生成 `dist/waygate_0.6.1_all.deb`；打包验证：
  - `python3 -m pytest workflow_controller/tests/test_packaging.py -q` -> `4 passed`
  - `git diff --check` -> passed
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.1_all.deb`
  - `dpkg-deb --field dist/waygate_0.6.1_all.deb Package Version Architecture Depends` -> `waygate / 0.6.1 / all / python3`
  - 解包后 `waygate --version` -> `waygate 0.6.1`
  - 包内容包含 `workflow_controller/annotation_agents.py`、`docs/workflow/external-spec-intake-and-annotation-policy.md` 和 `docs/architecture/external-spec-intake-and-annotation-architecture.md`

### Final Acceptance Guided Launch Walkthrough
- **状态：** implementation verified; full regression passed.
- Final Acceptance 前新增 `FINAL_WALKTHROUGH_PREPARE` 阶段：Verifier / bug-fix verifier 通过后先写 `final-walkthrough-launch.json`，再生成 Final Acceptance gate。
- Unit Plan Controller State Patch 支持 `final_acceptance_walkthrough.launch`，可声明 `agent_start`、`manual_only` 或 `not_required`；validator 会阻断缺 command、缺 readiness hint、非法 cwd、保存 env/secret 值和缺 manual instructions。
- `agent_start` 会按声明命令启动并检查 `ready_url`、`ready_command` 或 `ready_output_contains`；启动失败只写入 gate 供人工选择返工路由，不自动批准或绕过终验。
- Final Acceptance gate 新增 `## Golden Path 人工走查`，展示启动状态、入口、ready check、日志、stop command、fixture/test data、user steps、expected、人工确认和观察记录。
- 正式 workflow 文档新增 `docs/workflow/final-acceptance-guided-walkthrough-policy.md` 并登记到 `docs/README.md`。
- 已完成定向验证：
  - `python3 -m pytest workflow_controller/tests/test_final_walkthrough.py -q` -> `13 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `72 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `191 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_real_runtime.py -q` -> `23 passed`
  - `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py::test_gate_order_runs_annotation_before_human_gate_events_for_requirements_unit_plan_and_final -q` -> `1 passed`
  - `git diff --check` -> passed
  - `python3 -m pytest workflow_controller/tests -q` -> `571 passed in 74.80s`
- 用户要求打包后，已生成 `dist/waygate_0.6.1_all.deb`；打包验证：
  - `python3 -m pytest workflow_controller/tests/test_packaging.py -q` -> `4 passed`
  - `git diff --check` -> passed
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.1_all.deb`
  - `dpkg-deb --field dist/waygate_0.6.1_all.deb Package Version Architecture Depends` -> `waygate / 0.6.1 / all / python3`
  - 解包后 `waygate --version` -> `waygate 0.6.1`
  - 包内容包含 `workflow_controller/steps/final_walkthrough.py` 和 `docs/workflow/final-acceptance-guided-walkthrough-policy.md`

### V0.6.1 Annotation Agent CLI 启用补充
- **状态：** implementation verified; full regression passed.
- `init`、`start`、`go`、`drive`、`run` 现在支持 `--annotation-agent` 系列参数，操作者可以通过 `waygate go V0.6.1 --annotation-agent codex` 启用非批准型风险标注 Agent，无需手改 `session.json`。
- 支持 `requirements`、`unit-plan`、`final-acceptance`、`all` role alias，支持 `codex`、`claude-code` / `claude`、`opencode` backend；支持 command、env key allowlist、timeout、failure policy 和禁用覆盖。
- CLI override 会写入或更新 `annotationAgents`，只保存环境变量名，不保存 secret 值；annotation artifact 仍只能作为风险提示，不能批准、跳过、修改或绕过 gate。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_v061_annotation_agents.py workflow_controller/tests/test_v061_docs.py -q` -> `18 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_init_with_test_strategist_flag_enables_it_in_session workflow_controller/tests/test_rrc_controller.py::test_init_with_code_simplifier_flag_configures_refiner_runner_only workflow_controller/tests/test_rrc_controller.py::test_rrc_go_dry_run_creates_and_resumes_inferred_state_dir -q` -> `3 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `558 passed in 74.49s`
  - `git diff --check` -> passed

### V0.6.1 External Spec Intake 终验同步
- **状态：** Final Acceptance approved; human-readable status synced.
- Controller Final Acceptance 已批准：`finalAcceptanceAccepted=true`，确认人为 human，hash 为 `sha256:43189e15a45c23582e73f28ff3fc8d1cabfc30026ba17acf22bbba92c7c0d85a`。
- 当前目标 `Complete V0.6.1 development acceptance using current planning progress` 已标记为 `covered`；四个单元 `v0-6-1-u1-external-spec-intake`、`v0-6-1-u2-annotation-config-prompts`、`v0-6-1-u3-flexible-evidence`、`v0-6-1-u4-docs-regression` 均已 `passes=true`。
- Final Acceptance evidence matrix 中 AC-17 / AC-18 均 passed；Final Scope Audit 显示 AC coverage `18/18`、Journey coverage `7/7`、AO coverage `1/1`、unexplained changed files `0`。
- 必需文档 deliverables 均为 present：`ROADMAP.md`、`ROADMAP.zh-CN.md`、`docs/workflow/external-spec-intake-and-annotation-policy.md`、`docs/architecture/external-spec-intake-and-annotation-architecture.md` 和 `docs/README.md` registry。
- 验证命令均已通过：`git diff --check && python3 -m pytest workflow_controller/tests/test_v061_docs.py -q`、`git diff --check`、`python3 -m pytest workflow_controller/tests -q`。
- 本次状态同步更新了 `ROADMAP.md`、`ROADMAP.zh-CN.md`、`task_plan.md` 和 `progress.md`；未发现新的 workflow decision、defect 或 risk，因此 `findings.md` 未新增终验记录。
- 用户明确要求打包后，已将 package version 同步到 `0.6.1`，把新增 `docs/architecture/` 正式文档纳入 Debian 包，并生成 `dist/waygate_0.6.1_all.deb`。
- 打包验证通过：`python3 -m pytest workflow_controller/tests/test_packaging.py -q` -> `4 passed`；`bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.1_all.deb`；`dpkg-deb --field dist/waygate_0.6.1_all.deb Package Version Architecture Depends` -> `waygate / 0.6.1 / all / python3`；解包后 `waygate --version` -> `waygate 0.6.1`。

## 会话：2026-05-22

### V0.6.0m Golden Path E2E 前置校验
- **状态：** implementation verified; full regression passed; packaged as `0.6.0m`.
- Unit Plan approval 现在会在人工确认阶段阻断 `golden_path: true` 但不是 `layer=e2e`、缺真实入口、使用 `component_mock`/`contract_mock`/`visual` 等非真实环境、缺 fixture/setup、命令未进入 `verification_commands`、expected 过弱或声明核心 API mock/stub 的测试用例。
- Requirements 中声明 E2E 的 AC 或 active E2E Journey，必须在 Unit Plan 中映射到 `layer=e2e` test case；`workflow_validation_level=closure` 不再替代 e2e Journey 的 test case layer。
- API-only / service-only 项目不要求浏览器字段；只要使用真实入口、真实环境、真实 fixture/setup 和 pytest/API/service E2E 命令即可承担 golden path。
- Unit Plan Test Case Matrix 现在显式展示 Golden Path 列，并继续展示 Layer、Environment、Real Entry 和 Core API Mock，便于人工审核。
- 已完成 RED/GREEN 定向验证：
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py::test_unit_plan_golden_path_rejects_non_e2e_layer workflow_controller/tests/test_acceptance_obligations.py::test_unit_plan_golden_path_rejects_missing_real_entrypoint workflow_controller/tests/test_acceptance_obligations.py::test_unit_plan_golden_path_rejects_mock_environment_kind workflow_controller/tests/test_acceptance_obligations.py::test_unit_plan_accepts_api_only_e2e_golden_path workflow_controller/tests/test_acceptance_obligations.py::test_unit_plan_requires_e2e_case_for_e2e_acceptance_criterion -q` -> RED: `4 failed, 1 passed`; GREEN: `5 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py::test_prompt_contracts_require_ac_mapped_executable_e2e_assertions workflow_controller/tests/gates/test_gates_structure.py::TestGeneratorsLayer::test_render_unit_plan_gate_body workflow_controller/tests/test_packaging.py::test_version_flag_outputs_package_version -q` -> RED: `3 failed`; GREEN: `3 passed`
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_acceptance_obligations.py -q` -> `341 passed`
  - `python3 -m pytest workflow_controller/tests/test_packaging.py -q` -> `4 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `532 passed in 70.69s`
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.0m_all.deb`
  - `dpkg-deb --field dist/waygate_0.6.0m_all.deb Package Version Architecture Depends` -> `waygate / 0.6.0m / all / python3`
  - `WAYGATE_LIB_DIR=<extract>/usr/lib/waygate <extract>/usr/bin/waygate --version` -> `waygate 0.6.0m`
  - `WAYGATE_LIB_DIR=<extract>/usr/lib/waygate <extract>/usr/bin/waygate retry --help` -> `usage: waygate retry [-h] [--state-dir STATE_DIR]`

### Recoverable Agent Timeout / `waygate retry`
- **状态：** implementation verified; full regression passed.
- Agent runner 返回 `timeout` 或 `agent_idle_without_done` 时不再把 workflow 置为 blocked，也不要求通过 `waygate revise` 回到 Requirements / Unit Plan；controller 记录 `recoverableAgentWait`，保持当前 stage、`status=active` 和既有 approvals。
- 新增 `waygate retry --state-dir <state-dir>`，只清除 recoverable wait 并保留 Requirements / Unit Plan / Final Acceptance approval hash 与 actor 信息。
- Subprocess runner 的 `TimeoutExpired` 现在归一化为 `RunnerResult(status='timeout', returncode=124)`，与 tmux runner 的 recoverable status 统一处理。
- 正式文档新增 `docs/workflow/recoverable-agent-timeout-policy.md`，并登记到 `docs/README.md`；`docs/workflow.md` 和 `docs/workflow.zh-CN.md` 已同步说明。
- 已完成定向验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_requirements_draft_timeout_records_recoverable_wait_without_blocking workflow_controller/tests/test_rrc_controller.py::test_builder_timeout_records_recoverable_wait_and_keeps_current_unit workflow_controller/tests/test_rrc_controller.py::test_retry_clears_recoverable_agent_wait_without_changing_approvals -q` -> `3 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_requirements_draft_timeout_resumes_existing_pending_run_without_redispatch workflow_controller/tests/test_rrc_controller.py::test_requirements_draft_does_not_recover_done_and_body_older_than_timeout workflow_controller/tests/test_rrc_controller.py::test_requirements_draft_waits_on_existing_timeout_run_until_fresh_body_arrives -q` -> `3 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_run_stops_on_existing_recoverable_agent_wait_until_retry workflow_controller/tests/test_rrc_agent_runners.py::test_subprocess_runner_timeout_returns_recoverable_timeout_result -q` -> `2 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_unit_plan_draft_timeout_records_recoverable_wait_and_preserves_requirements_approval -q` -> `1 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_refiner.py workflow_controller/tests/test_rrc_builder.py workflow_controller/tests/test_rrc_agent_runners.py -q -k 'not test_drive_plannotator_reviews_requirements_bundle_when_available_and_keeps_approval_gate_separate'` -> `241 passed, 1 deselected`
  - `python3 -m pytest workflow_controller/tests -q` -> `525 passed, 2 failed`；失败均为 `0.0.0.0:20001` 已被当时正在运行的 `python3 -m workflow_controller.cli go V2.0 --auto-approve --tmux-target 7.0` 进程占用导致 prototype preview server bind 失败。
  - `python3 -m pytest workflow_controller/tests -q -k 'not test_prototype_preview_server_only_serves_review_bundle_manifest_prototypes_and_approval_gate and not test_drive_plannotator_reviews_requirements_bundle_when_available_and_keeps_approval_gate_separate'` -> `525 passed, 2 deselected`
  - 最后补充验证：`python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_init_with_target_and_workspace_without_ralph_creates_target_acceptance_state workflow_controller/tests/test_rrc_controller.py::test_run_stops_on_existing_recoverable_agent_wait_until_retry -q` -> `2 passed`
  - 端口释放后标准全量验证：`python3 -m pytest workflow_controller/tests -q` -> `527 passed in 72.50s`

### V0.6.2 Requirements-stage E2E 前置审阅门禁
- **状态：** implementation verified; full regression passed.
- Requirements prompt 和默认 Requirements gate body 新增固定 `## 4.6 E2E 测试方法与前置依赖矩阵（E2E Test Method & Prerequisite Matrix）`，位于 4.5 之后、4.7 之前。
- Requirements preflight 现在在 e2e AC、active e2e Journey、明确 Playwright/browser/end-to-end 测试策略或 Web/原型/UI 真实浏览器证明需求出现时，要求 4.6 矩阵并校验真实入口、用户步骤、fixture/setup、具体命令、`local_real|production_readonly`、mock policy 和强断言。
- Unit Plan prompt 要求继承已批准 4.6 的 E2E 方法、真实入口、fixture/setup、命令依赖、环境类型、mock policy 和断言意图。
- 正式文档新增 `docs/workflow/requirements-e2e-review-policy.md`，并登记到 `docs/README.md`；`docs/workflow.md` 和 `docs/workflow.zh-CN.md` 已同步说明。
- 已完成定向验证：
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `73 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `72 passed`
  - `python3 -m pytest workflow_controller/tests/gates/test_gates_structure.py -q` -> `19 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `186 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `521 passed in 67.89s`
- 用户要求打包后已执行 `bash packaging/debian/build-deb.sh`，生成 `dist/waygate_0.6.0k_all.deb`；`dpkg-deb --field dist/waygate_0.6.0k_all.deb Package Version Architecture Depends` -> `waygate / 0.6.0k / all / python3`。本次未做版本号 bump。

## 会话：2026-05-21

### Unit Plan 自动打回连续原因计数修复
- **状态：** complete
- `unitPlanAutoRevisionMax` 现在表示同一个 controller invalid reason 连续最多自动打回 5 次；如果本次 Unit Plan 预检失败原因与上次不同，视为有效推进并重置连续计数。
- `unit_plan_draft_auto_revision_requested` 继续用 `attempt` 表示当前 reason 的连续 attempt，并新增 `total_attempt`；`unit_plan_draft_auto_revision_blocked` 新增 `consecutive_attempts` 和 `total_attempts`；`controller-validation-error.json` 的 `attempt` 记录当前 reason 的连续 attempt。
- Requirements 自动打回语义保持不变；本轮仅对齐 Unit Plan 自动打回计数。
- 已验证 RED：新增 Unit Plan 自动打回测试先失败于不同 reason 仍被总次数预算阻塞、request event 缺少 `total_attempt`。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_unit_plan_auto_revision_budget_resets_when_invalid_reason_changes workflow_controller/tests/test_rrc_controller.py::test_unit_plan_auto_revision_budget_blocks_repeated_same_reason_with_attempt_payloads workflow_controller/tests/test_rrc_controller.py::test_requirements_auto_revision_budget_resets_when_invalid_reason_changes workflow_controller/tests/test_rrc_controller.py::test_requirements_auto_revision_budget_still_blocks_repeated_same_reason -q` -> `4 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `185 passed in 10.70s`
  - `python3 -m pytest workflow_controller/tests -q` -> `508 passed in 69.58s`

### V0.6.0k UI/UX Skill Policy
- **状态：** implementation verified; full regression passed; packaged as `0.6.0k`.
- Requirements prompt 现在明确 UI/Web/prototype、可点击原型、prototype evidence 和生产 UI 一致性工作必须使用 `ui-ux-pro-max`，并要求先盘点真实 route、DOM/组件、既有页面结构、截图、历史设计或参考环境；`frontend-design` 只能作为全新视觉探索或局部润色辅助。
- Unit Plan prompt 要求 UI/Web/prototype test case 保留 `ui-ux-pro-max` 设计/交互检查，不能只写 `frontend-design` 或泛化“使用设计技能”；Builder prompt 和 UI Design Brief 同步要求按交互、可访问性、布局和遮挡检查实现与验证。
- `waygate doctor` 的 `skill_recommendations.ui_ux_design` 改为要求 `ui-ux-pro-max`：只安装 `frontend-design` 时输出 warning/manual action；两者都安装时优先 `matched=ui-ux-pro-max`。
- `init` / `run` 等命令现在第一行输出 `waygate <version>`；`start` / `go` / `drive` 等连续运行命令在带时间戳的第一行输出版本号，便于现场确认实际启动的版本且不破坏 `drive` 每行带时间戳的输出契约。
- 正式文档新增 `docs/workflow/ui-ux-skill-policy.md` 并登记到 `docs/README.md`；README、USAGE、ROADMAP、CHANGELOG 和 recommended-environment 文档不再把 `frontend-design` 与 `ui-ux-pro-max` 作为等价选择。
- 版本更新为 `0.6.0k`，已生成 `dist/waygate_0.6.0k_all.deb`。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `72 passed`
  - `python3 -m pytest workflow_controller/tests/test_diagnostics.py -q` -> `16 passed`
  - `python3 -m pytest workflow_controller/tests/test_packaging.py -q` -> `4 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `506 passed in 69.04s`
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.0k_all.deb`
  - `dpkg-deb --field dist/waygate_0.6.0k_all.deb Package Version Architecture Depends` -> `waygate / 0.6.0k / all / python3`
  - 解包后执行 `usr/bin/waygate start --dry-run --max-steps 0` -> 第一行 `[HH:MM:SS] waygate 0.6.0k`

### Controller Prototype Fidelity Gate
- **状态：** implementation verified; full regression passed.
- Prototype conformance 现在按 fidelity 分级处理：默认 required UI/Web surface 需要 L1 visual evidence + L2 structural/interaction evidence；只有 Requirements、manifest 或 test case 明确 `screenshot_regression` / `pixel_exact` 时才启用 L3/L4。
- Unit Plan prototype conformance 校验新增 `visual_evidence_plan` 要求，拒绝缺 prototype/production screenshot、action path、交互截图计划、route/text visible 弱断言，以及显式 L4 缺像素级证据计划。
- Verifier evidence rows 保留 `screenshot_refs`，新增 `visual_evidence_refs`，并解析 `PROTOTYPE_SCREENSHOT:`、`PRODUCTION_SCREENSHOT:`、`INTERACTION_SCREENSHOT:` 和 `VISUAL_EVIDENCE: {...}` marker；prototype conformance E2E 缺 L1/L2 证据会标记 invalid evidence。
- Final Acceptance `Prototype Conformance Matrix` 新增 Fidelity、Visual Evidence、Prototype Screenshot、Production Screenshot、Interaction Screenshot 和 Action Path 列，并新增 `Visual Prototype Evidence` 小节；缺截图、缺 action path、交互截图缺失、遮挡或显式 L3/L4 缺截图回归结果都会阻断终验。
- 正式文档新增 `docs/workflow/prototype-fidelity-policy.md` 并登记到 `docs/README.md`，`docs/workflow.md` 同步说明视觉证据 marker 和终验展示。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `61 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `70 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `183 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_real_runtime.py -q` -> `23 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_verifier.py -q` -> `6 passed`
  - `python3 -m pytest workflow_controller/tests/test_prototype_review.py -q` -> `10 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `501 passed in 70.56s`

## 会话：2026-05-20

### Controller Verifier 失败后的 Builder 精确复现闭环
- **状态：** implementation verified.
- Builder prompt 现在在上一轮 `lastFailure.stage == VERIFY_UNIT` 且存在具体 failed command 时注入 `Controller Verification Failure Protocol`，明确 failed command index、exact command、controller cwd、returncode、`verification.json` 路径、env keys 和 stdout/stderr tail。
- Builder 被要求第一动作复跑 controller 的 exact failed command；DONE 前必须在 `done_payload.controller_failure_resolution` 记录 failed command、复现结果、root cause 或 mismatch analysis、fix summary、同命令 rerun exit code 和完整 approved verification list 运行结果。
- Controller 在 Builder 完成后校验该 resolution：缺少 `controller_failure_resolution` 或 `failed_command` 与上一轮 verifier `lastFailure.details.command` 不一致时，直接阻塞在 `EXECUTE_UNIT`，不会进入 Refiner。
- Verifier 重复失败 fingerprint 不再把完整 stdout/stderr tail 纳入 hash；改用 stage、issue type、command、returncode 和 Playwright test title / error class / timeout 等稳定失败特征。stdout/stderr tail 仍保留在 `lastFailure.details` 和摘要中用于排查。
- 正式工作流文档已同步 `docs/workflow.md` 和 `docs/workflow.zh-CN.md`。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_builder.py workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_claude_runner_pastes_short_dispatch_that_points_to_full_prompt workflow_controller/tests/test_rrc_controller.py::test_repeated_verification_failure_blocks_before_another_retry workflow_controller/tests/test_rrc_controller.py::test_repeated_playwright_timeout_fingerprint_ignores_volatile_output_tail workflow_controller/tests/test_rrc_controller.py::test_builder_done_after_verifier_failure_requires_controller_failure_resolution workflow_controller/tests/test_rrc_controller.py::test_builder_done_after_verifier_failure_rejects_mismatched_failed_command workflow_controller/tests/test_rrc_controller.py::test_builder_done_after_verifier_failure_with_matching_resolution_enters_refiner -q` -> `12 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `183 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_real_runtime.py -q` -> `21 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `493 passed in 73.29s`

### Plannotator 远程开关与 controller preview 固定端口修复
- **状态：** implementation verified; packaged as `0.6.0j`.
- Waygate 启动 Plannotator 时改为传入 `PLANNOTATOR_REMOTE=1` 和 `PLANNOTATOR_PORT=<port>`，不再向子进程注入 bind host 环境变量。
- Controller prototype preview server 默认固定使用 `20001` 端口；`WAYGATE_PREVIEW_PORT` 可覆盖该端口，`WAYGATE_DISPLAY_HOST` 继续只影响终端展示 URL。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `179 passed`
  - `python3 -m pytest workflow_controller/tests/test_prototype_review.py -q` -> `10 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `488 passed in 70.72s`
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.0j_all.deb`
  - `dpkg-deb --field dist/waygate_0.6.0j_all.deb Package Version Architecture Depends` -> `waygate / 0.6.0j / all / python3`

### Plannotator / prototype preview URL 主 IP 展示修复
- **状态：** implementation verified; packaged as `0.6.0j`.
- 修复现场问题：终端不再把 Plannotator 审批页和原型渲染预览页展示为 `http://0.0.0.0:<port>`；`0.0.0.0` 只保留为 bind/listen 地址。
- 新增 `workflow_controller/networking.py`，默认通过本机 outbound route 推导主 IPv4 地址，并用该地址拼接浏览器可打开的 Plannotator / prototype preview URL；可用 `WAYGATE_DISPLAY_HOST` 显式覆盖展示 host。
- Controller prototype preview server 默认绑定 `0.0.0.0`；当前修正后 Plannotator 子进程通过 `PLANNOTATOR_REMOTE=1` 请求远程访问，不再注入 bind host 环境变量。
- README、USAGE、ROADMAP、CHANGELOG 和 recommended-environment 文档已同步：`0.0.0.0` 是监听地址，不再作为默认浏览器目标展示。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_prototype_review.py -q` -> `9 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `179 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `487 passed in 68.55s`
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.0j_all.deb`
  - `dpkg-deb --field dist/waygate_0.6.0j_all.deb Package Version Architecture Depends` -> `waygate / 0.6.0j / all / python3`
  - `dpkg-deb -c dist/waygate_0.6.0j_all.deb | rg 'workflow_controller/networking.py|recommended-environment|USAGE|README'` -> package contains the new helper and updated docs.

### V0.6.0j Requirements 基础设施追问友好化
- **状态：** implementation verified; version unchanged.
- Requirements no-`--spec` prompt 现在把基础设施追问拆成“面向用户的基础设施追问模板”和“面向 agent 的记录与验证要求”：用户看到温和、可部分回答、有示例的问题；agent 仍保留首次澄清、4.8 留痕、4.9 来源/验证状态和非破坏性核对要求。
- 默认用户追问文案按 3 组组织：代码与运行、调试与资料、参考与依赖；prompt 明确要求不要把 controller 门禁规则、4.8/4.9 结构、blocked、DONE_FILE 或“必须/不得/阻断/占位”等词原样作为用户追问文案。
- Validator 语义未放宽：本次只改 Requirements prompt 和 prompt 测试；`## 4.9` 对空泛 `暂无/不清楚`、无 4.8 问答/核对记录的“用户确认/已验证”仍按既有 preflight 规则阻断。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py::test_requirements_prompt_uses_grouped_friendly_infrastructure_followup workflow_controller/tests/test_rrc_human_gates.py::test_requirements_prompt_discourages_raw_gate_rule_wording_as_user_followup workflow_controller/tests/test_rrc_human_gates.py::test_requirements_prompt_without_spec_requires_infrastructure_gap_followup_and_verification workflow_controller/tests/test_rrc_human_gates.py::test_requirements_prompt_without_spec_keeps_agent_side_clarification -q` -> `4 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `70 passed`
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `55 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `485 passed in 70.09s`

### V0.6.0j Requirements 基础设施缺口追问与验证优化
- **状态：** implementation verified; full regression passed; packaged as `0.6.0j`。
- 无 `--spec` Requirements prompt 现在保持第一轮只澄清、不读项目、不写 gate；用户给出具体回答后，要求读取项目上下文、盘点 `## 4.9` 七类基础设施缺口，缺口仍存在时继续在 tmux pane 中直接追问用户。
- 用户补充代码仓库、运行环境、调试入口、参考环境、文档、接口和依赖后，prompt 要求优先通过本地 repo、配置文件、README/USAGE、docs、state-dir artifact、package manifest、测试命令等非破坏性来源核对；无法访问的外部系统、生产环境、私有 wiki/API 必须标注“用户提供，未能直接验证”并说明原因。
- Requirements `## 4.8` 现在明确要求记录基础设施追问问题、用户回答、核对方式、验证结论和残余风险；`## 4.9` 要求每类基础设施事实写明事实来源和验证状态。
- Requirements validator 继续拒绝 `暂无`、`不清楚` 等占位值；对 `未发现` / `没有` / `不涉及` 要求已检查来源、4.8 用户确认问答或具体原因；当 4.9 声称“用户确认”或“已验证”时，要求 4.8 有对应问答、验证方式和验证结论。
- 正式文档已同步 `docs/workflow.md` / `docs/workflow.zh-CN.md`，并更新 README、USAGE、ROADMAP、CHANGELOG、`task_plan.md` 和 `findings.md`；版本更新为 `0.6.0j`。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py::test_requirements_prompt_without_spec_requires_infrastructure_gap_followup_and_verification -q` -> `1 passed`
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py::test_requirements_preflight_rejects_docs_address_none_placeholder workflow_controller/tests/test_acceptance_obligations.py::test_requirements_preflight_rejects_unclear_runtime_environment workflow_controller/tests/test_acceptance_obligations.py::test_requirements_preflight_accepts_missing_external_docs_after_checked_sources workflow_controller/tests/test_acceptance_obligations.py::test_requirements_preflight_rejects_missing_infrastructure_fact_without_checked_source_or_reason workflow_controller/tests/test_acceptance_obligations.py::test_requirements_preflight_accepts_user_confirmed_absent_external_docs_with_qa_record workflow_controller/tests/test_acceptance_obligations.py::test_requirements_preflight_rejects_user_confirmed_fact_without_qa_record workflow_controller/tests/test_acceptance_obligations.py::test_requirements_preflight_rejects_verified_infrastructure_fact_without_validation_record -q` -> `7 passed`
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `55 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `68 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `179 passed`
  - `python3 -m pytest workflow_controller/tests/test_packaging.py -q` -> `3 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_real_runtime.py workflow_controller/tests/test_rrc_e2e.py -q` -> `22 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `483 passed in 69.18s`
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.0j_all.deb`
  - `dpkg-deb --field dist/waygate_0.6.0j_all.deb Package Version Architecture Depends` -> `waygate / 0.6.0j / all / python3`
  - `WAYGATE_LIB_DIR=<extract>/usr/lib/waygate <extract>/usr/bin/waygate --version` -> `waygate 0.6.0j`

### V0.6.0i 文档生命周期
- **状态：** implementation verified; full regression passed.
- `waygate init/start` 现在创建 `docs/README.md` 文档入口和四个 `docs/*` 子目录；已有 `docs/README.md` 时生成 `docs/README.md.generated`，不覆盖用户文件。
- `AGENTS.md` 模板和根目录规范已加入 `docs/README.md` 必读项，并明确 `task_plan.md` / `progress.md` / `findings.md` 是过程与决策事实源，`.rrc-controller-*` 是审计证据，不是长期文档入口。
- Requirements `## 4.9 目标项目基础设施信息` 的 `文档地址` 现在要求结构化盘点正式维护文档、Controller 过程证据、外部 Agent / 人工沟通文档、外部 wiki / 设计稿 / API 文档、缺失但需要沉淀的文档；空泛 `docs/`、`README/USAGE` 会被预检拒绝。
- Unit Plan 新增 Document Deliverables Matrix prompt 和 validator；长期产品/架构/流程/运维/证据规则变更必须声明文档动作或明确不需要正式文档变更及原因。
- Final Acceptance 现在渲染 Document Deliverables Status，并且只阻断 Unit Plan 标记 `Required For Acceptance = true` 的缺失文档。
- 已完成定向验证：
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `48 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `67 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `179 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_e2e.py -q` -> `1 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_real_runtime.py -q` -> `21 passed`
  - `python3 -m pytest workflow_controller/tests/test_packaging.py workflow_controller/tests/test_diagnostics.py -q` -> `17 passed`
- 已完成全量验证：
  - `python3 -m pytest workflow_controller/tests -q` -> `475 passed in 69.21s`

## 会话：2026-05-19

### V0.6.0h tmux 推荐配置与 Doctor CLI 信息层级
- **状态：** complete
- `waygate doctor` 顶部新增 `summary:`、`focus:` 和 `action_required:`，先展示 overall status、warning/manual action 数量、P1/P2/P3 关注项和需要人工处理的事项，再保留 executable/module/dpkg/PATH、`warnings`、`environment_checks`、`tmux_config`、skills 和 `claude_assets` 详细清单。
- `waygate doctor --color auto|always|never` 已支持给状态、P1 关注项、manual action 和 section 标题上色；非 TTY 输出默认保持纯文本，便于日志和脚本消费。
- 新增 `tmux_config` 诊断：固定读取 `HOME/.tmux.conf`，检查 `set -g mouse on`、`set -g history-limit 100000`、`set -g @scroll-speed 5` 和 `set -g @copy-mode-vi 'on'`；支持 `set` / `set-option`、简单引号解析和同 key 后写覆盖。
- Doctor 对 tmux 配置保持只读：缺失或不匹配时输出 `status=warning`、expected/actual 和 manual action，不修改用户配置、不 reload tmux，也不输出无关配置行。
- 文档已同步 README / README.zh-CN / USAGE / USAGE.zh-CN / ROADMAP / ROADMAP.zh-CN / CHANGELOG / CHANGELOG.zh-CN / docs/operations recommended environment；版本更新为 `0.6.0h`。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_diagnostics.py -q` -> `14 passed`
  - `python3 -m pytest workflow_controller/tests/test_packaging.py -q` -> `3 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `464 passed in 70.92s`
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.0h_all.deb`
  - `dpkg-deb --field dist/waygate_0.6.0h_all.deb Version` -> `0.6.0h`
  - `WAYGATE_LIB_DIR=/tmp/waygate-0.6.0h-extract/usr/lib/waygate /tmp/waygate-0.6.0h-extract/usr/bin/waygate --version` -> `waygate 0.6.0h`

### V0.6.0f 收尾与 V0.6.0g Doctor / 远程审阅可达性
- **状态：** complete
- V0.6.0f 已按人类可读记录收尾：代码版本、CHANGELOG 和 ROADMAP 均记录真实 E2E evidence gate 已交付；历史 `.rrc-controller-v0.6.0f/session.json` 仍保持原 active state，没有手工改成 DONE。
- V0.6.0g 已实施：`waygate doctor` 新增 `claude_assets`，只报告 `~/.claude/commands`、`agents`、`rules`、`plugins` 的路径、状态和数量，不读取 cache、file-history、secret 或环境变量值。
- `skill_recommendations` 已与 README 推荐基线对齐，补齐 code review、plan execution、webapp testing，以及 README 中已有的 `frontend-design` / `ui-ux-pro-max` UI-heavy requirements 推荐组。
- Controller prototype preview server 默认绑定 `0.0.0.0`；后续已通过 2026-05-20 主 IP 展示修复把终端浏览器 URL 改为本机主 IP 或 `WAYGATE_DISPLAY_HOST`。
- Waygate 当前通过 `PLANNOTATOR_REMOTE=1` 请求 Plannotator 远程访问，并保留 `PLANNOTATOR_PORT`；不再由 Waygate 控制 Plannotator bind host。
- `workflow_controller.__version__` 更新为 `0.6.0g`，已生成 `dist/waygate_0.6.0g_all.deb`。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_diagnostics.py -q` -> `9 passed`
  - `python3 -m pytest workflow_controller/tests/test_prototype_review.py -q` -> `7 passed`
  - `python3 -m pytest workflow_controller/tests/test_packaging.py -q` -> `3 passed`
  - `python3 -m pytest workflow_controller/tests -q` -> `459 passed in 69.83s`
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.0g_all.deb`
  - `dpkg-deb --field dist/waygate_0.6.0g_all.deb Package Version Architecture Depends` -> `waygate / 0.6.0g / all / python3`
  - `WAYGATE_LIB_DIR=/tmp/waygate-0.6.0g-extract/usr/lib/waygate /tmp/waygate-0.6.0g-extract/usr/bin/waygate --version` -> `waygate 0.6.0g`
- 当前环境没有 `python` 命令，因此全量验证使用 `python3 -m pytest ...` 执行。

### `waygate doctor` skills 诊断调整
- **状态：** complete
- `waygate doctor` 现在扫描常见 agent skill 根目录：`~/.agents/skills`、`~/.codex/skills`、`~/.codex/superpowers/skills`、`~/.config/opencode/skills`，并支持 `WAYGATE_SKILL_ROOTS` 追加自定义目录。
- 输出新增 `skill_roots`、`installed_skills` 和 `skill_recommendations`；推荐项覆盖 startup、planning、requirements、TDD、debugging、test strategy、refiner 和 verification。
- `waygate doctor` 的 agent runner 检测只依据 `PATH` 中的 `claude` / `codex` CLI 是否可用。
- 本次移除非 CLI 本地应用条目扫描与相关说明，保留 CLI 环境检测和 skills 检测。
- 已完成验证：`python3 -m pytest workflow_controller/tests/test_diagnostics.py -q` -> `7 passed`；`python3 -m pytest workflow_controller/tests/test_packaging.py -q` -> `3 passed`；`python3 -m pytest workflow_controller/tests -q` -> `448 passed in 66.85s`。

## 会话：2026-05-18

### V0.6.0e development acceptance 终验同步
- **状态：** complete
- Controller Final Acceptance 已批准：`finalAcceptanceAccepted=true`，确认人为 human，hash 为 `sha256:03f58971c4b936c54198ffbbd84f8cf85887158f563c325fac1437cdc4cb83c7`。
- 当前目标 `Complete V0.6.0e development acceptance using current planning progress` 已标记为 `covered`；单元 `target-v0-6-0e` 已 `passes=true`。
- Final Acceptance evidence matrix 中 AC-01 到 AC-09 均 passed；Final Scope Audit 显示 AC coverage `9/9`、Journey coverage `6/6`、unexplained changed files `0`。
- 验证命令均已通过：`python3 -m pytest workflow_controller/tests/test_diagnostics.py -q`、`python3 -m pytest workflow_controller/tests/test_packaging.py -q`、`python3 -m pytest workflow_controller/tests/gates/test_gates_structure.py -q`、`bash packaging/debian/build-deb.sh`、`python3 -m pytest workflow_controller/tests -q`。
- 本次状态同步更新了 `task_plan.md` 和 `progress.md`；未发现新的 workflow decision、defect 或 risk，因此 `findings.md` 未新增终验记录。

## 会话：2026-05-17

### Requirements Plannotator 主审批对象修复
- **状态：** implementation verified; packaged as `0.6.0d`。
- Requirements 阶段的 Plannotator 主审阅/审批对象恢复为 `approvals/requirements-and-acceptance.md`；即使存在 `plannotator-review.html` 和 `prototype-review-manifest.json`，也不会把 HTML bundle 传给 `plannotator annotate`。
- 原型渲染预览保留：Requirements review 期间继续启动 controller preview server，终端单独输出 `▶ Plannotator 审批页: http://localhost:20000` 和 `▶ 原型渲染预览页: http://127.0.0.1:<port>/plannotator-review.html`。
- `requirements-last-review.json` / event payload 记录 approval gate、辅助预览文件、manifest 路径和临时 preview URL；approval 文件不写入 `127.0.0.1:<port>` 这类临时 URL。
- `workflow_controller.__version__` 更新为 `0.6.0d`，并同步 CHANGELOG、ROADMAP、USAGE 中的当前行为说明。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_requirements_plannotator_review_path_uses_approval_gate_even_with_prototype_bundle workflow_controller/tests/test_rrc_controller.py::test_drive_plannotator_reviews_requirements_bundle_when_available_and_keeps_approval_gate_separate -q` -> `2 passed`
  - `python3 -m pytest workflow_controller/tests/test_prototype_review.py -q` -> `7 passed`
  - `PATH="/tmp/waygate-test-bin:$PATH" python -m pytest workflow_controller/tests -q` -> `438 passed in 65.33s`
  - `PATH="/tmp/waygate-test-bin:$PATH" bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.0d_all.deb`
  - `dpkg-deb --field dist/waygate_0.6.0d_all.deb Package Version Architecture Depends` -> `waygate / 0.6.0d / all / python3`
  - `WAYGATE_LIB_DIR=/tmp/waygate-0.6.0d-extract/usr/lib/waygate /tmp/waygate-0.6.0d-extract/usr/bin/waygate --version` -> `waygate 0.6.0d`

### 目标项目基础设施 intake 全局化与 Waygate 来源诊断
- **状态：** implementation verified; system install blocked by interactive sudo。
- Requirements Draft prompt 不再只对 V0.6.0 注入基础设施 intake；所有目标项目都会要求固定 `## 4.9 目标项目基础设施信息`，覆盖代码仓库、运行时、调试、参考环境、文档、架构/交互/接口和依赖信息。
- Requirements preflight 已阻断缺失 4.9、缺任一基础设施类别、或类别内容为空/TBD/待补/不清楚；validation-only revision 也会保留该要求，不能只修其他 preflight 错误后进入人工确认。
- 新增 `waygate doctor` 诊断：输出 executable path、module path/version、dpkg version、PATH 中所有 `waygate` 候选，并在 `~/.local/bin/waygate` 位于 `/usr/bin/waygate` 前时报告 shadow warning。
- Debian build 已强制 `WAYGATE_VERSION` 不得与 `workflow_controller.__version__` 不一致；包内 wrapper 支持 `WAYGATE_LIB_DIR` 以便解包验证；postinst 会警告用户级 wrapper，但不删除用户文件。
- `workflow_controller.__version__` 更新为 `0.6.0c`，并重新打包 `dist/waygate_0.6.0c_all.deb`。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_packaging.py -q` -> `3 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/test_acceptance_obligations.py -q` -> `97 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_diagnostics.py workflow_controller/tests/test_packaging.py -q` -> `182 passed`
  - `PATH="/tmp/waygate-test-bin:$PATH" python -m pytest workflow_controller/tests -q` -> `437 passed in 64.19s`
  - `PATH="/tmp/waygate-test-bin:$PATH" bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.0c_all.deb`
  - 解包验证：`WAYGATE_LIB_DIR=/tmp/waygate-0.6.0c-extract/usr/lib/waygate /tmp/waygate-0.6.0c-extract/usr/bin/waygate --version` -> `waygate 0.6.0c`；`doctor` 能报告当前 `.local/bin/waygate` shadow。
- 现场恢复未执行：`sudo apt install -y ./dist/waygate_0.6.0c_all.deb` 失败于 `sudo: a terminal is required to read the password`，因此未移动 `~/.local/bin/waygate`，也未在 `/home/lichangkun/code/proxy-collector` 执行 V1.8.4 Requirements revision。

### V0.6.0c development acceptance 终验同步
- **状态：** complete
- Controller Final Acceptance 已批准：`finalAcceptanceAccepted=true`，确认人为 human，hash 为 `sha256:75feebccb4ebb9a5b431b503cc721e02435ce74c4e4ffda82eb3214cc85a2f6b`。
- 当前目标 `Complete V0.6.0c development acceptance using current planning progress` 已标记为 `covered`；单元 `target-v0-6-0c` 已 `passes=true`。
- Final Acceptance evidence matrix 中 AC-01 到 AC-15 均 passed 或具备 manual evidence；Final Scope Audit 显示 AO coverage `5/5`、AC coverage `15/15`、Journey coverage `5/5`、unexplained changed files `0`。
- Golden Path `TC-V060C-AC15-FULL-PYTEST` 已 passed：`PATH="/tmp/waygate-test-bin:$PATH" python -m pytest workflow_controller/tests -q` -> `428 passed in 58.76s`。
- 本次状态同步更新了 `task_plan.md` 和 `progress.md`；未发现新的 workflow decision、defect 或 risk，因此 `findings.md` 未新增终验记录。

## 会话：2026-05-16

### Requirements 自动打回连续原因计数修复
- **状态：** complete
- 修复 Requirements 草案 controller 预检自动打回预算：默认 `requirementsAutoRevisionMax=2` 现在表示“连续相同 invalid reason 最多自动修订 2 次”，而不是整轮 Requirements 草案总共只能修订 2 次。
- 当本次预检错误与上一次不同，例如从缺 `prototype-manifest.json` 变为缺 `surface_contracts[]`，再变为 Journey verification layer 缺失，会视为新的有效打回并重置连续计数。
- 相同 reason 连续重复失败仍会阻塞，避免 agent 在同一个错误上无限自动修订。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_requirements_auto_revision_budget_resets_when_invalid_reason_changes workflow_controller/tests/test_rrc_controller.py::test_requirements_auto_revision_budget_still_blocks_repeated_same_reason -q` -> `2 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_drive_auto_revises_pending_requirements_gate_before_human_review workflow_controller/tests/test_rrc_controller.py::test_drive_auto_revises_requirements_when_plannotator_approve_fails_controller_validation workflow_controller/tests/test_rrc_controller.py::test_drive_refreshes_pending_requirements_invalid_reason_from_current_gate -q` -> `3 passed`
  - `PATH="/tmp/waygate-test-bin:$PATH" python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `176 passed`
  - `PATH="/tmp/waygate-test-bin:$PATH" python -m pytest workflow_controller/tests -q` -> `428 passed in 58.04s`

### Prototype Surface Conformance 流程修复
- **状态：** complete
- `prototype-manifest.json` 现在支持 `surface_contracts[]`，并兼容 `ui_surfaces[]` / `page_state_targets[]`；每个 required surface 必须声明 id/title/kind/page_states/click_path/entrypoints/implementation_targets/linked_acceptance_criteria/required。
- HTML/URL 原型出现弹窗、抽屉、选择器、管理面板等多 surface 信号但未声明 `surface_contracts` 时，Requirements preflight 会阻断；legacy 单 route/page manifest 继续按 prototype-level `implementation_targets` 兼容。
- Plannotator review bundle 新增 `Prototype Surface Coverage Matrix`，人工确认 Requirements 时可看到每个 surface、真实入口和生产目标。
- Unit Plan prototype conformance 校验改为按 `prototype + surface + production target` 分组；相邻弹窗测试不能代替当前 surface，真实浏览器 surface 要求 E2E、`prototype_surfaces`、`production_targets`、`user_steps` 和具体 expected。
- Final Acceptance `Prototype Conformance Matrix` 新增 Surface 和 Entry Point 列；终验阻断逻辑按 `test_case_id` 对齐 verifier evidence，避免同一 command 误覆盖相邻 surface。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_prototype_review.py -q` -> `7 passed`
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `30 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `62 passed`
  - `PATH="/tmp/waygate-test-bin:$PATH" python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `174 passed`
  - `PATH="/tmp/waygate-test-bin:$PATH" python -m pytest workflow_controller/tests -q` -> `426 passed in 57.98s`

### Plannotator 原型审阅可达性增强
- **状态：** complete
- Requirements 人工确认选择 Plannotator 审阅后，controller 现在同时打印两个显眼入口：`▶ Plannotator 审批页: http://localhost:<port>` 和 `▶ 原型渲染预览页: http://127.0.0.1:<port>/plannotator-review.html`。
- `--color always` / `auto` 有色输出会高亮这两条入口；`--color never` 保持纯文本格式。
- `plannotator-review.html` 新增 `Prototype Links` 表格，并在各 prototype preview 卡片内提供明确 source 链接：本地 HTML 使用 `Open rendered source`，本地 Markdown 使用 `Open markdown/source doc`，图片使用 `Open image`，外部 URL 保留链接和 iframe。
- 本地 HTML prototype 继续以内嵌 `iframe srcdoc` 渲染；source 链接只出现在 controller preview server 提供的 HTML review 页面内，不生成 `localhost:20000/prototypes/...` 链接。
- Preview server 明确返回 `.md` 为 `text/markdown; charset=utf-8`、`.html` 为 `text/html; charset=utf-8`。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_prototype_review.py -q` -> `4 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_drive_plannotator_reviews_requirements_bundle_when_available_and_keeps_approval_gate_separate -q` -> `1 passed`
  - `PATH="/tmp/waygate-test-bin:$PATH" python -m pytest workflow_controller/tests -q` -> `415 passed in 57.78s`
  - `PATH="/tmp/waygate-test-bin:$PATH" bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.0b_all.deb`
  - `dpkg-deb --field dist/waygate_0.6.0b_all.deb Package Version Architecture Depends` -> `waygate / 0.6.0b / all / python3`

### Plannotator 原型 HTML 纯文本预览修复
- **状态：** complete
- 现场 2 号窗口 V2.9.1 复现：Requirements 人工确认中 Plannotator 打开 `plannotator-review.md`，其中 HTML 原型只是相对链接，点击后在 Plannotator 中按文档文本查看，无法看到浏览器渲染效果。
- 根因：V0.6.0a/b 已有只读 preview server 且 standalone HTML 的 `Content-Type` 正确为 `text/html`，但 controller 仍把 Markdown bundle 传给 Plannotator；Plannotator 对 Markdown 链接目标不承担浏览器渲染语义。
- 修复：prototype review bundle 现在同时生成 `plannotator-review.md` 和 `plannotator-review.html`；HTML bundle 内嵌本地 HTML prototype 的 `iframe srcdoc` 渲染预览，并保留 AC/Journey/Production Target 矩阵。
- Controller 在 Requirements prototype bundle 存在时优先把 `plannotator-review.html` 交给 Plannotator，preview server 的 `prototype_review_preview_url` 也指向 HTML bundle；Markdown bundle 继续保留作审计/兼容 artifact。
- 二次现场复现：用户点击 `http://localhost:20000/prototypes/.../v29-course-ops-clickable-prototype.html` 时仍看到 Plannotator 文本/SPA 视图；该地址属于 Plannotator 自身路由，不是 controller 临时 preview server。
- 二次修复：HTML review 中本地 HTML prototype 只以内嵌 `iframe srcdoc` 呈现，不再输出 `href="prototypes/..."` 的 standalone 相对链接，避免人工审阅时被引导到 Plannotator `/prototypes/...` 路由。
- 已用修复后的代码重建现场 V2.9.1 bundle：`/home/lichangkun/courses/.rrc-controller-v2.9.1/artifacts/requirements-draft/plannotator-review.html`，文件内已包含 V2.9.1 原型的 `iframe srcdoc` 渲染预览。
- 已再次重建现场 V2.9.1 bundle，确认 `plannotator-review.html` 内 `srcdoc=` 存在且 `href="prototypes/` 不再存在。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_prototype_review.py::test_prototype_review_bundle_normalizes_manifest_copies_assets_and_renders_markdown_and_html -q` -> 二次回归新增 `href="prototypes/"` 断言，修复前 failed，修复后 passed。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_drive_plannotator_reviews_requirements_bundle_when_available_and_keeps_approval_gate_separate -q` -> 修复前 failed，修复后 passed。
  - `python3 -m pytest workflow_controller/tests/test_prototype_review.py -q` -> `4 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `60 passed`。
  - `PATH="/tmp/waygate-test-bin:$PATH" python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `171 passed`。
  - `PATH="/tmp/waygate-test-bin:$PATH" python -m pytest workflow_controller/tests -q` -> `415 passed in 57.15s`。
- 已重新打包当前修复：`PATH="/tmp/waygate-test-bin:$PATH" bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.0b_all.deb`；`dpkg-deb --field` 确认为 `waygate / 0.6.0b / all / python3`，解包检查确认包内包含 `Standalone source` 修复。

### Requirements 预检修订重复澄清修复
- **状态：** complete
- 现场 2 号窗口 V2.9.1 复现：Requirements 预检第一次打回后，后续自动修订只剩 Journey layer 错误，但 prompt 仍执行无 `--spec` 首次澄清协议，导致 agent 重复询问 `## 4.8` 已经记录的范围、像素级一致性和真实页面 Playwright 验收问题。
- 根因定位在 `_render_requirements_draft_prompt()`：旧逻辑只根据 `requirementsSpec` 区分首次 intake 与 spec-backed drafting，没有识别 `requirementsRevisionFeedback` 表示已有 Requirements gate 和已澄清事实。
- 修复：当存在 `requirementsRevisionFeedback` 时，Requirements prompt 切换为 revision drafting 协议，要求复用已有 gate、Requirements Dialogue Brief、controller validation error 和 `## 4.8`，只在当前错误无法从既有事实解决时再问新的阻断澄清。
- 已新增回归 `test_requirements_revision_prompt_reuses_prior_clarifications`，覆盖预检自动打回后不得重复询问已澄清问题；初次无 spec 强制澄清和 spec-backed drafting 行为保持不变。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py::test_requirements_revision_prompt_reuses_prior_clarifications -q` -> 修复前 `1 failed`，修复后 passed。
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py::test_requirements_revision_prompt_reuses_prior_clarifications workflow_controller/tests/test_rrc_human_gates.py::test_requirements_prompt_without_spec_keeps_agent_side_clarification workflow_controller/tests/test_rrc_human_gates.py::test_requirements_prompt_with_spec_skips_mandatory_clarification_and_expands_matrices -q` -> `3 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `60 passed`。
  - `python3 -m pytest workflow_controller/tests/test_rrc_controller.py::test_requirements_revision_feedback_includes_controller_validation_error workflow_controller/tests/test_rrc_controller.py::test_drive_auto_revises_requirements_when_plannotator_approve_fails_controller_validation -q` -> `2 passed`。
  - `PATH="/tmp/waygate-test-bin:$PATH" python -m pytest workflow_controller/tests -q` -> `415 passed in 57.20s`。

### V0.6.0b Prototype Conformance Gate 实施
- **状态：** complete
- 新增 prototype manifest 合约：`implementation_targets` 必须把每个 UI/Web prototype 映射到真实生产目标，兼容 `production_targets` / `real_targets`，并在 Plannotator review bundle 中展示 Production Targets。
- Requirements 预检现在会从正文识别 prototype / clickable webpage prototype / UI contract 等原型义务；即使 `currentUnitNeedsUiDesign` 没打开，也会要求合法 `prototype-manifest.json` 和真实实现目标映射。V0.6.0/V0.6.0a/V0.6.0b controller policy work 保持例外，不要求 controller 自己提供业务原型。
- Unit Plan 预检新增 prototype conformance 校验：每个 implementation target 必须有真实生产 UI 测试；测试用例需要 `prototype_conformance`、`production_targets`、具体 command 和非弱 expected，浏览器 route/page 必须是 E2E；只打开 `requirements-draft/prototypes`、`prototype-review` 或 `file://...prototype` 的测试会被拒绝。
- Final Acceptance 新增 `Prototype Conformance Matrix`，展示 Prototype、Linked AC、Production Target、Test Case、Command、Status；缺失或未 passed 的 required row 会阻断终验。
- Controller State Patch 支持并保留 `currentUnitIsWebSystem`；Requirements/Unit Plan prompt 和 gate template 已同步。
- `workflow_controller.__version__` 更新为 `0.6.0b`，双语 USAGE/CHANGELOG/ROADMAP、`task_plan.md` 和 `findings.md` 已同步。
- 当前环境没有 `python` 命令，验证时使用临时 PATH shim `python -> python3` 运行既有会执行 `python -c` 的回归用例。
- 已完成验证：
  - `python3 -m pytest workflow_controller/tests/test_prototype_review.py -q` -> `4 passed`
  - `python3 -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `27 passed`
  - `python3 -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `59 passed`
  - `PATH="/tmp/waygate-test-bin:$PATH" python3 -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `171 passed`
  - `PATH="/tmp/waygate-test-bin:$PATH" python -m pytest workflow_controller/tests -q` -> `414 passed in 57.66s`
  - `PATH="/tmp/waygate-test-bin:$PATH" bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.0b_all.deb`
  - `dpkg-deb --field dist/waygate_0.6.0b_all.deb Package Version Architecture Depends` -> `waygate / 0.6.0b / all / python3`

## 会话：2026-05-15

### V0.6.0a Prototype Review Bundle 实施
- **状态：** complete
- 已先提交 V0.6.0 基线：`dc3cd0b chore: finalize v0.6.0 baseline`。
- 新增 `workflow_controller/prototype_review.py`：读取 `artifacts/requirements-draft/prototype-manifest.json`，校验原型 id/type/path-or-URL/title/AC/Journey/page states/click path，复制本地图片/HTML 到 `artifacts/requirements-draft/prototypes/`，生成 `prototype-review-manifest.json` 和 `plannotator-review.md`。
- Requirements Plannotator 审阅现在在存在 bundle 时打开 `plannotator-review.md`，approval gate 仍是 `approvals/requirements-and-acceptance.md`；Plannotator summary/event 记录 review path、approval gate path、manifest path 和 localhost preview URL。
- 新增只读 localhost preview server，仅服务 review bundle、normalized manifest、`prototypes/` 和 approval gate，并在 Plannotator 决策结束后关闭。
- Requirements preflight 强化为 UI/UX 或 Web 系统必须有合法 prototype manifest，并阻断缺文件、未知 AC、缺 page states、缺 click path、缺 AC 映射和敏感 URL query。
- `workflow_controller.__version__` 更新为 `0.6.0a`，双语 USAGE/CHANGELOG/ROADMAP 及 Requirements prompt/template 已同步。
- 已完成验证：
  - `python -m pytest workflow_controller/tests/test_prototype_review.py -q` -> `3 passed`
  - `python -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `24 passed`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `170 passed`
  - `python -m pytest workflow_controller/tests/test_packaging.py -q` -> `2 passed`
  - `python -m pytest workflow_controller/tests -q` -> `407 passed in 70.72s`
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.6.0a_all.deb`
  - `dpkg-deb --field dist/waygate_0.6.0a_all.deb Package Version Architecture Depends` -> `waygate / 0.6.0a / all / python3`

### V0.6.0a Prototype Review Bundle 路线图命名
- **状态：** complete
- 已将 Plannotator 原型审阅联动能力命名为 `V0.6.0a - Prototype Review Bundle for Plannotator`，并写入 `ROADMAP.md` 与 `ROADMAP.zh-CN.md`。
- 该版本定位为 V0.6.0 的体验补丁：Requirements 人工确认前生成 prototype manifest 和 Plannotator review bundle，让原型图、本地 HTML 原型、外部原型 URL 与 AC/Journey 映射能在 Plannotator 中直接审阅。
- 本次只固化路线图命名和范围，未修改 controller 实现代码。

### 测试用例契约强化路线图
- **状态：** complete
- 已将测试策略/测试用例质量治理规划写入 `ROADMAP.md` 和 `ROADMAP.zh-CN.md` 的 V0.6.2 Strict Test Presence 下。
- 新增 TC1–TC7 路线：Test Case Contract v1、`test_cases[]` 事实源收敛、旧格式迁移、严格 Unit Plan 预检、Test Case Review Agent、Verifier evidence 对齐和 Final Acceptance 矩阵升级。
- 本次只更新路线图与进度/发现记录，未修改 controller 实现代码。

## 会话：2026-05-14

### V0.6.0 Infrastructure Knowledge Base 终验同步
- **状态：** complete
- Controller Final Acceptance 已批准：`finalAcceptanceAccepted=true`，确认人为 human，hash 为 `sha256:515efa8ca6c7b92d6f2ad9e56096157cd466a49027e37fadafeea4dc882178ae`。
- 当前目标 `Complete V0.6.0 development acceptance using current planning progress` 已标记为 `covered`；单元 `v0-6-0-u1-infrastructure-intake-gate` 已 `passes=true`。
- Final Acceptance evidence matrix 中 AC-01 到 AC-13 均 passed；Final Scope Audit 显示 AO coverage `9/9`、AC coverage `13/13`、Journey coverage `6/6`、unexplained changed files `0`。
- 本次状态同步更新了 `task_plan.md` 和 `progress.md`；未发现新的 workflow decision、defect 或 risk，因此 `findings.md` 未新增终验记录。

### V0.5.6 Spec Intake & Dependency Documentation 终验同步
- **状态：** complete
- Controller Final Acceptance 已批准：`finalAcceptanceAccepted=true`，确认人为 human，hash 为 `sha256:570ca6ba96be0984d317a316a9b19faebeaf445988598be28b9eac8fbf4c0a7e`。
- 当前目标 `Complete V0.5.6 development acceptance using current planning progress` 已标记为 `covered`；单元 `v0-5-6-u1-spec-intake-dependency-docs` 已 `passes=true`。
- Final Acceptance evidence matrix 中 AC-01 到 AC-12 均 passed；Final Scope Audit 显示 AO coverage `4/4`、AC coverage `12/12`、Journey coverage `6/6`、unexplained changed files `0`。
- 本次状态同步更新了 `task_plan.md` 和 `progress.md`；未发现新的 workflow decision、defect 或 risk，因此 `findings.md` 未新增终验记录。

### auto-created Claude pane 初次 dispatch 清输入修复
- **状态：** complete
- 现场 `waygate go V2.9 --auto-approve` 失败于 Requirements drafter，summary 显示 tmux stderr 为 `can't find pane: %24`。
- 复盘 run events：`send-keys -t %24 C-c` 成功，0.2 秒后 `send-keys -t %24 C-u` 失败，说明 auto-created Claude pane 被初次 dispatch 前的 `C-c` 清输入动作中断/关闭。
- 修复：`make_runner()` 在 auto-created pane 的首次 Requirements Draft dispatch 中通过 request env 关闭清输入；tmux runner 现在优先读取 request env 的清输入开关。复用既有 pane、tmux-claude 正常清输入、tmux-codex 只发 `C-u` 的行为保持不变。
- 已验证 RED/GREEN：新增 `test_tmux_runner_request_env_can_disable_input_clear_for_auto_created_pane` 和 `test_make_runner_disables_initial_clear_for_auto_created_requirements_pane`，修复前均失败，修复后通过。
- 已验证：
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_runner_request_env_can_disable_input_clear_for_auto_created_pane workflow_controller/tests/test_rrc_agent_runners.py::test_make_runner_disables_initial_clear_for_auto_created_requirements_pane -q` -> `2 passed`
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_dispatch_clears_input_before_submit_and_idle_nudge_does_not workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_claude_runner_clears_input_without_clearing_session_by_default workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_codex_runner_reuses_tmux_dispatch_and_records_backend -q` -> `3 passed`
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `34 passed in 16.99s`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_init_without_tmux_target_inside_tmux_creates_claude_pane workflow_controller/tests/test_rrc_controller.py::test_rrc_go_inside_tmux_auto_creates_claude_pane workflow_controller/tests/test_rrc_controller.py::test_auto_created_claude_pane_permission_mode_can_be_overridden workflow_controller/tests/test_rrc_controller.py::test_auto_created_claude_pane_command_can_be_overridden -q` -> `4 passed`
  - `python -m pytest workflow_controller/tests -q` -> `386 passed in 70.54s`

### auto-created Claude pane stale state 恢复
- **状态：** complete
- 用户复测 `waygate go V2.9 --auto-approve` 后仍失败；新的 `requirements-draft-summary.json` 显示 runner dispatch 到 `%24` 时 `tmux send-keys` 返回 `can't find pane: %24`。
- 复盘确认这次不再是 `C-c` 清输入杀 pane：runner metadata 已携带 `WAYGATE_TMUX_CLEAR_INPUT_BEFORE_DISPATCH`，events 没有 dispatch 前 `C-c` / `C-u`，失败发生在复用旧 state 的 stale `%24`。
- 已按 TDD 新增回归 `test_rrc_go_recreates_stale_auto_created_claude_pane_on_resume`：修复前失败于 resume 后仍保留 `%88`，修复后在 stale old target 时自动创建 `%89` 并更新 state。
- 修复：恢复已有 target acceptance state 时，对 controller 自动创建的 `tmux-claude` pane 重新探测；如果探测结果完全为空，调用 auto-create 路径重建 Claude pane。显式用户 target 不做静默替换。
- 已验证：
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_rrc_go_recreates_stale_auto_created_claude_pane_on_resume -q` -> `1 passed`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_rrc_go_inside_tmux_auto_creates_claude_pane workflow_controller/tests/test_rrc_controller.py::test_rrc_go_recreates_stale_auto_created_claude_pane_on_resume workflow_controller/tests/test_rrc_controller.py::test_rrc_go_with_tmux_target_detects_codex_pane workflow_controller/tests/test_rrc_controller.py::test_rrc_go_with_tmux_codex_runner_auto_discovers_codex_pane workflow_controller/tests/test_rrc_agent_runners.py::test_make_runner_disables_initial_clear_for_auto_created_requirements_pane -q` -> `5 passed`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `167 passed in 13.98s`
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `34 passed in 16.79s`
  - `python -m pytest workflow_controller/tests -q` -> `387 passed in 69.69s`
- 已重新打包：`WAYGATE_VERSION=0.5.6 bash packaging/debian/build-deb.sh` -> `dist/waygate_0.5.6_all.deb`。
- 打包验证通过：`python -m pytest workflow_controller/tests/test_packaging.py -q` -> `2 passed`；`dpkg-deb --field dist/waygate_0.5.6_all.deb Package Version Architecture Depends` -> `waygate / 0.5.6 / all / python3`；解包检查确认包内 `rrc_controller.py` 包含 `_is_auto_created_tmux_claude_target`、`_tmux_target_inspection_is_missing` 和 `_auto_created_tmux_target_resolution`。

### Requirements 无 spec 强制澄清修复
- **状态：** complete
- 用户现场复测 V2.9 后指出：没有 `--spec` 时预期应该在 Agent pane 中一起问答澄清，但实际没有可见澄清问题，agent 直接读取项目、生成 Requirements。
- 根因：旧回归只检查 prompt 包含“必须澄清/不得写 DONE_FILE”，没有覆盖“第一轮只能问问题、不得先读项目/写 body、继续不是有效回答”；同时 prompt 中写 body_path 的指令排在澄清协议之前，且“可用保守假设推进时必须推进”与强制澄清冲突。
- 修复：无 `--spec` 的 Requirements Draft prompt 现在把澄清协议提到写文件指令之前，明确第一条回复只能包含澄清问题；收到具体澄清回答前不得读取项目文件、检索代码、生成 Requirements 正文或写入 body_path；「继续」「按你理解」「你看着办」不算有效澄清回答，必须继续追问或 blocked。
- 已验证 RED/GREEN：
  - `python -m pytest workflow_controller/tests/test_rrc_human_gates.py::test_requirements_prompt_requires_clarification_before_gate workflow_controller/tests/test_rrc_human_gates.py::test_requirements_prompt_without_spec_keeps_agent_side_clarification -q` -> 修复前 `2 failed`，修复后 `2 passed`
  - `python -m pytest workflow_controller/tests/test_rrc_human_gates.py::test_requirements_prompt_requires_clarification_before_gate -q` -> 顺序断言修复前失败于澄清协议晚于写文件指令，修复后通过
  - `python -m pytest workflow_controller/tests/test_rrc_human_gates.py::test_requirements_prompt_requires_clarification_before_gate workflow_controller/tests/test_rrc_human_gates.py::test_requirements_prompt_without_spec_keeps_agent_side_clarification workflow_controller/tests/test_rrc_human_gates.py::test_requirements_prompt_with_spec_skips_mandatory_clarification_and_expands_matrices -q` -> `3 passed`
  - `python -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `48 passed in 25.24s`
  - `python -m pytest workflow_controller/tests -q` -> `387 passed in 70.59s`
- 已重新打包：`WAYGATE_VERSION=0.5.6 bash packaging/debian/build-deb.sh` -> `dist/waygate_0.5.6_all.deb`。
- 打包验证通过：`python -m pytest workflow_controller/tests/test_packaging.py -q` -> `2 passed`；`dpkg-deb --field dist/waygate_0.5.6_all.deb Package Version Architecture Depends` -> `waygate / 0.5.6 / all / python3`；解包检查确认包内 prompt 包含“第一条回复只能包含澄清问题”、“不得先读取项目文件”和“不能视为有效澄清回答”，且不包含旧的“可用保守假设推进时必须推进”绕过语句。

### revise target state-dir 推导修复
- **状态：** complete
- 用户按建议在 `courses` 目录执行 `waygate revise --gate requirements --reason ...` 失败，错误为 Requirements 当前阶段不允许 revision。
- 现场 state 扫描确认 `.rrc-controller-v2.9/session.json` 实际位于 `WAITING_REQUIREMENTS_ACCEPTANCE`，可 revision；失败原因是 `revise` 默认读取 `.plan-ralph`，不像 `go V2.9` 自动推导 `.rrc-controller-v2.9`。
- 修复：`revise` 支持 positional target 和 `--target` / `--workspace-dir`，按 `go` 相同 slug 规则推导 `.rrc-controller-<target>`；仍保留无 target 时的 `.plan-ralph` 兼容默认。
- 已验证 RED/GREEN：
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_revise_with_target_infers_go_style_state_dir -q` -> 修复前失败于 `unrecognized arguments: V2.9`，修复后 `1 passed`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_revise_with_target_infers_go_style_state_dir workflow_controller/tests/test_rrc_human_gates.py::test_revise_requirements_gate_reruns_tmux_drafter_with_human_feedback workflow_controller/tests/test_rrc_human_gates.py::test_revise_requirements_gate_can_rewind_from_unit_plan_approval workflow_controller/tests/test_rrc_human_gates.py::test_revise_requirements_gate_can_rewind_from_plan_approved_with_reason -q` -> `4 passed`
  - `python -m pytest workflow_controller/tests -q` -> `388 passed in 70.43s`
- 已重新打包：`WAYGATE_VERSION=0.5.6 bash packaging/debian/build-deb.sh` -> `dist/waygate_0.5.6_all.deb`。
- 打包验证通过：`python -m pytest workflow_controller/tests/test_packaging.py -q` -> `2 passed`；`dpkg-deb --field dist/waygate_0.5.6_all.deb Package Version Architecture Depends` -> `waygate / 0.5.6 / all / python3`；解包后 `python3 -m workflow_controller.rrc_controller revise --help` 显示 positional `TARGET`、`--target` 和 `--workspace-dir`，并确认包内保留无 spec 强制澄清 prompt。

### tmux-codex 派发前清输入避免自退出
- **状态：** complete
- 复现并定位：tmux runner 默认清输入键 `C-c, C-u` 同时用于 `tmux-claude` 和 `tmux-codex`；Claude Code 可用 `C-c` 取消未提交草稿，但 Codex TUI 会把 `C-c` 解释为中断/退出当前 Codex，会在发送新 prompt 前把 agent 自己结束掉。
- 已改为 backend-specific 清理键：`tmux-claude` 继续使用 `C-c` 后 `C-u`，`tmux-codex` 默认只使用 `C-u` 清当前输入，不发送 `C-c`。
- 保留既有行为：正常 dispatch 前仍会清输入；idle nudge 不会清输入；Codex submit key、submit delay 和 submit retry 逻辑不变。
- 已验证 RED/GREEN：新增 Codex runner 回归断言，修复前失败于 `send-keys ... C-c` 仍出现，修复后通过。
- 已验证：
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_codex_runner_reuses_tmux_dispatch_and_records_backend workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_claude_runner_clears_input_without_clearing_session_by_default workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_dispatch_clears_input_before_submit_and_idle_nudge_does_not -q` -> `3 passed`
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `32 passed in 16.37s`
  - `python -m pytest workflow_controller/tests -q` -> `374 passed in 67.06s`

## 会话：2026-05-13

### Requirements Change 回退入口
- **状态：** complete
- 已补齐 `waygate revise --gate requirements --reason "<reason>"`：在 `PLAN_APPROVED` / `EXECUTE_UNIT` 且 Requirements 与 Unit Plan 已批准后，用户可显式创建 Requirements change request 并回到 Requirements 人工确认。
- Requirements revision prompt 会明确标注“这是 approved Requirements 后的需求变更，不是 Unit Plan 返工”，注入人工 `--reason`、当前 Unit Plan 约束上下文，以及最近 Builder blocked summary（如存在）；drafter 被要求把变更落到需求、AC、架构约束、范围外和测试策略中。
- 现场 8 号窗口 `/home/lichangkun/code/proxy-collector/.rrc-controller-v1.8.1` 复核确认：旧 approved Requirements 已在 prompt 中，但被放在 Unit Plan/blocker 后且只标成普通 feedback，导致新草案收缩成当前 CLI Proxy blocker 相关需求，丢掉“自动生成”“小眼睛”和 AC-04/AC-05 等后续单元需求。
- 已修复 Requirements change prompt：新增 `Approved Requirements Baseline (Preserve Unless Explicitly Changed)` section，把旧 approved gate 提升为必须保留的完整 baseline，并明确要求不要把 Requirements 收缩为当前 unit、Builder blocker 或 Unit Plan 片段；Unit Plan/blocker 只作为 delta 上下文。
- 回退会清除 Requirements / Unit Plan approval 状态与 hash/actor，删除当前 `approvals/unit-plan.md`，追加 `change_requests.jsonl` 的 `pending_requirements_approval` 记录，增加 `requirementsRevisionCount`，并回到 `WAITING_REQUIREMENTS_ACCEPTANCE`。
- `WAITING_FINAL_ACCEPTANCE` 仍不允许直接 `revise --gate requirements`，错误提示改为使用 final acceptance rejection route 选择 Requirements revision。
- Requirements revision prompt 的 Markdown code fence 现在会根据反馈内容自适应长度，避免 Unit Plan 的 fenced Controller State Patch 破坏外层 prompt。
- 修复验证中暴露 Plannotator 短命进程 hang：fake Plannotator 打印链接后退出会留下未回收子进程，旧 `_process_is_alive()` 用 `os.kill(pid, 0)` 把 zombie 当成 alive，导致 `drive` 一直等待浏览器决策；现在先用 `waitpid(..., WNOHANG)` 识别并回收已退出子进程。
- 已验证 RED/GREEN：新增 approved Unit Plan 后 Requirements revision、approved baseline 保留、CLI `--reason`、Final Acceptance 禁止直返 Requirements，以及 Plannotator 短命进程不再卡住的回归覆盖。
- 已验证：
  - `timeout 10 python -m pytest workflow_controller/tests/test_rrc_controller.py::test_drive_blocks_revise_after_plannotator_when_feedback_is_not_submitted -q` -> 修复前超时退出 `124`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_drive_blocks_revise_after_plannotator_when_feedback_is_not_submitted -q` -> `1 passed`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_revise_requirements_after_plan_approved_preserves_approved_baseline_before_blocker workflow_controller/tests/test_rrc_controller.py::test_revise_requirements_after_plan_approved_reopens_requirements_change_request -q` -> `2 passed`
  - `python -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `45 passed`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `159 passed in 11.42s`
  - `python -m pytest workflow_controller/tests -q` -> `374 passed in 48.61s`
- 已重新打包：`bash packaging/debian/build-deb.sh` -> `dist/waygate_0.5.4_all.deb`。
- 打包验证通过：`python -m pytest workflow_controller/tests/test_packaging.py -q` -> `2 passed`；`dpkg-deb --field dist/waygate_0.5.4_all.deb Package Version Architecture Depends` -> `waygate / 0.5.4 / all / python3`；解包检查确认包内包含 `Approved Requirements Baseline (Preserve Unless Explicitly Changed)`、`不要把 Requirements 收缩为当前 unit`、`os.waitpid(pid, os.WNOHANG)` 和 `--reason`；解包后 `python3 -m workflow_controller.cli revise --help` 可显示 `--reason REASON`。

### Builder blocked 恢复与人工评审草稿清理
- **状态：** complete
- Builder `blocked` 后的 Unit Plan 修订入口已补齐：`waygate revise --gate unit-plan` 现在支持在 `PLAN_APPROVED` / `EXECUTE_UNIT` 且当前 unit 的 `builder-summary.json` 表示 blocked 时回到 Unit Plan revision。
- Unit Plan revision prompt 会把 Builder `done_payload.summary` 放在最前面作为 blocker 上下文，并保留已有 Unit Plan gate / 人工反馈；Requirements approval 保留，Unit Plan approval hash 清除。
- 人工评审防串聊提醒改为单行文本，避免在 Claude 输入框里制造多行草稿。
- 正常 tmux dispatch 前的输入清理由 `C-u` 改为 `C-c C-u`：先取消未提交的多行草稿，再兜底清当前行；idle nudge 仍不清输入、不发送 `/clear`。
- 8 号窗口现场复核：06:46:31 runner 已发送 `C-c C-u` 且 returncode=0，但 9ms 内立即 paste 新 dispatch，Claude TUI 未及时处理取消，导致旧人工评审提醒仍残留在输入区并作为新 dispatch 前缀。已修复为 `C-c` 与 `C-u` 分开发送，每次后默认等待 0.2s settle；可用 `WAYGATE_TMUX_CLEAR_INPUT_SETTLE_SECONDS` / `RRC_TMUX_CLEAR_INPUT_SETTLE_SECONDS` 调整。
- 已验证 RED/GREEN：旧清理实现只发 `C-u C-u C-u` 时新增用例失败；改为 `C-c C-u` 后通过。
- 已验证：
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_claude_runner_clears_input_without_clearing_session_by_default -q` -> 修复前失败于仍是单条 `send-keys ... C-c C-u`，修复后 `1 passed`
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `32 passed`
  - `python -m pytest workflow_controller/tests -q` -> `374 passed in 65.84s`
- 已重新打包：`bash packaging/debian/build-deb.sh` -> `dist/waygate_0.5.4_all.deb`。
- 打包验证通过：`python -m pytest workflow_controller/tests/test_packaging.py -q` -> `2 passed`；`dpkg-deb --field dist/waygate_0.5.4_all.deb Package Version Architecture Depends` -> `waygate / 0.5.4 / all / python3`；解包检查确认包含 `DEFAULT_TMUX_CLEAR_INPUT_SETTLE_SECONDS = 0.2`、`WAYGATE_TMUX_CLEAR_INPUT_SETTLE_SECONDS`、分键 `send-keys ... key`、单行人工评审提醒和 `Builder Blocked Summary`。

## 会话：2026-05-12

### V0.5.4 人工评审防串聊与强制 Requirements 澄清
- **状态：** complete
- Controller Final Acceptance 已批准：`finalAcceptanceAccepted=true`，确认人为 human，hash 为 `sha256:5c23862c9a86a39cd8af05ac3637909b3d5bbbe338653b2db4507851d3f48e80`。
- 当前目标 `Complete V0.5.4 development acceptance using current planning progress` 已标记为 `covered`；单元 `v0-5-4-u1-review-boundary-and-version-rules` 已 `passes=true`。
- 已完成内容：
  - Requirements Draft prompt 强制先澄清，等待用户回答期间不写 `DONE_FILE`。
  - 澄清结论进入 `## 4.8 已澄清事项、关键假设与待确认风险`，并同步到需求、范围外、验收标准和测试策略。
  - Requirements、Unit Plan、Final Acceptance、Bug Fix 人工评审阶段向 `tmuxTarget` 粘贴中英文防串聊提醒，不提交、不推进 workflow。
  - 正常 tmux dispatch 默认先 `C-u` 清输入框，idle nudge 不清输入框，`WAYGATE_TMUX_CLEAR_INPUT_BEFORE_DISPATCH=0` 可关闭。
  - compact/status 展示项目目标版本分支；`waygate --version` 仍表示 package version。
  - 根目录 `AGENTS.md` 和 `workflow_controller/agent_guides.py` 生成模板补充版本规划规则。
- Final Acceptance evidence matrix 中 AC-01 到 AC-07 均 passed；Golden Path `python -m pytest workflow_controller/tests -q` 已 passed。
- 本次状态同步更新了 `task_plan.md` 和 `progress.md`；`findings.md` 没有新增决策、缺陷或风险，因此未修改。
- V0.5.4 打包完成：`workflow_controller.__version__` 更新为 `0.5.4`，双语 README/USAGE 安装示例和双语 CHANGELOG 已同步，已生成 `dist/waygate_0.5.4_all.deb`。
- 打包验证通过：`python -m pytest workflow_controller/tests/test_packaging.py -q` -> `2 passed`；`python -m pytest workflow_controller/tests -q` -> `363 passed in 50.22s`；`dpkg-deb --field dist/waygate_0.5.4_all.deb Version` -> `0.5.4`。
- Requirements Draft 澄清等待现场修复完成：默认 timeout 从 1800 秒调整为 7200 秒；超时消息改为“等了太久，先休息一下，等agent好了，再接着干”；超时后保留 `requirements-draft-summary.json` 中的 pending run 信息。下次运行会继续等待同一轮 run，不重新派发需求讨论；只有在 `done.json` 和 `requirements-body.md` 都存在、且二者修改时间都晚于 timeout 记录时间时，才直接生成 Requirements Gate；旧残留不会被误审核。
- 已验证：新增 RED/GREEN 覆盖 `test_requirements_draft_uses_two_hour_timeout_by_default`、`test_requirements_draft_timeout_resumes_existing_pending_run_without_redispatch`、`test_requirements_draft_recovers_legacy_timed_out_summary_when_done_run_and_body_exist`、`test_requirements_draft_does_not_recover_done_and_body_older_than_timeout` 和 `test_requirements_draft_waits_on_existing_timeout_run_until_fresh_body_arrives`；修订路径回归 passed；全量 `python -m pytest workflow_controller/tests -q` -> `368 passed in 52.00s`。
- tmux-claude 重复 dispatch 现场修复完成：根因是 submit retry 看到 Claude pane 里的历史 `workflow-controller dispatch` / RUN_ID 文本后，无法区分 transcript 和输入框残留，可能在第一轮完成后让 Claude 又开始同一个 RUN_ID。已禁用 tmux-claude 的歧义提交重试，保留 tmux-codex 的 prompt/input 重试。
- 已验证：`test_tmux_claude_does_not_retry_when_dispatch_text_is_visible_after_submit` RED/GREEN；Codex submit retry 三条回归 passed；`python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `32 passed in 11.77s`；全量 `python -m pytest workflow_controller/tests -q` -> `365 passed in 51.16s`。
- Builder blocked 错误提示现场修复完成：当 agent 写出 `DONE_FILE status=blocked` 且包含 `summary` 时，`run_builder()` 的 RuntimeError 现在会直接显示 `agent status=<status>: <summary>`，不再只输出 exit code 和 `builder-summary.json` 路径。
- 已验证 RED/GREEN：`test_run_builder_failure_error_includes_agent_done_summary` 先失败于错误信息缺少 blocker summary，修复后 passed。

## 会话：2026-05-09

### Final Acceptance 后 Agent 状态同步
- **状态：** complete
- 现场问题：Final Acceptance 由 controller / human gate 批准后，最后一轮实现 agent pane 已经停止，无法得知验收已通过，也就不会及时更新 `task_plan.md`、`progress.md`、`findings.md` 等状态文档。
- 根因：终验通过后原流程直接从 `WAITING_FINAL_ACCEPTANCE` 推到 `RELEASE_GATE` / `DONE`，中间没有再向 live tmux agent 派发 controller state transition。
- 修复：
  - 新增 `FINAL_ACCEPTANCE_AGENT_SYNC` 状态和 `sync_final_acceptance_agent` action。
  - Final Acceptance 通过后，如果 state 中存在 workspace 且配置了 `tmux-claude` / `tmux-codex` live pane，会先派发最终状态同步 prompt。
  - prompt 明确要求 agent 读取 `AGENTS.md`、`ROADMAP.md`、`task_plan.md`、`progress.md`、`findings.md`、`session.json` 和 final acceptance gate，只更新状态文档，不改源码、gate、controller state 或无关文件。
  - agent 必须写 `artifacts/final-acceptance-sync/final-sync-summary.json`；controller 将同步结果写入 `finalAcceptanceAgentSyncStatus` 和事件日志。
  - 无 workspace 或无 live tmux pane 时记录 `skipped`，不影响 dry-run、subprocess 和历史本地流程。
- 文档同步：
  - `README.md` / `README.zh-CN.md`
  - `USAGE.md` / `USAGE.zh-CN.md`
  - `docs/workflow.md` / `docs/workflow.zh-CN.md`
  - `docs/architecture.md` / `docs/architecture.zh-CN.md`
- 已验证 RED：
  - `python -m pytest workflow_controller/tests/state_machine/test_state_transitions.py::TestComputeNextAllowedAction::test_final_acceptance_agent_sync -q` -> 先失败于 action 为 `None`。
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_final_acceptance_approval_syncs_tmux_agent_before_release -q` -> 先失败于缺少 `workflow_controller.steps.final_sync`。
- 已验证 GREEN：
  - `python -m pytest workflow_controller/tests/state_machine/test_state_transitions.py -q` -> `36 passed in 0.05s`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_final_acceptance_approval_accepts_passed_journey_evidence workflow_controller/tests/test_rrc_controller.py::test_final_acceptance_approval_syncs_tmux_agent_before_release workflow_controller/tests/test_rrc_controller.py::test_dry_run_until_done_advances_workflow_and_writes_artifacts workflow_controller/tests/test_rrc_controller.py::test_non_dry_run_until_done_with_auto_approve_advances_to_done -q` -> `4 passed in 0.41s`
  - `python -m pytest workflow_controller/tests/test_rrc_human_gates.py::test_final_acceptance_gate_blocks_done_until_approved -q` -> `1 passed in 0.18s`
  - `python -m pytest workflow_controller/tests/test_packaging.py -q` -> `1 passed in 0.41s`
  - `python -m pytest workflow_controller/tests/test_rrc_e2e.py::test_e2e_controller_runs_target_through_tmux_runner_and_verifier -q` -> `1 passed in 3.80s`
  - `python -m pytest workflow_controller/tests -q` -> `356 passed in 47.46s`

## 会话：2026-05-07

### GitHub 发布脱敏与 superpowers 目录清理
- **状态：** complete
- 按发布要求移除已跟踪的 `docs/superpowers/` 目录，并在 `.gitignore` 中新增 `docs/superpowers/`，后续不再同步到远程。
- 全文清理与本机环境绑定的虚拟环境激活命令，统一改为直接运行 `python -m pytest ...`。
- 清理公开文档和维护记录中的本机绝对路径，将现场 target、运行副本、用户 bin、实现计划等替换为通用占位或通用说明。
- 同步更新 `AGENTS.md` 与 `workflow_controller/agent_guides.py` 中生成的标准验证命令，避免新项目 guide 继续写入本机路径。
- 已验证：
  - `python -m pytest workflow_controller/tests/test_packaging.py -q` -> `1 passed in 0.49s`
  - `python -m pytest workflow_controller/tests -q` -> `354 passed in 48.50s`
  - 本机路径和私有环境标识扫描无残留；tracked 文件中无 `docs/superpowers/`。

### GitHub 发布文档整理
- **状态：** complete
- 按用户确认的方案 A 整理 GitHub 对外呈现：英文作为默认入口，中文以 `.zh-CN.md` 完整保留，并在 README 顶部互链。
- `README.md` 已重写为 GitHub 风格英文入口，聚焦项目定位、能力、安装、Quick Start、workflow、文档索引和项目状态。
- 新增 `README.zh-CN.md`，保留完整中文入口。
- `USAGE.md` 改为英文 CLI 使用说明；新增 `USAGE.zh-CN.md`。
- `ROADMAP.md` 改为英文路线图；新增 `ROADMAP.zh-CN.md`。
- 新增双语架构和工作流文档：
  - `docs/architecture.md`
  - `docs/architecture.zh-CN.md`
  - `docs/workflow.md`
  - `docs/workflow.zh-CN.md`
- 新增 GitHub 社区文件：`LICENSE`、`CONTRIBUTING.md`、`CONTRIBUTING.zh-CN.md`、`CHANGELOG.md`、`CHANGELOG.zh-CN.md`、`SECURITY.md`、issue templates 和 PR template。
- `.gitignore` 已补充 `.rrc-controller-*/`、`.venv/`、coverage/cache 等发布忽略项，避免本地 controller state 和构建产物污染 GitHub。
- Debian package docs 安装清单已同步双语 README/USAGE/ROADMAP/CHANGELOG/LICENSE 和公开 docs，并更新 packaging 测试断言。
- 已验证：
  - 源码范围 Markdown 本地链接检查 -> `checked 23 source markdown files; all local links resolve`
  - `python -m pytest workflow_controller/tests/test_packaging.py -q` -> `1 passed in 0.58s`
  - `python -m pytest workflow_controller/tests -q` -> `354 passed in 51.27s`

### V1.6 tmux-codex runner 自动发现修复
- **状态：** complete
- 现场命令 `waygate go V1.6 --auto-approve --runner tmux-codex` 失败：`--runner=tmux-codex requires --tmux-target pointing at an existing Codex pane`。
- 根因：显式指定 `--runner tmux-codex` 且未指定 `--tmux-target` 时，controller 直接报错；只有默认/Claude 路径具备 tmux 自发现或自动创建行为，Codex 路径没有扫描当前 tmux session 中已有 Codex pane。
- 修复：`tmux-codex` 显式 runner 无 target 时会扫描当前 tmux session 的 panes，识别 Codex backend，优先选择 `pane_current_path` 等于目标 workspace 的 pane；若只有一个 Codex pane 也可使用；多个不匹配时继续阻断，避免派发到错误窗口。
- 现场烟测进一步暴露错投风险：controller pane 的进程参数可能包含 `--runner tmux-codex`，旧的宽松 substring 检测会把 controller pane 误识别为 Codex。已修复为跳过 `TMUX_PANE` 指向的当前 controller pane，并用 token 级匹配识别 `codex` / `claude`，不再把 `tmux-codex` / `tmux-claude` runner 参数当作 agent 信号。
- 不自动创建 Codex pane；未发现可用 pane 时仍要求用户显式传 `--tmux-target`。
- 已按 TDD 增加回归测试：
  - `test_init_with_explicit_tmux_codex_runner_auto_discovers_codex_pane`
  - `test_init_with_explicit_tmux_codex_runner_skips_current_controller_pane`
  - `test_rrc_go_with_tmux_codex_runner_auto_discovers_codex_pane`
  - `test_rrc_go_with_tmux_target_ignores_waygate_runner_argument_in_process_tree`
- 已验证 RED：新增测试在修复前分别失败于 `--runner=tmux-codex requires --tmux-target pointing at an existing Codex pane`、错误选择当前 controller pane `%24`、以及把 `--runner tmux-codex` 参数误判成 Codex process-tree。
- 已验证 GREEN：
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_init_with_explicit_tmux_codex_runner_auto_discovers_codex_pane workflow_controller/tests/test_rrc_controller.py::test_init_with_explicit_tmux_codex_runner_skips_current_controller_pane workflow_controller/tests/test_rrc_controller.py::test_rrc_go_with_tmux_codex_runner_auto_discovers_codex_pane workflow_controller/tests/test_rrc_controller.py::test_rrc_go_with_tmux_target_ignores_waygate_runner_argument_in_process_tree workflow_controller/tests/test_rrc_controller.py::test_rrc_go_with_tmux_target_detects_codex_from_process_tree workflow_controller/tests/test_rrc_controller.py::test_init_with_tmux_target_detects_codex_agent_and_selects_tmux_codex workflow_controller/tests/test_rrc_controller.py::test_rrc_go_with_tmux_target_detects_codex_pane workflow_controller/tests/test_rrc_controller.py::test_init_without_tmux_target_inside_tmux_creates_claude_pane workflow_controller/tests/test_rrc_controller.py::test_rrc_go_inside_tmux_auto_creates_claude_pane -q` -> `9 passed in 2.84s`
  - `python -m pytest workflow_controller/tests -q` -> `354 passed in 48.67s`
- 已按用户要求重新打包安装包：`bash packaging/debian/build-deb.sh` -> `dist/waygate_0.5.3_all.deb`。
- 已验证安装包：
  - `dpkg-deb --info dist/waygate_0.5.3_all.deb` -> `Package: waygate`、`Version: 0.5.3`、`Architecture: all`、`Depends: python3`
  - `dpkg-deb --contents dist/waygate_0.5.3_all.deb` -> 包含 `/usr/bin/waygate` 和 `/usr/lib/waygate/workflow_controller/rrc_controller.py`
  - 从 deb 解包后的 `rrc_controller.py` 包含 `_discover_tmux_agent_target`、`_current_tmux_pane_from_environment`、`_has_agent_name_token` 和 `discoverable Codex pane` 错误提示
  - `PYTHONPATH=/tmp/waygate-deb-check/usr/lib/waygate python3 -m workflow_controller.cli --help` -> 正常输出 `usage: waygate ...`

## 会话：2026-05-06

### V1.5 Unit Plan 设计/架构 traceability 误判修复
- **状态：** complete
- 现场 `<target-project>/.rrc-controller-v1.5` 的 Unit Plan 自动打回报错：`unit plan design/architecture traceability is incomplete`，覆盖 `TC-FD-001` 到 `TC-FD-010`。
- 复现确认：Requirements 的 Design/Architecture Traceability Matrix 使用 `` `## 7...` / `PDR-01...` ``、`` `## 8...` / `TAR-01...`、`TAR-02...` `` 这类 Markdown heading ref；Unit Plan JSON `test_cases[]` 已包含等价的 `product_design_refs` / `technical_architecture_refs`，但 validator 以原始字符串精确匹配，导致语义等价引用被误判缺失。
- 已按 TDD 增加回归测试 `test_unit_plan_approval_accepts_markdown_heading_trace_refs_from_requirements`。
- 已验证 RED：`python -m pytest workflow_controller/tests/test_acceptance_obligations.py::test_unit_plan_approval_accepts_markdown_heading_trace_refs_from_requirements -q` -> 失败于 `unit plan design/architecture traceability is incomplete`。
- 修复：trace ref parser 对 `PDR-*`、`TAR-*`、`PD-*`、`TA-*` 稳定 id 做 canonical matching；没有稳定 id 时继续使用规范化全文，避免放宽到任意 prose。
- 已验证 GREEN：
  - `python -m pytest workflow_controller/tests/test_acceptance_obligations.py::test_unit_plan_approval_accepts_markdown_heading_trace_refs_from_requirements -q` -> `1 passed in 0.03s`
  - `python -m pytest workflow_controller/tests/test_acceptance_obligations.py -q` -> `20 passed in 0.06s`
  - 源码 validator 对现场 V1.5 `requirements-and-acceptance.md` + `unit-plan.md` 的 Controller State Patch 验证通过。
- 已验证全量测试：`python -m pytest workflow_controller/tests -q` -> `349 passed in 47.43s`
- 安装副本 `/usr/lib/waygate` 需要 sudo 权限刷新；当前非交互 sudo 失败：`sudo: a password is required`。已新增用户级 wrapper `<user-bin>/waygate`，通过 `PYTHONPATH=<waygate-repo>` 加载修复后的源码；当前 PATH 中它优先于 `/usr/bin/waygate`。
- 使用修复版 `waygate` 对 V1.5 state 运行后，traceability 报错消失，继续暴露 Journey contract id 规范化问题：contract 中 journey id 是 `` `J-01` ``，Unit Plan JSON 映射是 `J-01`。
- 已按 TDD 增加回归测试 `test_unit_plan_approval_accepts_backticked_journey_contract_ids`；RED 先失败于 `unitPlanAccepted is False`。
- 修复：Journey contract 读取、Requirements Journey 抽取和 Unit Plan test case mapping 统一规范化 `J-*` id，并在 enriched contract 中写回去掉反引号的 id。
- 已验证 Journey GREEN：`python -m pytest workflow_controller/tests/test_rrc_controller.py::test_unit_plan_approval_accepts_covers_journeys_mapping workflow_controller/tests/test_rrc_controller.py::test_unit_plan_approval_accepts_journey_refs_mapping workflow_controller/tests/test_rrc_controller.py::test_unit_plan_approval_accepts_backticked_journey_contract_ids -q` -> `3 passed in 0.08s`
- 现场 V1.5 现在进入下一条更具体的 Unit Plan gate 错误：`TC-FD-001`、`TC-FD-006`、`TC-FD-007` 的 command 必须逐条出现在 `verification_commands`；这不是 parser 误判，而是待修订 Unit Plan 质量问题。
- 已验证全量测试：`python -m pytest workflow_controller/tests -q` -> `350 passed in 48.44s`
- 已按用户要求打包安装包：`bash packaging/debian/build-deb.sh` -> `dist/waygate_0.5.3_all.deb`。
- 已验证安装包：
  - `dpkg-deb --info dist/waygate_0.5.3_all.deb` -> `Package: waygate`、`Version: 0.5.3`、`Architecture: all`、`Depends: python3`
  - `dpkg-deb --contents dist/waygate_0.5.3_all.deb` -> 包含 `/usr/bin/waygate` 和 `/usr/lib/waygate/workflow_controller/...`
  - 从 deb 解包后的 `validators/__init__.py` 包含 `_normalize_requirements_trace_ref` / `_requirements_trace_ref_ids`
  - 从 deb 解包后的 `journeys.py` 包含 `_normalize_journey_id`
  - `PYTHONPATH=/tmp/waygate-deb-check/usr/lib/waygate python3 -m workflow_controller.cli --help` -> 正常输出 `usage: waygate ...`

### Requirements 反馈污染 AO Ledger 修复
- **状态：** complete
- 现场 V1.4.1 Requirements 自动打回后阻塞，错误里出现 `AO-001 待人工确认 Requirements...`、`AO-002 请求目标...` 等伪 AO。
- 根因：requirements revision 生成 prompt 需要携带完整 gate 正文，但 controller 同时把这份完整 gate 正文送入 Acceptance Obligation Ledger；ledger 的列表解析器把审批摘要、需求正文、旧草案和 controller 文案里的每个列表项都拆成 active must AO。
- 修复后，Requirements / Unit Plan revision 的 AO 只来自 Plannotator 实际反馈或 annotations；完整 gate 正文仍作为 drafter 修订上下文，但不再进入 AO 拆分。
- Plannotator 纯文本 `# File Feedback` / `## 1. General feedback...` 输出现在会按反馈章节拆成独立 AO。
- Requirements / Unit Plan AO 识别现在兼容 `AO-01` / `AO-1` 这类非三位编号，并规范化为 `AO-001`，降低 agent 输出格式抖动导致的误阻塞。
- Requirements traceability 对 `out_of_scope` / `deferred` / `rejected` 行的 reason 判定已修复：像 `` `sdk/api/handlers` 属于旧 stream 目标。`` 这类包含 `api` 的完整原因不再被误当成单纯 verification layer。
- 现场 `.rrc-controller-v1.4.1` 已完成 live recovery：备份 `session.json.before-ao-clean-20260506T050656Z` 后，将 110 条 `sourceRef=requirements:revision-1` 的污染 AO 标为 `duplicate` 并刷新 AO artifacts；Requirements 已通过。
- 清理 AO 后，污染前提下生成的 Unit Plan 又因 Journey 映射错误被 gate 拦截；已用清理后的 state 触发 Unit Plan revise，修正 Journey 映射并补齐 J-05 test case commands 到 `verification_commands`。当前 state 停在 `WAITING_UNIT_PLAN_APPROVAL`，`requirementsAccepted=true`，`unitPlanAccepted=false`，`blockedReason=null`，等待人工审阅 Unit Plan。
- 当前证据与恢复目录：`<target-project>/.rrc-controller-v1.4.1`。先只读该 state 复现；确认 Requirements 已过但 Unit Plan 被污染 AO 阻塞后，按 live recovery 路径修改了该 controller state。
- 已验证 RED：
  - `python -m pytest workflow_controller/tests/test_acceptance_obligations.py::test_plannotator_plain_file_feedback_becomes_distinct_acceptance_obligations workflow_controller/tests/test_acceptance_obligations.py::test_requirements_approval_accepts_non_padded_ao_ids workflow_controller/tests/test_rrc_human_gates.py::test_revise_requirements_gate_uses_only_plannotator_feedback_for_obligations -q` 先失败于纯文本反馈只生成 1 条 AO、Requirements `AO-01` 不识别、以及 gate 正文被拆成 AO。
  - `python -m pytest workflow_controller/tests/test_acceptance_obligations.py::test_requirements_approval_accepts_out_of_scope_with_blank_ac_and_reason -q` 先失败于 `AO-069` 的 `out_of_scope` 行仍被判定未映射。
- 已验证 GREEN：
  - `python -m pytest workflow_controller/tests/test_acceptance_obligations.py::test_requirements_approval_accepts_out_of_scope_with_blank_ac_and_reason -q` -> `1 passed in 0.05s`
  - `python -m pytest workflow_controller/tests/test_acceptance_obligations.py workflow_controller/tests/test_rrc_human_gates.py -q` -> `60 passed in 17.04s`
  - `python -m pytest workflow_controller/tests/test_acceptance_obligations.py::test_unit_plan_approval_accepts_non_padded_ao_ids workflow_controller/tests/test_acceptance_obligations.py::test_plannotator_plain_file_feedback_becomes_distinct_acceptance_obligations workflow_controller/tests/test_acceptance_obligations.py::test_requirements_approval_accepts_non_padded_ao_ids workflow_controller/tests/test_rrc_human_gates.py::test_revise_requirements_gate_uses_only_plannotator_feedback_for_obligations -q` -> `4 passed in 1.59s`
  - `python -m pytest workflow_controller/tests/test_acceptance_obligations.py workflow_controller/tests/test_rrc_human_gates.py -q` -> `59 passed in 16.51s`
  - `python -m pytest workflow_controller/tests -q` -> `347 passed in 45.63s`

### auto Claude pane 权限模式与 tmux 派发兜底修复
- **状态：** complete
- 现场复现 1：首次运行自动创建 tmux pane 后，dispatch prompt 已粘贴到 Claude/Codex 输入框，但没有被提交，后续只能靠 idle nudge 才驱动起来。
- 现场复现 2：自动启动的 Claude Code 写 `DONE_FILE` 时触发 `Create file .../done.json` 确认，停在 “Do you want to create done.json?”，说明根因是自动创建 pane 使用默认交互权限模式。
- 自动创建 Claude pane 现在默认启动 `claude --permission-mode bypassPermissions`，避免 worker 在写文件或运行命令时停在确认框。
- 支持 `WAYGATE_AUTO_CLAUDE_PERMISSION_MODE` 覆盖权限模式，也支持 `WAYGATE_AUTO_CLAUDE_COMMAND` 覆盖完整启动命令。
- runner 仍在每个 tmux run 目录中预创建同 `RUN_ID` 的 pending `done.json`，作为完成信号文件的兜底，不再把它当作主修复。
- tmux 等待循环会忽略 `status=pending`，只在 `done` / `blocked` / invalid / wrong run 等非 pending 信号时结束。
- tmux 派发后会捕获 pane；如果 dispatch prompt 和 `RUN_ID` 仍停在输入框，自动补发一次提交键。Codex 保留原有事件名与 `agent_not_working_after_submit` 兼容路径；Claude 只在确认 prompt 仍在输入框或 collapsed pasted content 时补交。
- README / USAGE 已补充 auto Claude 权限模式、环境变量覆盖、pending `DONE_FILE` 和派发后补交说明。
- 已验证 RED：
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_init_without_tmux_target_inside_tmux_creates_claude_pane workflow_controller/tests/test_rrc_controller.py::test_rrc_go_inside_tmux_auto_creates_claude_pane -q` 先失败于 auto pane 仍启动裸 `claude`。
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_claude_retries_submit_when_prompt_remains_in_input -q` 先失败于 `result.status == 'timeout'`。
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_runner_precreates_done_file_before_dispatch -q` 先失败于 `result.status == 'failed'`。
- 已验证 GREEN：
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_init_without_tmux_target_inside_tmux_creates_claude_pane workflow_controller/tests/test_rrc_controller.py::test_auto_created_claude_pane_permission_mode_can_be_overridden workflow_controller/tests/test_rrc_controller.py::test_auto_created_claude_pane_command_can_be_overridden workflow_controller/tests/test_rrc_controller.py::test_init_without_workspace_uses_current_directory_for_auto_claude_pane workflow_controller/tests/test_rrc_controller.py::test_rrc_go_inside_tmux_auto_creates_claude_pane -q` -> `5 passed in 1.01s`
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_runner_precreates_done_file_before_dispatch workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_claude_retries_submit_when_prompt_remains_in_input workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_claude_runner_fails_fast_when_pane_returns_idle_after_dispatch -q` -> `3 passed in 1.98s`
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `31 passed in 12.65s`
  - `python -m pytest workflow_controller/tests/test_rrc_real_runtime.py -q` -> `18 passed in 3.71s`
  - `python -m pytest workflow_controller/tests -q` -> `343 passed in 47.44s`

### V0.5.3 Waygate 安装化与现场降噪
- **状态：** complete
- 对外项目名、deb 包名和安装后命令统一为 Waygate / `waygate`；内部 Python package 仍保留 `workflow_controller`，避免大规模 import 重命名。
- 新增 Debian 包构建脚本 `packaging/debian/build-deb.sh`，默认输出 `dist/waygate_0.5.3_all.deb`。
- deb 包安装 `/usr/bin/waygate` wrapper，通过 `python3 -m workflow_controller.cli` 调用内部 CLI，并安装 README / USAGE / ROADMAP 到 `/usr/share/doc/waygate/`。
- CLI help 和面向用户的 README / USAGE 示例已切换到 `waygate`；源码调试仍兼容 `python -m workflow_controller.cli ...`。
- compact reporter 现在按最终渲染状态卡去重，避免 Plannotator approve 后因未渲染字段变化重复打印相同 `检查 Unit Plan 确认` 状态卡。
- 相对 artifact 目录 runner 测试改为在 `tmp_path` 下运行，避免生成 repo root `relative-artifacts/` 测试产物。
- 已验证 RED：
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_compact_reporter_dedupes_identical_rendered_status_cards -q` 先失败于重复输出相同状态卡。
  - `python -m pytest workflow_controller/tests/test_packaging.py::test_build_deb_creates_waygate_package -q` 先失败于缺少 `packaging/debian/build-deb.sh`。
- 已验证 GREEN：
  - `python -m pytest workflow_controller/tests/test_packaging.py -q` -> `1 passed in 0.38s`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_compact_reporter_dedupes_identical_rendered_status_cards -q` -> `1 passed in 0.43s`
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_runner_dispatch_prompt_uses_absolute_paths_for_relative_artifact_dir -q && test ! -e relative-artifacts` -> `1 passed in 0.68s`
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `29 passed in 9.64s`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `140 passed in 9.53s`
  - `python -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `40 passed in 13.83s`
  - `python -m pytest workflow_controller/tests/gates/test_gates_structure.py -q` -> `18 passed in 0.04s`
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.5.3_all.deb`
  - `dpkg-deb --info dist/waygate_0.5.3_all.deb` -> `Package: waygate`, `Version: 0.5.3`, `Depends: python3`
  - `dpkg-deb --contents dist/waygate_0.5.3_all.deb` -> 包含 `/usr/bin/waygate`、`workflow_controller/cli.py`、README / USAGE / ROADMAP docs
  - `python -m workflow_controller.cli --help` -> `usage: waygate ...`
  - `python -m pytest workflow_controller/tests -q` -> `339 passed in 40.64s`

### Unit Plan Journey 映射字段兼容修复
- **状态：** complete
- Unit Plan Journey gate validator 现在识别 `journey_refs` 和 `journeyRefs`，同时保留 `journey_id`、`journey_ids`、`covers_journeys` 等既有字段。
- Verifier Journey evidence 生成路径同步识别 `journey_refs` 和 `journeyRefs`，避免 gate 通过后 `journey-evidence.json` 漏写对应 row。
- Unit Plan prompt 已明确推荐 `covers_journeys` / `journey_ids`，并说明 `journey_refs` / `journeyRefs` 只是兼容别名；closure/E2E test case 必须在 `test_cases[]` JSON 中显式写 Journey 映射。
- README 已补充 Unit Plan Gate 的 Test Case Matrix / Controller State Patch 示例和 Journey 映射字段说明。
- 已验证 RED：
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_unit_plan_approval_accepts_journey_refs_mapping -q` 先失败于 `unitPlanAccepted is False`。
  - `python -m pytest workflow_controller/tests/test_rrc_verifier.py::test_run_verifier_derives_journey_evidence_from_journey_refs -q` 先失败于缺少 `journey_evidence_rows`。
- 已验证 GREEN：
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_unit_plan_approval_accepts_journey_refs_mapping -q` -> `1 passed in 0.07s`
  - `python -m pytest workflow_controller/tests/test_rrc_verifier.py::test_run_verifier_derives_journey_evidence_from_journey_refs -q` -> `1 passed in 0.03s`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `139 passed in 10.26s`
  - `python -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `40 passed in 14.33s`
  - `python -m pytest workflow_controller/tests/test_rrc_verifier.py -q` -> `6 passed in 0.05s`
  - `python -m pytest workflow_controller/tests/gates/test_gates_structure.py -q` -> `18 passed in 0.07s`
  - `python -m pytest workflow_controller/tests -q` -> `337 passed in 41.24s`

### Unit Plan 自动打回默认次数调整
- **状态：** complete
- Unit Plan controller 预检失败后的默认自动打回预算从 2 次提高到 5 次。
- `unitPlanAutoRevisionMax` 显式覆盖机制不变；已有 state 设置该字段时仍优先生效。
- README 已补充 Unit Plan 预检失败默认最多自动打回 5 次说明。
- 已验证 RED：`python -m pytest workflow_controller/tests/test_rrc_controller.py::test_default_unit_plan_auto_revision_budget_is_five -q` 先失败于 `2 == 5`。
- 已验证 GREEN：
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_default_unit_plan_auto_revision_budget_is_five -q` -> `1 passed in 0.10s`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `138 passed in 9.78s`
  - `python -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `40 passed in 14.47s`
  - `python -m pytest workflow_controller/tests/gates/test_gates_structure.py -q` -> `18 passed in 0.06s`
  - `python -m pytest workflow_controller/tests -q` -> `335 passed in 40.40s`

## 会话：2026-05-05

### V0.5.2 现场 tmux-codex 派发竞态与关键信息着色修复
- **状态：** complete
- 现场 7 号窗口的“回车发不出去”不是 Ctrl 键卡住；证据显示 Codex 写出 `done.json` 后仍在 `Working`，controller 已读到 `DONE_FILE` 并立即把下一轮 prompt 粘进了 Codex 的排队输入框。
- `tmux-codex` runner 现在在 `DONE_FILE status=done` 后捕获目标 pane，确认其离开 `Working` 状态后才返回完成，避免 controller 提前派发下一轮。
- runner events 新增 `tmux_agent_busy_after_done` 和 `tmux_agent_idle_after_done`，用于诊断 DONE_FILE 与 TUI 工作态不同步的问题。
- compact 输出在有色模式下会突出 `[修订]` / `[阻塞]`、自动打回动作，以及 AO/AC/Test Case/Journey/unit 等定位符；默认 `--color auto` 保持不变。
- README 已补充 tmux-codex post-done 等待和关键信息着色说明。
- 已验证定向测试：
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `29 passed in 9.96s`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_drive_color_auto_keeps_captured_output_plain workflow_controller/tests/test_rrc_controller.py::test_drive_color_always_adds_ansi_to_compact_output workflow_controller/tests/test_rrc_controller.py::test_drive_auto_revises_invalid_unit_plan_with_short_precheck_status workflow_controller/tests/test_rrc_controller.py::test_colored_auto_revision_message_highlights_gate_and_ids -q` -> `4 passed in 0.69s`
- 已验证回归测试：
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `137 passed in 9.72s`
  - `python -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `40 passed in 12.57s`
  - `python -m pytest workflow_controller/tests/gates/test_gates_structure.py -q` -> `18 passed in 0.06s`
  - `python -m pytest workflow_controller/tests -q` -> `334 passed in 38.87s`

### V0.5.2 审批摘要优先 + Unit Plan 进度输出修复
- **状态：** complete
- Requirements / Unit Plan approval Markdown 现在顶部先展示 `## 审批摘要`，结论、变更点、需要人确认的点、验收命令和 Controller/Critic 检查摘要都在摘要区。
- Requirements 详细正文、AO/AC traceability、Design/Architecture traceability、Journey Acceptance Matrix、Unit Plan 目标覆盖、Test Case Matrix、执行单元和 `## Controller State Patch` 均保留在同一个审批 Markdown 的附录区。
- `## Human Confirmation` 仍只由 controller 追加；agent 生成内容不会生成确认段落。
- Plannotator 审阅路径回到 approval Markdown 本身，summary 记录 `review_path`、`approval_gate_path`、`summary_path` 和 `full_path`。
- Unit Plan 进入人工确认前会先运行 controller 预检；失败时自动打回 drafter，终端只输出短原因，完整原因写入 state 和 `artifacts/unit-plan-draft/controller-validation-error.json`。
- compact drive 输出恢复 Unit Plan 阶段状态卡：生成草案、预检草案、自动打回草案、等待确认；controller-only revise 和人工/Plannotator revise 也输出短状态。
- README 已同步 V0.5.2：说明 approval Markdown 摘要优先结构、Plannotator 审阅 approval Markdown、Unit Plan 人工审核前预检打回，以及 `controller-validation-error.json` artifact。
- 已验证定向测试：
  - `python -m pytest workflow_controller/tests/gates/test_gates_structure.py -q` -> `18 passed in 0.08s`
  - `python -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `40 passed in 13.61s`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `136 passed in 10.82s`
  - `python -m pytest workflow_controller/tests/test_rrc_real_runtime.py -q` -> `18 passed in 3.91s`
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `28 passed in 9.82s`
- 已验证全量测试：`python -m pytest workflow_controller/tests -q` -> `332 passed in 43.67s`

### Agent-side Requirements Clarification
- **状态：** complete
- Requirements Draft prompt 已明确：信息足够时直接生成 gate；只有关键缺口会导致方向错误时，目标 Claude/Codex agent 才在自己的 tmux pane 中集中提问。
- Requirements Draft 后新增 controller 预检自动返工：缺 Journey、缺 verification layer、缺 AO/AC 映射等可判定问题不会先进入人工审核。
- Requirements Gate 模板新增 `## 4.8 已澄清事项、关键假设与待确认风险`，要求把 agent-side 问答形成的决策和保守假设落到 gate 正文。
- tmux dispatch 文案已说明：agent 提问期间不写 DONE_FILE，回答后继续；只有任务完成或真正阻断时才写 DONE_FILE。
- ROADMAP / README / USAGE / task_plan 已同步：V0.4.1 是 agent-side clarification + gate revision；V0.4.5a brief 是上下文压缩，不是提问机制。

### V0.4.1–V0.4.5a 控制平面收敛
- **状态：** complete
- 已确认当前未提交实现覆盖 V0.4.1 Requirements Negotiation Loop、V0.4.2 Change Request Ledger、V0.4.3 Independent Bug Fix Gate、V0.4.4 Journey Acceptance Layer、V0.4.5 Final Scope Audit 和 V0.4.5a Requirements Dialogue Brief。
- `ROADMAP.md` 已同步：V0.4.1–V0.4.5a 标记为已完成，V0.4.6 保持为下一步。
- `task_plan.md` 已追加阶段 30–36，明确 V0.4.1–V0.4.5a 完成项和 V0.4.6 剩余项。
- 已确认 `.rrc-controller-*` 是本地 controller state 产物，本轮不纳入提交。
- 已验证全量测试：`python -m pytest workflow_controller/tests -q` -> `303 passed in 31.97s`

## 会话：2026-05-04

### README 项目能力说明
- **状态：** complete
- 新增 `README.md`，以中文专业说明项目定位、当前能力、核心设计原则、工作流、CLI、artifact 结构、架构、runner 角色、验证方式、能力边界和安全审计规则。
- README 已补充交互流程图、状态流转图，以及 Requirements Gate、Unit Plan Gate、Final Acceptance Gate 三类人工审核文档示例。
- README 已补充每一步 Prompt 的 artifact、模板/生成逻辑、输入事实源、期望输出和人工审核归属。
- README 已明确产品设计图和技术架构的主审核位置是 Requirements Gate；Unit Plan 继承设计/架构引用，Final Acceptance 通过 evidence matrix 反向审计覆盖。
- README 已补充功能测试与 E2E 测试要求，明确 Requirements / Unit Plan / Builder / Verifier / Final Acceptance 各阶段如何要求测试，以及当前仍需补齐的 strict test presence 风险。
- ROADMAP 已将 V0.4.6 更新为 `Strict Test Presence + Requirements Test Strategist`，目标是补齐“非 manual AC 没有可执行 test case 也可能通过”的风险。
- 已修正 Test Case Matrix AO 覆盖解析：带产品设计/技术架构列的矩阵必须从真实 `Command/Evidence` 和 `Expected Result` 列读取测试证据，避免把设计引用误算成测试。
- 已修正 `go` 默认路径推断：显式传 `--workspace-dir` 时，默认 `state-dir` 会落到目标项目目录下；README/USAGE 已同步说明。
- README 已将三类人工审核文档从片段示例升级为完整结构展示，包含 `Human Confirmation`、`Content hash`、Requirements 全章节、Unit Plan state patch、Final Acceptance 返工路由。
- README 明确区分已实现能力与 ROADMAP 规划能力，避免把 Journey Acceptance、workspace isolation、file/tool policy、clean verification、结构化契约文件误写成当前已完成。
- 已验证全量测试：`python -m pytest workflow_controller/tests -q` -> `303 passed in 33.18s`

### V0.4.0 Project Agent Operating Guide
- **状态：** complete
- `init` 现在默认在工作区生成中文 `AGENTS.md` 和标准 docs 目录：`docs/product`、`docs/architecture`、`docs/workflow`、`docs/operations`。
- 新增 `--claude-md`，可生成只指向 canonical `AGENTS.md` 的中文 `CLAUDE.md` shim。
- `AGENTS.md` 已加入中文工程行为准则：先澄清、简洁实现、精准修改、避免无关重构、以证据验证 bugfix。
- 新增 `--no-agent-guides`，允许显式跳过 agent guide 和 docs layout 生成。
- 已存在 `AGENTS.md` / `CLAUDE.md` 时不会覆盖原文件，会写入 `AGENTS.md.generated` / `CLAUDE.md.generated` 作为 merge 草稿。
- 生成结果写入 `session.json` 的 `agentGuideArtifacts`，记录 workspace、文件状态和 docs 目录。
- `start` 在创建新 state 或 `--force` 重建 state 时也复用同一配置。
- 已按 TDD 验证 RED：新增测试先失败于缺少 `AGENTS.md` 与 `--claude-md` 参数。
- 已补充边界回归：`--no-agent-guides` 跳过生成，`start` 创建新 state 时同样生成 guide。
- 已验证定向测试：`python -m pytest workflow_controller/tests/test_rrc_controller.py::test_init_creates_agent_operating_guide_and_docs_layout workflow_controller/tests/test_rrc_controller.py::test_init_can_generate_claude_md_and_does_not_overwrite_existing_guides -q` -> `2 passed in 0.19s`
- 已验证 controller 回归：`python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `94 passed in 5.08s`
- 已验证全量测试：`python -m pytest workflow_controller/tests -q` -> `272 passed in 30.72s`
- code-simplifier refinement pass 完成：未发现需要额外行为保持清理的改动。

### V0.4+ 版本路线图整合
- **状态：** complete
- 已将后续控制框架补齐项整合进 `ROADMAP.md`。
- `ROADMAP.md` 已新增 `V0.4+ Priority Backlog` 表格，保留优先级、版本号、主题、要做什么和排序理由。
- V0.4 现在包含：项目初始化规约、`AGENTS.md` / `CLAUDE.md`、文档目录事实源表、需求协商、`change_requests.jsonl`、独立 Bug Fix Gate、Journey Acceptance Layer、Final Scope Audit 和 Requirements-stage Test Strategist。
- Journey Acceptance Layer 已调整为 V0.4.4，用于补齐当前只有 unit task acceptance / golden path、没有一等 Journey 验收模型的问题；Final Scope Audit 顺延为 V0.4.5，因为它需要审计 Journey 覆盖。
- V0.5 现在聚焦 Execution Plane：per-role runner、opencode runner、task workspace/branch isolation、file/tool policy、clean verification。
- V0.6 现在聚焦恢复与可观测性：checkpoint/time-travel、unified trace、evidence 类型扩展、failure taxonomy、automatic context repair。
- V0.7 现在聚焦结构化契约和权威验收：`requirements.json`、`acceptance.json`、`tasks.json`、`journeys.json`、CI integration 和 lifecycle hooks。
- 本节是路线图整合记录；V0.4.0 后续实现记录见本会话上方条目。

### V0.3.6 Final Acceptance Evidence Matrix
- **状态：** complete
- Final Acceptance gate 现在基于 `verification.json.evidence_rows` 渲染 `## 验收证据矩阵（Final Acceptance Evidence Matrix）`。
- 矩阵包含 AO、AC、Test Case、Layer、Status、Evidence、Expected、Artifacts 和 Golden Path。
- 旧 verification artifact 没有 `evidence_rows` 时仍保留原证据摘要，并在矩阵中显示 missing schema row。
- 最终验收 patch list 返工路径会附带 evidence matrix context，避免 Builder/defect-fix unit 丢失 AO/AC/Test Case/Evidence 定位。
- V0.3.6 不新增路由；仍复用 requirements、unit_plan、defect_fix、implementation、blocked。
- 已验证定向测试：`python -m pytest workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/gates/test_gates_structure.py -q` -> `147 passed in 14.76s`
- 已验证全量测试：`python -m pytest workflow_controller/tests -q` -> `268 passed in 30.15s`

### V0.3.5 Verifier Evidence Schema
- **状态：** complete
- `verification.json` 现在保留既有 verdict 字段，同时新增 `evidence_schema_version=v0.3.5` 和 `evidence_rows`。
- Evidence rows 记录 unit、test case、AC、AO、verification layer、command/manual evidence、expected、status、result index、returncode、artifact refs 和 golden path。
- 自动化命令结果会映射为 `passed` / `failed` / `missing`；无命令的人工证据会映射为 `manual`。
- Controller 在 verifier 通过后校验 evidence schema；schema 缺失或 malformed 时按验证失败进入既有返工/重复失败保护，不进入 `UNIT_COMPLETE`。
- V0.3.5 本身不改变 Final Acceptance gate 渲染；V0.3.6 已消费 `evidence_rows` 渲染最终验收矩阵。
- 已验证定向测试：`python -m pytest workflow_controller/tests/test_rrc_verifier.py workflow_controller/tests/test_rrc_real_runtime.py workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/gates/test_gates_structure.py -q` -> `169 passed in 17.97s`
- 已验证全量测试：`python -m pytest workflow_controller/tests -q` -> `267 passed in 29.94s`

## 会话：2026-05-03

### V0.3.4 Product Design / Technical Architecture Traceability
- **状态：** complete
- V0.3.4 范围明确为 Requirements + Unit Plan 的设计/架构可追溯链路，不包含 Verifier evidence schema 或 Final Acceptance evidence matrix。
- Requirements draft prompt 和本地 gate template 新增 `Design/Architecture Traceability Matrix`。
- Requirements approval 在矩阵存在时要求每条 AC 同时具备 Product Design Ref 和 Technical Architecture Ref；旧 requirements 无该矩阵时保持兼容。
- Unit Plan prompt 和 Test Case Matrix template 新增产品设计引用、技术架构引用字段。
- Unit Plan approval 会校验 test case 是否保留 requirements 中对应 AC 的设计/架构引用。
- 已验证定向测试：`python -m pytest workflow_controller/tests/test_acceptance_obligations.py workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/gates/test_gates_structure.py workflow_controller/tests/test_rrc_controller.py -q` -> `159 passed in 15.06s`
- 已验证全量测试：`python -m pytest workflow_controller/tests -q` -> `264 passed in 31.38s`

### V0.3.3 Requirements Quality Gate 完成
- **状态：** complete
- Requirements approval 现在会在写入 accepted 前执行质量预检。
- 每个 active `must` AO 必须在 Requirements Traceability Matrix 或等价结构中映射到 AC，或显式标记为 `deferred` / `rejected` / `out_of_scope` 并写明原因。
- 每条 AC 必须声明 verification layer；支持 `unit`、`functional`、`integration`、`e2e`、`manual`，并兼容既有 `API` 语义。
- `approve_human_gate('requirements')` 和已预批准 gate 的 `check_requirements_acceptance` 都会阻断无效 requirements，不会进入 Unit Plan。
- requirements gate invalid 会写入 `blockedReason`，并在 requirements revision prompt 中追加 `Controller Validation Error`。
- Requirements draft prompt 和本地 gate template 已新增 `## 4. 需求可追溯矩阵（Requirements Traceability Matrix）`。
- 已验证：`python -m pytest workflow_controller/tests -q` -> `259 passed in 30.51s`

### V0.3.2 CodeSimplifier 集成完成
- **状态：** complete
- 已将 Builder 后的本地 Refiner 占位升级为默认开启的 CodeSimplifier/Refiner role runner。
- 新增 CLI 配置：`--no-code-simplifier`、`--code-simplifier`、`--code-simplifier-command`、`--code-simplifier-env KEY=VALUE`，支持 `init` 和 `start`。
- 新增状态字段 `codeSimplifierEnabled=true`，旧 session reconcile 时默认补齐为开启。
- Refiner 现在总是写入 `simplifier-result.json`，并继续写 `refinement-summary.json` 作为 reviewer 兼容 artifact。
- disabled 模式写 `status=skipped` 并进入 Reviewer；enabled 模式渲染 `code-simplifier-prompt.md` 并调用 `role='refiner'` runner。
- CodeSimplifier runner 输出缺失、状态非法或 schema 明显错误时会落为 `status=failed`，不会静默进入 Reviewer。
- `changes_requested` 会通过既有重复失败 guard 回到 Builder，并把 CodeSimplifier findings 注入下一轮 Builder prompt。
- `failed` 会停留在 Refiner 重试/阻断路径，不进入 Reviewer。
- runner metadata 只记录 env key；stdout/stderr 中配置的 env value 会被 redacted。
- 已验证：`python -m pytest workflow_controller/tests -q` -> `252 passed in 30.76s`

### V0.3.1 Acceptance Obligation Ledger 完成
- **状态：** complete
- 已新增 AO Ledger：人工反馈、Plannotator annotations、Requirements/Unit Plan 返工和 Final Acceptance rejection 会进入 `acceptanceObligations`。
- 已写入 AO artifacts：`artifacts/acceptance-obligations/acceptance-obligations.json` 和 `acceptance-obligations.md`。
- Requirements / Unit Plan prompt 会注入 AO Ledger，并要求每条 must AO 进入 AC、测试用例或人工证据映射。
- Unit Plan approval 会阻断缺失 active must AO 覆盖的计划，并列出缺失 AO id 与标题；已修复审查发现的 approved gate bypass。
- AO coverage 只计算结构化 `test_cases[].covers_obligations` 或 Test Case Matrix 中有 test case、layer、command/evidence、expected 的映射，不再把复制的 ledger/prose AO id 视为覆盖。
- Plannotator structured annotations 会传入 AO 创建逻辑，避免多条浏览器批注被压成一条 AO。
- 已修复 E2E fixture：closure unit 必须包含 `golden_path` test case。
- 已验证：`python -m pytest workflow_controller/tests -q` -> `240 passed in 32.12s`

### V0.3.1 Acceptance Obligation Ledger 启动
- **状态：** complete
- 目标：完成 V0.3.1 最小可交付功能，让人工反馈、验收失败和关键需求问题进入结构化 AO Ledger，后续 Unit Plan 和 Verifier 必须逐条覆盖。
- Phase 0：复用现有 planning-with-files 文件，并在 `task_plan.md` 追加阶段 22。
- Phase 1：已按已讨论的 V0.3.1 方向完成设计，不再拆 MVP 选项。
- 视觉辅助：跳过，本任务不是 UI/视觉设计任务。

## 会话：2026-05-01

### V0.2 版本规划确认
- **状态：** complete
- 背景：
  - requirements-drafting agent 将 V0.2 的"背景"写成"V0.1 完成了 Test Strategist 接入"，被 Plannotator 标注为全错。
  - 根因：工作区内没有版本规划文档，agent 只能从 progress.md 最近记录推断，推断错误。
  - `composed-sleeping-dolphin.md`（OpenMAIC 课程管理计划）误被放入 targetContextFiles，对 V0.2 规划无帮助。
- 已确认版本路线图（用户确认版）：
  - **V0.1**：Test Strategist 接入（已完成，144 passed）
  - **V0.2**：全面重构（架构分层：state_machine/、gates/、runners/、prompts/、steps/、controller.py、cli.py）
  - **V0.3**：需求质量 + 证据标准化
  - **V0.4**：需求协商 + Bug Fix 环节（新 bug-fix gate，替代原 defect_fix → Unit Plan 路径）
  - **V0.5**：Agent 灵活性（opencode runner、per-role 配置）
- 已完成：
  - 创建 `ROADMAP.md`，记录确认版版本路线图
  - 更新 `task_plan.md` 的当前阶段描述
  - 更新 `findings.md` 记录 V0.2 真实范围
- 影响：
  - V0.2 的真实范围是**全面架构重构**，不是 idle 逻辑修复（那只是当前已完成的增量改动，应归入已提交变更）
  - requirements-body.md 的描述需要以架构重构为主线重写（等待 controller 下一轮 requirements revision）

## 会话：2026-04-29

### 阶段 9：Plannotator 与人工 Gate 集成
- **状态：** complete
- 背景：
  - 用户使用 Plannotator 审阅需求和 Unit Plan 时，期望浏览器 `Approve` 后 controller 自动继续。
  - 之前 controller 让 Plannotator 审阅的文件与 Claude 写入的 body artifact 不一致。
  - 用户需要启动 Plannotator 时直接看到打开网址。
- 已完成：
  - Plannotator `Approve` 输出 `decision=approved` 后，controller 自动调用对应 gate approval 并继续。
  - Plannotator `Close` 输出 `decision=dismissed` 后，controller 保持 gate pending。
  - 需求审阅文件改为 `artifacts/requirements-draft/requirements-body.md`。
  - Unit Plan 审阅文件改为 `artifacts/unit-plan-draft/unit-plan-body.md`。
  - `approvals/requirements-and-acceptance.md` 和 `approvals/unit-plan.md` 继续作为确认文件。
  - 启动 Plannotator 时输出 `打开网址：http://localhost:20000`。

### 阶段 10：Unit Plan Gate 校验与反馈闭环
- **状态：** complete
- 背景：
  - 用户按 `a` 后 Unit Plan 可能仍然 gate invalid，但旧流程会留下令人误解的确认状态。
  - Plannotator 多条反馈在终端短预览中看起来像只收到第一条。
- 已完成：
  - `approve_human_gate('unit-plan')` 先校验 Unit Plan，再写 approval。
  - 无效 Unit Plan 保持 pending，并在菜单中显示 `unit plan gate invalid: ...`。
  - Unit Plan 返工 prompt 包含 `Controller Validation Error`。
  - Plannotator 反馈显示 `共 N 条，完整反馈已写入 Claude 返工 prompt。`，并保留预览。
  - Plannotator 返回 `annotations` 数组时保留结构化信息。
- 已验证：
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py -q` -> `65 passed in 17.62s`
  - 实际运行目录单测：Plannotator feedback 回显用例通过。

### 阶段 11：Unit Plan Rollup 与历史单元兼容
- **状态：** complete
- 背景：
  - V2.2 当前只剩 `v2-2-u5-baidu-search` 需要执行。
  - Unit Plan 的 rollup objective `Complete V2.2...` 合理引用 `v2-2-u1` 到 `u5`，但旧校验要求 partial objective 的每个 unit 都必须出现在 `units`。
- 已完成：
  - 已完成历史单元可以出现在 `partial` 聚合目标里。
  - 未完成且未声明在 `units` 中的 unit 仍然被阻断。
  - Unit Plan drafter prompt 更新，说明 completed existing unit 可用于 rollup objective。
- 已验证：
  - 新增正向用例：partial rollup 可引用 completed existing units。
  - 新增反向用例：undeclared unfinished unit 仍然阻断。
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py -q` -> `67 passed in 17.44s`
  - 实际运行目录新增用例 -> `2 passed in 1.16s`

### 阶段 12：Unit Plan 确认后执行推进修复
- **状态：** complete
- 背景：
  - 用户在 V2.2 Unit Plan 菜单按 `a` 后，controller 输出 `[停止] 当前没有可执行的下一步。`
  - 现场 `session.json` 状态为 `currentStep=PLAN_CREATED`、`scopeApproved=True`、`unitPlanAccepted=True`、`lastVerifiedStep=VERIFY_UNIT`。
- 根因：
  - 状态机只处理 `PLAN_CREATED + scopeApproved=false -> require_scope_approval`。
  - `PLAN_CREATED + scopeApproved=true` 没有动作，导致 `compute_next_allowed_action()` 返回 `None`。
  - 新 Unit Plan 生效时没有重置上一单元留下的 `lastVerifiedStep=VERIFY_UNIT`。
- 已完成：
  - Unit Plan 确认后若 `scopeApproved=True`，直接进入 `PLAN_APPROVED`。
  - 新 Unit Plan 生效后将 `lastVerifiedStep` 重置为 `PLAN_CREATED`。
  - `reconcile_state()` 会自动把已落盘的 `PLAN_CREATED + scopeApproved=True + unitPlanAccepted=True` 修复为 `PLAN_APPROVED`。
  - 已同步 `rrc_controller.py`、`rrc_validators.py` 和相关测试到实际运行目录。
- 已验证：
  - 新增用例：preapproved scope 的 Unit Plan approval 直接进入 builder-ready state。
  - 新增用例：已落盘卡住状态在 `get_status()` 中自动修复。
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py -q` -> `69 passed in 17.65s`
  - 实际运行目录新增用例 -> `2 passed in 1.19s`
  - 当前 V2.2 state 检查结果：
    - `currentStep=PLAN_APPROVED`
    - `nextAction=run_builder`
    - `currentUnitId=v2-2-u5-baidu-search`
    - `lastVerifiedStep=PLAN_CREATED`

### 阶段 13：Final Acceptance Defect Fix 流程
- **状态：** complete
- 背景：
  - 最终验收可能发现历史已完成单元的缺陷，例如 i18n、logo、主页、工作台没有真正改到位。
  - 当前 Builder 只允许执行当前 unit，不能越界修历史 covered unit。
  - 走需求变更太重，因为原需求可能是对的，只是实现没满足。
- 已完成：
  - 新增最终验收拒绝路由 `defect_fix`。
  - 最终验收 gate 的 Rejection Routing 增加 `Defect fix` 选项。
  - 终端路由菜单增加 `1  验收缺陷修复 -> Defect Fix`。
  - `defect_fix` 会保持 requirements accepted，不走 requirements draft。
  - `defect_fix` 会进入 Unit Plan revision，并设置 `unitPlanRevisionMode=defect_fix`。
  - Unit Plan drafter prompt 增加 `Final Acceptance Defect-Fix Mode`，要求生成 bug-fix units、不改变已批准需求、不重新解释目标。
  - Controller State Patch 支持已 covered objective 通过新增 bug-fix unit reopen 为 `partial`。
  - Builder prompt 对 defect-fix unit 携带最终验收缺陷清单，避免 Builder 缺少原始验收上下文。
  - 已同步 `rrc_controller.py`、`rrc_human_gates.py`、`rrc_steps.py` 和相关测试到实际运行目录。
- 已验证：
  - 新增用例：final acceptance `Defect fix` route 进入 Unit Plan revision。
  - 新增用例：Unit Plan defect-fix prompt 要求 bug-fix units 且不改需求。
  - 新增用例：Builder prompt 包含最终验收缺陷清单。
  - 新增用例：covered objective 可通过 defect-fix unit reopen 为 partial。
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py -q` -> `73 passed in 17.44s`
  - `python -m pytest workflow_controller/tests -q` -> `110 passed in 38.52s`
  - 实际运行目录新增关键用例 -> `4 passed in 1.27s`

### 阶段 14：Unit Plan 测试用例矩阵与测试策略预检
- **状态：** complete
- 背景：
  - 当前 controller 只能验证命令是否通过，不能判断测试用例是否覆盖验收标准。
  - 用户指出测试用例方面非常欠缺，尤其会出现“验证全绿但人工验收发现大量核心场景没测”的问题。
- 已完成：
  - Unit Plan drafter prompt 增加 `Use the test-strategy skill...`。
  - Unit Plan required structure 增加 `## Test Case Matrix`。
  - Test Case Matrix 明确映射：`Acceptance Criterion -> Test Case -> Layer -> Command/Evidence -> Expected Result`。
  - Controller State Patch unit 增加 `test_cases` 示例字段。
  - Unit Plan local template 会渲染 test case matrix 和每个 unit 的 test cases。
  - Unit Plan approval 新增 `validate_unit_plan_test_case_coverage()`。
  - 只有 `tsc`/lint/typecheck 等静态检查、且没有 `test_cases` 或 Test Case Matrix evidence 的 unit 会被拒绝。
  - Builder prompt 要求先补 mapped test cases；defect-fix unit 要补回归测试或人工证据。
  - `rrc_models.py` 增加 `UNIT_PLANNER` role hint：`test-strategy + writing-plans`。
  - 已同步 `rrc_controller.py`、`rrc_human_gates.py`、`rrc_steps.py`、`rrc_models.py` 和相关测试到实际运行目录。
- 已验证：
  - 新增用例：Unit Plan prompt 要求 `test-strategy` 和 Test Case Matrix。
  - 新增用例：只有静态检查的 Unit Plan 被 approval 阻断。
  - 新增用例：有明确 Test Case Matrix/manual evidence 的计划可通过。
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py -q` -> `76 passed in 17.64s`
  - `python -m pytest workflow_controller/tests -q` -> `113 passed in 38.17s`
  - 实际运行目录新增关键用例 -> `3 passed in 1.20s`

### 当前未提交变更
- **状态：** pending
- `workflow_controller/rrc_controller.py`
- `workflow_controller/rrc_human_gates.py`
- `workflow_controller/rrc_models.py`
- `workflow_controller/rrc_steps.py`
- `workflow_controller/tests/test_rrc_controller.py`
- `workflow_controller/tests/test_rrc_human_gates.py`
- `task_plan.md`
- `findings.md`
- `progress.md`

### 阶段 17：旧 Final Acceptance Gate 路由迁移修复
- **状态：** complete
- 背景：
  - 用户在 Plannotator 最终验收反馈后选择 `1  验收缺陷修复 -> Defect Fix`。
  - controller 已回显 `[验收路由] 已选择：Defect fix`，但随后报错：`Final acceptance rejection routing must select one option...`。
- 根因：
  - 现场 `approvals/final-acceptance.md` 是旧格式，`Rejection Routing` 中没有 `Defect fix` 行。
  - 旧 `_write_final_acceptance_rejection_route()` 只会勾选已存在的 checklist 行，缺失 route 时不会补齐，也不会校验写入是否成功。
  - 终端选择 route 会重写 gate，mtime 晚于 Plannotator summary；如果继续按 stale 处理，会丢失本轮浏览器批注。
- 已完成：
  - `ensure_final_acceptance_gate()` 会规范化旧 Rejection Routing checklist，自动补齐 `Defect fix`。
  - 终端 route 写入改为重写 canonical checklist，并设置唯一选中项。
  - `reject_final_acceptance_gate()` 从 gate 文件读取路由，返工 prompt 仍使用 gate + Plannotator feedback 的完整组合内容。
  - final acceptance route 写入导致 gate mtime 变新时，仍读取本轮 Plannotator feedback。
  - 已同步 `rrc_controller.py`、`rrc_human_gates.py` 和 `tests/test_rrc_controller.py` 到实际运行目录。
- 已验证：
  - 新增红绿用例：旧 final acceptance gate 缺少 `Defect fix` 行时，选择 `1` 后进入 defect-fix，并保留 Plannotator 反馈。
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py -q` -> `77 passed in 17.46s`
  - `python -m pytest workflow_controller/tests -q` -> `114 passed in 38.31s`
  - 实际运行目录关键用例 -> `2 passed in 1.25s`

### 阶段 18：Defect Fix Unit Plan Prompt 显性化回滚
- **状态：** complete
- 背景：
  - 用户指出：既然实际 prompt 已经包含 Plannotator 反馈，就不需要额外改 prompt 结构。
- 已完成：
  - 回滚 defect-fix 模式下的专用 `Final Acceptance Defects From Plannotator/Human Review` 区块。
  - 保留原本已存在的数据流：`unitPlanRevisionFeedback` 仍进入 `Existing Unit Plan draft with human notes and requested changes` 区块。
  - 删除对应的显性化测试断言。
  - 保留旧 gate 缺 `Defect fix` 行的路由迁移修复。

### 阶段 19：非 Ralph 新目标初始化修复
- **状态：** complete
- 背景：
  - 用户执行 `init --workspace-dir <target-project> --target "V3.0"`，随后 `start --target "V3.0"` 报 existing session mismatch。
  - 现场 `session.json` 为 demo state：`requestedOutcome=usable-system`、`currentUnitId=unit-01`。
- 根因：
  - `init_state()` 只有 `from_ralph=True` 时才使用 target/workspace 构建真实目标状态。
  - `from_ralph=False` 时直接落到 `DEFAULT_INITIAL_STATE`，导致 `--target` 被静默忽略。
- 已完成：
  - 新增 `build_state_from_target_acceptance()`，无需 Ralph session 也能从 `workspace_dir + target` 构建 target acceptance state。
  - `init_state()` 在非 Ralph 且传入 `--target` 时使用新路径，生成 `target-acceptance-prompt.md`。
  - 初始化后进入 `REQUIREMENTS_DRAFT`，下一步为 `run_requirements_drafter`，避免 demo dry-run 直接完成。
  - 保留不传 target 的默认 demo 初始化行为，兼容现有测试和演示用法。
  - 已同步 `rrc_controller.py`、`rrc_real_runtime.py` 和 `tests/test_rrc_controller.py` 到实际运行目录。
  - 已用真实 V3.0 state-dir 重新执行 `init --force`，当前 state 正确：
    - `requestedOutcome=V3.0`
    - `currentUnitId=target-v3-0`
    - `currentStep=REQUIREMENTS_DRAFT`
    - `nextAllowedActions=['run_requirements_drafter']`
- 已验证：
  - 新增红绿用例：`init --target V3.0 --workspace-dir ...` 不带 `--from-ralph` 时创建真实 target state。
  - 相关初始化/start/Ralph 用例 -> `7 passed in 0.60s`
  - 实际运行目录关键用例 -> `2 passed in 2.49s`
  - `python -m pytest workflow_controller/tests -q` -> `115 passed in 40.82s`

### 阶段 20：V0.1 Unit 1 配置、runner 与 env 隔离
- **状态：** complete
- 背景：
  - 执行 approved unit `v0-1-u1-config-runner-isolation`。
  - 上轮 controller verifier 在 `/bin/sh` 下执行 `source ...` 导致 approved verification commands 返回 127。
- 已确认：
  - 默认 `testStrategistEnabled=false` 已覆盖。
  - `roleRunners.test_strategist` 默认 `subprocess + codex exec --dangerously-bypass-approvals-and-sandbox -`，并支持 role-specific override。
  - `roleRunners.test_strategist.env` 只通过 role runner request 注入，不污染 builder 等非 Test Strategist runner。
  - runner metadata 只记录 role、runner 和 env keys，不记录代理、token 或 secret value。
  - verifier 已用 bash 执行 shell verification command，并有 `source ./activate` 回归用例覆盖。
- 已验证：
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `19 passed in 10.94s`
  - `python -m pytest workflow_controller/tests/test_rrc_real_runtime.py -q` -> `15 passed in 6.44s`
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `50 passed in 3.92s`
- Review note：
  - 独立 review 提醒 Test Strategist production orchestration path 尚未接入 role 参数；该接入属于后续 controller orchestration unit，当前 unit 已完成 runner/config/env 隔离基础能力。

### 阶段 21：V0.1 Unit 5 回归验收
- **状态：** complete
- 背景：
  - 执行 approved unit `v0-1-u5-regression-acceptance`。
  - 核心缺口是完整 E2E 用例 `TC-E2E01-enabled-full-unit-plan-strategy-flow` 尚未落到 `test_rrc_controller.py` 中。
- 已完成：
  - 新增 `test_e2e_test_strategist_unit_plan_flow`，覆盖默认关闭 baseline、启用 Test Strategist、首轮 Critical gap 自动返工、第二轮 Major/Minor 进入现有 Unit Plan gate、summary/gap/review artifacts、env key-only 记录、无 `WAITING_TEST_STRATEGY_APPROVAL`。
  - 确认 disabled flow 不生成 `test-strategy.json` / `unit-plan-gap-report.json` / `unit-plan-review-package.json`。
  - 确认 enabled flow 生成完整 strategist artifacts，且最终 `approvals/unit-plan.md` 不包含 unresolved Critical gap。
  - 确认本单元没有新增浏览器 UI 或 browser-visible page，不需要浏览器验收。
- 已验证：
  - RED：`python -m pytest workflow_controller/tests/test_rrc_controller.py::test_e2e_test_strategist_unit_plan_flow -q` -> `ERROR: not found`。
  - GREEN：`python -m pytest workflow_controller/tests/test_rrc_controller.py::test_e2e_test_strategist_unit_plan_flow -q` -> `1 passed in 0.22s`。
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `19 passed in 11.03s`。
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `66 passed in 4.40s`。
  - `python -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `33 passed in 14.74s`。
  - `python -m pytest workflow_controller/tests/test_rrc_real_runtime.py -q` -> `15 passed in 6.52s`。
  - `python -m pytest workflow_controller/tests -q` -> `144 passed in 40.34s`。
- Review note：
  - simplify skill required three subagent reviews, but all three Agent calls returned API 503; local simplify pass found no cleanup worth changing.

## 会话：2026-04-28

### 阶段 5：控制器可靠性增强
- **状态：** complete
- 开始时间：2026-04-28
- 目标：
  - 防止同一 verification/review/builder timeout 死循环。
  - 防止 tmux Claude 写错旧 run 的 done.json。
  - 将验证环境从命令字符串中抽离为 `verification_env`。
  - 在 Unit Plan approval 阶段预检明显不可运行的验证配置。
  - 改善 timeout/idle 诊断信息。
- 计划测试：
  - `python -m pytest workflow_controller/tests -q`
- 已完成：
  - 重复 verification/review 失败会按 unit/stage/fingerprint 计数；默认第一次返工，第二次相同失败直接 `blocked`。
  - tmux runner 为每个 run 注入 `RRC_RUN_ID`，prompt 要求 `done.json` 携带 `run_id`，控制器拒绝 wrong-run done signal。
  - verifier 支持 state/unit 级 `verification_env`/`verificationEnv`，运行时注入 subprocess，artifact 只记录 env key。
  - Unit Plan approval 会拒绝明显缺 `verification_env` 的 Playwright/E2E/Prisma 验证命令，并在 drafter prompt 中提示填写 `verification_env`。
  - tmux timeout 现在区分普通 timeout、idle-without-done、wrong-run done signal、invalid done.json，并保存 pane tail。
- 已验证：
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py::test_repeated_verification_failure_blocks_before_another_retry -q`
  - `python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q`
  - `python -m pytest workflow_controller/tests/test_rrc_real_runtime.py::test_run_verifier_injects_unit_verification_env_without_inlining_it_in_command -q`
  - `python -m pytest workflow_controller/tests/test_rrc_human_gates.py::test_unit_plan_approval_rejects_playwright_command_without_database_env -q`
  - `python -m pytest workflow_controller/tests -q` -> `76 passed in 19.91s`

### 阶段 6：控制器运行可见性优化
- **状态：** complete
- 开始时间：2026-04-28
- 背景：
  - Claude 写入 `done.json` 后，controller 会继续执行自己的 verifier。
  - verifier 使用捕获输出，长 Playwright 命令运行时终端没有新日志，容易误判为 controller 没反应。
  - 紧凑输出将历史 covered units 纳入分母，导致 V2.1 显示为 `1/10`，实际当前目标只有 4 个单元。
- 已完成：
  - verifier 仅在状态变化时输出标志：验证开始、每条命令开始、每条命令结束、验证完成。
  - 不做 30 秒 heartbeat，不刷命令 stdout/stderr，避免输出噪声。
  - 紧凑 roadmap 对当前 requestedOutcome 优先按目标相关 objectiveCoverage 计算单元进度，V2.1 显示为 `1/4`、`2/4`。
- 已验证：
  - `python -m pytest workflow_controller/tests -q` -> `79 passed in 21.05s`
  - 实际运行目录新增行为测试 -> `3 passed in 1.40s`

### 阶段 7：验证失败原因摘要
- **状态：** complete
- 开始时间：2026-04-28
- 背景：
  - controller 验证失败时紧凑输出只显示“验证未通过”，用户需要打开 artifact 才能看到失败命令和根因。
  - 本次实际失败根因是 Playwright 验证命令缺少 `DATABASE_URL`，Next.js warning 只是噪声。
- 已完成：
  - retry 输出会追加 compact failure reason：失败命令、exit code、优先提取的根因行。
  - 对 `Environment variable not found: DATABASE_URL` 这类错误会压缩成 `missing env DATABASE_URL`。
  - 保留完整 stdout/stderr 在 `verification.json`。
- 已验证：
  - `python -m pytest workflow_controller/tests -q` -> `80 passed in 19.99s`
  - 实际运行目录失败摘要测试 -> `1 passed in 1.15s`

### 阶段 8：旧 Session 验证环境自动修复
- **状态：** complete
- 开始时间：2026-04-28
- 背景：
  - 同类 `DATABASE_URL` 缺失问题已第二次出现，上一次靠手工修改 session 收场。
  - 新 Unit Plan approval 预检无法覆盖已经批准的旧 session。
- 已完成：
  - verifier 运行前会检查 verification command 所需环境。
  - 对 Playwright/Prisma/显式 `DATABASE_URL` 命令，若 state/unit 未配置 `DATABASE_URL`，会尝试从 `executionWorkspacePath/prisma/dev.db` 或 `workspacePath/prisma/dev.db` 自动推导。
  - 推导成功会写入 state-level `verification_env` 和 `verification_env_inferred`，后续验证复用，不需要手改 session。
  - 推导失败会直接 `blocked`，提示 `verification environment is incomplete`，不会回 Builder 重试。
- 已验证：
  - `python -m pytest workflow_controller/tests -q` -> `82 passed in 20.37s`
  - 实际运行目录新增验证环境测试 -> `2 passed in 1.33s`

### 阶段 1：运行问题修复
- **状态：** complete
- 执行的操作：
  - 修复 Plannotator 启动方式，避免控制器等待前台进程直到超时。
  - 增加 Plannotator 端口配置，默认使用 20000。
  - 修复 Unit Plan 确认后状态不推进的问题。
  - 提高默认最大步数到 2000。
  - 增加重复无进展 50 次保护。
- 创建/修改的文件：
  - `workflow_controller/rrc_plannotator.py`
  - `workflow_controller/rrc_controller.py`
  - `workflow_controller/rrc_human_gates.py`
  - `workflow_controller/rrc_steps.py`
  - 相关测试文件

### 阶段 2：输出体验优化
- **状态：** complete
- 执行的操作：
  - 默认切换为紧凑输出。
  - 将重复循环信息聚合为 attempt 摘要。
  - 保留 `--verbose` 作为原始详细日志开关。
  - 增加颜色参数 `--color auto|always|never`。
  - 状态、阶段、动作展示改为中文。
- 创建/修改的文件：
  - `workflow_controller/rrc_controller.py`
  - `workflow_controller/rrc_steps.py`
  - 相关测试文件

### 阶段 3：迁移到 ai-works 分支工作区
- **状态：** complete
- 开始时间：2026-04-28 10:31 +0800
- 执行的操作：
  - 确认 `~/works/ai-works` 是 bare/manage repo。
  - 创建 `workflow-controller` 孤儿分支 worktree。
  - 将当前项目复制到 `~/works/ai-works/worktrees/workflow-controller/workflow_controller/`。
  - 清理误提交的 `__pycache__`。
  - 新增 `.gitignore`。
  - 提交初始项目基线。
- 创建/修改的文件：
  - `.gitignore`
  - `workflow_controller/`
- 提交：
  - `fd27a54 Add workflow controller project`

### 阶段 4：计划与进度文件
- **状态：** complete
- 开始时间：2026-04-28 10:45 +0800
- 执行的操作：
  - 在新工作区根目录写入计划、发现、进度三份持久化上下文文件。
  - 将计划与进度文件提交到 `workflow-controller` 分支。
- 创建/修改的文件：
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

## 测试结果
| 测试 | 输入 | 预期结果 | 实际结果 | 状态 |
|------|------|---------|---------|------|
| 新工作区单元测试 | `python -m pytest workflow_controller/tests -q` | 全部通过 | `76 passed in 19.91s` | 通过 |
| Git 工作区状态 | `git status --short` | 无未提交变更 | 计划文件提交后无输出 | 通过 |
| Worktree 注册 | `git --git-dir=~/works/ai-works/.git worktree list` | 出现 `workflow-controller` | 已注册 `workflow-controller` worktree | 通过 |

## 错误日志
| 时间戳 | 错误 | 尝试次数 | 解决方案 |
|--------|------|---------|---------|
| 2026-04-28 10:31 +0800 | `git worktree add --orphan workflow-controller <path>` 参数形式错误 | 1 | 改用 `git worktree add --orphan -b workflow-controller <path>` |
| 2026-04-28 10:33 +0800 | 初始提交包含 `__pycache__` 和 `.pyc` | 1 | `git rm -r` 删除缓存文件，新增 `.gitignore`，执行 `git commit --amend --no-edit` |

## 五问重启检查
| 问题 | 答案 |
|------|------|
| 我在哪里？ | `~/works/ai-works/worktrees/workflow-controller` 的 `workflow-controller` 分支 |
| 我要去哪里？ | 后续所有 Waygate 开发都在此 worktree 继续 |
| 目标是什么？ | 保留当前已修复功能，并以可测试、可提交的新工作区作为开发基线 |
| 我学到了什么？ | 见 `findings.md` |
| 我做了什么？ | 见上方阶段记录 |

---
*每个阶段完成后或遇到错误时更新此文件*
