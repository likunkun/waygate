# Waygate

[English](README.md) | [使用说明](USAGE.zh-CN.md) | [文档入口](docs/README.md) | [架构](docs/architecture.zh-CN.md) | [工作流](docs/workflow.zh-CN.md) | [推荐环境](docs/operations/recommended-environment.zh-CN.md) | [介绍材料](docs/product/waygate-introduction-and-best-practices.zh-CN.md) | [路线图](ROADMAP.zh-CN.md)

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
| Requirements Gate | 生成人类可审阅的需求与验收标准，并执行可追溯校验，包括 V0.6.0j 基础设施缺口追问和验证留痕。 |
| 分段 Requirements Package | V0.6.2 把过载的 Requirements draft 拆成 scope、产品设计、架构和测试策略 checkpoint；V0.6.2a 确保这些 checkpoint 围绕目标产品/目标系统表面；V0.6.2b 让 Product Design 原型预览常驻到 Requirements review；V0.6.2c 使用中文主 checkpoint 名称并支持 Requirements checkpoint 定点 revise；V0.6.2d 增加多单元 handoff 连贯性硬门禁，要求下游 Builder 启动前已有上游证据；V0.6.2e 允许 `--spec` 导入真实需求文档包目录。 |
| 外部 spec intake | V0.6.1 会把受支持的 OpenSpec/OpenAPI 和 Spec Kit 来源导入为可审计 conversion artifacts；V0.6.2e 同时支持 Open Spec package directory 和 Spec Kit feature package directory，并对 unsupported/deferred 格式给出清晰错误。 |
| Unit Plan Gate | Unit Plan 必须映射目标、AC、测试用例、Journey 和验证命令。 |
| 标注 Agent | V0.6.1 支持在 Requirements、Unit Plan 和 Final Acceptance 人工 gate 前运行非批准型、按 role 配置的 annotation / verification-assist pass。 |
| Runner 支持 | 支持 subprocess、`tmux-claude`、`tmux-codex`；可以自动识别已有 tmux pane。 |
| 精修与评审 | Builder 之后可进入 CodeSimplifier/Refiner 和 Reviewer。 |
| 验证证据 | Verifier 输出结构化 evidence rows，覆盖 AC、Test Case、命令和 artifact。 |
| 灵活验收证据 | V0.6.1 保持严格命令证据确定性，同时允许带结构化 evidence refs 和 `human_review_required` 的描述型命令行。 |
| 真实 E2E 证据 | V0.6.0f 阻止带核心 API mock/stub 的浏览器测试覆盖 E2E、golden path、prototype conformance 或生产证据。 |
| Golden path 前置校验 | V0.6.0m 会在 Unit Plan 阶段阻断非真实 `layer=e2e` 的 `golden_path: true` 测试；必须有真实入口、真实环境、fixture/setup、命令和强断言。API-only/service-only E2E 不要求浏览器。 |
| 文档生命周期 | V0.6.0i 初始化 `docs/README.md`，Requirements 盘点文档来源，Unit Plan 声明文档交付，Final Acceptance 只阻断标记为 required 的文档动作。 |
| UI/UX skill policy | V0.6.0k 要求 UI/Web/prototype 工作使用 `ui-ux-pro-max`，`frontend-design` 只作为可选视觉探索或局部润色辅助。 |
| 最终验收 | Final Acceptance Gate 展示证据矩阵、Journey 覆盖、Scope Audit 和返工路由。 |
| Bug Fix Loop | 最终验收缺陷可以进入独立 bug-fix gate，不需要改写原需求。 |
| 环境检测 | V0.6.0h 扩展 `waygate doctor`，提供摘要优先输出、`focus:`、`action_required`、`--color auto|always|never`、`tmux_config`、Python、pytest、tmux、可选 agent 工具、Plannotator、Debian packaging、skill 根目录扫描、`.claude` asset 数量和与 README 对齐的推荐 skill 缺口。 |
| Debian 包 | `packaging/debian/build-deb.sh` 可构建 `waygate` 命令包。 |

## 本地依赖

Waygate 以 Python 3 代码运行。本地开发和验证使用 `python -m pytest workflow_controller/tests -q`，因此 Python 环境中需要安装 `pytest`。

真实 agent 执行依赖所选 runner：

- `tmux-claude` 需要 `tmux` 和 Claude Code。未指定 pane 时，Waygate 可以在 tmux 中创建 Claude Code pane。
- `tmux-codex` 需要 `tmux` 和已有 Codex pane。Waygate 可以在当前 tmux session 中发现匹配的 Codex pane。
- `waygate doctor` 会检查 `~/.tmux.conf` 中是否包含推荐的 `mouse on`、`history-limit 100000`、`@scroll-speed 5` 和 `@copy-mode-vi` 配置；它只报告 manual action，不会修改或 reload 你的 tmux 配置。
- Plannotator 是可选但推荐的浏览器人工 gate 审阅工具，可通过 `--plannotator-command` 和 `--plannotator-port` 配置。Waygate 默认把 review 服务绑定到 `0.0.0.0`，但终端展示的浏览器 URL 会使用本机主 IP 地址；controller preview 固定使用 `20001` 端口，并通过 `PLANNOTATOR_REMOTE=1` 请求 Plannotator 开启远程访问。
- 项目需要的 agent skills 由 agent runtime 加载，不由 Debian 包安装；`waygate doctor` 会扫描常见本地 skill 根目录并给出建议性缺口提示。
- Debian package 构建需要标准 shell 工具和 `dpkg-deb`。

