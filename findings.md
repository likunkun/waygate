# 发现与决策

## 2026-05-25 Unit Plan AC 证据闭环预检

- `verification_assist` 是辅助验证形态，不能在 Unit Plan 阶段静态替代 Final Scope Audit 可计数的 AC coverage；它可能产出 `needs_human_review`，而 Final Scope Audit 只接受 `passed` 或带有效 manual evidence 的 `manual` evidence row。
- Unit Plan gate 需要同时检查单个 test case 的 exact command 合同，以及 approved Requirements AC id 是否至少有一个 final-valid evidence candidate。有效 candidate 是精确匹配 `verification_commands[]` 的 command case，或显式 manual layer / `evidence_type=manual_evidence` 且带具体 manual evidence 的 manual case。
- 如果 approved AC 只有 `verification_assist`、弱 manual note 或没有映射 test case，应在 Unit Plan preflight 阶段阻断，并指向具体 AC 与 test case；不要等到 Final Scope Audit 才暴露缺口。

## 2026-05-24 Final Acceptance 人工批准优先

- Final Acceptance gate 已经位于 verifier、scope audit、journey/prototype/real E2E/document deliverable 和 walkthrough entrypoint 预检之后；到人工 gate 时，人工批准应是最终验收决策本身。
- 人工系统观察记录可以继续作为审阅上下文和审计记录，但不能在人工点击 Approve 后再作为硬门槛阻止验收。否则 Plannotator / CLI 的批准语义会被一个空字段覆盖，等同于限制人工最终判断。
- Controller 仍保留最终验收前置 deterministic evidence 检查；本次只取消“人工观察记录必填”对最终批准的阻断，不允许跳过 verifier 或 pre-human gate checks。

## 2026-05-24 Annotation Agent 人工 Gate 顺序

- Annotation / verification-assist 批注的边界是“人工确认前的风险上下文”，不是人工确认后的补充步骤。用户已批准的 gate 应先按 approval file 和 deterministic validator 推进状态，不应再启动 annotation Agent。
- Unit Plan 修订路径必须与正常 Unit Plan drafter 路径保持同一 gate ordering：controller preflight 通过后先运行 `unit_plan_annotation`，再暴露给人工 gate；否则人工看到的 approval Markdown 可能缺少风险批注。
- `check_requirements_acceptance`、`check_unit_plan_approval`、`check_final_acceptance` 只在 gate pending/stale 时做 annotation freshness 检查。已 approved gate 缺少 fresh annotation artifact 是历史审计缺口，不应阻塞或延迟已提交的人工作业。

## 2026-05-24 Verification-Assist Agent 语义修正

- `verification-assist Agent` 不是终验批注 Agent 的同义词。批注角色继续只提供 risk-only context；`verification_assist` 是 Unit Plan test case 显式选择的一种验证执行方式。
- `descriptive_command` 与 `agent_assisted_case` 必须分开：前者仍执行命令，Agent 判断不能覆盖命令 exit code 或 deterministic evidence policy；后者不执行命令，Verifier 依赖 assist artifact 的 structured judgement 形成该 test case 的 evidence row。
- `agent_assisted_case` 可以作为 controller evidence，但不能批准 gate。默认 `human_review_required=true`，Final Acceptance 仍必须通过 human confirmation、manual observation 记录和 controller transition。
- 默认复用 `final_acceptance_verification_assist` 作为 backend 是兼容配置选择，不表示该 Agent 只在终验阶段做 annotation；文档和 prompt 必须说明它也可作为显式 verification-assist test case backend。
- Golden path E2E 可以使用 `verification_assist` 替代命令，但仍必须保留 `layer=e2e`、真实环境、真实入口、fixture/setup、强 expected assertion，且不得使用核心 API mock/stub。

## 2026-05-24 Annotation Agent 可见性与新鲜度

