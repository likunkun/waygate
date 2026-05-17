# 进度日志

## 会话：2026-05-17

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
