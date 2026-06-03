# 文档入口与登记表

本文件是 Waygate 项目的正式文档入口和轻量登记表。`task_plan.md`、`progress.md`、`findings.md` 记录过程、进度和决策；`.rrc-controller-*` 目录记录审计证据。它们可以作为事实来源，但不是长期文档入口。

Current annotation note: annotation uses subprocess only. `WAYGATE_ANNOTATION_TMUX` is a deprecated no-op kept for old shells; it does not create annotation panes. Persisted audit data remains env key-only.

## 文档生命周期

- Requirements 阶段盘点正式维护文档、Controller 过程证据、外部 Agent / 人工沟通生成文档、外部 wiki / 设计稿 / API 文档，以及缺失但需要沉淀的文档。
- Unit Plan 阶段用 Document Deliverables Matrix 声明本 unit 是否需要正式文档动作；纯代码小修可以声明不需要正式文档变更并写明原因。
- Builder 按 Unit Plan 落文档；`Required For Acceptance = true` 的文档动作必须在 Final Acceptance 前完成。
- Final Acceptance / Final Sync 只阻断 Unit Plan 声明为 required 的文档动作，不把所有历史缺失文档变成本轮阻断。

## 正式文档目录

| 目录 | 用途 |
| --- | --- |
| `docs/product/` | 产品背景、用户旅程、需求说明。 |
| `docs/architecture/` | 技术架构、模块边界、关键设计决策。 |
| `docs/workflow/` | Agent 协作、审批流程、验收流程、证据规则、文档生命周期。 |
| `docs/operations/` | 运行、部署、排障和运维说明。 |

## 当前登记