- Annotation agent 是 controller-side subprocess，不是 tmux builder/reviewer/drafter pane 内的可见任务；因此运行状态必须由 controller pane 输出紧凑生命周期行，而不是期待用户在目标 agent pane 看到活动。
- Annotation stdout/stderr 可能包含模型诊断、环境噪音或敏感上下文，只能继续 capture 到 artifact/event 的受控字段；终端只显示 role、backend、artifact、returncode、elapsed 和错误摘要。
- Annotation artifact 必须绑定当前 gate body 的 `gate_content_hash`。Requirements gate 内容变化后，旧 artifact 只能作为历史审计证据，不能当作当前人工 gate 的有效标注。
- Annotation artifact 的人类可见批注必须是简体中文。`summary`、`issues[].message` 和 `non_approval_statement` 这类字段面向人工审批，不能依赖英文模型输出；taxonomy key、AC/AO/Journey id、文件路径和命令可保留原文。
- `human_language=zh-CN` 是当前 annotation artifact 的有效性标记之一。旧 artifact 即使 gate hash 匹配，但没有语言标记，也不能作为当前人工 gate 的有效标注，需要重新运行 annotation。
- 当前 fresh annotation artifact 会以固定边界块写回同一个 approval Markdown，位置在 `## Human Confirmation` 之后，因此不改变 `gate_body()` 或 approval content hash；重复进入 gate 时替换旧块，stale artifact 或非 `zh-CN` artifact 会移除旧块且不展示为当前批注。
- Requirements 人工修订和 unblock/check 恢复路径都必须在进入人工确认前重新确保 annotation fresh；annotation runtime 失败仍是 `annotation_runtime` blocker，不应引导用户修改 Requirements 合同。

## 2026-05-24 Annotation Agent CLI 后端兼容性

- Annotation agent 后端命令兼容性属于 runner/runtime blocker，不是 Requirements、Unit Plan 或 Final Acceptance 合同失败。`requirements_annotation annotation pass failed before human gate` 这类错误不能引导用户修改 Requirements 文档。
- Codex CLI `0.133.0` 的 `codex exec` 已不接受旧参数 `--ask-for-approval never`。Waygate 内置 `--annotation-agent codex` 模板改为 `codex exec --sandbox workspace-write -o {artifact_path} ...`，继续保持非批准型 risk-only artifact 语义。
- 已写入旧 session 的 Waygate 内置 Codex annotation args 需要在 runtime/config normalize 路径自动归一化；但用户通过 `--annotation-agent-cmd` 自定义的命令属于操作者显式配置，不能被 Waygate 猜测或改写。
- Annotation runtime blocker 修复后应通过 `waygate unblock --state-dir <state-dir> --reason "<fixed annotation runtime condition>"` 重新执行 pending annotation，再进入真实人工 gate；不应要求用户做 Requirements revise。

## 2026-05-24 Final Acceptance 人工系统观察记录

- Final Acceptance 的人工批准对象不应只是 Markdown gate 或 Plannotator 文档审批；gate 必须展示真实系统入口、自动化证据和人工可参考的观察记录位置，方便人工做最终判断。
- Controller 不负责猜测真实入口。Unit Planner 必须在 `final_acceptance_walkthrough.inspection` 中声明 `surface_kind`、`entrypoint`、`manual_steps` 和 `expected_observations`；Builder 如果实现后入口变化，必须在 DONE payload 中确认最终入口和原因。
- 自动化 verifier、golden path 和 launch artifact 是终验前置证据。Final Acceptance gate 需要展示 `## Agent 提供的人工走查入口`，并在 `## 人工系统观察记录（Review Notes）` 中提供 observed entrypoint、actual observation、data/account/fixture 和 issues/evidence path，作为审阅上下文和审计补充。
- `waygate approve --gate final-acceptance` 与 Plannotator Approve 走同一条 controller 校验路径；人工一旦批准，空观察记录不再阻断 Final Acceptance。

## 2026-05-23 Builder blocked artifact 复阻塞

