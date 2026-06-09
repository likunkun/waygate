# 变更日志

重要项目变更应记录在这里。

## 0.6.2j

- 将 Annotation Agent 产品合同保真审查增强打包为 `0.6.2j`。
- 增加人工 gate 前 advisory risk-only annotation 覆盖，用于提示产品合同保真、信息衰减、产品字段映射缺口和 out-of-scope 边界风险。
- 该 annotation 增强不新增 deterministic validator、state schema 字段、CLI 参数、审批来源或 hard gate。

## 0.6.2i

- V0.6.2i 是 staged Requirements prompt 与正式文档合同的 prompt-only 版本。
- 新增 prompt-only 的 Requirements 验收前置 intake 文案：无 `--spec` 会话必须先确认当前版本目标、非目标、验收重点、成功/失败证据和范围边界，不能在用户回答前直接起草或缩小范围。
- 强化 Product Design prompt 合同：每个 UI/Web/prototype surface 都必须是 1:1 用户任务原型，写明 actor、任务起点、点击路径、页面状态、主业务对象、成功终点、AC/Journey 映射和 production target。
- Unit Plan、Builder、Test Strategist 和 Refiner prompt 增加 Product Journey Contract 交接文案，要求 `主业务对象血缘拆分矩阵`，并明确 fixture、工程层、截图或 prototype artifact 不能替代产品旅程闭环。
- 同步正式 workflow/architecture 文档、README/USAGE、路线图、docs registry 和 package version metadata 到 `0.6.2i`；不新增 deterministic validator、state schema 字段、CLI 参数或 hard gate。

## 0.6.2h

- 修复 Requirements Test Strategy 4.6 解析：validator 只消费 canonical 固定列 E2E 矩阵块，不再把后续 subsection 表格（例如 4.7 AC closure matrix）当作 4.6 obligations。
- 新增 staged Requirements 回归测试，覆盖有效 11 列 4.6 矩阵后跟 5 列 4.7 closure 表且包含同一 E2E AC 的场景。
- 同步 staged Requirements workflow / architecture 文档、release notes 和 package version metadata 到 `0.6.2h`。

## 0.6.2g

- Product Design prompt 增加三条分支：无 spec 时在同一 tmux conversation 使用 brainstorming 并逐页/逐入口确认；有 supported spec 时保持兼容 staged artifact flow；backend/API/CLI-only 时基于 Scope 正向依据做一次 no-UI/no-prototype 确认。
- 移除 annotation 专用 tmux pane runtime。Annotation pass 现在始终使用 subprocess；`WAYGATE_ANNOTATION_TMUX` 作为废弃 no-op 被接受但不再创建 pane、run-local wrapper、run id 或 `done.json`。
- 移除 Claude Code annotation backend。声明式 annotation backend 仅支持 `opencode` 和 `codex`；已有 session 中的 Waygate 内置 Claude annotation 配置会迁移为内置 OpenCode 模板。Claude Code 仍可作为普通 `tmux-claude` workflow runner 使用。
- 强化 env key-only audit metadata，state、events、summaries、artifacts 和 captured output 只记录 key 名，不记录 env value、token、database URL value、password、secret、`api_key`、signature 或 proxy value。
- 新增 V0.6.2g `scripts/verify/` 脚本入口，并同步正式 workflow、architecture、usage、release 和 roadmap 文档；V0.6.3 Strict Test Presence / Per-Role Runner Configuration 继续作为后续范围。

## 0.6.2f

- Plannotator approve payload 中的 Requirements / Unit Plan approval notes 会以 audit-only advisory context 持久化，并在下一阶段 prompt 的 `Approval Notes Non-Contract Context` 中注入。
- 人工 gate menu 新增 `i` 与 `m`：`i` 只根据 review notes 生成 pending draft；`m` 只在正文 hash 已变化、存在 reason 或 notes、deterministic validator 通过时采纳人工已编辑正文。
- 自动执行中的 Ctrl+C 会进入可审计 `blockedContext.category=human_interrupt` 状态，记录 tmux `C-c` best-effort 结果并展示恢复 guidance。
- CLI review route 拆分：`waygate approve --reason` 走受控 manual adoption；`waygate revise` 无 reason 回到当前 approval point；checkpoint revise 继续要求 `--reason`。
- 新增 V0.6.2f review bundle 与 prototype conformance evidence，覆盖 approval notes、draft merge、manual adoption、interruption recovery、revise routes、legacy review compatibility 和真实 Waygate target mapping。
- README/USAGE/CHANGELOG/ROADMAP、正式 workflow/architecture 文档、verification scripts 和 package version metadata 同步到 `0.6.2f`，并保持 V0.6.3 Strict Test Presence / Per-Role Runner Configuration 为后续范围。

