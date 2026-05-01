# 发现与决策

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
| 测试复用 Hermes venv | 当前项目来自 Hermes 环境，依赖已可用 |
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
- 测试命令：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q`
- 实际运行目录：`/home/lichangkun/.hermes/hermes-agent/workflow_controller`
- V2.2 当前 state dir：`/home/lichangkun/works/2026Q2/courses/.rrc-controller-v2-2`

## 视觉/浏览器发现
- 本任务未使用浏览器或图片检查。

---
*每执行2次查看/浏览器/搜索操作后更新此文件*
*防止视觉信息丢失*
