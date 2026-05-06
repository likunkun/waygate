# 进度日志

## 会话：2026-05-06

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
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_packaging.py -q` -> `1 passed in 0.38s`
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_controller.py::test_compact_reporter_dedupes_identical_rendered_status_cards -q` -> `1 passed in 0.43s`
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_agent_runners.py::test_tmux_runner_dispatch_prompt_uses_absolute_paths_for_relative_artifact_dir -q && test ! -e relative-artifacts` -> `1 passed in 0.68s`
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `29 passed in 9.64s`
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `140 passed in 9.53s`
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `40 passed in 13.83s`
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/gates/test_gates_structure.py -q` -> `18 passed in 0.04s`
  - `bash packaging/debian/build-deb.sh` -> `dist/waygate_0.5.3_all.deb`
  - `dpkg-deb --info dist/waygate_0.5.3_all.deb` -> `Package: waygate`, `Version: 0.5.3`, `Depends: python3`
  - `dpkg-deb --contents dist/waygate_0.5.3_all.deb` -> 包含 `/usr/bin/waygate`、`workflow_controller/cli.py`、README / USAGE / ROADMAP docs
  - `python -m workflow_controller.cli --help` -> `usage: waygate ...`
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `339 passed in 40.64s`

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
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `337 passed in 41.24s`

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
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `335 passed in 40.40s`

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
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `334 passed in 38.87s`

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
- 已验证全量测试：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `332 passed in 43.67s`

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
- 已验证全量测试：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `303 passed in 33.18s`

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
- 已验证定向测试：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_controller.py::test_init_creates_agent_operating_guide_and_docs_layout workflow_controller/tests/test_rrc_controller.py::test_init_can_generate_claude_md_and_does_not_overwrite_existing_guides -q` -> `2 passed in 0.19s`
- 已验证 controller 回归：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `94 passed in 5.08s`
- 已验证全量测试：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `272 passed in 30.72s`
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
- 已验证定向测试：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/gates/test_gates_structure.py -q` -> `147 passed in 14.76s`
- 已验证全量测试：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `268 passed in 30.15s`

### V0.3.5 Verifier Evidence Schema
- **状态：** complete
- `verification.json` 现在保留既有 verdict 字段，同时新增 `evidence_schema_version=v0.3.5` 和 `evidence_rows`。
- Evidence rows 记录 unit、test case、AC、AO、verification layer、command/manual evidence、expected、status、result index、returncode、artifact refs 和 golden path。
- 自动化命令结果会映射为 `passed` / `failed` / `missing`；无命令的人工证据会映射为 `manual`。
- Controller 在 verifier 通过后校验 evidence schema；schema 缺失或 malformed 时按验证失败进入既有返工/重复失败保护，不进入 `UNIT_COMPLETE`。
- V0.3.5 本身不改变 Final Acceptance gate 渲染；V0.3.6 已消费 `evidence_rows` 渲染最终验收矩阵。
- 已验证定向测试：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_verifier.py workflow_controller/tests/test_rrc_real_runtime.py workflow_controller/tests/test_rrc_controller.py workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/gates/test_gates_structure.py -q` -> `169 passed in 17.97s`
- 已验证全量测试：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `267 passed in 29.94s`

## 会话：2026-05-03

### V0.3.4 Product Design / Technical Architecture Traceability
- **状态：** complete
- V0.3.4 范围明确为 Requirements + Unit Plan 的设计/架构可追溯链路，不包含 Verifier evidence schema 或 Final Acceptance evidence matrix。
- Requirements draft prompt 和本地 gate template 新增 `Design/Architecture Traceability Matrix`。
- Requirements approval 在矩阵存在时要求每条 AC 同时具备 Product Design Ref 和 Technical Architecture Ref；旧 requirements 无该矩阵时保持兼容。
- Unit Plan prompt 和 Test Case Matrix template 新增产品设计引用、技术架构引用字段。
- Unit Plan approval 会校验 test case 是否保留 requirements 中对应 AC 的设计/架构引用。
- 已验证定向测试：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_acceptance_obligations.py workflow_controller/tests/test_rrc_human_gates.py workflow_controller/tests/gates/test_gates_structure.py workflow_controller/tests/test_rrc_controller.py -q` -> `159 passed in 15.06s`
- 已验证全量测试：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `264 passed in 31.38s`

### V0.3.3 Requirements Quality Gate 完成
- **状态：** complete
- Requirements approval 现在会在写入 accepted 前执行质量预检。
- 每个 active `must` AO 必须在 Requirements Traceability Matrix 或等价结构中映射到 AC，或显式标记为 `deferred` / `rejected` / `out_of_scope` 并写明原因。
- 每条 AC 必须声明 verification layer；支持 `unit`、`functional`、`integration`、`e2e`、`manual`，并兼容既有 `API` 语义。
- `approve_human_gate('requirements')` 和已预批准 gate 的 `check_requirements_acceptance` 都会阻断无效 requirements，不会进入 Unit Plan。
- requirements gate invalid 会写入 `blockedReason`，并在 requirements revision prompt 中追加 `Controller Validation Error`。
- Requirements draft prompt 和本地 gate template 已新增 `## 4. 需求可追溯矩阵（Requirements Traceability Matrix）`。
- 已验证：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `259 passed in 30.51s`

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
- 已验证：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `252 passed in 30.76s`

### V0.3.1 Acceptance Obligation Ledger 完成
- **状态：** complete
- 已新增 AO Ledger：人工反馈、Plannotator annotations、Requirements/Unit Plan 返工和 Final Acceptance rejection 会进入 `acceptanceObligations`。
- 已写入 AO artifacts：`artifacts/acceptance-obligations/acceptance-obligations.json` 和 `acceptance-obligations.md`。
- Requirements / Unit Plan prompt 会注入 AO Ledger，并要求每条 must AO 进入 AC、测试用例或人工证据映射。
- Unit Plan approval 会阻断缺失 active must AO 覆盖的计划，并列出缺失 AO id 与标题；已修复审查发现的 approved gate bypass。
- AO coverage 只计算结构化 `test_cases[].covers_obligations` 或 Test Case Matrix 中有 test case、layer、command/evidence、expected 的映射，不再把复制的 ledger/prose AO id 视为覆盖。
- Plannotator structured annotations 会传入 AO 创建逻辑，避免多条浏览器批注被压成一条 AO。
- 已修复 E2E fixture：closure unit 必须包含 `golden_path` test case。
- 已验证：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `240 passed in 32.12s`

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
  - 用户执行 `init --workspace-dir /home/lichangkun/works/ai-works/worktrees/union --target "V3.0"`，随后 `start --target "V3.0"` 报 existing session mismatch。
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
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `19 passed in 10.94s`
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_real_runtime.py -q` -> `15 passed in 6.44s`
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `50 passed in 3.92s`
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
  - RED：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_controller.py::test_e2e_test_strategist_unit_plan_flow -q` -> `ERROR: not found`。
  - GREEN：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_controller.py::test_e2e_test_strategist_unit_plan_flow -q` -> `1 passed in 0.22s`。
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q` -> `19 passed in 11.03s`。
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_controller.py -q` -> `66 passed in 4.40s`。
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_human_gates.py -q` -> `33 passed in 14.74s`。
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests/test_rrc_real_runtime.py -q` -> `15 passed in 6.52s`。
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q` -> `144 passed in 40.34s`。
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
  - `source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q`
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