## 0.6.2e

- 新增 `open-spec-package` intake，支持包含 `01-requirements.md` 且至少包含一个支撑文档的 Open Spec 文档包目录。
- 扩展 Spec Kit feature package 识别：任意目录只要 `spec.md` 同目录有 `plan.md`、`tasks.md` 或 `contracts/` 等 feature artifact，即可导入。
- `.specify` 工具/工作区根目录和普通 docs 目录会被拒绝，并提示传入 `specs/<feature>/` 或具体 `spec.md`。
- package directory 导入会生成 conversion artifacts，并在 `import-summary.json`、`source-map.json` 和 `validation-report.json` 中记录 package entrypoints。
- 同步 Requirements prompt/brief、README/USAGE、workflow/architecture 文档和 package version metadata 到 `0.6.2e`。

## 0.6.2d

- 新增 Unit Continuity Gate：多单元 Unit Plan 必须包含 `单元连贯性摘要`、Handoff Matrix，以及结构化 `depends_on` / `handoff` metadata。
- Unit Plan validation 新增缺失依赖、循环依赖、模糊 handoff 摘要、下游 `requires[]` 与上游 `produces[]` 不匹配、ready checks 未映射到命令或测试用例等检查。
- Verifier 会写 `artifacts/<unit-id>/handoff-evidence.json`；声明的 handoff artifacts 或 ready checks 缺失时 producer verification 失败。
- 下游 Builder 在依赖 handoff evidence 缺失、failed 或不匹配时，以 `blockedContext.category=unit_handoff` 阻塞执行。
- 新增 `docs/workflow/unit-continuity-handoff-policy.md` 并将 package version metadata 更新到 `0.6.2d`。

## 0.6.2b

- 新增 Blocked Assist：为 `status=blocked` workflow 提供受控诊断对话、summary artifact、人工确认的 `human_reason`，并由 controller 显式选择恢复路线。
- 将 Requirements 原型预览从 Plannotator 临时服务提升为 controller 进程级常驻预览服务。
- Product Design checkpoint 校验通过后立即生成 Plannotator review HTML/manifest；final approval gate 尚未装配时使用 Scope checkpoint 作为 requirements reference。
- Architecture、Test Strategy、final Requirements assembly、Requirements 人工评审和 Plannotator 辅助审阅期间复用同一个 preview URL。
- final Requirements assembly 后重新生成 review bundle，让 manifest 补齐真实 approval gate path，同时保留当前预览端口。
- 预览端口从 `WAYGATE_PREVIEW_PORT` 或默认 `20001` 起步，端口被占用时自动递增。
- Plannotator Close 后不再关闭预览服务，并在代理环境下提示配置 `NO_PROXY/no_proxy`。

## 0.6.2a

- 为 staged Requirements package 新增目标产品表面分类，记录目标 UI/Web/prototype 需求、可见表面，以及来自 spec、目标上下文、unit metadata 和反馈的脱敏证据片段。
- 更新 staged Scope、Product Design、Architecture 和 Test Strategy prompt，使其围绕目标产品/目标系统，而不是 Waygate/controller 工作流。
- 保留 UI/Web 目标的 Requirements prototype 硬门禁，同时允许明确的 backend/API/CLI-only 目标声明不需要 UI 的依据。
- 非 Waygate 目标项目中，如果 Product Design 或 Architecture 主要描述 Waygate/controller 内部流程，preflight 会判 invalid。
- 改善 staged revision 路由：UI/prototype 反馈回到 Product Design，交互/API/数据流反馈回到 Architecture。
- AO 映射或 E2E AC/Journey 映射缺口与 prototype 文案同时出现时，优先回到 Scope，避免因 prototype 关键词误入 Product Design 循环。
- `prototype_required=required` 或 `web_system=required` 时，Product Design checkpoint prompt 和 stage validation 都要求 `artifacts/requirements-draft/prototype-manifest.json`。
- 明确 Product Design manifest 本地路径语义：本地原型 path 必须从 `artifacts/requirements-draft/` 解析；缺文件诊断会输出 resolved path，并提示 workspace-relative `docs/prototypes/...` 的修复方式。

## 0.6.2

