# 发现与决策

## 2026-05-16 Requirements 自动打回连续原因计数

- Requirements 草案预检自动修订预算的核心风险不是“总共修订几次”，而是“同一个 controller invalid reason 被 agent 反复修不掉”。不同 invalid reason 表示 gate 已向前推进，应视为新的有效打回。
- `requirementsAutoRevisionMax` 继续保留为默认 2，但语义调整为连续相同 reason 的最大自动修订次数；reason 变化时连续计数重置。
- 自动修订事件继续保留 `attempt` 字段表示当前 reason 的连续 attempt，同时新增 `total_attempt` 便于排查一轮 Requirements 草案内实际发生了多少次自动打回。
- 相同 reason 连续超过上限仍会进入 `requirements_draft_auto_revision_blocked`，避免 Requirements drafter 在同一错误上无限循环。

## 2026-05-16 Prototype Surface Conformance 流程修复

- 只把整张 prototype 映射到 route/page 仍会漏掉真实交互入口；`AssignManageDialog` 这类弹窗、抽屉、管理面板和单项操作入口必须作为独立 surface contract 进入 Requirements、Unit Plan 和 Final Acceptance。
- `surface_contracts[]` 是新的细粒度验收事实源；`ui_surfaces[]` / `page_state_targets[]` 仅作为输入别名，归一化后统一落到 `surface_contracts`。
- 如果 prototype 已声明 required surface，后续 conformance 不再用 prototype-level `implementation_targets` 代替 surface targets；prototype-level target 只保留 legacy/汇总兼容。
- Unit Plan 的匹配键必须包含 `prototype + surface + production target`，否则 `PublishTargetDialog` 这类相邻 surface 测试会误覆盖 `AssignManageDialog`。
- Final Acceptance verifier evidence 必须优先按 `test_case_id` 对齐；同一个 Playwright command 可能覆盖多个 test case，不能用 command fallback 证明未执行的 surface test。

## 2026-05-16 Plannotator 原型审阅可达性增强

- Requirements 人工确认选择 Plannotator 后，终端必须同时暴露审批入口和 controller preview server 的渲染入口；Plannotator 审批事实源仍是 `approvals/requirements-and-acceptance.md`，`plannotator-review.html` 只是审阅视图。
- 本地 HTML prototype 的主审阅体验仍应是 `iframe srcdoc`，这样 Plannotator 打开 HTML review 后可直接看到渲染效果。
- 后续可达性需求允许在 controller preview server 提供的 `plannotator-review.html` 内放置本地 source 相对链接，方便人工打开独立页面或文档；禁止的是诱导点击 Plannotator 自身 `localhost:20000/prototypes/...` 路由。
- Markdown prototype 是本地 source/documentation artifact，应作为 path-backed prototype 复制到 `requirements-draft/prototypes/`，并由 preview server 以 `text/markdown; charset=utf-8` 提供。

## 2026-05-16 Plannotator 原型 HTML 纯文本预览

- Preview server 直接访问 HTML prototype 时已返回 `Content-Type: text/html; charset=utf-8`，所以问题不在静态服务 MIME。
- Plannotator 当前审阅入口拿到的是 `plannotator-review.md`；Markdown 中的本地 HTML prototype 是相对链接，Plannotator 对该链接目标按文档查看，导致用户看到 HTML 源码/纯文本，而不是浏览器渲染结果。
- Prototype review bundle 需要一个真正的 HTML 审阅入口，而不是只靠 Markdown 链接。HTML bundle 应内嵌本地 HTML prototype 的 `iframe srcdoc`，让 Plannotator 打开的首屏就能看到渲染效果，同时保留 AC/Journey/Production Target 映射。
- Markdown bundle 仍应保留作为审计和兼容 artifact；Requirements 人工确认的审批事实源仍是 `approvals/requirements-and-acceptance.md`，HTML bundle 只是 review view。
- `http://localhost:20000/prototypes/...` 是 Plannotator 自身 Web app 的路由，不等同于 controller 临时 preview server 的 `/prototypes/...` 静态服务；review HTML 中不能放会引导用户点击该路径的相对 prototype 链接。
- 对本地 HTML prototype，HTML review 应以内嵌 `iframe srcdoc` 作为唯一渲染入口；standalone prototype 路径可以作为不可点击 source path 展示，避免人审误进入 Plannotator 的文本/SPA 视图。

## 2026-05-16 Requirements 预检修订重复澄清

- 无 `--spec` 的首次 Requirements intake 必须先澄清，这个规则仍然正确；但 Requirements 预检自动打回后的 revision 已经有上一版 gate、Requirements Dialogue Brief、controller validation error 和 `## 4.8`，不应再被当成首次 intake。
- 现场 V2.9.1 证明，revision prompt 如果继续保留“第一条回复只能澄清 / 继续不是有效回答 / 未完成首次澄清不能 drafting”，agent 会重复询问已经在 `## 4.8` 记录的范围问题，甚至把 controller 可自动修复的 Journey layer 错误变成人工阻塞。
- `requirementsRevisionFeedback` 是区分修订轮次的可靠信号：它由 controller 在人工 revision 或 validation-only 自动 revision 前注入，且包含上一版 gate 和当前阻断原因。
- Requirements revision prompt 应复用已有澄清事实，只在当前 controller validation error 或人工反馈无法从已有 gate、brief 和 `## 4.8` 解决时再问新的阻断澄清。

## 2026-05-16 V0.6.0b Prototype Conformance Gate

- V0.6.0a 只能保证 Requirements 阶段的 prototype artifact 可审阅、可点击，但不能保证 Builder 最终实现的生产 route/page 继承了原型的信息架构和交互合约。
- 原型 manifest 需要明确 `implementation_targets`，否则 Unit Plan、Verifier 和 Final Acceptance 无法判断哪些真实页面必须与哪个 prototype 对齐。`production_targets` / `real_targets` 作为兼容别名保留，但推荐输出 `implementation_targets`。
- Requirements 正文一旦把 prototype、clickable webpage prototype 或 UI contract 写成验收义务，即使 state flags 没打开，也必须触发 manifest 与 production target 预检；但 V0.6.0/V0.6.0a/V0.6.0b 这类 controller policy work 不要求 controller 自己产出业务原型。
- 静态 prototype 点击测试只能证明 review artifact 可用，不能证明生产 UI 一致性。Unit Plan 中的 prototype conformance 必须通过 `prototype_conformance`、`production_targets`、真实 route/page command 和具体 expected 断言表达。
- Final Acceptance 需要单独展示 Prototype Conformance Matrix；证据缺失或未通过时阻断终验，避免普通 AC 覆盖证据掩盖 UI 合约未落地。

## 2026-05-15 V0.6.0a Prototype Review Bundle 实施决策

