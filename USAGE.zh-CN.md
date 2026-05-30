# Waygate 使用说明

[English](USAGE.md) | [README](README.zh-CN.md)

本文是 Waygate 的 CLI 使用说明。概念、架构、V0.6.2 staged Requirements package policy、V0.6.1 external spec intake 与 annotation policy、V0.6.0m golden-path E2E 前置校验、V0.6.0j Requirements 基础设施追问与验证规则、V0.6.0k UI/UX skill policy，以及 V0.6.0i 文档生命周期入口见 [docs/README.md](docs/README.md)、[docs/workflow.zh-CN.md](docs/workflow.zh-CN.md)、[docs/workflow/staged-requirements-package-policy.md](docs/workflow/staged-requirements-package-policy.md)、[docs/workflow/external-spec-intake-and-annotation-policy.md](docs/workflow/external-spec-intake-and-annotation-policy.md)、[docs/workflow/requirements-e2e-review-policy.md](docs/workflow/requirements-e2e-review-policy.md)、[docs/workflow/ui-ux-skill-policy.md](docs/workflow/ui-ux-skill-policy.md)、[docs/architecture/staged-requirements-package-architecture.md](docs/architecture/staged-requirements-package-architecture.md) 与 [docs/architecture/external-spec-intake-and-annotation-architecture.md](docs/architecture/external-spec-intake-and-annotation-architecture.md)。

V0.6.0h 环境准备见 [docs/operations/recommended-environment.zh-CN.md](docs/operations/recommended-environment.zh-CN.md)。介绍与最佳实践讲解材料见 [docs/product/waygate-introduction-and-best-practices.zh-CN.md](docs/product/waygate-introduction-and-best-practices.zh-CN.md)。

V0.6.0f 收紧浏览器验收证据：mock/stub 核心业务 API 的 Playwright 或浏览器测试不能作为 E2E、golden path、prototype conformance 或生产就绪证据。

V0.6.0m 会更早阻断 golden path E2E 错误：Unit Plan approval 会拒绝 `golden_path: true` 但不是 `layer=e2e`、缺真实入口、使用 mock 环境、缺 fixture/setup、命令未进入 `verification_commands` 或断言过弱的 test case。API-only 或 service-only E2E 可以使用 pytest/API/service 命令，不要求浏览器字段。

V0.6.1 增加 OpenSpec/OpenAPI 和 Spec Kit spec intake、人工 gate 前的非批准型 annotation / verification-assist pass，以及带 `human_review_required` 的灵活 verifier evidence rows。

V0.6.2 将 Requirements draft 拆成 scope、产品设计、架构和测试策略 checkpoint，再装配成一个带 checkpoint hash 的最终 Requirements approval package。V0.6.2a 新增目标产品表面分类，确保 staged Product Design 和 Architecture 围绕目标产品/目标系统。V0.6.2b 在 Product Design 成功后启动常驻原型预览，并让该 URL 一直可用于 Requirements review。V0.6.2c 使用中文主 checkpoint 名称，并支持 Requirements checkpoint 定点 revise。

## 环境准备

Waygate 本身是 Python 代码，并提供 Debian 包。真实 agent 执行依赖你选择的 runner：

| Runner | 依赖 |
| --- | --- |
| `subprocess` | 一个可以执行 agent 任务的本地命令。 |
| `tmux-claude` | `tmux` 和 Claude Code pane，或允许 Waygate 创建一个。 |
| `tmux-codex` | `tmux` 和已有 Codex pane。 |
| `dry-run` | 不需要真实 agent；会生成 mock artifacts。 |

构建并安装：

```bash
bash packaging/debian/build-deb.sh
sudo apt install ./dist/waygate_0.6.2c_all.deb
waygate --help
waygate doctor
waygate doctor --color auto
```

`waygate doctor` 会先输出 `summary:`、`focus:` 和 `action_required:`，再输出详细清单。`focus:` 层会把人工最该先看的事项分组前置，例如 P1 tmux 配置修复、安装来源风险、环境风险和 skill 缺口。使用 `--color auto|always|never` 可以高亮状态、P1 关注项、manual action 和 section 标题；非 TTY 输出默认保持纯文本。它会报告当前 executable path、导入的 module path、module version、已安装 dpkg version、`PATH` 中所有 `waygate` 候选，Python、pytest、tmux、Claude Code、Codex、Plannotator、`dpkg-deb` 等环境检测，针对 `~/.tmux.conf` 的 `tmux_config` 检查，skill 根目录扫描、已安装 skills、与 README 对齐的推荐 workflow skill 缺口、`claude_assets`，以及推荐 Plannotator port。Waygate runner 仍需要可用的 `claude` 或 `codex` CLI。如果它显示 `~/.local/bin/waygate` 排在 `/usr/bin/waygate` 前面，请手工改名或删除该用户级 wrapper，然后执行 `hash -r`。