- 新增 Staged Requirements Package 流程：Requirements Scope、Product Design Brief、Technical Architecture Brief 和 Requirements Test Strategy Brief 作为聚焦 checkpoint 运行，最后仍保留一个人工 Requirements approval gate。
- 新增最终 package assembly，包含 checkpoint artifact hash、附录内容和 staged package 一致性校验。
- 将详细目标项目基础设施 intake 后移到 Unit Plan Infrastructure / Execution Context Matrix，Requirements 只保留最小上下文。
- Unit Plan 继承 staged artifact path、hash 和 status metadata，确保 scope、AC、Journey、设计、架构、E2E 和风险义务继续向下游传递。
- 新增 V0.6.2 正式 workflow / architecture 文档，并将 Strict Test Presence / Per-Role Runner Configuration 保留在 V0.6.3。

## 0.6.1

- 新增受支持的 OpenSpec/OpenAPI 和 Spec Kit intake 路径，生成 normalized requirements、source maps、validation reports，并对 unsupported/deferred 格式给出清晰错误。
- 新增 Requirements、Unit Plan、Final Acceptance gate 前的非批准型、按 role 配置的 annotation 和 verification-assist 能力。
- `init`、`start`、`go`、`drive`、`run` 新增 `--annotation-agent` 系列 CLI 参数，允许操作者启用风险标注 Agent，无需手改 `session.json`。
- 新增风险标注 artifact 的提示词合同与 prompt template registry 覆盖。
- 新增灵活 verifier evidence rows，让描述型命令证据记录结构化引用和 `human_review_required`，但不覆盖确定性命令状态。
- 新增 V0.6.1 正式 workflow / architecture 文档，并将新的 `docs/architecture/` 子目录纳入 Debian 包。

## 0.6.0m

- Unit Plan 新增 `golden_path: true` 前置校验：golden path test case 必须是 `layer=e2e`，使用 `local_real` 或 `production_readonly`，声明真实入口，提供 fixture/setup，使用出现在 `verification_commands` 中的具体命令，包含强 expected 断言，并且不得 mock/stub 核心业务 API。
- Requirements 中声明 E2E 的 AC 和 active E2E Journey 必须在 Unit Plan 中映射到 `layer=e2e` test case，才能通过 Unit Plan approval。
- 明确 E2E 不等于浏览器专属：API-only 和 service-only golden path 可以使用 pytest/API/service E2E 调真实入口。
- Unit Plan Test Case Matrix 显式展示 Golden Path 列，并与 Layer、Environment、Real Entry、Core API Mock 一起供人工审核。
- Requirements/Unit Plan prompt、workflow 文档、README/USAGE 和 package version 已同步到 `0.6.0m`。

## 0.6.0k

- Requirements、Unit Plan、Builder 和 UI Design Brief prompt contract 对 UI/Web/prototype 工作明确要求使用 `ui-ux-pro-max`。
- 明确 `frontend-design` 只能作为全新视觉探索或局部视觉润色辅助，不能替代既有产品 UI/原型一致性工作。
- 原型设计前必须盘点真实 UI：route、DOM/组件、既有页面结构、截图、历史设计或参考环境。
- `waygate doctor` 的 `skill_recommendations.ui_ux_design` 现在只安装 `frontend-design` 时输出 warning 和 manual action，两者都安装时优先展示 `ui-ux-pro-max`。
- 新增并打包 `docs/workflow/ui-ux-skill-policy.md`。
- 启动时输出运行版本号：`init` 和 `run` 第一行输出 `waygate <version>`；`start`、`go`、`drive` 通过带时间戳的 drive 输出通道输出同一版本行。

## 0.6.0j

- 调整无 `--spec` Requirements prompt：第一轮仍只能提出澄清问题；收到具体回答后读取项目上下文、盘点 `## 4.9` 基础设施缺口，并在事实仍缺失时继续在同一 tmux pane 追问。
- 要求 agent 对用户补充的基础设施事实做非破坏性核对；无法访问的外部系统、生产环境、私有 wiki/API 等必须标注为用户提供且未能直接验证。
- 加强 Requirements 预检：空泛或无依据的缺失基础设施事实会被拒绝，除非写明已检查来源、4.8 中有用户确认问答，或给出具体不涉及原因。
- 当 `## 4.9` 声称“用户确认”或“已验证”时，要求 `## 4.8` 有对应问答、核对方式和验证结论留痕。
- 修复 Plannotator 和原型预览访问地址：服务仍可绑定 `0.0.0.0`，但终端展示的浏览器 URL 使用本机主 IP 地址或 `WAYGATE_DISPLAY_HOST`。
- 将 Plannotator 远程访问配置切换为 `PLANNOTATOR_REMOTE=1`，并让 controller prototype preview server 默认固定使用 `20001` 端口。

