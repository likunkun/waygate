# Workflow Controller

Workflow Controller 是一个给 AI 编程任务用的“流程控制器”。

它不是新的聊天机器人，也不是另一个代码生成器。它做的事情更朴素：把一次容易失控的 AI 编程任务，拆成需求确认、任务计划、实现、精修、评审、验证、最终验收几个明确步骤；每一步都有状态、有文件、有证据，失败了能回到正确的位置继续修。

一句话说：

> 让 AI 写代码，但让 Controller 管范围、顺序、证据和完成判定。

## 为什么需要它

直接和 AI 聊天写代码，经常会遇到这些问题：

- 需求说着说着变了，最后做出来的不是一开始要的东西。
- AI 做了一半，就用一句“已经完成”结束。
- 测试有没有跑、跑了什么、结果是什么，都只存在聊天记录里。
- 长任务中途断了，再继续时只能靠上下文猜状态。
- 最终验收发现问题时，不知道该回需求、回计划、回实现，还是只修一个 bug。

Workflow Controller 的思路是：AI 可以负责产出草案和代码，但不能自己宣布完成。完成必须由状态机推进，并且要有可审计的 artifact。

## 现在能做什么

这个框架现在已经可以跑完整的 AI 编程交付流程：

```text
Requirements Draft
  -> Requirements Gate
  -> Unit Plan
  -> Unit Plan Gate
  -> Builder
  -> CodeSimplifier / Refiner
  -> Reviewer
  -> Verifier
  -> Final Acceptance Gate
  -> Done
```

如果最终验收发现缺陷，还能走独立的 bug fix 分支：

```text
Final Acceptance rejected as defect_fix
  -> Bug Fix Gate
  -> Bug Fix Agent
  -> Regression Verifier
  -> Final Acceptance Gate
```

已经可用的能力包括：

| 能力 | 说明 |
|---|---|
| 短命令启动 | `go V1.0` 自动推断 state-dir/workspace，并在 tmux 内自动创建 Claude pane；指定 `--tmux-target` 时自动识别 Codex/Claude。 |
| 可恢复状态机 | 所有进度写在 `session.json` 和 `events.jsonl`，中断后继续跑。 |
| 低噪声进度输出 | 默认 compact 模式只打印关键状态、短原因和人工 gate；`--color always` 会突出自动打回、阻塞和 AO/AC/Test Case/Journey/unit 定位符。 |
| 人工 Gate | Requirements、Unit Plan、Final Acceptance、Bug Fix 都生成 Markdown 审核文件；Requirements 和 Unit Plan 顶部先展示审批摘要，完整矩阵留在同一文件附录区。Unit Plan 预检失败默认最多自动打回 5 次。 |
| Plannotator 审阅 | 人工 gate 可用浏览器批注、批准或拒绝；默认打开 approval Markdown 本身，先看到顶部摘要。 |
| 单元化执行 | 每次只推进一个 unit，避免 AI 一口气改完整个世界。 |
| CodeSimplifier | Builder 后默认进入代码精修审查，不合格会打回 Builder。 |
| Reviewer | 独立审查风险、缺失测试和明显回归。 |
| Verifier | 执行验证命令，写入结构化 `verification.json`。 |
| Final Acceptance Matrix | 最终验收展示 AO、AC、Test Case、命令、结果和 artifact。 |
| Change Request Ledger | requirements 变更和最终验收需求返工会写入 `change_requests.jsonl`。 |
| Journey Acceptance | 用户旅程需要有 Unit Plan 映射和 verifier evidence，不能只靠自然语言说通过。 |
| Agent Guide 初始化 | 初始化时可生成 `AGENTS.md` 和标准 docs 目录。 |
| tmux runner | 可以把 Builder/Planner 等工作派到指定 tmux pane。 |
| dry-run | 可以不调用真实 agent，只生成 mock artifacts，用来测试流程。 |

## 适合什么场景

适合：

- 一个需求要拆成多步实现。
- 需要人工确认需求、计划和最终验收。
- 需要留下测试、审查、返工原因和最终证据。
- 需要让不同 agent role 分工，而不是一个模型从头包到尾。
- 长任务可能暂停、恢复、续跑。
- 团队想知道 AI 到底改了什么、为什么算完成。

不太适合：

- 一行脚本、一次性小改动。
- 没有明确验收标准的探索性聊天。
- 不关心证据、不需要恢复、不需要审计的临时实验。

## 三分钟上手

先进入项目根目录并激活环境：

```bash
cd /home/lichangkun/works/ai-works/worktrees/workflow-controller
source /home/lichangkun/.hermes/hermes-agent/venv/bin/activate
```

最常用的启动方式是在 tmux 里运行 `go`：

```bash
python -m workflow_controller.cli go V1.0
```

这条命令等价于“为 V1.0 创建或继续一个 controller session，然后持续驱动 workflow”。它会自动推断：

| 项 | 推断值 |
|---|---|
| target | `V1.0` |
| workspace-dir | 当前目录，也就是你运行命令时所在的目标项目根目录 |
| state-dir | `<workspace-dir>/.rrc-controller-v1.0`；未显式传 `--workspace-dir` 时表现为 `.rrc-controller-v1.0` |
| runner | 未传 `--tmux-target` 且在 tmux 内时自动创建 Claude pane 并使用 `tmux-claude`；传了 `--tmux-target` 时自动识别 `tmux-codex` 或 `tmux-claude` |