源码运行：

```bash
python -m workflow_controller.cli --help
```

## 推荐入口：`go`

在目标项目根目录运行：

```bash
waygate go V1.0
```

`go` 会推断常用参数：

| 字段 | 默认值 |
| --- | --- |
| `target` | 位置参数，例如 `V1.0`。 |
| `workspace-dir` | 当前目录；如果传了 `--workspace-dir` 或 `--tmux-target`，会使用更明确的来源。 |
| `state-dir` | `<workspace-dir>/.rrc-controller-<target>`。 |
| runner | tmux 内无 target 时自动创建 Claude pane；传 `--tmux-target` 时自动识别 Claude 或 Codex。 |

常用示例：

```bash
# 创建或继续一个 target session。
waygate go V1.0

# 使用已有 tmux pane；Waygate 自动识别 Claude 或 Codex。
waygate go V1.0 --tmux-target 1.2

# 显式使用已有 Codex pane。未传 target 时，
# Waygate 会在当前 tmux session 中寻找匹配的 Codex pane。
waygate go V1.0 --runner tmux-codex

# 不使用 tmux。
waygate go V1.0 --runner subprocess

# 模拟完整流程。
waygate go V1.0 --runner subprocess --dry-run --max-steps 20

# 从目标项目外部启动。
waygate go V1.0 --workspace-dir /path/to/target-project

# 从受支持的 Waygate Markdown requirements spec 启动。
waygate go V1.0 --spec ./requirements.md

# 为全部审阅 role 启用非批准型 Codex 标注 Agent。
waygate go V0.6.1 --annotation-agent codex

# 只启用 Unit Plan 标注 role。
waygate go V0.6.1 --annotation-agent unit-plan=codex
```

如果上一轮 agent 派发因 timeout 或 idle-without-DONE 停止，使用同一个 target 或 `--state-dir` 再运行 `waygate go ...`。Waygate 会从 `session.json` 读取 `recoverableAgentWait`，记录自动恢复事件，并继续同一阶段。显式 `blocked` 状态不同：交互式 `go`、`drive`、`start` 可以打开 Blocked Assist 做诊断，但只有人工选择的 route 会改变状态。外部条件修好后用 `unblock`；批准合同需要变更时用 `revise` 或 Final Acceptance rejection route。

## Prototype Review Bundle

对 UI/UX 或 Web 系统需求，Requirements drafter 必须写出 `artifacts/requirements-draft/prototype-manifest.json`。Waygate 会校验 manifest，把本地图片/HTML 原型复制到 `artifacts/requirements-draft/prototypes/`，并渲染 `plannotator-review.md` 与 `plannotator-review.html`。Plannotator 审批/批注的主文件是 `approvals/requirements-and-acceptance.md`；HTML bundle 只作为当前 review session 中的原型渲染辅助预览 URL。

Waygate 默认把 review 服务绑定到 `0.0.0.0`，并用本机主 IP 地址展示 Plannotator 审批页和原型预览页。Plannotator 使用 `20000` 端口；controller prototype preview server 固定使用 `20001` 端口，便于提前申请 ACL。`--plannotator-port` 可以调整 Plannotator 端口，`WAYGATE_PREVIEW_PORT` 可以调整 controller preview 端口，`WAYGATE_DISPLAY_HOST` 可以覆盖终端展示的浏览器 host，`WAYGATE_PREVIEW_HOST` 可以覆盖 controller preview bind host。Waygate 通过 `PLANNOTATOR_REMOTE=1` 请求 Plannotator 开启远程访问。

manifest 必须把每个原型映射到真实 AC ID，并包含页面状态和点击路径。带 `token`、`password`、`secret`、`api_key`、`signature` 等敏感 query key 的 URL 会被拒绝。

## 两步模式

需要先检查初始化状态时，可以先 `init` 再 `drive`：

```bash
waygate init \
  --state-dir .rrc-controller-v1.0 \
  --workspace-dir . \
  --target V1.0 \
  --spec ./requirements.md \
  --runner tmux-claude \
  --tmux-target 1.2

waygate drive --state-dir .rrc-controller-v1.0
```

## 子命令

### `init`

创建 `session.json`、`approvals/`、`artifacts/` 和初始 target state。

```bash
waygate init --target V1.0 --workspace-dir . --spec ./requirements.md
```

`--spec <path>` 当前只导入可读的本地 Waygate Markdown spec 文件。Waygate 会在 `session.json` 中保存 path、SHA-256 hash、source type 和 import time，不保存 spec 全文。OpenSpec 和 Spec Kit 路径会被识别为后续 external spec intake，并在当前版本明确拒绝或 deferred。

