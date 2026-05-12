# Waygate

[English](README.md) | [使用说明](USAGE.zh-CN.md) | [架构](docs/architecture.zh-CN.md) | [工作流](docs/workflow.zh-CN.md) | [路线图](ROADMAP.zh-CN.md)

Waygate 是一个面向 AI 编程交付的流程控制面。

它不是新的聊天机器人，也不是另一个代码生成器。Waygate 把一次 AI 编程任务放进可恢复、可审计的交付循环：需求、单元计划、实现、精修、评审、验证和最终验收。Agent 可以产出草案和代码，但不能单方面宣布完成。

## 为什么需要 Waygate

直接用 AI 聊天写代码，经常出现这些问题：

- 长对话里需求逐渐漂移；
- 模型用一句“完成了”结束，但没有持久证据；
- 测试结果只存在聊天记录里；
- 任务中断后无法可靠恢复；
- 最终验收发现问题时，不知道该回需求、回计划、回实现，还是进入 bug 修复。

Waygate 把这些状态转移显式化。状态写入磁盘，人工 gate 是 Markdown 文件，验证证据是结构化 artifact，失败会路由回正确阶段，而不是藏在聊天上下文里。

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

## 安装

构建并安装 Debian 包：

```bash
bash packaging/debian/build-deb.sh
sudo apt install ./dist/waygate_0.5.4_all.deb
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