- 原型审阅需要和 approval gate 分离：Plannotator 可审阅 `artifacts/requirements-draft/plannotator-review.md`，但 Requirements 批准状态仍只写入 `approvals/requirements-and-acceptance.md`，避免 review view 成为审批事实源。
- `prototype-manifest.json` 是 agent 输出事实源，`prototype-review-manifest.json` 是 controller 规范化后的审阅事实源；本地图片/HTML 必须复制进 `artifacts/requirements-draft/prototypes/`，避免 Plannotator 依赖任意工作区路径。
- Web 系统的原型不能只靠 prose 通过预检；必须有结构化 manifest，并且每个 prototype 必须映射真实 AC、包含 page states 和 click path。Web manifest 还必须至少包含可点击 HTML 或 URL，不接受 image-only。
- 外部 prototype URL 允许用于审阅，但 query key 中出现 token、password、secret、api_key、signature 等敏感字段时必须阻断，避免把带凭据 URL 写入 artifact 或日志。
- localhost preview server 只在 Requirements bundle 审阅期间启动，绑定 `127.0.0.1` 随机端口，只服务 review bundle、normalized manifest、`prototypes/` 和 approval gate；决策结束后关闭，降低意外暴露范围。

## 2026-05-15 V0.6.0a Prototype Review Bundle

- V0.6.0 已要求 Requirements 阶段提供 prototype evidence，但当前 Plannotator 默认审阅 approval Markdown；原型路径只是普通文本，无法保证图片、HTML 或 URL 在浏览器审阅中顺滑打开。
- Requirements 审阅对象和 approval gate 应继续分离：Plannotator 可以打开专用 review bundle，但批准状态仍落在 `approvals/requirements-and-acceptance.md`。
- 原型证据需要结构化 manifest 承载 prototype id、类型、路径或 URL、AC/Journey 映射、页面状态和点击路径；Markdown review bundle 只作为人工审阅视图。
- Controller 预检应在人工确认前检查原型资产路径、可点击访问方式、页面状态、点击路径和 AC 映射，避免无效原型进入人工确认。
- `V0.6.0a` 定位为 V0.6.0 的体验补丁，不改变 Requirements / Unit Plan / Final Acceptance 的审批语义。

## 2026-05-15 测试用例契约强化路线

- 仅要求 test case 有 `id`、`acceptance_criterion`、`layer`、`fixture`、`command` 和 `expected` 不足以防止 AI 生成看似完整但证明力不足的测试计划。
- 后续测试治理应优先收敛结构化事实源：Controller State Patch 的 `test_cases[]` 应成为权威来源，Markdown Test Case Matrix 只作为 review view。
- Test Case Contract v1 应从自由文本字段升级为可审计字段：`acceptance_criteria[]`、`covers_obligations[]`、`covers_journeys[]`、`path_type`、`setup[]`、`entrypoint`、`command_id`、`manual_evidence` 和 `assertions[]`。
- Controller 负责硬性阻断缺失映射、弱断言、static-only 冒充行为测试、E2E 缺少用户步骤和人工证据冒充自动化；Test Case Review Agent 只做人工确认前批注，不自动批准。
- Verifier 和 Final Acceptance 需要按 test case 逐条产生和展示 evidence，未执行的计划测试必须明确标为 `missing`，不能由 agent 总结代替证据。

## 2026-05-14 tmux-codex 清输入自退出

- `C-c` 在 Claude Code 和 Codex TUI 中不是等价的安全清理动作：Claude Code 中可用于取消未提交草稿，Codex TUI 中可能中断或退出当前 Codex 进程。
- tmux dispatch 前清理输入框必须按 backend 区分；不能把 Claude 的 `C-c` / `C-u` 组合泛化到 Codex。
- Codex 路径应默认只发送 `C-u` 清当前输入，并继续依赖 paste 后 submit delay 与 submit retry 处理 Codex 折叠 pasted content 或首次 Enter 未生效的情况。
- idle nudge 仍不能清输入；对正在运行的 agent 发送 `C-c` 会打断任务，对 Codex 风险更高。

## 2026-05-14 auto-created Claude pane 初次清输入退出

- `waygate go V2.9 --auto-approve` 现场失败不是 auto-created pane 没创建成功；`tmux send-keys -t %24 C-c` 返回码为 0 证明 pane 当时存在。
- 根因是 auto-created Claude pane 刚启动后立即进入通用 dispatch 前清输入流程，`C-c` 会中断或关闭尚未稳定的 Claude pane；随后 `C-u` 返回 `can't find pane: %24`，Requirements drafter 以 runner exit code 1 失败。
- 新建 pane 本来没有人工草稿需要清理；清输入只应默认用于复用既有 pane。auto-created pane 的首次 Requirements Draft dispatch 应跳过清输入，后续已有 pane 仍保留清输入保护。

## 2026-05-14 auto-created Claude pane stale state 恢复

- 第二次 `waygate go V2.9 --auto-approve` 现场失败的 stderr 仍是 `can't find pane: %24`，但 events 已经没有 dispatch 前 `C-c` / `C-u`，说明初次清输入修复生效，剩余问题是旧 state 中保存的 auto-created pane 已经不存在。
- `start()` 恢复已有 `session.json` 时，如果 state 同时已有 `agentRunner` 和 `tmuxTarget`，旧逻辑不会重新探测 target；因此 stale `%24` 会直接进入 runner dispatch，直到 `tmux send-keys` 才失败。
- 修复边界必须限于 controller 自动创建的 Claude pane：当 `tmuxTargetResolution.source` 或 `detectedSource` 为 `auto-created` 且 runner 为 `tmux-claude`，恢复时探测为空才重新创建 pane 并更新 state。用户显式指定的 tmux target 不应被静默替换。

## 2026-05-14 Requirements 无 spec 澄清被绕过

- 现场 V2.9 无 `--spec` 时，Requirements Draft agent 没有在 pane 中展示可见澄清问题，而是直接检索项目、读取 roadmap 和源码并写出 Requirements Gate。
- 旧回归测试只断言 prompt 中出现“必须澄清”和“不得写 DONE_FILE”，没有断言第一轮必须只问问题、不能先读项目/写 body，也没有断言「继续」「你看着办」这类非具体回复不能算澄清完成。
- prompt 旧文案还存在直接冲突：前面要求先澄清，后面又说“可用保守假设推进时必须推进”；并且写 body_path 的指令位于澄清协议之前，agent 容易优先执行写文件任务。
- 无 `--spec` 的 Requirements Draft 必须把澄清协议放在写文件指令之前，并明确：第一条回复只能是澄清问题；收到具体澄清回答前不得读项目文件、检索代码、生成正文或写 body；「继续」「按你理解」「你看着办」不是有效澄清回答。
- `waygate revise --gate requirements` 不会像 `waygate go V2.9` 一样自动推导目标 state-dir；在多 controller state 的 workspace 中容易误读默认 state。`revise` 应支持 positional target / `--target`，按同一 slug 规则推导 `.rrc-controller-<target>`。

## 2026-05-13 Approved Unit Plan 后 Requirements Change