### Annotation Agent 选项

Annotation Agent 默认关闭。只有需要在人工审阅前生成风险提示时才启用：

```bash
waygate go V0.6.1 --annotation-agent codex
waygate init --target V0.6.1 --annotation-agent unit-plan=codex
waygate drive --state-dir .rrc-controller-v0.6.1 --annotation-agent unit-plan=codex --annotation-agent-cmd unit-plan='python3 fake.py'
```

支持的 role alias 是 `requirements`、`unit-plan`、`final-acceptance` 和 `all`。支持的 backend 是 `codex`、`claude-code`（也接受 `claude`）和 `opencode`。Annotation subprocess 会在父进程存在时默认继承标准代理 key：`HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`、`NO_PROXY` 及对应小写形式。可用 `--no-annotation-agent ROLE|all` 禁用 role，`--annotation-agent-env-key ROLE=KEY` 继承额外非代理环境变量名，`--annotation-agent-timeout ROLE=SECONDS` 设置超时，`--annotation-agent-failure-policy ROLE=block|warn` 设置失败策略。

内置 `--annotation-agent codex` 会启用三个 role，使用 `command=codex`、`args=["exec", "--sandbox", "workspace-write", "-o", "{artifact_path}", "..."]`、`timeout_seconds=7200`、`failure_policy=block` 和 `prompt_template=risk-json-v1`。Annotation 输出只能辅助标注风险，不能批准、跳过、修改或绕过任何 Waygate gate。Waygate 旧内置 Codex annotation args 会自动归一化；自定义 `--annotation-agent-cmd` 不会被改写。

Annotation Agent 作为 controller 侧 subprocess 运行，不会显示在 tmux builder pane。进入人工 gate 前，controller pane 会打印 `标注 Agent 开始：角色=requirements_annotation 后端=codex 产物=<path>`、`标注 Agent 完成：角色=requirements_annotation 返回码=0 用时=<duration>` 或 `标注 Agent 失败：角色=requirements_annotation 错误=<summary> 产物=<path> 用时=<duration>` 这类紧凑中文生命周期行；`--color always` 和 TTY 下的 `--color auto` 会给 Agent 标签与状态上色，`--color never` 保持纯文本。stdout/stderr 仍只写入 artifact 和 event。当 fresh annotation artifact 与当前 gate body 匹配后，人工 gate 菜单会显示 artifact 路径、风险数量和中文紧凑摘要，Plannotator review metadata 也会记录同一个 artifact 引用。人类可见批注字段必须是简体中文；英文-only 的 `summary` 或风险 message 会被拒绝，不会作为当前批注展示。Requirements 修订会重新运行 Requirements annotation，artifact 会记录 `gate_content_hash` 和 `human_language=zh-CN`，因此旧 gate body 或旧 prompt 合同的 annotation 不会被当作当前审阅上下文复用。

### `start`

如有需要先初始化，然后持续驱动 workflow。

```bash
waygate start --state-dir .rrc-controller-v1.0 --spec ./requirements.md
```

### `drive`

继续已有 session，直到人工 gate、终态或步数上限。

```bash
waygate drive --state-dir .rrc-controller-v1.0
```

### `run`

推进一步，或通过 `--until-done` 跑到终态。

```bash
waygate run --state-dir .rrc-controller-v1.0
waygate run --state-dir .rrc-controller-v1.0 --until-done
```

### `status`

打印当前工作流状态。

```bash
waygate status --state-dir .rrc-controller-v1.0
```

### `doctor`

打印安装来源、PATH、环境和 skill 检测信息。该命令不读取 controller state 或 controller artifacts。

```bash
waygate doctor
waygate doctor --color always
```

### `approve`

人工审阅 Markdown gate 后批准。

```bash
waygate approve --state-dir .rrc-controller-v1.0 --gate requirements
waygate approve --state-dir .rrc-controller-v1.0 --gate unit-plan
waygate approve --state-dir .rrc-controller-v1.0 --gate final-acceptance
```

最终验收批准会在下一次 `run`、`drive`、`start` 或 `go` 推进时处理。如果配置了 live tmux agent pane，Waygate 会在 release 前派发最终状态同步 prompt，让 agent 更新 `task_plan.md`、`progress.md` 和 `findings.md`。

### `revise`

在 feedback 已写入 gate 后，让 agent 重新生成 Requirements 或 Unit Plan。

```bash
waygate revise --state-dir .rrc-controller-v1.0 --gate unit-plan
waygate revise --state-dir .rrc-controller-v1.0 --gate requirements --checkpoint product-design --reason "补产品原型和页面状态"
```

