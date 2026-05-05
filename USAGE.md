# Workflow Controller 使用说明

## 概览

Controller 把一个开发目标拆分为若干 Unit，依次驱动以下阶段，在人工 gate 处暂停等待确认：

```
Requirements Draft → Unit Plan → Builder → Verifier → Final Acceptance
```

每个人工 gate 处 controller 自动启动 Plannotator（默认 `http://localhost:20000`）并打印网址，等待浏览器操作后自动继续。

Requirements Draft 阶段不会由 controller 终端问卷打断；如果目标 Claude/Codex agent 判断缺少会导致方向做错的关键信息，它会直接在自己的 tmux pane 里集中提问，用户回答后继续生成 Requirements Gate。

生成后的 Requirements Gate 会先经过 controller 预检；缺 Journey、缺 verification layer、缺 AO/AC 映射等可自动判定的问题会直接打回 Requirements Drafter，不先进入人工审核。

---

## 环境准备

```bash
# 进入工作区
cd ~/works/ai-works/worktrees/workflow-controller

# 激活虚拟环境
source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate
```

---

## 快速开始

### 目标项目初始化

推荐短命令：

```bash
python -m workflow_controller.cli go V1.0
```

这会自动推断：

| 项 | 推断值 |
|----|--------|
| target | `V1.0` |
| workspace-dir | 当前目录，即目标项目根目录 |
| state-dir | `<workspace-dir>/.rrc-controller-v1.0`；未显式传 `--workspace-dir` 时表现为 `.rrc-controller-v1.0` |
| runner | 未传 `--tmux-target` 且在 tmux 内时自动右侧创建 Claude pane；传入 `--tmux-target` 时自动识别 `tmux-codex` 或 `tmux-claude` |

如果已经有正在运行的 Codex 或 Claude pane，可以指定目标 pane：

```bash
python -m workflow_controller.cli go V1.0 --tmux-target 1.2
```

未显式传 `--workspace-dir` 时，controller 会使用目标 pane 的当前目录作为 workspace，并把默认 state-dir 放在该目录下。

完全展开的 `start` 写法仍然兼容：

```bash
python -m workflow_controller.cli start \
  --state-dir .rrc-controller-v1.0 \
  --workspace-dir . \
  --target "V1.0" \
  --runner tmux-claude \
  --tmux-target 1.2
```

`start` 在 state-dir 不存在时自动初始化，无需单独执行 `init`。

跨目录启动时应显式传目标项目目录；`go` 会把默认 state-dir 放到该目录下：

```bash
python -m workflow_controller.cli go V1.0 \
  --workspace-dir ~/works/target-project
```

### 两步法（先 init 再 drive）

适合需要检查初始状态后再启动的场景：

```bash
python -m workflow_controller.cli init \
  --state-dir .rrc-controller-v1.0 \
  --workspace-dir . \
  --target "V1.0" \
  --runner tmux-claude \
  --tmux-target 1.2

python -m workflow_controller.cli drive \
  --state-dir .rrc-controller-v1.0
```

## 子命令速查

### `go` — 推荐短入口

按目标推断常用参数，等价于 `start` 的便捷层：state-dir 不存在时初始化，存在时按现有 `start` 兼容性校验继续。

```bash
# 新目标：推断目标项目内的 .rrc-controller-v1.0；在 tmux 内无 target 时自动创建 Claude pane
python -m workflow_controller.cli go V1.0

# 指向已有 pane：自动识别 Codex 或 Claude
python -m workflow_controller.cli go V1.0 --tmux-target 1.2

# 显式使用 subprocess runner
python -m workflow_controller.cli go V1.0 --runner subprocess

# 缺少 TARGET 且未显式传 --state-dir 时会报错，避免串错目标项目
python -m workflow_controller.cli go --tmux-target 1.2
```

`TARGET` 也可用 `--target TARGET` 传入；若位置参数和 `--target` 同时传入且不一致，CLI 会直接报错。没有 TARGET 时必须显式传 `--state-dir`，否则 `go` 会拒绝启动。