- Builder `status=blocked` artifact 是有效阻塞事实源，但只对对应 Builder run 有效。人工 `unblock` 表示该外部条件已处理，Unit Plan 重新批准表示上游执行合同已更新；之后不能再用同一个旧 `builder-summary.json` / run_id 把 workflow 复原到 blocked。
- 正确边界是记录已处理的 Builder blocked context key（unit + run_id，缺 run_id 时退回 artifact path/summary），让同一个旧 artifact 不再参与 reconciliation；新的 Builder run 会产生新的 run_id，仍可正常进入官方 blocked state。
- 现场 V0.1 证明，仅修改 Unit Plan 为 localhost 默认值不足以推进：旧 artifact `target-v0-1-20260523T111412138716Z` 仍被 `get_status()` 反复读取，导致 controller 还没重新派发 Builder 就再次 blocked。

## 2026-05-23 Waygate 停止状态原因化引导

- `retry` 的语义必须保持窄边界：只清除 timeout / idle / pending agent silence 形成的 `recoverableAgentWait`。显式 `blocked` 代表 agent 或 controller 已给出阻塞判断，不能被普通 retry 清掉。
- 环境/外部依赖类 blocked 与合同类 blocked 需要不同路由。缺生产只读 URL、Docker/Compose/Playwright、端口、服务、凭据、权限、DB/API 等应先人工修环境，再用 `unblock` 表示外部条件已修好；Unit Plan 或 Requirements 合同不可执行时必须走对应 `revise` gate。
- `unblock` 不是审批，也不是需求/计划变更。它只清除 blocked 状态并重新计算当前阶段 next action；Requirements、Unit Plan、Final Acceptance gate、approval hash 和 artifacts 必须保留。
- Builder DONE payload 的 `status=blocked` 是 controller state 的事实源，不应只停留在 `builder-summary.json`。Controller 必须把它 reconciliation 成官方 `status=blocked/currentStep=EXECUTE_UNIT/blockedReason=<summary>`，这样 `status`、`unblock` 和 `revise --gate unit-plan` 都有一致入口。
- 停止输出需要把“原因、下一步、命令”放在用户当下可执行的位置；自然语言总结不能替代可复制命令，也不能把 timeout retry 与 blocked revise/unblock 混为一谈。

## 2026-05-23 Annotation Agent 环境可用性风险标注

- Annotation agent 的职责是把人工批准前容易忽略的外部环境假设显式标注出来，不是把这些风险升级为新的审批者或自动阻断器；Requirements / Unit Plan / Final Acceptance 的批准语义仍只来自原 gate、controller transition 和必要的 verifier evidence。
- `production_readonly` 不能由本地 `127.0.0.1`、localhost preview 或只声明 env key 代替。若当前验收真的需要远端只读环境，Unit Plan / verifier evidence 需要真实外部入口，例如 `PRODUCTION_WEB_BASE_URL` 或 `PRODUCTION_API_BASE_URL`；没有部署环境时应走正式 Requirements / Unit Plan 变更、延期或 manual blocked 路由。
- Docker、Docker Compose、Playwright/browser、端口、数据库、缓存、外部 API 和服务依赖属于运行环境可用性事实。Controller deterministic preflight 能检查一部分结构字段，但 annotation prompt 应在人工 review 前提醒 agent 标注“计划假设存在但未证明可执行”的剩余风险。
- `verification_env` 只保存 key 名称，不能证明 value 存在、服务可达、生产环境已部署或端口可用；标注 Agent 只能提示 `verification_env_gap` / `runtime_dependency_gap`，不能把 env key declaration 当作验收证据。

## 2026-05-23 Final Acceptance Guided Launch Walkthrough

- Final Acceptance 的事实边界应是“自动化验证已通过后的人工真实入口走查”，而不是让人工只看泛化检查清单。启动状态、ready check、真实入口、fixture/test data、user steps、expected 和人工观察必须在 gate 中可见。
- Unit Plan 是声明最终走查启动方式的正确位置：它已经确定 closure unit、golden path、verification commands 和真实入口，controller 不应从 README、package scripts 或其他项目文件猜启动命令。
- `agent_start` 启动失败不代表可以跳过 Final Acceptance，也不代表实现一定失败；它应形成可审计 launch artifact，由人工在 Final Acceptance gate 中选择 blocked、implementation、unit_plan 或其他既有返工路由。
- `env_keys` 只能保存环境变量名。把 token、DATABASE_URL、password 或 API key 值写入 Unit Plan state、artifact 或日志会扩大 secret 泄露面，因此 validator 应在人工批准 Unit Plan 前阻断。
- `manual_only` 和 `not_required` 仍需要形成明确 gate 说明；否则人工会回到临时口头说明，无法审计 Final Acceptance 入口和观察记录。

