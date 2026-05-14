# Waygate

[English](README.md) | [使用说明](USAGE.zh-CN.md) | [架构](docs/architecture.zh-CN.md) | [工作流](docs/workflow.zh-CN.md) | [路线图](ROADMAP.zh-CN.md)

Waygate 是一个面向 AI 编程交付的流程控制面。

它不是新的聊天机器人，也不是另一个代码生成器。Waygate 把一次 AI 编程任务放进可恢复、可审计的交付循环：需求、单元计划、实现、精修、评审、验证和最终验收。Agent 可以产出草案和代码，但不能单方面宣布完成。

## 为什么需要 Waygate

直接用 AI 聊天写代码，经常出现这些问题：

- AI 偷懒：只做容易的一部分，剩下的默认跳过，还会说“完成了”。
- 只做功能，不做场景：接口或页面看起来有了，但真实用户路径、边界条件、验收路径没有覆盖。
- 全过程都需要人参与：人一直在回“继续”，因为流程没有稳定的下一步和完成信号。
- 结果和预期不一样：最后看起来偏了，但很难追溯是需求、计划、实现还是验证阶段开始漂移。
- 多项目并行时人会被绕晕：多个项目、多个 pane、多个 agent、多个上下文混在一起，人被迫承担流程记忆和状态管理。

Waygate 的目标是把 AI 编程从长聊天变成受控交付流程。它把“帮我做这个”拆成明确 gate：需求、Unit Plan、实现、精修、评审、验证和最终验收。每个 gate 都落盘，每条验收标准都要对应证据，失败会回到正确阶段，而不是藏在聊天记录里。

Waygate 不是要把人移出流程，而是把人的注意力放回真正重要的判断：确认需求、审查范围、接受证据、选择返工路线。重复的 controller 工作由 Waygate 处理，状态写在磁盘上，agent 想跳过工作但声称完成会更难。

## 当前能力

| 能力 | 说明 |
| --- | --- |
| 可恢复工作流 | `session.json`、`events.jsonl`、approvals 和 artifacts 是事实源。 |
| Requirements Gate | 生成人类可审阅的需求与验收标准，并执行可追溯校验。 |
| Unit Plan Gate | Unit Plan 必须映射目标、AC、测试用例、Journey 和验证命令。 |
| Runner 支持 | 支持 subprocess、`tmux-claude`、`tmux-codex`；可以自动识别已有 tmux pane。 |
| 精修与评审 | Builder 之后可进入 CodeSimplifier/Refiner 和 Reviewer。 |
| 验证证据 | Verifier 输出结构化 evidence rows，覆盖 AC、Test Case、命令和 artifact。 |
| 最终验收 | Final Acceptance Gate 展示证据矩阵、Journey 覆盖、Scope Audit 和返工路由。 |
| Bug Fix Loop | 最终验收缺陷可以进入独立 bug-fix gate，不需要改写原需求。 |
| Debian 包 | `packaging/debian/build-deb.sh` 可构建 `waygate` 命令包。 |

## 本地依赖

Waygate 以 Python 3 代码运行。本地开发和验证使用 `python -m pytest workflow_controller/tests -q`，因此 Python 环境中需要安装 `pytest`。

真实 agent 执行依赖所选 runner：

- `tmux-claude` 需要 `tmux` 和 Claude Code。未指定 pane 时，Waygate 可以在 tmux 中创建 Claude Code pane。
- `tmux-codex` 需要 `tmux` 和已有 Codex pane。Waygate 可以在当前 tmux session 中发现匹配的 Codex pane。
- Plannotator 是可选但推荐的浏览器人工 gate 审阅工具，可通过 `--plannotator-command` 和 `--plannotator-port` 配置。
- 项目需要的 agent skills 由 agent runtime 加载，不由 Debian 包安装；请在 agent 环境中安装所需 skills。
- Debian package 构建需要标准 shell 工具和 `dpkg-deb`。

Waygate Markdown spec intake 可通过 `init`、`start`、`go` 的 `--spec <path>` 使用。V0.5.6 只支持本地 Waygate Markdown spec 文件；识别到的外部格式会明确 deferred，不会被静默导入。

## Waygate Agent 使用的 Skills

Waygate 不会把 skills 自动安装进 Claude Code、Codex 或其他 agent runtime。它假设你选择的 agent 环境已经安装了任务需要的 skills。Controller 负责让流程可审计，skills 负责让不同 agent 角色更擅长自己的工作。

推荐基线 skills：