| 类型 | 入口 | 用途 / 可信度 |
| --- | --- | --- |
| 正式维护文档 | `docs/architecture.md`、`docs/architecture.zh-CN.md` | 当前技术架构入口；后续可按主题迁入 `docs/architecture/`。 |
| 正式维护文档 | `docs/workflow.md`、`docs/workflow.zh-CN.md` | 当前工作流入口；流程规则变更优先登记并沉淀到 `docs/workflow/`。 |
| 正式维护文档 | `docs/workflow/controller-agent-interaction-audit.md` | Controller-Agent 主流程、返工路线、关键 prompt 来源和 Requirements 到 Final Acceptance 贯穿性审计。 |
| 正式维护文档 | `docs/workflow/controller-agent-interaction-audit.html` | 上述审计的自包含 Plannotator 风格可视化版本，便于浏览流程图、提示语卡片和贯穿性矩阵。 |
| 正式维护文档 | `docs/workflow/external-spec-intake-and-annotation-policy.md` | V0.6.1 外部 spec intake、V0.6.2e `open-spec-package` / Spec Kit feature package directory intake、subprocess-only annotation runtime、`WAYGATE_ANNOTATION_TMUX` deprecated no-op、`opencode` / `codex` annotation backends、env key-only audit、gate ordering、role-based annotation、prompt contract、non-approval semantics、`descriptive_command` 与 `agent_assisted_case` evidence 流程规则。 |
| 正式维护文档 | `docs/workflow/unit-plan-evidence-row-preflight-policy.md` | Unit Plan evidence-row 前置校验规则：自动化 test case command 必须精确匹配 `verification_commands`，且所有可执行命令必须是 `scripts/verify/` 下的脚本入口；`verification_assist` 例外，Final Scope Audit 缺 AC evidence row 时回到 Unit Plan revise。 |
| 正式维护文档 | `docs/architecture/external-spec-intake-and-annotation-architecture.md` | V0.6.1 OpenSpec / Spec Kit import contract、V0.6.2e Open Spec package directory import contract、subprocess-only annotation runtime、legacy Claude annotation migration to OpenCode、env key-only metadata、annotation_agents.py、prompt template registry、runner adapter、verification-assist case runner 和 verification.json schema 模块边界。 |
| 正式维护文档 | `docs/workflow/staged-requirements-package-policy.md` | V0.6.2 / V0.6.2a / V0.6.2b / V0.6.2c / V0.6.2d / V0.6.2e / V0.6.2f / V0.6.2g / V0.6.2h / V0.6.2i Staged Requirements Package 流程规则：需求范围检查点、产品设计简报、技术架构简报、需求测试策略简报、Product Design no-spec brainstorming prompt contract、Requirements acceptance-first intake、1:1 user-task prototype、Product Journey Contract、目标产品表面分类、Product Design 后常驻原型预览、final gate assembly、annotation ordering、Requirements checkpoint revise、Unit Plan handoff、Requirements package directory intake、human review control handoff、Requirements 4.6 parser boundary、source/provenance AC obligation boundary 和 downstream invalidation。 |
| 正式维护文档 | `docs/workflow/unit-continuity-handoff-policy.md` | V0.6.2d Unit Continuity Gate：多单元 Unit Plan 的 `depends_on`、`handoff`、Handoff Matrix、producer `handoff-evidence.json`、downstream Builder `unit_handoff` blocker 和恢复路线。 |
| 正式维护文档 | `docs/architecture/staged-requirements-package-architecture.md` | V0.6.2 / V0.6.2a / V0.6.2b / V0.6.2c / V0.6.2d / V0.6.2e / V0.6.2f / V0.6.2g / V0.6.2h / V0.6.2i `requirements_package.py`、`requirements_surface.py`、Product Design prompt branch helper、checkpoint prompt renderer、stage runner、controller orchestration、controller process-level prototype preview、gate generator/validator、Requirements checkpoint revise、Unit Plan prompt inheritance、Requirements package directory intake、human review control prompt handoff、Product Journey Contract、主业务对象血缘拆分矩阵、Requirements 4.6 fixed-table parsing、source/provenance AC collection 和 Infrastructure / Execution Context Matrix 模块边界。 |
| 正式维护文档 | `docs/workflow/human-review-control-policy.md` | V0.6.2f Human Review Control：approval notes non-contract context、AO-001 clarification boundary、`i` draft merge、`m` guarded manual adoption、Ctrl+C `human_interrupt` recovery、`approve --reason` / `revise` route split、legacy review compatibility 和 review-bundle conformance。 |
| 正式维护文档 | `docs/architecture/human-review-control-architecture.md` | V0.6.2f Human Review Control 模块边界：`approval_notes.py`、`rrc_controller.py`、prompt renderers、CLI route、state/artifact/event shape、tmux interrupt adapter、review bundle evidence 和 prototype conformance target mapping。 |
| 正式维护文档 | `docs/workflow/requirements-e2e-review-policy.md` | V0.6.3 Strict Test Presence 中的真实 E2E / 浏览器/API/service 验收前置审阅规则；V0.6.0m Unit Plan golden path 必须是真实 `layer=e2e`。 |
| 正式维护文档 | `docs/workflow/recoverable-wait-go-resume-design.md` | 2026-05-26 设计：移除用户可见 `retry`，由 `go/run/drive/start` 自动消费 timeout/idle recoverable wait，同时保持 blocked 的 `unblock` / `revise` 边界。 |
| 正式维护文档 | `docs/workflow/recoverable-agent-timeout-policy.md` | Agent 超时、idle-without-DONE 和 `go/run/drive/start` 自动恢复 recoverable wait 的策略；说明 transient runner silence 不走 `waygate revise`。 |
| 正式维护文档 | `docs/workflow/stop-guidance-and-unblock-policy.md` | Waygate 停止状态原因化 guidance、recoverable wait 与显式 `blocked` 的边界、环境类 `unblock` 和 Builder blocked reconciliation 规则。 |
| 正式维护文档 | `docs/workflow/blocked-assist-policy.md` | `status=blocked` 时的可选诊断对话层、summary artifact、人工 `human_reason` 要求，以及 continue / Unit Plan / Requirements / Final Acceptance 路由边界。 |
| 正式维护文档 | `docs/workflow/final-acceptance-guided-walkthrough-policy.md` | Final Acceptance 前的启动准备阶段、Agent 提供的 `final_acceptance_walkthrough.inspection` / `launch` 合同、人工观察记录审阅上下文和 Golden Path 人工走查 gate 规则。 |
| 正式维护文档 | `docs/workflow/prototype-fidelity-policy.md` | UI/Web 原型一致性 fidelity、视觉证据、Verifier marker 和终验阻断规则。 |
| 正式维护文档 | `docs/workflow/ui-ux-skill-policy.md` | V0.6.0k UI/Web/prototype 工作必须使用 `ui-ux-pro-max`，`frontend-design` 只能作为辅助视觉探索或润色。 |
| 正式维护文档 | `docs/product/waygate-introduction-and-best-practices.md`、`docs/product/waygate-introduction-and-best-practices.zh-CN.md` | Waygate 介绍和最佳实践。 |
| 正式维护文档 | `docs/operations/recommended-environment.md`、`docs/operations/recommended-environment.zh-CN.md` | 推荐本地环境和诊断说明。 |
| Controller 过程证据 | `.rrc-controller-*/artifacts/` | 审计证据，不是长期文档入口。 |
| 外部 Agent / 人工沟通生成文档 | 未登记 | 发现后先登记，再决定是否提升。 |
| 外部 wiki / 设计稿 / API 文档 | 未登记 | 发现后记录用途、访问方式和可信度。 |
| 缺失但需要沉淀的文档 | 未登记 | 由 Requirements / Unit Plan 决定是否进入当前 unit。 |