- Requirements 是 Unit Plan 和 Builder 的上游约束源；当 approved Requirements 写死某个不可执行策略时，Unit Plan revision 不能合法绕过它，必须先创建 Requirements change request。
- `waygate revise --gate requirements --reason ...` 在 `PLAN_APPROVED` / `EXECUTE_UNIT` 中代表用户显式要求变更已批准 Requirements，因此应同时失效 Requirements 和 Unit Plan approval，并重新进入 Requirements 人工确认。
- Builder blocked summary 只适合作为 Requirements revision prompt 的辅助证据；它不能替代用户变更原因、当前 Requirements、Unit Plan 约束和后续人工审批。
- Final Acceptance 阶段已经有带路由选择的 rejection gate；直接 `revise --gate requirements` 会绕过终验路由语义，因此仍应提示使用 final acceptance rejection route。
- Requirements revision prompt 可能嵌入 Unit Plan 的 fenced JSON patch；外层 Markdown fence 必须根据内容自适应长度，避免 prompt 结构被内层 code fence 截断。
- 8 号窗口现场证明仅“把旧 gate 放进反馈上下文”不够：旧 approved Requirements 被埋在 Unit Plan 与 Builder blocker 之后时，drafter 会把需求误收缩为当前 unit 的 blocker 修订，丢掉后续单元需求。Approved Requirements change 必须把旧 gate 明确标成 baseline，并要求 preserve-unless-explicitly-changed。
- Unit Plan、当前 unit 和 Builder blocked summary 在 Requirements change prompt 中只能作为 delta/context；它们不能作为需求范围事实源，也不能影响旧 Requirements 中未被 `--reason` 或人工反馈明确修改的 AC、Journey、Design/Architecture、Out of Scope 和 Test Strategy。

## 2026-05-13 Plannotator 短命进程等待问题

- Plannotator runner 看到 review link 后会先返回给 controller；如果被调用进程打印链接后立即退出，后续 `_wait_for_plannotator_gate_decision()` 只能通过 `process_id` 判断进程状态。
- 仅使用 `os.kill(pid, 0)` 会把已退出但未回收的子进程 zombie 当成仍然 alive，导致 controller 无限等待 Plannotator 决策，测试和现场都无法消费后续 `r/q` 输入。
- `_process_is_alive()` 对当前子进程应优先调用 `os.waitpid(pid, os.WNOHANG)`：返回 pid 表示已退出并可视为 closed；非子进程或已被回收时再回退到 `os.kill(pid, 0)`。

## 2026-05-13 人工评审提醒草稿清理

- 人工评审提醒原先是中英文两行，controller 只粘贴、不提交；下一轮正常 dispatch 前只发送一次 `C-u`，在 Claude 多行输入框里只能保证清理光标所在行，无法可靠移除整段未提交草稿。
- 修复边界应在 runner 派发前清理输入草稿：先发 `C-c` 取消当前未提交输入，再发 `C-u` 兜底清当前行；不能用 `/clear`，否则会清掉 agent 会话上下文。
- 为避免后续再次制造多行残留，人工评审提醒应保持单行文本；视觉换行由终端宽度自然处理，不写入实际 newline。
- idle nudge 不能复用 dispatch 前清理逻辑；nudge 是对正在等待完成信号的 agent 提醒，发送 `C-c` 会把正在进行的 agent 工作打断。
- 8 号窗口现场进一步证明，`tmux send-keys C-c C-u` 返回码为 0 只能说明按键已交给 tmux，不能证明 Claude TUI 已处理完成。现场 06:46:31 的 events 显示清理命令和 `paste-buffer` 相隔不到 10ms，导致旧人工评审提醒仍作为多行输入前缀保留，并和新的 `workflow-controller dispatch` 拼到一起。
- 清理必须拆成两个 tmux 命令：先 `C-c`，等待短暂 settle，再 `C-u`，再等待短暂 settle，最后才 paste 新 dispatch。该 settle 不是 idle nudge，也不能应用到 nudge 阶段。

## 2026-05-13 Builder blocked 到 Unit Plan revision 恢复

- Builder 在已批准 Unit Plan 后返回 `blocked` 不一定代表 Requirements 需要变更；当 blocker 指向实现计划缺口或未定义的相邻契约时，更合理的恢复路径是回到 Unit Plan revision。
- `builder-summary.json` 中的 `runner_status=blocked` 或 `done_payload.status=blocked` 是 controller 可验证的恢复信号；自然语言错误输出不能作为唯一事实源。
- Unit Plan revision prompt 必须优先携带 Builder `done_payload.summary`，否则 drafter 看不到真正的 blocker，容易继续生成同一个不可执行计划。
- Requirements approval 在该恢复路径中应保持不变；只清除 Unit Plan approval，并重新进入 `WAITING_UNIT_PLAN_APPROVAL`。

## 需求
- 最终验收阶段不应强迫只能选择同意，应保留清晰的人工确认路径。
- Plannotator 启动不应因长期前台运行导致控制器 30 秒超时。
- Plannotator 默认端口应匹配本机使用习惯：20000。
- Unit Plan 人工确认后应推进状态，不能停留在 `WAITING_UNIT_PLAN_APPROVAL` 中重复检查直到步数耗尽。
- 50 步全局上限太低，默认至少应提高到 2000；同时需要对“没有状态变化的重复循环”做单独保护。
- 默认输出应低噪声：用紧凑阶段编排展示目标、当前阶段、剩余阶段和 attempt 摘要。
- 原始详细输出仍需保留，放到 `--verbose`。
- 输出状态和阶段文案使用中文，并支持颜色。
- 当前项目后续开发应迁移到 `~/works/ai-works/` 下的分支工作区。

## 研究发现
- `~/works/ai-works` 是 bare/manage repo，本身不是普通 work tree。
- 该仓库已通过 `worktrees/` 目录管理多个分支工作区。
- 当前适合新增 `workflow-controller` 分支和同名 worktree，而不是把代码直接放在 bare repo 根目录。
- 从新工作区根目录运行 `python -m pytest workflow_controller/tests -q` 可以保持原有包导入方式。
- 源目录里存在测试产生的 `__pycache__`，复制后需要清理，避免进入新仓库历史。