## 0.6.0i

- 新增 `docs/README.md` 作为生成和打包的文档入口与轻量登记表。
- 更新生成的 `AGENTS.md` 指引，要求读取 `docs/README.md`，区分正式文档、过程状态文档，并明确 `.rrc-controller-*` 是审计证据而不是长期文档入口。
- Requirements 基础设施 intake 的文档来源改为结构化盘点：正式维护文档、Controller 过程证据、外部 Agent / 人工沟通文档、外部 wiki / 设计稿 / API 文档，以及缺失但需要沉淀的文档。
- Unit Plan 新增 Document Deliverables Matrix prompt 和校验，覆盖长期产品、架构、流程、运维、证据规则和文档生命周期变更。
- Final Acceptance 展示文档交付状态，并且只阻断 `Required For Acceptance = true` 的文档动作。

## 0.6.0h

- `waygate doctor` 新增 `tmux_config` section，检查推荐 `~/.tmux.conf` 配置：`mouse on`、`history-limit 100000`、`@scroll-speed 5` 和 `@copy-mode-vi 'on'`。
- tmux 配置诊断保持只读：warning 会展示 expected/actual 和 manual action，但 Waygate 不修改也不 reload tmux 配置。
- Doctor 输出改为先展示 `summary:`、`focus:` 和 `action_required:`，再展示安装来源、PATH、环境、skills 和 Claude assets 等详细 section。
- 新增 `waygate doctor --color auto|always|never`，高亮状态、P1 关注项、manual action 和 section 标题，方便人工扫描；非 TTY 输出默认保持纯文本。
- 保留既有详细 section 便于排障，同时把 PATH shadow、版本不一致、缺工具、缺 skill 和 tmux 配置事项提升到顶部。
- README、USAGE、路线图、推荐环境文档和包版本同步到 `0.6.0h`。

## 0.6.0g

- `waygate doctor` 新增 `claude_assets` section，报告 `~/.claude/commands`、`agents`、`rules`、`plugins` 的路径、状态和数量，不读取内容。
- `skill_recommendations` 与当时 README 推荐基线对齐，补齐 code review、plan execution、webapp testing 和 UI-heavy requirements；V0.6.0k 后 `ui-ux-pro-max` 成为 UI/Web/prototype 必需 skill。
- Controller prototype preview server 默认绑定 `0.0.0.0`，提升远程浏览器可达性。
- 通过 `PLANNOTATOR_REMOTE=1` 请求 Plannotator 开启远程访问，不再控制 bind host。
- 文档说明远程审阅 host 行为；当前浏览器 URL 会用本机主 IP 地址展示。

## 0.6.0f

- Unit Plan 人工确认新增真实 E2E 证据门禁：mock/stub 核心业务 API 的浏览器测试不能覆盖 E2E、golden path、prototype conformance、Journey closure 或 Web 系统验收。
- Verifier evidence rows 新增 environment kind、真实入口、核心 API mock 状态、mocked routes、浏览器 console/page/request 运行错误和截图引用字段。
- 即使命令退出码为 0，带核心 API mock 的浏览器 E2E 证据也会标记为 `invalid`；真实 E2E 中记录到 console/page/request runtime error 时验证失败。
- Final Acceptance 与 Prototype Conformance 矩阵新增环境、mock 和 runtime error 列，并用真实 E2E 证据阻断非真实 prototype/golden-path 终验。
- 当 Requirements 或人工反馈要求远程日志、生产页面或部署后验证时，必须使用 `environment_kind=production_readonly` 的只读生产证据，不能用本地测试替代。

## 0.6.0e