如果已经有可用的 Codex 或 Claude pane，可以显式指定：

```bash
python -m workflow_controller.cli go V1.0 --tmux-target 1.2
```

未显式传 `--workspace-dir` 时，指定已有 pane 会使用该 pane 的当前目录作为 workspace，state-dir 也会落在这个目录下。

如果你不是在目标项目根目录执行命令，应显式传入目标项目目录：

```bash
python -m workflow_controller.cli go V1.0 \
  --workspace-dir /path/to/target-project
```

此时 `state-dir` 会自动落在 `/path/to/target-project/.rrc-controller-v1.0`。

如果不想用 tmux，只想用本地 subprocess：

```bash
python -m workflow_controller.cli go V1.0 --runner subprocess
```

如果只是想试流程，不调用真实 agent：

```bash
python -m workflow_controller.cli go V1.0 --runner subprocess --dry-run --max-steps 20
```

更多 CLI 参数见 [USAGE.md](USAGE.md)。

## 一次运行时会发生什么

运行 `go` 后，Controller 会做这些事：

1. 如果 state-dir 不存在，先初始化 `session.json`、`approvals/`、`artifacts/`。
2. 生成 Requirements Gate，让人确认需求和验收标准；如果存在会导致方向做错的缺口，Requirements Drafter 会先在目标 tmux agent pane 里集中提问；如果草案没通过 controller 预检，会自动打回 drafter，不进入人工审核。
3. Requirements 批准后，生成 Unit Plan Gate，让人确认任务拆分和测试矩阵；如果 Unit Plan 草案没通过 controller 预检，会先自动打回 planner，不进入人工审核菜单。
4. Unit Plan 批准后，按 unit 调 Builder。
5. Builder 改完后，进入 CodeSimplifier / Refiner。
6. Refiner 通过后，进入 Reviewer。
7. Reviewer 通过后，进入 Verifier。
8. Verifier 写出真实验证证据。
9. 所有 unit 通过后，生成 Final Acceptance Gate。
10. 人工最终批准后，才进入 `DONE`。

如果某一步失败，不会硬往后走。例如：

| 失败位置 | Controller 怎么处理 |
|---|---|
| Requirements 不完整 | 留在 Requirements Gate，要求 revise。 |
| Unit Plan 缺测试、缺 AO/Journey 映射或 state patch 无效 | 人工审核前自动预检；失败时写入 controller validation artifact 并打回 planner。 |
| CodeSimplifier 要求修改 | 回 Builder。 |
| Reviewer 发现问题 | 回 Builder 或阻塞。 |
| Verifier 命令失败 | 记录 failure，回实现或阻塞。 |
| Final Acceptance 发现缺陷 | 根据路由回 requirements、unit_plan、implementation、bug_fix 或 blocked。 |

## 人需要做什么

这个框架不是让人完全退出流程。它把人放在最关键的几个判断点：

| Gate | 人要看什么 |
|---|---|
| Requirements Gate | 需求是否对，验收标准是否具体，用户旅程和范围有没有漏。 |
| Unit Plan Gate | unit 拆得是否合理，每条 AC 有没有测试或人工证据。 |
| Final Acceptance Gate | 证据矩阵是否可信，改动是否满足已批准需求。 |
| Bug Fix Gate | 缺陷是否属于已批准范围，回归验证是否足够。 |

需求阶段的澄清发生在目标 Claude/Codex pane 中，不走 controller 终端问卷。Agent 拿到回答后继续生成 gate，并把已澄清事项、关键假设和待确认风险写进 `requirements-and-acceptance.md`。Controller 能自己判定的 requirements / unit plan 质量问题会先自动返工；只有通过预检的 gate 才交给人审阅。

Requirements 和 Unit Plan approval Markdown 都是“摘要优先、细节后置”的单文件结构：文件顶部是 `## 审批摘要`，包含结论、变更点、需要人确认的点、验收命令和 Controller/Critic 检查摘要；完整 AO/AC/Journey/Test Case 矩阵、原始正文和 `## Controller State Patch` 保留在同一个 Markdown 的附录区。`## Human Confirmation` 只由 controller 自动追加，agent 不应生成。

Gate 都是 Markdown 文件，默认在：

```text
<state-dir>/approvals/
  requirements-and-acceptance.md
  unit-plan.md
  final-acceptance.md
  bug-fix.md
```

人工可以通过 Plannotator 在浏览器里批注和批准，也可以直接用 CLI：

```bash
python -m workflow_controller.cli approve \
  --state-dir .rrc-controller-v1.0 \
  --gate unit-plan
```

最终验收拒绝时：

```bash
python -m workflow_controller.cli reject --state-dir .rrc-controller-v1.0
```

Controller 会要求选择返工路由，而不是把所有问题都粗暴丢回实现阶段。

## 交互流程与 Prompt

一次完整运行里，Controller 发给 agent 或展示给人的交互是固定的。每一步的 prompt 都会落到 artifact，人工审核看到的是由这些 prompt 生成或汇总出来的 gate 文档。