## 技术决策
| 决策 | 理由 |
|------|------|
| 使用 `workflow-controller` 孤儿分支 | 保留一个独立项目历史，不污染现有 `ai-works` 分支 |
| 将代码放在根目录下的 `workflow_controller/` | 保持测试路径和 Python 包结构稳定 |
| 新增 `.gitignore` 忽略 Python 缓存和 pytest 缓存 | 避免生成文件进入提交 |
| 计划文件放在 worktree 根目录 | 后续进入目录即可看到任务上下文 |
| 测试复用项目虚拟环境 | 当前项目已有可复用测试环境 |
| 防循环逻辑放在 controller 状态机 | prompt 只能提示 agent，不能作为可靠安全边界 |
| verifier 结果是验证事实源 | agent 的 done summary 只能代表 builder 阶段结束，不能代表 controller 验证通过 |
| 默认第二次相同失败即阻断 | 第一次失败给 Builder 返工机会；第二次 unit/stage/fingerprint 相同说明没有产生有效新策略，应停下来暴露具体失败 |
| `done.json` 必须携带当前 `run_id` | tmux pane 可能残留旧 agent 上下文，路径唯一仍不足以证明完成信号属于本轮 |
| `verification_env` 只记录 key 不记录 value | 验证需要稳定环境注入，但 artifact 不应泄露数据库 URL、token 等敏感值 |
| Unit Plan approval 只预检明显环境依赖 | 目前对 Playwright/Prisma/显式 `DATABASE_URL` 做强校验，避免误伤普通 pytest E2E |
| Plannotator 审阅 body artifact，approval 文件只做确认落盘 | 浏览器批注必须落在 Claude 实际生成内容上；`approvals/*.md` 负责 controller 的确认状态和 hash |
| Plannotator `Approve` 直接驱动 controller 继续 | 用户期望浏览器 approve 就完成 gate 操作，避免同一确认在浏览器和终端重复操作 |
| Unit Plan 无效时禁止写 approved | approval 文件代表人工确认和可执行状态，不能在 controller gate invalid 时留下 approved 假象 |
| `partial` rollup objective 可引用已完成历史单元 | V2.x 聚合目标经常表示“整体目标仍 partial，历史子单元已 covered，剩余只执行新增 unit” |
| Unit Plan 确认后若 scope 已批准应进入 `PLAN_APPROVED` | 人工 gate 可能在已有 scopeApproved 的新目标/新单元中发生，不能回到需要 scope approval 的旧状态 |
| 最终验收缺陷使用 `defect_fix` 路由 | 验收中发现 i18n/logo/主页/工作台等已完成单元的 bug，不应走 requirements change，也不应强迫当前 unit builder 越界修复 |
| `defect_fix` 复用 Unit Plan revision 而不是 requirements draft | 原需求仍正确，只需要根据验收缺陷生成可执行 bug-fix units |
| Builder prompt 对 defect-fix unit 携带最终验收缺陷清单 | Unit Plan 负责定义修复单元，Builder 仍需要看到原始验收缺陷作为实现上下文 |
| Unit Plan 使用 `test-strategy` skill | TDD 解决“先写测试再实现”，但不能替代从验收标准到测试用例矩阵的策略设计 |
| Test Case Matrix 成为 Unit Plan 一等内容 | 只看 verification command 是否通过不足以证明验收覆盖；需要 AC -> test case -> layer -> evidence 的映射 |
| 静态检查不能单独作为行为验收 | `tsc`/lint/typecheck 可以兜底质量，但不能证明用户路径、UI 可见结果或缺陷回归 |
| Final Acceptance 通过后先同步 live agent | 终验批准是 controller/human 侧状态变化；最后一轮实现 agent 已停止，不主动派发同步就无法及时更新 `task_plan.md` / `progress.md` / `findings.md` |
| Requirements Draft 澄清等待超时后保留 pending run | 需求澄清是一问一答的人类等待，不应 30 分钟后重新派发同一需求讨论；超时只暂停 controller，下一次继续只有在 `done.json` 和 body 都晚于 timeout 记录时才接回 |
| tmux-claude 不做基于 pane 文本的 submit retry | Claude pane 的历史 transcript 和输入框残留在 `capture-pane` 中难以可靠区分；看到同一 RUN_ID 不足以证明需要再次回车 |

## 遇到的问题
| 问题 | 解决方案 |
|------|---------|
| `--orphan` worktree 命令首次参数顺序错误 | 使用 `--orphan -b workflow-controller <path>` |
| 初始提交包含 `.pyc` 文件 | 删除缓存文件、添加 `.gitignore`、amend 初始提交 |
| `.pytest_cache` 在测试后会生成 | 已通过 `.gitignore` 忽略 |
| Claude 可能写旧 run 的 `done.json` 或停在 prompt | 已通过 run_id 校验和 idle/timeout 诊断区分 |
| Unit Plan 生成的验证命令可能缺少环境变量 | 已通过 `verification_env` 和 approval 预检降低风险 |
| 过宽的 E2E 预检会误伤 `pytest tests/e2e/...` | 已收窄为 Playwright/Prisma/显式 `DATABASE_URL` |
| Plannotator 审阅文件与 Claude 写入文件不一致 | 改为浏览器审阅 `artifacts/*-draft/*-body.md`，确认文件仍使用 `approvals/*.md` |
| Plannotator 多条反馈看起来只收到第一条 | 根因是终端只显示 220 字符预览；prompt 中实际包含多条反馈。已改为显示 `共 N 条` 并保留完整反馈 |
| Unit Plan approval 被 `objectiveCoverage may omit existing unit ids...` 卡住 | 根因是 rollup partial objective 引用了已完成历史单元；已允许 completed existing units 出现在 partial rollup 中 |
| Unit Plan 已确认后输出“当前没有可执行的下一步” | 根因是 `PLAN_CREATED + scopeApproved=True` 未被状态机覆盖；已自动修复为 `PLAN_APPROVED -> run_builder` |
| 最终验收发现历史单元缺陷但无法修复 | 根因是历史单元已 marked covered，而当前 Builder 只能修当前 unit；新增 `defect_fix` 路由生成专门 bug-fix units |
| 验证全绿但人工发现大量漏测 | 根因是 controller 只验证命令结果，不验证测试用例是否覆盖验收标准；已增加 Test Case Matrix prompt 和静态-only approval 阻断 |
| 选择 `Defect fix` 后仍提示未选择 Rejection Routing | 根因是现场旧 `final-acceptance.md` 没有 `Defect fix` 行，旧写入逻辑只勾选已存在行且不校验写入结果；已改为规范化 canonical checklist 并补齐缺失 route |
| Plannotator 反馈后终端写 route 可能让反馈变 stale | 终端选择 route 会重写 gate 文件导致 mtime 晚于 Plannotator summary；final acceptance 现在允许读取本轮 stale feedback，避免返工 prompt 丢失浏览器批注 |
| `init --target` 不带 `--from-ralph` 生成 demo state | 根因是非 Ralph 初始化无 target 分支，直接使用 `DEFAULT_INITIAL_STATE`；已新增 target acceptance 初始化路径 |
| Final Acceptance 通过后 agent 不知道验收结果 | 根因是终验通过后直接进入 `RELEASE_GATE` / `DONE`，没有 runner 派发；已新增 `FINAL_ACCEPTANCE_AGENT_SYNC`，要求 live tmux agent 在 release 前同步状态文档并写 summary artifact |
| Requirements Draft 澄清等待超时后重新讨论需求 | 根因是 requirements 专用 timeout 仍为 1800 秒，且超时后下一次执行会创建新 run 并重新派发 prompt；已改为默认 7200 秒，并在超时 summary 中记录 `done_path`，下次仅在 fresh `done.json` + fresh body 同时存在时恢复 |
| Claude 完成后又自动开始同一个 dispatch | 根因是 tmux-claude submit retry 把 pane 中可见的历史 `workflow-controller dispatch` / RUN_ID 当作“prompt 仍在输入框”；已禁用 tmux-claude 该重试，tmux-codex 专用重试不变 |
| Builder agent blocked 时终端只显示 exit code | 根因是 `run_builder()` 抛错时没有提取 `done_payload.summary`；已将 agent `status` 和 `summary` 直接拼入 RuntimeError，完整 artifact 路径仍保留 |

## 2026-05-09 Final Acceptance 后 Agent 状态同步

- 该问题主要出现在终验：Requirements / Unit Plan approval 后通常还会派发 drafter 或 builder prompt，agent 能通过下一轮任务获得新状态；Final Acceptance approval 原先直接进入 release/DONE，没有下一轮 agent prompt。
- controller state 是事实源，但 `task_plan.md`、`progress.md`、`findings.md` 是 agent 和维护者的人类可读上下文；只更新 state 不同步这些文档，会导致后续 agent 继续把已验收目标视为 in_progress。
- 修复边界选择在 Final Acceptance approval 后、release 前新增 `FINAL_ACCEPTANCE_AGENT_SYNC`：这能让 live tmux agent 获得明确的 controller state transition，又不改变 Requirements/Unit Plan/Verifier gate 语义。
- 终验状态同步只在存在 workspace 且配置 live tmux agent pane 时默认启用；无 live pane 的 dry-run、subprocess 和历史本地路径应记录 skipped，避免为没有常驻 agent 的流程引入无意义阻塞。
- 同步 prompt 必须禁止修改 approved gate、controller state、artifacts 和源码；允许修改的目标限定为状态文档，如 `task_plan.md`、`progress.md`、`findings.md`，必要时按 `ROADMAP.md` 与 `session.json` 校准版本事实。
- `artifacts/final-acceptance-sync/final-sync-summary.json` 是本步骤证据；缺失或 runner 失败时 controller 阻断在 `FINAL_ACCEPTANCE_AGENT_SYNC`，避免 release/DONE 掩盖状态文档未同步。