## 2026-05-22 V0.6.0m Golden Path E2E 前置校验

- `golden_path: true` 表示最终验收主路径，不应由 `unit`、`integration`、`manual` 或 mock/contract 测试承担；否则 Final Acceptance 才暴露 evidence row 非 E2E，会把可在 Unit Plan 阶段发现的问题推迟到验收末端。
- Unit Plan approval 是阻断错误 golden path 的正确位置：它已经拿到结构化 `test_cases[]`、`verification_commands` 和 Requirements 4.6 E2E 审阅结果，可以在人工批准前暴露 layer、environment、real entry、mock policy、fixture/setup、command 和 assertion 缺口。
- E2E 的语义是跨真实入口验证业务主路径，不等于必须使用浏览器。UI/Web/prototype golden path 通常需要 Playwright/browser E2E；API-only 或 service-only 项目可以用 pytest/API/service E2E 调真实 API/service endpoint。
- `workflow_validation_level=closure` 只能说明单元承担闭环验收责任，不能替代 test case 的 `layer=e2e`。Requirements 中声明 E2E 的 AC 或 active Journey 必须在 Unit Plan 中映射到真实 `layer=e2e` test case。
- Final Acceptance 的 real E2E evidence gate 仍保留为最后防线，用于阻断 evidence row 中非 E2E、缺真实入口、核心 API mock、非真实环境和 runtime errors；人工同意不能绕过该 evidence gate。

## 2026-05-22 Recoverable Agent Timeout / `waygate retry`

- Agent 超时、pane idle 但未写 DONE、或用户暂时无响应，属于 runner 层 transient wait，不是 Requirements 或 Unit Plan 合同错误；把这种情况置为 `blocked` 会迫使用户错误地用 `waygate revise` 修改上游 gate。
- 可恢复等待的状态边界是：保持原 stage、`status=active`、清空 `blockedReason`、记录 `recoverableAgentWait` 和事件，并停止自动 loop。Requirements、Unit Plan 和 Final Acceptance approval 不应被失效。
- `waygate retry` 只表达“允许同一阶段再次尝试/接回 pending run”，不能隐式修改 requirements、unit plan、approval gate 或 artifact；真正的合同返工仍只能走 Requirements / Unit Plan revise 或 Final Acceptance rejection routing。
- 只有 runner status `timeout` 与 `agent_idle_without_done` 纳入 recoverable wait。Agent 显式 `blocked`、controller validation failure、verifier 环境错误、重复失败阻断和 Final Acceptance blocked route 仍然应保持真实 blocked 语义。
- Subprocess `TimeoutExpired` 需要归一化为 `status=timeout` / `returncode=124`，否则 subprocess runner 会绕开 recoverable wait 语义并表现为未捕获异常。

## 2026-05-22 Requirements-stage E2E 前置审阅门禁

- 真实 E2E / 浏览器验收的测试方法、真实入口、fixture/setup、命令依赖、环境类型、mock policy 和断言意图必须在 Requirements 人工批准前暴露；否则 Unit Plan 才发现缺口时，人类已经批准了不完整的验收合同。
- 触发条件必须只看真实 AC、active Journey、Test Strategy 或明确 Web/原型/UI 合同内容；模板指导文本不能单独触发 4.6 或 prototype manifest 要求。
- 当文本要求 E2E 但没有 e2e AC 或 active e2e Journey 时，正确修复不是只补一张 4.6 表，而是先把 E2E 审阅映射到具体 AC 或 Journey。
- `environment_kind` 在 Requirements 4.6 阶段只接受 `local_real` 和 `production_readonly`；`component_mock` / `contract_mock` / `visual` 仍只能作为后续 Unit Plan 的辅助非 E2E 测试语义。
- 截图和人工观察只能作为辅助 artifact；Expected Assertions 必须包含 DOM/API/数据库/状态/数量/排序/权限/导出内容等可机器断言的具体期望。