- 扩展 `waygate doctor` 的 `environment_checks`，覆盖 Python、pytest、tmux、tmux session、Claude Code、Codex、Plannotator、`dpkg-deb` 和推荐 Plannotator port `20000`。
- 扩展 `waygate doctor`，扫描常见 agent skill 根目录、报告已安装 skills、输出推荐 workflow skill 缺口 warning，并支持 `WAYGATE_SKILL_ROOTS` 追加自定义根目录。
- Claude Code、Codex 和 Plannotator 保持可选，缺失时输出 warning/manual action，不让 `doctor` 失败。
- 新增 `docs/operations/` 双语推荐环境 recommended-environment 文档和 `docs/product/` 双语 Waygate introduction/best practices 文档，包含 PPT 大纲但不生成 `.pptx`。
- 更新 README、USAGE、ROADMAP 和包内文档入口，记录 V0.6.0e，同时保持 V0.6.1 和 V0.6.2 为后续范围。
- Debian 包会把新增 product 与 operations 文档安装到 `/usr/share/doc/waygate/docs/`，并与 `workflow_controller.__version__` 保持版本一致。

## 0.6.0d

- 即使存在 prototype review bundle，Requirements Plannotator 的审批目标也恢复为 `approvals/requirements-and-acceptance.md`。
- `plannotator-review.html` 保留为 controller preview server 提供的原型渲染辅助预览页。
- Plannotator review metadata 会记录审批文件、辅助预览文件、manifest 路径和临时 preview URL，但不会把临时 localhost URL 写入 approval 文件。

## 0.6.0c

- 目标项目基础设施 intake 现在适用于每个 Requirements draft，并固定输出 `## 4.9 目标项目基础设施信息`。
- Requirements preflight 会阻断缺失、不完整或仍是占位内容的基础设施类别。
- 新增 `waygate doctor`，输出 executable path、module path/version、dpkg version、PATH 候选和命令 shadow 警告。
- Debian 打包会强制 control `Version`、包内 `__version__` 和 `waygate --version` 保持一致。
- Debian post-install 会提示 `~/.local/bin/waygate` 等用户级 wrapper 的 shadow 风险，但不会删除用户文件。

## 0.6.0b

- 新增 Requirements、Unit Plan 和 Final Acceptance 的原型到生产 UI 一致性门禁。
- prototype manifest 中每个 UI/Web 原型必须通过 `implementation_targets` 或兼容别名映射真实实现目标。
- 一致性验收从整张 prototype target 扩展到 required `surface_contracts`，覆盖弹窗、抽屉、面板、选择器、管理 surface 和真实入口。
- Unit Plan 新增真实 route/page 一致性测试校验，要求具体断言。
- Final Acceptance 新增 `Prototype Conformance Matrix`，缺失或失败的一致性证据会阻断终验。
- Controller State Patch 保留 `currentUnitIsWebSystem`。

## 0.6.0a

- 新增 Requirements prototype review bundle，供 Plannotator 审阅原型证据。
- 新增 `prototype-manifest.json` 校验、规范化 review manifest、本地原型资产复制和只读 localhost 预览链接。
- approval 仍落在 `approvals/requirements-and-acceptance.md`；后续版本把渲染后的 prototype HTML 仅作为辅助预览。
- 强化 UI/UX 和 Web 原型预检：阻断缺文件、未知 AC、缺页面状态、缺点击路径、缺 AC 映射和敏感 URL query。

## 0.6.0

- Python 包新增 `__version__`，CLI 新增 `--version` flag。
- 清理路线图版本编号：下一步优先级从 V0.6.0 开始。
- 整理 GitHub 对外英文和中文文档。
- 新增 contribution、security、issue 和 pull request 社区文件。
- Requirements 草案修订后，controller 预检仍会先于人工确认执行。

## 0.5.4

- Requirements Gate 写入前必须先做简洁需求澄清，澄清结论记录到 4.8 小节。
- Requirements、Unit Plan、Final Acceptance 和 Bug Fix 人工评审阶段新增 tmux 防串聊提醒，不提交输入、不推进 workflow state。
- 正常 tmux 派发默认先清空 agent 输入框，并支持 `WAYGATE_TMUX_CLEAR_INPUT_BEFORE_DISPATCH=0` 关闭。
- compact/status 输出把当前项目目标版本与 Waygate 包版本分开展示。
- 项目 agent guide 补充版本规划事实源规则。

## 0.5.3

- 新增 Waygate Debian 包和 `/usr/bin/waygate` wrapper。
- 改进 compact 终端输出和 approval gate 状态展示。
- 修复 tmux runner 可靠性问题，包括 Codex pane 自动发现和 Claude pane 默认启动命令。
- 改进 Requirements 与 Unit Plan 中 AO、traceability 和 Journey mapping 校验。

## 更早历史

更早开发历史保留在 `progress.md`、`findings.md` 和 `task_plan.md` 中。这些文件是维护者历史，不是使用 Waygate 必需的用户文档。