| 顺序 | 阶段 | 发给谁 | Prompt / 文档路径 | 人工是否审核 | 目的 |
|---|---|---|---|---|---|
| 1 | Requirements Draft | Requirements Drafter | `<state-dir>/artifacts/requirements-draft/requirements-draft-prompt.md` | 否 | 生成需求、AC、AO、用户旅程、测试策略草案；必要时在目标 agent pane 里集中提问后继续。 |
| 2 | Requirements Gate | Human | `<state-dir>/approvals/requirements-and-acceptance.md` | 是 | 冻结需求范围、验收标准、产品设计概要和架构概要。 |
| 3 | Requirements Revision | Requirements Drafter | `<state-dir>/artifacts/requirements-revisions/revision-<n>.json` 记录差异 | 是 | 根据人工批注返工，并记录每轮 revision diff。 |
| 4 | Unit Plan Draft | Unit Planner / Test Strategist | `<state-dir>/artifacts/unit-plan-draft/unit-plan-draft-prompt.md` | 否 | 生成 unit 拆分、测试用例矩阵、journey 映射和 state patch。 |
| 5 | Unit Plan Gate | Human | `<state-dir>/approvals/unit-plan.md` | 是 | 确认任务粒度、测试覆盖、E2E 闭环和执行顺序。 |
| 6 | Builder | Builder | `<state-dir>/artifacts/<unit-id>/builder-prompt.md` | 否 | 只实现当前 unit，并优先补齐 AC 对应测试。 |
| 7 | Refiner | CodeSimplifier / Refiner | `<state-dir>/artifacts/<unit-id>/code-simplifier-prompt.md` | 否 | 保持行为不变地精修代码；发现问题可打回 Builder。 |
| 8 | Reviewer | Reviewer | `<state-dir>/artifacts/<unit-id>/review-prompt.md` 或 runner artifact | 否 | 独立审查风险、缺失测试和明显回归。 |
| 9 | Verifier | Verifier / test runner | `verification_commands` 和 `<state-dir>/artifacts/<unit-id>/verification.json` | 否 | 运行真实验证命令，写入 exit code、stdout/stderr 和 evidence rows。 |
| 10 | Final Acceptance Gate | Human | `<state-dir>/approvals/final-acceptance.md` | 是 | 对照最终证据矩阵、journey evidence 和 scope audit 判断是否交付。 |
| 11 | Bug Fix Gate | Human + Bug Fix Agent | `<state-dir>/approvals/bug-fix.md`、`<state-dir>/artifacts/bug-fixes/<bug-fix-id>/bug-fix-prompt.md` | 是 | 最终验收缺陷进入独立修复和回归验证，不偷改需求。 |

## 交付物长什么样

Controller 的 state-dir 是整个 workflow 的事实源。一个典型目录如下：

```text
.rrc-controller-v1.0/                         # 当前 target 的 controller state-dir，默认位于目标项目根目录下
  session.json                                # 主状态文件；Controller 根据它决定下一步
  events.jsonl                                # append-only 事件日志；记录状态推进和 gate 操作
  change_requests.jsonl                       # 需求变更账本；记录已批准需求之后的变更请求
  approvals/                                  # 人工审核 gate 文档目录
    requirements-and-acceptance.md            # Requirements Gate；冻结需求、AC、AO、设计/架构和测试策略
    unit-plan.md                              # Unit Plan Gate；冻结 unit 拆分、测试矩阵和 state patch
    final-acceptance.md                       # Final Acceptance Gate；展示最终证据矩阵和返工路由
    bug-fix.md                                # Bug Fix Gate；记录验收缺陷、根因和修复边界
  artifacts/                                  # Agent、Verifier 和 Controller 生成的审计证据
    requirements-draft/                       # Requirements Drafter 的输入、正文和摘要
      requirements-draft-prompt.md            # 发给 Requirements Drafter 的完整 prompt
      requirements-body.md                    # Requirements Drafter 原始正文草案；approval Markdown 会把它包装成摘要优先结构
      controller-validation-error.json        # Requirements 自动预检失败的完整原因，终端只打印短摘要
      requirements-draft-summary.json         # Requirements Drafter 运行摘要和 runner metadata
    unit-plan-draft/                          # Unit Planner / Test Strategist 的产物目录
      unit-plan-draft-prompt.md               # 发给 Unit Planner 的完整 prompt
      unit-plan-body.md                       # Unit Plan 原始正文草案；approval Markdown 会把它包装成摘要优先结构
      controller-validation-error.json        # Unit Plan 自动预检失败的完整原因，终端只打印短摘要
      test-strategy.json                      # Test Strategist 结构化测试策略
      unit-plan-gap-report.json               # Test Strategist 发现的测试策略缺口
      unit-plan-review-package.json           # 合并给人工 gate 的测试策略审查包
    <unit-id>/                                # 单个执行 unit 的 Builder/Refiner/Reviewer/Verifier 证据
      builder-prompt.md                       # 发给 Builder 的当前 unit prompt
      builder-summary.json                    # Builder 完成摘要和 runner metadata
      changed-files.txt                       # Builder 或后续阶段声明的变更文件
      code-simplifier-prompt.md               # 发给 CodeSimplifier / Refiner 的行为保持精简 prompt
      simplifier-result.json                  # CodeSimplifier / Refiner 结构化结果
      review-summary.json                     # Reviewer 审查摘要
      verification.json                       # Verifier 结构化证据，包含命令结果和 evidence_rows
    bug-fixes/                                # 独立缺陷修复环节的证据目录
      <bug-fix-id>/                           # 单个 bug fix 的根因、修复和回归证据
        bug-fix-prompt.md                     # 发给 Bug Fix Agent 的缺陷修复 prompt
        root-cause.json                       # 根因分类和路由判断
        bug-fix-summary.json                  # Bug Fix Agent 修复摘要
        verification.json                     # 缺陷修复后的回归验证证据
    journeys/                                 # Journey Acceptance 证据目录
      journeys.json                           # 结构化用户旅程契约
      journey-evidence.json                   # Journey 验证结果和证据行
```