### `init` — 初始化会话目录

创建 `session.json`、`approvals/`、`artifacts/` 等目录结构，不启动工作流。

```bash
python -m workflow_controller.cli init \
  --state-dir .rrc-controller-v1.0 \
  --workspace-dir . \
  --target "V1.0" \
  --runner tmux-claude \
  --tmux-target 1.2
```

### `start` — 初始化并持续驱动

等同于 `init`（如尚未初始化）+ `drive`。是最常用的启动命令。

```bash
python -m workflow_controller.cli start \
  --state-dir .rrc-controller-v1.0 \
  --verbose
```

### `drive` — 持续驱动，停在人工 gate

从已有 session 继续执行，遇到人工确认 gate 时暂停，等待 Plannotator 或终端操作。

```bash
python -m workflow_controller.cli drive \
  --state-dir .rrc-controller-v1.0
```

### `run` — 执行单步或跑到结束

```bash
# 执行一步
python -m workflow_controller.cli run --state-dir .rrc-controller-v1.0

# 跑到 done/blocked/failed
python -m workflow_controller.cli run --state-dir .rrc-controller-v1.0 --until-done
```

### `status` — 查看当前状态

```bash
python -m workflow_controller.cli status --state-dir .rrc-controller-v1.0
```

### `approve` — 手动批准 gate

```bash
# 批准 unit-plan gate
python -m workflow_controller.cli approve \
  --state-dir .rrc-controller-v1.0 \
  --gate unit-plan

# 可用 gate 名称：requirements | unit-plan | final-acceptance
```

### `reject` — 拒绝最终验收

```bash
python -m workflow_controller.cli reject --state-dir .rrc-controller-v1.0
```

### `revise` — 触发返工

```bash
python -m workflow_controller.cli revise \
  --state-dir .rrc-controller-v1.0 \
  --gate unit-plan

# 可用 gate 名称：requirements | unit-plan
```

### `migrate` — 迁移旧 gate 格式

用于升级旧版本生成的 state-dir，修复 gate 文件格式不兼容问题：

```bash
python -m workflow_controller.cli migrate --state-dir .rrc-controller-v1.0
```

---

## 典型工作流

```
start / drive
  │
  ├─ run_requirements_drafter
  │    └─ WAITING_REQUIREMENTS_ACCEPTANCE  ← Plannotator 审阅，浏览器 Approve 继续
  │
  ├─ run_unit_plan_drafter
  │    └─ WAITING_UNIT_PLAN_APPROVAL       ← Plannotator 审阅，浏览器 Approve 继续
  │
  ├─ run_builder → run_verifier
  │    └─ 通过后进入下一单元或 final acceptance
  │
  └─ WAITING_FINAL_ACCEPTANCE              ← Plannotator 审阅，浏览器 Approve 完成
```

---

## 人工 Gate 操作

| 操作 | 说明 |
|------|------|
| 浏览器点 **Approve** | 自动写入确认文件并继续，无需回终端 |
| 浏览器点 **Close** | 保持 pending，等待下次检查 |
| 浏览器添加批注后点 **Approve** | 批注写入 Claude 下一轮 prompt |
| 终端按 `r` | 直接触发返工，跳过浏览器 |
| 终端按 `a` | 直接批准当前 gate |

---

## 常用参数速查

### `init` / `start` / `drive` 公共参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--state-dir` | 存放 `session.json` 和 `artifacts/` 的目录 | 必填 |
| `--workspace-dir` | 项目工作区目录 | 可选 |
| `--target` | 目标标签，如 `V1.0` | 可选 |
| `--runner` | `subprocess`、`tmux-claude` 或 `tmux-codex` | 未指定时由 `go`/tmux target 解析 |
| `--tmux-target` | tmux pane 地址，如 `1.2` | 可选；未传且在 tmux 内时自动创建 Claude pane |
| `--agent` | 覆盖 agent 命令字符串 | 可选 |
| `--force` | 强制重新初始化，覆盖已有 `session.json` | 关闭 |
| `--auto-approve` | 自动批准低风险 gate（测试/干跑用） | 关闭 |
| `--unsafe-skip-human-gates` | 绕过所有人工 gate（仅用于自动化测试） | 关闭 |
| `--test-strategist` | 启用 Test Strategist 独立挑战测试策略 | 关闭 |
| `--test-strategist-command` | Test Strategist 子进程命令（默认沿用全局 runner） | 可选 |
| `--test-strategist-env KEY=VALUE` | 注入 Test Strategist 专属环境变量（可重复） | 可选 |