## 2026-05-21 Unit Plan 自动打回连续原因计数

- Unit Plan 草案预检自动修订预算应与 Requirements 保持同一语义：风险点是同一个 controller invalid reason 被反复修不掉，而不是一轮 Unit Plan 内出现了多个不同缺口。
- `unitPlanAutoRevisionMax` 继续保留默认 5 和 state 覆盖机制，但语义调整为连续相同 reason 的最大自动修订次数；reason 变化时连续计数重置。
- `unit_plan_draft_auto_revision_requested` 的 `attempt` 表示当前 reason 的连续 attempt，`total_attempt` 表示本轮 Unit Plan 草案累计自动打回次数；`controller-validation-error.json` 的 `attempt` 同样记录当前 reason 的连续 attempt。
- 相同 reason 连续超过上限仍会进入 `unit_plan_draft_auto_revision_blocked`，blocked event 同时记录 `consecutive_attempts` 和 `total_attempts`，避免 drafter 在同一错误上无限循环。

## 2026-05-21 V0.6.0k UI/UX Skill Policy

- UI/Web/prototype、可点击原型、prototype evidence 和生产 UI 一致性工作需要稳定使用 `ui-ux-pro-max`；把 `frontend-design` 当成等价 skill 会让既有产品 UI/原型一致性工作退回到泛视觉探索，削弱 route、DOM/组件、交互、可访问性、布局和遮挡检查。
- `frontend-design` 的边界保留为全新视觉探索或局部视觉润色辅助；它不能替代既有产品 UI、prototype conformance、production UI consistency 或 prototype fidelity 工作。
- UI/原型设计前必须先盘点真实 UI 事实源：route、DOM/组件、既有页面结构、截图、历史设计或参考环境。只根据 prose 设计原型不足以证明既有产品一致性。
- `waygate doctor` 的 `ui_ux_design` 推荐项应以 `ui-ux-pro-max` 为 required/ok 匹配；只安装 `frontend-design` 时输出 warning/manual action，避免环境诊断误导 agent 认为技能已经满足。
- V0.6.0k 只收敛 skill policy，不回滚 V0.6.0j 和 Controller Prototype Fidelity Gate 的 L1-L4 视觉证据规则。

## 2026-05-21 Controller Prototype Fidelity Gate

- UI/Web prototype conformance 的默认验收边界应是 L1 visual evidence + L2 structural/interaction，而不是像素级一致；这样能防止“页面差很多但 route/text E2E 通过”，同时避免把需求期 HTML 原型误当成高保真设计稿。
- L3 screenshot regression 和 L4 pixel exact 只应由 Requirements、prototype manifest 或 test case 显式声明触发；品牌 Logo、固定尺寸组件和高保真设计稿可升级到 L4，普通业务页面不默认承担像素级门槛。
- Unit Plan 是视觉证据计划的入口：prototype conformance test case 必须声明 prototype screenshot、production screenshot、viewport、entrypoint、action path，交互 surface 还要有 interaction screenshot；`expected` 必须覆盖布局/结构/顺序和真实点击后的交互，而不是 route/text visible。
- Verifier 的 `visual_evidence_refs` 是终验事实源，Builder summary 或自然语言截图说明不能替代。stdout/stderr marker 让 Playwright 等 E2E 命令把截图路径和 action path 结构化写入 `verification.json`。
- Final Acceptance 必须把每个 surface 的 visual evidence 展示出来供人工审阅；`passed` 状态本身不能证明原型一致，缺 prototype/production screenshot、缺 action path、交互截图缺失、目标被 overlay/fixed header 遮挡或显式 L3/L4 缺回归结果都应阻断。

## 2026-05-20 Controller Verifier 失败后的 Builder 精确复现闭环