## 2026-05-03 V0.3.1 设计发现

- V0.3 roadmap 原先写作“需求质量 + 证据标准化 + CodeSimplifier”，但用户当前更痛的问题是人工反馈被压缩后无法逐条追踪；V0.3.1 已先建立 Acceptance Obligation Ledger。
- 现有代码中 Plannotator feedback 会作为整段文本进入 revision feedback，Unit Plan validator 已有 Test Case Matrix/静态-only 阻断，但缺少稳定的 AO id 和“每条人工问题必须覆盖”的 ledger/gate。
- V0.3.1 最小化完成路径：human feedback/final acceptance rejection → AO Ledger → Requirements/Unit Plan prompt 注入 → Unit Plan AO coverage validator。
- AO Ledger 当前覆盖：Plannotator annotations 按条生成 AO；bullet/numbered feedback 按条拆分；无法拆分时保留整段原文为单条 AO。
- Unit Plan approval 当前只在存在 active must AO 时启用 AO coverage gate；旧 session 缺少 `acceptanceObligations` 不会被误伤。
- AO coverage 不能靠复制 ledger 或 prose 中出现 AO id 通过，必须来自结构化 test case / Test Case Matrix 映射，且 approved gate 路径也会执行同一校验。

## 2026-05-03 V0.3.2 CodeSimplifier 集成发现

- CodeSimplifier 现在默认开启，符合用户期望的 Builder 后自动精修流程；可用 `--no-code-simplifier` 显式关闭。
- 默认开启不能让无 workspace 的 demo/synthetic 流程误启动外部 agent；这类场景写入 `status=skipped`、`mode=no-workspace` 的审计 artifact。
- Refiner 的新事实源是 `simplifier-result.json`，但 `refinement-summary.json` 仍需保留，因为 reviewer 现有 artifact 检查依赖该兼容文件。
- `changes_requested` 属于可操作的实现返工，应回到 `EXECUTE_UNIT` 并复用既有 repeated-failure guard；`failed` 更像 Refiner/runner 异常，应停留在 `REFINE_UNIT` 重试或阻断，不能进入 Reviewer。
- Builder prompt 的 previous failure feedback 现在同时承载 review、verification 和 CodeSimplifier findings，避免新增单独状态字段造成反馈分散。
- role runner env value 不应进入 artifacts；metadata 只记录 env key，runner stdout/stderr 中匹配到的配置 env value 也会被 redacted。
- `init` 和 `start` 的 CodeSimplifier flags 需要与 Test Strategist overrides 合并 roleRunners，避免同时配置时互相覆盖。

## 2026-05-03 V0.3.3 Requirements Quality Gate 发现

- V0.3.1 只在 Unit Plan approval 阶段阻断 AO 覆盖缺失，仍允许不合格 requirements 先被 approve；V0.3.3 已把 AO->AC 与 AC verification layer 校验前移到 Requirements approval。
- Requirements gate validator 不能把模板说明里的示例 AC 当作真实 AC；本地模板中的示例已改成 `AC-ID [verification: e2e]`，避免空模板误通过或误报。
- 对 active must AO，空模板行必须保持 `pending`，不能用 `deferred/rejected/out_of_scope` 等可通过状态作占位。
- AC layer 解析必须偏结构化：支持 AC 行的 `[verification: e2e]`、traceability matrix 的 `Verification Layer` cell，以及以 layer 开头的 Test Strategy 行；不能把 AC 描述中的普通词 `manual` 当作 layer。
- `requirements gate invalid` 与 `unit plan gate invalid` 一样需要进入 revision feedback，否则 drafter 看不到 controller 阻断原因。

## 2026-05-03 V0.3.4 Design / Architecture Traceability 发现

- V0.3.4 的合理边界是把 Product Design / Technical Architecture 引用进入 Requirements → Unit Plan test case 链路；Verifier evidence schema 和 Final Acceptance evidence matrix 应拆到后续 V0.3.5/V0.3.6。
- Requirements 设计/架构可追溯 gate 只在文件存在 `Design/Architecture Traceability Matrix` 时启用，避免历史 gate 因新增模板要求被误伤。
- 新 Requirements 本地 template 会默认生成设计/架构可追溯矩阵，因此新 session 会被引导进入 V0.3.4 规则。
- Unit Plan test case 的设计/架构 refs 必须是 requirements 对应 AC refs 的超集，避免 planner 用相似描述或空字段通过。
- Unit Plan template 需要把产品设计引用和技术架构引用作为 Test Case Matrix 一等列，而不是隐藏在 prose 中。

## 2026-05-04 V0.3.5 Verifier Evidence Schema 发现

- V0.3.5 的合理边界是 verifier artifact schema，不改 Final Acceptance gate；最终验收矩阵已由 V0.3.6 消费 `evidence_rows`。
- `verification.json` 需要保持旧字段兼容，因为 reviewer、final acceptance summary 和既有测试仍读取 `passed`、`results`、`evidence_files`。
- Evidence row 应以 Unit Plan test case 为主；没有 test cases 的历史 session 保持兼容，允许空 `evidence_rows`，但 schema version 和 rows 字段必须存在。
- 自动化命令 row 通过 command 与 verification result 匹配；手工证据 row 保留 `manual_evidence` 和 artifact refs，不伪装成自动化 pass。
- Controller 不能只看 `passed=true`；schema malformed 也必须走验证失败返工，否则 V0.3.6 无法可靠渲染证据矩阵。

## 2026-05-04 V0.3.6 Final Acceptance Evidence Matrix 发现

- Final Acceptance gate 应消费 V0.3.5 的 `evidence_rows`，但不能删除旧证据摘要；旧摘要仍服务于快速浏览和历史 artifact 兼容。
- patch list 能减少 Builder 噪声，但不能丢掉证据定位；因此 patch list 返工反馈需要附带 evidence matrix context。
- 没有 `evidence_rows` 的历史 `verification.json` 不能让 final acceptance gate 崩掉，应显示 missing schema row 指向 `verification.json`。
- V0.3.6 只增强 gate 渲染和反馈上下文，不新增最终验收路由；更复杂的 defect-fix gate 属于 V0.4。

## 2026-05-05 V0.4 控制平面收敛发现

- 当前未提交改动已经跨越 V0.4.1–V0.4.5a 多个子版本，并且在 `rrc_controller.py`、gate generator/validator 和 human gate tests 中相互交织；强行按子版本拆 patch 会增加误拆风险。
- 本轮收敛按 V0.4 控制平面整体提交更稳妥：规划文档标明每个 V0.4.x 子版本状态，commit 作为 V0.4.1–V0.4.5a 的整合交付。
- `.rrc-controller-V0.2*` 和 `.rrc-controller-v0.1` 是本地运行 state-dir，应继续保持未跟踪；它们不是版本规划或产品能力交付物。
- V0.4.6 的主线仍未完成：Requirements-stage Test Strategist 和 strict non-manual AC test presence gate 仍是下一步；本轮只把 Unit Plan Test Strategist 的 fake/mock E2E 风险识别作为前置强化纳入基线。