最重要的文件：

| 文件 | 用途 |
|---|---|
| `session.json` | 当前状态。Controller 根据它决定下一步能做什么。 |
| `events.jsonl` | append-only 事件日志，用来追踪发生过什么。 |
| `approvals/*.md` | 人工审核 gate。正文变化后旧 approval 会变 stale。 |
| `verification.json` | Verifier 的结构化证据，包含命令、退出码、状态和 evidence rows。 |
| `final-acceptance.md` | 最终验收矩阵，把需求、测试和证据串起来。 |
| `change_requests.jsonl` | requirements 变更审计记录。 |
| `root-cause.json` | bug fix 分支的根因分类和路由依据。 |

## 人工审核文档样例

下面是四类人工审核文档的完整骨架。实际运行时这些文件会带有 gate 元信息、内容 hash、批准状态和 Controller State Patch；人工只需要在对应 gate 上审阅、批注、批准或拒绝。

### Requirements Gate 样例

路径：`.rrc-controller-v1.0/approvals/requirements-and-acceptance.md`

```markdown
# 需求与验收确认

## 审批摘要

### 结论
- 待人工确认 Requirements 与 Acceptance Criteria 后进入 Unit Plan。

### 变更点
- 请求目标：`V1.0`
- 可行目标：`V1.0`
- 当前单元：`target-v1-0`
- AO 覆盖要求：3 条 active must AO 需要在 AC 中覆盖。

### 需要人确认的点
- 需求描述、用户旅程和验收标准是否准确。
- 每条 AC 是否声明 verification layer，并能被测试或人工证据验证。
- Product Design / Technical Architecture 引用是否足以支持后续执行。
- Journey Acceptance Matrix 是否覆盖跨单元闭环。

### 验收命令
- `python -m pytest workflow_controller/tests/test_rrc_controller.py -q`
- `python -m pytest workflow_controller/tests/test_rrc_e2e.py -q`

### Controller/Critic 检查摘要
- Controller 会在人工确认前预检 AO/AC 映射、verification layer、设计/架构引用和 Journey 合约。
- Critic：未配置独立审批模型；最终确认仍由人或 controller 规则完成。

## 附录 A：完整需求与验收正文

## 1. 需求
- 请求目标：`V1.0`
- 可行目标：`V1.0`
- 当前单元：`target-v1-0`
- 背景：用户需要在一个受控 AI 编程流程中完成 V1.0 交付。
- 范围：初始化 controller state、生成人工 gate、按 unit 执行、验证并最终验收。

## 2. 用户旅程
- JOURNEY-001：用户启动 `go V1.0`，审核 Requirements、Unit Plan、Final Acceptance，并看到可追溯证据。
- 正常路径：init -> requirements approve -> unit plan approve -> builder/refiner/reviewer/verifier -> final approve。
- 异常路径：requirements 批注后 revise；final acceptance 拒绝后进入 defect_fix。

## 3. 验收标准
- AC-001 [verification: functional]：`go V1.0 --workspace-dir /target/project` 在目标项目目录下生成 state-dir。
- AC-002 [verification: e2e]：一个完整 unit 从 Builder 到 Verifier 后进入 Final Acceptance。
- AC-003 [verification: manual]：人工 gate 展示 AO、AC、Test Case、Evidence 的追溯关系。

## 4. 需求可追溯矩阵（Requirements Traceability Matrix）

| AO | AC | Status | Verification Layer | Evidence/Reason |
| --- | --- | --- | --- | --- |
| AO-001 | AC-001 | covered | functional | CLI integration test |
| AO-002 | AC-002 | covered | e2e | tmux runner e2e test |
| AO-003 | AC-003 | covered | manual | final acceptance gate sample |

## 4.5 设计与架构可追溯矩阵（Design/Architecture Traceability Matrix）

| AC | Product Design Ref | Technical Architecture Ref | Notes |
| --- | --- | --- | --- |
| AC-001 | docs/product/controller-startup.md | docs/architecture/state-dir.md | 展示 workspace/state-dir 推断规则 |
| AC-002 | docs/product/human-gates.md | docs/architecture/state-machine.md | 覆盖端到端交付旅程 |
| AC-003 | docs/product/review-documents.md | docs/architecture/evidence-schema.md | 说明人工审核材料结构 |

## 5. 测试策略（Test Strategy）
- 功能测试：验证 CLI 参数解析、state-dir 推断、gate 校验、状态转移。
- 集成测试：验证 requirements -> unit plan -> builder -> verifier 的最短闭环。
- E2E 测试：使用 fake runner 或 tmux runner 跑完整 workflow。
- 人工证据：Final Acceptance Gate 必须展示 evidence matrix 和 scope audit。

## 6. 范围外
- 不实现 CI 作为最终权威验证源。
- 不实现每个 unit 的独立 workspace/branch 隔离。

## 7. 产品设计概要
- 主要用户流程：用户用一个命令启动目标交付，Controller 在关键 gate 暂停等待确认。
- 关键页面/状态：Markdown gate、Plannotator 审阅页、CLI status line。
- 验收示意：最终文档能明确显示每条 AC 对应的测试、命令、结果和 artifact。

## 8. 架构概要
- 模块边界：CLI、StateStore、Gate generator/parser、Step runner、Verifier。
- 数据流：CLI args -> session.json -> prompt artifacts -> runner result -> verification evidence -> final gate。
- 外部依赖：pytest、tmux runner、可选 Plannotator。
- 主要风险：测试证据不足、人工 gate 被绕过、runner 输出格式不稳定。

## 9. 人工审阅清单
- [ ] 需求描述准确。
- [ ] 用户旅程覆盖正常、异常、权限、重试和持久化路径。
- [ ] 每条 AC 都声明 verification layer。
- [ ] 每个 active must AO 都映射到 AC，或明确 deferred/rejected/out_of_scope。
- [ ] 产品设计概要足以让评审者理解用户体验。
- [ ] 架构概要足以让评审者理解模块边界和风险。
```