- Controller Verifier 的失败命令是下一轮 Builder 调试的事实源；Builder 自测通过不能替代 controller 上一轮 failed command 的复现记录。
- Builder prompt 需要把 failed command index、exact command、controller cwd、returncode、`verification.json` 路径、env keys 和输出 tail 放在同一个协议段中，避免 agent 只跑相邻测试或修改后的命令。
- `done_payload.controller_failure_resolution` 是 Builder 完成契约的一部分：`failed_command` 必须与上一轮 `lastFailure.details.command` 完全一致，并记录复现、根因或环境差异、修复、同命令复跑和完整 approved verification list 结果。
- 缺少该结构化证据时继续进入 Refiner/Reviewer 会掩盖 controller verifier 失败，因此 controller 应在 Builder 阶段直接阻塞，暴露“Agent did not reproduce controller failed command”。
- 重复失败 fingerprint 不应使用完整 stdout/stderr tail；耗时、retry 行、ANSI 或上下文 tail 波动不应绕过重复失败阻断。稳定判定应基于 stage、issue type、command、returncode 和 Playwright title / error class / timeout 等失败特征，tail 只用于人类和 agent 排查。

## 2026-05-20 Plannotator remote env 与 controller preview 固定端口

- Plannotator 的远程访问开关应由 `PLANNOTATOR_REMOTE=1` 表达；Waygate 不再通过 bind host 环境变量控制 Plannotator 的监听地址。
- Waygate 仍负责传入 `PLANNOTATOR_PORT=<port>`，并继续用本机主 IP 或 `WAYGATE_DISPLAY_HOST` 生成浏览器可打开的审批 URL。
- Controller prototype preview server 是 Waygate 自己控制的监听服务；默认固定为 `20001` 端口，便于提前申请 ACL。`WAYGATE_PREVIEW_PORT` 只改变监听端口，`WAYGATE_DISPLAY_HOST` 仍只改变展示 host。

## 2026-05-20 Plannotator / prototype preview URL 主 IP 展示

- `0.0.0.0` 是服务监听地址，不是稳定的浏览器访问目标。终端输出 `http://0.0.0.0:<port>` 会让用户点击后打不开页面，因此不能再把 wildcard bind host 当作 display host。
- 正确边界是 bind host 和 display host 分离：controller preview server 可继续绑定 `0.0.0.0` 以支持远程访问；Plannotator 远程访问由 `PLANNOTATOR_REMOTE=1` 请求；终端展示、summary artifact 和 event payload 中的 browser URL 应使用本机主 IP 地址，或使用 `WAYGATE_DISPLAY_HOST` 显式覆盖。
- 主 IP 推导使用 UDP outbound route 获取本机 IPv4 地址；这不需要真实发送应用数据包，但能匹配当前机器访问外部网络时使用的主要网卡地址。无法推导时才退回 loopback。

## 2026-05-20 V0.6.0j Requirements 基础设施追问友好化

- Requirements prompt 需要区分“对用户怎么问”和“agent 必须怎么留痕/验证”。用户追问应使用分组引导式文案，允许用户先回答知道的部分；controller 规则词和门禁术语只应作为 agent 内部约束，不应原样出现在用户问题里。
- 基础设施事实的体验优化不能削弱 preflight：`## 4.9` 仍必须记录具体事实、事实来源和验证状态；“用户确认”或“已验证”仍必须能在 `## 4.8` 中找到对应问答、核对方式和验证结论。
- 友好追问的默认信息架构固定为三组：代码与运行、调试与资料、参考与依赖。这样能减少一次性 7 类清单的压迫感，同时仍覆盖现有 4.9 分类。

## 2026-05-20 V0.6.0j Requirements 基础设施追问与验证