## 2026-05-05 V0.5.2 审批摘要与 Unit Plan 输出发现

- 审批文件不需要拆附件；把摘要放在顶部、完整矩阵和原始正文放在同一 Markdown 附录区，可以同时满足人工快速审阅和现有 parser/validator 全文扫描。
- `## Controller State Patch` 仍需保持精确 heading，不能改成带前缀的附录标题，否则现有 `extract_unit_plan_state_patch()` 不能可靠定位 fenced JSON。
- Plannotator 重新审阅 approval Markdown 本身后，顶部摘要成为默认落点；`artifacts/*-body.md` 仍可保留为 agent 原始输出 artifact，但不再是人工 gate 的审阅目标。
- Unit Plan 自动预检必须发生在人工菜单之前；否则用户按 `a` 才看到 controller 可判定错误，会形成“人工已确认但 controller 又拒绝”的错误心智模型。
- compact 输出不能只按 current unit 去重；同一 unit 内从 Unit Plan 生成、预检、自动打回到等待确认也需要重新打印状态卡。
- 完整 validation error 可以进入 state 和 controller-validation artifact；终端 compact 输出只显示短原因，避免大量 AO/Journey 缺口刷屏。

## 2026-05-05 tmux-codex DONE_FILE / Working 竞态发现

- 7 号窗口现场不是 Ctrl 键卡住；底部同时出现 `Working` 和新的 `[Pasted Content ...]`，说明 Codex 仍在上一轮执行，新一轮 prompt 已被 controller 粘到排队输入框。
- 直接根因是 controller 只以 `DONE_FILE` 为 tmux runner 完成信号；Codex 可能先写 `done.json`，随后继续执行若干文件恢复、校验或总结步骤。
- 当 controller 在 Codex 仍 `Working` 时继续派发下一轮，Enter 不会表现为空闲输入框的“开始新回合”，而是进入 Codex 的队列/输入状态，看起来像“回车发不出去”或“像 Ctrl 被按住”。
- 修复边界应在 runner 层：`tmux-codex` 看到 `DONE_FILE status=done` 后仍需确认 pane 已离开 `Working`；这比要求 agent “最后才写 done”更可靠。
- compact 自动打回和阻塞信息应保留短原因，但有色模式下突出 AO/AC/Test Case/Journey/unit 等定位符，降低在长 validation reason 里找关键点的成本。
- `--color auto` 默认保持不变；在真实 tmux TTY 内会启用颜色，在捕获输出或脚本里默认保持纯文本，仍可用 `--color always` / `--color never` 显式控制。

## 2026-05-06 Unit Plan 自动打回次数决策

- 现场 V1.3 在两次自动打回后仍缺 Journey 映射而阻塞，说明 2 次默认预算对连续修复 AO、设计/架构 traceability、Journey 映射这类多层 gate 缺口偏紧。
- Unit Plan 自动打回默认预算提高到 5 次；仍保留 `unitPlanAutoRevisionMax` state 字段作为显式覆盖，避免未来需要针对单个 session 收紧或放宽时改代码。

## 2026-05-06 Unit Plan Journey 映射字段兼容

- 根因：Journey gate validator 和 Verifier Journey evidence 各自维护 `_journey_ids_from_case()`，都只识别 `journey_id` / `journey_ids` / `covers_journeys` 等字段，不识别 agent 生成的 `journey_refs`。
- 影响：Unit Plan 语义上已经把 E2E test case 映射到 active Journey，但 controller 仍判定 `journey mapping is incomplete`；即使 gate 放行，Verifier evidence 也会因同一字段不识别而漏写 `journey-evidence.json`。
- 决策：`covers_journeys` 和 `journey_ids` 仍是推荐字段；`journey_refs` / `journeyRefs` 作为历史兼容别名进入 gate validator 和 verifier evidence 识别路径。
- Prompt 和 README 必须明确：Journey 映射要写进 Controller State Patch 的 `test_cases[]` 结构化字段，不能只写在 Markdown prose、Journey Acceptance Matrix、产品设计引用或技术架构引用里。

## 2026-05-06 V0.5.3 Waygate 安装化与现场降噪

- 对外品牌、deb 包名和安装后命令统一为 Waygate / `waygate`；内部 Python package 暂保留 `workflow_controller`，避免 import 路径和历史 artifact 大规模迁移。
- deb 包采用最小安装策略：源码安装到 `/usr/lib/waygate/workflow_controller`，`/usr/bin/waygate` 通过 `PYTHONPATH=/usr/lib/waygate python3 -m workflow_controller.cli` 调用内部入口。
- Debian control 只硬依赖 `python3`；tmux、Plannotator、Codex、Claude 等外部工具继续作为运行模式的现场前置条件，不写成强制 deb 依赖，避免安装包误拉不可控工具链。
- 包构建产物 `dist/` 和 `.build/` 进入 `.gitignore`；deb 内容排除 tests、`__pycache__`、`.pytest_cache` 和 pyc/pyo。
- compact 重复状态卡的根因不是状态机重复推进，而是非渲染字段变化导致旧 key 去重失效；V0.5.3 改为再按最终渲染文本去重，保留 unit 切换和 `force=True` 的显式输出。
- `relative-artifacts/` 泄漏来自测试对相对 artifact dir 的当前工作目录假设；测试应 `chdir(tmp_path)` 后断言 runner 仍使用绝对 prompt/artifact 路径，避免污染 repo root。

## 2026-05-06 auto Claude pane 权限模式与 tmux 派发兜底

- 现场“第一次运行创建了 tmux pane、prompt 也传过去但没有回车，最后靠 idle 机制驱动起来”与 2026-05-05 的 Codex `DONE_FILE`/`Working` 竞态不同：这次发生在首次 dispatch 提交路径，prompt 仍停留在输入框。
- 现有补交机制只覆盖 `tmux-codex`；自动创建 Claude pane 走 `tmux-claude`，缺少“提交后确认 dispatch 是否仍在输入框”的保护。
- 新增通用 tmux submit retry：派发后捕获 pane，若看到 `workflow-controller dispatch.` 和当前 `RUN_ID`，或 TUI 折叠为 `Pasted Content`，则补发一次提交键。Claude 不使用 Codex 的 `agent_not_working_after_submit` 泛化分支，避免普通 idle pane 被误回车。
- 现场 Claude Code 停在 `Create file .../done.json` 确认，根因不是 `done.json` 单点，而是自动创建 pane 使用裸 `claude` 默认交互权限模式；后续任意写文件或命令都可能继续弹确认。
- 主修复应在 auto pane 启动命令：默认使用 `claude --permission-mode bypassPermissions`，并允许用 `WAYGATE_AUTO_CLAUDE_PERMISSION_MODE` 或 `WAYGATE_AUTO_CLAUDE_COMMAND` 覆盖。
- runner 层预创建同 `RUN_ID` 的 pending `done.json` 只作为防御性兜底：agent 后续更新已有完成信号文件，controller 等待循环忽略 pending，仍校验 wrong run、invalid JSON 和 post-done Codex Working 状态。
- 事件契约保持 `dispatch_started` 为第一条；新增 `done_file_precreated` 和 `done_signal_pending` 便于诊断 pending sentinel 行为。

