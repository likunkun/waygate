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

## 遇到的问题
| 问题 | 解决方案 |
|------|---------|
| `--orphan` worktree 命令首次参数顺序错误 | 使用 `--orphan -b workflow-controller <path>` |
| 初始提交包含 `.pyc` 文件 | 删除缓存文件、添加 `.gitignore`、amend 初始提交 |
| `.pytest_cache` 在测试后会生成 | 已通过 `.gitignore` 忽略 |
| Claude 可能写旧 run 的 `done.json` 或停在 prompt | 已通过 run_id 校验和 idle/timeout 诊断区分 |
| Unit Plan 生成的验证命令可能缺少环境变量 | 已通过 `verification_env` 和 approval 预检降低风险 |
| 过宽的 E2E 预检会误伤 `pytest tests/e2e/...` | 已收窄为 Playwright/Prisma/显式 `DATABASE_URL` |

## 资源
- 新工作区：`~/works/ai-works/worktrees/workflow-controller`
- 分支：`workflow-controller`
- 初始提交：`fd27a54 Add workflow controller project`
- 测试命令：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q`

## 视觉/浏览器发现
- 本任务未使用浏览器或图片检查。

---
*每执行2次查看/浏览器/搜索操作后更新此文件*
*防止视觉信息丢失*