- 无 `--spec` Requirements intake 的第一轮澄清仍应保持用户友好：agent 第一条回复只问问题，不读项目、不写 gate；但用户给出具体回答后，agent 必须读取项目上下文并盘点 4.9 基础设施缺口。
- 4.9 基础设施事实不能只依赖用户自然语言补充。代码仓库、运行环境、调试入口、参考环境、文档、接口和依赖需要优先通过本地 repo、配置、README/USAGE、docs、state-dir artifact、package manifest、测试命令等非破坏性来源核对。
- 外部系统、生产环境、私有 wiki/API 和无法访问的参考环境不能伪造验证结论；可写“用户提供，未能直接验证”，但必须说明无法验证原因，并在人工审阅时暴露风险。
- 4.8 是基础设施追问与验证留痕位置：当 4.9 声称“用户确认”或“已验证”时，4.8 必须有对应问答、核对方式和验证结论，否则 controller preflight 应阻断。
- `未发现` / `没有` / `不涉及` 不是天然有效事实。可接受写法必须包含已检查来源、4.8 中的用户确认问答，或具体不涉及原因。

## 2026-05-20 V0.6.0i 文档生命周期

- `docs/README.md` 承担当前阶段的文档入口和轻量登记表职责；暂不拆 `docs/document-registry.md`，避免在登记规模尚小时增加维护面。
- `task_plan.md`、`progress.md`、`findings.md` 继续作为过程、进度和决策事实源；正式长期产品、架构、流程、运维内容应沉淀到 `docs/*`，不能只停留在过程文档里。
- `.rrc-controller-*` 目录是审计证据和 gate/artifact 事实源，不应被当作长期文档入口；需要长期引用的外部 Agent 文档或 artifact 应先在 `docs/README.md` 登记，再决定是否提升到正式 docs。
- Unit Plan 的 Document Deliverables Matrix 是本轮文档动作事实源；Final Acceptance 只阻断 `Required For Acceptance = true` 的文档 deliverable，避免历史 backlog 文档缺口误伤当前 unit。
- Requirements `文档地址` 只写 `docs/`、`README`、`USAGE` 或 `暂无` 过于空泛；可接受写法必须说明正式维护文档、过程证据、外部来源和缺失文档的用途或可信度。

## 2026-05-19 V0.6.0h tmux 推荐配置与 Doctor 信息层级

- `waygate doctor` 的 tmux 配置检查必须保持只读；它只能报告 `found/missing/ok/warning` 和 manual action，不能自动写入 `~/.tmux.conf`，也不能 reload tmux。
- 推荐 tmux 配置本轮固定为 `mouse on`、`history-limit 100000`、`@scroll-speed 5` 和 `@copy-mode-vi 'on'`；其中 `@copy-mode-vi` 继续按自定义 option 检查，不替换成 tmux 标准 `mode-keys vi`。
- Doctor 只读取 `HOME/.tmux.conf`，解析 `set -g key value` / `set-option -g key value` 和简单引号值；同一 key 多次出现时，后出现的有效配置为准。
- 为避免泄露本机配置或 secret，`tmux_config` 只输出推荐 key 的 expected/actual，不输出整份 `.tmux.conf`，也不输出无关配置行。
- CLI 在非 TTY 和 `--color never` 下仍保持纯文本；本轮 UI/UX 改进落在信息层级与终端高亮上：顶部 `summary:`、`focus:` 和 `action_required:` 放状态、优先关注项与人工处理事项，既有详细 section 保留在后面，兼容用户排障习惯。
- `waygate doctor --color auto|always|never` 只改变 ANSI 展示，不改变诊断语义；`auto` 仅在 TTY 启用颜色，避免污染日志、管道和测试快照。

## 2026-05-19 V0.6.0g Doctor / 远程审阅可达性

- `.rrc-controller-v0.6.0f/session.json` 当前仍是历史遗留 active state；它不能被手工改成 DONE 来制造 gate/state transition。V0.6.0f 收尾只记录在人类可读项目记录、CHANGELOG/ROADMAP 和真实验证证据中。
- README 推荐基线中包含 `frontend-design` 或 `ui-ux-pro-max`，因此 doctor 推荐组如果声称与 README 对齐，就必须覆盖 UI-heavy requirements 这一组；只覆盖 workflow 类 skills 会造成文档与诊断分叉。
- `.claude` 不是通用 skill root；doctor 只应把 `~/.claude/commands`、`agents`、`rules`、`plugins` 当作 Claude runtime assets 做路径/状态/数量检查，不能递归读取 cache、file-history、token、配置内容或环境变量值。
- Controller prototype preview 绑定 `0.0.0.0` 能提升远程审阅可达性，但 `0.0.0.0` 本身不是远程浏览器应直接使用的主机名；文档和终端输出必须提醒用户通常要替换成运行 Waygate 的机器 IP 或 hostname。
- Plannotator 的 bind 行为不再由 Waygate 的 host env 控制；Waygate 只传 remote 开关和端口，并负责展示可打开的审批 URL。

