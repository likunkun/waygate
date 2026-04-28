# 任务计划：Workflow Controller 后续开发基线

## 目标
将当前 `workflow_controller` 功能、决策和进度固化到 `~/works/ai-works/worktrees/workflow-controller`，后续开发以该分支工作区为准。

## 当前阶段
已完成 workflow-controller 可靠性增强：重复失败硬阻断、run_id 防串线、verification_env、Unit Plan 预检和 timeout 诊断。

## 各阶段

### 阶段 1：需求与问题收敛
- [x] 确认 Plannotator 启动失败和超时问题
- [x] 确认 Unit Plan 审批后卡在确认阶段的问题
- [x] 确认 50 步上限过低、重复循环缺少保护的问题
- [x] 确认控制器输出信息过繁、需要紧凑中文状态的问题
- [x] 确认后续开发目录迁移到 `~/works/ai-works/`
- **状态：** complete

### 阶段 2：运行流程修复
- [x] Plannotator 启动改为非阻塞等待链接出现
- [x] Plannotator 默认使用 20000 端口，并支持命令行配置
- [x] Unit Plan gate 保留已确认状态，避免审批后反复检查
- [x] gate 内容异常时重新进入人工确认，而不是空转
- [x] 默认最大步数提高到 2000
- [x] 增加重复无进展 50 次保护
- **状态：** complete

### 阶段 3：终端输出体验
- [x] 默认使用紧凑状态面板
- [x] 重复循环时展示 attempt 摘要
- [x] 原始详细输出放到 `--verbose`
- [x] 状态、阶段、动作标签使用中文
- [x] 支持 `--color auto|always|never`
- [x] 保留面向 tmux 另一窗口的实际进展可见性
- **状态：** complete

### 阶段 4：新仓库分支工作区
- [x] 确认 `~/works/ai-works` 是 bare/manage repo
- [x] 创建孤儿分支 `workflow-controller`
- [x] 创建 worktree：`~/works/ai-works/worktrees/workflow-controller`
- [x] 复制当前项目到新工作区的 `workflow_controller/`
- [x] 清理 `__pycache__` 等生成文件
- [x] 添加 `.gitignore`
- [x] 完成初始提交
- **状态：** complete

### 阶段 5：计划与进度持久化
- [x] 在新工作区创建 `task_plan.md`
- [x] 在新工作区创建 `findings.md`
- [x] 在新工作区创建 `progress.md`
- [x] 提交计划与进度文件
- **状态：** complete

### 阶段 6：后续开发
- [x] 根据下一项用户需求继续实现
- [x] 每次阶段完成后更新 `progress.md`
- [x] 重大决策或已知限制更新 `findings.md`
- [x] 计划变化时更新 `task_plan.md`
- **状态：** in_progress

### 阶段 7：控制器可靠性增强
- [x] 重复失败硬阻断：同一 unit/stage/fingerprint 连续失败后 block
- [x] run_id 防串线：DONE_FILE 必须包含并匹配当前 run_id
- [x] verification_env 机制：unit/state 环境变量统一注入 verifier
- [x] Unit Plan approval 预检：拒绝明显缺环境的验证计划
- [x] timeout/idle 诊断：区分 idle、无输出、wrong run、invalid done
- [x] 完整测试通过
- **状态：** complete

### 阶段 8：运行可见性优化
- [x] verifier 在状态变化时输出进度标志
- [x] 不使用固定 30 秒 heartbeat，避免无意义刷屏
- [x] 紧凑输出按当前目标单元显示进度，避免 V2.1 误显示为历史总单元数
- [x] 同步到实际运行目录 `/home/lichangkun/.hermes/hermes-agent/workflow_controller`
- [x] 测试通过
- **状态：** complete

### 阶段 9：验证失败原因摘要
- [x] controller retry 输出显示失败命令摘要
- [x] controller retry 输出显示 exit code
- [x] controller retry 输出优先提取根因，如缺少 `DATABASE_URL`
- [x] 完整失败详情仍保留在 `verification.json`
- [x] 同步到实际运行目录 `/home/lichangkun/.hermes/hermes-agent/workflow_controller`
- [x] 测试通过
- **状态：** complete

### 阶段 10：旧 Session 验证环境自动修复
- [x] verifier 前置检查 Playwright/Prisma/DATABASE_URL 环境需求
- [x] 可从 `prisma/dev.db` 推导时自动写入 `verification_env.DATABASE_URL`
- [x] 推导来源写入 `verification_env_inferred`
- [x] 推导失败时直接 `blocked`，不回 Builder 重试
- [x] 同步到实际运行目录 `/home/lichangkun/.hermes/hermes-agent/workflow_controller`
- [x] 测试通过
- **状态：** complete

## 关键问题
1. 多实例同时运行是否要在控制器层面增加显式实例隔离或锁文件策略，仍需结合真实运行方式验证。
2. 是否需要为新工作区补充独立的打包配置、入口脚本或 CI，后续按开发需要决定。

## 已做决策
| 决策 | 理由 |
|------|------|
| 后续开发目录使用 `~/works/ai-works/worktrees/workflow-controller` | 和现有 `ai-works` worktree 管理方式一致，便于长期开发 |
| 使用孤儿分支 `workflow-controller` | 当前项目来自 Hermes 子目录，不适合混入现有业务分支历史 |
| 保留包目录 `workflow_controller/` | 现有测试以该包路径运行，复制后无需改导入结构 |
| 默认紧凑输出，`--verbose` 查看原始日志 | 常规运行只看进展，排错时仍能看到完整细节 |
| 终端状态使用中文 | 用户明确要求展示状态中文化 |
| Plannotator 默认 20000 端口 | 用户本机 Plannotator 使用该端口 |

## 遇到的错误
| 错误 | 尝试次数 | 解决方案 |
|------|---------|---------|
| `git worktree add --orphan workflow-controller <path>` 语法不匹配 | 1 | 改用 `git worktree add --orphan -b workflow-controller <path>` |
| 首次提交误包含 `__pycache__` | 1 | `git rm` 删除生成文件，新增 `.gitignore`，并 amend 初始提交 |

## 备注
- 进入新工作区：`cd ~/works/ai-works/worktrees/workflow-controller`
- 测试命令：`source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate && python -m pytest workflow_controller/tests -q`
- 当前初始功能提交：`fd27a54 Add workflow controller project`