### `go` 推断规则

| 参数/输入 | 未显式传入时的行为 |
|-----------|--------------------|
| `TARGET` / `--target` | 用作目标标签；两者同时传入且不一致时报错 |
| `--state-dir` | 有 target 时推断为 `<workspace-dir>/.rrc-controller-<target-slug>`；未显式传 `--workspace-dir` 时表现为当前目录下的 `.rrc-controller-<target-slug>` |
| target slug | 小写；保留字母、数字、点、下划线、连字符；其他字符替换为 `-`；去掉首尾 `-` |
| `--workspace-dir` | 当前目录；指定 `--tmux-target` 且未显式传 workspace 时，使用目标 pane 当前目录 |
| `--runner` | 传了 `--tmux-target` 时自动识别 `tmux-codex` / `tmux-claude`；未传 target 且在 tmux 内时自动创建 Claude pane；显式 `--runner subprocess` 不使用 tmux |

### `start` / `drive` 运行时参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--max-steps` | 最大自动步数 | 2000 |
| `--dry-run` | 模拟执行，写 mock artifacts，不调用真实 agent | 关闭 |
| `--verbose` | 显示每步完整输出 | 关闭 |
| `--color` | `auto` / `always` / `never`；有色模式突出自动打回/阻塞和 AO/AC/Test Case/Journey/unit 定位符 | `auto` |
| `--actor` | 人工 gate 确认时记录的操作人名称 | `human` |
| `--plannotator-port` | Plannotator 监听端口 | `20000` |
| `--plannotator-command` | 覆盖 Plannotator 启动命令 | 可选 |

---

## 目录结构

```
.rrc-controller-v1.0/
├── session.json                  # 当前工作流状态
├── events.jsonl                  # 状态变更事件日志
├── approvals/
│   ├── requirements-and-acceptance.md   # 需求人工确认文件
│   ├── unit-plan.md                     # Unit Plan 人工确认文件
│   └── final-acceptance.md              # 最终验收确认文件
└── artifacts/
    ├── requirements-draft/
    │   ├── requirements-body.md          # Plannotator 审阅文件
    │   └── requirements-draft-summary.json
    ├── unit-plan-draft/
    │   ├── unit-plan-body.md             # Plannotator 审阅文件
    │   ├── unit-plan-draft-summary.json
    │   ├── test-strategy.json            # Test Strategist 输出（启用时）
    │   ├── unit-plan-gap-report.json     # Gap report（启用时）
    │   └── unit-plan-review-package.json
    └── <unit-id>/
        ├── builder-summary.json
        ├── changed-files.txt
        └── verification.json
```

---

## Test Strategist（默认关闭）

启用后 controller 在 Unit Plan draft 阶段调用第二个模型（Test Strategist）独立挑战测试策略，Critical gap 自动触发 Unit Planner 返工，Major/Minor gap 写入现有 Unit Plan gate 供人工统一判断，不新增任何人工审批阶段。

### 启用方式

**最简启用**（沿用全局 runner 命令）：

```bash
python -m workflow_controller.cli start \
  --state-dir .rrc-controller-v1.0 \
  --test-strategist
```

**指定独立命令和代理环境**（推荐用于 Codex 等需要单独代理的 runner）：

```bash
python -m workflow_controller.cli start \
  --state-dir .rrc-controller-v1.0 \
  --test-strategist \
  --test-strategist-command "codex exec --dangerously-bypass-approvals-and-sandbox -" \
  --test-strategist-env HTTP_PROXY=http://127.0.0.1:7890 \
  --test-strategist-env HTTPS_PROXY=http://127.0.0.1:7890 \
  --test-strategist-env NO_PROXY=localhost,127.0.0.1
```