## 2026-05-19 `waygate doctor` skills 诊断

- Skills 诊断应保持全局环境视角，不绑定当前 `session.json` 或 unit；这样 `waygate doctor` 可用于安装/排障前置检查，而不会把当前 workflow scope 误当作全局事实。
- `SKILL.md` 文件存在只能证明本机常见 skill 根目录可读，不能证明某个 Claude/Codex/OpenCode runtime 在当前会话中一定会加载该 skill；因此 skill 缺口输出为 warning/manual action，不让 `doctor` 失败。
- 推荐 skill 组按 Waygate 常用 workflow 能力表达：startup、planning、requirements、builder TDD、debugging、test strategy、refiner 和 verification。`test-strategy` / `testing-strategy` 作为等价候选处理。
- Agent runner 可用性仍依赖 `PATH` 中的 `claude` 或 `codex` CLI；`waygate doctor` 保持为 CLI 环境检测和 skills 检测。
- 非 CLI 本地应用条目不属于 runner readiness 事实源；`doctor` 不应扫描或输出这类条目。

## 2026-05-17 Requirements Plannotator 主审批对象

- Requirements approval 的唯一事实源必须是 `approvals/requirements-and-acceptance.md`；`plannotator-review.html` 是原型渲染辅助预览页，不能成为 Plannotator gate 的主 annotate 目标。
- Controller 可以在 Requirements review 期间启动临时 preview server，并把 `prototype_review_preview_url` 写入 `requirements-last-review.json` 和 event payload 供当前会话排查；但该 URL 绑定临时端口，不能注入持久 approval 文件。
- Requirements Plannotator metadata 应同时记录 `approval_gate_path`、`review_path/full_path` 和辅助 `prototype_review_path`：前者用于审批事实源校验，后者用于说明当前 review session 的原型预览入口。
- 旧的“存在 bundle 就把 HTML 传给 Plannotator”会让 approval 语义被渲染视图顶替；修复边界应放在 controller review path 选择和 preview server 启动条件上，不改 prototype bundle 生成逻辑。

## 2026-05-17 基础设施 intake 与安装来源一致性

- 基础设施 intake 是 Waygate 处理目标项目的通用 Requirements 约束，不应由目标版本号触发；只在 V0.6.0 prompt 中注入会导致 V1.8.4 等真实目标项目缺少仓库、运行时、调试、参考环境、文档、架构/接口和依赖事实。
- Requirements preflight 必须把 `## 4.9 目标项目基础设施信息` 当成硬门禁；缺失、缺类别、空内容和 TBD/待补/不清楚这类占位都不能进入人工确认。允许写“不涉及”，但必须附具体理由。
- validation-only revision 不能只修 prototype/Journey/AC 等当前错误后绕过基础设施事实；同一 preflight 路径需要重新检查 4.9，确保修订后的 gate 仍完整。
- `WAYGATE_VERSION` override 会让 Debian control `Version` 与包内 `workflow_controller.__version__` 分叉；build script 应直接拒绝不一致，而不是构建一个 `waygate --version` 与 dpkg version 不同的包。
- `/home/lichangkun/.local/bin/waygate` 位于 `/usr/bin/waygate` 前时会 shadow DEB wrapper。Debian postinst 和 `waygate doctor` 只警告，不删除用户文件；现场清理应在确认新包已安装后由人工改名或删除并执行 `hash -r`。
- 本轮尝试安装 `dist/waygate_0.6.0c_all.deb` 时 sudo 需要交互密码；因此未执行系统安装、未移动 `.local/bin/waygate`，也未对 proxy-collector V1.8.4 live state 进行 Requirements revision。

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
