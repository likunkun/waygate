# 文档入口与登记表

本文件是 Waygate 项目的正式文档入口和轻量登记表。`task_plan.md`、`progress.md`、`findings.md` 记录过程、进度和决策；`.rrc-controller-*` 目录记录审计证据。它们可以作为事实来源，但不是长期文档入口。

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
| 正式维护文档 | `docs/workflow/requirements-e2e-review-policy.md` | V0.6.2 Requirements 阶段真实 E2E / 浏览器验收前置审阅矩阵、阻断规则和 Unit Plan 继承要求。 |
| 正式维护文档 | `docs/workflow/prototype-fidelity-policy.md` | UI/Web 原型一致性 fidelity、视觉证据、Verifier marker 和终验阻断规则。 |
| 正式维护文档 | `docs/workflow/ui-ux-skill-policy.md` | V0.6.0k UI/Web/prototype 工作必须使用 `ui-ux-pro-max`，`frontend-design` 只能作为辅助视觉探索或润色。 |
| 正式维护文档 | `docs/product/waygate-introduction-and-best-practices.md`、`docs/product/waygate-introduction-and-best-practices.zh-CN.md` | Waygate 介绍和最佳实践。 |
| 正式维护文档 | `docs/operations/recommended-environment.md`、`docs/operations/recommended-environment.zh-CN.md` | 推荐本地环境和诊断说明。 |
| Controller 过程证据 | `.rrc-controller-*/artifacts/` | 审计证据，不是长期文档入口。 |
| 外部 Agent / 人工沟通生成文档 | 未登记 | 发现后先登记，再决定是否提升。 |
| 外部 wiki / 设计稿 / API 文档 | 未登记 | 发现后记录用途、访问方式和可信度。 |
| 缺失但需要沉淀的文档 | 未登记 | 由 Requirements / Unit Plan 决定是否进入当前 unit。 |