`--test-strategist-env` 可重复使用，每次传一个 `KEY=VALUE`。这些 env 只注入 Test Strategist 子进程，不影响 Unit Planner、Builder、Reviewer 或 Verifier。

### 行为说明

| 场景 | 行为 |
|------|------|
| 无 Critical gap | 生成 Review Package，进入现有 `WAITING_UNIT_PLAN_APPROVAL` |
| 有 Critical gap（第 1、2 次） | 阻止写 Unit Plan gate，整理 gap feedback，触发 Unit Planner 返工 |
| 有 Critical gap（第 3 次） | workflow blocked，`blockedReason` 包含 gap id 和 retry count |
| Major/Minor gap | 写入 `## Test Strategy Gap Report`，不阻断流程 |
| codex 不可用（允许 fallback） | 降级到全局 runner，summary 标记 `actual_independence=same_family_fallback` |
| codex 不可用（禁止 fallback） | workflow blocked，输出可操作 blocker |

### 产出 artifacts

| 文件 | 内容 |
|------|------|
| `test-strategy.json` | 验收标准 → 测试用例矩阵，含层级、命令、fixture、证据 |
| `unit-plan-gap-report.json` | gap id、severity、类型、原因 |
| `unit-plan-review-package.json` | Unit Planner 与 Test Strategist 合并后的审核对象 |
| `unit-plan-draft-summary.json` | enabled 状态、runner、independence、gap counts、retry count |

所有 artifacts 只记录 env key，不记录代理地址、token 或 secret 明文。

---

## Final Acceptance 返工路由

最终验收拒绝时，终端菜单提供三条路由：

| 选项 | 路由 | 说明 |
|------|------|------|
| `1` | Defect fix | 不改需求，生成 bug-fix units 修复已完成单元的缺陷 |
| `2` | Requirements change | 重新走 Requirements Draft 流程 |
| `3` | Unit plan revision | 保留需求，只重新生成 Unit Plan |

---

## 运行测试

```bash
source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate

# 全量
python -m pytest workflow_controller/tests -q

# 分模块
python -m pytest workflow_controller/tests/test_rrc_controller.py -q
python -m pytest workflow_controller/tests/test_rrc_human_gates.py -q
python -m pytest workflow_controller/tests/test_rrc_agent_runners.py -q
python -m pytest workflow_controller/tests/test_rrc_real_runtime.py -q

# 新模块子目录
python -m pytest workflow_controller/tests/state_machine/ -q
python -m pytest workflow_controller/tests/gates/ -q
python -m pytest workflow_controller/tests/runners/ -q
python -m pytest workflow_controller/tests/steps/ -q

# 单个用例
python -m pytest workflow_controller/tests/test_rrc_controller.py::test_e2e_test_strategist_unit_plan_flow -q
```

---

## 故障排查

| 现象 | 可能原因 | 处理方式 |
|------|---------|---------|
| `当前没有可执行的下一步` | 状态卡住 | `status` 查看当前 step，必要时 `migrate` 修复旧 gate 格式 |
| Unit Plan gate invalid | 静态检查只有 tsc/lint、缺 Test Case Matrix 或缺验证环境 | 按 `r` 返工，补充 `## Test Case Matrix` 和 `verification_env` |
| `blocked: Test strategist failed` | codex 不可用且禁止 fallback | 检查 codex 安装或在 `roleRunners` 中改用其他 runner |
| verification 命令返回 127 | verifier 在 `/bin/sh` 下执行了 `source` | verification command 改用 bash 内建命令或 venv 绝对路径 |
| Plannotator 未响应 | 端口冲突或 Plannotator 未启动 | 检查 `--plannotator-port`，或手动用 `approve` 命令批准 gate |
| ImportError 导入失败 | 包路径或虚拟环境未激活 | 确认在工作区根目录，且已激活 Hermes venv |