### Unit Plan Gate 样例

路径：`.rrc-controller-v1.0/approvals/unit-plan.md`

```markdown
# 单元计划确认（Unit Plan Confirmation）

## 审批摘要

### 结论
- 待人工确认 Unit Plan 后进入执行阶段。

### 变更点
- 当前单元：`unit-v1-0-controller-start`
- 待执行单元数：2 / 2
- `partial` V1.0 controlled delivery -> unit-v1-0-controller-start, unit-v1-0-delivery-loop

### 需要人确认的点
- 每个目标是否映射到一个或多个可执行 unit。
- 每条非 manual AC 是否有 Test Case、fixture/setup、命令或人工证据、具体 expected assertion。
- Journey 是否映射到 closure 或 E2E 测试用例，并在 `test_cases[]` JSON 中写入 `covers_journeys` 或 `journey_ids`。
- Controller State Patch 是否只改变当前计划允许的 state 字段。

### 验收命令
- `python -m pytest workflow_controller/tests/test_rrc_controller.py -q`
- `python -m pytest workflow_controller/tests/test_rrc_e2e.py -q`

### Controller/Critic 检查摘要
- Controller 会在进入人工确认前预检 Controller State Patch、AO 覆盖、测试用例覆盖、验证环境、Golden Path 和 Journey 映射。
- Critic：未配置独立审批模型；最终确认仍由人或 controller 规则完成。

## 附录 A：目标覆盖矩阵
- `partial` V1.0 controlled delivery -> unit-v1-0-controller-start, unit-v1-0-delivery-loop

## 附录 B：测试用例矩阵（Test Case Matrix）

| 验收标准 | 测试用例 | Journey | 层级 | 产品设计引用 | 技术架构引用 | 测试数据/Fixture | 命令/证据 | 预期结果 |
|---|---|---|---|---|---|---|---|---|
| AC-001 | TC-001 | - | functional | docs/product/controller-startup.md | docs/architecture/state-dir.md | tmp target project | `python -m pytest workflow_controller/tests/test_rrc_controller.py -q` | state-dir 位于目标项目下 |
| AC-002 | TC-002 | JOURNEY-001 | e2e | docs/product/human-gates.md | docs/architecture/state-machine.md | fake tmux runner | `python -m pytest workflow_controller/tests/test_rrc_e2e.py -q` | workflow 到达 Final Acceptance |

Journey 映射必须进入 Controller State Patch 的 `test_cases[]` 结构化字段。推荐字段是 `covers_journeys: ["J-..."]` 或 `journey_ids: ["J-..."]`；controller 也兼容历史别名 `journey_refs` / `journeyRefs`，但新输出不应优先使用这些别名。只在 Markdown 说明、Journey Acceptance Matrix、产品设计引用或技术架构引用里写 Journey id，不能算作 Unit Plan gate 的 Journey 映射。

## Journey Acceptance Matrix

| Journey | Linked AC | Unit | Verification | Required Evidence |
|---|---|---|---|---|
| JOURNEY-001 | AC-001, AC-002, AC-003 | unit-v1-0-delivery-loop | e2e | verification.json + final-acceptance.md |

## 附录 C：执行单元

### unit-v1-0-controller-start - Controller 启动与 state-dir 推断
- Workflow validation level: `fragment`
- Scope:
  - 实现 `go TARGET --workspace-dir` 的目标项目 state-dir 推断。
  - 缺少 TARGET 且未显式传 `--state-dir` 时拒绝启动。
- Non-goals:
  - 不引入 CI 权威验证。
- Verification commands:
  - `python -m pytest workflow_controller/tests/test_rrc_controller.py -q`

### unit-v1-0-delivery-loop - 端到端交付闭环
- Workflow validation level: `closure`
- Scope:
  - 通过 fake runner 覆盖 requirements、unit plan、builder、refiner、verifier、final acceptance。
- Verification commands:
  - `python -m pytest workflow_controller/tests/test_rrc_e2e.py -q`

## Controller State Patch

~~~json
{
  "currentUnitId": "unit-v1-0-controller-start",
  "objectiveCoverage": [
    {
      "objective": "V1.0 controlled delivery",
      "units": ["unit-v1-0-controller-start", "unit-v1-0-delivery-loop"],
      "status": "partial"
    }
  ],
  "units": [
    {
      "id": "unit-v1-0-controller-start",
      "name": "Controller 启动与 state-dir 推断",
      "passes": false,
      "workflow_validation_level": "fragment",
      "test_cases": [
        {
          "id": "TC-001",
          "acceptance_criterion": "AC-001",
          "layer": "functional",
          "fixture": "tmp target project",
          "command": "python -m pytest workflow_controller/tests/test_rrc_controller.py -q",
          "expected": "state-dir 位于目标项目下"
        }
      ],
      "verification_commands": ["python -m pytest workflow_controller/tests/test_rrc_controller.py -q"]
    },
    {
      "id": "unit-v1-0-delivery-loop",
      "name": "端到端交付闭环",
      "passes": false,
      "workflow_validation_level": "closure",
      "test_cases": [
        {
          "id": "TC-002",
          "acceptance_criterion": "AC-002",
          "covers_journeys": ["JOURNEY-001"],
          "layer": "e2e",
          "golden_path": true,
          "fixture": "fake tmux runner",
          "command": "python -m pytest workflow_controller/tests/test_rrc_e2e.py -q",
          "expected": "workflow 到达 Final Acceptance"
        }
      ],
      "verification_commands": ["python -m pytest workflow_controller/tests/test_rrc_e2e.py -q"]
    }
  ]
}
~~~

## 附录 D：人工审阅清单
- [ ] unit 粒度足够小，可以独立实现和验证。
- [ ] journey acceptance 覆盖了跨 unit 的真实用户闭环。
- [ ] 每条非 manual AC 都有可执行测试命令。
- [ ] E2E 用例不是截图替代断言。
- [ ] Controller State Patch 不删除或弱化已批准 AC。
```