## 2026-05-06 Requirements revision AO 污染

- V1.4.1 现场 state `<target-project>/.rrc-controller-v1.4.1` 中 110 个 `acceptanceObligations` 全部来自 `requirements:revision-1`，其中 AO-001 到 AO-012 是审批摘要和 controller 文案，AO-013 起包含旧错误需求正文，说明 AO Ledger 已被完整 requirements gate 污染。
- 根因不是 Requirements drafter 单纯没映射 AO，而是 `_revise_requirements_gate()` 把 `revision_feedback` 同时用于两件不同的事：给 drafter 的完整上下文，以及给 AO Ledger 的“真实人工反馈”。后者不应包含完整 gate 正文。
- 修复边界：完整 gate 正文继续进入 revision prompt，帮助 drafter 看旧草案；AO Ledger 只消费 Plannotator 实际反馈或 structured annotations。controller-validation-only 自动打回继续不生成新 AO。
- Plannotator 没有 structured annotations 时，会输出 `# File Feedback` 和 `## 1. General feedback...` 章节；ledger 需要按这些章节拆分，而不是把整段当成一条，也不能回退去拆 gate 正文。
- Requirements traceability 需要兼容 `AO-01` / `AO-1`，规范化为 `AO-001`；否则 agent 明明语义上映射了 AO，也会因为编号宽度不一致被误判缺失。
- Requirements resolution reason 不能用宽松 verification layer 识别来否定完整原因；`` `sdk/api/handlers` 属于旧 stream 目标。`` 包含 `api` 路径词但不是单纯的 `api` layer，因此 `AO-069 |  | out_of_scope | manual | <reason>` 应算已显式处理。
- 现有已污染 state 不应被代码修复静默改写；需要单独按当前目标决定是清理 `.rrc-controller-v1.4.1` 的 AO ledger，还是重建该 target state 后重新跑 requirements。
- 本次为恢复 7 号窗口，已选择清理 live AO ledger：备份 `session.json.before-ao-clean-20260506T050656Z`，将 110 条 `sourceRef=requirements:revision-1` 污染 AO 标为 `duplicate`，保留 approved Requirements gate 作为事实源；恢复后不再被 Requirements gate invalid 阻塞。
- 污染 AO 前提下生成的 Unit Plan 会进一步产生错误 Journey 映射；清理 AO 后必须重新 revise Unit Plan，不能沿用“覆盖 AO-001..AO-110”的污染版计划。现场已修订到 `WAITING_UNIT_PLAN_APPROVAL` 且 `blockedReason=null`，下一步只能由人审阅/确认 Unit Plan。

## 2026-05-06 Unit Plan 设计/架构 traceability ref 规范化

- V1.5 现场 state `<target-project>/.rrc-controller-v1.5` 的 Unit Plan 并没有缺少 `product_design_refs` / `technical_architecture_refs`；人工表格和 Controller State Patch JSON 都已包含对应引用。
- 根因是 validator 把 Requirements 中的 Markdown heading ref 当原始字符串比较：`` `## 7. 产品设计概要` / `PDR-01 失败诊断卡片` `` 被解析成含残留反引号的字符串，而 Unit Plan 写成 `## 7. 产品设计概要 / PDR-01 失败诊断卡片`，语义等价但字符串不相等。
- 中文顿号分隔的架构引用会进一步放大误判：`` `## 8. 架构概要` / `TAR-01...`、`TAR-02...` `` 与 Unit Plan 中两个完整 heading path 引用无法互相 subset。
- 修复边界：优先抽取并匹配稳定 trace id（`PDR-*`、`TAR-*`、`PD-*`、`TA-*`），没有稳定 id 时才使用规范化全文；这样既兼容现场 Markdown heading 写法，又不会让任意 prose 通过 traceability gate。
- 已确认源码修复后的 validator 可直接通过现场 V1.5 `requirements-and-acceptance.md` 与 `unit-plan.md` 校验；系统安装副本 `/usr/lib/waygate` 仍需有 sudo 权限才能刷新。为让现场命令立即使用修复版，已创建 `<user-bin>/waygate` wrapper 并优先加载源码工作区。
- V1.5 Journey contract 同样存在 Markdown id 规范化问题：Requirements Journey 表生成的 `journey_id` 可能带反引号（如 `` `J-01` ``），Unit Plan JSON 中的 `covers_journeys` 通常是不带反引号的 `J-01`。Journey gate 必须在 contract 和 test case mapping 两侧统一规范化 `J-*`。
- 修复 Journey id 规范化后，现场 V1.5 gate 继续前进到真实 Unit Plan 质量缺口：部分 Journey test case 的 `command` 没有逐条列入 `verification_commands`。这应由 Unit Plan revision 补齐精确命令，而不是放宽为任意 regex 推断。

## 2026-05-07 tmux-codex 显式 runner 自动发现

- V1.6 现场命令 `waygate go V1.6 --auto-approve --runner tmux-codex` 在已有 Codex pane 的 tmux session 内仍报错，说明问题不是缺少 Codex pane，而是显式 `tmux-codex` 分支没有走 pane discovery。
- 根因：`_resolve_target_agent_runner()` 在 `agent_runner == 'tmux-codex'` 且没有 `tmux_target` 时直接抛错；Claude 默认路径可自动创建 pane，显式 target 路径可检测 pane backend，但 Codex 显式 runner 缺少“发现当前 session 已有 pane”的中间路径。
- 修复边界：Codex 不自动创建新 pane，只发现已有 pane；优先选择 `pane_current_path` 等于目标 workspace 的 Codex pane，只有一个 Codex pane 时可回退使用，多个候选且无 workspace match 时保持阻断，避免错投。
- discovery 只在 `TMUX` 环境存在时启用；非 tmux 环境仍给出需要 `--tmux-target` 或可发现 Codex pane 的明确错误。
- 自动发现不能把当前 controller pane 当作目标 agent pane。现场 smoke 发现 controller 进程参数里有 `--runner tmux-codex`，如果继续用宽松 substring 检测，会把当前 pane 误判成 Codex；因此 discovery 使用 `TMUX_PANE` 跳过当前 pane，并将 agent 文本识别改为 token 级匹配，排除 `tmux-codex` / `tmux-claude` runner 名称。
- 当前 `<target-project>/.rrc-controller-v1.6/session.json` 已因手动 `--tmux-target 7.1` 继续推进；本修复面向后续不手填 target 的同类命令。

## 2026-05-07 GitHub 发布文档整理

- GitHub 默认入口应服务外部读者，而不是延续内部开发日志口吻；因此 `README.md` 采用英文简洁入口，中文完整入口放到 `README.zh-CN.md`，两者互链。
- 长篇能力说明不应全部堆在 README；CLI 用法放 `USAGE*.md`，架构和工作流放 `docs/architecture*` 与 `docs/workflow*`，路线图放 `ROADMAP*`。
- `task_plan.md`、`progress.md`、`findings.md` 是维护者历史和工作记忆，不作为用户必读文档；README 只说明它们的定位，不把它们放在主路径上。
- `.rrc-controller-*` 是本地 controller state，可能包含 prompt、artifact、路径和项目上下文；发布前必须由 `.gitignore` 忽略，不能作为 GitHub 内容提交。
- Debian 包内文档应与 GitHub 文档一致，至少包含双语 README/USAGE/ROADMAP/CHANGELOG/LICENSE 和公开 docs，避免安装用户看到过时中文单语文档。
- 本轮选择 MIT License 作为默认宽松开源许可；如果后续需要更严格的专利授权或贡献协议，可切换到 Apache-2.0 并更新 LICENSE/README。

