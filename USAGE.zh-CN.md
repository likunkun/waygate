# Waygate 使用说明

[English](USAGE.md) | [README](README.zh-CN.md)

本文是 Waygate 的 CLI 使用说明。概念和架构见 [docs/workflow.zh-CN.md](docs/workflow.zh-CN.md) 与 [docs/architecture.zh-CN.md](docs/architecture.zh-CN.md)。

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
sudo apt install ./dist/waygate_0.6.0c_all.deb
waygate --help
waygate doctor
```

`waygate doctor` 会输出当前 executable path、导入的 module path、module version、已安装 dpkg version，以及 `PATH` 中所有 `waygate` 候选。如果它显示 `~/.local/bin/waygate` 排在 `/usr/bin/waygate` 前面，请手工改名或删除该用户级 wrapper，然后执行 `hash -r`。

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
```

## Prototype Review Bundle

对 UI/UX 或 Web 系统需求，Requirements drafter 必须写出 `artifacts/requirements-draft/prototype-manifest.json`。Waygate 会校验 manifest，把本地图片/HTML 原型复制到 `artifacts/requirements-draft/prototypes/`，渲染 `plannotator-review.md`，并在 Plannotator 中打开这个 review bundle。批准状态仍然只落在 `approvals/requirements-and-acceptance.md`。

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

打印安装来源和 PATH 诊断信息。该命令不读取 controller state。

```bash
waygate doctor
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
```

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