### Final Acceptance Gate 样例

路径：`.rrc-controller-v1.0/approvals/final-acceptance.md`

```markdown
# 最终验收确认

## 结果
- Requested outcome: `V1.0`
- Feasible outcome: `V1.0`
- Overall status: pending human approval

## 目标覆盖

| Objective | Units | Status |
|---|---|---|
| V1.0 controlled delivery | unit-v1-0-controller-start, unit-v1-0-delivery-loop | covered |

## 证据摘要

| Unit | Stage | Status | Artifact |
|---|---|---|---|
| unit-v1-0-controller-start | Verifier | passed | artifacts/unit-v1-0-controller-start/verification.json |
| unit-v1-0-delivery-loop | Verifier | passed | artifacts/unit-v1-0-delivery-loop/verification.json |

## Final Acceptance Evidence Matrix

| AO | AC | Test Case | Layer | Status | Evidence | Expected | Artifacts |
|---|---|---|---|---|---|---|---|
| AO-001 | AC-001 | TC-001 | functional | passed | pytest exit 0 | state-dir 位于目标项目下 | artifacts/unit-v1-0-controller-start/verification.json |
| AO-002 | AC-002 | TC-002 | e2e | passed | pytest exit 0 | workflow 到达 Final Acceptance | artifacts/unit-v1-0-delivery-loop/verification.json |
| AO-003 | AC-003 | TC-003 | manual | pending | human review | evidence matrix 可读且完整 | approvals/final-acceptance.md |

## Journey Matrix

| Journey | Status | Evidence | Missing |
|---|---|---|---|
| JOURNEY-001 | passed | journey-evidence.json + verification.json | - |

## Final Scope Audit

| Category | Result | Notes |
|---|---|---|
| Covered requirements | passed | AC-001, AC-002, AC-003 均有 evidence |
| Uncovered requirements | passed | 无 |
| Out-of-scope changes | passed | 未发现超范围修改 |
| Unexplained diff | passed | changed files 均映射到 unit |

## Bug Fix Evidence
- No active defect_fix route.
- 如存在 bug fix，必须列出 `root-cause.json`、`bug-fix-summary.json` 和回归 `verification.json`。

## 变更文件
- workflow_controller/rrc_controller.py
- workflow_controller/tests/test_rrc_controller.py
- README.md

## 返工路由（Rejection Routing）
- 需求变更: requirements
- 计划/测试问题: unit_plan
- 实现问题: implementation
- 已批准范围内缺陷: defect_fix
- 外部阻塞: blocked

## 人工审阅清单
- [ ] Evidence matrix 中每条 covered AC 都有真实证据。
- [ ] Journey evidence 能证明跨 unit 闭环可用。
- [ ] Scope audit 未发现未覆盖需求或超范围改动。
- [ ] 如拒绝，已选择明确返工路由并写明反馈。
```

### Bug Fix Gate 样例

路径：`.rrc-controller-v1.0/approvals/bug-fix.md`