## 2026-05-07 GitHub 发布脱敏

- `docs/superpowers/` 是本地规划/技能产物，不应作为 Waygate 公共项目文档发布；应从索引中移除并写入 `.gitignore`。
- 公开仓库中不应出现本机 venv 激活命令、用户目录、工作区绝对路径或私有目标项目路径；文档示例统一使用通用 `python -m pytest ...` 或 `<target-project>` 这类占位。
- `AGENTS.md` 和 `agent_guides.py` 是会传播到目标项目的模板，必须避免写入维护者本机路径，否则 `waygate init` 会把本地环境泄漏到新仓库。

## 2026-05-04 V0.4+ 路线图整合发现

- `AGENTS.md` / `CLAUDE.md` 应作为项目初始化规约进入 V0.4.0，但它们只定义 agent 如何工作、去哪读事实源，不能替代 requirements、acceptance、state 或 evidence。
- `CLAUDE.md` 应尽量薄，只引用 canonical `AGENTS.md`，避免多个 agent 入口文件规则漂移。
- 项目文档目录和事实源表应在初始化时生成，降低 agent 读错版本、把 progress 当需求、绕过 controller state 的概率。
- 当前 V0.3.x 已有 `golden_path` 和 closure/E2E test case，但还没有一等 Journey 模型；需要 V0.4.4 引入 Journey Acceptance Layer，解决“unit 都过但整体流程不通”的任务粒度问题。
- Journey Acceptance 应与现有 AO/AC/Test Case/Evidence 链路并行：Journey -> Requirement/AC -> Unit -> E2E command -> Journey evidence -> Final Acceptance Journey Matrix。
- Final Scope Audit 应放在 Journey Acceptance 之后，因为 scope audit 需要同时核对 AO、AC、Test Case、Journey 和 diff。
- V0.5 应聚焦执行隔离和权限，而不是继续扩展 gate 文档；否则流程约束仍停留在 prompt 层。
- V0.7 再把 `requirements.json`、`acceptance.json`、`tasks.json`、`journeys.json` 变成一等事实源，避免过早重构打断 V0.4/V0.5 的控制能力补齐。

## 2026-05-04 V0.4.0 Project Agent Operating Guide 发现

- agent guide 的工作区选择需要优先使用显式 `--workspace-dir`，其次使用 state 的 `workspacePath` / `executionWorkspacePath`，最后才退回 `state_dir.parent`；这样 `--state-dir /tmp/x/.plan-ralph` 会在 `/tmp/x` 生成 guide，而不会污染当前 repo。
- `AGENTS.md` 是 canonical 文件；`CLAUDE.md` 只作为可选 shim，避免规则双写漂移。
- 已存在 guide 文件时不能覆盖用户规则；写 `.generated` 草稿比直接合并更安全。
- `start` 也需要接入同样的 guide 配置，因为它可能在 state 不存在或 `--force` 时隐式调用 `init_state()`。
- `agentGuideArtifacts` 写入 state 可以让后续 status/debug 知道 guide 是 created、drafted、unchanged 还是 skipped。

## 2026-05-01 版本规划发现

- **V0.2 真实范围是全面架构重构**，不是 idle 行为修复（idle 修复是已完成的增量改动，属于 V0.1 后的 hotfix）。
- requirements-drafting agent 写错背景的根因：工作区没有版本规划文档，agent 从 progress.md 最近记录推断 V0.1 内容并用作 V0.2 背景，推断错误。
- `ROADMAP.md` 现已创建，后续 requirements agent 必须读取它才能正确描述版本背景。
- `composed-sleeping-dolphin.md`（OpenMAIC 课程管理项目计划）误放入 targetContextFiles，与 workflow-controller 无关，应从 V0.2 targetContextFiles 中移除。
- V0.4 的 defect_fix 路由将从"退回 Unit Plan"改为独立 bug-fix 环节（bug-fix gate → Bug Fix Agent → 验证），只有根因是架构问题时才升级到 unit_plan 路由。

## 2026-04-29 运行发现
- `.rrc-controller-v2-2` 的当前有效单元是 `v2-2-u5-baidu-search`，历史 `v2-2-u1` 到 `u4` 已完成。
- 当前 V2.2 Unit Plan 的合理形态是：只执行 `v2-2-u5-baidu-search`，但 rollup objective 可引用 `u1-u5` 表示整体 V2.2 覆盖。
- `requirements-draft` 和 `unit-plan-draft` 的历史 prompt 证明 Plannotator 多条反馈已完整进入 Claude 返工 prompt；`*-last-review.stdout.log` 只代表最近一次提交结果。
- `get_status()` 需要承担轻量状态修复职责，因为用户可能已经把旧 bug 状态写入 `session.json` 后才更新 controller。
- 最终验收缺陷的合理默认处理是 `defect_fix`：不改变 requirements，让 Unit Plan drafter 根据缺陷清单新增 `v*-fix-*` 类单元，并把受影响 objective reopen 为 `partial`。
- 测试策略最低标准：每个可执行 unit 要有行为测试用例或明确人工证据；只有 tsc/lint/typecheck 的 Unit Plan 会在 approval 阶段被拒绝。
- `.rrc-controller-v2-2/approvals/final-acceptance.md` 是 defect-fix 功能上线前生成的旧格式，`Rejection Routing` 只有 requirements/unit plan/implementation/blocked 四项；controller 必须能迁移这类已落盘 gate，不能要求用户手改。
- `artifacts/unit-plan-draft/runs/unit-plan-draft-20260429T000347849514Z/prompt.md` 已包含本轮 Plannotator feedback；因此不需要额外调整 defect-fix Unit Plan prompt 结构。
- `.rrc-controller-v3.0` 的错误 demo state 已用修复后的 `init --force` 覆盖为真实 V3.0 state：`currentStep=REQUIREMENTS_DRAFT`、`currentUnitId=target-v3-0`、`nextAction=run_requirements_drafter`。
- V0.1 完整 E2E 验收应同时证明 disabled baseline 无 Test Strategist artifacts，以及 enabled flow 的 planner -> strategist -> Critical rework -> Major/Minor gate -> summary/artifact redaction 闭环；本任务不新增 UI 或浏览器页面。

## 资源
- 新工作区：`~/works/ai-works/worktrees/workflow-controller`
- 分支：`workflow-controller`
- 初始提交：`fd27a54 Add workflow controller project`
- 测试命令：`python -m pytest workflow_controller/tests -q`
- 实际运行目录：`<local-runtime-copy>`
- V2.2 当前 state dir：`<target-project>/.rrc-controller-v2-2`

## 视觉/浏览器发现
- 本任务未使用浏览器或图片检查。

---
*每执行2次查看/浏览器/搜索操作后更新此文件*
*防止视觉信息丢失*
