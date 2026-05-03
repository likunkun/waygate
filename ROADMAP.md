# Workflow Controller — 版本路线图（确认版）

## V0.1 — Test Strategist 接入（已完成）

- Test Strategist 配置、runner/env 隔离
- prompt/schema/artifacts 支持
- Controller 编排、Critical 自动返工、fallback 阻断
- Review Package 合并与现有 Unit Plan gate 校验
- 全链路回归验收，全量测试 144 passed

---

## V0.2 — 全面重构

架构分层，为后续版本留好扩展位置。

```
workflow_controller/
├── state_machine/        # 状态转移规则、allowed action 计算
├── gates/                # generators / parsers / validators 三层
├── runners/              # base 接口 + tmux_claude + codex + opencode（占位）
├── prompts/              # requirements / unit_plan / builder / bug_fix（占位）
├── steps/                # requirements / unit_plan / builder / bug_fix（占位）
├── controller.py         # 纯编排
├── cli.py                # CLI 入口
└── tests/                # 按模块拆分
```

---

## V0.3 — Acceptance-Driven Loop + 需求质量 + 证据标准化 + CodeSimplifier

**V0.3.1 Acceptance Obligation Ledger（已完成）：**

人工反馈、Plannotator annotations、Requirements/Unit Plan 返工和 Final Acceptance rejection 会进入结构化 AO Ledger，避免多条人工问题被压缩成单个 closure unit。

```
Human Feedback → AO Ledger → Requirements AC → Unit Plan Test Case → Verifier Evidence → Final Acceptance
```

- AO 使用稳定 id（如 `AO-001`）存入 controller state 的 `acceptanceObligations`
- AO artifacts 写入 `artifacts/acceptance-obligations/acceptance-obligations.json` 和 `.md`
- Requirements / Unit Plan prompt 注入 AO Ledger
- Unit Plan approval 阻断缺失 active must AO 覆盖的计划
- 全量测试：`240 passed in 32.12s`

**V0.3.2 CodeSimplifier 集成（已完成）：**

Builder 完成后、Reviewer/Verifier 启动前，controller 默认调用 CodeSimplifier 对本次改动文件做简化审查：

```
Builder → CodeSimplifier/Refiner → Reviewer → Verifier → Final Acceptance
```

- CodeSimplifier 以 runner 形式执行，输入为 `changed-files.txt`，输出写入 `artifacts/<unit-id>/simplifier-result.json`
- `ok/skipped` 进入 Reviewer；`changes_requested` 自动触发 Builder 返工；`failed` 停留在 Refiner retry/block，不进入 Reviewer
- 默认开启；可通过 `--no-code-simplifier` 关闭，并可用 `--code-simplifier-command` / `--code-simplifier-env` 覆盖 runner
- 全量测试：`252 passed in 30.76s`

**V0.3.3 Requirements Quality Gate（已完成）：**

- Requirements approval 前预检：每条 active `must` AO 必须映射到 AC，或显式 `deferred` / `rejected` / `out_of_scope` 且写明原因
- 每条 AC 必须声明 verification layer：`unit` / `integration` / `e2e` / `manual`
- Requirements draft prompt 和本地 template 新增 `Requirements Traceability Matrix`
- 无效 requirements 不会写入 approved，也不会进入 Unit Plan；阻断原因进入 requirements revision prompt
- 全量测试：`259 passed in 30.51s`

**V0.3.4 Product Design / Technical Architecture Traceability（已完成）：**

- Requirements approval 会在存在 `Design/Architecture Traceability Matrix` 时，要求每条 AC 同时映射 Product Design Ref 和 Technical Architecture Ref
- Requirements draft prompt 和本地 template 新增设计/架构可追溯矩阵
- Unit Plan approval 要求 test case 保留对应 AC 的 `product_design_refs` 和 `technical_architecture_refs`
- Unit Plan prompt 和本地 template 的 Test Case Matrix 增加产品设计引用和技术架构引用列
- 兼容旧 requirements：没有设计/架构可追溯矩阵的历史 gate 不会被 V0.3.4 新规则阻断
- 全量测试：`264 passed in 31.38s`

**V0.3.5 Verifier Evidence Schema（已完成）：**

- Verifier evidence schema 记录 AO/AC/Test Case/Evidence 对账矩阵
- Verifier artifact 从纯命令结果扩展为结构化 evidence rows
- 证据 schema 需要兼容手工证据、自动化测试命令和 golden path 结果
- Controller 在 Verifier 通过后校验 `evidence_schema_version` 和 `evidence_rows`，schema 无效时按验证失败返工，不进入 Unit Complete
- 定向测试：`169 passed in 17.97s`
- 全量测试：`267 passed in 29.94s`

**V0.3.6 Final Acceptance Evidence Matrix（规划中）：**

- 引入 evidence schema：最终验收 gate 按结构化模板渲染（AO id、AC 编号、验证层、命令、预期结果），替代纯文本 checklist
- 最终验收 gate 基于 Verifier evidence schema 渲染可审阅矩阵
- 拒绝时保留 AO/AC/Test Case/Evidence 定位，便于路由到 requirements、unit_plan、defect_fix 或 implementation

**可选：**

- Codex Test Strategist 接入 requirements 阶段

---

## V0.4 — 需求协商 + Bug Fix 环节

**需求协商循环：**
- Requirements gate 支持多轮批注返工，满意后正式 approve

**Bug Fix 环节（替代原 defect_fix → Unit Plan 重路径）：**

```
defect_fix 路由触发
  → bug-fix gate（人工填写：预期行为 vs 实际行为）
  → Bug Fix Agent（定位根因 + 修复 + 补回归测试）
  → 验证（跑已有 test cases）
  → 通过 → 回最终验收
  → 失败 → 返工
  → 根因是架构问题 → 升级到 unit_plan 路由
```

**最终验收路由语义（更新后）：**

| 路由 | 行为 |
|------|------|
| `requirements` | 退回需求重写 |
| `unit_plan` | 退回 Unit Plan 修订 |
| `defect_fix` | 进入 Bug Fix 环节（问题描述 → 诊断修复） |
| `implementation` | 退回 Builder 返工（修改清单或完整 gate） |
| `blocked` | 挂起等待解除 |

---

## V0.5 — Agent 灵活性

- `runners/base.py` 标准接口（V0.2 预留）
- opencode runner 实现
- per-role runner 独立配置