```markdown
# Bug Fix Gate

- Bug Fix ID: `bug-fix-1`
- Scope: 只修复已批准 requirements 下的缺陷；不得新增、删除或弱化 AC。

## Final Acceptance Defect Feedback
- Final Acceptance 中发现 AC-002 的 E2E 闭环失败：Verifier 通过了单元命令，但真实 journey 没有生成 `journey-evidence.json`。

## Expected Behavior
- JOURNEY-001 应能从启动、审核、执行、验证到 Final Acceptance 形成完整证据链。

## Actual Behavior
- `verification.json` 存在，但 `journey-evidence.json` 缺失，Final Acceptance Matrix 无法证明跨 unit 闭环。

## Root Cause
- Classification: implementation_bug
- Summary: Verifier 只写入 unit evidence，未同步 journey evidence。
- Route: defect_fix

## Regression Verification
- 添加或更新回归测试：`python -m pytest workflow_controller/tests/test_rrc_verifier.py -q`
- 重新生成 `artifacts/journeys/journey-evidence.json`。
- Final Acceptance Gate 必须显示 JOURNEY-001 passed。

## 人工审阅清单
- [ ] 缺陷属于已批准范围。
- [ ] 根因分类合理。
- [ ] 修复没有修改 requirements 或 AC。
- [ ] 回归验证能防止同类问题复发。
```

## 为什么它比“聊天式完成”可靠

### 1. AI 不能自己宣布完成

Builder 可以写代码，Reviewer 可以给意见，Verifier 可以跑命令，但最终状态必须由 Controller 推进。自然语言“完成了”不等于完成。

### 2. 需求先冻结，再实现

Requirements Gate 批准前不会进入 Unit Plan。实现阶段不能偷偷弱化 AC，也不能把新需求混进 bug fix。

### 3. 每个 unit 都要有证据

Unit Plan 里会定义 verification commands 和 test cases。Verifier 执行后写入 artifact，Final Acceptance 再读取这些证据。

### 4. 返工有路由

最终验收失败不只有“重做”一种选择：

| 路由 | 什么时候用 |
|---|---|
| `requirements` | 需求本身错了或漏了。 |
| `unit_plan` | 需求对，但拆分、测试或架构计划不对。 |
| `implementation` | 计划对，实现没做好。 |
| `defect_fix` | 已完成内容里有缺陷，需要定向修复和回归验证。 |
| `blocked` | 环境、权限、数据或证据不足，暂时不能判断。 |

### 5. 长任务能恢复

状态不靠聊天上下文，而是写在 state-dir 里。断了以后重新跑：

```bash
python -m workflow_controller.cli go V1.0 --tmux-target 1.2
```

如果 `.rrc-controller-v1.0/session.json` 已存在，Controller 会续跑；如果 target、runner、tmux target 等关键参数冲突，会拒绝继续，避免串错任务。

## 常用命令

| 命令 | 作用 |
|---|---|
| `go TARGET` | 推荐入口。推断常用参数，初始化或续跑。 |
| `init` | 只初始化 state，不启动 workflow。 |
| `start` | state 不存在时 init，然后持续 drive。 |
| `drive` | 从已有 state 持续推进，停在人工 gate。 |
| `run` | 只执行一步，或 `--until-done` 跑到终态。 |
| `status` | 查看当前 step、status 和 next action。 |
| `approve` | 批准 requirements、unit-plan、final-acceptance 或 bug-fix gate。 |
| `reject` | 拒绝 Final Acceptance 并进入返工路由。 |
| `revise` | 对 requirements 或 unit-plan gate 触发返工。 |
| `migrate` | 迁移旧 state/gate 格式。 |

例子：

```bash
# 查看状态
python -m workflow_controller.cli status --state-dir .rrc-controller-v1.0

# 执行一步
python -m workflow_controller.cli run --state-dir .rrc-controller-v1.0

# 持续推进已有 session
python -m workflow_controller.cli drive --state-dir .rrc-controller-v1.0

# 批准最终验收
python -m workflow_controller.cli approve \
  --state-dir .rrc-controller-v1.0 \
  --gate final-acceptance
```

## Runner 怎么接

当前支持的 runner 后端包括：

| Runner | 适合场景 |
|---|---|
| `subprocess` | 本地命令式 agent，适合测试、dry-run 或简单集成。 |
| `tmux-claude` | 把 prompt 派发到已有 tmux pane 里的 Claude Code。 |
| `tmux-codex` | 把 prompt 派发到已有 tmux pane 里的 Codex。 |
| `codex` / `opencode` | runner 抽象中已有适配或预留。 |

最常用的是 tmux：

```bash
python -m workflow_controller.cli go V1.0
```

未指定 `--tmux-target` 时，controller 必须运行在 tmux 内，会自动在右侧创建 Claude pane。指定已有 pane 时，controller 会检测目标里运行的是 Codex 还是 Claude：

```bash
python -m workflow_controller.cli go V1.0 --tmux-target 1.2
```

`tmux-codex` 使用 Codex TUI 的 Enter 提交语义。Codex 写出 `DONE_FILE` 后，controller 会先确认目标 pane 已离开 `Working` 状态，再推进下一步；这样可以避免上一轮 agent 尚未完全退出时，下一轮 prompt 被粘到 Codex 的排队输入框里，看起来像“回车没有发出去”。