| Skill | 阶段 | 作用 |
| --- | --- | --- |
| `planning-with-files` | 项目初始化、长任务、`/clear` 后恢复 | 用 `task_plan.md`、`progress.md`、`findings.md` 做持久项目记忆，避免多步骤工作依赖单次聊天上下文。 |
| `superpowers:using-superpowers` | Agent 启动 | 要求 agent 行动前检查适用 skill，减少无结构的自由发挥。 |
| `superpowers:brainstorming` | 需求发现和范围收敛 | 把模糊目标变成明确需求，再进入实现。 |
| `superpowers:writing-plans` | Unit Plan / 实施计划 | 需求明确后生成可执行的逐步实施计划。 |
| `superpowers:test-driven-development` | Builder 和 bug-fix | 行为变更先写失败测试，再实现。 |
| `superpowers:systematic-debugging` | 测试失败、Verifier 失败、runner 异常 | 修复前先找根因，尤其适合 controller、runner、agent 状态交互的问题。 |
| `test-strategy` 或 `testing-strategy` | Requirements 和 Unit Plan 测试矩阵 | 设计真正有意义的 verification layer，避免只靠 lint/typecheck 证明行为。 |
| `code-simplifier` | Builder 后的 Refiner 阶段 | 在不改变行为的前提下检查最近实现的清晰度和可维护性。 |
| `superpowers:verification-before-completion` | DONE、review、release、final acceptance 前 | 防止没有新鲜证据就声称完成。 |
| `superpowers:requesting-code-review` 和 `superpowers:receiving-code-review` | Reviewer 和返工循环 | 让 review finding 更具体，也避免盲目接受不严谨反馈。 |
| `superpowers:executing-plans` 或 `superpowers:subagent-driven-development` | 执行已批准的多步骤计划 | 按书面计划逐项执行，并保留 checkpoint 和 review 边界。 |
| `webapp-testing` | 浏览器可见 UI 或流程验证 | 需要验证前端行为时，用 Playwright 类检查、截图和浏览器日志形成证据。 |
| `frontend-design` 或 `ui-ux-pro-max` | UI 密集型需求 | 目标包含前端时，用于界面设计、交互状态、布局和可访问性。 |
| `pdf`、`docx`、`pptx` | 文档类任务 | 只有项目需求涉及对应文件类型时才使用。 |

常见阶段映射：

```text
Requirements Draft        -> brainstorming, planning-with-files
Requirements Gate         -> test-strategy/testing-strategy when ACs need test design
Unit Plan                 -> writing-plans, test-strategy/testing-strategy
Builder                   -> test-driven-development, systematic-debugging when failures appear
Refiner                   -> code-simplifier
Reviewer                  -> requesting-code-review / receiving-code-review
Verifier                  -> verification-before-completion, webapp-testing for browser flows
Final Acceptance / Rework -> systematic-debugging, executing-plans or subagent-driven-development
Long sessions             -> planning-with-files throughout
```

## 安装

构建并安装 Debian 包：

```bash
bash packaging/debian/build-deb.sh
sudo apt install ./dist/waygate_*_all.deb
waygate --help
```

源码调试入口：

```bash
cd /path/to/workflow-controller
python -m workflow_controller.cli --help
```

开发时使用的测试环境：

```bash
python -m pytest workflow_controller/tests -q
```

## 快速开始

在目标项目根目录运行：

```bash
waygate go V1.0
```

它会创建或继续：

```text
<target-project>/.rrc-controller-v1.0/
```

在 tmux 里，Waygate 可以创建或识别 agent pane。如果已经有 Codex 或 Claude pane，可以显式传入：

```bash
waygate go V1.0 --tmux-target 1.2
```

强制使用本地 subprocess：

```bash
waygate go V1.0 --runner subprocess
```

只试流程、不调用真实 agent：

```bash
waygate go V1.0 --runner subprocess --dry-run --max-steps 20
```

完整 CLI 见 [USAGE.zh-CN.md](USAGE.zh-CN.md)。

## 工作流

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
  -> Agent Status Sync
  -> Done
```

最终验收发现缺陷时，可以进入：

```text
Bug Fix Gate
  -> Bug Fix Agent
  -> Regression Verifier
  -> Final Acceptance Gate
```

详细流程见 [docs/workflow.zh-CN.md](docs/workflow.zh-CN.md)。

## 仓库结构

```text
workflow_controller/
  cli.py                     # CLI 入口
  rrc_controller.py          # 主编排层
  gates/                     # Gate 生成、解析、校验
  prompts/                   # 各角色 prompt 构造
  runners/                   # subprocess 和 tmux runner
  state_machine/             # 状态存储与状态转移
  steps/                     # 工作流步骤实现
  tests/                     # pytest 测试

packaging/debian/            # Debian 包构建脚本
docs/                        # 架构和流程文档
```

## 文档

| 文档 | English | 中文 |
| --- | --- | --- |
| README | [README.md](README.md) | [README.zh-CN.md](README.zh-CN.md) |
| CLI 使用 | [USAGE.md](USAGE.md) | [USAGE.zh-CN.md](USAGE.zh-CN.md) |
| 架构 | [docs/architecture.md](docs/architecture.md) | [docs/architecture.zh-CN.md](docs/architecture.zh-CN.md) |
| 工作流 | [docs/workflow.md](docs/workflow.md) | [docs/workflow.zh-CN.md](docs/workflow.zh-CN.md) |
| 路线图 | [ROADMAP.md](ROADMAP.md) | [ROADMAP.zh-CN.md](ROADMAP.zh-CN.md) |

`task_plan.md`、`progress.md` 和 `findings.md` 是本仓库开发历史文件，对维护者有用，但使用 Waygate 不依赖它们。

## 项目状态

Waygate 仍在快速演进。当前实现适合本地受控流程：为 AI 编程任务提供持久状态、gate 文档和验证 artifact。它还不是托管服务，也还没有完成 per-role 文件写入策略和 clean verification 隔离。

后续计划见 [ROADMAP.zh-CN.md](ROADMAP.zh-CN.md)。

## 贡献

欢迎 issue 和 pull request。提交前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

Waygate 使用 [MIT License](LICENSE) 发布。