Waygate Markdown spec intake 仍可通过 `init`、`start`、`go` 的 `--spec <path>` 使用。`--spec` 也接受 Open Spec package directory（包含 `01-requirements.md`，并至少包含 `02-specification.md` 等一个支撑文档）和 Spec Kit feature package directory（包含 `spec.md`，并有 `plan.md`、`tasks.md` 或 `contracts/` 等 feature companion）。`.specify` 工具/工作区根目录和普通 docs 目录会被拒绝，并提示传入 `specs/<feature>/` 或具体 `spec.md`。V0.6.1 还支持受支持 OpenSpec/OpenAPI 输入；识别到但 unsupported 或 deferred 的格式会清晰失败，不会被静默导入。

V0.6.2 staged Requirements package 规则见 [docs/workflow/staged-requirements-package-policy.md](docs/workflow/staged-requirements-package-policy.md) 和 [docs/architecture/staged-requirements-package-architecture.md](docs/architecture/staged-requirements-package-architecture.md)。V0.6.1 外部 spec intake、annotation、提示词合同和灵活验收证据规则见 [docs/workflow/external-spec-intake-and-annotation-policy.md](docs/workflow/external-spec-intake-and-annotation-policy.md) 和 [docs/architecture/external-spec-intake-and-annotation-architecture.md](docs/architecture/external-spec-intake-and-annotation-architecture.md)。V0.6.0m golden-path E2E 前置校验和 V0.6.2 Requirements E2E 审阅规则见 [docs/workflow/requirements-e2e-review-policy.md](docs/workflow/requirements-e2e-review-policy.md)。V0.6.0j Requirements 基础设施追问与验证规则见 [docs/workflow.zh-CN.md](docs/workflow.zh-CN.md)。V0.6.0k UI/UX skill policy 见 [docs/workflow/ui-ux-skill-policy.md](docs/workflow/ui-ux-skill-policy.md)。V0.6.0i 文档生命周期入口见 [docs/README.md](docs/README.md)。V0.6.0h 推荐环境见 [docs/operations/recommended-environment.zh-CN.md](docs/operations/recommended-environment.zh-CN.md)。面向同学讲解的介绍与最佳实践材料见 [docs/product/waygate-introduction-and-best-practices.zh-CN.md](docs/product/waygate-introduction-and-best-practices.zh-CN.md)。

## Waygate Agent 使用的 Skills

Waygate 不会把 skills 自动安装进 Claude Code、Codex 或其他 agent runtime。它假设你选择的 agent 环境已经安装了任务需要的 skills。Controller 负责让流程可审计，skills 负责让不同 agent 角色更擅长自己的工作。

`test-strategy` 是比较小众的外部 skill，不随 Waygate Debian 包内置安装。需要在每个会使用它的 agent runtime 环境中单独安装，来源为 `AbsolutelySkilled/AbsolutelySkilled`：

```bash
npx skills add AbsolutelySkilled/AbsolutelySkilled --skill test-strategy
```

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
| `ui-ux-pro-max` | UI/Web/prototype 需求 | UI、Web、可点击原型、prototype evidence 和生产 UI 一致性工作必须使用；`frontend-design` 只能辅助全新视觉探索或局部润色，不能替代 `ui-ux-pro-max`。 |
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
waygate doctor
```

V0.6.0h 的 `waygate doctor` 会先输出 `summary:`、`focus:` 和 `action_required:`，把最高优先级风险和需要人工处理的事项放在详细清单前面。使用 `waygate doctor --color auto|always|never` 可以给状态、P1 关注项、action 和 section 标题上色，方便人工扫描；非 TTY 输出默认保持纯文本。它还会输出安装来源、环境检测、`tmux_config`、`skill_recommendations` 和 `claude_assets`。如果它显示 `~/.local/bin/waygate` 这类用户级 wrapper 排在 `/usr/bin/waygate` 前面，请手工改名或删除该用户级文件，然后执行 `hash -r`。Debian 包会提示 shadow 风险，但不会删除用户文件。

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
| 推荐环境 | [docs/operations/recommended-environment.md](docs/operations/recommended-environment.md) | [docs/operations/recommended-environment.zh-CN.md](docs/operations/recommended-environment.zh-CN.md) |
| 介绍与最佳实践 | [docs/product/waygate-introduction-and-best-practices.md](docs/product/waygate-introduction-and-best-practices.md) | [docs/product/waygate-introduction-and-best-practices.zh-CN.md](docs/product/waygate-introduction-and-best-practices.zh-CN.md) |
| 路线图 | [ROADMAP.md](ROADMAP.md) | [ROADMAP.zh-CN.md](ROADMAP.zh-CN.md) |

`task_plan.md`、`progress.md` 和 `findings.md` 是本仓库开发历史文件，对维护者有用，但使用 Waygate 不依赖它们。

## 项目状态

Waygate 仍在快速演进。当前实现适合本地受控流程：为 AI 编程任务提供持久状态、gate 文档和验证 artifact。它还不是托管服务，也还没有完成 per-role 文件写入策略和 clean verification 隔离。

后续计划见 [ROADMAP.zh-CN.md](ROADMAP.zh-CN.md)。

## 贡献

欢迎 issue 和 pull request。提交前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

Waygate 使用 [MIT License](LICENSE) 发布。