## Agent 角色

这个框架把“AI 做任务”拆成多个角色：

| 角色 | 职责 |
|---|---|
| Requirements Drafter | 写需求、验收标准、用户旅程和追溯矩阵；仅在关键缺口会导致方向错误时，在目标 agent pane 里向用户集中提问。 |
| Unit Planner | 把需求拆成 unit、测试用例和验证命令。 |
| Test Strategist | 可选角色，独立挑战测试策略。 |
| Builder | 只实现当前 unit。 |
| CodeSimplifier / Refiner | 在不改变行为的前提下精修代码，发现问题可打回 Builder。 |
| Reviewer | 独立审查风险、缺陷和测试缺口。 |
| Verifier | 执行验证命令，产出 evidence rows。 |
| Bug Fix Agent | 处理最终验收缺陷，写 root cause 和回归证据。 |
| Human | 在 gate 处确认范围、计划和最终结果。 |

这些角色可以共用 runner，也可以通过 role runner 配置拆开。

## 一个具体例子

假设你要交付 `V1.0`：

```bash
python -m workflow_controller.cli go V1.0 --tmux-target 1.2
```

Controller 可能先生成：

```text
.rrc-controller-v1.0/approvals/requirements-and-acceptance.md
```

你审核后批准：

```bash
python -m workflow_controller.cli approve \
  --state-dir .rrc-controller-v1.0 \
  --gate requirements
```

然后生成 Unit Plan：

```text
.rrc-controller-v1.0/approvals/unit-plan.md
```

你确认 unit 和 test matrix 合理后批准：

```bash
python -m workflow_controller.cli approve \
  --state-dir .rrc-controller-v1.0 \
  --gate unit-plan
```

后面 Builder、Refiner、Reviewer、Verifier 会按状态机推进。到最终验收时，你会看到类似这样的证据矩阵：

```markdown
| AO | AC | Test Case | Layer | Status | Evidence | Expected | Artifacts |
|---|---|---|---|---|---|---|---|
| AO-001 | AC-001 | TC-001 | e2e | passed | pnpm test:e2e exit 0 | user can finish checkout | artifacts/unit-01/verification.json |
```

这时再批准 Final Acceptance：

```bash
python -m workflow_controller.cli approve \
  --state-dir .rrc-controller-v1.0 \
  --gate final-acceptance
```

如果验收发现缺陷，就拒绝并走 `defect_fix`，Controller 会生成：

```text
.rrc-controller-v1.0/approvals/bug-fix.md
.rrc-controller-v1.0/artifacts/bug-fixes/bug-fix-1/
```

修复后必须有 root cause 和 regression verification，才会回到 Final Acceptance。

## 测试和验证

项目测试命令：

```bash
python -m pytest workflow_controller/tests -q
```

当前工作树最近一次全量验证：

```text
303 passed
```

常用定向测试：

```bash
python -m pytest workflow_controller/tests/test_rrc_controller.py -q
python -m pytest workflow_controller/tests/test_rrc_human_gates.py -q
python -m pytest workflow_controller/tests/test_rrc_verifier.py -q
python -m pytest workflow_controller/tests/runners/ -q
```

## 当前边界

这个项目已经是可跑的 controller 框架，但还不是最终形态：

- Clean checkout / clean env 作为最终权威验证仍在规划中。
- 每个 unit 独立 workspace 或 branch 隔离仍在规划中。
- 更严格的 file/tool policy 仍在规划中。
- 当前 Journey evidence 已能防止很多自然语言伪通过，但在更强文件权限隔离前，恶意 agent 仍可能篡改 artifacts。
- Strict Test Presence 还会继续加强，目标是让每条非 manual AC 都必须有结构化可执行 test case。

完整路线图见 [ROADMAP.md](ROADMAP.md)。

## 项目结构

```text
workflow_controller/
  cli.py                    # CLI 入口
  rrc_controller.py          # 主控制器和流程编排
  state_machine/             # next action、state reconciliation、state store
  gates/                     # gate generator / parser / validator
  steps/                     # requirements、unit_plan、builder、bug_fix 等阶段
  prompts/                   # agent prompt 模板
  runners/                   # subprocess / tmux / codex / opencode runner
  acceptance_obligations.py  # AO ledger
  agent_guides.py            # AGENTS.md / CLAUDE.md 初始化模板
  journeys.py                # Journey contract 和 evidence 校验
  tests/                     # 单元、集成、E2E 和 runner 测试
```

## 相关文档

| 文件 | 说明 |
|---|---|
| [USAGE.md](USAGE.md) | CLI 用法、参数和故障排查。 |
| [ROADMAP.md](ROADMAP.md) | 版本规划和能力边界。 |
| [task_plan.md](task_plan.md) | 当前开发计划。 |
| [progress.md](progress.md) | 当前进度记录。 |
| [findings.md](findings.md) | 设计发现、决策和风险。 |

## 最后再说一遍

Workflow Controller 的价值不在于“让 AI 更会写代码”，而在于让 AI 写代码这件事变得可控、可恢复、可审计、可验收。

它把一次模糊的聊天式编程，变成一条能停、能看、能改、能证明的交付流程。