对 staged Requirements package，`--checkpoint` 可定点回到 `scope`、`product-design`、`architecture` 或 `test-strategy`；也接受中文别名 `需求范围`、`产品设计`、`技术架构`、`测试策略`。不传 `--checkpoint` 时，`--reason` 继续走语义路由推断 checkpoint。`--checkpoint` 只适用于 `--gate requirements`。

blocked 恢复菜单进入 Unit Plan 或 Requirements 返工前，会要求填写非空人工原因。Blocked Assist summary 只能作为上下文，不能替代人工确认的 `human_reason`。

### `reject`

拒绝最终验收，并选择返工路由。

```bash
waygate reject --state-dir .rrc-controller-v1.0
```

### `migrate`

升级旧 gate 文件格式。

```bash
waygate migrate --state-dir .rrc-controller-v1.0
```

## 关键参数

| 参数 | 含义 |
| --- | --- |
| `--state-dir` | Controller state 目录。 |
| `--workspace-dir` | 目标项目目录。 |
| `--target` / 位置参数 | 验收目标标签。 |
| `--runner` | `subprocess`、`tmux-claude` 或 `tmux-codex`。 |
| `--tmux-target` | 已有 tmux pane，例如 `1.2` 或 `%43`。 |
| `--agent` | runner 使用的 agent 命令。 |
| `--dry-run` | 生成 mock artifacts，不调用真实 agent。 |
| `--max-steps` | 自动执行步数上限。 |
| `--auto-approve` | 在测试或受控运行中自动生成低风险 approval artifact。 |
| `--annotation-agent BACKEND` | 为全部 role 启用同一个非批准型 annotation backend。 |
| `--annotation-agent ROLE=BACKEND` | 只启用一个 annotation role；可重复。 |
| `--no-annotation-agent ROLE|all` | 禁用一个 annotation role 或全部 role。 |
| `--annotation-agent-cmd ROLE='COMMAND ...'` | 覆盖完整 annotation 命令行，使用 `shlex.split` 解析。 |
| `--annotation-agent-env-key ROLE=KEY` | 继承额外非代理环境变量名；标准代理 key 在父进程存在时默认继承，secret 值不写入 state。 |
| `--annotation-agent-timeout ROLE=SECONDS` | 覆盖 role 超时时间。 |
| `--annotation-agent-failure-policy ROLE=block|warn` | 设置 annotation 失败是阻断人工 gate 还是只写 warning evidence。 |
| `--verbose` | 打印详细执行输出。 |
| `--color auto|always|never` | 控制 compact 输出高亮。 |

## tmux runner 说明

传入 `--tmux-target` 时，Waygate 会探测 pane command、title、process tree 和可见输出，判断是 Claude 还是 Codex。

传 `--runner tmux-codex` 但不传 `--tmux-target` 时，Waygate 会在当前 tmux session 中寻找已有 Codex pane，并优先选择当前路径匹配目标 workspace 的 pane。Waygate 不会自动创建 Codex pane。

自动创建 Claude pane 时默认命令是：

```bash
claude --permission-mode bypassPermissions
```

可以通过环境变量覆盖：

```bash
export WAYGATE_AUTO_CLAUDE_PERMISSION_MODE=acceptEdits
export WAYGATE_AUTO_CLAUDE_COMMAND='claude --permission-mode dontAsk --model sonnet'
```

## State 目录

一个 session 目录大致如下：

```text
.rrc-controller-v1.0/
  session.json
  events.jsonl
  change_requests.jsonl
  approvals/
    requirements-and-acceptance.md
    unit-plan.md
    final-acceptance.md
  artifacts/
    requirements-draft/
    unit-plan-draft/
    <unit-id>/
```

不要提交 `.rrc-controller-*` 目录。它们是本地运行状态，可能包含项目相关 artifact。

## 测试

运行全量测试：

```bash
python -m pytest workflow_controller/tests -q
```

运行打包验证：

```bash
python -m pytest workflow_controller/tests/test_packaging.py -q
```

## 故障排查

| 现象 | 检查项 |
| --- | --- |
| `requires --tmux-target` | 当前不在 tmux 中，或没有发现匹配 Codex pane。显式传 `--tmux-target`。 |
| Gate 反复被打回 | 查看 `artifacts/*/controller-validation-error.json`。 |
| Verifier 连续失败 | 查看 `verification.json` 和失败命令输出。 |
| Agent 过早写 `done.json` | 查看 tmux runner metadata 和 events 中的 post-done busy 状态。 |
| target 状态不符合预期 | 确认 `--workspace-dir`、`--state-dir` 和已有 `session.json` 匹配。 |
